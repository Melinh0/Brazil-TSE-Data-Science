from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.patches import Patch

from .analysis import candidatos_eleitos, candidatos_por_uf, resultado_por_candidato
from .config import PASTA_FIGURAS, ROTULOS_CARGO
from .http import log

sns.set_theme(style="whitegrid", palette="tab10")
FIGURA = (12, 7)
DPI = 150

CORES_CARGO = {
    1: "#e41a1c",
    3: "#377eb8",
    5: "#4daf4a",
    6: "#984ea3",
    7: "#02818a",
    11: "#ff7f00",
    13: "#1f78b4",
}


def _br(valor: float, casas: int = 0) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _votos_br(valor: float) -> str:
    if valor >= 1e6:
        return f"{_br(valor / 1e6, 1)} mi"
    if valor >= 1e3:
        return f"{_br(valor / 1e3, 0)} mil"
    return _br(valor)


def _eixo_votos(eixo, rotulo: str) -> None:
    eixo.set_xlabel(rotulo)

    def rotulo_milhoes(valor: float, _pos: int) -> str:
        if valor == 0:
            return "0"
        texto = f"{valor / 1e6:.6f}".rstrip("0").rstrip(".").replace(".", ",")
        return f"{texto} mi"

    eixo.xaxis.set_major_formatter(rotulo_milhoes)
    eixo.xaxis.offsetText.set_visible(False)


def _salvar(fig, nome: str, rect: tuple[float, float, float, float] | None = None) -> Path:
    PASTA_FIGURAS.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_FIGURAS / nome
    if rect:
        fig.tight_layout(rect=rect)
    else:
        fig.tight_layout()
    fig.savefig(caminho, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    log(f"  [figura] {caminho.name}")
    return caminho


def _titulo(eixo, titulo: str, subtitulo: str | None = None) -> None:
    eixo.set_title(titulo, fontsize=14, fontweight="bold", loc="left", pad=26)
    if subtitulo:
        eixo.text(0.0, 1.015, subtitulo, transform=eixo.transAxes, fontsize=10, color="#444444")


def _pct(valor: float, casas: int = 1) -> str:
    return f"{_br(valor, casas)}%"


def _pct_auto(valor: float) -> str:
    return _pct(valor, 2) if 0 < abs(valor) < 1 else _pct(valor)


def _altura(n: int, por_item: float = 0.34, base: float = 7.0) -> float:
    return max(base, por_item * n)


def _sigla_chave(sigla: pd.Series) -> pd.Series:
    return sigla.astype(str).str.replace(r"\s+", "", regex=True).str.upper()


def _partidos_agregados(dados: pd.DataFrame) -> pd.DataFrame:
    """Votos por sigla, unindo variantes de escrita da mesma sigla (ex.: 'PC do B' e 'PCDOB')."""
    quadro = dados[["partido", "votos"]].copy()
    quadro["chave"] = _sigla_chave(quadro["partido"])
    nomes = quadro.sort_values("votos", ascending=False).drop_duplicates("chave")[["chave", "partido"]]
    agregado = quadro.groupby("chave", observed=True, dropna=False)["votos"].sum().reset_index()
    return agregado.merge(nomes, on="chave")[["partido", "votos"]]


def grafico_partidos_prefeitura(votos: pd.DataFrame) -> Path | None:
    dados = votos[(votos["cargo_cd"] == 11) & (votos["turno"] == 1)]
    if dados.empty:
        return None
    agregado = _partidos_agregados(dados).sort_values("votos", ascending=False).iloc[::-1]
    total = dados["votos"].sum()

    fig, eixo = plt.subplots(figsize=(12, _altura(len(agregado))))
    barras = eixo.barh(agregado["partido"], agregado["votos"], color=sns.color_palette("Blues_r", len(agregado)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct_auto(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais para prefeito")
    eixo.set_ylabel("Partido")
    _titulo(
        eixo,
        "Eleições 2024 — Partidos na disputa pela prefeitura",
        "Todos os partidos por votos nominais (1º turno)",
    )
    eixo.set_xlim(0, agregado["votos"].max() * 1.25)
    return _salvar(fig, "2024_prefeitura_partidos.png")


def grafico_partidos_veradores(votos: pd.DataFrame) -> Path | None:
    dados = votos[votos["cargo_cd"] == 13]
    if dados.empty:
        return None
    agregado = _partidos_agregados(dados).sort_values("votos", ascending=False).iloc[::-1]
    total = dados["votos"].sum()

    fig, eixo = plt.subplots(figsize=(12, _altura(len(agregado))))
    barras = eixo.barh(agregado["partido"], agregado["votos"], color=sns.color_palette("Oranges_r", len(agregado)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct_auto(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais para vereador")
    eixo.set_ylabel("Partido")
    _titulo(
        eixo,
        "Eleições 2024 — Partidos na disputa por vereador",
        "Todos os partidos, todos os municípios (votos nominais)",
    )
    eixo.set_xlim(0, agregado["votos"].max() * 1.25)
    return _salvar(fig, "2024_veradores_partidos.png")


def grafico_prefeitos_eleitos(votos: pd.DataFrame) -> Path | None:
    eleitos = candidatos_eleitos(votos, 11)
    if eleitos.empty:
        return None
    agregado = eleitos.groupby("partido", observed=True)["municipio"].nunique().reset_index(name="municipios")
    agregado = agregado.sort_values("municipios", ascending=False).iloc[::-1]

    fig, eixo = plt.subplots(figsize=(12, _altura(len(agregado))))
    barras = eixo.barh(agregado["partido"], agregado["municipios"], color=sns.color_palette("Greens_r", len(agregado)))
    eixo.bar_label(barras, labels=[f" {_br(v)} municípios" for v in agregado["municipios"]], padding=4, fontsize=9)
    eixo.set_xlabel("Municípios vencidos")
    eixo.set_ylabel("Partido")
    _titulo(
        eixo,
        "Eleições 2024 — Prefeitos eleitos por partido",
        "Todos os partidos com candidato à prefeitura em situação \"Eleito\" (inclui vencedores de 2º turno)",
    )
    eixo.set_xlim(0, agregado["municipios"].max() * 1.3)
    return _salvar(fig, "2024_prefeitos_eleitos_por_partido.png")


def grafico_comparecimento(apuracao: pd.DataFrame, ano: int) -> Path | None:
    if apuracao.empty:
        return None
    dados = apuracao.sort_values("pct_comparecimento", ascending=True)

    fig, eixo = plt.subplots(figsize=(12, 10))
    posicoes = np.arange(len(dados))
    eixo.barh(posicoes, dados["pct_comparecimento"], color="#2b8cbe", label="Comparecimento (%)")
    eixo.barh(
        posicoes,
        dados["pct_abstencao"],
        left=dados["pct_comparecimento"],
        color="#f0f0f0",
        edgecolor="#bbbbbb",
        label="Abstenção (%)",
    )
    eixo.set_yticks(posicoes, dados["uf"])
    for indice, valor in enumerate(dados["pct_comparecimento"]):
        eixo.text(valor - 1.5, indice, _pct(valor), va="center", ha="right", fontsize=8, color="white")
    eixo.set_xlabel("% do eleitorado")
    eixo.set_xlim(0, 100)
    _titulo(
        eixo,
        f"Eleições {ano} — Comparecimento x abstenção por estado",
        "Percentual do eleitorado apto que compareceu às urnas",
    )
    eixo.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=2, frameon=False)
    return _salvar(fig, f"{ano}_comparecimento_por_uf.png")


def grafico_genero(candidatos: pd.DataFrame, ano: int) -> Path | None:
    if candidatos.empty:
        return None
    dados = candidatos[candidatos["genero"].notna()].copy()
    dados["genero"] = dados["genero"].str.upper()
    contagem = (
        dados.groupby(["cargo_cd", "genero"], observed=True).size().unstack(fill_value=0).reindex(columns=["FEMININO", "MASCULINO"], fill_value=0)
    )
    contagem = contagem.loc[contagem.sum(axis=1).sort_values(ascending=False).index]
    contagem.index = [ROTULOS_CARGO.get(str(int(indice)), str(indice)) for indice in contagem.index]

    fig, eixo = plt.subplots(figsize=FIGURA)
    contagem.plot(kind="barh", stacked=True, ax=eixo, color=["#d7301f", "#4575b4"], width=0.75)
    for posicao, linha in enumerate(contagem.iterrows()):
        total = linha[1].sum()
        feminino = 100.0 * linha[1].get("FEMININO", 0) / total if total else 0
        eixo.text(total * 1.01, posicao, f"{_pct(feminino)} feminino", va="center", fontsize=9, color="#333333")
    eixo.set_xlabel("Candidaturas registradas")
    eixo.set_ylabel("Cargo")
    eixo.legend(["Feminino", "Masculino"], title="Gênero", loc="upper right")
    _titulo(
        eixo,
        f"Eleições {ano} — Candidaturas por gênero e cargo",
        "Somente cargos principais (presidente, governador, senador, deputados, prefeito e vereador)",
    )
    eixo.set_xlim(0, contagem.values.max() * 1.25)
    return _salvar(fig, f"{ano}_candidatos_por_genero.png")


def grafico_idade(candidatos: pd.DataFrame, ano: int) -> Path | None:
    if candidatos.empty or "idade" not in candidatos:
        return None
    cargos_alvo = (11, 13) if ano == 2024 else (1, 3, 6)
    dados = candidatos[candidatos["cargo_cd"].isin(cargos_alvo) & candidatos["idade"].notna()]
    if dados.empty:
        return None

    fig, eixo = plt.subplots(figsize=FIGURA)
    for cargo in cargos_alvo:
        sub = dados[dados["cargo_cd"] == cargo]["idade"]
        if sub.empty:
            continue
        pesos = np.full(len(sub), 100.0 / len(sub))
        eixo.hist(
            sub,
            bins=np.arange(18, 82, 2),
            weights=pesos,
            histtype="stepfilled",
            alpha=0.5,
            label=ROTULOS_CARGO.get(str(int(cargo)), str(cargo)),
            color=CORES_CARGO.get(int(cargo), "#999999"),
            edgecolor=CORES_CARGO.get(int(cargo), "#999999"),
            linewidth=1.2,
        )
    eixo.axvline(dados["idade"].median(), color="#333333", linestyle="--", linewidth=1.5)
    eixo.text(dados["idade"].median() + 0.6, eixo.get_ylim()[1] * 0.95, f"mediana {dados['idade'].median():.0f} anos", fontsize=9)
    eixo.set_xlabel("Idade na data da eleição")
    eixo.set_ylabel("% das candidaturas do cargo")
    eixo.legend(title="Cargo")
    _titulo(
        eixo,
        f"Eleições {ano} — Distribuição de idade das candidaturas",
        "Percentual de candidaturas de cada cargo em cada faixa de idade (cor fixa por cargo)",
    )
    return _salvar(fig, f"{ano}_idade_candidatos.png")


def grafico_concentracao(votos: pd.DataFrame) -> Path | None:
    dados = votos[votos["cargo_cd"] == 13]
    if dados.empty:
        return None
    por_candidato = dados.groupby(["uf", "municipio", "candidato_urna"], observed=True)["votos"].sum().reset_index()
    por_candidato = por_candidato[por_candidato["votos"] > 0]
    if por_candidato.empty:
        return None
    por_candidato = por_candidato.sort_values(["uf", "municipio", "votos"], ascending=[True, True, False])
    totais = por_candidato.groupby(["uf", "municipio"], observed=True)["votos"].transform("sum")
    por_candidato["acumulado"] = por_candidato.groupby(["uf", "municipio"], observed=True)["votos"].cumsum() / totais
    por_candidato["posicao"] = por_candidato.groupby(["uf", "municipio"], observed=True).cumcount() + 1
    candidatos_por_municipio = por_candidato.groupby(["uf", "municipio"], observed=True).size()

    cotas = [(1, "O mais votado"), (3, "Top 3"), (5, "Top 5"), (10, "Top 10"), (20, "Top 20")]
    medias = [100 * por_candidato[por_candidato["posicao"] == topo]["acumulado"].mean() for topo, _ in cotas]
    pares = [(rotulo, media) for (_, rotulo), media in zip(cotas, medias) if not np.isnan(media)]
    if not pares:
        return None
    pares.sort(key=lambda par: par[1])
    rotulos = [par[0] for par in pares]
    valores = [par[1] for par in pares]

    fig, eixo = plt.subplots(figsize=FIGURA)
    barras = eixo.barh(rotulos, valores, color=sns.color_palette("Blues_r", len(valores)))
    eixo.bar_label(barras, labels=[_pct(v) for v in valores], padding=4, fontsize=10)
    eixo.set_xlabel("% médio dos votos a vereador do município")
    eixo.set_xlim(0, max(valores) * 1.18)
    _titulo(
        eixo,
        "Eleições 2024 — Concentração dos votos na disputa por vereador",
        f"Quanto cada grupo de candidatos mais votados leva do total de votos do município "
        f"(média de {len(candidatos_por_municipio):,} municípios, "
        f"{candidatos_por_municipio.mean():.0f} candidatos com voto por município)",
    )
    return _salvar(fig, "2024_concentracao_votos.png")


def grafico_presidente(votos: pd.DataFrame) -> Path | None:
    agregado = resultado_por_candidato(votos, 1)
    if agregado.empty:
        return None
    agregado = agregado[agregado["votos"] > 0].sort_values("votos", ascending=True).tail(12)

    fig, eixo = plt.subplots(figsize=FIGURA)
    rotulos = [f"{candidato} ({partido})" for candidato, partido in zip(agregado["candidato_urna"], agregado["partido"])]
    barras = eixo.barh(rotulos, agregado["votos"], color=sns.color_palette("Reds_r", len(agregado)))
    total = agregado["votos"].sum()
    eixo.bar_label(
        barras,
        labels=[f" {_br(v / 1e6, 2)} mi ({_pct(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais (soma dos municípios)")
    _titulo(
        eixo,
        "Eleições 2026 — Resultado da presidência no 1º turno",
        "Agregação de todos os municípios a partir dos arquivos oficiais de votação",
    )
    eixo.set_xlim(0, agregado["votos"].max() * 1.3)
    return _salvar(fig, "2026_presidente_resultado.png")


def grafico_presidente_por_uf(votos: pd.DataFrame) -> Path | None:
    dados = votos[(votos["cargo_cd"] == 1) & (votos["uf"].astype(str).str.upper() != "ZZ")]
    if dados.empty:
        return None
    agregado = dados.groupby(["uf", "candidato_urna"], observed=True)[["votos"]].sum().reset_index()
    totais = agregado.groupby("uf", observed=True)["votos"].sum().rename("total")
    agregado = agregado.join(totais, on="uf")
    agregado["pct"] = 100.0 * agregado["votos"] / agregado["total"]

    ordem_nacional = agregado.groupby("candidato_urna", observed=True)["votos"].sum().sort_values(ascending=False).index
    matriz = agregado.pivot_table(index="uf", columns="candidato_urna", values="pct", aggfunc="sum", fill_value=0.0)
    matriz = matriz[[c for c in ordem_nacional if c in matriz.columns]]
    matriz = matriz.sort_values(matriz.columns[0], ascending=False)

    largura = max(13.0, 1.0 * len(matriz.columns) + 5)
    tamanho_annot = 8 if len(matriz.columns) <= 8 else 6
    fig, eixo = plt.subplots(figsize=(largura, 15))
    sns.heatmap(
        matriz,
        annot=matriz.map(lambda valor: _pct(valor) if pd.notna(valor) else ""),
        fmt="",
        cmap="YlOrRd",
        linewidths=0.4,
        cbar_kws={"label": "% dos votos nominais na UF"},
        ax=eixo,
        annot_kws={"size": tamanho_annot},
    )
    eixo.set_yticklabels(matriz.index, fontsize=10, rotation=0)
    eixo.tick_params(axis="y", length=0)
    eixo.set_xlabel("")
    eixo.set_ylabel("Estado")
    _titulo(
        eixo,
        "Eleições 2026 — Votos na presidência por estado",
        "Percentual de todos os candidatos, ordenados pelos votos nacionais",
    )
    return _salvar(fig, "2026_presidente_por_uf.png")


def grafico_governadores(votos: pd.DataFrame) -> Path | None:
    candidatos = candidatos_por_uf(votos, 3)
    if candidatos.empty:
        return None
    situacao = candidatos["situacao"].astype(str).str.upper().str.strip()
    eleito = situacao.str.startswith("ELEITO")
    segundo = situacao.str.contains("TURNO")
    candidatos = candidatos.copy()
    candidatos["eleito"] = eleito
    candidatos["segundo"] = segundo
    dados = candidatos[eleito | segundo]
    if dados.empty:
        return None
    dados = dados.sort_values(["uf", "posicao"]).iloc[::-1]

    cores = []
    for _, linha in dados.iterrows():
        if linha["eleito"]:
            cores.append("#1a9850")
        elif linha["posicao"] == 1:
            cores.append("#fdae61")
        else:
            cores.append("#e6550d")

    fig, eixo = plt.subplots(figsize=(12, _altura(len(dados), por_item=0.42, base=9)))
    rotulos = [f"{uf} — {candidato} ({partido})" for uf, candidato, partido in zip(dados["uf"], dados["candidato_urna"], dados["partido"])]
    barras = eixo.barh(rotulos, dados["pct"], color=cores)
    eixo.bar_label(barras, labels=[f" {_pct(v)}" for v in dados["pct"]], padding=4, fontsize=8)
    eixo.axvline(50, color="#333333", linestyle="--", linewidth=1.2)
    eixo.set_xlabel("% dos votos nominais da UF")
    eixo.set_xlim(0, max(60, dados["pct"].max() * 1.15))
    eixo.legend(
        handles=[
            Patch(facecolor="#1a9850", label="Eleito no 1º turno"),
            Patch(facecolor="#fdae61", label="Líder (2º turno em 25/10)"),
            Patch(facecolor="#e6550d", label="Adversário (2º turno em 25/10)"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=3,
        frameon=False,
    )
    pendentes = sorted(set(dados[~dados["eleito"]]["uf"]))
    _titulo(
        eixo,
        "Eleições 2026 — Disputa de governador por estado",
        f"Situação segundo o TSE: {len(set(dados[dados['eleito']]['uf']))} eleitos no 1º turno; "
        + (f"2º turno em {len(pendentes)} estados ({', '.join(pendentes)})" if pendentes else "sem 2º turno"),
    )
    return _salvar(fig, "2026_governador_liderancas.png")


def grafico_deputados_partidos(votos: pd.DataFrame) -> Path | None:
    dados = votos[votos["cargo_cd"] == 6]
    if dados.empty:
        return None
    agregado = _partidos_agregados(dados).sort_values("votos", ascending=False).iloc[::-1]
    total = dados["votos"].sum()

    fig, eixo = plt.subplots(figsize=(12, _altura(len(agregado))))
    barras = eixo.barh(agregado["partido"], agregado["votos"], color=sns.color_palette("Purples_r", len(agregado)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct_auto(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais para deputado federal")
    eixo.set_ylabel("Partido")
    _titulo(eixo, "Eleições 2026 — Votos em deputado federal por partido", "Todos os partidos, todos os estados")
    eixo.set_xlim(0, agregado["votos"].max() * 1.3)
    return _salvar(fig, "2026_deputados_federais_partidos.png")


def grafico_deputados_estaduais_partidos(votos: pd.DataFrame) -> Path | None:
    dados = votos[votos["cargo_cd"].isin([7, 8])]
    if dados.empty:
        return None
    agregado = _partidos_agregados(dados).sort_values("votos", ascending=False).iloc[::-1]
    total = dados["votos"].sum()

    fig, eixo = plt.subplots(figsize=(12, _altura(len(agregado))))
    barras = eixo.barh(agregado["partido"], agregado["votos"], color=sns.color_palette("YlGnBu_r", len(agregado)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct_auto(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais para deputado estadual e distrital")
    eixo.set_ylabel("Partido")
    _titulo(
        eixo,
        "Eleições 2026 — Votos em deputado estadual por partido",
        "Todos os partidos, todos os estados (inclui os 24 deputados distritais do DF)",
    )
    eixo.set_xlim(0, agregado["votos"].max() * 1.3)
    return _salvar(fig, "2026_deputados_estaduais_partidos.png")


def grafico_senadores_partidos(votos: pd.DataFrame) -> Path | None:
    dados = votos[votos["cargo_cd"] == 5]
    if dados.empty:
        return None
    agregado = _partidos_agregados(dados).sort_values("votos", ascending=False).iloc[::-1]
    total = dados["votos"].sum()

    fig, eixo = plt.subplots(figsize=(12, _altura(len(agregado))))
    barras = eixo.barh(agregado["partido"], agregado["votos"], color=sns.color_palette("Reds_r", len(agregado)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct_auto(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais para senador")
    eixo.set_ylabel("Partido")
    _titulo(eixo, "Eleições 2026 — Votos em senador por partido", "Todos os partidos, todos os estados (votos nominais)")
    eixo.set_xlim(0, agregado["votos"].max() * 1.3)
    return _salvar(fig, "2026_senadores_partidos.png")


def grafico_eleitos_painel(
    eleitos: pd.DataFrame,
    votos: pd.DataFrame,
    cargos: tuple[int, ...],
    titulo: str,
    nome: str,
    cargo_cd: int,
) -> Path | None:
    if eleitos is None or eleitos.empty:
        return None
    dados = eleitos[eleitos["cargo_cd"].isin(cargos)].copy()
    if dados.empty:
        return None
    cor = CORES_CARGO.get(cargo_cd, "#1f78b4")
    paleta = CORES_CADEIRAS.get(cargo_cd, "Blues_r")
    total_votos = float(dados["votos"].sum()) or 1.0
    geral = float(votos[votos["cargo_cd"].isin(cargos)]["votos"].sum()) if votos is not None and not votos.empty else 0.0
    base = geral if geral > 0 else total_votos

    fig, eixos = plt.subplots(2, 3, figsize=(19, 11))

    eixo = eixos[0][0]
    partidos = _partidos_agregados(dados).sort_values("votos", ascending=False).iloc[::-1]
    barras = eixo.barh(partidos["partido"], partidos["votos"], color=sns.color_palette(paleta, len(partidos)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct_auto(100 * v / base)})" for v in partidos["votos"]],
        padding=3,
        fontsize=8,
    )
    eixo.set_xlim(0, partidos["votos"].max() * 1.45)
    eixo.set_title(f"Votos por partido ({_votos_br(total_votos)} aos eleitos)", loc="left", fontsize=11, fontweight="bold")
    _eixo_votos(eixo, "Votos nominais · % sobre o total do cargo")

    eixo = eixos[0][1]
    top = dados.nlargest(15, "votos").iloc[::-1]
    rotulos = [f"{nome_c} ({uf}) — {part}" for nome_c, uf, part in zip(top["candidato_urna"], top["uf"], top["partido"])]
    barras = eixo.barh(rotulos, top["votos"], color=cor)
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct_auto(100 * v / base)})" for v in top["votos"]],
        padding=3,
        fontsize=8,
    )
    eixo.set_xlim(0, top["votos"].max() * 1.4)
    eixo.set_title("Top 15 mais votados", loc="left", fontsize=11, fontweight="bold")
    _eixo_votos(eixo, "Votos nominais")
    for texto in eixo.get_yticklabels():
        texto.set_fontsize(8)

    eixo = eixos[0][2]
    genero = (
        dados["genero"].astype(str).str.upper().str.strip().value_counts().reindex(["FEMININO", "MASCULINO"], fill_value=0)
    )
    barras = eixo.bar(genero.index, genero.values, color=[cor, "#9ecae1"], width=0.55)
    eixo.bar_label(barras, labels=[f" {_br(v)} ({_pct(100 * v / len(dados))})" for v in genero.values], fontsize=10)
    eixo.set_ylim(0, max(genero.values) * 1.2)
    eixo.set_ylabel("Eleitos")
    eixo.set_title("Gênero", loc="left", fontsize=11, fontweight="bold")

    eixo = eixos[1][0]
    idade = pd.to_numeric(dados["idade"], errors="coerce").dropna()
    if not idade.empty:
        eixo.hist(idade, bins=np.arange(20, 96, 5), color=cor, edgecolor="white")
        mediana, media = idade.median(), idade.mean()
        eixo.axvline(mediana, color="#333333", linestyle="--", linewidth=1.2)
        eixo.set_title(
            f"Idade — mediana {_br(mediana)} anos · média {_br(media, 1)}",
            loc="left",
            fontsize=11,
            fontweight="bold",
        )
    else:
        eixo.set_title("Idade", loc="left", fontsize=11, fontweight="bold")
    eixo.set_xlabel("Idade (anos)")
    eixo.set_ylabel("Eleitos")

    eixo = eixos[1][1]
    raca = dados["raca"].astype(str).str.upper().str.strip().value_counts().iloc[::-1]
    barras = eixo.barh(raca.index, raca.values, color=cor)
    eixo.bar_label(barras, labels=[f" {_br(v)} ({_pct(100 * v / len(dados))})" for v in raca.values], padding=3, fontsize=9)
    eixo.set_xlim(0, raca.max() * 1.35)
    eixo.set_title("Raça / cor", loc="left", fontsize=11, fontweight="bold")
    eixo.set_xlabel("Eleitos")

    eixo = eixos[1][2]
    escolaridade = dados["escolaridade"].astype(str).str.strip().value_counts().iloc[::-1]
    barras = eixo.barh(escolaridade.index, escolaridade.values, color=cor)
    eixo.bar_label(
        barras,
        labels=[f" {_br(v)} ({_pct(100 * v / len(dados))})" for v in escolaridade.values],
        padding=3,
        fontsize=9,
    )
    eixo.set_xlim(0, escolaridade.max() * 1.35)
    eixo.set_title("Escolaridade", loc="left", fontsize=11, fontweight="bold")
    eixo.set_xlabel("Eleitos")

    fig.suptitle(
        f"Eleições 2026 — {titulo}: {_br(len(dados))} eleitos",
        x=0.01,
        y=0.985,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    fig.text(
        0.01,
        0.955,
        f"Fonte: TSE (votação oficial e cadastro de candidatos) · percentuais dos votos sobre {_votos_br(base)} votos do cargo"
        + (f" · inclui os 24 deputados distritais do DF" if 8 in cargos else ""),
        fontsize=10,
        color="#444444",
    )
    return _salvar(fig, nome, rect=(0, 0, 1, 0.94))


def grafico_senado_composicao(senado: pd.DataFrame) -> Path | None:
    if senado is None or senado.empty:
        return None
    quadro = senado.copy()
    quadro["chave"] = _sigla_chave(quadro["partido"])
    nomes = quadro.groupby("chave")["partido"].agg(lambda s: s.value_counts().idxmax())
    contas = quadro.groupby(["chave", "classe"], observed=True).size().unstack(fill_value=0)
    contas = contas.reindex(columns=[2022, 2026], fill_value=0)
    contas["total"] = contas.sum(axis=1)
    contas = contas.sort_values("total").reset_index()
    contas["partido"] = contas["chave"].map(nomes)

    fig, eixo = plt.subplots(figsize=(12, max(7.0, 0.42 * len(contas) + 3.5)))
    barras26 = eixo.barh(contas["partido"], contas[2026], color="#2166ac", label="Classe 2026-2034 (eleitos em 2026)")
    barras22 = eixo.barh(
        contas["partido"],
        contas[2022],
        left=contas[2026],
        color="#92c5de",
        label="Classe 2022-2030 (meio mandato)",
    )
    eixo.bar_label(barras26, labels=[str(int(v)) if v else "" for v in contas[2026]], label_type="center", fontsize=8, color="white", fontweight="bold")
    eixo.bar_label(barras22, labels=[str(int(v)) if v else "" for v in contas[2022]], label_type="center", fontsize=8, color="#08306b", fontweight="bold")
    eixo.bar_label(barras22, labels=[f" {_br(int(v))}" for v in contas["total"]], padding=3, fontsize=9, fontweight="bold")
    eixo.set_xlim(0, contas["total"].max() * 1.15)
    eixo.set_xlabel("Cadeiras")
    eixo.legend(loc="lower right", frameon=False)
    _titulo(
        eixo,
        f"Senado Federal — Composição das {_br(int(contas['total'].sum()))} cadeiras após as eleições de 2026",
        "54 cadeiras da classe 2026-2034 (2 por estado) + 27 da classe 2022-2030 em meio mandato · partido da última eleição",
    )
    return _salvar(fig, "2026_senado_composicao.png")


CORES_CADEIRAS = {11: "Blues_r", 13: "Oranges_r", 3: "Greens_r", 5: "Reds_r", 6: "Purples_r", 7: "YlGnBu_r"}


def _cadeiras_por_partido(votos: pd.DataFrame, cargo_cd: int | tuple[int, ...]) -> pd.DataFrame:
    alvos = (cargo_cd,) if isinstance(cargo_cd, int) else tuple(cargo_cd)
    situacao = votos["situacao"].astype(str).str.upper().str.strip()
    dados = votos[votos["cargo_cd"].isin(alvos) & situacao.str.startswith("ELEITO")]
    if dados.empty or "candidato_sq" not in dados:
        return pd.DataFrame()
    cadeiras = (
        dados.groupby("partido", observed=True, dropna=False)["candidato_sq"].nunique().reset_index(name="cadeiras")
    )
    return cadeiras.sort_values("cadeiras", ascending=False).reset_index(drop=True)


def _nota_cadeiras(votos: pd.DataFrame, cargo_cd: int) -> str | None:
    if cargo_cd == 7:
        return "inclui os 24 deputados distritais do DF"
    if cargo_cd != 3:
        return None
    situacao = votos["situacao"].astype(str).str.upper().str.strip()
    pendentes = sorted(set(votos[(votos["cargo_cd"] == 3) & situacao.str.contains("TURNO")]["uf"].unique()))
    if not pendentes:
        return None
    return f"líderes eleitos no 1º turno; 2º turno pendente em {len(pendentes)} estados ({', '.join(pendentes)})"


def grafico_cadeiras(votos: pd.DataFrame, ano: int) -> Path | None:
    if votos.empty:
        return None
    cargos = (11, 13) if ano == 2024 else (3, 5, 6, 7)
    paineis = []
    for cargo in cargos:
        quadro = _cadeiras_por_partido(votos, (7, 8) if cargo == 7 else cargo)
        if not quadro.empty:
            paineis.append((cargo, quadro))
    if not paineis:
        return None

    fig, eixos = plt.subplots(
        len(paineis),
        1,
        figsize=(13, sum(max(4.0, 0.34 * len(q) + 2.2) for _, q in paineis) + 1.5),
        squeeze=False,
    )
    for eixo, (cargo, quadro) in zip([linha[0] for linha in eixos], paineis):
        total = int(quadro["cadeiras"].sum())
        dados = quadro.iloc[::-1]
        barras = eixo.barh(
            dados["partido"],
            dados["cadeiras"],
            color=sns.color_palette(CORES_CADEIRAS.get(cargo, "Blues_r"), len(dados)),
        )
        eixo.bar_label(
            barras,
            labels=[f" {_br(int(v))} ({_pct_auto(100 * v / total)})" for v in dados["cadeiras"]],
            padding=3,
            fontsize=8,
        )
        nota = _nota_cadeiras(votos, cargo)
        titulo = f"{ROTULOS_CARGO.get(str(cargo), str(cargo))} — {_br(total)} cadeiras"
        eixo.set_title(f"{titulo} ({nota})" if nota else titulo, fontsize=12, fontweight="bold", loc="left", pad=8)
        eixo.set_xlabel("Cadeiras (titulares eleitos)")
        eixo.set_xlim(0, dados["cadeiras"].max() * 1.28)
    fig.suptitle(
        f"Eleições {ano} — Divisão das cadeiras por partido",
        x=0.01,
        ha="left",
        fontsize=15,
        fontweight="bold",
    )
    return _salvar(fig, f"{ano}_cadeiras_por_partido.png", rect=(0, 0, 1, 0.965))


def gerar_graficos(pacotes: dict[int, dict[str, pd.DataFrame]]) -> list[Path]:
    gerados: list[Path] = []
    for ano, pacote in pacotes.items():
        log(f"[figuras {ano}]")
        votos = pacote.get("votos", pd.DataFrame())
        candidatos = pacote.get("candidatos", pd.DataFrame())
        apuracao = pacote.get("apuracao", pd.DataFrame())
        eleitos = pacote.get("eleitos", pd.DataFrame())
        senado = pacote.get("senado", pd.DataFrame())

        funcoes = []
        if ano == 2024:
            funcoes = [
                lambda: grafico_partidos_prefeitura(votos),
                lambda: grafico_partidos_veradores(votos),
                lambda: grafico_prefeitos_eleitos(votos),
                lambda: grafico_comparecimento(apuracao, ano),
                lambda: grafico_genero(candidatos, ano),
                lambda: grafico_idade(candidatos, ano),
                lambda: grafico_concentracao(votos),
                lambda: grafico_cadeiras(votos, ano),
            ]
        elif ano == 2026:
            funcoes = [
                lambda: grafico_presidente(votos),
                lambda: grafico_presidente_por_uf(votos),
                lambda: grafico_governadores(votos),
                lambda: grafico_comparecimento(apuracao, ano),
                lambda: grafico_deputados_partidos(votos),
                lambda: grafico_deputados_estaduais_partidos(votos),
                lambda: grafico_senadores_partidos(votos),
                lambda: grafico_cadeiras(votos, ano),
                lambda: grafico_genero(candidatos, ano),
                lambda: grafico_eleitos_painel(eleitos, votos, (5,), "Senador", "2026_senadores_eleitos.png", 5),
                lambda: grafico_eleitos_painel(eleitos, votos, (6,), "Deputado Federal", "2026_dep_federais_eleitos.png", 6),
                lambda: grafico_eleitos_painel(
                    eleitos, votos, (7, 8), "Deputado Estadual e Distrital", "2026_dep_estaduais_eleitos.png", 7
                ),
                lambda: grafico_senado_composicao(senado),
            ]
        for funcao in funcoes:
            try:
                caminho = funcao()
            except Exception as erro:
                log(f"  [erro] grafico falhou: {erro}")
                caminho = None
            if caminho is not None:
                gerados.append(caminho)
    return gerados
