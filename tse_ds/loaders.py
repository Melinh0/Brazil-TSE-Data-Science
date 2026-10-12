from __future__ import annotations

from pathlib import Path

import pandas as pd

from .http import log
from .odsele import iterar_csvs, membros_csv

COLUNAS_VOTACAO = [
    "ANO_ELEICAO",
    "NR_TURNO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "TP_ABRANGENCIA",
    "SG_UF",
    "SG_UE",
    "NM_UE",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "CD_CARGO",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_PARTIDO",
    "SG_PARTIDO",
    "NM_PARTIDO",
    "NM_URNA_CANDIDATO",
    "NM_CANDIDATO",
    "DS_SIT_TOT_TURNO",
    "QT_VOTOS_NOMINAIS",
    "QT_VOTOS_NOMINAIS_VALIDOS",
]

CHAVES_VOTACAO = [
    "ANO_ELEICAO",
    "NR_TURNO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "TP_ABRANGENCIA",
    "SG_UF",
    "SG_UE",
    "NM_UE",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "CD_CARGO",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_PARTIDO",
    "SG_PARTIDO",
    "NM_PARTIDO",
    "NM_URNA_CANDIDATO",
    "DS_SIT_TOT_TURNO",
]

COLUNAS_SECAO = [
    "ANO_ELEICAO",
    "NR_TURNO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "TP_ABRANGENCIA",
    "SG_UF",
    "SG_UE",
    "NM_UE",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "CD_CARGO",
    "DS_CARGO",
    "NR_VOTAVEL",
    "NM_VOTAVEL",
    "QT_VOTOS",
    "SQ_CANDIDATO",
]

CHAVES_SECAO = [
    "ANO_ELEICAO",
    "NR_TURNO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "TP_ABRANGENCIA",
    "SG_UF",
    "SG_UE",
    "NM_UE",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "CD_CARGO",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NM_VOTAVEL",
    "NR_VOTAVEL",
]

COLUNAS_CADASTRO = [
    "ANO_ELEICAO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "SG_UF",
    "SG_UE",
    "NM_UE",
    "CD_CARGO",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NR_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
    "NR_PARTIDO",
    "SG_PARTIDO",
    "NM_PARTIDO",
    "DT_NASCIMENTO",
    "DS_GENERO",
    "DS_COR_RACA",
    "DS_GRAU_INSTRUCAO",
    "DS_SITUACAO_CANDIDATURA",
    "DS_SIT_TOT_TURNO",
]

COLUNAS_DETALHE = [
    "ANO_ELEICAO",
    "NR_TURNO",
    "CD_ELEICAO",
    "DS_ELEICAO",
    "SG_UF",
    "NM_UE",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "CD_CARGO",
    "DS_CARGO",
    "ST_VOTO_EM_TRANSITO",
    "QT_APTOS",
    "QT_TOTAL_SECOES",
    "QT_SECOES_NAO_INSTALADAS",
    "QT_COMPARECIMENTO",
    "QT_ABSTENCOES",
    "QT_VOTOS_BRANCOS",
    "QT_TOTAL_VOTOS_NULOS",
    "QT_VOTOS",
    "QT_TOTAL_VOTOS_VALIDOS",
]

COLUNAS_PARTIDO = [
    "ANO_ELEICAO",
    "NR_TURNO",
    "CD_ELEICAO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "CD_CARGO",
    "DS_CARGO",
    "TP_AGREMIACAO",
    "NR_PARTIDO",
    "SG_PARTIDO",
    "NM_PARTIDO",
    "NM_COLIGACAO",
    "QT_VOTOS_LEGENDA_VALIDOS",
    "QT_VOTOS_NOMINAIS_VALIDOS",
]

SUFIXO_BRASIL = "_BRASIL.CSV"


def membros_para_leitura(caminho: Path) -> list[str]:
    nomes = membros_csv(caminho)
    brasil = [nome for nome in nomes if nome.upper().endswith(SUFIXO_BRASIL)]
    if brasil:
        extras = [nome for nome in nomes if nome.upper().endswith("_BR.CSV") and nome not in brasil]
        return brasil + extras
    return nomes


def _numericas(colunas: list[str]) -> dict[str, str]:
    return {coluna: "Int64" for coluna in colunas if coluna.startswith("QT_")}


def ler_votacao_municipal(
    caminho: Path,
    cargos: tuple[int, ...] | list[int] | None = None,
    chunksize: int = 150_000,
) -> pd.DataFrame:
    caminho = Path(caminho)
    partes: list[pd.DataFrame] = []
    total = 0
    for membro in membros_para_leitura(caminho):
        for pedaco in iterar_csvs(caminho, usecols=COLUNAS_VOTACAO, chunksize=chunksize, membro=membro):
            if cargos:
                pedaco = pedaco[pedaco["CD_CARGO"].isin([str(c) for c in cargos])]
            if pedaco.empty:
                continue
            for coluna in ("QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS"):
                pedaco[coluna] = pd.to_numeric(pedaco[coluna], errors="coerce").fillna(0).astype("int64")
            agregado = (
                pedaco.groupby(CHAVES_VOTACAO, dropna=False, observed=True)[
                    ["QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS"]
                ]
                .sum()
                .reset_index()
            )
            for coluna in agregado.select_dtypes(include="object").columns:
                agregado[coluna] = agregado[coluna].astype("category")
            partes.append(agregado)
            total += len(pedaco)
            log(f"  [leitura] {membro}: {total:,} linhas processadas")

    if not partes:
        return pd.DataFrame(columns=CHAVES_VOTACAO + ["QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS"])

    textos = [
        coluna
        for coluna in partes[0].columns
        if all(isinstance(parte[coluna].dtype, pd.CategoricalDtype) for parte in partes)
    ]
    for coluna in textos:
        unicos: set = set()
        for parte in partes:
            unicos.update(parte[coluna].dropna().unique().tolist())
        dtype = pd.CategoricalDtype(sorted(unicos))
        for parte in partes:
            parte[coluna] = parte[coluna].astype(dtype)

    quadro = pd.concat(partes, ignore_index=True)
    partes.clear()
    quadro = (
        quadro.groupby(CHAVES_VOTACAO, dropna=False, observed=True)[
            ["QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS"]
        ]
        .sum()
        .reset_index()
        .rename(
            columns={
                "ANO_ELEICAO": "ano",
                "NR_TURNO": "turno",
                "CD_ELEICAO": "eleicao_cd",
                "DS_ELEICAO": "eleicao",
                "TP_ABRANGENCIA": "abrangencia",
                "SG_UF": "uf",
                "SG_UE": "ue",
                "NM_UE": "ue_nome",
                "CD_MUNICIPIO": "municipio_cd",
                "NM_MUNICIPIO": "municipio",
                "CD_CARGO": "cargo_cd",
                "DS_CARGO": "cargo",
                "SQ_CANDIDATO": "candidato_sq",
                "NR_PARTIDO": "partido_nr",
                "SG_PARTIDO": "partido",
                "NM_PARTIDO": "partido_nome",
                "NM_URNA_CANDIDATO": "candidato_urna",
                "DS_SIT_TOT_TURNO": "situacao",
                "QT_VOTOS_NOMINAIS": "votos",
                "QT_VOTOS_NOMINAIS_VALIDOS": "votos_validos",
            }
        )
    )
    quadro["cargo_cd"] = pd.to_numeric(quadro["cargo_cd"], errors="coerce").astype("Int64")
    for coluna in ("ano", "turno", "eleicao_cd", "partido_nr", "municipio_cd"):
        quadro[coluna] = pd.to_numeric(quadro[coluna], errors="coerce").astype("Int64")
    for coluna in quadro.select_dtypes(include="object").columns:
        quadro[coluna] = quadro[coluna].astype("category")
    log(f"  [ok] votacao municipal: {len(quadro):,} linhas agregadas")
    return quadro


def ler_cadastro_candidatos(caminho: Path, cargos: tuple[int, ...] | None = None) -> pd.DataFrame:
    caminho = Path(caminho)
    quadro = pd.DataFrame()
    for membro in membros_para_leitura(caminho):
        pedaco = next(iterar_csvs(caminho, usecols=COLUNAS_CADASTRO, membro=membro))
        quadro = pd.concat([quadro, pedaco], ignore_index=True) if not quadro.empty else pedaco
    if quadro.empty:
        return quadro
    if cargos:
        quadro = quadro[quadro["CD_CARGO"].isin([str(c) for c in cargos])].copy()
    quadro = quadro.drop_duplicates(subset=["SQ_CANDIDATO"])
    quadro = quadro.rename(
        columns={
            "ANO_ELEICAO": "ano",
            "CD_ELEICAO": "eleicao_cd",
            "DS_ELEICAO": "eleicao",
            "SG_UF": "uf",
            "SG_UE": "ue",
            "NM_UE": "ue_nome",
            "CD_CARGO": "cargo_cd",
            "DS_CARGO": "cargo",
            "SQ_CANDIDATO": "candidato_sq",
            "NR_CANDIDATO": "candidato_nr",
            "NM_CANDIDATO": "candidato",
            "NM_URNA_CANDIDATO": "candidato_urna",
            "NR_PARTIDO": "partido_nr",
            "SG_PARTIDO": "partido",
            "NM_PARTIDO": "partido_nome",
            "DT_NASCIMENTO": "nascimento",
            "DS_GENERO": "genero",
            "DS_COR_RACA": "raca",
            "DS_GRAU_INSTRUCAO": "escolaridade",
            "DS_SITUACAO_CANDIDATURA": "situacao_candidatura",
            "DS_SIT_TOT_TURNO": "situacao",
        }
    )
    quadro["cargo_cd"] = pd.to_numeric(quadro["cargo_cd"], errors="coerce").astype("Int64")
    quadro["ano"] = pd.to_numeric(quadro["ano"], errors="coerce").astype("Int64")
    quadro["partido_nr"] = pd.to_numeric(quadro["partido_nr"], errors="coerce").astype("Int64")
    quadro["municipio"] = quadro["ue_nome"]
    quadro["municipio_cd"] = pd.to_numeric(quadro["ue"], errors="coerce").astype("Int64")
    log(f"  [ok] cadastro de candidatos: {len(quadro):,} linhas")
    return quadro


def ler_detalhe_munzona(caminho: Path, nivel: str = "uf") -> pd.DataFrame:
    caminho = Path(caminho)
    quadros = []
    for membro in membros_para_leitura(caminho):
        quadros.append(next(iterar_csvs(caminho, usecols=COLUNAS_DETALHE, membro=membro)))
    quadro = pd.concat(quadros, ignore_index=True)
    quadro = quadro[quadro["ST_VOTO_EM_TRANSITO"].fillna("N").str.upper() == "N"].copy()
    for coluna in (
        "QT_APTOS",
        "QT_TOTAL_SECOES",
        "QT_SECOES_NAO_INSTALADAS",
        "QT_COMPARECIMENTO",
        "QT_ABSTENCOES",
        "QT_VOTOS_BRANCOS",
        "QT_TOTAL_VOTOS_NULOS",
        "QT_VOTOS",
        "QT_TOTAL_VOTOS_VALIDOS",
    ):
        quadro[coluna] = pd.to_numeric(quadro[coluna], errors="coerce").fillna(0).astype("int64")
    chave_zona = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA"]
    # aptos/secoes/comparecimento sao constantes por zona (repetidos em cada cargo/turno):
    # max por zona resolve a repeticao sem escolher um cargo arbitrario.
    por_zona = (
        quadro.groupby(chave_zona, dropna=False, observed=True)[
            [
                "QT_APTOS",
                "QT_TOTAL_SECOES",
                "QT_SECOES_NAO_INSTALADAS",
                "QT_COMPARECIMENTO",
                "QT_ABSTENCOES",
            ]
        ]
        .max()
        .reset_index()
    )
    # votos/brancos/nulos/validos sao proprios de cada (zona, cargo, turno):
    # somar sobre as linhas distintas da zona da o total da apuracao municipal.
    por_zona = por_zona.merge(
        quadro.groupby(chave_zona, dropna=False, observed=True)[
            ["QT_VOTOS_BRANCOS", "QT_TOTAL_VOTOS_NULOS", "QT_VOTOS", "QT_TOTAL_VOTOS_VALIDOS"]
        ]
        .sum()
        .reset_index(),
        on=chave_zona,
    )
    colunas_soma = [
        "QT_APTOS",
        "QT_TOTAL_SECOES",
        "QT_SECOES_NAO_INSTALADAS",
        "QT_COMPARECIMENTO",
        "QT_ABSTENCOES",
        "QT_VOTOS_BRANCOS",
        "QT_TOTAL_VOTOS_NULOS",
        "QT_VOTOS",
        "QT_TOTAL_VOTOS_VALIDOS",
    ]
    if nivel == "municipio":
        agrupamento = ["SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO"]
        rotulos = {"SG_UF": "uf", "CD_MUNICIPIO": "municipio_cd", "NM_MUNICIPIO": "municipio"}
    else:
        agrupamento = ["SG_UF"]
        rotulos = {"SG_UF": "uf"}
    quadro = (
        por_zona.groupby(agrupamento, dropna=False, observed=True)[colunas_soma]
        .sum()
        .reset_index()
        .rename(
            columns={
                **rotulos,
                "QT_APTOS": "eleitores",
                "QT_TOTAL_SECOES": "secoes_totais",
                "QT_SECOES_NAO_INSTALADAS": "secoes_nao_instaladas",
                "QT_COMPARECIMENTO": "comparecimento",
                "QT_ABSTENCOES": "abstencao",
                "QT_VOTOS_BRANCOS": "votos_brancos",
                "QT_TOTAL_VOTOS_NULOS": "votos_nulos",
                "QT_VOTOS": "votos",
                "QT_TOTAL_VOTOS_VALIDOS": "votos_validos",
            }
        )
    )
    quadro["pct_comparecimento"] = 100.0 * quadro["comparecimento"] / quadro["eleitores"].replace(0, pd.NA)
    quadro["pct_abstencao"] = 100.0 * quadro["abstencao"] / quadro["eleitores"].replace(0, pd.NA)
    quadro["pct_secoes"] = 100.0 * (
        quadro["secoes_totais"] - quadro["secoes_nao_instaladas"]
    ) / quadro["secoes_totais"].replace(0, pd.NA)
    if nivel == "municipio":
        quadro["municipio_cd"] = pd.to_numeric(quadro["municipio_cd"], errors="coerce").astype("Int64")
        quadro["municipio"] = quadro["municipio"].astype(str).str.strip()
        ordenacao = ["uf", "municipio"]
        log(f"  [ok] detalhe da apuracao por municipio: {len(quadro):,} municipios")
    else:
        ordenacao = ["uf"]
        log(f"  [ok] detalhe da apuracao por UF: {len(quadro)} UFs")
    return quadro.sort_values(ordenacao).reset_index(drop=True)


def ler_votacao_partido(caminho: Path, cargos: tuple[int, ...] | None = None) -> pd.DataFrame:
    caminho = Path(caminho)
    pedacos = list(iterar_csvs(caminho, usecols=COLUNAS_PARTIDO, chunksize=400_000))
    quadro = pd.concat(pedacos, ignore_index=True)
    if cargos:
        quadro = quadro[quadro["CD_CARGO"].isin([str(c) for c in cargos])].copy()
    for coluna in ("QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_NOMINAIS_VALIDOS"):
        quadro[coluna] = pd.to_numeric(quadro[coluna], errors="coerce").fillna(0).astype("int64")
    agrupado = (
        quadro.groupby(["SG_UF", "CD_CARGO", "DS_CARGO", "SG_PARTIDO", "NM_PARTIDO"], dropna=False, observed=True)[
            ["QT_VOTOS_LEGENDA_VALIDOS", "QT_VOTOS_NOMINAIS_VALIDOS"]
        ]
        .sum()
        .reset_index()
        .rename(
            columns={
                "SG_UF": "uf",
                "CD_CARGO": "cargo_cd",
                "DS_CARGO": "cargo",
                "SG_PARTIDO": "partido",
                "NM_PARTIDO": "partido_nome",
                "QT_VOTOS_LEGENDA_VALIDOS": "votos_legenda",
                "QT_VOTOS_NOMINAIS_VALIDOS": "votos_nominais",
            }
        )
    )
    log(f"  [ok] votacao em partido: {len(agrupado):,} linhas")
    return agrupado


def ler_votacao_secao(
    caminho: Path,
    cargos: tuple[int, ...] | list[int] | None = None,
    cadastro: pd.DataFrame | None = None,
    chunksize: int = 300_000,
) -> pd.DataFrame:
    """Agrega votacao por secao (nivel municipio) para cargos ausentes no arquivo munzona."""
    caminho = Path(caminho)
    partes: list[pd.DataFrame] = []
    total = 0
    for pedaco in iterar_csvs(caminho, usecols=COLUNAS_SECAO, chunksize=chunksize):
        if cargos:
            pedaco = pedaco[pedaco["CD_CARGO"].isin([str(c) for c in cargos])]
        pedaco = pedaco[
            ~pedaco["SQ_CANDIDATO"].fillna("").str.strip().isin(("", "-1"))
            & ~pedaco["NR_VOTAVEL"].fillna("").str.strip().isin(("95", "96"))
        ]
        if pedaco.empty:
            continue
        pedaco["QT_VOTOS"] = pd.to_numeric(pedaco["QT_VOTOS"], errors="coerce").fillna(0).astype("int64")
        agregado = pedaco.groupby(CHAVES_SECAO, dropna=False, observed=True)["QT_VOTOS"].sum().reset_index()
        partes.append(agregado)
        total += len(pedaco)
        log(f"  [leitura] {caminho.name}: {total:,} linhas processadas")

    colunas_vazias = [
        "ano",
        "turno",
        "eleicao_cd",
        "eleicao",
        "abrangencia",
        "uf",
        "ue",
        "ue_nome",
        "municipio_cd",
        "municipio",
        "cargo_cd",
        "cargo",
        "candidato_sq",
        "candidato",
        "candidato_urna",
        "votavel_nr",
        "partido_nr",
        "partido",
        "partido_nome",
        "situacao",
        "votos",
        "votos_validos",
    ]
    if not partes:
        return pd.DataFrame(columns=colunas_vazias)

    quadro = (
        pd.concat(partes, ignore_index=True)
        .groupby(CHAVES_SECAO, dropna=False, observed=True)["QT_VOTOS"]
        .sum()
        .reset_index()
        .rename(
            columns={
                "ANO_ELEICAO": "ano",
                "NR_TURNO": "turno",
                "CD_ELEICAO": "eleicao_cd",
                "DS_ELEICAO": "eleicao",
                "TP_ABRANGENCIA": "abrangencia",
                "SG_UF": "uf",
                "SG_UE": "ue",
                "NM_UE": "ue_nome",
                "CD_MUNICIPIO": "municipio_cd",
                "NM_MUNICIPIO": "municipio",
                "CD_CARGO": "cargo_cd",
                "DS_CARGO": "cargo",
                "SQ_CANDIDATO": "candidato_sq",
                "NM_VOTAVEL": "candidato_urna",
                "NR_VOTAVEL": "votavel_nr",
                "QT_VOTOS": "votos",
            }
        )
    )
    quadro["votos_validos"] = quadro["votos"]

    if cadastro is not None and not cadastro.empty:
        indice = cadastro.set_index("candidato_sq")
        for coluna in ("candidato", "partido_nr", "partido", "partido_nome", "situacao"):
            if coluna in indice.columns:
                quadro[coluna] = quadro["candidato_sq"].map(indice[coluna])
    for coluna in ("candidato", "partido", "partido_nome", "situacao"):
        if coluna not in quadro.columns:
            quadro[coluna] = pd.NA

    for coluna in ("ano", "turno", "eleicao_cd", "municipio_cd", "partido_nr", "votavel_nr", "cargo_cd"):
        quadro[coluna] = pd.to_numeric(quadro[coluna], errors="coerce").astype("Int64")
    for coluna in quadro.select_dtypes(include="object").columns:
        quadro[coluna] = quadro[coluna].astype("category")
    log(f"  [ok] votacao por secao agregada: {len(quadro):,} linhas")
    return quadro


COLUNAS_PERFIL = [
    "SG_UF",
    "DS_GENERO",
    "DS_FAIXA_ETARIA",
    "DS_GRAU_ESCOLARIDADE",
    "DS_ESTADO_CIVIL",
    "DS_RACA_COR",
    "DS_IDENTIDADE_GENERO",
    "QT_ELEITORES",
]

DIMENSOES_PERFIL = {
    "DS_GENERO": "genero",
    "DS_FAIXA_ETARIA": "faixa_etaria",
    "DS_GRAU_ESCOLARIDADE": "grau_escolaridade",
    "DS_ESTADO_CIVIL": "estado_civil",
    "DS_RACA_COR": "raca",
    "DS_IDENTIDADE_GENERO": "identidade_genero",
}

VALORES_DESCARTADOS_PERFIL = {"", "-1", "NÃO INFORMADO", "INVÁLIDA"}


def ler_perfil_eleitorado(caminho: Path, chunksize: int = 1_000_000) -> pd.DataFrame:
    """Agrega o perfil do eleitorado em formato longo (uf, dimensao, categoria, eleitores)."""
    caminho = Path(caminho)
    membros = membros_csv(caminho)
    brasil = [nome for nome in membros if nome.upper().endswith("_BRASIL.CSV")]
    # sem o consolidado do Brasil, processa cada membro (UF) separadamente para
    # nao misturar o total nacional com os totais estaduais.
    selecao = brasil[:1] if brasil else membros
    if not brasil:
        log("  [aviso] perfil sem membro BRASIL; agregando membro a membro")
    partes: list[pd.DataFrame] = []
    total = 0
    for membro in selecao:
        for pedaco in iterar_csvs(caminho, usecols=COLUNAS_PERFIL, chunksize=chunksize, membro=membro):
            pedaco["QT_ELEITORES"] = (
                pd.to_numeric(pedaco["QT_ELEITORES"], errors="coerce").fillna(0).astype("int64")
            )
            for coluna, dimensao in DIMENSOES_PERFIL.items():
                if coluna not in pedaco:
                    continue
                sub = pedaco[["SG_UF", coluna, "QT_ELEITORES"]].copy()
                rotulo = sub[coluna].astype(str).str.strip()
                descartar = rotulo.str.upper().isin(VALORES_DESCARTADOS_PERFIL)
                sub = sub[~descartar].copy()
                sub["categoria"] = rotulo[~descartar]
                sub = sub.drop(columns=[coluna]).rename(columns={"SG_UF": "uf"})
                sub["dimensao"] = dimensao
                partes.append(
                    sub.groupby(["uf", "dimensao", "categoria"], observed=True, dropna=False)[
                        "QT_ELEITORES"
                    ]
                    .sum()
                    .reset_index()
                )
            total += len(pedaco)
            log(f"  [leitura] {membro}: {total:,} linhas processadas")
    if not partes:
        return pd.DataFrame(columns=["uf", "dimensao", "categoria", "eleitores"])
    quadro = (
        pd.concat(partes, ignore_index=True)
        .groupby(["uf", "dimensao", "categoria"], observed=True, dropna=False)["QT_ELEITORES"]
        .sum()
        .reset_index()
        .rename(columns={"QT_ELEITORES": "eleitores"})
    )
    log(f"  [ok] perfil do eleitorado: {len(quadro):,} agregados")
    return quadro
