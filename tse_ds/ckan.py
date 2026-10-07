from __future__ import annotations

from dataclasses import dataclass

from .config import CKAN_BASE, DATASETS_POR_ANO, PADROES_ARQUIVO, RECURSOS_OBRIGATORIOS, RECURSOS_OPCIONAIS
from .http import ClienteHTTP


@dataclass
class Recurso:
    ano: int
    nome_logico: str
    dataset: str
    titulo: str
    url: str
    disponivel: bool

    @property
    def arquivo(self) -> str:
        return self.url.rsplit("/", 1)[-1]


def _acao(cliente: ClienteHTTP, acao: str, **params) -> dict:
    resposta = cliente.get_json(f"{CKAN_BASE}/{acao}", params=params)
    if not resposta.get("success"):
        raise RuntimeError(f"CKAN {acao} falhou: {resposta}")
    return resposta["result"]


def recursos_do_dataset(cliente: ClienteHTTP, dataset_id: str) -> list[dict]:
    try:
        pacote = _acao(cliente, "package_show", id=dataset_id)
    except Exception as erro:
        print(f"  [aviso] dataset {dataset_id} indisponivel: {erro}")
        return []
    return list(pacote.get("resources", []))


def _encontrar(resources: list[dict], arquivo: str) -> str | None:
    arquivo = arquivo.lower()
    for recurso in resources:
        url = (recurso.get("url") or "").lower()
        if url.endswith(arquivo) or url.endswith("/" + arquivo):
            return recurso["url"]
    return None


def _existe(cliente: ClienteHTTP, url: str) -> bool:
    try:
        resposta = cliente.get(url, stream=True, headers={"Range": "bytes=0-63"})
        next(resposta.iter_content(64), b"")
        resposta.close()
        return resposta.status_code in (200, 206)
    except Exception:
        return False


def resolver_recursos(
    cliente: ClienteHTTP,
    ano: int,
    apenas: tuple[str, ...] | None = None,
    incluir_opcionais: bool = False,
) -> list[Recurso]:
    obrigatorios = RECURSOS_OBRIGATORIOS.get( ano, ())
    if apenas:
        alvos = apenas
    else:
        alvos = obrigatorios + (RECURSOS_OPCIONAIS.get(ano, ()) if incluir_opcionais else ())

    datasets = DATASETS_POR_ANO.get(ano, ())
    cache: dict[str, list[dict]] = {}
    for dataset in datasets:
        cache[dataset] = recursos_do_dataset(cliente, dataset)

    recursos: list[Recurso] = []
    for nome in alvos:
        arquivo = PADROES_ARQUIVO[nome].format(ano=ano)
        url = None
        dataset_usado = ""
        for dataset, resources in cache.items():
            url = _encontrar(resources, arquivo)
            if url:
                dataset_usado = dataset
                break
        if url:
            recursos.append(Recurso(ano, nome, dataset_usado, arquivo, url, True))
        else:
            sugestao = f"https://cdn.tse.jus.br/estatistica/sead/odsele/{nome}/{arquivo}"
            recursos.append(Recurso(ano, nome, "", arquivo, sugestao, _existe(cliente, sugestao)))
    return recursos


def listar_fontes(cliente: ClienteHTTP, ano: int) -> list[Recurso]:
    return resolver_recursos(cliente, ano, incluir_opcionais=True)


def datasets_disponiveis(cliente: ClienteHTTP) -> list[str]:
    try:
        resultado = _acao(cliente, "package_search", q="resultados OR candidatos OR eleitorado", rows=100)
    except Exception as erro:
        print(f"  [aviso] busca no CKAN falhou: {erro}")
        return []
    nomes = [item["name"] for item in resultado.get("results", [])]
    return sorted(nomes)
