from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import divulga, loaders
from .config import CARGOS_PRINCIPAIS, PADROES_ARQUIVO, PASTA_TABELAS, PASTA_ZIP, ROTULOS_CARGO, UFS
from .http import log

CARGOS_ANALISE = {2024: (11, 13), 2026: (1, 3, 5, 6)}
ELEICAO_PRINCIPAL = {2024: 619, 2026: 6257}


def caminho_zip(ano: int, recurso: str) -> Path:
    padrao = PADROES_ARQUIVO.get(recurso, "{recurso}_{ano}.zip")
    return PASTA_ZIP / padrao.format(ano=ano, recurso=recurso)


def tabela_votos(ano: int, cargos: tuple[int, ...] | None = None, force: bool = False) -> pd.DataFrame:
    destino = PASTA_TABELAS / f"votos_municipio_{ano}.parquet"
    alvos = tuple(cargos or CARGOS_ANALISE.get(ano, ()))
    if destino.exists() and not force:
        quadro_cache = pd.read_parquet(destino)
        presentes = (
            {int(c) for c in quadro_cache["cargo_cd"].dropna().unique()}
            if not quadro_cache.empty
            else set()
        )
        if not alvos or set(alvos) <= presentes:
            log(f"  [ok] reutilizando {destino.name}")
            return quadro_cache
        faltantes = sorted(set(alvos) - presentes)
        log(f"  [info] {destino.name} nao cobre os cargos {faltantes}; reconstruindo")
    zip_caminho = caminho_zip(ano, "votacao_candidato_munzona")
    if not zip_caminho.exists():
        log(f"  [erro] arquivo ausente: {zip_caminho}")
        return pd.DataFrame()
    quadro = loaders.ler_votacao_municipal(zip_caminho, cargos=alvos)

    presentes = {int(c) for c in quadro["cargo_cd"].dropna().unique()} if not quadro.empty else set()
    faltantes = tuple(cargo for cargo in alvos if cargo not in presentes)
    if faltantes:
        zip_secao = caminho_zip(ano, "votacao_secao")
        if zip_secao.exists():
            log(f"  [aviso] cargos {faltantes} ausentes em {zip_caminho.name}; usando {zip_secao.name}")
            cadastro = loaders.ler_cadastro_candidatos(caminho_zip(ano, "consulta_cand"))
            extra = loaders.ler_votacao_secao(zip_secao, cargos=faltantes, cadastro=cadastro)
            if not extra.empty:
                quadro = pd.concat([quadro, extra], ignore_index=True) if not quadro.empty else extra
        else:
            log(f"  [aviso] cargos {faltantes} indisponiveis: {zip_secao.name} ausente")

    if not quadro.empty:
        PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
        quadro.to_parquet(destino, index=False)
        log(f"  [ok] {destino.name}: {len(quadro):,} linhas")
    return quadro


def tabela_cadastro(ano: int, cargos: tuple[int, ...] | None = None, force: bool = False) -> pd.DataFrame:
    destino = PASTA_TABELAS / f"candidatos_{ano}.parquet"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_parquet(destino)
    zip_caminho = caminho_zip(ano, "consulta_cand")
    if not zip_caminho.exists():
        log(f"  [erro] arquivo ausente: {zip_caminho}")
        return pd.DataFrame()
    quadro = loaders.ler_cadastro_candidatos(zip_caminho, cargos=cargos or CARGOS_PRINCIPAIS)
    if not quadro.empty:
        quadro["idade"] = calcular_idade(quadro, ano)
        PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
        quadro.to_parquet(destino, index=False)
        log(f"  [ok] {destino.name}: {len(quadro):,} linhas")
    return quadro


def calcular_idade(quadro: pd.DataFrame, ano: int) -> pd.Series:
    nascimento = pd.to_datetime(quadro["nascimento"], format="%d/%m/%Y", errors="coerce")
    referencia = pd.Timestamp(f"{ano}-10-04" if ano == 2026 else f"{ano}-10-06")
    dias = (referencia - nascimento).dt.days
    return (dias.fillna(-1) // 365).astype("Int64").where(dias.notna())


def tabela_apuracao_uf(ano: int, force: bool = False) -> pd.DataFrame:
    destino = PASTA_TABELAS / f"apuracao_uf_{ano}.csv"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_csv(destino)

    quadro = pd.DataFrame()
    if ano == 2026:
        quadro = _apuracao_json(ano)
    if quadro.empty:
        zip_caminho = caminho_zip(ano, "detalhe_votacao_munzona")
        if zip_caminho.exists():
            quadro = loaders.ler_detalhe_munzona(zip_caminho)
        else:
            log(f"  [erro] sem fonte de apuracao para {ano}: {zip_caminho.name} ausente")
            return pd.DataFrame()

    quadro = quadro.sort_values("uf").reset_index(drop=True)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    quadro.to_csv(destino, index=False, encoding="utf-8")
    log(f"  [ok] {destino.name}: {len(quadro)} UFs")
    return quadro


def _apuracao_json(ano: int) -> pd.DataFrame:
    geral = divulga.carregar_todos_acompanhamentos(ano)
    if geral is None or geral.empty:
        log(f"  [aviso] sem arquivos de acompanhamento (EA14) para {ano}")
        return pd.DataFrame()
    preferida = ELEICAO_PRINCIPAL.get(ano)
    ufs = geral[
        (geral["tipo_abrangencia"] == "uf") & (geral["codigo_abrangencia"].str.upper().isin(set(UFS)))
    ]
    if preferida is not None and (ufs["codigo_eleicao"] == preferida).any():
        ufs = ufs[ufs["codigo_eleicao"] == preferida]
    else:
        primeiro = ufs["codigo_eleicao"].iloc[0]
        ufs = ufs[ufs["codigo_eleicao"] == primeiro]
    ufs = ufs.copy()
    ufs["uf"] = ufs["codigo_abrangencia"].str.upper()
    return ufs[
        [
            "uf",
            "eleitores",
            "comparecimento",
            "abstencao",
            "secoes_totais",
            "secoes_totalizadas",
            "pct_comparecimento",
            "pct_abstencao",
            "pct_secoes",
        ]
    ]


def resultado_por_candidato(
    quadro: pd.DataFrame,
    cargo_cd: int,
    por_uf: bool = False,
) -> pd.DataFrame:
    if quadro.empty:
        return pd.DataFrame()
    dados = quadro[quadro["cargo_cd"] == cargo_cd]
    if dados.empty:
        return pd.DataFrame()
    chaves = ["uf", "partido", "candidato_urna"] if por_uf else ["partido", "candidato_urna"]
    agregado = (
        dados.groupby(chaves, observed=True, dropna=False)[["votos", "votos_validos"]]
        .sum()
        .reset_index()
        .sort_values("votos", ascending=False)
        .reset_index(drop=True)
    )
    total = agregado["votos_validos"].sum()
    agregado["pct"] = 100.0 * agregado["votos_validos"] / total if total else 0.0
    agregado["cargo"] = ROTULOS_CARGO.get(str(cargo_cd), str(cargo_cd))
    return agregado


def candidatos_eleitos(quadro: pd.DataFrame, cargo_cd: int) -> pd.DataFrame:
    if quadro.empty:
        return pd.DataFrame()
    dados = quadro[
        (quadro["cargo_cd"] == cargo_cd)
        & quadro["situacao"].astype(str).str.upper().str.strip().str.startswith("ELEITO")
    ]
    if dados.empty:
        return pd.DataFrame()
    return (
        dados.groupby(["uf", "municipio", "partido", "candidato_urna"], observed=True, dropna=False)["votos"]
        .sum()
        .reset_index()
        .sort_values(["uf", "municipio"])
        .reset_index(drop=True)
    )


def vencedores_por_uf(quadro: pd.DataFrame, cargo_cd: int) -> pd.DataFrame:
    if quadro.empty:
        return pd.DataFrame()
    dados = quadro[quadro["cargo_cd"] == cargo_cd]
    if dados.empty:
        return pd.DataFrame()
    por_candidato = (
        dados.groupby(["uf", "partido", "candidato_urna"], observed=True, dropna=False)[["votos", "votos_validos"]]
        .sum()
        .reset_index()
    )
    totais_uf = por_candidato.groupby("uf", observed=True)["votos_validos"].sum().rename("validos_uf")
    por_candidato = por_candidato.join(totais_uf, on="uf")
    por_candidato["pct"] = 100.0 * por_candidato["votos_validos"] / por_candidato["validos_uf"]
    indice = por_candidato.groupby("uf", observed=True)["votos"].idxmax()
    vencedores = por_candidato.loc[indice].sort_values("uf").reset_index(drop=True)
    vencedores["cargo"] = ROTULOS_CARGO.get(str(cargo_cd), str(cargo_cd))
    return vencedores


COLUNAS_CADASTRO_ELEITOS = [
    "candidato_sq",
    "candidato",
    "candidato_nr",
    "nascimento",
    "idade",
    "genero",
    "raca",
    "escolaridade",
    "situacao_candidatura",
]


def tabela_partidos(ano: int, por_uf: bool = False, force: bool = False) -> pd.DataFrame:
    """Votos de todos os partidos, nacionalmente ou por estado, em todos os cargos analisados."""
    rotulo = "uf" if por_uf else "nacional"
    destino = PASTA_TABELAS / f"partidos_{rotulo}_{ano}.csv"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_csv(destino)
    votos = tabela_votos(ano)
    if votos.empty:
        return pd.DataFrame()
    chaves = (["uf"] if por_uf else []) + ["cargo_cd", "cargo", "partido", "partido_nome"]
    agregado = votos.groupby(chaves, observed=True, dropna=False)["votos"].sum().reset_index()
    grupos = ["cargo_cd"] + (["uf"] if por_uf else [])
    totais = agregado.groupby(grupos, observed=True, dropna=False)["votos"].transform("sum")
    agregado["pct"] = (100.0 * agregado["votos"] / totais.where(totais > 0)).fillna(0.0).round(2)
    agregado = agregado.sort_values(
        grupos + ["votos"], ascending=[True] * len(grupos) + [False]
    ).reset_index(drop=True)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    agregado.to_csv(destino, index=False, encoding="utf-8")
    log(f"  [ok] {destino.name}: {len(agregado):,} linhas")
    return agregado


def tabela_eleitos(ano: int, force: bool = False) -> pd.DataFrame:
    """Todos os candidatos eleitos nos cargos analisados, com partido, idade e genero."""
    destino = PASTA_TABELAS / f"eleitos_{ano}.csv"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_csv(destino)
    votos = tabela_votos(ano)
    cadastro = tabela_cadastro(ano)
    if votos.empty:
        return pd.DataFrame()
    situacao = votos["situacao"].astype(str).str.upper().str.strip()
    dados = votos[situacao.str.startswith("ELEITO")]
    if dados.empty:
        log(f"  [aviso] nenhum candidato eleito encontrado para {ano}")
        return pd.DataFrame()

    municipal = ano == 2024
    chaves = ["cargo_cd", "cargo", "uf"]
    if municipal:
        chaves.append("municipio")
    chaves += ["candidato_sq", "candidato_urna", "partido", "partido_nome"]
    agregado = dados.groupby(chaves, observed=True, dropna=False)[["votos"]].sum().reset_index()

    colunas = [c for c in COLUNAS_CADASTRO_ELEITOS if c in cadastro.columns]
    if not cadastro.empty and colunas:
        mapa = cadastro[colunas].drop_duplicates(subset=["candidato_sq"]).copy()
        agregado["candidato_sq"] = agregado["candidato_sq"].astype(str)
        mapa["candidato_sq"] = mapa["candidato_sq"].astype(str)
        agregado = agregado.merge(mapa, on="candidato_sq", how="left")
    agregado.insert(0, "ano", ano)

    ordenacao = ["cargo_cd", "uf"] + (["municipio"] if municipal else [])
    ascendente = [True] * len(ordenacao) + [False]
    agregado = agregado.sort_values(
        ordenacao + ["votos"], ascending=ascendente
    ).reset_index(drop=True)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    agregado.to_csv(destino, index=False, encoding="utf-8")
    log(f"  [ok] {destino.name}: {len(agregado):,} linhas")
    return agregado


def montar_pacote(ano: int, force: bool = False) -> dict[str, pd.DataFrame]:
    return {
        "votos": tabela_votos(ano, force=force),
        "candidatos": tabela_cadastro(ano, force=force),
        "apuracao": tabela_apuracao_uf(ano, force=force),
        "partidos": tabela_partidos(ano, force=force),
        "partidos_estado": tabela_partidos(ano, por_uf=True, force=force),
        "eleitos": tabela_eleitos(ano, force=force),
    }


def executar(anos: tuple[int, ...] | list[int], force: bool = False) -> dict[int, dict[str, pd.DataFrame]]:
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    return {ano: montar_pacote(ano, force=force) for ano in anos}
