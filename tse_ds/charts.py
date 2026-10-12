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


def _rotulo_milhoes(valor: float, _pos: int) -> str:
    if valor == 0:
        return "0"
    texto = f"{valor / 1e6:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{texto} mi"


def _eixo_milhoes(eixo, rotulo: str) -> None:
    eixo.set_xlabel(rotulo)
    eixo.xaxis.set_major_formatter(_rotulo_milhoes)
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
    ano: int = 2026,
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
        f"Eleições {ano} — {titulo}: {_br(len(dados))} eleitos",
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


from .analysis import FAIXAS_COMPARTILHADAS


def grafico_prefeitos_mais_votados(mais_votados: pd.DataFrame) -> Path | None:
    """Top 20 prefeitos mais votados nacionalmente."""
    dados = mais_votados[
        (mais_votados["cargo_cd"] == 11)
        & (mais_votados["escopo"] == "nacional")
    ].sort_values("posicao")
    if dados.empty:
        return None
    dados = dados.iloc[::-1]
    rotulos = [f"{nome_c} ({uf}) — {part}" for nome_c, uf, part in zip(dados["candidato_urna"], dados["uf"], dados["partido"])]
    fig, eixo = plt.subplots(figsize=(13, _altura(len(dados), por_item=0.42)))
    barras = eixo.barh(rotulos, dados["votos"], color=sns.color_palette("Blues_r", len(dados)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct(p)})" for v, p in zip(dados["votos"], dados["pct"])],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlim(0, dados["votos"].max() * 1.28)
    _eixo_votos(eixo, "Votos nominais (soma dos turnos)")
    _titulo(
        eixo,
        "Eleições 2024 — Top 20 prefeitos mais votados",
        "Ranking nacional por votos recebidos (1º e 2º turnos somados) · % dos votos nominais a prefeito no país",
    )
    return _salvar(fig, "2024_prefeitos_mais_votados.png")


def grafico_vereadores_mais_votados(mais_votados: pd.DataFrame) -> Path | None:
    """Top 20 vereadores mais votados nacionalmente."""
    dados = mais_votados[
        (mais_votados["cargo_cd"] == 13)
        & (mais_votados["escopo"] == "nacional")
    ].sort_values("posicao")
    if dados.empty:
        return None
    dados = dados.iloc[::-1]
    rotulos = [f"{nome_c} ({uf}) — {part}" for nome_c, uf, part in zip(dados["candidato_urna"], dados["uf"], dados["partido"])]
    fig, eixo = plt.subplots(figsize=(13, _altura(len(dados), por_item=0.42)))
    barras = eixo.barh(rotulos, dados["votos"], color=sns.color_palette("Oranges_r", len(dados)))
    eixo.bar_label(
        barras,
        labels=[f" {_votos_br(v)} ({_pct(p)})" for v, p in zip(dados["votos"], dados["pct"])],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlim(0, dados["votos"].max() * 1.28)
    _eixo_votos(eixo, "Votos nominais")
    _titulo(
        eixo,
        "Eleições 2024 — Top 20 vereadores mais votados",
        "Ranking nacional por votos nominais · % dos votos nominais a vereador no país",
    )
    return _salvar(fig, "2024_vereadores_mais_votados.png")


def _painel_top_por_uf(
    mais_votados: pd.DataFrame,
    cargo_cd: int,
    cor: str,
    titulo: str,
    nome: str,
) -> Path | None:
    """Top 10 candidatos mais votados por UF em painel 9x3."""
    dados = mais_votados[
        (mais_votados["cargo_cd"] == cargo_cd)
        & (mais_votados["escopo"] == "uf")
    ].sort_values(["uf", "posicao"])
    if dados.empty:
        return None
    fig, eixos = plt.subplots(9, 3, figsize=(19, 24), squeeze=False)
    eixos_planos = [ax for row in eixos for ax in row]
    ufs = sorted(dados["uf"].unique())
    for indice, uf in enumerate(ufs):
        eixo = eixos_planos[indice]
        sub = dados[dados["uf"] == uf].iloc[::-1]
        if sub.empty:
            eixo.set_visible(False)
            continue
        rotulos = [f"{nome_c} — {part}" for nome_c, part in zip(sub["candidato_urna"], sub["partido"])]
        barras = eixo.barh(rotulos, sub["votos"], color=cor)
        eixo.bar_label(
            barras,
            labels=[f" {_votos_br(v)} ({_pct(p)})" for v, p in zip(sub["votos"], sub["pct"])],
            padding=3,
            fontsize=8,
        )
        eixo.set_xlim(0, sub["votos"].max() * 1.32)
        eixo.set_title(f"{uf} — Top 10", fontsize=11, fontweight="bold", loc="left")
        _eixo_votos(eixo, "Votos")
        for texto in eixo.get_yticklabels():
            texto.set_fontsize(8)
    for eixo in eixos_planos[len(ufs):]:
        eixo.set_visible(False)
    fig.suptitle(
        titulo,
        fontsize=16,
        fontweight="bold",
        x=0.01,
        y=0.995,
        ha="left",
    )
    fig.text(
        0.01,
        0.975,
        "Top 10 por estado · rótulo com % dos votos nominais da UF no cargo",
        fontsize=11,
        color="#444444",
    )
    return _salvar(fig, nome, rect=(0, 0, 1, 0.965))


def grafico_top_por_uf_prefeitos(mais_votados: pd.DataFrame) -> Path | None:
    """Top 10 prefeitos mais votados por UF."""
    return _painel_top_por_uf(
        mais_votados,
        cargo_cd=11,
        cor=CORES_CARGO.get(11, "#ff7f00"),
        titulo="Eleições 2024 — Prefeitos mais votados por estado",
        nome="2024_top_por_uf_prefeitos.png",
    )


def grafico_top_por_uf_vereadores(mais_votados: pd.DataFrame) -> Path | None:
    """Top 10 vereadores mais votados por UF."""
    return _painel_top_por_uf(
        mais_votados,
        cargo_cd=13,
        cor=CORES_CARGO.get(13, "#1f78b4"),
        titulo="Eleições 2024 — Vereadores mais votados por estado",
        nome="2024_top_por_uf_vereadores.png",
    )


def grafico_eleitorado_faixa_etaria(eleitorado: pd.DataFrame) -> Path | None:
    """Distribuição do eleitorado por faixa etária (nacional)."""
    faixas = eleitorado[eleitorado["dimensao"] == "faixa_etaria"].copy()
    if faixas.empty:
        return None
    ordem = list(FAIXAS_COMPARTILHADAS)
    mapa = {tse: bin for bin, itens in FAIXAS_COMPARTILHADAS.items() for tse in itens}
    faixas["faixa"] = faixas["categoria"].map(mapa)
    faixas = faixas[faixas["faixa"].notna()].groupby("faixa", observed=True)["eleitores"].sum().reindex(ordem).fillna(0).astype(int)
    total = faixas.sum()
    fig, eixo = plt.subplots(figsize=FIGURA)
    barras = eixo.barh(faixas.index[::-1], faixas.values[::-1], color=sns.color_palette("Blues_r", len(faixas)))
    eixo.bar_label(barras, labels=[f" {_votos_br(v)} ({_pct(100 * v / total)})" for v in faixas.values[::-1]], padding=4, fontsize=10)
    _eixo_milhoes(eixo, "Eleitores")
    _titulo(
        eixo,
        "Eleições 2024 — Perfil etário do eleitorado",
        f"Distribuição nacional dos {_br(total)} eleitores aptos por faixa etária",
    )
    return _salvar(fig, "2024_eleitorado_faixa_etaria.png")


def grafico_eleitorado_grau_instrucao(eleitorado: pd.DataFrame) -> Path | None:
    """Distribuição do eleitorado por grau de instrução (nacional)."""
    esc = eleitorado[eleitorado["dimensao"] == "grau_escolaridade"].copy()
    if esc.empty:
        return None
    ordem = [
        "ANALFABETO",
        "LÊ E ESCREVE",
        "ENSINO FUNDAMENTAL INCOMPLETO",
        "ENSINO FUNDAMENTAL COMPLETO",
        "ENSINO MÉDIO INCOMPLETO",
        "ENSINO MÉDIO COMPLETO",
        "SUPERIOR INCOMPLETO",
        "SUPERIOR COMPLETO",
    ]
    esc = esc[esc["categoria"].isin(ordem)].groupby("categoria", observed=True)["eleitores"].sum().reindex(ordem).fillna(0).astype(int)
    total = esc.sum()
    fig, eixo = plt.subplots(figsize=FIGURA)
    barras = eixo.barh(esc.index[::-1], esc.values[::-1], color=sns.color_palette("Greens_r", len(esc)))
    eixo.bar_label(barras, labels=[f" {_votos_br(v)} ({_pct(100 * v / total)})" for v in esc.values[::-1]], padding=4, fontsize=10)
    _eixo_milhoes(eixo, "Eleitores")
    _titulo(
        eixo,
        "Eleições 2024 — Perfil educacional do eleitorado",
        f"Distribuição nacional dos {_br(total)} eleitores aptos por grau de instrução",
    )
    return _salvar(fig, "2024_eleitorado_grau_instrucao.png")


DIMENSOES_ELEITORADO = (
    ("genero", "Gênero", ("FEMININO", "MASCULINO")),
    ("raca", "Raça / cor declarada", ("Branca", "Parda", "Preta", "Amarela", "Indígena")),
    ("estado_civil", "Estado civil", ("SOLTEIRO", "CASADO", "VIÚVO", "DIVORCIADO", "SEPARADO")),
    ("identidade_genero", "Identidade de gênero*", ("Cisgênero", "Transgênero", "Prefere não informar")),
)


def grafico_eleitorado_por_uf(eleitorado: pd.DataFrame) -> Path | None:
    """Painel 2x2 de heatmaps: perfil do eleitorado por UF (gênero, raça, estado civil, identidade)."""
    if eleitorado.empty:
        return None
    fig, eixos = plt.subplots(2, 2, figsize=(16, 13))
    total_genero = eleitorado[eleitorado["dimensao"] == "genero"]["eleitores"].sum()
    total_identidade = eleitorado[eleitorado["dimensao"] == "identidade_genero"]["eleitores"].sum()
    for eixo, (dimensao, titulo, ordem) in zip([ax for linha in eixos for ax in linha], DIMENSOES_ELEITORADO):
        sub = eleitorado[eleitorado["dimensao"] == dimensao].copy()
        if sub.empty:
            eixo.set_visible(False)
            continue
        total_uf = sub.groupby("uf", observed=True)["eleitores"].sum()
        sub["pct"] = 100.0 * sub["eleitores"] / sub["uf"].map(total_uf)
        sub["categoria"] = sub["categoria"].replace({"SEPARADO JUDICIALMENTE": "SEPARADO"})
        matriz = sub.pivot_table(index="uf", columns="categoria", values="pct", fill_value=0.0)
        colunas = [c for c in ordem if c in matriz.columns]
        matriz = matriz[colunas].sort_index()
        sns.heatmap(
            matriz,
            annot=True,
            fmt=".1f",
            cmap="YlGnBu",
            linewidths=0.4,
            cbar_kws={"label": "% dos eleitores da UF", "shrink": 0.85},
            ax=eixo,
            annot_kws={"size": 9},
        )
        eixo.set_title(titulo, fontsize=12, fontweight="bold", loc="left")
        eixo.set_xlabel("")
        eixo.set_ylabel("")
        eixo.tick_params(axis="x", labelrotation=0, labelsize=9, length=0)
        eixo.tick_params(axis="y", labelrotation=0, labelsize=8, length=0)
        for texto in eixo.get_xticklabels():
            texto.set_ha("center")
    fig.suptitle(
        "Eleições 2024 — Perfil do eleitorado por UF",
        x=0.01,
        y=0.985,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    cobertura = 100.0 * total_identidade / total_genero if total_genero else 0.0
    fig.text(
        0.01,
        0.95,
        "Percentual de eleitores de cada categoria dentro do estado · "
        f"* identidade de gênero auto-declarada por apenas {_pct(cobertura)} do eleitorado",
        fontsize=11,
        color="#444444",
    )
    return _salvar(fig, "2024_eleitorado_por_uf.png", rect=(0, 0, 1, 0.935))


def grafico_eleitores_vs_populacao(idade_ibge: pd.DataFrame) -> Path | None:
    """Taxa de eleitores sobre população 16+ (TSE x IBGE) por UF."""
    if idade_ibge.empty:
        return None
    dados = idade_ibge[idade_ibge["uf"] != "BR"].copy()
    total_eleitores = dados.groupby("uf", observed=True)["eleitores"].sum()
    total_pop = dados.groupby("uf", observed=True)["populacao"].sum()
    taxa = (100.0 * total_eleitores / total_pop.replace(0, pd.NA)).round(2).sort_values()
    fig, eixo = plt.subplots(figsize=(10, 10))
    barras = eixo.barh(taxa.index, taxa.values, color="#2b8cbe")
    eixo.bar_label(barras, labels=[f" {_pct(v)}" for v in taxa.values], padding=4, fontsize=9)
    eixo.axvline(100, color="#333333", linestyle="--", linewidth=1)
    eixo.set_xlabel("Eleitores (% da população 16+ pelo Censo 2022)")
    _titulo(eixo, "Eleições 2024 — Eleitores vs população 16+ por estado", "Taxa de aptos sobre população residente 16+ (Censo 2022) · >100% indica defasagem do censo ou eleitores falecidos não purgados")
    return _salvar(fig, "2024_eleitores_vs_populacao.png")


def grafico_renda_vs_comparecimento(cruzamento: pd.DataFrame) -> Path | None:
    """Renda per capita vs comparecimento municipal (scatter + tendência)."""
    if cruzamento.empty or "renda_media" not in cruzamento.columns:
        return None
    dados = cruzamento[cruzamento["renda_media"].notna() & cruzamento["pct_comparecimento"].notna()].copy()
    if len(dados) < 100:
        return None
    fig, eixo = plt.subplots(figsize=(12, 8))
    scatter = eixo.scatter(
        dados["renda_media"],
        dados["pct_comparecimento"],
        s=dados["eleitores"] / 1000,
        alpha=0.4,
        c=dados["pct_eleitores_populacao"],
        cmap="viridis",
    )
    plt.colorbar(scatter, ax=eixo, label="Eleitores (% da população 16+)")
    coef = np.polyfit(dados["renda_media"], dados["pct_comparecimento"], 1)
    x_ord = np.linspace(dados["renda_media"].min(), dados["renda_media"].max(), 100)
    eixo.plot(x_ord, np.polyval(coef, x_ord), color="#d7301f", linewidth=2, label="Tendência linear")
    correlacao = dados["renda_media"].corr(dados["pct_comparecimento"])
    eixo.legend(loc="upper right", frameon=True, framealpha=0.9)
    eixo.set_xlabel("Renda per capita média (R$ — Censo 2022)")
    eixo.set_ylabel("Comparecimento (%)")
    _titulo(
        eixo,
        "Eleições 2024 — Renda municipal vs comparecimento",
        f"Cada ponto = município ({len(dados):,}) · tamanho proporcional aos eleitores · "
        f"cor = eleitores/população · Pearson r = {correlacao:+.2f}",
    )
    return _salvar(fig, "2024_renda_vs_comparecimento.png")


def grafico_renda_faixas_municipios(cruzamento: pd.DataFrame) -> Path | None:
    """Distribuição de municípios por faixa de renda com comparecimento médio ponderado."""
    if cruzamento.empty or "renda_faixa" not in cruzamento.columns:
        return None
    dados = cruzamento[cruzamento["renda_faixa"] != "nan"].copy()
    if dados.empty:
        return None
    ordem = ["até R$ 500", "R$ 500 a 1.000", "R$ 1.000 a 2.000", "R$ 2.000 a 4.000", "acima de R$ 4.000"]
    agg = (
        dados.groupby("renda_faixa", observed=True)
        .agg(municipios=("municipio", "count"), eleitores=("eleitores", "sum"), comparecimento=("comparecimento", "sum"))
        .reindex([f for f in ordem if f in dados["renda_faixa"].unique()])
        .dropna(subset=["municipios"])
    )
    agg["comparecimento_medio"] = 100.0 * agg["comparecimento"] / agg["eleitores"].replace(0, pd.NA)
    fig, eixo = plt.subplots(figsize=(12, 6))
    barras = eixo.barh(agg.index[::-1], agg["municipios"][::-1], color=sns.color_palette("Reds_r", len(agg)))
    eixo.bar_label(
        barras,
        labels=[
            f" {int(v)} município{'s' if v != 1 else ''} · comparecimento médio {_pct(agg.loc[idx, 'comparecimento_medio'])}"
            for idx, v in agg["municipios"][::-1].items()
        ],
        padding=4,
        fontsize=10,
    )
    eixo.set_xlim(0, agg["municipios"].max() * 1.35)
    eixo.set_xlabel("Municípios")
    _titulo(
        eixo,
        "Eleições 2024 — Municípios por faixa de renda per capita",
        "Comparecimento médio ponderado pelos eleitores · Censo 2022 (renda) × apuração TSE (comparecimento)",
    )
    return _salvar(fig, "2024_renda_faixas_municipios.png")


def grafico_segundo_turno_prefeitos(segundo_turno: pd.DataFrame) -> Path | None:
    """Todas as disputas de 2º turno para prefeito, com votos de cada candidato."""
    if segundo_turno.empty:
        return None
    dados = segundo_turno[segundo_turno["cargo_cd"] == 11].copy()
    if dados.empty:
        return None
    ordem = (
        dados.groupby(["uf", "municipio"], observed=True)["total_municipio"]
        .first()
        .sort_values(ascending=False)
        .index
    )
    posicoes: list[float] = []
    valores: list[float] = []
    rotulos: list[str] = []
    etiquetas: list[str] = []
    cores: list[str] = []
    posicao = 0.0
    for uf, municipio in ordem:
        sub = dados[(dados["uf"] == uf) & (dados["municipio"] == municipio)].sort_values(
            "votos", ascending=False
        )
        for _, linha in sub.iterrows():
            posicoes.append(posicao)
            valores.append(linha["votos"])
            rotulos.append(f"{linha['candidato_urna']} ({linha['partido']}) — {municipio}/{uf}")
            cores.append("#1a9850" if linha["eleito"] else "#f46d43")
            if linha["eleito"]:
                etiquetas.append(
                    f" {_votos_br(linha['votos'])} ({_pct(linha['pct'])} · vitória de {_pct(linha['margem_pct'])})"
                )
            else:
                etiquetas.append(f" {_votos_br(linha['votos'])} ({_pct(linha['pct'])})")
            posicao += 1
        posicao += 0.7
    fig, eixo = plt.subplots(figsize=(15, _altura(len(posicoes), por_item=0.28, base=10)))
    barras = eixo.barh(posicoes, valores, color=cores)
    eixo.bar_label(barras, labels=etiquetas, padding=3, fontsize=8)
    eixo.set_yticks(posicoes, rotulos, fontsize=8)
    eixo.invert_yaxis()
    eixo.set_xlim(0, max(valores) * 1.28)
    _eixo_votos(eixo, "Votos nominais no 2º turno")
    eixo.legend(
        handles=[
            Patch(facecolor="#1a9850", label="Vencedor"),
            Patch(facecolor="#f46d43", label="Derrotado"),
        ],
        loc="lower right",
        frameon=False,
    )
    eixo.set_title(
        "Eleições 2024 — 2º turno da prefeitura: votos de cada candidato",
        fontsize=14,
        fontweight="bold",
        loc="left",
        pad=44,
    )
    eixo.text(
        0.0,
        1.012,
        f"{len(ordem)} municípios com segunda fase · ordem por total de votos da disputa · "
        "margem = diferença em pontos percentuais sobre os votos válidos do turno",
        transform=eixo.transAxes,
        fontsize=10,
        color="#444444",
    )
    return _salvar(fig, "2024_segundo_turno_prefeitos.png")


def grafico_segundo_turno_margens(segundo_turno: pd.DataFrame) -> Path | None:
    """Margem de vitória e distribuição por UF das disputas de 2º turno."""
    if segundo_turno.empty:
        return None
    vencedores = segundo_turno[(segundo_turno["cargo_cd"] == 11) & (segundo_turno["posicao"] == 1)].copy()
    if vencedores.empty:
        return None
    fig, (eixo_hist, eixo_uf) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [1.4, 1]})

    margens = vencedores["margem_pct"].dropna()
    eixo_hist.hist(margens, bins=12, color="#2b8cbe", edgecolor="white", linewidth=1.2)
    mediana = margens.median()
    eixo_hist.axvline(mediana, color="#333333", linestyle="--", linewidth=1.4)
    eixo_hist.text(
        mediana,
        eixo_hist.get_ylim()[1] * 0.92,
        f" mediana {_pct(mediana)}",
        fontsize=10,
        color="#333333",
    )
    eixo_hist.set_xlabel("Margem de vitória (pontos percentuais)")
    eixo_hist.set_ylabel("Municípios")
    eixo_hist.set_title("Distribuição das margens", loc="left", fontsize=12, fontweight="bold")

    por_uf = vencedores.groupby("uf", observed=True).size().sort_values()
    barras = eixo_uf.barh(por_uf.index, por_uf.values, color="#fd8d3c")
    eixo_uf.bar_label(barras, labels=[f" {_br(int(v))}" for v in por_uf.values], padding=3, fontsize=9)
    eixo_uf.set_xlabel("Municípios com 2º turno")
    eixo_uf.set_xlim(0, por_uf.max() * 1.2)
    eixo_uf.set_title("Disputas por estado", loc="left", fontsize=12, fontweight="bold")

    fig.suptitle(
        "Eleições 2024 — 2º turno da prefeitura: margens de vitória",
        x=0.01,
        y=0.99,
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
    fig.text(
        0.01,
        0.94,
        f"{len(vencedores)} disputas de 2º turno em outubro de 2024 · "
        f"margem média {_pct(margens.mean())} · disputa mais apertada {_pct(margens.min())}",
        fontsize=11,
        color="#444444",
    )
    return _salvar(fig, "2024_segundo_turno_margens.png", rect=(0, 0, 1, 0.91))


FAIXAS_RENDA_GRAFICO = ["até R$ 500", "R$ 500 a 1.000", "R$ 1.000 a 2.000", "R$ 2.000 a 4.000", "acima de R$ 4.000"]


def grafico_renda_vs_vencedor(cruzamento: pd.DataFrame) -> Path | None:
    """Renda municipal vs concentração de votos do vencedor (último turno)."""
    if cruzamento.empty or "vencedor_pct" not in cruzamento.columns:
        return None
    dados = cruzamento[cruzamento["vencedor_pct"].notna() & cruzamento["renda_media"].notna()].copy()
    if len(dados) < 100:
        return None
    fig, eixo = plt.subplots(figsize=(12, 8))
    for situacao, cor, rotulo in (
        (False, "#4daf4a", "Decidido no 1º turno"),
        (True, "#e41a1c", "Foi a 2º turno"),
    ):
        sub = dados[dados["segundo_turno"] == situacao]
        eixo.scatter(sub["renda_media"], sub["vencedor_pct"], s=12, alpha=0.5, color=cor, label=rotulo)
    coef = np.polyfit(dados["renda_media"], dados["vencedor_pct"], 1)
    x_ord = np.linspace(dados["renda_media"].min(), dados["renda_media"].max(), 100)
    eixo.plot(x_ord, np.polyval(coef, x_ord), color="#333333", linewidth=2, linestyle="--", label="Tendência linear")
    correlacao = dados["renda_media"].corr(dados["vencedor_pct"])
    eixo.legend(loc="lower left", frameon=True, framealpha=0.9)
    eixo.set_xlabel("Renda per capita média (R$ — Censo 2022)")
    eixo.set_ylabel("% dos votos do vencedor (último turno)")
    _titulo(
        eixo,
        "Eleições 2024 — Renda municipal vs concentração de votos no vencedor",
        f"Cada ponto = município ({len(dados):,}) · quanto mais alto, mais dominante foi o vencedor · "
        f"Pearson r = {correlacao:+.2f}",
    )
    return _salvar(fig, "2024_renda_vs_vencedor.png")


def grafico_candidatos_por_renda(cruzamento: pd.DataFrame) -> Path | None:
    """Candidatos a prefeito por município e frequência de 2º turno, por faixa de renda."""
    if cruzamento.empty or "candidatos_prefeito" not in cruzamento.columns:
        return None
    dados = cruzamento[cruzamento["candidatos_prefeito"].notna() & (cruzamento["renda_faixa"] != "nan")].copy()
    if dados.empty:
        return None
    faixas = [f for f in FAIXAS_RENDA_GRAFICO if f in set(dados["renda_faixa"])]
    agg = dados.groupby("renda_faixa", observed=True).agg(
        candidatos=("candidatos_prefeito", "mean"),
        municipios=("municipio", "count"),
        pct_2t=("segundo_turno", lambda s: 100.0 * s.mean()),
    ).reindex(faixas)
    posicoes = np.arange(len(agg))
    fig, eixo = plt.subplots(figsize=(12, 6))
    barras = eixo.barh(posicoes, agg["candidatos"], color=sns.color_palette("Blues_r", len(agg)))
    eixo.bar_label(
        barras,
        labels=[
            f" {v:.1f} candidatos · {int(m)} município{'s' if int(m) != 1 else ''}"
            for v, m in zip(agg["candidatos"], agg["municipios"])
        ],
        padding=4,
        fontsize=10,
    )
    eixo.set_yticks(posicoes, agg.index)
    eixo.invert_yaxis()
    eixo.set_xlim(0, agg["candidatos"].max() * 1.35)
    eixo.set_xlabel("Candidatos a prefeito por município (média)")
    eixo2 = eixo.twinx()
    eixo2.plot(agg["pct_2t"], posicoes, marker="o", color="#d7301f", linewidth=2, label="% em 2º turno")
    for y, valor in zip(posicoes, agg["pct_2t"]):
        eixo2.annotate(f" {_pct(valor)}", (valor, y), va="center", fontsize=9, color="#d7301f")
    eixo2.set_xlim(0, max(agg["pct_2t"].max() * 1.3, 5))
    eixo2.set_xlabel("% dos municípios que foram a 2º turno")
    eixo2.legend(loc="lower right", frameon=False)
    _titulo(
        eixo,
        "Eleições 2024 — Competição municipal por faixa de renda",
        "Barras: média de candidatos a prefeito · linha: % dos municípios da faixa que tiveram 2º turno",
    )
    return _salvar(fig, "2024_candidatos_por_renda.png")


def grafico_votos_invalidos_renda(cruzamento: pd.DataFrame) -> Path | None:
    """Votos válidos, brancos e nulos por faixa de renda municipal."""
    if cruzamento.empty or "pct_invalidos" not in cruzamento.columns:
        return None
    dados = cruzamento[cruzamento["pct_invalidos"].notna() & (cruzamento["renda_faixa"] != "nan")].copy()
    if dados.empty:
        return None
    faixas = [f for f in FAIXAS_RENDA_GRAFICO if f in set(dados["renda_faixa"])]
    agg = dados.groupby("renda_faixa", observed=True)[["votos_validos", "votos_brancos", "votos_nulos"]].sum().reindex(faixas)
    total = agg.sum(axis=1)
    pct_validos = 100.0 * agg["votos_validos"] / total
    pct_brancos = 100.0 * agg["votos_brancos"] / total
    pct_nulos = 100.0 * agg["votos_nulos"] / total
    posicoes = np.arange(len(agg))
    fig, eixo = plt.subplots(figsize=(12, 6))
    b1 = eixo.barh(posicoes, pct_validos, color="#2ca25f", label="Votos válidos")
    b2 = eixo.barh(posicoes, pct_brancos, left=pct_validos, color="#f0f0f0", edgecolor="#bbbbbb", label="Em branco")
    b3 = eixo.barh(posicoes, pct_nulos, left=pct_validos + pct_brancos, color="#de2d26", label="Nulos")
    eixo.bar_label(b1, labels=[_pct(v) for v in pct_validos], label_type="center", fontsize=9, color="white", fontweight="bold")
    eixo.bar_label(b2, labels=[_pct(v) if v > 2.0 else "" for v in pct_brancos], label_type="center", fontsize=8, color="#444444")
    eixo.bar_label(b3, labels=[_pct(v) if v > 2.0 else "" for v in pct_nulos], label_type="center", fontsize=9, color="white", fontweight="bold")
    eixo.set_yticks(posicoes, agg.index)
    eixo.invert_yaxis()
    eixo.set_xlim(0, 100)
    eixo.set_xlabel("% dos votos registrados na eleição municipal")
    eixo.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False)
    _titulo(
        eixo,
        "Eleições 2024 — Votos válidos, brancos e nulos por faixa de renda",
        "Soma dos votos registrados em todos os municípios da faixa (apuração TSE × renda Censo 2022)",
    )
    return _salvar(fig, "2024_votos_invalidos_renda.png")


def grafico_painel_bi(pacote: dict[str, pd.DataFrame], ano: int) -> Path | None:
    """Painel executivo (BI) com KPIs e gráficos-resumo do ano."""
    apuracao = pacote.get("apuracao", pd.DataFrame())
    votos = pacote.get("votos", pd.DataFrame())
    candidatos = pacote.get("candidatos", pd.DataFrame())
    eleitos = pacote.get("eleitos", pd.DataFrame())
    segundo_turno = pacote.get("segundo_turno", pd.DataFrame())
    if apuracao.empty and votos.empty:
        return None
    brasil = (
        votos[votos["uf"].astype(str).str.upper() != "ZZ"] if not votos.empty else votos
    )
    total_eleitores = int(apuracao["eleitores"].sum()) if not apuracao.empty else 0
    pct_comp = 100.0 * apuracao["comparecimento"].sum() / total_eleitores if total_eleitores else 0.0
    municipios = brasil["municipio_cd"].nunique() if not brasil.empty else 0
    total_votos = int(brasil["votos"].sum()) if not brasil.empty else 0
    n_2t = (
        segundo_turno.groupby(["uf", "municipio"], observed=True).ngroups
        if not segundo_turno.empty
        else 0
    )
    cargos_2t = set(segundo_turno["cargo_cd"].dropna().unique()) if not segundo_turno.empty else set()
    rotulo_2t = "Prefeitos em 2º turno" if cargos_2t <= {11} else "Disputas de 2º turno"
    kpis = [
        ("Eleitores aptos", _votos_br(total_eleitores) if total_eleitores else "—"),
        ("Comparecimento", _pct(pct_comp)),
        ("Municípios apurados", _br(municipios)),
        ("Candidaturas registradas", _br(len(candidatos)) if not candidatos.empty else "—"),
        ("Votos nominais analisados", _votos_br(total_votos)),
        (rotulo_2t, _br(n_2t) if n_2t else "—"),
    ]

    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(
        3, 6, height_ratios=[1, 1, 2.4], hspace=0.55, wspace=0.6, left=0.07, right=0.97, top=0.86, bottom=0.07
    )
    for indice, (rotulo, valor) in enumerate(kpis):
        linha, coluna = divmod(indice, 3)
        eixo = fig.add_subplot(gs[linha, coluna * 2 : coluna * 2 + 2])
        eixo.set_xticks([])
        eixo.set_yticks([])
        for espinha in eixo.spines.values():
            espinha.set_color("#cccccc")
        eixo.set_facecolor("#f5f5f5")
        eixo.text(0.5, 0.64, valor, ha="center", va="center", fontsize=20, fontweight="bold", color="#1f4e79", transform=eixo.transAxes)
        eixo.text(0.5, 0.22, rotulo, ha="center", va="center", fontsize=11, color="#444444", transform=eixo.transAxes)

    eixo = fig.add_subplot(gs[2, 0:3])
    agregado = pd.Series(dtype=float)
    if not eleitos.empty and ano == 2024 and "municipio" in eleitos.columns:
        prefeitos = eleitos[eleitos["cargo_cd"] == 11]
        if not prefeitos.empty:
            agregado = prefeitos.groupby("partido", observed=True)["municipio"].nunique().sort_values(ascending=False).head(10)
            eixo.set_xlabel("Municípios vencidos")
            eixo.set_title("Prefeitos eleitos — top 10 partidos", loc="left", fontsize=12, fontweight="bold")
    if agregado.empty and not brasil.empty:
        situacao = brasil["situacao"].astype(str).str.upper().str.strip()
        eleitos_cargo = brasil[brasil["cargo_cd"].isin((3, 5, 6, 7)) & situacao.str.startswith("ELEITO")]
        if not eleitos_cargo.empty and "candidato_sq" in eleitos_cargo:
            agregado = eleitos_cargo.groupby("partido", observed=True)["candidato_sq"].nunique().sort_values(ascending=False).head(10)
            eixo.set_xlabel("Cadeiras eleitas (gov., sen., dep.)")
            eixo.set_title("Eleitos — top 10 partidos (cargos estaduais)", loc="left", fontsize=12, fontweight="bold")
    if not agregado.empty:
        agregado = agregado.iloc[::-1]
        barras = eixo.barh(agregado.index, agregado.values, color=sns.color_palette("Blues_r", len(agregado)))
        eixo.bar_label(barras, labels=[f" {_br(int(v))}" for v in agregado.values], padding=3, fontsize=9)
        eixo.set_xlim(0, agregado.max() * 1.25)
    else:
        eixo.set_visible(False)

    eixo = fig.add_subplot(gs[2, 3:6])
    if not apuracao.empty:
        comp = apuracao.sort_values("pct_comparecimento")
        barras = eixo.barh(comp["uf"], comp["pct_comparecimento"], color="#2b8cbe")
        eixo.bar_label(barras, labels=[_pct(v) for v in comp["pct_comparecimento"]], padding=3, fontsize=8)
        eixo.set_xlim(0, 100)
        eixo.set_xlabel("% do eleitorado")
        eixo.set_title("Comparecimento por UF", loc="left", fontsize=12, fontweight="bold")
    else:
        eixo.set_visible(False)

    fig.suptitle(
        f"Eleições {ano} — Painel executivo (BI)",
        x=0.07,
        y=0.96,
        ha="left",
        fontsize=17,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.915,
        "Indicadores calculados a partir dos dados oficiais do TSE (votação, cadastro e comparecimento)",
        fontsize=11,
        color="#444444",
    )
    return _salvar(fig, f"{ano}_painel_bi.png")


def gerar_graficos(pacotes: dict[int, dict[str, pd.DataFrame]]) -> list[Path]:
    gerados: list[Path] = []
    for ano, pacote in pacotes.items():
        log(f"[figuras {ano}]")
        votos = pacote.get("votos", pd.DataFrame())
        candidatos = pacote.get("candidatos", pd.DataFrame())
        apuracao = pacote.get("apuracao", pd.DataFrame())
        eleitos = pacote.get("eleitos", pd.DataFrame())
        senado = pacote.get("senado", pd.DataFrame())
        mais_votados = pacote.get("mais_votados", pd.DataFrame())
        eleitorado = pacote.get("eleitorado", pd.DataFrame())
        idade_ibge = pacote.get("idade_ibge", pd.DataFrame())
        cruzamento = pacote.get("cruzamento", pd.DataFrame())
        segundo_turno = pacote.get("segundo_turno", pd.DataFrame())

        funcoes = []
        if ano == 2024:
            funcoes = [
                lambda: grafico_painel_bi(pacote, ano),
                lambda: grafico_partidos_prefeitura(votos),
                lambda: grafico_partidos_veradores(votos),
                lambda: grafico_prefeitos_eleitos(votos),
                lambda: grafico_comparecimento(apuracao, ano),
                lambda: grafico_genero(candidatos, ano),
                lambda: grafico_idade(candidatos, ano),
                lambda: grafico_concentracao(votos),
                lambda: grafico_cadeiras(votos, ano),
                lambda: grafico_prefeitos_mais_votados(mais_votados),
                lambda: grafico_vereadores_mais_votados(mais_votados),
                lambda: grafico_top_por_uf_prefeitos(mais_votados),
                lambda: grafico_top_por_uf_vereadores(mais_votados),
                lambda: grafico_segundo_turno_prefeitos(segundo_turno),
                lambda: grafico_segundo_turno_margens(segundo_turno),
                lambda: grafico_eleitorado_faixa_etaria(eleitorado),
                lambda: grafico_eleitorado_grau_instrucao(eleitorado),
                lambda: grafico_eleitorado_por_uf(eleitorado),
                lambda: grafico_eleitores_vs_populacao(idade_ibge),
                lambda: grafico_renda_vs_comparecimento(cruzamento),
                lambda: grafico_renda_vs_vencedor(cruzamento),
                lambda: grafico_renda_faixas_municipios(cruzamento),
                lambda: grafico_candidatos_por_renda(cruzamento),
                lambda: grafico_votos_invalidos_renda(cruzamento),
            ]
        elif ano == 2026:
            funcoes = [
                lambda: grafico_painel_bi(pacote, ano),
                lambda: grafico_presidente(votos),
                lambda: grafico_presidente_por_uf(votos),
                lambda: grafico_governadores(votos),
                lambda: grafico_comparecimento(apuracao, ano),
                lambda: grafico_deputados_partidos(votos),
                lambda: grafico_deputados_estaduais_partidos(votos),
                lambda: grafico_senadores_partidos(votos),
                lambda: grafico_cadeiras(votos, ano),
                lambda: grafico_genero(candidatos, ano),
                lambda: grafico_eleitos_painel(eleitos, votos, (5,), "Senador", "2026_senadores_eleitos.png", 5, ano=ano),
                lambda: grafico_eleitos_painel(eleitos, votos, (6,), "Deputado Federal", "2026_dep_federais_eleitos.png", 6, ano=ano),
                lambda: grafico_eleitos_painel(
                    eleitos, votos, (7, 8), "Deputado Estadual e Distrital", "2026_dep_estaduais_eleitos.png", 7, ano=ano
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
