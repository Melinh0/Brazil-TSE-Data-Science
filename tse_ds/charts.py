from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .analysis import candidatos_eleitos, resultado_por_candidato, vencedores_por_uf
from .config import PASTA_FIGURAS, ROTULOS_CARGO
from .http import log

sns.set_theme(style="whitegrid", palette="tab10")
FIGURA = (12, 7)
DPI = 150


def _br(valor: float, casas: int = 0) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _salvar(fig, nome: str) -> Path:
    PASTA_FIGURAS.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_FIGURAS / nome
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


def grafico_partidos_prefeitura(votos: pd.DataFrame) -> Path | None:
    dados = votos[(votos["cargo_cd"] == 11) & (votos["turno"] == 1)]
    if dados.empty:
        return None
    agregado = dados.groupby(["partido", "partido_nome"], observed=True)["votos"].sum().reset_index()
    agregado = agregado.sort_values("votos", ascending=False).head(15).iloc[::-1]
    total = dados["votos"].sum()

    fig, eixo = plt.subplots(figsize=FIGURA)
    barras = eixo.barh(agregado["partido"], agregado["votos"], color=sns.color_palette("Blues_r", len(agregado)))
    eixo.bar_label(
        barras,
        labels=[f" {_br(v / 1e6, 1)} mi ({_pct(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais para prefeito")
    eixo.set_ylabel("Partido")
    _titulo(eixo, "Eleições 2024 — Maiores partidos na disputa pela prefeitura", "Top 15 partidos por votos nominais (1º turno)")
    eixo.set_xlim(0, agregado["votos"].max() * 1.25)
    return _salvar(fig, "2024_prefeitura_top_partidos.png")


def grafico_prefeitos_eleitos(votos: pd.DataFrame) -> Path | None:
    eleitos = candidatos_eleitos(votos, 11)
    if eleitos.empty:
        return None
    agregado = eleitos.groupby("partido", observed=True)["municipio"].nunique().reset_index(name="municipios")
    agregado = agregado.sort_values("municipios", ascending=False).head(15).iloc[::-1]

    fig, eixo = plt.subplots(figsize=FIGURA)
    barras = eixo.barh(agregado["partido"], agregado["municipios"], color=sns.color_palette("Greens_r", len(agregado)))
    eixo.bar_label(barras, labels=[f" {_br(v)} municípios" for v in agregado["municipios"]], padding=4, fontsize=9)
    eixo.set_xlabel("Municípios vencidos")
    eixo.set_ylabel("Partido")
    _titulo(
        eixo,
        "Eleições 2024 — Prefeitos eleitos por partido",
        "Municípios com candidato à prefeitura em situação \"Eleito\" (inclui vencedores de 2º turno)",
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
    paleta = sns.color_palette("Set2", len(cargos_alvo))
    for cor, cargo in zip(paleta, cargos_alvo):
        sub = dados[dados["cargo_cd"] == cargo]["idade"]
        if sub.empty:
            continue
        eixo.hist(sub, bins=np.arange(18, 82, 2), histtype="stepfilled", alpha=0.55, label=ROTULOS_CARGO[str(cargo)], color=cor)
    eixo.axvline(dados["idade"].median(), color="#333333", linestyle="--", linewidth=1.5)
    eixo.text(dados["idade"].median() + 0.6, eixo.get_ylim()[1] * 0.95, f"mediana {dados['idade'].median():.0f} anos", fontsize=9)
    eixo.set_xlabel("Idade na data da eleição")
    eixo.set_ylabel("Número de candidaturas")
    eixo.legend(title="Cargo")
    _titulo(eixo, f"Eleições {ano} — Distribuição de idade das candidaturas", "Histograma por cargo principal")
    return _salvar(fig, f"{ano}_idade_candidatos.png")


def grafico_concentracao(votos: pd.DataFrame) -> Path | None:
    dados = votos[votos["cargo_cd"] == 13]
    if dados.empty:
        return None
    por_candidato = dados.groupby(["uf", "municipio", "candidato_urna"], observed=True)["votos"].sum().sort_values(ascending=False)
    por_candidato = por_candidato[por_candidato > 0]
    if por_candidato.empty:
        return None
    acumulado = por_candidato.cumsum() / por_candidato.sum()
    percentual_candidatos = 100.0 * np.arange(1, len(acumulado) + 1) / len(acumulado)

    top10 = acumulado[percentual_candidatos <= 10].iloc[-1]
    fig, eixo = plt.subplots(figsize=FIGURA)
    eixo.plot([0, 100], [0, 100], linestyle="--", color="#999999", label="Distribuição uniforme")
    eixo.plot(percentual_candidatos, acumulado.values * 100, color="#7b3294", linewidth=2.2, label="Votos de vereadores")
    eixo.fill_between(percentual_candidatos, 0, acumulado.values * 100, color="#7b3294", alpha=0.12)
    eixo.axvline(10, color="#c51b7d", linestyle=":", linewidth=1.4)
    eixo.annotate(
        f"10% mais votados\nconcentram {_pct(top10 * 100)} dos votos",
        xy=(10, top10 * 100),
        xytext=(28, top10 * 100 - 22),
        arrowprops={"arrowstyle": "->", "color": "#c51b7d"},
        fontsize=10,
        color="#c51b7d",
    )
    eixo.set_xlabel("% de candidatos (ordenados dos mais aos menos votados)")
    eixo.set_ylabel("% acumulado de votos")
    eixo.set_xlim(0, 100)
    eixo.set_ylim(0, 100)
    eixo.legend(loc="lower right")
    _titulo(eixo, "Eleições 2024 — Concentração dos votos em vereadores", "Curva de Lorenz da votação nominal de vereador")
    return _salvar(fig, "2024_concentracao_votos.png")


def grafico_presidente(votos: pd.DataFrame) -> Path | None:
    agregado = resultado_por_candidato(votos, 1)
    if agregado.empty:
        return None
    agregado = agregado[agregado["votos_validos"] > 0].sort_values("votos_validos", ascending=True).tail(12)

    fig, eixo = plt.subplots(figsize=FIGURA)
    rotulos = [f"{candidato} ({partido})" for candidato, partido in zip(agregado["candidato_urna"], agregado["partido"])]
    barras = eixo.barh(rotulos, agregado["votos_validos"], color=sns.color_palette("Reds_r", len(agregado)))
    total = agregado["votos_validos"].sum()
    eixo.bar_label(
        barras,
        labels=[f" {_br(v / 1e6, 2)} mi ({_pct(100 * v / total)})" for v in agregado["votos_validos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos válidos (soma dos municípios)")
    _titulo(
        eixo,
        "Eleições 2026 — Resultado da presidência no 1º turno",
        "Agregação de todos os municípios a partir dos arquivos oficiais de votação",
    )
    eixo.set_xlim(0, agregado["votos_validos"].max() * 1.3)
    return _salvar(fig, "2026_presidente_resultado.png")


def grafico_presidente_por_uf(votos: pd.DataFrame) -> Path | None:
    dados = votos[(votos["cargo_cd"] == 1) & (votos["uf"].astype(str).str.upper() != "ZZ")]
    if dados.empty:
        return None
    agregado = dados.groupby(["uf", "candidato_urna"], observed=True)[["votos_validos"]].sum().reset_index()
    totais = agregado.groupby("uf", observed=True)["votos_validos"].sum().rename("total")
    agregado = agregado.join(totais, on="uf")
    agregado["pct"] = 100.0 * agregado["votos_validos"] / agregado["total"]

    principais = (
        agregado.groupby("candidato_urna", observed=True)["votos_validos"].sum().sort_values(ascending=False).head(6).index
    )
    matriz = agregado[agregado["candidato_urna"].isin(principais)].pivot_table(
        index="uf", columns="candidato_urna", values="pct", aggfunc="sum", fill_value=0.0
    )
    matriz = matriz[[c for c in principais if c in matriz.columns]]
    matriz = matriz.sort_values(matriz.columns[0], ascending=False)

    fig, eixo = plt.subplots(figsize=(13, 15))
    sns.heatmap(
        matriz,
        annot=matriz.map(lambda valor: _pct(valor) if pd.notna(valor) else ""),
        fmt="",
        cmap="YlOrRd",
        linewidths=0.4,
        cbar_kws={"label": "% dos votos válidos na UF"},
        ax=eixo,
        annot_kws={"size": 8},
    )
    eixo.set_yticklabels(matriz.index, fontsize=10, rotation=0)
    eixo.tick_params(axis="y", length=0)
    eixo.set_xlabel("")
    eixo.set_ylabel("Estado")
    _titulo(
        eixo,
        "Eleições 2026 — Votos na presidência por estado",
        "Percentual dos 6 candidatos mais votados nacionalmente",
    )
    return _salvar(fig, "2026_presidente_por_uf.png")


def grafico_governadores(votos: pd.DataFrame) -> Path | None:
    vencedores = vencedores_por_uf(votos, 3)
    if vencedores.empty:
        return None
    dados = vencedores.sort_values("pct")

    fig, eixo = plt.subplots(figsize=(12, 11))
    rotulos = [f"{uf} — {candidato} ({partido})" for uf, candidato, partido in zip(dados["uf"], dados["candidato_urna"], dados["partido"])]
    cores = ["#1a9850" if v >= 50 else "#fdae61" for v in dados["pct"]]
    barras = eixo.barh(rotulos, dados["pct"], color=cores)
    eixo.bar_label(barras, labels=[f" {_pct(v)}" for v in dados["pct"]], padding=4, fontsize=8)
    eixo.axvline(50, color="#333333", linestyle="--", linewidth=1.2, label="Maioria simples (50%)")
    eixo.set_xlabel("% dos votos válidos da UF")
    eixo.set_xlim(0, max(60, dados["pct"].max() * 1.15))
    eixo.legend(loc="lower right")
    _titulo(
        eixo,
        "Eleições 2026 — Candidato à frente na disputa de governador",
        "Verde: mais de 50%; laranja: abaixo de 50% (segundo turno em 25/10/2026)",
    )
    return _salvar(fig, "2026_governador_liderancas.png")


def grafico_deputados_partidos(votos: pd.DataFrame) -> Path | None:
    dados = votos[votos["cargo_cd"] == 6]
    if dados.empty:
        return None
    agregado = dados.groupby(["partido", "partido_nome"], observed=True)["votos"].sum().reset_index()
    agregado = agregado.sort_values("votos", ascending=False).head(15).iloc[::-1]
    total = dados["votos"].sum()

    fig, eixo = plt.subplots(figsize=FIGURA)
    barras = eixo.barh(agregado["partido"], agregado["votos"], color=sns.color_palette("Purples_r", len(agregado)))
    eixo.bar_label(
        barras,
        labels=[f" {_br(v / 1e6, 1)} mi ({_pct(100 * v / total)})" for v in agregado["votos"]],
        padding=4,
        fontsize=9,
    )
    eixo.set_xlabel("Votos nominais para deputado federal")
    eixo.set_ylabel("Partido")
    _titulo(eixo, "Eleições 2026 — Votos em deputado federal por partido", "Top 15 partidos, todos os estados")
    eixo.set_xlim(0, agregado["votos"].max() * 1.3)
    return _salvar(fig, "2026_deputados_federais_partidos.png")


def gerar_graficos(pacotes: dict[int, dict[str, pd.DataFrame]]) -> list[Path]:
    gerados: list[Path] = []
    for ano, pacote in pacotes.items():
        log(f"[figuras {ano}]")
        votos = pacote.get("votos", pd.DataFrame())
        candidatos = pacote.get("candidatos", pd.DataFrame())
        apuracao = pacote.get("apuracao", pd.DataFrame())

        funcoes = []
        if ano == 2024:
            funcoes = [
                lambda: grafico_partidos_prefeitura(votos),
                lambda: grafico_prefeitos_eleitos(votos),
                lambda: grafico_comparecimento(apuracao, ano),
                lambda: grafico_genero(candidatos, ano),
                lambda: grafico_idade(candidatos, ano),
                lambda: grafico_concentracao(votos),
            ]
        elif ano == 2026:
            funcoes = [
                lambda: grafico_presidente(votos),
                lambda: grafico_presidente_por_uf(votos),
                lambda: grafico_governadores(votos),
                lambda: grafico_comparecimento(apuracao, ano),
                lambda: grafico_deputados_partidos(votos),
                lambda: grafico_genero(candidatos, ano),
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
