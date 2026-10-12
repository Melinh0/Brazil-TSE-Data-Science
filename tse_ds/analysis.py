from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import divulga, ibge, loaders
from .config import CARGOS_PRINCIPAIS, PADROES_ARQUIVO, PASTA_TABELAS, PASTA_ZIP, ROTULOS_CARGO, UFS
from .http import log

CARGOS_ANALISE = {2024: (11, 13), 2026: (1, 3, 5, 6, 7, 8)}
ELEICAO_PRINCIPAL = {2024: 619, 2026: 6257}

FAIXAS_COMPARTILHADAS: dict[str, tuple[str, ...]] = {
    "16 a 17 anos": ("16 anos", "17 anos"),
    "18 a 24 anos": ("18 anos", "19 anos", "20 anos", "21 a 24 anos"),
    "25 a 34 anos": ("25 a 29 anos", "30 a 34 anos"),
    "35 a 44 anos": ("35 a 39 anos", "40 a 44 anos"),
    "45 a 54 anos": ("45 a 49 anos", "50 a 54 anos"),
    "55 a 59 anos": ("55 a 59 anos",),
    "60 a 69 anos": ("60 a 64 anos", "65 a 69 anos"),
    "70 anos ou mais": (
        "70 a 74 anos",
        "75 a 79 anos",
        "80 a 84 anos",
        "85 a 89 anos",
        "90 a 94 anos",
        "95 a 99 anos",
        "100 anos ou mais",
    ),
}


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
    total = agregado["votos"].sum()
    agregado["pct"] = 100.0 * agregado["votos"] / total if total else 0.0
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


def candidatos_por_uf(quadro: pd.DataFrame, cargo_cd: int) -> pd.DataFrame:
    """Todos os candidatos de cada UF, ordenados por votos, com posicao e percentual."""
    if quadro.empty:
        return pd.DataFrame()
    dados = quadro[quadro["cargo_cd"] == cargo_cd]
    if dados.empty:
        return pd.DataFrame()
    por_candidato = (
        dados.groupby(["uf", "partido", "candidato_urna"], observed=True, dropna=False)
        .agg(votos=("votos", "sum"), votos_validos=("votos_validos", "sum"), situacao=("situacao", "first"))
        .reset_index()
    )
    totais_uf = por_candidato.groupby("uf", observed=True)["votos"].sum().rename("total_uf")
    por_candidato = por_candidato.join(totais_uf, on="uf")
    por_candidato["pct"] = 100.0 * por_candidato["votos"] / por_candidato["total_uf"]
    por_candidato = por_candidato.sort_values(["uf", "votos"], ascending=[True, False]).reset_index(drop=True)
    por_candidato["posicao"] = por_candidato.groupby("uf", observed=True).cumcount() + 1
    por_candidato["cargo"] = ROTULOS_CARGO.get(str(cargo_cd), str(cargo_cd))
    return por_candidato


def vencedores_por_uf(quadro: pd.DataFrame, cargo_cd: int) -> pd.DataFrame:
    candidatos = candidatos_por_uf(quadro, cargo_cd)
    if candidatos.empty:
        return pd.DataFrame()
    vencedores = candidatos[candidatos["posicao"] == 1].copy().reset_index(drop=True)
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
    votos = tabela_votos(ano, force=force)
    if votos.empty:
        return pd.DataFrame()
    votos = votos.copy()
    votos["chave"] = votos["partido"].astype(str).str.replace(r"\s+", "", regex=True).str.upper()
    base = (["uf"] if por_uf else []) + ["cargo_cd", "cargo", "chave"]
    agregado = votos.groupby(base, observed=True, dropna=False)["votos"].sum().reset_index()
    detalhe = votos.groupby(base + ["partido", "partido_nome"], observed=True, dropna=False)["votos"].sum().reset_index()
    principais = detalhe.loc[
        detalhe.groupby(base, observed=True, dropna=False)["votos"].idxmax(), base + ["partido", "partido_nome"]
    ]
    colunas = (["uf"] if por_uf else []) + ["cargo_cd", "cargo", "partido", "partido_nome", "votos"]
    agregado = agregado.merge(principais, on=base)[colunas]
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


def tabela_senado_composicao(force: bool = False) -> pd.DataFrame:
    """Composição das 81 cadeiras do Senado após 2026 (classe 2026-2034 + meio mandato 2022-2030)."""
    destino = PASTA_TABELAS / "senado_composicao.csv"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_csv(destino)

    colunas = [
        "classe",
        "cargo",
        "uf",
        "candidato_sq",
        "candidato_urna",
        "candidato",
        "partido",
        "partido_nome",
        "nascimento",
        "idade",
        "genero",
        "raca",
        "escolaridade",
        "votos",
    ]
    quadros = []

    eleitos = tabela_eleitos(2026, force=force)
    if not eleitos.empty:
        classe26 = eleitos[eleitos["cargo_cd"] == 5].copy()
        if not classe26.empty:
            classe26["classe"] = 2026
            quadros.append(classe26[[c for c in colunas if c in classe26.columns]])

    zip22 = caminho_zip(2022, "consulta_cand")
    if zip22.exists():
        cadastro = loaders.ler_cadastro_candidatos(zip22, cargos=(5,))
        situacao = cadastro["situacao"].astype(str).str.upper().str.strip()
        classe22 = cadastro[situacao.str.startswith("ELEITO")].drop_duplicates("candidato_sq").copy()
        if not classe22.empty:
            classe22["idade"] = calcular_idade(classe22, 2026)
            classe22["classe"] = 2022
            classe22["cargo"] = "Senador"
            classe22["votos"] = pd.NA
            quadros.append(classe22[[c for c in colunas if c in classe22.columns]])
    else:
        log(f"  [aviso] {zip22.name} ausente; classe 2022 do senado indisponivel")

    if not quadros:
        return pd.DataFrame(columns=colunas)
    quadro = pd.concat(quadros, ignore_index=True, sort=False)
    for coluna in colunas:
        if coluna not in quadro:
            quadro[coluna] = pd.NA
    quadro = quadro[colunas].sort_values(["classe", "uf"]).reset_index(drop=True)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    quadro.to_csv(destino, index=False, encoding="utf-8")
    log(f"  [ok] {destino.name}: {len(quadro)} cadeiras ({', '.join(str(c) for c in sorted(quadro['classe'].unique()))})")
    return quadro


def tabela_eleitorado(ano: int, force: bool = False) -> pd.DataFrame:
    """Perfil do eleitorado agregado em formato longo (uf, dimensao, categoria, eleitores)."""
    destino = PASTA_TABELAS / f"perfil_eleitorado_{ano}.parquet"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_parquet(destino)
    zip_caminho = caminho_zip(ano, "perfil_eleitorado")
    if not zip_caminho.exists():
        log(f"  [erro] arquivo ausente: {zip_caminho}")
        return pd.DataFrame()
    quadro = loaders.ler_perfil_eleitorado(zip_caminho)
    if quadro.empty:
        return quadro
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    quadro.to_parquet(destino, index=False)
    log(f"  [ok] {destino.name}: {len(quadro):,} linhas")
    return quadro


def tabela_mais_votados(ano: int, force: bool = False) -> pd.DataFrame:
    """Top 20 nacional e top 10 por UF dos candidatos mais votados em cada cargo."""
    destino = PASTA_TABELAS / f"mais_votados_{ano}.csv"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_csv(destino)
    votos = tabela_votos(ano, force=force)
    cargos = CARGOS_ANALISE.get(ano, ())
    if votos.empty or not cargos:
        return pd.DataFrame()
    dados = votos[votos["cargo_cd"].isin(cargos) & votos["uf"].astype(str).str.upper().ne("ZZ")]
    chaves = ["cargo_cd", "cargo", "uf", "municipio", "candidato_urna", "partido", "partido_nome"]
    agregado = dados.groupby(chaves, observed=True, dropna=False)["votos"].sum().reset_index()
    agregado = agregado[agregado["votos"] > 0]
    if agregado.empty:
        return pd.DataFrame()

    total_nacional = agregado.groupby("cargo_cd", observed=True)["votos"].transform("sum")
    agregado["pct_nacional"] = 100.0 * agregado["votos"] / total_nacional
    total_uf = agregado.groupby(["cargo_cd", "uf"], observed=True)["votos"].transform("sum")
    agregado["pct_uf"] = 100.0 * agregado["votos"] / total_uf

    nacional = (
        agregado.sort_values(["cargo_cd", "votos"], ascending=[True, False])
        .groupby("cargo_cd", observed=True)
        .head(20)
        .assign(escopo="nacional")
    )
    nacional["posicao"] = nacional.groupby("cargo_cd", observed=True).cumcount() + 1
    nacional["pct"] = nacional["pct_nacional"]

    por_uf = (
        agregado.sort_values(["cargo_cd", "uf", "votos"], ascending=[True, True, False])
        .groupby(["cargo_cd", "uf"], observed=True)
        .head(10)
        .assign(escopo="uf")
    )
    por_uf["posicao"] = por_uf.groupby(["cargo_cd", "uf"], observed=True).cumcount() + 1
    por_uf["pct"] = por_uf["pct_uf"]

    colunas = [
        "cargo_cd",
        "cargo",
        "escopo",
        "uf",
        "posicao",
        "municipio",
        "candidato_urna",
        "partido",
        "partido_nome",
        "votos",
        "pct",
    ]
    quadro = pd.concat([nacional, por_uf], ignore_index=True)[colunas]
    quadro["pct"] = quadro["pct"].round(2)
    quadro["_uf_ordenacao"] = quadro["uf"].astype(str).where(quadro["escopo"] == "uf", "")
    quadro = quadro.sort_values(
        ["cargo_cd", "escopo", "_uf_ordenacao", "posicao"], na_position="last"
    ).drop(columns="_uf_ordenacao").reset_index(drop=True)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    quadro.to_csv(destino, index=False, encoding="utf-8")
    log(f"  [ok] {destino.name}: {len(quadro):,} linhas")
    return quadro


COLUNAS_SEGUNDO_TURNO = [
    "ano",
    "cargo_cd",
    "cargo",
    "uf",
    "municipio",
    "posicao",
    "candidato_urna",
    "partido",
    "partido_nome",
    "situacao",
    "eleito",
    "votos",
    "pct",
    "total_municipio",
    "vencedor",
    "vencedor_pct",
    "margem_votos",
    "margem_pct",
]


def tabela_segundo_turno(ano: int, force: bool = False) -> pd.DataFrame:
    """Candidatos disputantes de 2º turno, com votos, percentual e margem de vitória."""
    destino = PASTA_TABELAS / f"segundo_turno_{ano}.csv"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_csv(destino)
    vazio = pd.DataFrame(columns=COLUNAS_SEGUNDO_TURNO)
    votos = tabela_votos(ano, force=force)
    if votos.empty:
        return vazio
    dados = votos[
        (votos["turno"] == 2)
        & votos["uf"].astype(str).str.upper().ne("ZZ")
        & (votos["votos"] > 0)
    ]
    if dados.empty:
        log(f"  [aviso] nenhuma disputa de 2º turno na base de {ano}")
        return vazio
    chaves = [
        "cargo_cd",
        "cargo",
        "uf",
        "municipio",
        "candidato_urna",
        "partido",
        "partido_nome",
        "situacao",
    ]
    grupos = ["cargo_cd", "uf", "municipio"]
    quadro = dados.groupby(chaves, observed=True, dropna=False)["votos"].sum().reset_index()
    quadro = quadro.sort_values(grupos + ["votos"], ascending=[True, True, True, False])
    quadro["posicao"] = quadro.groupby(grupos, observed=True, dropna=False).cumcount() + 1
    quadro["total_municipio"] = quadro.groupby(grupos, observed=True, dropna=False)["votos"].transform("sum")
    quadro["pct"] = (100.0 * quadro["votos"] / quadro["total_municipio"].replace(0, pd.NA)).round(2)
    quadro["eleito"] = (
        quadro["situacao"].astype(str).str.upper().str.strip().str.startswith("ELEITO")
    )
    vencedor = quadro[quadro["posicao"] == 1][grupos + ["candidato_urna", "pct"]].rename(
        columns={"candidato_urna": "vencedor", "pct": "vencedor_pct"}
    )
    segundo = quadro[quadro["posicao"] == 2][grupos + ["votos", "pct"]].rename(
        columns={"votos": "segundo_votos", "pct": "segundo_pct"}
    )
    quadro = quadro.merge(vencedor, on=grupos).merge(segundo, on=grupos, how="left")
    quadro["margem_votos"] = quadro["votos"] - quadro["segundo_votos"]
    quadro["margem_pct"] = (quadro["pct"] - quadro["segundo_pct"]).round(2)
    quadro = quadro.drop(columns=["segundo_votos", "segundo_pct"])
    quadro.insert(0, "ano", ano)
    quadro = quadro[COLUNAS_SEGUNDO_TURNO].sort_values(
        ["cargo_cd", "margem_pct"], ascending=[True, False]
    ).reset_index(drop=True)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    quadro.to_csv(destino, index=False, encoding="utf-8")
    log(
        f"  [ok] {destino.name}: {len(quadro)} candidatos em "
        f"{quadro.groupby(grupos, observed=True).ngroups} disputas"
    )
    return quadro


def tabela_idade_tse_ibge(ano: int = 2024, force: bool = False) -> pd.DataFrame:
    """Eleitores x população residente por faixa etária comum (TSE x IBGE), por UF e Brasil."""
    destino = PASTA_TABELAS / f"idade_tse_ibge_{ano}.csv"
    if destino.exists() and not force:
        log(f"  [ok] reutilizando {destino.name}")
        return pd.read_csv(destino)
    eleitorado = tabela_eleitorado(ano, force=force)
    if eleitorado.empty:
        return pd.DataFrame()
    faixas = eleitorado[eleitorado["dimensao"] == "faixa_etaria"].copy()
    if faixas.empty:
        log("  [aviso] dimensao faixa_etaria ausente no perfil do eleitorado")
        return pd.DataFrame()
    mapa = {tse: compartilhada for compartilhada, itens in FAIXAS_COMPARTILHADAS.items() for tse in itens}
    faixas["faixa"] = faixas["categoria"].map(mapa)
    perdidas = sorted(set(faixas.loc[faixas["faixa"].isna(), "categoria"]))
    if perdidas:
        log(f"  [aviso] faixas sem equivalencia IBGE ignoradas: {', '.join(perdidas)}")
    faixas = faixas[faixas["faixa"].notna()]
    eleitores = faixas.groupby(["uf", "faixa"], observed=True)["eleitores"].sum().reset_index()
    try:
        populacao = ibge.populacao_uf_faixa(force=force)
    except Exception as erro:
        log(f"  [aviso] IBGE indisponivel ({erro}); comparacao de idade cancelada")
        return pd.DataFrame()
    if populacao.empty:
        return pd.DataFrame()
    quadro = eleitores.merge(populacao, on=["uf", "faixa"], how="inner")
    quadro["taxa"] = (100.0 * quadro["eleitores"] / quadro["populacao"].replace(0, pd.NA)).round(2)
    brasil = quadro.groupby("faixa", observed=True)[["eleitores", "populacao"]].sum().reset_index()
    brasil["uf"] = "BR"
    brasil["taxa"] = (100.0 * brasil["eleitores"] / brasil["populacao"].replace(0, pd.NA)).round(2)
    quadro = pd.concat([quadro, brasil], ignore_index=True)
    ordem = list(FAIXAS_COMPARTILHADAS)
    quadro["faixa"] = pd.Categorical(quadro["faixa"], categories=ordem, ordered=True)
    quadro = quadro.sort_values(["uf", "faixa"]).reset_index(drop=True)
    quadro["faixa"] = quadro["faixa"].astype(str)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    quadro.to_csv(destino, index=False, encoding="utf-8")
    log(f"  [ok] {destino.name}: {len(quadro):,} linhas")
    return quadro


def _corrigir_chave_municipio_tse_ibge(uf: str, municipio: str) -> str:
    """Corrige divergências de nome entre TSE e IBGE (Censo 2022)."""
    correcoes: dict[str, str] = {
        "BA|CAMACA": "CAMACAN",
        "MG|BARAO DE MONTE ALTO": "BARAO DO MONTE ALTO",
        "MG|DONA EUSEBIA": "DONA EUZEBIA",
        "MG|SAO THOME DAS LETRAS": "SAO TOME DAS LETRAS",
        "MT|SANTO ANTONIO DO LEVERGER": "SANTO ANTONIO DE LEVERGER",
        "PA|ELDORADO DOS CARAJAS": "ELDORADO DO CARAJAS",
        "PR|MUNHOZ DE MELLO": "MUNHOZ DE MELO",
        "RO|ALVORADA DO OESTE": "ALVORADA D OESTE",
        "RO|ESPIGAO DO OESTE": "ESPIGAO D OESTE",
        "RR|SAO LUIZ": "SAO LUIZ DO ANAUI",
        "SE|AMPARO DE SAO FRANCISCO": "AMPARO DO SAO FRANCISCO",
        "SP|SAO LUIS DO PARAITINGA": "SAO LUIZ DO PARAITINGA",
    }
    chave = f"{uf}|{ibge.normalizar_municipio(municipio)}"
    return correcoes.get(chave, ibge.normalizar_municipio(municipio))


COLUNAS_CRUZAMENTO_RESULTADO = [
    "votos_validos",
    "votos_brancos",
    "votos_nulos",
    "pct_invalidos",
    "votos_prefeito_1t",
    "candidatos_prefeito",
    "vencedor",
    "vencedor_votos",
    "vencedor_pct",
    "margem_pct",
    "segundo_turno",
]


def _resultados_prefeitura_1turno(votos: pd.DataFrame) -> pd.DataFrame:
    """Resultado da prefeitura por município (último turno disponível): vencedor e margem.

    Alguns municípios têm apenas o 2º turno no arquivo de votação (ex.: ARACAJU/SE);
    nesses casos o resultado é calculado a partir do turno disponível.
    """
    grupos = ["uf", "municipio"]
    base = votos[
        (votos["cargo_cd"] == 11)
        & votos["uf"].astype(str).str.upper().ne("ZZ")
        & (votos["votos"] > 0)
    ]
    if base.empty:
        return pd.DataFrame()
    um = base[base["turno"] == 1]
    dois = base[base["turno"] == 2]
    chaves_um = pd.MultiIndex.from_frame(um[grupos].drop_duplicates())
    chaves_dois = dois[grupos].drop_duplicates()
    so_dois = chaves_dois[~chaves_dois.set_index(grupos).index.isin(chaves_um)]
    if not so_dois.empty:
        usar = pd.concat(
            [um, dois[dois.set_index(grupos).index.isin(so_dois.set_index(grupos).index)]],
            ignore_index=True,
        )
    else:
        usar = um
    candidatos = (
        usar.groupby(grupos + ["candidato_urna"], observed=True, dropna=False)["votos"]
        .sum()
        .reset_index()
        .sort_values(grupos + ["votos"], ascending=[True, True, False])
    )
    candidatos["posicao"] = candidatos.groupby(grupos, observed=True, dropna=False).cumcount() + 1
    total = candidatos.groupby(grupos, observed=True, dropna=False)["votos"].sum().rename("votos_prefeito_1t")
    contagem = candidatos.groupby(grupos, observed=True, dropna=False).size().rename("candidatos_prefeito")
    vencedor = (
        candidatos[candidatos["posicao"] == 1]
        .set_index(grupos)[["candidato_urna", "votos"]]
        .rename(columns={"candidato_urna": "vencedor", "votos": "vencedor_votos"})
    )
    segundo = (
        candidatos[candidatos["posicao"] == 2]
        .set_index(grupos)["votos"]
        .rename("segundo_votos")
    )
    quadro = pd.concat([total, contagem, vencedor, segundo], axis=1).reset_index()
    base_total = quadro["votos_prefeito_1t"].replace(0, pd.NA)
    quadro["vencedor_pct"] = (100.0 * quadro["vencedor_votos"] / base_total).round(2)
    quadro["margem_pct"] = (
        100.0 * (quadro["vencedor_votos"] - quadro["segundo_votos"]) / base_total
    ).round(2)
    quadro["segundo_turno"] = quadro.set_index(grupos).index.isin(
        chaves_dois.set_index(grupos).index
    )
    return quadro.drop(columns=["segundo_votos"])


def tabela_cruzamento_municipios(ano: int = 2024, force: bool = False) -> pd.DataFrame:
    """Cruza apuracao municipal do TSE com renda/populacao IBGE e o resultado da eleicao."""
    destino = PASTA_TABELAS / f"cruzamento_municipios_{ano}.csv"
    if destino.exists() and not force:
        cache = pd.read_csv(destino)
        if set(COLUNAS_CRUZAMENTO_RESULTADO) <= set(cache.columns):
            log(f"  [ok] reutilizando {destino.name}")
            return cache
        log(f"  [info] {destino.name} sem as colunas de resultado; reconstruindo")
    zip_detalhe = caminho_zip(ano, "detalhe_votacao_munzona")
    if not zip_detalhe.exists():
        log(f"  [erro] arquivo ausente: {zip_detalhe}")
        return pd.DataFrame()
    try:
        renda = ibge.renda_municipal(force=force)
        populacao = ibge.populacao_municipal(force=force)
    except Exception as erro:
        log(f"  [aviso] IBGE indisponivel ({erro}); cruzamento municipal cancelado")
        return pd.DataFrame()
    if renda.empty or populacao.empty:
        return pd.DataFrame()
    detalhe = loaders.ler_detalhe_munzona(zip_detalhe, nivel="municipio")
    if detalhe.empty:
        return pd.DataFrame()

    base = renda.merge(
        populacao[["municipio_ibge", "uf", "populacao"]], on="municipio_ibge", how="left"
    )
    base["chave"] = base["uf"].astype(str) + "|" + base["municipio"].map(ibge.normalizar_municipio)
    duplicadas = base["chave"].duplicated(keep=False)
    if duplicadas.any():
        log(f"  [aviso] {int(duplicadas.sum())} municipios IBGE com chave duplicada; descartados")
        base = base[~duplicadas]
    base = base[["municipio_ibge", "chave", "populacao", "renda_media", "renda_mediana"]]
    detalhe["chave"] = detalhe.apply(
        lambda r: f"{r['uf']}|{_corrigir_chave_municipio_tse_ibge(r['uf'], r['municipio'])}",
        axis=1,
    )
    quadro = detalhe.merge(base, on="chave", how="left")
    sem_ibge = quadro[quadro["municipio_ibge"].isna()]
    if not sem_ibge.empty:
        exemplos = sorted((sem_ibge["uf"].astype(str) + " " + sem_ibge["municipio"].astype(str)))[:8]
        log(
            f"  [aviso] {len(sem_ibge)} municipios TSE sem correspondencia IBGE "
            f"(ex.: {', '.join(exemplos)})"
        )
    quadro["pct_eleitores_populacao"] = (
        100.0 * quadro["eleitores"] / quadro["populacao"].replace(0, pd.NA)
    ).round(2)
    quadro["pct_invalidos"] = (
        100.0
        * (quadro["votos_brancos"].fillna(0) + quadro["votos_nulos"].fillna(0))
        / quadro["votos"].replace(0, pd.NA)
    ).round(2)
    resultados = _resultados_prefeitura_1turno(tabela_votos(ano, force=force))
    if resultados.empty:
        log("  [aviso] resultado do 1º turno indisponivel; cruzamento sem colunas eleitorais")
        for coluna in COLUNAS_CRUZAMENTO_RESULTADO:
            if coluna not in quadro:
                quadro[coluna] = pd.NA
    else:
        quadro = quadro.merge(resultados, on=["uf", "municipio"], how="left")
        quadro["segundo_turno"] = quadro["segundo_turno"].eq(True)
        sem_resultado = int(quadro["vencedor"].isna().sum())
        if sem_resultado:
            log(
                f"  [aviso] {sem_resultado} municipios sem votos de prefeito "
                f"na base de votacao do TSE (lacuna do arquivo oficial)"
            )
    quadro["renda_faixa"] = pd.cut(
        quadro["renda_media"],
        bins=[0, 500, 1000, 2000, 4000, float("inf")],
        labels=[
            "até R$ 500",
            "R$ 500 a 1.000",
            "R$ 1.000 a 2.000",
            "R$ 2.000 a 4.000",
            "acima de R$ 4.000",
        ],
    ).astype(str).replace("nan", "sem dados (Censo 2022)")
    colunas = [
        "uf",
        "municipio",
        "municipio_cd",
        "eleitores",
        "comparecimento",
        "pct_comparecimento",
        "populacao",
        "pct_eleitores_populacao",
        "renda_media",
        "renda_mediana",
        "renda_faixa",
        "votos_validos",
        "votos_brancos",
        "votos_nulos",
        "pct_invalidos",
        "votos_prefeito_1t",
        "candidatos_prefeito",
        "vencedor",
        "vencedor_votos",
        "vencedor_pct",
        "margem_pct",
        "segundo_turno",
    ]
    colunas = [c for c in colunas if c in quadro.columns]
    quadro = quadro[colunas].sort_values(["uf", "municipio"]).reset_index(drop=True)
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    quadro.to_csv(destino, index=False, encoding="utf-8")
    log(f"  [ok] {destino.name}: {len(quadro):,} linhas")
    return quadro


def montar_pacote(ano: int, force: bool = False) -> dict[str, pd.DataFrame]:
    pacote = {
        "votos": tabela_votos(ano, force=force),
        "candidatos": tabela_cadastro(ano, force=force),
        "apuracao": tabela_apuracao_uf(ano, force=force),
        "partidos": tabela_partidos(ano, force=force),
        "partidos_estado": tabela_partidos(ano, por_uf=True, force=force),
        "eleitos": tabela_eleitos(ano, force=force),
        "senado": tabela_senado_composicao(force=force),
        "mais_votados": tabela_mais_votados(ano, force=force),
        "eleitorado": pd.DataFrame(),
        "idade_ibge": pd.DataFrame(),
        "cruzamento": pd.DataFrame(),
        "segundo_turno": pd.DataFrame(),
    }
    if caminho_zip(ano, "perfil_eleitorado").exists():
        pacote["eleitorado"] = tabela_eleitorado(ano, force=force)
    pacote["segundo_turno"] = tabela_segundo_turno(ano, force=force)
    if ano == 2024:
        pacote["idade_ibge"] = tabela_idade_tse_ibge(ano, force=force)
        pacote["cruzamento"] = tabela_cruzamento_municipios(ano, force=force)
    return pacote


def executar(anos: tuple[int, ...] | list[int], force: bool = False) -> dict[int, dict[str, pd.DataFrame]]:
    PASTA_TABELAS.mkdir(parents=True, exist_ok=True)
    return {ano: montar_pacote(ano, force=force) for ano in anos}
