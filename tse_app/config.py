from __future__ import annotations

import json
import os

from tse_ds.config import RAIZ

PASTA_APP = RAIZ / "data" / "app"
PASTA_GEO = RAIZ / "data" / "geo"
PASTA_TABELAS = RAIZ / "outputs" / "tabelas"
PASTA_FIGURAS = RAIZ / "outputs" / "figuras"
PASTA_JSON = RAIZ / "data" / "json"

ARQUIVO_CHAVES = PASTA_APP / "ollama_keys.txt"
ARQUIVO_ESTADO = PASTA_APP / "estado.json"

URL_CHAT = "https://ollama.com/api/chat"
MODELO_PADRAO = "gpt-oss:120b"

ANOS = (2024, 2026)

REGIOES: dict[str, tuple[str, ...]] = {
    "N": ("AC", "AP", "AM", "PA", "RO", "RR", "TO"),
    "NE": ("AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"),
    "S": ("PR", "RS", "SC"),
    "SE": ("ES", "MG", "RJ", "SP"),
    "CO": ("DF", "GO", "MT", "MS"),
}

NOMES_REGIAO = {
    "N": "Norte",
    "NE": "Nordeste",
    "S": "Sul",
    "SE": "Sudeste",
    "CO": "Centro-Oeste",
}

UF_REGIAO = {uf: sigla for sigla, ufs in REGIOES.items() for uf in ufs}

NOMES_UF = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}

NOMES_CARGO = {
    1: "Presidente",
    3: "Governador",
    5: "Senador",
    6: "Deputado Federal",
    7: "Deputado Estadual",
    8: "Deputado Distrital",
    11: "Prefeito",
    13: "Vereador",
}

ORDEM_CARGO = (1, 3, 5, 6, 7, 8, 11, 13)


def garantir_pastas_app() -> None:
    PASTA_APP.mkdir(parents=True, exist_ok=True)
    PASTA_GEO.mkdir(parents=True, exist_ok=True)


def ler_chaves() -> list[str]:
    """Lê as chaves do Ollama Cloud (arquivo local, separadas por vírgula/quebra de linha)."""
    if os.environ.get("OLLAMA_API_KEYS"):
        bruto = os.environ["OLLAMA_API_KEYS"]
    elif ARQUIVO_CHAVES.exists():
        bruto = ARQUIVO_CHAVES.read_text(encoding="utf-8-sig")
    else:
        return []
    partes = [
        p.strip().lstrip("\ufeff")
        for p in bruto.replace(";", ",").replace("\n", ",").split(",")
    ]
    vistos: list[str] = []
    for parte in partes:
        if parte and "." in parte and parte not in vistos:
            vistos.append(parte)
    return vistos


def modelo_usado() -> str:
    return os.environ.get("OLLAMA_MODEL", MODELO_PADRAO)


def ler_estado() -> dict:
    if ARQUIVO_ESTADO.exists():
        try:
            return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def gravar_estado(estado: dict) -> None:
    garantir_pastas_app()
    ARQUIVO_ESTADO.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
