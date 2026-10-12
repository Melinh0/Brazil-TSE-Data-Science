from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from tse_ds.config import RAIZ
from tse_ds.odsele import iterar_csvs, membros_csv

from .config import PASTA_APP

PASTA_ZONAS = PASTA_APP / "zonas"
PASTA_ZIP = RAIZ / "data" / "zip"

COLUNAS_ZONA = [
    "NR_TURNO",
    "SG_UF",
    "CD_MUNICIPIO",
    "NM_MUNICIPIO",
    "NR_ZONA",
    "CD_CARGO",
    "SQ_CANDIDATO",
    "SG_PARTIDO",
    "NM_URNA_CANDIDATO",
    "NM_CANDIDATO",
    "DS_SIT_TOT_TURNO",
    "QT_VOTOS_NOMINAIS",
]


def _zip_zonal(ano: int) -> Path | None:
    caminho = PASTA_ZIP / f"votacao_candidato_munzona_{ano}.zip"
    return caminho if caminho.exists() else None


def cache_zonas_existe(ano: int, uf: str) -> bool:
    """True quando o cache de zonas da UF já foi gerado (leitura barata)."""
    return (PASTA_ZONAS / f"votos_zona_{ano}_{uf.upper()}.parquet").exists()


def _membro_uf(zip_caminho: Path, uf: str) -> str | None:
    sufixo = f"_{uf.upper()}.CSV"
    for nome in membros_csv(zip_caminho):
        alto = nome.upper()
        if alto.endswith(sufixo) and "BRASIL" not in alto:
            return nome
    return None


def votos_zona(ano: int, uf: str) -> pd.DataFrame:
    """Votos nominais por zona eleitoral de uma UF (cache em data/app/zonas/)."""
    uf = uf.upper().strip()
    destino = PASTA_ZONAS / f"votos_zona_{ano}_{uf}.parquet"
    if destino.exists():
        return pd.read_parquet(destino)
    zip_caminho = _zip_zonal(ano)
    if zip_caminho is None:
        return pd.DataFrame()
    membro = _membro_uf(zip_caminho, uf)
    if membro is None:
        return pd.DataFrame()
    inicio = time.time()
    partes: list[pd.DataFrame] = []
    for pedaco in iterar_csvs(
        zip_caminho, usecols=COLUNAS_ZONA, chunksize=250_000, membro=membro
    ):
        if pedaco.empty:
            continue
        pedaco["SG_UF"] = pedaco["SG_UF"].astype(str).str.upper().str.strip()
        pedaco = pedaco[pedaco["SG_UF"] == uf.upper()]
        if pedaco.empty:
            continue
        pedaco["QT_VOTOS_NOMINAIS"] = (
            pd.to_numeric(pedaco["QT_VOTOS_NOMINAIS"], errors="coerce").fillna(0).astype("int64")
        )
        pedaco["CD_MUNICIPIO"] = pd.to_numeric(
            pedaco["CD_MUNICIPIO"], errors="coerce"
        ).astype("Int64")
        pedaco["NR_ZONA"] = pd.to_numeric(pedaco["NR_ZONA"], errors="coerce").astype("Int64")
        pedaco["CD_CARGO"] = pd.to_numeric(pedaco["CD_CARGO"], errors="coerce").astype("Int64")
        pedaco["NR_TURNO"] = pd.to_numeric(pedaco["NR_TURNO"], errors="coerce").astype("Int64")
        for coluna in ("SG_PARTIDO", "NM_URNA_CANDIDATO", "NM_CANDIDATO", "DS_SIT_TOT_TURNO"):
            pedaco[coluna] = pedaco[coluna].astype(str).str.strip()
        partes.append(
            pedaco[
                [
                    "NR_TURNO",
                    "SG_UF",
                    "CD_MUNICIPIO",
                    "NM_MUNICIPIO",
                    "NR_ZONA",
                    "CD_CARGO",
                    "SQ_CANDIDATO",
                    "SG_PARTIDO",
                    "NM_URNA_CANDIDATO",
                    "NM_CANDIDATO",
                    "DS_SIT_TOT_TURNO",
                    "QT_VOTOS_NOMINAIS",
                ]
            ]
        )
    if not partes:
        return pd.DataFrame()
    quadro = pd.concat(partes, ignore_index=True)
    PASTA_ZONAS.mkdir(parents=True, exist_ok=True)
    quadro.to_parquet(destino, index=False)
    print(
        f"  [app] cache de zonas {ano}/{uf}: {len(quadro):,} linhas "
        f"({time.time() - inicio:.1f}s, {destino.name})"
    )
    return quadro


def zonas_municipio(ano: int, uf: str, municipio_cd: int) -> pd.DataFrame:
    """Votos por zona de um município, já no turno decisivo de cada cargo."""
    quadro = votos_zona(ano, uf)
    if quadro.empty:
        return quadro
    quadro = quadro[quadro["CD_MUNICIPIO"] == int(municipio_cd)]
    if quadro.empty:
        return quadro
    turno_max = quadro.groupby("CD_CARGO", observed=True)["NR_TURNO"].transform("max")
    quadro = quadro[quadro["NR_TURNO"] == turno_max]
    return quadro.reset_index(drop=True)
