from __future__ import annotations

import numbers
from datetime import datetime
from pathlib import Path

import pandas as pd

from .analysis import candidatos_eleitos, resultado_por_candidato
from .config import PASTA_FIGURAS, PASTA_SAIDA
from .http import log

ROTULOS = {
    "uf": "UF",
    "partido": "Sigla",
    "partido_nome": "Partido",
    "votos": "Votos",
    "pct": "%",
    "municipio": "Município",
    "candidato_urna": "Candidato (urna)",
    "candidato": "Candidato",
    "candidato_nr": "Nº",
    "idade": "Idade",
    "genero": "Gênero",
    "raca": "Raça",
    "escolaridade": "Escolaridade",
    "cargo": "Cargo",
    "nascimento": "Nascimento",
}

COLUNAS_LISTA_ELEITOS = [
    "uf",
    "municipio",
    "candidato",
    "candidato_urna",
    "partido",
    "partido_nome",
    "idade",
    "genero",
    "votos",
]


def _celula(valor) -> str:
    try:
        if valor is None or pd.isna(valor):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(valor, numbers.Integral):
        return f"{int(valor):,}".replace(",", ".")
    if isinstance(valor, numbers.Real):
        if float(valor).is_integer():
            return f"{int(valor):,}".replace(",", ".")
        return f"{valor:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor)


def _tabela_md(
    quadro: pd.DataFrame,
    colunas: list[str] | None = None,
    limite: int = 15,
    rotulos: bool = False,
) -> str:
    dados = quadro.head(limite)
    if colunas:
        dados = dados[[c for c in colunas if c in dados.columns]]
    if dados.empty:
        return "_sem dados_"
    cabecalho = (
        "| "
        + " | ".join(
            ROTULOS.get(col, str(col).replace("_", " ").title()) if rotulos else str(col).replace("_", " ").title()
            for col in dados.columns
        )
        + " |"
    )
    separador = "|" + "|".join(["---"] * len(dados.columns)) + "|"
    linhas = [cabecalho, separador]
    for _, linha in dados.iterrows():
        linhas.append("| " + " | ".join(_celula(valor) for valor in linha) + " |")
    return "\n".join(linhas)


def _numero(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _figuras_do_ano(ano: int) -> list[Path]:
    if not PASTA_FIGURAS.exists():
        return []
    return sorted(PASTA_FIGURAS.glob(f"{ano}_*.png"))


def _secao_partidos(partidos: pd.DataFrame, por_estado: bool) -> list[str]:
    if partidos.empty:
        return []
    titulo = (
        "### Todos os partidos — resultado por estado"
        if por_estado
        else "### Todos os partidos — total nacional"
    )
    linhas = [titulo, ""]
    colunas = (["uf"] if por_estado else []) + ["partido", "partido_nome", "votos", "pct"]
    for cargo_cd in sorted(partidos["cargo_cd"].dropna().unique()):
        sub = partidos[partidos["cargo_cd"] == cargo_cd]
        rotulo = str(sub["cargo"].iloc[0]) if "cargo" in sub.columns else str(cargo_cd)
        linhas.append(f"#### {rotulo}")
        linhas.append("")
        linhas.append(_tabela_md(sub, colunas, limite=len(sub), rotulos=True))
        linhas.append("")
    return linhas


def _resumo_genero(eleitos: pd.DataFrame) -> str:
    if eleitos.empty or "genero" not in eleitos.columns:
        return ""
    contagem = eleitos["genero"].astype(str).str.upper().str.strip().value_counts()
    partes = [
        f"{rotulo.lower()}s: {_numero(contagem.get(rotulo, 0))}"
        for rotulo in ("FEMININO", "MASCULINO")
        if contagem.get(rotulo, 0)
    ]
    return "; ".join(partes)


def _pendencias_finais(eleitos: pd.DataFrame, votos: pd.DataFrame) -> list[str]:
    """Cargos/UFs sem resultado final publicado pelo TSE na base baixada."""
    notas: list[str] = []
    if votos.empty:
        return notas
    for cargo_cd in sorted(votos["cargo_cd"].dropna().unique()):
        sub = votos[votos["cargo_cd"] == cargo_cd]
        if sub.empty:
            continue
        rotulo = str(sub["cargo"].iloc[0])
        eleitos_sub = (
            eleitos[eleitos["cargo_cd"] == cargo_cd] if not eleitos.empty else eleitos
        )
        if eleitos_sub.empty:
            notas.append(
                f"- **{rotulo}**: sem resultado final publicado pelo TSE "
                f"(situação `#NULO` no cadastro); {_numero(sub['candidato_sq'].nunique())} candidatos e "
                f"{_numero(sub['votos'].sum())} votos já apurados."
            )
            continue
        ufs_dados = set(sub["uf"].astype(str))
        ufs_finalizadas = set(eleitos_sub["uf"].astype(str))
        faltando = sorted(ufs_dados - ufs_finalizadas)
        if faltando:
            situacao = sub["situacao"].astype(str).str.upper().str.contains("TURNO").any()
            motivo = "2º turno pendente" if situacao else "sem marcação de eleito na base"
            notas.append(
                f"- **{rotulo}**: sem resultado final em {len(faltando)} UF(s): "
                f"{', '.join(faltando)} ({motivo})."
            )
    return notas


def _secao_eleitos(eleitos: pd.DataFrame, ano: int, votos: pd.DataFrame | None = None) -> list[str]:
    if eleitos.empty and (votos is None or votos.empty):
        return []
    linhas: list[str] = ["### Eleitos — cargos analisados", ""]
    if not eleitos.empty:
        resumo_geral = _resumo_genero(eleitos)
        if resumo_geral:
            linhas.append(f"Distribuição por gênero (todos os cargos): {resumo_geral}.")
            linhas.append("")
            linhas.append(
                f"Listas completas com nome, partido, idade e gênero: "
                f"`outputs/eleitos_{ano}.md` e `outputs/tabelas/eleitos_{ano}.csv`."
            )
            linhas.append("")
    pendencias = _pendencias_finais(eleitos, votos) if votos is not None else []
    if pendencias:
        linhas.append("Cargos/UFs ainda sem resultado final na base baixada:")
        linhas.append("")
        linhas.extend(pendencias)
        linhas.append("")
    if eleitos.empty:
        return linhas
    for cargo_cd in sorted(eleitos["cargo_cd"].dropna().unique()):
        sub = eleitos[eleitos["cargo_cd"] == cargo_cd]
        rotulo = str(sub["cargo"].iloc[0]) if "cargo" in sub.columns else str(cargo_cd)
        linhas.append(f"#### {rotulo} — {_numero(len(sub))} eleitos")
        linhas.append("")
        resumo = _resumo_genero(sub)
        if resumo:
            linhas.append(f"Gênero: {resumo}.")
            linhas.append("")
        if len(sub) <= 600:
            linhas.append(_tabela_md(sub, COLUNAS_LISTA_ELEITOS, limite=len(sub), rotulos=True))
            linhas.append("")
        else:
            colunas = ["partido", "partido_nome"]
            if "municipio" in sub.columns:
                colunas.append("municipio")
            else:
                colunas.append("uf")
            agregado = (
                sub.groupby(colunas, observed=True, dropna=False)
                .agg(quantidade=("candidato_urna", "nunique"), votos=("votos", "sum"))
                .reset_index()
                .sort_values("quantidade", ascending=False)
                .head(20)
            )
            linhas.append(
                f"Tabela completa ({_numero(len(sub))} linhas) em `outputs/eleitos_{ano}.md`. "
                "Resumo por partido:"
            )
            linhas.append("")
            linhas.append(_tabela_md(agregado, None, limite=len(agregado), rotulos=True))
            linhas.append("")
    return linhas


def gerar_listas_eleitos(pacotes: dict[int, dict[str, pd.DataFrame]]) -> dict[int, Path]:
    """Gera as listas completas dos eleitos (todos os cargos) em markdown."""
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    gerados: dict[int, Path] = {}
    for ano in sorted(pacotes):
        eleitos = pacotes[ano].get("eleitos", pd.DataFrame())
        votos = pacotes[ano].get("votos", pd.DataFrame())
        destino = PASTA_SAIDA / f"eleitos_{ano}.md"
        if eleitos.empty:
            continue
        partes = [f"# Eleitos {ano} — todos os cargos analisados", ""]
        partes.append(f"*Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} a partir dos dados abertos do TSE.*")
        partes.append("")
        partes.append(
            f"Total: **{_numero(len(eleitos))}** candidatos eleitos nos cargos analisados; "
            f"distribuição por gênero: {_resumo_genero(eleitos)}."
        )
        partes.append("")
        pendencias = _pendencias_finais(eleitos, votos)
        if pendencias:
            partes.append("Cargos/UFs ainda sem resultado final na base baixada:")
            partes.append("")
            partes.extend(pendencias)
            partes.append("")
        colunas = [c for c in COLUNAS_LISTA_ELEITOS if c in eleitos.columns]
        for cargo_cd in sorted(eleitos["cargo_cd"].dropna().unique()):
            sub = eleitos[eleitos["cargo_cd"] == cargo_cd]
            rotulo = str(sub["cargo"].iloc[0]) if "cargo" in sub.columns else str(cargo_cd)
            partes.append(f"## {rotulo} — {_numero(len(sub))} eleitos")
            partes.append("")
            resumo = _resumo_genero(sub)
            if resumo:
                partes.append(f"Gênero: {resumo}.")
                partes.append("")
            if len(sub) > 400 and "uf" in sub.columns:
                for uf, grupo in sub.groupby("uf", sort=True):
                    partes.append(f"### {uf} — {_numero(len(grupo))}")
                    partes.append("")
                    partes.append(_tabela_md(grupo, colunas, limite=len(grupo), rotulos=True))
                    partes.append("")
            else:
                partes.append(_tabela_md(sub, colunas, limite=len(sub), rotulos=True))
                partes.append("")
        destino.write_text("\n".join(partes), encoding="utf-8")
        gerados[ano] = destino
        log(f"  [ok] listas de eleitos: {destino.name} ({destino.stat().st_size:,} bytes)")
    return gerados


def gerar(pacotes: dict[int, dict[str, pd.DataFrame]]) -> Path:
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    destino = PASTA_SAIDA / "relatorio.md"
    listas = gerar_listas_eleitos(pacotes)
    partes: list[str] = []
    partes.append("# Análise das Eleições Brasileiras — TSE 2024 e 2026")
    partes.append("")
    partes.append(f"*Relatório gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} a partir dos dados abertos do Tribunal Superior Eleitoral.*")
    partes.append("")
    partes.append("Fontes: Portal de Dados Abertos do TSE (CSVs de votação e candidaturas) e")
    partes.append("plataforma de divulgação de resultados (`resultados.tse.jus.br`, arquivos JSON EA11/EA12/EA14/EA20).")
    partes.append("")

    for ano in sorted(pacotes):
        pacote = pacotes[ano]
        votos = pacote.get("votos", pd.DataFrame())
        candidatos = pacote.get("candidatos", pd.DataFrame())
        apuracao = pacote.get("apuracao", pd.DataFrame())
        partidos = pacote.get("partidos", pd.DataFrame())
        partidos_estado = pacote.get("partidos_estado", pd.DataFrame())
        eleitos = pacote.get("eleitos", pd.DataFrame())
        partes.append(f"## Eleições {ano}")
        partes.append("")

        if not apuracao.empty:
            total_eleitores = apuracao["eleitores"].sum()
            total_comparecimento = apuracao["comparecimento"].sum()
            total_abstencao = apuracao["abstencao"].sum()
            partes.append(f"- Eleitorado: **{_numero(total_eleitores)}** eleitores")
            partes.append(f"- Comparecimento: **{_numero(total_comparecimento)}** ({100 * total_comparecimento / total_eleitores:.1f}%)")
            partes.append(f"- Abstenção: **{_numero(total_abstencao)}** ({100 * total_abstencao / total_eleitores:.1f}%)")
            menor = apuracao.loc[apuracao["pct_comparecimento"].idxmin()]
            maior = apuracao.loc[apuracao["pct_comparecimento"].idxmax()]
            partes.append(
                f"- Maior comparecimento: **{maior['uf']}** ({maior['pct_comparecimento']:.1f}%); "
                f"menor: **{menor['uf']}** ({menor['pct_comparecimento']:.1f}%)"
            )
            partes.append("")

        if not votos.empty:
            total_votos = int(votos["votos"].sum())
            brasil = votos[votos["uf"].astype(str).str.upper() != "ZZ"]
            municípios = brasil["municipio_cd"].nunique()
            partes.append(f"- Votos nominais apurados (cargos analisados): **{_numero(total_votos)}**")
            partes.append(f"- Municípios com dados: **{_numero(municípios)}**")
            partes.append("")

        if ano == 2026 and not votos.empty:
            presidente = resultado_por_candidato(votos, 1)
            if not presidente.empty:
                partes.append("### Presidência — 1º turno")
                partes.append("")
                partes.append(
                    _tabela_md(
                        presidente.head(10),
                        ["candidato_urna", "partido", "votos_validos", "pct"],
                    )
                )
                partes.append("")
            governador = resultado_por_candidato(votos, 3)
            if not governador.empty:
                cargos = len(votos[votos["cargo_cd"] == 3]["uf"].unique())
                partes.append(f"### Governadores — {cargos} unidades federativas em disputa")
                partes.append("")
                top_partidos = (
                    votos[votos["cargo_cd"] == 3].groupby("partido", observed=True)["votos"].sum().sort_values(ascending=False).head(8)
                )
                partes.append(_tabela_md(top_partidos.reset_index(), ["partido", "votos"]))
                partes.append("")

        if ano == 2024 and not votos.empty:
            prefeitos = candidatos_eleitos(votos, 11)
            if not prefeitos.empty:
                por_partido = prefeitos.groupby("partido", observed=True)["municipio"].nunique().sort_values(ascending=False).head(10)
                partes.append("### Prefeitos eleitos por partido")
                partes.append("")
                partes.append(_tabela_md(por_partido.reset_index(), ["partido", "municipio"]))
                partes.append("")

        if not candidatos.empty and "genero" in candidatos:
            contagem = candidatos["genero"].str.upper().value_counts()
            if not contagem.empty:
                total_cand = contagem.sum()
                feminino = int(contagem.get("FEMININO", 0))
                partes.append(
                    f"- Candidaturas registradas: **{_numero(total_cand)}** "
                    f"({100 * feminino / total_cand:.1f}% femininas)"
                )
                partes.append("")

        partes.extend(_secao_partidos(partidos, por_estado=False))
        partes.extend(_secao_partidos(partidos_estado, por_estado=True))
        partes.extend(_secao_eleitos(eleitos, ano, votos))
        if ano in listas:
            relativo = listas[ano].relative_to(PASTA_SAIDA).as_posix()
            partes.append(f"Listas completas dos eleitos: [`{relativo}`]({relativo})")
            partes.append("")

        figuras = _figuras_do_ano(ano)
        if figuras:
            partes.append("### Gráficos")
            partes.append("")
            for figura in figuras:
                relativo = figura.relative_to(PASTA_SAIDA).as_posix()
                partes.append(f"![{figura.stem}]({relativo})")
                partes.append("")

        partes.append("---")
        partes.append("")

    partes.append("## Reproduzir esta análise")
    partes.append("")
    partes.append("```bash")
    partes.append("pip install -r requirements.txt")
    partes.append("python main.py tudo --ano 2024 --ano 2026")
    partes.append("```")
    partes.append("")
    partes.append("Comandos úteis:")
    partes.append("")
    partes.append("| Comando | O que faz |")
    partes.append("|---|---|")
    partes.append("| `python main.py meta` | lista as fontes de dados disponíveis |")
    partes.append("| `python main.py baixar` | baixa CSVs do CKAN e JSONs da divulgação (paralelo) |")
    partes.append("| `python main.py analisar` | gera as tabelas tratadas e caches |")
    partes.append("| `python main.py graficos` | gera os PNGs |")
    partes.append("| `python main.py relatorio` | gera `relatorio.md` e as listas de eleitos |")
    partes.append("| `python main.py tudo` | pipeline completo |")
    partes.append("")
    partes.append("Saídas:")
    partes.append("")
    partes.append("- `outputs/figuras/*.png` — gráficos;")
    partes.append("- `outputs/relatorio.md` — este relatório;")
    partes.append("- `outputs/eleitos_2024.md` e `outputs/eleitos_2026.md` — listas completas dos eleitos (nome, partido, idade, gênero);")
    partes.append("- `outputs/tabelas/eleitos_{ano}.csv` — mesmas listas em CSV;")
    partes.append("- `outputs/tabelas/partidos_nacional_{ano}.csv` — votos de todos os partidos no país;")
    partes.append("- `outputs/tabelas/partidos_estado_{ano}.csv` — votos de todos os partidos por estado;")
    partes.append("- `outputs/tabelas/votos_municipio_{ano}.parquet`, `candidatos_{ano}.parquet` — bases tratadas.")
    partes.append("")

    destino.write_text("\n".join(partes), encoding="utf-8")
    log(f"  [ok] relatorio: {destino}")
    return destino
