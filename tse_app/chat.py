from __future__ import annotations

import json
import time
from collections.abc import Iterator

import requests

from .config import URL_CHAT, ler_chaves, modelo_usado
from .escopo import Escopo
from .store import FonteDados

SISTEMA = (
    "Você é um analista eleitoral do projeto Brazil TSE Data Science. "
    "Responda sempre em português do Brasil, de forma direta e objetiva (no máximo ~250 palavras), "
    "usando SOMENTE os dados do contexto fornecido para a região selecionada. "
    "Cite números concretos (votos, percentuais, correlações) e compare com o que o contexto traz. "
    "Se a informação necessária não estiver no contexto, diga claramente que não há dado disponível "
    "para aquele recorte em vez de inventar. Use markdown simples (tópicos e negrito). "
    "GRANULARIDADE: o TSE não publica votação por bairro; a menor granularidade são as ZONAIS "
    "e, nas eleições de 2024 e 2026, as SEÇÕES ELEITORAIS (use a lista de seções do contexto "
    "quando presente). Quando perguntarem sobre bairros, use a lista bairro→zona do contexto "
    "(quando presente — é uma aproximação via locais de votação geocodificados do OSM) "
    "e avise que é uma aproximação, citando as zonas e os votos nelas. "
    "Quando pedirem os eleitos, use a lista 'Eleitos' do contexto (candidato, partido e votos "
    "no recorte), distinguindo prefeito/vereador (municipais 2024) dos cargos gerais de 2026."
)

LIMITE_HISTORICO = 6
MAX_TOKENS_SAIDA = 1400


class ChatErro(RuntimeError):
    """Erro de comunicação com o Ollama Cloud (chaves esgotadas, modelo indisponível etc.)."""


class ClienteOllama:
    """Cliente do Ollama Cloud com rotação de chaves para diluir a cota gratuita."""

    def __init__(self, chaves: list[str] | None = None, modelo: str | None = None):
        self.chaves = chaves if chaves is not None else ler_chaves()
        self.modelo = modelo or modelo_usado()
        self._rotacao = 0
        self._esfriando: dict[str, float] = {}
        self.tokens_entrada = 0
        self.tokens_saida = 0
        self.requisicoes = 0
        self.ultima_chave: str | None = None

    def disponivel(self) -> tuple[bool, str]:
        if not self.chaves:
            return False, "nenhuma chave configurada em data/app/ollama_keys.txt"
        agora = time.time()
        ativas = [c for c in self.chaves if self._esfriando.get(c, 0) <= agora]
        if not ativas:
            menor = min(self._esfriando.values())
            return False, f"todas as chaves em espera por {int(menor - agora)}s"
        return True, f"{len(ativas)}/{len(self.chaves)} chaves ativas · modelo {self.modelo}"

    def _proxima_chave(self) -> str:
        agora = time.time()
        total = len(self.chaves)
        for _ in range(total):
            chave = self.chaves[self._rotacao % total]
            self._rotacao += 1
            if self._esfriando.get(chave, 0) <= agora:
                return chave
        raise ChatErro("todas as chaves do Ollama Cloud estão em período de espera")

    def _penalizar(self, chave: str, segundos: float) -> None:
        self._esfriando[chave] = max(self._esfriando.get(chave, 0), time.time() + segundos)

    def stream(self, mensagens: list[dict]) -> Iterator[str]:
        """Envia a conversa e devolve o texto gerado em pedaços (streaming)."""
        if not self.chaves:
            raise ChatErro("nenhuma chave Ollama configurada (data/app/ollama_keys.txt)")
        ultimo_erro = ""
        for _ in range(len(self.chaves)):
            chave = self._proxima_chave()
            self.ultima_chave = chave
            try:
                resposta = requests.post(
                    URL_CHAT,
                    headers={
                        "Authorization": f"Bearer {chave}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.modelo,
                        "messages": mensagens,
                        "stream": True,
                        "options": {
                            "temperature": 0.4,
                            "num_predict": MAX_TOKENS_SAIDA,
                        },
                    },
                    stream=True,
                    timeout=300,
                )
            except requests.RequestException as erro:
                self._penalizar(chave, 30)
                ultimo_erro = str(erro)
                continue

            if resposta.status_code == 429:
                self._penalizar(chave, 600)
                ultimo_erro = "cota gratuita atingida nesta chave (rotacionando)"
                continue
            if resposta.status_code in (401, 403):
                self._penalizar(chave, 3600)
                ultimo_erro = f"chave recusada (HTTP {resposta.status_code})"
                continue
            if resposta.status_code != 200:
                self._penalizar(chave, 60)
                ultimo_erro = f"HTTP {resposta.status_code}: {resposta.text[:200]}"
                continue

            self.requisicoes += 1
            parcial: list[str] = []
            for linha in resposta.iter_lines(decode_unicode=True):
                if not linha:
                    continue
                try:
                    evento = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if "error" in evento:
                    raise ChatErro(str(evento["error"]))
                mensagem = evento.get("message") or {}
                pedaco = mensagem.get("content") or ""
                if pedaco:
                    parcial.append(pedaco)
                    yield pedaco
                if evento.get("done"):
                    self.tokens_entrada += int(evento.get("prompt_eval_count") or 0)
                    self.tokens_saida += int(evento.get("eval_count") or 0)
            if parcial:
                return
            ultimo_erro = "resposta vazia do modelo"
            self._penalizar(chave, 60)
        raise ChatErro(ultimo_erro or "falha ao chamar o Ollama Cloud")


class ServicoChat:
    """Conversa com contexto da região selecionada, com histórico curto para economizar tokens."""

    def __init__(self, fonte: FonteDados, cliente: ClienteOllama | None = None):
        self.fonte = fonte
        self.cliente = cliente or ClienteOllama()
        self.historico: list[dict] = []
        self.escopo_atual: Escopo | None = None

    def reiniciar(self) -> None:
        self.historico.clear()
        self.escopo_atual = None

    def contexto(self, escopo: Escopo, ano: int, cargo_cd: int) -> str:
        return self.fonte.contexto(escopo, ano, cargo_cd)

    def responder(
        self, escopo: Escopo, ano: int, cargo_cd: int, pergunta: str
    ) -> Iterator[str]:
        contexto = self.contexto(escopo, ano, cargo_cd)
        # o histórico é preservado mesmo ao trocar de escopo: só o contexto de
        # dados (system) é atualizado para o novo recorte, mantendo a conversa linear
        self.escopo_atual = escopo
        mensagens: list[dict] = [
            {
                "role": "system",
                "content": (
                    SISTEMA
                    + "\n\nContexto de dados (use SOMENTE isto como fonte):\n"
                    + contexto
                ),
            },
        ]
        mensagens += self.historico[-LIMITE_HISTORICO:]
        mensagens.append({"role": "user", "content": pergunta})

        partes: list[str] = []
        for pedaco in self.cliente.stream(mensagens):
            partes.append(pedaco)
            yield pedaco
        resposta = "".join(partes).strip()
        if resposta:
            self.historico.append({"role": "user", "content": pergunta})
            self.historico.append({"role": "assistant", "content": resposta})
            del self.historico[:-LIMITE_HISTORICO]
