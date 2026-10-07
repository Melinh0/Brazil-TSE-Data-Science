from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

TAMANHO_BLOCO = 1 << 20


class ClienteHTTP:
    def __init__(self, rps: float = 8.0, timeout: int = 120) -> None:
        self.timeout = timeout
        self._intervalo = 1.0 / max(rps, 0.1)
        self._trava = threading.Lock()
        self._ultimo = 0.0
        self.sessao = requests.Session()
        self.sessao.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            }
        )
        retry = Retry(
            total=5,
            connect=5,
            read=5,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
        self.sessao.mount("https://", adapter)
        self.sessao.mount("http://", adapter)

    def _aguardar(self) -> None:
        with self._trava:
            agora = time.monotonic()
            espera = self._ultimo + self._intervalo - agora
            self._ultimo = max(agora, self._ultimo + self._intervalo)
        if espera > 0:
            time.sleep(espera)

    def get(self, url: str, **kwargs) -> requests.Response:
        self._aguardar()
        kwargs.setdefault("timeout", self.timeout)
        return self.sessao.get(url, **kwargs)

    def head(self, url: str, **kwargs) -> requests.Response:
        self._aguardar()
        kwargs.setdefault("timeout", self.timeout)
        return self.sessao.head(url, **kwargs)

    def get_json(self, url: str, **kwargs):
        resposta = self.get(url, **kwargs)
        resposta.raise_for_status()
        return resposta.json()

    def baixar(self, url: str, destino: Path, force: bool = False, progresso: bool = True) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists() and destino.stat().st_size > 0 and not force:
            if progresso:
                print(f"  [ok] ja baixado: {destino.name} ({destino.stat().st_size:,} bytes)")
            return destino

        self._aguardar()
        resposta = self.sessao.get(url, stream=True, timeout=self.timeout)
        resposta.raise_for_status()
        total = int(resposta.headers.get("content-length") or 0)
        parcial = destino.with_suffix(destino.suffix + ".parcial")
        baixado = 0
        ultimo_log = 0.0
        with open(parcial, "wb") as arquivo:
            for bloco in resposta.iter_content(TAMANHO_BLOCO):
                if not bloco:
                    continue
                arquivo.write(bloco)
                baixado += len(bloco)
                agora = time.monotonic()
                if progresso and (agora - ultimo_log >= 2.0 or (total and baixado == total)):
                    ultimo_log = agora
                    if total:
                        pct = 100.0 * baixado / total
                        print(
                            f"\r  [baixando] {destino.name}: {baixado / 1e6:,.1f} / {total / 1e6:,.1f} MB ({pct:,.1f}%)",
                            end="",
                            flush=True,
                        )
                    else:
                        print(
                            f"\r  [baixando] {destino.name}: {baixado / 1e6:,.1f} MB",
                            end="",
                            flush=True,
                        )
        if progresso:
            print()
        parcial.replace(destino)
        if progresso:
            print(f"  [ok] {destino.name}: {destino.stat().st_size:,} bytes")
        return destino


def log(mensagem: str) -> None:
    print(mensagem, file=sys.stdout, flush=True)
