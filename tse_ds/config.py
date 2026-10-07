from __future__ import annotations

from pathlib import Path

ANOS_PADRAO = (2024, 2026)

CKAN_BASE = "https://dadosabertos.tse.jus.br/api/3/action"
ODSELE_BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
RESULTADOS_BASE = "https://resultados.tse.jus.br"
AMBIENTE = "oficial"

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DADOS = RAIZ / "data"
PASTA_ZIP = PASTA_DADOS / "zip"
PASTA_JSON = PASTA_DADOS / "json"
PASTA_SAIDA = RAIZ / "outputs"
PASTA_TABELAS = PASTA_SAIDA / "tabelas"
PASTA_FIGURAS = PASTA_SAIDA / "figuras"

UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
)

CARGOS = {
    1: "Presidente",
    2: "Vice-Presidente",
    3: "Governador",
    4: "Vice-Governador",
    5: "Senador",
    6: "Deputado Federal",
    7: "Deputado Estadual",
    8: "Deputado Distrital",
    11: "Prefeito",
    12: "Vice-Prefeito",
    13: "Vereador",
    25: "Conselheiro Distrital",
}

CARGOS_PRINCIPAIS = {1, 3, 5, 6, 7, 8, 11, 13, 25}

RECURSOS_OBRIGATORIOS = {
    2024: ("votacao_candidato_munzona", "consulta_cand", "detalhe_votacao_munzona", "votacao_partido_munzona"),
    2026: ("votacao_candidato_munzona", "consulta_cand", "votacao_secao"),
}

RECURSOS_OPCIONAIS = {
    2024: ("perfil_eleitorado",),
    2026: ("detalhe_votacao_munzona", "votacao_partido_munzona", "perfil_eleitorado"),
}

PADROES_ARQUIVO = {
    "votacao_candidato_munzona": "votacao_candidato_munzona_{ano}.zip",
    "votacao_partido_munzona": "votacao_partido_munzona_{ano}.zip",
    "detalhe_votacao_munzona": "detalhe_votacao_munzona_{ano}.zip",
    "consulta_cand": "consulta_cand_{ano}.zip",
    "perfil_eleitorado": "perfil_eleitorado_{ano}.zip",
    "votacao_secao": "votacao_secao_{ano}_BR.zip",
}

DATASETS_POR_ANO = {
    2024: ("resultados-2024", "candidatos-2024", "eleitorado-2024"),
    2026: ("resultados-2026", "candidatos-2026", "eleitorado-2026"),
}

TIPOS_DIVULGACAO = ("config", "acompanhamento")

ROTULOS_CARGO = {
    "1": "Presidente",
    "3": "Governador",
    "5": "Senador",
    "6": "Deputado Federal",
    "7": "Deputado Estadual",
    "8": "Deputado Distrital",
    "11": "Prefeito",
    "13": "Vereador",
    "25": "Conselheiro Distrital",
}


def garantir_pastas() -> None:
    for pasta in (PASTA_DADOS, PASTA_ZIP, PASTA_JSON, PASTA_SAIDA, PASTA_TABELAS, PASTA_FIGURAS):
        pasta.mkdir(parents=True, exist_ok=True)
