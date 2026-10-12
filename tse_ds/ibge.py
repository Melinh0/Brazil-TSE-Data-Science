from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

from .config import PASTA_IBGE, UFS
from .http import ClienteHTTP, log

BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
PERIODO_CENSO = "2022"

TABELA_POP_MUNICIPAL = 4714
TABELA_POP_SEXO_IDADE = 9514
TABELA_RENDA_MUNICIPAL = 10295
TABELA_PIB_MUNICIPAL = 5938

VAR_POPULACAO = "93"
VAR_RENDA_MEDIA = "13431"
VAR_RENDA_MEDIANA = "13534"
VAR_PIB_TOTAL = "37"

SEXO_HOMENS = 4
SEXO_MULHERES = 5
ROTULO_SEXO = {SEXO_HOMENS: "Masculino", SEXO_MULHERES: "Feminino"}

FAIXAS_IDADE_IBGE: dict[str, tuple[int, ...]] = {
    "16 a 17 anos": (6573, 6574),
    "18 a 24 anos": (6575, 6576, 93087),
    "25 a 34 anos": (93088, 93089),
    "35 a 44 anos": (93090, 93091),
    "45 a 54 anos": (93092, 93093),
    "55 a 59 anos": (93094,),
    "60 a 69 anos": (93095, 93096),
    "70 anos ou mais": (93097, 93098, 49108, 49109, 60040, 60041, 6653),
}

UF_POR_ID = {
    11: "RO",
    12: "AC",
    13: "AM",
    14: "RR",
    15: "PA",
    16: "AP",
    17: "TO",
    21: "MA",
    22: "PI",
    23: "CE",
    24: "RN",
    25: "PB",
    26: "PE",
    27: "AL",
    28: "SE",
    29: "BA",
    31: "MG",
    32: "ES",
    33: "RJ",
    35: "SP",
    41: "PR",
    42: "SC",
    43: "RS",
    50: "MS",
    51: "MT",
    52: "GO",
    53: "DF",
}

_cliente: ClienteHTTP | None = None


def _http() -> ClienteHTTP:
    global _cliente
    if _cliente is None:
        _cliente = ClienteHTTP(rps=2.0, timeout=180)
    return _cliente


def normalizar_municipio(nome: str) -> str:
    """Normaliza nomes de municípios para cruzamento TSE x IBGE."""
    texto = unicodedata.normalize("NFKD", str(nome))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9]+", " ", texto.upper())
    return re.sub(r"\s+", " ", texto).strip()


def _consultar(
    tabela: int,
    variaveis: str,
    localidades: str,
    classificacao: str | None = None,
    force: bool = False,
) -> list:
    chave = hashlib.sha1(
        f"{tabela}|{PERIODO_CENSO}|{variaveis}|{localidades}|{classificacao}".encode()
    ).hexdigest()[:12]
    destino = PASTA_IBGE / f"{tabela}_{chave}.json"
    if destino.exists() and not force:
        return json.loads(destino.read_text(encoding="utf-8"))
    url = f"{BASE}/{tabela}/periodos/{PERIODO_CENSO}/variaveis/{variaveis}"
    params: dict[str, str] = {"localidades": localidades}
    if classificacao:
        params["classificacao"] = classificacao
    bruto = _http().get_json(url, params=params)
    PASTA_IBGE.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(bruto, ensure_ascii=False), encoding="utf-8")
    log(f"  [ibge] tabela {tabela}: {destino.name} ({destino.stat().st_size:,} bytes)")
    return bruto


def _valor(serie: dict) -> float:
    try:
        return float((serie.get("serie") or serie).get(PERIODO_CENSO))
    except (TypeError, ValueError):
        return float("nan")


def _categoria(resultado: dict, classificacao_id: str) -> tuple[int, str] | None:
    for classe in resultado.get("classificacoes") or []:
        if str(classe.get("id")) != classificacao_id:
            continue
        for cat_id, nome in (classe.get("categoria") or {}).items():
            return int(cat_id), str(nome)
    return None


def _salvar(quadro: pd.DataFrame, destino: Path) -> pd.DataFrame:
    PASTA_IBGE.mkdir(parents=True, exist_ok=True)
    quadro.to_parquet(destino, index=False)
    log(f"  [ibge] {destino.name}: {len(quadro):,} linhas")
    return quadro


def _limpar_nome_municipio(nome: str) -> str:
    return re.sub(r"\s+-\s+[A-Z]{2}$", "", str(nome))


def populacao_municipal(force: bool = False) -> pd.DataFrame:
    """População residente por município (Censo 2022, tabela 4714)."""
    destino = PASTA_IBGE / "populacao_municipal.parquet"
    if destino.exists() and not force:
        log("  [ok] reutilizando data/ibge/populacao_municipal.parquet")
        return pd.read_parquet(destino)
    bruto = _consultar(TABELA_POP_MUNICIPAL, VAR_POPULACAO, "N6[all]", force=force)
    linhas = []
    for item in bruto:
        for resultado in item.get("resultados", []):
            for serie in resultado["series"]:
                localidade = serie["localidade"]
                codigo = int(localidade["id"])
                linhas.append(
                    {
                        "municipio_ibge": codigo,
                        "uf": UF_POR_ID.get(codigo // 100_000, ""),
                        "municipio": _limpar_nome_municipio(localidade["nome"]),
                        "populacao": _valor(serie),
                    }
                )
    quadro = pd.DataFrame(linhas, columns=["municipio_ibge", "uf", "municipio", "populacao"])
    if quadro.empty:
        return quadro
    quadro["populacao"] = quadro["populacao"].round().astype("Int64")
    return _salvar(quadro, destino)


def populacao_uf_faixa(force: bool = False) -> pd.DataFrame:
    """População por UF e faixa etária compatível com o perfil do eleitorado (Censo 2022, tabela 9514)."""
    destino = PASTA_IBGE / "populacao_uf_faixa.parquet"
    if destino.exists() and not force:
        log("  [ok] reutilizando data/ibge/populacao_uf_faixa.parquet")
        return pd.read_parquet(destino)
    codigos = sorted({codigo for faixa in FAIXAS_IDADE_IBGE.values() for codigo in faixa})
    classificacao = f"287[{','.join(str(c) for c in codigos)}]"
    bruto = _consultar(TABELA_POP_SEXO_IDADE, VAR_POPULACAO, "N3[all]", classificacao, force=force)
    por_categoria: dict[int, dict[str, float]] = {}
    for item in bruto:
        for resultado in item.get("resultados", []):
            cat = _categoria(resultado, "287")
            if cat is None:
                continue
            valores = por_categoria.setdefault(cat[0], {})
            for serie in resultado["series"]:
                uf = UF_POR_ID.get(int(serie["localidade"]["id"]))
                if uf:
                    valores[uf] = _valor(serie)
    linhas = []
    for faixa, categorias in FAIXAS_IDADE_IBGE.items():
        for uf in UFS:
            total = sum(por_categoria.get(cat, {}).get(uf, 0.0) for cat in categorias)
            linhas.append({"uf": uf, "faixa": faixa, "populacao": total})
    quadro = pd.DataFrame(linhas)
    quadro["populacao"] = quadro["populacao"].round().astype("Int64")
    return _salvar(quadro, destino)


def populacao_uf_sexo(force: bool = False) -> pd.DataFrame:
    """População por UF e sexo (Censo 2022, tabela 9514)."""
    destino = PASTA_IBGE / "populacao_uf_sexo.parquet"
    if destino.exists() and not force:
        log("  [ok] reutilizando data/ibge/populacao_uf_sexo.parquet")
        return pd.read_parquet(destino)
    classificacao = f"2[{SEXO_HOMENS},{SEXO_MULHERES}]"
    bruto = _consultar(TABELA_POP_SEXO_IDADE, VAR_POPULACAO, "N3[all]", classificacao, force=force)
    linhas = []
    for item in bruto:
        for resultado in item.get("resultados", []):
            cat = _categoria(resultado, "2")
            if cat is None:
                continue
            rotulo = ROTULO_SEXO.get(cat[0], str(cat[0]))
            for serie in resultado["series"]:
                uf = UF_POR_ID.get(int(serie["localidade"]["id"]))
                if uf:
                    linhas.append({"uf": uf, "sexo": rotulo, "populacao": _valor(serie)})
    quadro = pd.DataFrame(linhas, columns=["uf", "sexo", "populacao"])
    if quadro.empty:
        return quadro
    quadro["populacao"] = quadro["populacao"].round().astype("Int64")
    return _salvar(quadro, destino)


def renda_municipal(force: bool = False) -> pd.DataFrame:
    """Rendimento domiciliar per capita por município (Censo 2022, tabela 10295)."""
    destino = PASTA_IBGE / "renda_municipal.parquet"
    if destino.exists() and not force:
        log("  [ok] reutilizando data/ibge/renda_municipal.parquet")
        return pd.read_parquet(destino)
    variaveis = f"{VAR_RENDA_MEDIA},{VAR_RENDA_MEDIANA}"
    bruto = _consultar(TABELA_RENDA_MUNICIPAL, variaveis, "N6[all]", "2[6794]", force=force)
    por_municipio: dict[int, dict] = {}
    for item in bruto:
        coluna = "renda_media" if str(item.get("id")) == VAR_RENDA_MEDIA else "renda_mediana"
        for resultado in item.get("resultados", []):
            for serie in resultado["series"]:
                localidade = serie["localidade"]
                codigo = int(localidade["id"])
                registro = por_municipio.setdefault(
                    codigo,
                    {
                        "municipio_ibge": codigo,
                        "municipio": _limpar_nome_municipio(localidade["nome"]),
                    },
                )
                registro[coluna] = _valor(serie)
    quadro = pd.DataFrame(por_municipio.values())
    if quadro.empty:
        return quadro
    for coluna in ("renda_media", "renda_mediana"):
        if coluna not in quadro:
            quadro[coluna] = float("nan")
    quadro = quadro[["municipio_ibge", "municipio", "renda_media", "renda_mediana"]].sort_values(
        "municipio_ibge"
    ).reset_index(drop=True)
    return _salvar(quadro, destino)


def pib_municipal(force: bool = False) -> pd.DataFrame:
    """PIB total e per capita por município (2022, tabela 5938; per capita = PIB / população)."""
    destino = PASTA_IBGE / "pib_municipal.parquet"
    if destino.exists() and not force:
        log("  [ok] reutilizando data/ibge/pib_municipal.parquet")
        return pd.read_parquet(destino)
    bruto = _consultar(TABELA_PIB_MUNICIPAL, VAR_PIB_TOTAL, "N6[all]", force=force)
    linhas = []
    for item in bruto:
        for resultado in item.get("resultados", []):
            for serie in resultado["series"]:
                localidade = serie["localidade"]
                codigo = int(localidade["id"])
                linhas.append(
                    {
                        "municipio_ibge": codigo,
                        "uf": UF_POR_ID.get(codigo // 100_000, ""),
                        "municipio": _limpar_nome_municipio(localidade["nome"]),
                        "pib_total": _valor(serie),
                    }
                )
    quadro = pd.DataFrame(linhas)
    if quadro.empty:
        return quadro
    pop = populacao_municipal()
    quadro = quadro.merge(
        pop[["municipio_ibge", "populacao"]], on="municipio_ibge", how="left"
    )
    # SIDRA 5938 publica o PIB em R$ mil; per capita em R$ cheios
    quadro["pib_per_capita"] = (
        quadro["pib_total"] * 1000 / quadro["populacao"]
    ).round(2)
    quadro = quadro.drop(columns=["populacao"]).sort_values("municipio_ibge")
    quadro = quadro[
        ["municipio_ibge", "uf", "municipio", "pib_total", "pib_per_capita"]
    ].reset_index(drop=True)
    return _salvar(quadro, destino)
