from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import requests
from shapely.geometry import MultiPolygon, Polygon, shape

from .config import PASTA_GEO, NOMES_REGIAO, REGIOES, garantir_pastas_app

BASE_MALHAS = "https://servicodados.ibge.gov.br/api/v3/malhas"
FORMATO = "application/vnd.geo+json"
CABECALHO = {"User-Agent": "Brazil-TSE-Data-Science/1.0 (app desktop)"}

REGIAO_POR_ID = {"1": "N", "2": "NE", "3": "SE", "4": "S", "5": "CO"}

Poligonos = list[list[tuple[float, float]]]


def _baixar(nome: str, url: str) -> dict:
    garantir_pastas_app()
    destino: Path = PASTA_GEO / f"{nome}.geojson"
    if destino.exists() and destino.stat().st_size > 0:
        return json.loads(destino.read_text(encoding="utf-8"))
    resposta = requests.get(url, headers=CABECALHO, timeout=120)
    resposta.raise_for_status()
    bruto = resposta.text
    destino.write_text(bruto, encoding="utf-8")
    return json.loads(bruto)


def _extrair(geometria, area_minima: float) -> Poligonos:
    """Converte a geometria GeoJSON em anéis externos utilizáveis pelo Qt."""
    poligonos: Poligonos = []
    partes: list[Polygon]
    if isinstance(geometria, dict):
        objeto = shape(geometria)
    else:
        objeto = geometria
    if isinstance(objeto, Polygon):
        partes = [objeto]
    elif isinstance(objeto, MultiPolygon):
        partes = list(objeto.geoms)
    else:
        partes = [g for g in getattr(objeto, "geoms", []) if isinstance(g, Polygon)]
    for parte in partes:
        if parte.is_empty or parte.area < area_minima:
            continue
        anel = [(float(x), float(-y)) for x, y in parte.exterior.coords]
        if len(anel) >= 4:
            poligonos.append(anel)
    return poligonos


def _features(bruto: dict) -> list[tuple[str, dict]]:
    return [
        (str(f.get("properties", {}).get("codarea", "")), f.get("geometry") or {})
        for f in bruto.get("features", [])
    ]


@lru_cache(maxsize=1)
def malha_regioes() -> list[tuple[str, Poligonos]]:
    """Malha das 5 regiões do Brasil (código: N, NE, S, SE, CO)."""
    bruto = _baixar(
        "regioes_brasil",
        f"{BASE_MALHAS}/paises/BR?intrarregiao=REGIAO&formato={FORMATO}&qualidade=minima",
    )
    saida: list[tuple[str, Poligonos]] = []
    for codarea, geometria in _features(bruto):
        sigla = REGIAO_POR_ID.get(codarea, codarea)
        aneis = _extrair(geometria, area_minima=0.05)
        if aneis:
            saida.append((sigla, aneis))
    return saida


@lru_cache(maxsize=1)
def malha_ufs() -> list[tuple[str, Poligonos]]:
    """Malha das 27 UFs (código: sigla da UF)."""
    from tse_ds.ibge import UF_POR_ID

    bruto = _baixar(
        "brasil_ufs",
        f"{BASE_MALHAS}/paises/BR?intrarregiao=UF&formato={FORMATO}&qualidade=minima",
    )
    saida: list[tuple[str, Poligonos]] = []
    for codarea, geometria in _features(bruto):
        sigla = UF_POR_ID.get(int(codarea), codarea) if codarea.isdigit() else codarea
        aneis = _extrair(geometria, area_minima=0.02)
        if aneis:
            saida.append((str(sigla).upper(), aneis))
    return saida


@lru_cache(maxsize=32)
def malha_municipios(uf: str) -> list[tuple[str, Poligonos]]:
    """Malha dos municípios de uma UF (código: código IBGE de 7 dígitos)."""
    bruto = _baixar(
        f"municipios_{uf}",
        f"{BASE_MALHAS}/estados/{uf}?intrarregiao=municipio&formato={FORMATO}&qualidade=minima",
    )
    saida: list[tuple[str, Poligonos]] = []
    for codarea, geometria in _features(bruto):
        aneis = _extrair(geometria, area_minima=0.0015)
        if aneis:
            saida.append((codarea, aneis))
    return saida


def ufs_da_regiao(sigla: str) -> set[str]:
    return set(REGIOES.get(sigla, ()))


def nome_regiao(sigla: str) -> str:
    return NOMES_REGIAO.get(sigla, sigla)
