from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

from .http import ClienteHTTP, log


def baixar_zip(cliente: ClienteHTTP, url: str, destino: Path, force: bool = False) -> Path:
    return cliente.baixar(url, destino, force=force)


def membros_csv(caminho: Path) -> list[str]:
    with zipfile.ZipFile(caminho) as arquivo:
        return [nome for nome in arquivo.namelist() if nome.lower().endswith(".csv")]


def cabecalho_csv(caminho: Path, membro: str | None = None) -> list[str]:
    if caminho.suffix.lower() != ".zip":
        with open(caminho, encoding="latin-1") as arquivo:
            linha = arquivo.readline().rstrip("\r\n")
    else:
        with zipfile.ZipFile(caminho) as arquivo:
            nome = membro or membros_csv(caminho)[0]
            with arquivo.open(nome) as bruto:
                texto = io.TextIOWrapper(bruto, encoding="latin-1")
                linha = texto.readline().rstrip("\r\n")
    return [coluna.strip().strip('"') for coluna in linha.split(";")]


def iterar_csvs(
    caminho: Path,
    usecols: list[str] | None = None,
    chunksize: int | None = None,
    membro: str | None = None,
    **kwargs,
) -> Iterator[pd.DataFrame]:
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".zip":
        alvos = [membro] if membro else membros_csv(caminho)
    else:
        alvos = [None]

    for nome_membro in alvos:
        disponiveis = set(cabecalho_csv(caminho, nome_membro))
        colunas = [col for col in (usecols or []) if col in disponiveis] or None
        faltando = sorted(set(usecols or []) - disponiveis)
        if faltando:
            log(f"  [aviso] {nome_membro or caminho.name}: colunas ausentes ignoradas -> {', '.join(faltando)}")

        arquivo_zip = None
        if caminho.suffix.lower() == ".zip":
            arquivo_zip = zipfile.ZipFile(caminho)
            texto = io.TextIOWrapper(arquivo_zip.open(nome_membro), encoding="latin-1", newline="")
        else:
            texto = open(caminho, encoding="latin-1", newline="")
        try:
            leitor = pd.read_csv(
                texto,
                sep=";",
                usecols=colunas,
                dtype=str,
                chunksize=chunksize,
                low_memory=False,
                **kwargs,
            )
            if chunksize:
                yield from leitor
            else:
                yield leitor
        finally:
            texto.close()
            if arquivo_zip is not None:
                arquivo_zip.close()


def ler_csvs(caminho: Path, usecols: list[str] | None = None, **kwargs) -> pd.DataFrame:
    partes = list(iterar_csvs(caminho, usecols=usecols, **kwargs))
    if not partes:
        return pd.DataFrame(columns=usecols or [])
    return pd.concat(partes, ignore_index=True)
