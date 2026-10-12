from __future__ import annotations

from dataclasses import dataclass

from .config import NOMES_REGIAO, NOMES_UF, REGIOES, UF_REGIAO

TIPO_BR = "BR"
TIPO_REGIAO = "REGIAO"
TIPO_UF = "UF"
TIPO_MUNICIPIO = "MUNICIPIO"


@dataclass(frozen=True)
class Escopo:
    """Unidade geográfica corrente da análise (Brasil, região, UF ou município)."""

    tipo: str
    codigo: str
    nome: str
    uf: str | None = None
    regiao: str | None = None

    @property
    def nivel(self) -> int:
        return {TIPO_BR: 0, TIPO_REGIAO: 1, TIPO_UF: 2, TIPO_MUNICIPIO: 3}[self.tipo]

    @property
    def titulo(self) -> str:
        if self.tipo == TIPO_MUNICIPIO:
            return f"{self.nome}/{self.uf}"
        return self.nome


def escopo_brasil() -> Escopo:
    return Escopo(TIPO_BR, "BR", "Brasil")


def escopo_regiao(sigla: str) -> Escopo:
    return Escopo(TIPO_REGIAO, sigla, NOMES_REGIAO[sigla], regiao=sigla)


def escopo_uf(uf: str) -> Escopo:
    return Escopo(
        TIPO_UF, uf, NOMES_UF.get(uf, uf), uf=uf, regiao=UF_REGIAO[uf]
    )


def escopo_municipio(uf: str, codigo: int | str, nome: str) -> Escopo:
    return Escopo(
        TIPO_MUNICIPIO,
        str(codigo),
        nome,
        uf=uf,
        regiao=UF_REGIAO[uf],
    )


def filhos(escopo: Escopo) -> list[Escopo]:
    """Escopos filhos (nível imediatamente abaixo) do escopo atual."""
    if escopo.tipo == TIPO_BR:
        return [escopo_regiao(s) for s in REGIOES]
    if escopo.tipo == TIPO_REGIAO:
        return [escopo_uf(uf) for uf in REGIOES[escopo.codigo]]
    return []


def trilha(escopo: Escopo) -> list[Escopo]:
    """Caminho Brasil → região → UF → município até o escopo atual (para o breadcrumb)."""
    caminho = [escopo_brasil()]
    if escopo.tipo == TIPO_BR:
        return caminho
    caminho.append(escopo_regiao(escopo.regiao or UF_REGIAO[escopo.uf or ""]))
    if escopo.tipo == TIPO_REGIAO:
        return caminho
    caminho.append(escopo_uf(escopo.uf or ""))
    if escopo.tipo == TIPO_UF:
        return caminho
    caminho.append(escopo)
    return caminho
