from __future__ import annotations

import glob
import json
import time
from pathlib import Path

import pandas as pd

from .config import (
    NOMES_CARGO,
    ORDEM_CARGO,
    PASTA_APP,
    PASTA_JSON,
    PASTA_TABELAS,
    REGIOES,
    UF_REGIAO,
    garantir_pastas_app,
)
from .escopo import (
    TIPO_BR,
    TIPO_MUNICIPIO,
    TIPO_REGIAO,
    TIPO_UF,
    Escopo,
)

COLUNAS_VOTOS = [
    "turno",
    "eleicao_cd",
    "uf",
    "municipio_cd",
    "municipio",
    "cargo_cd",
    "cargo",
    "candidato_sq",
    "partido",
    "partido_nome",
    "candidato_urna",
    "situacao",
    "votos",
]

COLUNAS_INFO = [
    "candidato_sq",
    "candidato",
    "candidato_nr",
    "nascimento",
    "idade",
    "genero",
    "raca",
    "escolaridade",
]

CATEGORICAS = [
    "uf",
    "municipio",
    "cargo",
    "partido",
    "partido_nome",
    "candidato_urna",
    "situacao",
]

# unidade em que cada cargo é eleito × unidade de navegação do app: quando o
# escopo é maior que a unidade da eleição (ex.: prefeito visto no Brasil), a
# aba Eleitos lista os TOP_ELEITOS_ESCOPO candidatos eleitos mais votados.
UNIDADE_CARGO = {
    11: "municipio",
    13: "municipio",
    3: "uf",
    5: "uf",
    6: "uf",
    7: "uf",
    8: "uf",
    1: "brasil",
}
UNIDADE_ESCOPO = {
    TIPO_MUNICIPIO: "municipio",
    TIPO_UF: "uf",
    TIPO_REGIAO: "regiao",
    TIPO_BR: "brasil",
}
ORDEM_UNIDADE = {"municipio": 0, "uf": 1, "regiao": 2, "brasil": 3}
TOP_ELEITOS_ESCOPO = 25


def _locais_eleicao(decisao: pd.DataFrame, cargo_cd: int) -> dict[str, str]:
    """{candidato_sq: local em que foi eleito} — 'MUNICIPIO/UF' (municipal) ou 'UF'."""
    if cargo_cd == 1:
        return {}
    base = decisao.dropna(subset=["candidato_sq"]).drop_duplicates("candidato_sq")
    mapa: dict[str, str] = {}
    for registro in base.itertuples():
        sq = str(registro.candidato_sq)
        uf_valor = getattr(registro, "uf", None)
        uf = (
            ""
            if uf_valor is None or pd.isna(uf_valor)
            else str(uf_valor).strip().upper()
        )
        if cargo_cd in (11, 13):
            mun_valor = getattr(registro, "municipio", None)
            municipio = (
                ""
                if mun_valor is None or pd.isna(mun_valor)
                else str(mun_valor).strip().upper()
            )
            mapa[sq] = f"{municipio}/{uf}" if municipio and uf else (municipio or uf)
        elif uf:
            mapa[sq] = uf
    return mapa


def br(n: int | float | None) -> str:
    """Número no padrão pt-BR."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    return f"{int(round(float(n))):,}".replace(",", ".")


def pct(n: float | None, casas: int = 1) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    texto = f"{n:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{texto}%"


def moeda(n: float | None) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    return "R$ " + f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class FonteDados:
    """Camada de acesso aos resultados tratados (outputs/tabelas) e ao IBGE."""

    def __init__(self) -> None:
        garantir_pastas_app()
        self._mapa: pd.DataFrame | None = None
        self._votos: dict[int, pd.DataFrame] = {}
        self._info: dict[int, pd.DataFrame] = {}
        self._apuracao: dict[int, pd.DataFrame] = {}
        self._cruzamento: pd.DataFrame | None = None
        self._perfil: dict[int, pd.DataFrame] = {}
        self._idade: dict[int, pd.DataFrame] = {}
        self._cache_candidatos: dict[tuple, pd.DataFrame] = {}
        self._cache_serie: dict[tuple, dict] = {}
        self._cache_zonas: dict[tuple, pd.DataFrame] = {}
        self._cache_eleitos: dict[tuple, pd.DataFrame] = {}
        self._cache_secoes: dict[tuple, pd.DataFrame] = {}

    # ------------------------------------------------------------------ base
    def mapa_municipios(self) -> pd.DataFrame:
        """Correspondência TSE (municipio_cd) ↔ IBGE (7 dígitos) pelos JSONs da divulgação."""
        if self._mapa is not None:
            return self._mapa
        destino = PASTA_APP / "mapa_municipios.csv"
        linhas: list[dict] = []
        arquivos = sorted(
            glob.glob(str(PASTA_JSON / "ele*" / "**" / "mun-e*-cm.json"), recursive=True)
        )
        for caminho in arquivos:
            try:
                bruto = json.loads(Path(caminho).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for uf in bruto.get("abr", []):
                sigla = str(uf.get("cd", "")).upper()
                for mun in uf.get("mu", []):
                    try:
                        tse = int(str(mun.get("cd", "0")))
                        ibge = int(str(mun.get("cdi", "0")))
                    except ValueError:
                        continue
                    linhas.append(
                        {
                            "uf": sigla,
                            "municipio_cd": tse,
                            "municipio_ibge": ibge,
                            "municipio": str(mun.get("nm", "")).strip(),
                        }
                    )
        if linhas:
            quadro = (
                pd.DataFrame(linhas)
                .drop_duplicates(["uf", "municipio_cd"], keep="last")
                .reset_index(drop=True)
            )
            PASTA_APP.mkdir(parents=True, exist_ok=True)
            quadro.to_csv(destino, index=False, encoding="utf-8")
        elif destino.exists():
            quadro = pd.read_csv(destino)
        else:
            quadro = pd.DataFrame(
                columns=["uf", "municipio_cd", "municipio_ibge", "municipio"]
            )
        quadro["municipio_cd"] = quadro["municipio_cd"].astype("int64")
        quadro["municipio_ibge"] = quadro["municipio_ibge"].astype("int64")
        quadro["uf"] = quadro["uf"].astype(str).str.upper()
        self._mapa = quadro
        return quadro

    def votos(self, ano: int) -> pd.DataFrame:
        """Votos por município/candidato no turno decisivo da eleição principal de cada município."""
        if ano in self._votos:
            return self._votos[ano]
        destino = PASTA_APP / f"votos_{ano}.parquet"
        if destino.exists():
            quadro = pd.read_parquet(destino)
            self._votos[ano] = quadro
            return quadro
        origem = PASTA_TABELAS / f"votos_municipio_{ano}.parquet"
        if not origem.exists():
            raise FileNotFoundError(f"tabela de votos ausente: {origem}")
        inicio = time.time()
        bruto = pd.read_parquet(origem, columns=COLUNAS_VOTOS)
        bruto = bruto[bruto["uf"].astype(str).str.upper() != "ZZ"]
        totais = (
            bruto.groupby(["municipio_cd", "cargo_cd", "eleicao_cd"], observed=True)[
                "votos"
            ]
            .sum()
            .reset_index()
        )
        principal = (
            totais.sort_values("votos", ascending=False)
            .drop_duplicates(["municipio_cd", "cargo_cd"])[
                ["municipio_cd", "cargo_cd", "eleicao_cd"]
            ]
        )
        quadro = bruto.merge(
            principal, on=["municipio_cd", "cargo_cd", "eleicao_cd"], how="inner"
        )
        turno_max = quadro.groupby(["municipio_cd", "cargo_cd"], observed=True)[
            "turno"
        ].transform("max")
        quadro = quadro[quadro["turno"] == turno_max].drop(columns=["eleicao_cd"])
        for coluna in CATEGORICAS:
            if coluna in quadro:
                quadro[coluna] = quadro[coluna].astype("category")
        quadro["turno"] = quadro["turno"].astype("int8")
        quadro["municipio_cd"] = quadro["municipio_cd"].astype("int64")
        quadro["candidato_sq"] = quadro["candidato_sq"].astype(str)
        quadro = quadro.reset_index(drop=True)
        PASTA_APP.mkdir(parents=True, exist_ok=True)
        quadro.to_parquet(destino, index=False)
        self._votos[ano] = quadro
        print(
            f"  [app] cache de votos {ano}: {len(quadro):,} linhas "
            f"({time.time() - inicio:.1f}s, {destino.name})"
        )
        return quadro

    def info_candidatos(self, ano: int) -> pd.DataFrame:
        if ano in self._info:
            return self._info[ano]
        origem = PASTA_TABELAS / f"candidatos_{ano}.parquet"
        if origem.exists():
            quadro = pd.read_parquet(origem, columns=COLUNAS_INFO)
            quadro["candidato_sq"] = quadro["candidato_sq"].astype(str)
            quadro = quadro.drop_duplicates("candidato_sq").set_index("candidato_sq")
        else:
            quadro = pd.DataFrame().rename_axis("candidato_sq")
        self._info[ano] = quadro
        return quadro

    def apuracao(self, ano: int) -> pd.DataFrame:
        if ano in self._apuracao:
            return self._apuracao[ano]
        caminho = PASTA_TABELAS / f"apuracao_uf_{ano}.csv"
        quadro = pd.read_csv(caminho) if caminho.exists() else pd.DataFrame()
        if not quadro.empty:
            quadro["regiao"] = quadro["uf"].map(UF_REGIAO)
        self._apuracao[ano] = quadro
        return quadro

    def cruzamento(self) -> pd.DataFrame:
        if self._cruzamento is not None:
            return self._cruzamento
        caminho = PASTA_TABELAS / "cruzamento_municipios_2024.csv"
        quadro = pd.read_csv(caminho) if caminho.exists() else pd.DataFrame()
        if not quadro.empty:
            quadro["uf"] = quadro["uf"].astype(str).str.upper()
            quadro["regiao"] = quadro["uf"].map(UF_REGIAO)
            quadro = self._enriquecer_cruzamento(quadro)
        self._cruzamento = quadro
        return quadro

    @staticmethod
    def _enriquecer_cruzamento(quadro: pd.DataFrame) -> pd.DataFrame:
        """Acrescenta municipio_ibge e PIB per capita (IBGE 2022) ao cruzamento."""
        mapa = PASTA_APP / "mapa_municipios.csv"
        if mapa.exists():
            try:
                quadro_mapa = pd.read_csv(mapa, usecols=["municipio_cd", "municipio_ibge"])
                quadro = quadro.merge(quadro_mapa, on="municipio_cd", how="left")
            except (OSError, ValueError):
                pass
        try:
            from tse_ds import ibge

            pib = ibge.pib_municipal()
            if "municipio_ibge" in quadro and not pib.empty:
                quadro = quadro.merge(
                    pib[["municipio_ibge", "pib_total", "pib_per_capita"]],
                    on="municipio_ibge",
                    how="left",
                )
        except Exception:  # noqa: BLE001
            pass
        return quadro

    def perfil(self, ano: int) -> pd.DataFrame:
        if ano in self._perfil:
            return self._perfil[ano]
        caminho = PASTA_TABELAS / f"perfil_eleitorado_{ano}.parquet"
        quadro = pd.read_parquet(caminho) if caminho.exists() else pd.DataFrame()
        self._perfil[ano] = quadro
        return quadro

    def idade_ibge(self, ano: int) -> pd.DataFrame:
        if ano in self._idade:
            return self._idade[ano]
        caminho = PASTA_TABELAS / f"idade_tse_ibge_{ano}.csv"
        quadro = pd.read_csv(caminho) if caminho.exists() else pd.DataFrame()
        self._idade[ano] = quadro
        return quadro

    def zonas_municipio(self, escopo: Escopo, ano: int) -> pd.DataFrame:
        """Votos nominais por zona eleitoral do município (menor granularidade do TSE).

        Apenas lê o cache da UF — nunca extrai do zip aqui (extrairia o zip
        zonal inteiro e travaria a UI). Use `precisa_extrair_zonas` +
        `extrair_zonas` em um worker de segundo plano.
        """
        if escopo.tipo != TIPO_MUNICIPIO or not escopo.uf:
            return pd.DataFrame()
        chave = (escopo.uf, int(escopo.codigo), ano)
        if chave in self._cache_zonas:
            return self._cache_zonas[chave]
        from .zonas import cache_zonas_existe, zonas_municipio as _zonas_municipio

        if not cache_zonas_existe(ano, escopo.uf):
            return pd.DataFrame()
        quadro = _zonas_municipio(ano, escopo.uf, int(escopo.codigo))
        self._cache_zonas[chave] = quadro
        return quadro

    def precisa_extrair_zonas(self, escopo: Escopo, ano: int) -> bool:
        if escopo.tipo != TIPO_MUNICIPIO or not escopo.uf:
            return False
        from .zonas import cache_zonas_existe

        chave = (escopo.uf, int(escopo.codigo), ano)
        if chave in self._cache_zonas:
            return False
        return not cache_zonas_existe(ano, escopo.uf)

    def extrair_zonas(self, ano: int, uf: str) -> None:
        """Extrai o cache de zonas da UF do zip zonal (chamar em worker)."""
        from .zonas import votos_zona

        votos_zona(ano, uf)

    def secoes_municipio(
        self, escopo: Escopo, ano: int, cargo_cd: int | None = None
    ) -> pd.DataFrame:
        """Votos por seção eleitoral do município (uma linha por candidato; 2024/2026)."""
        if escopo.tipo != TIPO_MUNICIPIO or not escopo.uf:
            return pd.DataFrame()
        chave = (ano, escopo.uf, int(escopo.codigo), cargo_cd)
        if chave in self._cache_secoes:
            return self._cache_secoes[chave]
        from .secoes import caminho_cache as _caminho_cache
        from .secoes import secoes_municipio as _secoes_municipio

        caminho_uf = _caminho_cache(ano, escopo.uf)
        caminho_br = _caminho_cache(ano, "BR")
        if caminho_uf.exists():
            try:
                quadro = _secoes_municipio(ano, escopo.uf, int(escopo.codigo), cargo_cd)
            except Exception:  # noqa: BLE001
                quadro = pd.DataFrame()
        elif caminho_br.exists():
            # consolidado nacional (2026) também atende o município
            quadro = pd.read_parquet(caminho_br)
            quadro = quadro[
                (quadro["SG_UF"].astype(str).str.upper() == escopo.uf)
                & (quadro["CD_MUNICIPIO"] == int(escopo.codigo))
            ]
            if cargo_cd is not None:
                quadro = quadro[quadro["CD_CARGO"] == int(cargo_cd)]
            quadro = quadro.sort_values("votos", ascending=False).reset_index(drop=True)
        else:
            return pd.DataFrame()
        # só cacheia quando o parquet da fonte existe (extração pendente não pode
        # virar um "vazio definitivo" — o worker de extração ainda vai rodar)
        self._cache_secoes[chave] = quadro
        return quadro

    def _fontes_secoes(self, escopo: Escopo, ano: int) -> list[Path]:
        """Parquets de seções que atendem o escopo (consolidado BR quando existe)."""
        from .secoes import caminho_cache as _caminho_cache

        br = _caminho_cache(ano, "BR")
        if br.exists():
            return [br]
        if escopo.tipo == TIPO_BR:
            ufs = list(UF_REGIAO)
        elif escopo.tipo == TIPO_REGIAO:
            ufs = [uf for uf, regiao in UF_REGIAO.items() if regiao == escopo.codigo]
        else:
            ufs = [str(escopo.uf)] if escopo.uf else []
        return [
            caminho
            for uf in ufs
            if (caminho := _caminho_cache(ano, uf)).exists()
        ]

    def secoes_escopo(
        self, escopo: Escopo, ano: int, cargo_cd: int | None = None
    ) -> pd.DataFrame:
        """Seções mais votadas em escopos UF/região/Brasil (colunas: uf, municipio,
        NR_ZONA, NR_SECAO, votos) — agrega os caches por UF disponíveis.

        Em 2026 usa o consolidado nacional (secoes_{ano}_BR) quando existe; em
        2024 (sem consolidado) agrega os zips por UF já baixados.
        """
        if escopo.tipo == TIPO_MUNICIPIO:
            return self.totais_secoes_municipio(escopo, ano, cargo_cd)
        fontes = self._fontes_secoes(escopo, ano)
        chave = ("escopo", ano, escopo.tipo, str(escopo.codigo), cargo_cd, len(fontes))
        if chave in self._cache_secoes:
            return self._cache_secoes[chave]
        if not fontes:
            return pd.DataFrame()
        quadro = pd.concat(
            [pd.read_parquet(caminho) for caminho in fontes], ignore_index=True
        )
        if escopo.tipo == TIPO_UF and escopo.uf:
            quadro = quadro[quadro["SG_UF"].astype(str).str.upper() == escopo.uf]
        elif escopo.tipo == TIPO_REGIAO:
            ufs = {uf for uf, regiao in UF_REGIAO.items() if regiao == escopo.codigo}
            quadro = quadro[quadro["SG_UF"].astype(str).str.upper().isin(ufs)]
        if cargo_cd is not None:
            quadro = quadro[quadro["CD_CARGO"] == int(cargo_cd)]
        if quadro.empty:
            self._cache_secoes[chave] = quadro
            return quadro
        totais = (
            quadro.groupby(
                ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO"], observed=True
            )["votos"]
            .sum()
            .reset_index()
            .sort_values("votos", ascending=False)
            .reset_index(drop=True)
        )
        totais["SG_UF"] = totais["SG_UF"].astype(str).str.upper()
        mapa = self.mapa_municipios()[["uf", "municipio_cd", "municipio"]]
        totais = totais.merge(
            mapa,
            left_on=["SG_UF", "CD_MUNICIPIO"],
            right_on=["uf", "municipio_cd"],
            how="left",
        ).drop(columns=["uf", "municipio_cd"])
        totais["municipio"] = totais["municipio"].fillna(
            totais["CD_MUNICIPIO"].astype(str)
        )
        totais = totais.rename(columns={"SG_UF": "uf"})
        totais = totais[["uf", "municipio", "NR_ZONA", "NR_SECAO", "votos"]]
        self._cache_secoes[chave] = totais
        return totais

    def totais_secoes_municipio(
        self, escopo: Escopo, ano: int, cargo_cd: int | None = None
    ) -> pd.DataFrame:
        """Votos totais por seção (todos os votáveis somados)."""
        quadro = self.secoes_municipio(escopo, ano, cargo_cd)
        if quadro.empty:
            return quadro
        return (
            quadro.groupby(
                ["SG_UF", "CD_MUNICIPIO", "NR_ZONA", "NR_SECAO", "CD_CARGO"],
                observed=True,
            )["votos"]
            .sum()
            .reset_index()
            .sort_values("votos", ascending=False)
            .reset_index(drop=True)
        )

    def precisa_extrair_secoes(self, escopo: Escopo, ano: int) -> bool:
        from .secoes import caminho_cache as _caminho_cache
        from .secoes import precisa_extrair

        if _caminho_cache(ano, "BR").exists():
            return False  # consolidado cobre Brasil/região/UF/município
        if escopo.tipo in (TIPO_MUNICIPIO, TIPO_UF):
            return bool(escopo.uf) and precisa_extrair(ano, escopo.uf)
        # Brasil/região: em 2026 extrai o consolidado; em 2024 agrega UFs baixadas
        return ano == 2026 and precisa_extrair(ano, "BR")

    def eleitos(
        self, escopo: Escopo, ano: int, cargo_cd: int | None = None
    ) -> pd.DataFrame:
        """Candidatos eleitos relevantes ao escopo, com votos recebidos no escopo.

        Colunas: cargo, candidato, partido, votos_escopo, eleito_em, situacao.
        `eleito_em` traz o local da eleição ('MUNICIPIO/UF' para prefeito/vereador,
        'UF' para governador/senador/deputados, 'Brasil' para presidente) ou a
        pendência de 2º turno.
        Quando a eleição majoritária ainda depende de 2º turno (apenas turno 1
        disponível e ninguém marcado como ELEITO), devolve os 2 líderes com
        situacao='2º turno a disputar'.
        """
        chave = (escopo.tipo, escopo.codigo, ano, cargo_cd)
        if chave in self._cache_eleitos:
            return self._cache_eleitos[chave]
        quadro = self._calcular_eleitos(escopo, ano, cargo_cd)
        self._cache_eleitos[chave] = quadro
        return quadro

    def _calcular_eleitos(
        self, escopo: Escopo, ano: int, cargo_cd: int | None = None
    ) -> pd.DataFrame:
        votos = self.votos(ano)
        linhas: list[dict] = []
        ordem_escopo = ORDEM_UNIDADE[UNIDADE_ESCOPO[escopo.tipo]]
        cargos_iter = [cargo_cd] if cargo_cd is not None else self.cargos(ano)
        for cargo in cargos_iter:
            decisao, onde = self._escopo_decisao(escopo, ano, cargo)
            if decisao.empty:
                continue
            locais = _locais_eleicao(decisao, cargo)
            situacoes = (
                decisao["situacao"].astype(str).str.upper().str.strip()
                if "situacao" in decisao
                else pd.Series([""] * len(decisao), index=decisao.index)
            )
            pendente = False
            unidade_cargo = ORDEM_UNIDADE.get(UNIDADE_CARGO.get(cargo, "uf"), 1)
            if unidade_cargo < ordem_escopo:
                # escopo maior que a unidade da eleição (ex.: prefeito no Brasil):
                # lista os mais votados entre os eleitos dentro do escopo.
                eleitos = decisao[situacoes.str.startswith("ELEITO")].drop_duplicates(
                    "candidato_sq"
                )
                grupo = (
                    eleitos.groupby(
                        ["candidato_sq", "candidato_urna", "partido"],
                        observed=True,
                    )["votos"]
                    .sum()
                    .reset_index()
                    .sort_values("votos", ascending=False)
                )
                vencedores = grupo.head(TOP_ELEITOS_ESCOPO)
            elif cargo in (6, 7, 8, 13):
                vencedores = (
                    decisao[situacoes.str.startswith("ELEITO")]
                    .drop_duplicates("candidato_sq")
                )
                totais_cand = decisao.groupby("candidato_sq", observed=True)["votos"].sum()
                vencedores = (
                    vencedores.assign(
                        _total=vencedores["candidato_sq"].map(totais_cand)
                    )
                    .sort_values("_total", ascending=False)
                    .drop(columns=["_total"])
                )
            else:
                # majoritários (e senador: 3 vagas): maior total no turno decisivo
                grupo = (
                    decisao.groupby(
                        ["candidato_sq", "candidato_urna", "partido"],
                        observed=True,
                    )["votos"]
                    .sum()
                    .reset_index()
                    .sort_values("votos", ascending=False)
                )
                if cargo in (1, 3, 11) and not situacoes.str.startswith("ELEITO").any():
                    # só há turno 1 e ninguém foi eleito: 2º turno ainda vai ocorrer
                    pendente = True
                    vencedores = grupo.head(2)
                else:
                    vencedores = grupo.head(3 if cargo == 5 else 1)
            if vencedores.empty:
                continue
            base = votos[(votos["cargo_cd"] == cargo) & self.mascara(votos, escopo)]
            votos_escopo = base.groupby("candidato_sq", observed=True)["votos"].sum()
            # para escopo municipal, usar o nome do município do escopo como fallback
            municipio_escopo = ""
            if escopo.tipo == TIPO_MUNICIPIO and "/" in escopo.titulo:
                municipio_escopo = escopo.titulo.split("/")[0]
            for posicao, (_, vencedor) in enumerate(vencedores.iterrows(), start=1):
                sq = str(vencedor["candidato_sq"])
                local = (
                    locais.get(sq)
                    or ("Brasil" if cargo == 1 else (municipio_escopo or onde))
                )
                linhas.append(
                    {
                        "cargo_cd": cargo,
                        "cargo": self.nome_cargo(cargo),
                        "candidato": str(vencedor["candidato_urna"]),
                        "partido": str(vencedor["partido"]),
                        "votos_escopo": int(votos_escopo.get(sq, 0)),
                        "eleito_em": (
                            "aguarda 2º turno (líder do 1º turno)"
                            if pendente and posicao == 1
                            else (
                                "aguarda 2º turno (2º colocado no 1º turno)"
                                if pendente
                                else local
                            )
                        ),
                        "situacao": (
                            f"{posicao}º colocado no 1º turno"
                            if pendente
                            else (
                                f"ELEITO · {posicao}º mais votado {onde}"
                                if unidade_cargo < ordem_escopo
                                else "ELEITO"
                            )
                        ),
                    }
                )
        ordem = {c: i for i, c in enumerate(ORDEM_CARGO)}
        quadro = pd.DataFrame(linhas)
        if not quadro.empty:
            quadro["_o"] = quadro["cargo_cd"].map(ordem)
            quadro = quadro.sort_values(["_o", "votos_escopo"], ascending=[True, False])
            quadro = quadro.drop(columns=["_o"]).reset_index(drop=True)
        return quadro

    def _escopo_decisao(self, escopo: Escopo, ano: int, cargo_cd: int) -> tuple[pd.DataFrame, str]:
        """(votos onde a eleição foi decidida, rótulo do âmbito)."""
        votos = self.votos(ano)
        sub = votos[votos["cargo_cd"] == cargo_cd]
        if cargo_cd == 1:
            return sub, "no Brasil"
        if escopo.tipo == TIPO_MUNICIPIO:
            if cargo_cd in (11, 13):
                return sub[self.mascara(sub, escopo)], "no município"
            uf_sub = sub[sub["uf"].astype(str) == escopo.uf]
            return uf_sub, f"na UF ({escopo.uf})"
        if escopo.tipo == TIPO_UF:
            return sub[self.mascara(sub, escopo)], f"na UF ({escopo.codigo})"
        if escopo.tipo == TIPO_REGIAO:
            return sub[self.mascara(sub, escopo)], "na região"
        return sub, "no Brasil"

    # ------------------------------------------------------------- consultas
    def cargos(self, ano: int) -> list[int]:
        votos = self.votos(ano)
        disponiveis = set(int(c) for c in votos["cargo_cd"].unique())
        return [c for c in ORDEM_CARGO if c in disponiveis]

    @staticmethod
    def nome_cargo(cargo_cd: int) -> str:
        return NOMES_CARGO.get(cargo_cd, str(cargo_cd))

    def municipios(self, uf: str) -> pd.DataFrame:
        mapa = self.mapa_municipios()
        return mapa[mapa["uf"] == uf].sort_values("municipio")

    @staticmethod
    def mascara(quadro: pd.DataFrame, escopo: Escopo) -> pd.Series:
        if escopo.tipo == TIPO_BR:
            return quadro["uf"].astype(str) != "ZZ"
        if escopo.tipo == TIPO_REGIAO:
            ufs = {uf for uf, reg in UF_REGIAO.items() if reg == escopo.codigo}
            return quadro["uf"].astype(str).isin(ufs)
        if escopo.tipo == TIPO_UF:
            return quadro["uf"].astype(str) == escopo.codigo
        if "municipio_cd" in quadro:
            return quadro["municipio_cd"] == int(escopo.codigo)
        return quadro["uf"].astype(str) == escopo.uf

    @staticmethod
    def _uf_mapa(escopo: Escopo) -> str | None:
        """UF que concentra o mapa do escopo (municípios são desenhados dentro da UF)."""
        if escopo.tipo in (TIPO_UF, TIPO_MUNICIPIO):
            return escopo.codigo if escopo.tipo == TIPO_UF else escopo.uf
        return None

    def candidatos(self, escopo: Escopo, ano: int, cargo_cd: int) -> pd.DataFrame:
        """Candidatos de um cargo no escopo, com votos, percentual e informações cadastrais."""
        chave = (escopo.tipo, escopo.codigo, ano, cargo_cd)
        if chave in self._cache_candidatos:
            return self._cache_candidatos[chave]
        colunas = [
            "candidato_urna",
            "candidato",
            "partido",
            "partido_nome",
            "situacao",
            "votos",
            "pct",
            "municipio",
            "idade",
            "genero",
            "escolaridade",
            "candidato_nr",
        ]
        votos = self.votos(ano)
        sub = votos[(votos["cargo_cd"] == cargo_cd) & self.mascara(votos, escopo)]
        if sub.empty:
            vazio = pd.DataFrame(columns=colunas)
            self._cache_candidatos[chave] = vazio
            return vazio
        quadro = (
            sub.groupby(
                [
                    "candidato_sq",
                    "candidato_urna",
                    "partido",
                    "partido_nome",
                    "situacao",
                ],
                observed=True,
                dropna=False,
            )["votos"]
            .sum()
            .reset_index()
            .sort_values("votos", ascending=False)
        )
        total = int(quadro["votos"].sum())
        quadro["pct"] = (100.0 * quadro["votos"] / total).round(2) if total else 0.0

        if escopo.tipo == TIPO_MUNICIPIO:
            quadro["municipio"] = str(sub["municipio"].iloc[0])
            quadro["turno"] = int(sub["turno"].max())
            colunas = colunas + ["turno"]
        else:
            principal = (
                sub.sort_values("votos", ascending=False)
                .drop_duplicates("candidato_sq")
                .set_index("candidato_sq")["municipio"]
            )
            quadro = quadro.join(principal, on="candidato_sq")

        info = self.info_candidatos(ano)
        if not info.empty:
            extra = [c for c in COLUNAS_INFO if c in info.columns and c != "candidato_sq"]
            quadro = quadro.join(info[extra], on="candidato_sq")
        for coluna in ("candidato", "candidato_nr", "idade", "genero", "escolaridade"):
            if coluna not in quadro:
                quadro[coluna] = pd.NA
        if "municipio" not in quadro:
            quadro["municipio"] = pd.NA
        quadro = quadro[colunas].reset_index(drop=True)
        self._cache_candidatos[chave] = quadro
        return quadro

    def total_votos(self, escopo: Escopo, ano: int, cargo_cd: int) -> int:
        votos = self.votos(ano)
        sub = votos[(votos["cargo_cd"] == cargo_cd) & self.mascara(votos, escopo)]
        return int(sub["votos"].sum())

    # ------------------------------------------------------------ indicadores
    def indicadores(self, escopo: Escopo, ano: int) -> list[tuple[str, str, bool]]:
        """(id, rótulo, exige_cargo) dos indicadores válidos para o escopo/ano."""
        lista: list[tuple[str, str, bool]] = [
            ("votos", "Votos nominais", True),
            ("candidatos", "Nº de candidatos", True),
        ]
        municipios = escopo.tipo in (TIPO_UF, TIPO_MUNICIPIO)
        if not municipios and not self.apuracao(ano).empty:
            lista += [
                ("eleitores", "Eleitores aptos", False),
                ("comparecimento", "Comparecimento (%)", False),
            ]
        if ano == 2024 and municipios and not self.cruzamento().empty:
            lista += [
                ("eleitores", "Eleitores aptos", False),
                ("comparecimento", "Comparecimento (%)", False),
            ]
        if ano == 2024 and not self.cruzamento().empty:
            lista += [
                ("renda", "Renda per capita média", False),
                ("invalidos", "Votos brancos e nulos (%)", False),
            ]
            if not municipios:
                lista.append(("eleitores_pop", "Eleitores / população 16+ (%)", False))
        cruz = self.cruzamento()
        if "pib_per_capita" in cruz.columns and not cruz["pib_per_capita"].dropna().empty:
            lista.append(("pib", "PIB per capita (IBGE 2022)", False))
        return lista

    def serie(
        self, escopo: Escopo, ano: int, indicador: str, cargo_cd: int
    ) -> dict[str, float | None]:
        """Valor do indicador para cada filho do escopo (chave = código do filho)."""
        chave = (escopo.tipo, escopo.codigo, ano, indicador, cargo_cd)
        if chave in self._cache_serie:
            return self._cache_serie[chave]
        if indicador in ("votos", "candidatos"):
            valores = self._serie_cargos(escopo, ano, indicador, cargo_cd)
        else:
            valores = self._serie_geografica(escopo, ano, indicador)
        self._cache_serie[chave] = valores
        return valores

    def _serie_cargos(
        self, escopo: Escopo, ano: int, indicador: str, cargo_cd: int
    ) -> dict[str, float | None]:
        votos = self.votos(ano)
        sub = votos[votos["cargo_cd"] == cargo_cd]
        if escopo.tipo == TIPO_BR:
            mapa_regiao = pd.Series(
                {uf: reg for reg, ufs in REGIOES.items() for uf in ufs}
            )
            sub = sub.assign(_chave=sub["uf"].astype(str).map(mapa_regiao))
        elif escopo.tipo == TIPO_REGIAO:
            sub = sub[self.mascara(sub, escopo)].assign(_chave=sub["uf"].astype(str))
        else:
            uf = self._uf_mapa(escopo)
            sub = sub[sub["uf"].astype(str) == uf]
            sub = sub.assign(_chave=sub["municipio_cd"].astype(str))
        if indicador == "votos":
            serie = sub.groupby("_chave", observed=True)["votos"].sum()
        else:
            serie = (
                sub.groupby(["_chave", "candidato_sq"], observed=True)
                .size()
                .groupby(level=0)
                .nunique()
            )
        valores = {str(k): float(v) for k, v in serie.items() if k is not None}
        if escopo.tipo in (TIPO_UF, TIPO_MUNICIPIO):
            for codigo in self.municipios(uf or "")["municipio_cd"]:
                valores.setdefault(str(codigo), 0.0)
        return valores

    def _serie_geografica(
        self, escopo: Escopo, ano: int, indicador: str
    ) -> dict[str, float | None]:
        nivel = "uf" if escopo.tipo in (TIPO_BR, TIPO_REGIAO) else "municipio"

        if nivel == "uf":
            apuracao = self.apuracao(ano)
            if not apuracao.empty:
                if escopo.tipo == TIPO_BR:
                    grupo_col, dados = "regiao", apuracao
                else:
                    grupo_col, dados = "uf", apuracao[apuracao["regiao"] == escopo.codigo]
                if indicador == "eleitores":
                    serie = dados.groupby(grupo_col, observed=True)["eleitores"].sum()
                elif indicador == "comparecimento":
                    g = dados.groupby(grupo_col, observed=True)
                    serie = (
                        g["comparecimento"].sum() / g["eleitores"].sum().replace(0, pd.NA)
                    ) * 100.0
                else:
                    serie = pd.Series(dtype=float)
                if not serie.empty:
                    return {
                        str(k): (None if pd.isna(v) else float(v))
                        for k, v in serie.items()
                    }

            cruz = self.cruzamento()
            if cruz.empty or (ano != 2024 and indicador != "pib"):
                return {}
            if escopo.tipo == TIPO_BR:
                grupo_col, dados = "regiao", cruz
            else:
                grupo_col, dados = "uf", cruz[cruz["regiao"] == escopo.codigo]
            if dados.empty:
                return {}
            if indicador == "renda":
                serie = _media_ponderada(dados, grupo_col, "renda_media", "populacao")
            elif indicador == "pib" and "pib_per_capita" in dados.columns:
                serie = _media_ponderada(dados, grupo_col, "pib_per_capita", "populacao")
            elif indicador == "eleitores_pop":
                g = dados.groupby(grupo_col, observed=True)
                serie = (g["eleitores"].sum() / g["populacao"].sum().replace(0, pd.NA)) * 100.0
            elif indicador == "invalidos":
                g = dados.groupby(grupo_col, observed=True)
                brancos = g["votos_brancos"].sum()
                nulos = g["votos_nulos"].sum()
                validos = g["votos_validos"].sum()
                serie = 100.0 * (brancos + nulos) / (brancos + nulos + validos).replace(0, pd.NA)
            else:
                serie = pd.Series(dtype=float)
            if escopo.tipo == TIPO_UF:
                valor = serie.iloc[0] if len(serie) else None
                return {escopo.codigo: None if pd.isna(valor) else float(valor)}
            return {
                str(k): (None if pd.isna(v) else float(v)) for k, v in serie.items()
            }

        cruz = self.cruzamento()
        if cruz.empty or (ano != 2024 and indicador != "pib"):
            return {}
        uf = self._uf_mapa(escopo)
        dados = cruz[cruz["uf"] == uf] if uf else cruz
        colunas = {
            "eleitores": "eleitores",
            "comparecimento": "pct_comparecimento",
            "renda": "renda_media",
            "eleitores_pop": "pct_eleitores_populacao",
            "invalidos": "pct_invalidos",
            "pib": "pib_per_capita",
        }
        if indicador not in colunas:
            return {}
        serie = dados.set_index(dados["municipio_cd"].astype(str))[colunas[indicador]]
        valores: dict[str, float | None] = {
            k: (None if pd.isna(v) else float(v)) for k, v in serie.items()
        }
        if uf:
            for codigo in self.municipios(uf)["municipio_cd"]:
                valores.setdefault(str(codigo), None)
        return valores

    def resumo(self, escopo: Escopo, ano: int) -> list[tuple[str, str]]:
        """Pares (rótulo, valor) com os principais indicadores do escopo."""
        pares: list[tuple[str, str]] = []
        if escopo.tipo in (TIPO_BR, TIPO_REGIAO, TIPO_UF):
            apuracao = self.apuracao(ano)
            if not apuracao.empty:
                if escopo.tipo == TIPO_REGIAO:
                    ufs = [uf for uf, reg in UF_REGIAO.items() if reg == escopo.codigo]
                    apuracao = apuracao[apuracao["uf"].isin(ufs)]
                elif escopo.tipo == TIPO_UF:
                    apuracao = apuracao[apuracao["uf"] == escopo.codigo]
                eleitores = int(apuracao["eleitores"].sum())
                comparecimento = int(apuracao["comparecimento"].sum())
                abstencao = int(apuracao["abstencao"].sum())
                if eleitores:
                    pares.append(("Eleitores aptos", br(eleitores)))
                    pares.append(
                        (
                            "Comparecimento",
                            f"{br(comparecimento)} ({pct(100.0 * comparecimento / eleitores)})",
                        )
                    )
                    pares.append(
                        (
                            "Abstenção",
                            f"{br(abstencao)} ({pct(100.0 * abstencao / eleitores)})",
                        )
                    )
                if escopo.tipo == TIPO_REGIAO and len(apuracao) > 1:
                    maior = apuracao.loc[apuracao["pct_comparecimento"].idxmax()]
                    menor = apuracao.loc[apuracao["pct_comparecimento"].idxmin()]
                    pares.append(
                        (
                            "Maior / menor comparecimento",
                            f"{maior['uf']} ({pct(maior['pct_comparecimento'])}) / "
                            f"{menor['uf']} ({pct(menor['pct_comparecimento'])})",
                        )
                    )
        else:
            cruz = self.cruzamento()
            linha = (
                cruz[cruz["municipio_cd"] == int(escopo.codigo)]
                if not cruz.empty
                else cruz
            )
            if not linha.empty:
                dados = linha.iloc[0]
                pares += [
                    ("Eleitores aptos", br(dados["eleitores"])),
                    (
                        "Comparecimento",
                        f"{br(dados['comparecimento'])} ({pct(dados['pct_comparecimento'])})",
                    ),
                    ("População (Censo 2022)", br(dados["populacao"])),
                    ("Renda per capita média", moeda(dados["renda_media"])),
                    ("Votos brancos e nulos", pct(dados["pct_invalidos"])),
                ]
                if "pib_per_capita" in dados.index and pd.notna(dados.get("pib_per_capita")):
                    pares.append(
                        (
                            "PIB per capita (IBGE 2022)",
                            moeda(dados["pib_per_capita"]),
                        )
                    )
                if bool(dados.get("segundo_turno")):
                    final = self._resultado_segundo_turno(escopo, ano)
                    if final:
                        candidato, votos, pct_validos, adversario, votos_adv = final
                        pares.append(
                            (
                                "2º turno (resultado)",
                                f"{candidato} venceu {adversario} com {br(votos)} votos "
                                f"({pct(pct_validos)} dos válidos; adversário "
                                f"{br(votos_adv)})",
                            )
                        )
                    else:
                        pares.append(
                            (
                                "2º turno",
                                f"houve; líder do 1º turno: {dados['vencedor']} "
                                f"com {pct(dados['vencedor_pct'])} "
                                f"(margem {pct(dados['margem_pct'])})",
                            )
                        )
            else:
                pares.append(
                    ("Apuração municipal", "indisponível para este município no ano selecionado")
                )
        return pares

    def _resultado_segundo_turno(
        self, escopo: Escopo, ano: int
    ) -> tuple[str, float, float, str, float] | None:
        """(vencedor, votos, pct dos válidos, adversário, votos adversário) no 2º turno.

        Usa os dados zonais do TSE (turno 2) quando disponíveis; senão devolve None.
        """
        quadro = self.zonas_municipio(escopo, ano)
        if quadro.empty or 11 not in set(quadro["CD_CARGO"].dropna().astype(int)):
            return None
        turno2 = quadro[
            (quadro["CD_CARGO"] == 11) & (quadro["NR_TURNO"] == 2)
        ]
        if turno2.empty:
            return None
        totais = (
            turno2.groupby("NM_URNA_CANDIDATO", observed=True)["QT_VOTOS_NOMINAIS"]
            .sum()
            .sort_values(ascending=False)
        )
        if len(totais) < 2:
            return None
        candidato, votos = totais.index[0], float(totais.iloc[0])
        adversario, votos_adv = totais.index[1], float(totais.iloc[1])
        total_validos = float(totais.sum())
        if not total_validos:
            return None
        return candidato, votos, 100.0 * votos / total_validos, adversario, votos_adv

    # --------------------------------------------------------------- contexto
    def contexto(self, escopo: Escopo, ano: int, cargo_cd: int) -> str:
        """Texto compacto enviado ao modelo como contexto da região selecionada."""
        linhas: list[str] = [f"ESCOPO: {escopo.titulo} (eleições de {ano})", ""]
        linhas.append("## Indicadores do escopo")
        for rotulo, valor in self.resumo(escopo, ano):
            linhas.append(f"- {rotulo}: {valor}")

        cargos = self.cargos(ano)
        for cargo in cargos:
            total = self.total_votos(escopo, ano, cargo)
            if not total:
                continue
            candidatos = self.candidatos(escopo, ano, cargo)
            linhas.append("")
            if escopo.tipo == TIPO_MUNICIPIO:
                linhas.append(
                    f"## {self.nome_cargo(cargo)} — {len(candidatos)} candidatos "
                    f"com votos no município ({br(total)} votos, turno decisivo)"
                )
                limite = 200 if cargo in (11, 13) else 100
                for pos, (_, c) in enumerate(
                    candidatos.head(limite).iterrows(), start=1
                ):
                    situacao = str(c["situacao"]).strip()
                    marca = (
                        " · ELEITO"
                        if situacao.upper().startswith("ELEITO")
                        else ""
                    )
                    linhas.append(
                        f"{pos}. {c['candidato_urna']} ({c['partido']}): "
                        f"{br(c['votos'])} votos ({pct(c['pct'])}){marca}"
                    )
                if len(candidatos) > limite:
                    linhas.append(
                        f"(mais {len(candidatos) - limite} candidatos com votos "
                        "menores — use a tabela Candidatos do app para a lista completa)"
                    )
            else:
                top = candidatos.head(8)
                linhas.append(
                    f"## {self.nome_cargo(cargo)} — top 8 de {br(total)} votos no escopo"
                )
                for pos, (_, c) in enumerate(top.iterrows(), start=1):
                    extra = f" — {c['municipio']}"
                    situacao = str(c["situacao"]).strip()
                    linhas.append(
                        f"{pos}. {c['candidato_urna']} ({c['partido']}){extra}: "
                        f"{br(c['votos'])} votos ({pct(c['pct'])}) · {situacao}"
                    )

        alvo = cargo_cd if cargo_cd in cargos else (cargos[0] if cargos else None)
        if alvo and escopo.tipo == TIPO_MUNICIPIO:
            linhas.append("")
            linhas.extend(self._contexto_zonas(escopo, ano, alvo))
        if alvo and escopo.tipo != TIPO_MUNICIPIO:
            candidatos = self.candidatos(escopo, ano, alvo)
            if not candidatos.empty:
                partidos = (
                    candidatos.groupby("partido", observed=True)["votos"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(8)
                )
                total_partidos = int(partidos.sum())
                linhas.append("")
                linhas.append(
                    f"## Distribuição partidária — {self.nome_cargo(alvo)}"
                )
                for partido, votos in partidos.items():
                    linhas.append(
                        f"- {partido}: {br(votos)} ({pct(100.0 * votos / total_partidos)})"
                    )

        perfil = self.perfil(ano)
        if not perfil.empty and escopo.tipo != TIPO_MUNICIPIO:
            ufs = self._ufs_escopo(escopo, perfil["uf"].unique())
            perfil_escopo = perfil[perfil["uf"].isin(ufs)]
            if not perfil_escopo.empty:
                linhas.append("")
                linhas.append("## Perfil do eleitorado (TSE)")
                for dimensao in ("faixa_etaria", "genero", "grau_escolaridade"):
                    bloco = perfil_escopo[perfil_escopo["dimensao"] == dimensao]
                    if bloco.empty:
                        continue
                    totais = (
                        bloco.groupby("categoria", observed=True)["eleitores"]
                        .sum()
                        .sort_values(ascending=False)
                    )
                    geral = float(totais.sum())
                    if not geral:
                        continue
                    itens = ", ".join(
                        f"{cat} {pct(100.0 * v / geral, 0)}"
                        for cat, v in totais.head(5).items()
                    )
                    linhas.append(f"- {dimensao.replace('_', ' ')}: {itens}")

        idade = self.idade_ibge(ano)
        if not idade.empty and escopo.tipo != TIPO_MUNICIPIO:
            ufs = self._ufs_escopo(escopo, idade["uf"].unique())
            idade_escopo = idade[idade["uf"].isin(ufs) & (idade["uf"] != "BR")]
            if not idade_escopo.empty:
                por_faixa = idade_escopo.groupby("faixa", observed=True)[
                    ["eleitores", "populacao"]
                ].sum()
                por_faixa = por_faixa[por_faixa["populacao"] > 0]
                por_faixa["taxa"] = 100.0 * por_faixa["eleitores"] / por_faixa["populacao"]
                linhas.append("")
                linhas.append("## Eleitores x população 16+ por faixa etária (TSE x IBGE)")
                for faixa, linha in por_faixa.iterrows():
                    linhas.append(
                        f"- {faixa}: {pct(linha['taxa'])} da população residente na faixa"
                    )

        cruz = self.cruzamento()
        if not cruz.empty:
            sub = cruz[self.mascara(cruz, escopo)]
            if not sub.empty:
                linhas.append("")
                linhas.append("## Cruzamento TSE x IBGE (Censo 2022)")
                linhas.append(
                    f"- {len(sub):,} municípios; renda per capita média "
                    f"{moeda(sub['renda_media'].mean())} (mediana {moeda(sub['renda_media'].median())})"
                )
                if "pib_per_capita" in sub.columns and sub["pib_per_capita"].notna().any():
                    linhas.append(
                        f"- PIB per capita médio (IBGE 2022): "
                        f"{moeda(sub['pib_per_capita'].mean())} "
                        f"(mediana {moeda(sub['pib_per_capita'].median())})"
                    )
                faixa = (
                    sub.groupby("renda_faixa", observed=True)
                    .size()
                    .sort_values(ascending=False)
                )
                linhas.append(
                    "- Municípios por faixa de renda: "
                    + ", ".join(f"{nome}={int(qtd)}" for nome, qtd in faixa.items())
                )
                if len(sub) > 1:
                    correlacao = sub["renda_media"].corr(sub["pct_comparecimento"])
                    if pd.notna(correlacao):
                        linhas.append(
                            f"- Correlação renda × comparecimento: {correlacao:+.2f}"
                        )
                    if "pib_per_capita" in sub.columns:
                        corr_pib = sub["pib_per_capita"].corr(sub["pct_comparecimento"])
                        if pd.notna(corr_pib):
                            linhas.append(
                                f"- Correlação PIB per capita × comparecimento: {corr_pib:+.2f}"
                            )
        linhas.append("")
        return "\n".join(linhas)

    def _contexto_zonas(self, escopo: Escopo, ano: int, cargo_cd: int) -> list[str]:
        """Blocos de texto sobre as zonas eleitorais do município para o chat."""
        quadro = self.zonas_municipio(escopo, ano)
        if quadro.empty:
            linhas = [
                "## Zonas eleitorais",
                "- indisponíveis: baixe `votacao_candidato_munzona_{ano}.zip` em data/zip",
            ]
            linhas.extend(self._contexto_eleitos_secoes(escopo, ano, cargo_cd))
            return linhas
        total_zonas = int(quadro["NR_ZONA"].nunique())
        linhas = [
            f"## Zonas eleitorais de {escopo.titulo} ({ano})",
            "O TSE NÃO publica votação por bairro: a menor granularidade disponível "
            "é a ZONA ELEITORAL (e, em 2024 e 2026, a SEÇÃO ELEITORAL — veja o "
            "bloco de seções abaixo quando presente). Ao perguntarem sobre bairros, use a lista "
            "bairro→zona abaixo (aproximação via locais de votação geocodificados) "
            "e avise que é uma aproximação.",
            f"- Total de zonas eleitorais no município: {total_zonas}",
        ]
        do_cargo = quadro[quadro["CD_CARGO"] == cargo_cd]
        bairros = self.bairros_municipio(escopo)
        locais = self.locais_municipio(escopo)
        if do_cargo.empty:
            linhas.extend(self._contexto_eleitos_secoes(escopo, ano, cargo_cd))
            return linhas
        totais = (
            do_cargo.groupby("NR_ZONA", observed=True)["QT_VOTOS_NOMINAIS"]
            .sum()
            .sort_values(ascending=False)
        )
        linhas.append(
            f"### {self.nome_cargo(cargo_cd)} — zonas por votos nominais "
            "(top 3 candidatos em cada; máx. 12 zonas)"
        )
        for zona, total in totais.head(12).items():
            sub = do_cargo[do_cargo["NR_ZONA"] == zona]
            top = (
                sub.groupby(["NM_URNA_CANDIDATO", "SG_PARTIDO"], observed=True)[
                    "QT_VOTOS_NOMINAIS"
                ]
                .sum()
                .sort_values(ascending=False)
                .head(3)
            )
            detalhe = " · ".join(
                f"{pos}º {nome} ({partido}) {br(votos)}"
                for pos, ((nome, partido), votos) in enumerate(top.items(), start=1)
            )
            linhas.append(f"- Zona {int(zona)} ({br(total)} votos no cargo): {detalhe}")
        if bairros:
            linhas.append("")
            linhas.append(
                "### Bairros por zona eleitoral (aproximação OSM/geocoding; "
                "fonte: centros dos bairros vinculados ao local de votação mais próximo)"
            )
            for zona in sorted(bairros):
                nomes = ", ".join(bairros[zona][:18])
                if len(bairros[zona]) > 18:
                    nomes += f" … (+{len(bairros[zona]) - 18})"
                linhas.append(f"- Zona {zona}: {nomes}")
        elif locais:
            linhas.append("")
            linhas.append(
                "### Locais de votação por zona (referência 2026 — "
                "mapeamento de bairros ainda não gerado para este município)"
            )
            for zona in sorted(locais)[:12]:
                itens = " ; ".join(locais[zona][:2])
                linhas.append(f"- Zona {zona}: {itens}")
        linhas.extend(self._contexto_eleitos_secoes(escopo, ano, cargo_cd))
        return linhas

    def _contexto_eleitos_secoes(
        self, escopo: Escopo, ano: int, cargo_cd: int
    ) -> list[str]:
        """Blocos de eleitos e seções eleitorais (quando disponíveis)."""
        linhas: list[str] = []
        eleitos = self.eleitos(escopo, ano)
        if not eleitos.empty:
            linhas.append("")
            linhas.append(
                "### Eleitos (com os votos que receberam neste município)"
            )
            for linha in eleitos.itertuples():
                linhas.append(
                    f"- {linha.cargo}: {linha.candidato} ({linha.partido}) — "
                    f"{br(linha.votos_escopo)} votos no município · eleito {linha.eleito_em}"
                )
        secoes = self.secoes_municipio(escopo, ano, cargo_cd)
        if not secoes.empty:
            total_secoes = int(
                secoes[["NR_ZONA", "NR_SECAO"]].drop_duplicates().shape[0]
            )
            linhas.append("")
            linhas.append(
                f"## Seções eleitorais ({ano}) — {total_secoes} seções no município "
                f"({self.nome_cargo(cargo_cd)}): maiores (zona/seção/candidato)"
            )
            for linha in secoes.head(5).itertuples():
                linhas.append(
                    f"- Zona {int(linha.NR_ZONA)} / Seção {int(linha.NR_SECAO)} — "
                    f"{linha.NM_VOTAVEL}: {br(linha.votos)} votos"
                )
        return linhas

    def bairros_municipio(self, escopo: Escopo) -> dict[int, list[str]]:
        """{zona: [bairros]} aproximados (cache); vazio se ainda não mapeado."""
        if escopo.tipo != TIPO_MUNICIPIO or not escopo.uf:
            return {}
        from .bairros import bairros_por_zona

        try:
            return bairros_por_zona(
                escopo.uf, int(escopo.codigo), str(escopo.titulo).split("/")[0]
            )
        except Exception:  # noqa: BLE001
            return {}

    def locais_municipio(self, escopo: Escopo) -> dict[int, list[str]]:
        """{zona: [amostra de locais de votação]} a partir do zip de seções 2026."""
        if escopo.tipo != TIPO_MUNICIPIO or not escopo.uf:
            return {}
        from .bairros import locais_por_zona

        try:
            return locais_por_zona(escopo.uf, int(escopo.codigo))
        except Exception:  # noqa: BLE001
            return {}

    def precisa_mapear_bairros(self, escopo: Escopo) -> bool:
        """True quando o município ainda não tem o cache bairro→zona."""
        if escopo.tipo != TIPO_MUNICIPIO or not escopo.uf:
            return False
        from .config import PASTA_APP

        destino = PASTA_APP / "zonas" / f"bairros_{escopo.uf}_{int(escopo.codigo)}.parquet"
        return not destino.exists()

    @staticmethod
    def _ufs_escopo(escopo: Escopo, disponiveis) -> list[str]:
        disponiveis = {str(u) for u in disponiveis if str(u) != "BR"}
        if escopo.tipo == TIPO_BR:
            return sorted(disponiveis)
        if escopo.tipo == TIPO_REGIAO:
            return sorted(u for u in disponiveis if UF_REGIAO.get(u) == escopo.codigo)
        return [escopo.codigo] if escopo.codigo in disponiveis else []


def _media_ponderada(
    dados: pd.DataFrame, coluna_grupo: str, coluna_valor: str, coluna_peso: str
) -> pd.Series:
    g = dados.groupby(coluna_grupo, observed=True)
    numerador = g.apply(
        lambda bloco: (bloco[coluna_valor] * bloco[coluna_peso]).sum(),
        include_groups=False,
    )
    denominador = g[coluna_peso].sum().replace(0, pd.NA)
    return numerador / denominador
