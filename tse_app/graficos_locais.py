from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from .config import PASTA_APP
from .escopo import TIPO_MUNICIPIO, TIPO_UF, Escopo
from .store import FonteDados, br, moeda, pct

PASTA_LOCAIS = PASTA_APP / "figuras"

DPI = 180

ESTILO = {
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.grid": True,
    "grid.color": "#e5e7eb",
    "grid.linestyle": "-",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.size": 11,
}


LIMITE_BARRAS = 80
POR_PAGINA = 26


def _rotulo_escopo(escopo: Escopo) -> str:
    return escopo.titulo


def planejar_escopo(
    fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int | None
) -> list[Path]:
    """Caminhos de PNG que o escopo deveria produzir (sem gerar nada)."""
    base = PASTA_LOCAIS / f"{ano}_{escopo.tipo}_{escopo.codigo}"
    ordem: list[Path] = [Path(f"{base}_cargos.png")]
    if cargo_cd is not None:
        try:
            total_cand = len(fonte.candidatos(escopo, ano, cargo_cd))
        except Exception:  # noqa: BLE001
            total_cand = POR_PAGINA
        paginas = -(-total_cand // POR_PAGINA) if total_cand else 0
        for pagina in range(1, paginas + 1):
            ordem.append(Path(f"{base}_candidatos_{cargo_cd}_p{pagina}.png"))
        if escopo.tipo == TIPO_UF:
            ordem.append(Path(f"{base}_municipios_{cargo_cd}.png"))
        if escopo.tipo == TIPO_MUNICIPIO:
            ordem.append(Path(f"{base}_zonas_{cargo_cd}.png"))
            ordem.append(Path(f"{base}_secoes_{cargo_cd}.png"))
    if ano == 2024 and escopo.tipo in (TIPO_UF, TIPO_MUNICIPIO):
        ordem.append(Path(f"{base}_eleitores.png"))
    return ordem


def listar_escopo(
    fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int | None
) -> tuple[list[Path], list[Path]]:
    """(PNGs já gerados, PNGs ainda faltantes) — sem renderizar nada."""
    PASTA_LOCAIS.mkdir(parents=True, exist_ok=True)
    planejado = planejar_escopo(fonte, escopo, ano, cargo_cd)
    existentes = [caminho for caminho in planejado if caminho.exists()]
    faltantes = [caminho for caminho in planejado if not caminho.exists()]
    return existentes, faltantes


def gerar_escopo(
    fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int | None
) -> list[Path]:
    """Gráficos do escopo corrente — país, região, UF ou município (cacheados).

    Candidatos são paginados (POR_PAGINA barras por página) para manter a
    legibilidade; cada página é um PNG próprio.
    """
    PASTA_LOCAIS.mkdir(parents=True, exist_ok=True)
    base = PASTA_LOCAIS / f"{ano}_{escopo.tipo}_{escopo.codigo}"
    ordem = planejar_escopo(fonte, escopo, ano, cargo_cd)
    paginas_candidatos = 0
    if cargo_cd is not None:
        try:
            total_cand = len(fonte.candidatos(escopo, ano, cargo_cd))
            paginas_candidatos = (
                max(1, -(-max(total_cand, 1) // POR_PAGINA)) if total_cand else 0
            )
        except Exception:  # noqa: BLE001
            paginas_candidatos = 1
    with plt.rc_context(ESTILO):
        if not ordem[0].exists():
            _figura_cargos(fonte, escopo, ano, ordem[0])
        for pagina in range(1, paginas_candidatos + 1):
            alvo = Path(f"{base}_candidatos_{cargo_cd}_p{pagina}.png")
            if not alvo.exists():
                _figura_candidatos_cargo(
                    fonte, escopo, ano, cargo_cd, alvo, pagina
                )
        if cargo_cd is not None and escopo.tipo == TIPO_UF:
            alvo = Path(f"{base}_municipios_{cargo_cd}.png")
            if not alvo.exists():
                _figura_top_municipios(fonte, escopo, ano, cargo_cd, alvo)
        if cargo_cd is not None and escopo.tipo == TIPO_MUNICIPIO:
            alvo = Path(f"{base}_zonas_{cargo_cd}.png")
            if not alvo.exists():
                _figura_zonas(fonte, escopo, ano, cargo_cd, alvo)
            alvo = Path(f"{base}_secoes_{cargo_cd}.png")
            if not alvo.exists():
                _figura_secoes(fonte, escopo, ano, cargo_cd, alvo)
        if ano == 2024 and escopo.tipo in (TIPO_UF, TIPO_MUNICIPIO):
            alvo = Path(f"{base}_eleitores.png")
            if not alvo.exists():
                _figura_eleitores(fonte, escopo, alvo)
    return [caminho for caminho in ordem if caminho.exists()]


gerar_locais = gerar_escopo  # compatibilidade


def _figura_secoes(
    fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int, destino: Path
) -> None:
    """Top 20 seções eleitorais por votos totais (dados de seção, 2024/2026)."""
    secoes = fonte.totais_secoes_municipio(escopo, ano, cargo_cd)
    if secoes.empty:
        return
    topo = secoes.head(20).iloc[::-1]
    rotulos = [
        f"Z {int(r.NR_ZONA)} / S {int(r.NR_SECAO)}" for r in topo.itertuples()
    ]
    valores = [int(v) for v in topo["votos"]]
    fig, eixo = plt.subplots(figsize=(13, max(4.0, 0.4 * len(rotulos) + 2.0)))
    barras = eixo.barh(rotulos, valores, color="#2ca02c")
    eixo.bar_label(barras, labels=[br(v) for v in valores], padding=4, fontsize=10)
    eixo.set_xlim(0, max(valores) * 1.22)
    eixo.set_title(
        f"{_rotulo_escopo(escopo)} — {ano} — {fonte.nome_cargo(cargo_cd)} — "
        "maiores seções eleitorais por votos (todos os candidatos)",
        fontsize=14,
        fontweight="bold",
        loc="left",
    )
    eixo.set_xlabel("votos na seção (turno decisivo)", fontsize=11)
    fig.tight_layout()
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)


def _figura_top_municipios(
    fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int, destino: Path
) -> None:
    """Top 20 municípios da UF por votos nominais no cargo."""
    votos = fonte.votos(ano)
    sub = votos[
        (votos["cargo_cd"] == cargo_cd) & fonte.mascara(votos, escopo)
    ]
    if sub.empty:
        return
    serie = (
        sub.groupby(["municipio_cd", "municipio"], observed=True)["votos"]
        .sum()
        .sort_values(ascending=False)
        .head(20)
        .iloc[::-1]
    )
    rotulos = [str(nome) for _, nome in serie.index]
    valores = [int(v) for v in serie.values]
    fig, eixo = plt.subplots(figsize=(13, max(4.5, 0.42 * len(rotulos) + 2.2)))
    barras = eixo.barh(rotulos, valores, color="#ff7f0e")
    eixo.bar_label(barras, labels=[br(v) for v in valores], padding=4, fontsize=9)
    eixo.set_xlim(0, max(valores) * 1.25)
    eixo.set_title(
        f"{_rotulo_escopo(escopo)} — {ano} — {fonte.nome_cargo(cargo_cd)} — "
        "top 20 municípios por votos nominais",
        fontsize=14,
        fontweight="bold",
        loc="left",
    )
    eixo.set_xlabel("votos nominais (turno decisivo)", fontsize=11)
    fig.tight_layout()
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)


def _figura_cargos(fonte: FonteDados, escopo: Escopo, ano: int, destino: Path) -> None:
    linhas = [
        (fonte.nome_cargo(cargo), fonte.total_votos(escopo, ano, cargo))
        for cargo in fonte.cargos(ano)
    ]
    linhas = [(nome, valor) for nome, valor in linhas if valor]
    if not linhas:
        return
    linhas.sort(key=lambda linha: linha[1])
    nomes, valores = zip(*linhas)
    fig, eixo = plt.subplots(figsize=(13, max(3.6, 0.85 * len(nomes) + 2.0)))
    barras = eixo.barh(nomes, valores, color="#d62728")
    eixo.bar_label(barras, labels=[br(v) for v in valores], padding=4, fontsize=11)
    eixo.set_xlim(0, max(valores) * 1.2)
    eixo.tick_params(labelsize=12)
    eixo.set_title(
        f"{escopo.titulo} — {ano} — votos nominais por cargo",
        fontsize=16,
        fontweight="bold",
        loc="left",
    )
    eixo.set_xlabel("votos nominais (turno decisivo)", fontsize=12)
    fig.tight_layout()
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)


def _marcas_eleicao(
    fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int
) -> tuple[set[str], set[str]]:
    """(nomes de eleitos, nomes de líderes de 1º turno com 2º turno pendente)."""
    eleitos: set[str] = set()
    pendentes: set[str] = set()
    try:
        quadro = fonte.eleitos(escopo, ano, cargo_cd)
    except Exception:  # noqa: BLE001
        return eleitos, pendentes
    if quadro.empty:
        return eleitos, pendentes
    for registro in quadro.itertuples():
        nome = str(registro.candidato)
        if "aguarda" in str(registro.eleito_em) or "2º turno" in str(
            registro.situacao
        ):
            pendentes.add(nome)
        else:
            eleitos.add(nome)
    return eleitos, pendentes


def _figura_candidatos_cargo(
    fonte: FonteDados,
    escopo: Escopo,
    ano: int,
    cargo_cd: int,
    destino: Path,
    pagina: int = 1,
) -> None:
    """Candidatos do cargo no escopo, paginados (POR_PAGINA barras por página)."""
    candidatos = fonte.candidatos(escopo, ano, cargo_cd)
    if candidatos.empty:
        return
    eleitos, pendentes = _marcas_eleicao(fonte, escopo, ano, cargo_cd)
    total_candidatos = len(candidatos)
    visiveis = min(total_candidatos, LIMITE_BARRAS)
    inicio = (pagina - 1) * POR_PAGINA
    pedaco = candidatos.iloc[inicio : inicio + POR_PAGINA].iloc[::-1]
    if pedaco.empty:
        return

    def _marca(nome: str, situacao) -> str:
        if nome in eleitos or str(situacao).upper().strip().startswith("ELEITO"):
            return " ★"
        if nome in pendentes:
            return " ◇"
        return ""

    rotulos = [
        f"{r['candidato_urna']} ({r['partido']})"
        + _marca(str(r["candidato_urna"]), r.get("situacao", ""))
        for _, r in pedaco.iterrows()
    ]
    valores = list(pedaco["votos"])
    pct_col = list(pedaco["pct"])
    altura = max(4.2, 0.52 * len(rotulos) + 2.4)
    fig, eixo = plt.subplots(figsize=(14, altura))
    barras = eixo.barh(rotulos, valores, color="#1f77b4")
    eixo.bar_label(
        barras,
        labels=[f"{br(v)} ({pct(p)})" for v, p in zip(valores, pct_col)],
        padding=4,
        fontsize=10,
    )
    eixo.set_xlim(0, max(valores) * 1.3)
    eixo.tick_params(axis="y", labelsize=11)
    paginas = max(1, -(-visiveis // POR_PAGINA))
    legenda = []
    if eleitos:
        legenda.append("★ = eleito")
    if pendentes:
        legenda.append("◇ = líder do 1º turno (2º turno pendente)")
    cabecalho = (
        f"{escopo.titulo} — {ano} — {fonte.nome_cargo(cargo_cd)} — "
        f"{total_candidatos} candidatos com votos — página {pagina}/{paginas}"
        + (f" — {' · '.join(legenda)}" if legenda else "")
    )
    if total_candidatos > LIMITE_BARRAS:
        cabecalho += f"\nmostrando os {LIMITE_BARRAS} primeiros; a tabela do app tem a lista completa"
    eixo.set_title(cabecalho, fontsize=13, fontweight="bold", loc="left")
    eixo.set_xlabel("votos nominais no escopo (turno decisivo)", fontsize=11)
    fig.tight_layout()
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)


def _figura_eleitores(fonte: FonteDados, escopo: Escopo, destino: Path) -> None:
    cruz = fonte.cruzamento()
    if cruz.empty:
        return
    if escopo.tipo == TIPO_UF:
        linha = cruz[cruz["uf"].astype(str) == escopo.codigo]
        if linha.empty:
            return
        agregado = {
            "eleitores": float(linha["eleitores"].sum()),
            "comparecimento": float(linha["comparecimento"].sum()),
            "populacao": float(linha["populacao"].sum()),
        }
        agregado["pct_comparecimento"] = (
            agregado["comparecimento"] / agregado["eleitores"] * 100
            if agregado["eleitores"]
            else 0.0
        )
        agregado["pct_eleitores_populacao"] = (
            agregado["eleitores"] / agregado["populacao"] * 100
            if agregado["populacao"]
            else 0.0
        )
        linha = pd.Series(agregado)
    else:
        linha = cruz[cruz["municipio_cd"] == int(escopo.codigo)]
        if linha.empty:
            return
        linha = linha.iloc[0]
    fig, eixo = plt.subplots(figsize=(13, 6.0))
    categorias = ["Eleitores aptos", "Comparecimento", "População (Censo 2022)"]
    valores = [float(linha["eleitores"]), float(linha["comparecimento"]), float(linha["populacao"])]
    barras = eixo.bar(categorias, valores, color=["#1f77b4", "#2ca02c", "#ff7f0e"], width=0.55)
    eixo.bar_label(barras, labels=[br(v) for v in valores], padding=3, fontsize=10)
    eixo.set_ylim(0, max(valores) * 1.2)
    eixo.set_title(
        f"{escopo.titulo} — eleitorado × população (TSE × IBGE Censo 2022)",
        fontsize=13,
        fontweight="bold",
        loc="left",
    )
    eixo.set_ylabel("pessoas")
    resumo = (
        f"Comparecimento: {pct(linha['pct_comparecimento'])} · "
        f"Eleitores / população: {pct(linha['pct_eleitores_populacao'])}"
    )
    if "renda_media" in linha and pd.notna(linha.get("renda_media")):
        resumo += (
            f"\nRenda per capita média: {moeda(linha['renda_media'])} "
            f"(mediana {moeda(linha['renda_mediana'])}) · faixa: {linha['renda_faixa']}"
        )
    if pd.notna(linha.get("pib_per_capita")):
        resumo += f" · PIB per capita (IBGE 2022): {moeda(linha['pib_per_capita'])}"
    if isinstance(linha.get("vencedor"), str) and linha["vencedor"] and linha["vencedor"] != "nan":
        if bool(linha.get("segundo_turno")):
            resumo += (
                f"\n1º turno: {linha['vencedor']} liderou com {br(linha['vencedor_votos'])} "
                f"votos ({pct(linha['vencedor_pct'])}) · houve 2º turno"
            )
        else:
            resumo += (
                f"\nPrefeito 2024: {linha['vencedor']} — {br(linha['vencedor_votos'])} votos "
                f"({pct(linha['vencedor_pct'])}) · margem {pct(linha['margem_pct'])}"
            )
    eixo.text(
        0.0,
        -0.18,
        resumo,
        transform=eixo.transAxes,
        fontsize=10,
        va="top",
        color="#333333",
    )
    fig.tight_layout()
    fig.savefig(destino, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def _figura_zonas(
    fonte: FonteDados,
    escopo: Escopo,
    ano: int,
    cargo_cd: int | None,
    destino: Path,
) -> None:
    quadro = fonte.zonas_municipio(escopo, ano)
    if quadro.empty:
        return
    cargos_disponiveis = sorted(int(c) for c in quadro["CD_CARGO"].dropna().unique())
    cargo = cargo_cd if cargo_cd in cargos_disponiveis else None
    if cargo is None:
        totais = (
            quadro.groupby("CD_CARGO", observed=True)["QT_VOTOS_NOMINAIS"]
            .sum()
            .sort_values(ascending=False)
        )
        cargo = int(totais.index[0]) if not totais.empty else None
    if cargo is None:
        return
    do_cargo = quadro[quadro["CD_CARGO"] == cargo]
    totais = (
        do_cargo.groupby("NR_ZONA", observed=True)["QT_VOTOS_NOMINAIS"]
        .sum()
        .sort_values(ascending=False)
    )
    if totais.empty:
        return
    rotulos = [f"Zona {int(z)}" for z in totais.index]
    valores = [int(v) for v in totais.values]
    fig, eixo = plt.subplots(figsize=(13, max(3.8, 0.42 * len(rotulos) + 2.0)))
    barras = eixo.barh(rotulos[::-1], valores[::-1], color="#9467bd")
    eixo.bar_label(barras, labels=[br(v) for v in valores[::-1]], padding=4, fontsize=10)
    eixo.set_xlim(0, max(valores) * 1.22)
    eixo.tick_params(labelsize=11)
    eixo.set_title(
        f"{escopo.titulo} — {ano} — votos nominais por zona eleitoral "
        f"({fonte.nome_cargo(cargo)})",
        fontsize=15,
        fontweight="bold",
        loc="left",
    )
    eixo.set_xlabel("votos nominais na zona (turno decisivo)", fontsize=11)
    fig.tight_layout()
    fig.savefig(destino, dpi=DPI)
    plt.close(fig)
