from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

from tse_ds.config import RAIZ
from tse_ds.odsele import iterar_csvs

from .config import PASTA_APP

PASTA_DADOS = PASTA_APP / "zonas"
PASTA_ZIP = RAIZ / "data" / "zip"

ARQUIVO_LOCAIS = PASTA_DADOS / "locais_votacao_2026.parquet"
USER_AGENT = "BrazilTSE-DataScience/1.0 (github.com/local/brazil-tse-data-science)"
MAX_POR_ZONA = 4
TEMPO_ENTRE_REQUISICOES = 1.05


def extrair_locais() -> pd.DataFrame:
    """Extrai locais de votação (zona + endereço) de votacao_secao_2026 (1x, cacheado)."""
    if ARQUIVO_LOCAIS.exists():
        return pd.read_parquet(ARQUIVO_LOCAIS)
    zip_caminho = PASTA_ZIP / "votacao_secao_2026_BR.zip"
    if not zip_caminho.exists():
        return pd.DataFrame()
    inicio = time.time()
    colunas = [
        "SG_UF",
        "CD_MUNICIPIO",
        "NM_MUNICIPIO",
        "NR_ZONA",
        "NR_LOCAL_VOTACAO",
        "NM_LOCAL_VOTACAO",
        "DS_LOCAL_VOTACAO_ENDERECO",
    ]
    partes: list[pd.DataFrame] = []
    for pedaco in iterar_csvs(zip_caminho, usecols=colunas, chunksize=400_000):
        pedaco = pedaco.dropna(subset=["CD_MUNICIPIO", "NR_ZONA"])
        pedaco["CD_MUNICIPIO"] = (
            pd.to_numeric(pedaco["CD_MUNICIPIO"], errors="coerce").astype("Int64")
        )
        pedaco["NR_ZONA"] = pd.to_numeric(pedaco["NR_ZONA"], errors="coerce").astype("Int64")
        pedaco["NR_LOCAL_VOTACAO"] = pd.to_numeric(
            pedaco["NR_LOCAL_VOTACAO"], errors="coerce"
        ).astype("Int64")
        for coluna in (
            "SG_UF",
            "NM_MUNICIPIO",
            "NM_LOCAL_VOTACAO",
            "DS_LOCAL_VOTACAO_ENDERECO",
        ):
            pedaco[coluna] = pedaco[coluna].astype(str).str.strip()
        partes.append(pedaco)
    if not partes:
        return pd.DataFrame()
    quadro = pd.concat(partes, ignore_index=True)
    quadro = quadro.drop_duplicates(
        ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_LOCAL_VOTACAO", "DS_LOCAL_VOTACAO_ENDERECO"]
    )
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    quadro.to_parquet(ARQUIVO_LOCAIS, index=False)
    print(
        f"  [app] locais de votação 2026: {len(quadro):,} linhas "
        f"({time.time() - inicio:.1f}s, {ARQUIVO_LOCAIS.name})"
    )
    return quadro


def locais_municipio(uf: str, municipio_cd: int) -> pd.DataFrame:
    """Locais de votação do município (só lê o cache; sem extração na UI).

    Rode `python -m tse_app.bairros` (ou o worker do app) para gerar o parquet.
    """
    if not ARQUIVO_LOCAIS.exists():
        return pd.DataFrame()
    quadro = pd.read_parquet(ARQUIVO_LOCAIS)
    sub = quadro[
        (quadro["SG_UF"].astype(str).str.upper() == uf.upper())
        & (quadro["CD_MUNICIPIO"] == int(municipio_cd))
    ]
    return sub.sort_values(["NR_ZONA", "NR_LOCAL_VOTACAO"]).reset_index(drop=True)


def locais_por_zona(uf: str, municipio_cd: int, maximo: int = 3) -> dict[int, list[str]]:
    """Amostra de locais de votação por zona: {zona: ['ESCOLA — R. X, 123', ...]}."""
    quadro = locais_municipio(uf, municipio_cd)
    if quadro.empty:
        return {}
    saida: dict[int, list[str]] = {}
    for zona, grupo in quadro.groupby("NR_ZONA", observed=True):
        amostra = grupo.head(maximo)
        itens = [
            f"{linha.NM_LOCAL_VOTACAO} ({linha.DS_LOCAL_VOTACAO_ENDERECO})"
            for linha in amostra.itertuples()
        ]
        extra = len(grupo) - len(amostra)
        if extra > 0:
            itens.append(f"… e mais {extra} locais na zona")
        saida[int(zona)] = itens
    return saida


def _geocodificar_endereco(
    endereco: str, municipio: str, uf: str
) -> tuple[float, float] | None:
    consulta = f"{endereco}, {municipio}, {uf}, Brasil"
    try:
        resposta = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": consulta,
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "br",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resposta.raise_for_status()
        itens = resposta.json()
    except (requests.RequestException, ValueError):
        return None
    if not itens:
        return None
    try:
        return float(itens[0]["lat"]), float(itens[0]["lon"])
    except (KeyError, ValueError, TypeError):
        return None


def _geocodificar_locais(
    locais: pd.DataFrame, municipio: str, uf: str, destino: Path
) -> pd.DataFrame:
    """Geocodifica até MAX_POR_ZONA endereços por zona (cache parquet por município)."""
    if destino.exists():
        return pd.read_parquet(destino)
    amostras: list[pd.Series] = []
    for _, grupo in locais.groupby("NR_ZONA", observed=True):
        amostras.extend(grupo.head(MAX_POR_ZONA).to_dict("records"))
    linhas = []
    for indice, registro in enumerate(amostras, start=1):
        endereco = str(registro["DS_LOCAL_VOTACAO_ENDERECO"])
        coordenadas = _geocodificar_endereco(endereco, municipio, uf)
        time.sleep(TEMPO_ENTRE_REQUISICOES)
        if coordenadas is None:
            continue
        linhas.append(
            {
                "NR_ZONA": int(registro["NR_ZONA"]),
                "endereco": endereco,
                "local": str(registro["NM_LOCAL_VOTACAO"]),
                "lat": coordenadas[0],
                "lon": coordenadas[1],
            }
        )
        if indice % 10 == 0:
            print(f"  [app] geocodificados {indice}/{len(amostras)} locais…")
    quadro = pd.DataFrame(linhas)
    if not quadro.empty:
        destino.parent.mkdir(parents=True, exist_ok=True)
        quadro.to_parquet(destino, index=False)
    return quadro


def _bairros_osm(uf: str, municipio_cd: int, municipio: str) -> pd.DataFrame:
    """Centros dos bairros (place=suburb/neighbourhood) do município via Overpass/OSM."""
    from shapely.geometry import MultiPolygon, Point, Polygon
    from shapely.prepared import prep

    from . import geo

    mapa = PASTA_APP / "mapa_municipios.csv"
    ibge = None
    if mapa.exists():
        quadro_mapa = pd.read_csv(mapa)
        linha_mapa = quadro_mapa[quadro_mapa["municipio_cd"] == int(municipio_cd)]
        if not linha_mapa.empty:
            ibge = int(linha_mapa["municipio_ibge"].iloc[0])
    try:
        malha = geo.malha_municipios(uf)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    aneis = None
    if ibge is not None:
        for codarea, poligonos in malha:
            if str(codarea) == str(ibge):
                aneis = poligonos
                break
    if not aneis:
        return pd.DataFrame()
    # geo._extrair nega o y para coordenadas do Qt; restaura lat/lon reais
    forma = MultiPolygon(
        [Polygon([(x, -y) for x, y in anel]) for anel in aneis]
    )
    try:
        if not forma.is_valid:
            forma = forma.buffer(0)
    except Exception:  # noqa: BLE001
        pass
    limite = forma.bounds  # (minx, miny, maxx, maxy)
    consulta = (
        "[out:json][timeout:60];("
        f'node["place"~"^(suburb|neighbourhood|quarter)$"]({limite[1]},{limite[0]},{limite[3]},{limite[2]});'
        f'way["place"~"^(suburb|neighbourhood|quarter)$"]({limite[1]},{limite[0]},{limite[3]},{limite[2]});'
        ");out center tags;"
    )
    try:
        resposta = requests.post(
            "https://overpass-api.de/api/interpreter",
            data={"data": consulta},
            headers={"User-Agent": USER_AGENT},
            timeout=90,
        )
        resposta.raise_for_status()
        itens = resposta.json().get("elements", [])
    except (requests.RequestException, ValueError):
        return pd.DataFrame()
    # malha "qualidade=minima" é simplificada: ~1,3 km de tolerância na borda
    interno = prep(forma.buffer(0.012))
    linhas_bairro = []
    for elemento in itens:
        centro = elemento.get("center") or {}
        nome = (elemento.get("tags") or {}).get("name")
        try:
            lat = centro.get("lat", elemento.get("lat"))
            lon = centro.get("lon", elemento.get("lon"))
            ponto = Point(float(lon), float(lat))
        except (KeyError, ValueError, TypeError):
            continue
        if not nome or not interno.contains(ponto):
            continue
        linhas_bairro.append({"bairro": str(nome), "lat": ponto.y, "lon": ponto.x})
    quadro = pd.DataFrame(linhas_bairro).drop_duplicates("bairro")
    return quadro.reset_index(drop=True)


def bairros_zonas(uf: str, municipio_cd: int, municipio: str) -> pd.DataFrame:
    """Aproxima bairro→zona geocodificando locais de votação e bairros do OSM.

    Colunas: zona, bairro, lat, lon. Cacheado em data/app/zonas/.
    """
    destino = PASTA_DADOS / f"bairros_{uf}_{municipio_cd}.parquet"
    if destino.exists():
        return pd.read_parquet(destino)
    if not ARQUIVO_LOCAIS.exists():
        extrair_locais()
    locais = locais_municipio(uf, municipio_cd)
    if locais.empty:
        return pd.DataFrame()
    geocode_cache = PASTA_DADOS / f"geocode_{uf}_{municipio_cd}.parquet"
    pontos = _geocodificar_locais(locais, municipio, uf, geocode_cache)
    if pontos.empty:
        return pd.DataFrame()
    bairros = _bairros_osm(uf, municipio_cd, municipio)
    if bairros.empty:
        return pd.DataFrame()
    linhas = []
    for linha in bairros.itertuples():
        distancias = (pontos["lat"] - linha.lat) ** 2 + (
            (pontos["lon"] - linha.lon) * 0.9
        ) ** 2
        indice = distancias.idxmin()
        zona = int(pontos.loc[indice, "NR_ZONA"])
        linhas.append(
            {
                "zona": zona,
                "bairro": linha.bairro,
                "lat": float(linha.lat),
                "lon": float(linha.lon),
            }
        )
    quadro = pd.DataFrame(linhas).sort_values(["zona", "bairro"]).reset_index(drop=True)
    if not quadro.empty:
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        quadro.to_parquet(destino, index=False)
    return quadro


def bairros_por_zona(uf: str, municipio_cd: int, municipio: str) -> dict[int, list[str]]:
    """{zona: [bairros]} do cache; vazio se ainda não mapeado."""
    quadro = bairros_zonas(uf, municipio_cd, municipio)
    if quadro.empty:
        return {}
    return {
        int(zona): sorted(grupo["bairro"].tolist())
        for zona, grupo in quadro.groupby("zona", observed=True)
    }


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    quadro = extrair_locais()
    print(f"locais de votação extraídos: {len(quadro):,} linhas")
    if len(sys.argv) >= 4:
        uf_arg, cd_arg, nome_arg = sys.argv[1], int(sys.argv[2]), sys.argv[3]
        mapeado = bairros_zonas(uf_arg, cd_arg, nome_arg)
        print(f"bairros mapeados para {nome_arg}: {len(mapeado)}")
