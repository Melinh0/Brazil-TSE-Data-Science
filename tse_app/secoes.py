from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pandas as pd

from tse_ds.config import RAIZ
from tse_ds.odsele import iterar_csvs

from .config import PASTA_APP

PASTA_DADOS = PASTA_APP / "zonas"
PASTA_ZIP = RAIZ / "data" / "zip"

# 2026: consolidado BR em um zip; 2024: um zip por UF (baixado sob demanda).
ANOS_SECOES = (2024, 2026)
URL_SECAO = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_secao/"
    "votacao_secao_{ano}_{uf}.zip"
)


class SecoesErro(RuntimeError):
    """Falha ao obter as seções (zip ausente, download com falha ou corrompido)."""

COLUNAS = [
    "SG_UF",
    "CD_MUNICIPIO",
    "NR_ZONA",
    "NR_SECAO",
    "NR_TURNO",
    "CD_CARGO",
    "NR_VOTAVEL",
    "NM_VOTAVEL",
    "QT_VOTOS",
]


def caminho_cache(ano: int, uf: str) -> Path:
    return PASTA_DADOS / f"secoes_{ano}_{uf.upper()}.parquet"


def _zip_secao(ano: int, uf: str) -> Path:
    if ano == 2026:
        return PASTA_ZIP / "votacao_secao_2026_BR.zip"
    return PASTA_ZIP / f"votacao_secao_{ano}_{uf.upper()}.zip"


def _garantir_zip(ano: int, uf: str) -> Path:
    """Zip de seções do ano/UF; em 2024 baixa o arquivo da UF se ausente.

    Levanta `SecoesErro` quando o arquivo não pode ser obtido (a UI mostra o
    motivo em vez de ficar em branco).
    """
    caminho = _zip_secao(ano, uf)
    if caminho.exists():
        return caminho
    if ano == 2026:
        raise SecoesErro(
            f"{caminho.name} ausente em {PASTA_ZIP} — rode "
            "'python main.py baixar --recurso votacao_secao' e abra a aba de novo"
        )
    from tse_ds.http import ClienteHTTP

    url = URL_SECAO.format(ano=ano, uf=uf.upper())
    PASTA_ZIP.mkdir(parents=True, exist_ok=True)
    print(f"  [app] baixando {caminho.name} (seções {ano}/{uf.upper()})…")
    try:
        ClienteHTTP().baixar(url, caminho)
    except Exception as erro:  # noqa: BLE001
        caminho.unlink(missing_ok=True)  # remove download parcial
        raise SecoesErro(f"falha no download de {caminho.name}: {erro}") from erro
    if not caminho.exists():
        raise SecoesErro(f"download de {caminho.name} não produziu o arquivo")
    return caminho


def extrair_uf(uf: str, ano: int = 2026) -> pd.DataFrame:
    """Votos por seção eleitoral de uma UF no ano (cacheado).

    Com uf='BR' (2026) extrai o consolidado nacional inteiro — é a fonte das
    visões Brasil/região/UF. Mantém apenas o turno decisivo de cada
    município/cargo (mesmo critério de votos()).
    """
    uf = uf.upper()
    destino = caminho_cache(ano, uf)
    if destino.exists():
        return pd.read_parquet(destino)
    if uf == "BR" and ano != 2026:
        raise SecoesErro(
            f"as eleições de {ano} não têm consolidado nacional de seções "
            "(o TSE publica um zip por UF) — a visão Brasil/região agrega os "
            "zips por UF já baixados em data/zip"
        )
    zip_caminho = _garantir_zip(ano, uf)
    try:
        with zipfile.ZipFile(zip_caminho):  # valida o cabeçalho antes de iterar
            pass
    except zipfile.BadZipFile as erro:
        zip_caminho.unlink(missing_ok=True)  # download parcial/corrompido
        raise SecoesErro(
            f"{zip_caminho.name} corrompido (download interrompido?) — "
            "arquivo removido; abra a aba de novo para baixar outra vez"
        ) from erro
    inicio = time.time()
    chaves = [
        "SG_UF",
        "CD_MUNICIPIO",
        "NR_ZONA",
        "NR_SECAO",
        "NR_TURNO",
        "CD_CARGO",
        "NR_VOTAVEL",
        "NM_VOTAVEL",
    ]
    partes: list[pd.DataFrame] = []
    for pedaco in iterar_csvs(zip_caminho, usecols=COLUNAS, chunksize=400_000):
        if uf != "BR":
            pedaco = pedaco[pedaco["SG_UF"].astype(str).str.upper() == uf]
        if pedaco.empty:
            continue
        for coluna in (
            "CD_MUNICIPIO",
            "NR_ZONA",
            "NR_SECAO",
            "NR_TURNO",
            "CD_CARGO",
        ):
            pedaco[coluna] = pd.to_numeric(pedaco[coluna], errors="coerce").astype("Int64")
        pedaco["QT_VOTOS"] = (
            pd.to_numeric(pedaco["QT_VOTOS"], errors="coerce").fillna(0).astype("int64")
        )
        pedaco["NM_VOTAVEL"] = pedaco["NM_VOTAVEL"].astype(str).str.strip()
        # agrega já no chunk: dispensa manter todas as linhas brutas em memória
        partes.append(
            pedaco.groupby(chaves, observed=True)["QT_VOTOS"].sum().reset_index()
        )
    if not partes:
        return pd.DataFrame()
    quadro = pd.concat(partes, ignore_index=True)
    turno_max = quadro.groupby(["CD_MUNICIPIO", "CD_CARGO"], observed=True)[
        "NR_TURNO"
    ].transform("max")
    quadro = quadro[quadro["NR_TURNO"] == turno_max]
    resumo = (
        quadro.groupby(
            [
                "SG_UF",
                "CD_MUNICIPIO",
                "NR_ZONA",
                "NR_SECAO",
                "CD_CARGO",
                "NR_VOTAVEL",
                "NM_VOTAVEL",
            ],
            observed=True,
        )
        .agg(votos=("QT_VOTOS", "sum"))
        .reset_index()
    )
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    resumo.to_parquet(destino, index=False)
    print(
        f"  [app] seções {ano}/{uf}: {len(resumo):,} linhas "
        f"({time.time() - inicio:.1f}s, {destino.name})"
    )
    return resumo


def secoes_municipio(
    ano: int, uf: str, municipio_cd: int, cargo_cd: int | None = None
) -> pd.DataFrame:
    """Votos por seção do município (turno decisivo), sem extração na UI.

    Uma linha por (zona, seção, cargo, candidato/votável).
    """
    destino = caminho_cache(ano, uf)
    if not destino.exists():
        return pd.DataFrame()
    quadro = pd.read_parquet(destino)
    quadro = quadro[quadro["CD_MUNICIPIO"] == int(municipio_cd)]
    if quadro.empty:
        return quadro
    if cargo_cd is not None:
        quadro = quadro[quadro["CD_CARGO"] == int(cargo_cd)]
    return quadro.sort_values("votos", ascending=False).reset_index(drop=True)


def totais_secao(
    ano: int, uf: str, municipio_cd: int, cargo_cd: int | None = None
) -> pd.DataFrame:
    """Votos totais por seção (somando todos os votáveis), para gráficos."""
    quadro = secoes_municipio(ano, uf, municipio_cd, cargo_cd)
    if quadro.empty:
        return quadro
    return (
        quadro.groupby(["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO"], observed=True)[
            "votos"
        ]
        .sum()
        .reset_index()
        .sort_values("votos", ascending=False)
        .reset_index(drop=True)
    )


def precisa_extrair(ano: int, uf: str) -> bool:
    return ano in ANOS_SECOES and not caminho_cache(ano, uf).exists()


def status_pendencia(ano: int, uf: str) -> str:
    """Mensagem da aba Seções quando o cache do ano/UF ainda não existe."""
    uf = uf.upper()
    if caminho_cache(ano, uf).exists():
        return (
            "O cache da UF existe, mas este município/cargo não tem linhas de "
            "seção (turno decisivo)."
        )
    if ano == 2024 and uf == "BR":
        return (
            "2024 não tem consolidado nacional: a visão do Brasil/região agrega "
            "os zips por UF de data/zip (nenhum UF disponível ainda). Navegue até "
            "um município/UF para baixar o zip da UF automaticamente."
        )
    if _zip_secao(ano, uf).exists():
        return (
            "Extraindo o arquivo de seções em segundo plano — a tabela "
            "preenche ao concluir (status na barra inferior)."
        )
    if ano == 2026:
        return (
            "votacao_secao_2026_BR.zip ausente em data/zip — rode "
            "'python main.py baixar --recurso votacao_secao' e abra a aba de novo."
        )
    return (
        "Baixando o zip de seções da UF do TSE em segundo plano — a tabela "
        "preenche ao concluir (status na barra inferior)."
    )


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    uf_arg = sys.argv[1].upper() if len(sys.argv) > 1 else "CE"
    ano_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    try:
        quadro = extrair_uf(uf_arg, ano_arg)
    except SecoesErro as erro:
        print(f"[erro] {erro}")
        sys.exit(1)
    print(f"seções {ano_arg}/{uf_arg}: {len(quadro):,} linhas")
