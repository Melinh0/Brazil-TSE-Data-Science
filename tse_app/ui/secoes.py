from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..store import FonteDados, br
from ..escopo import TIPO_MUNICIPIO, TIPO_UF, Escopo
from ..secoes import status_pendencia

LIMITE_LINHAS = 3000
ROTULOS_MUNICIPIO = ["Zona", "Seção", "Candidato", "Partido", "Votos", "% da seção"]
ROTULOS_ESCOPO = ["UF", "Município", "Zona", "Seção", "Votos", "% do escopo"]


class PainelSecoes(QWidget):
    """Votos por seção eleitoral (eleições 2024/2026).

    No município mostra a linha de cada candidato por seção; em UF/região/Brasil
    mostra as seções mais votadas do escopo (agregando os caches por UF).
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dados = pd.DataFrame()
        self._ano = 2026
        self._modo_nacional = False
        self._titulo = QLabel("Votos por seção eleitoral")
        self._titulo.setStyleSheet("font-size:16px; font-weight:600;")
        self._nota = QLabel("")
        self._nota.setWordWrap(True)
        self._nota.setStyleSheet("color:#666666;")

        self._combo_zona = QComboBox()
        self._combo_zona.addItem("Todas as zonas", None)
        self._combo_zona.currentIndexChanged.connect(self._preencher)
        self._combo_zona.setVisible(False)

        topo = QHBoxLayout()
        topo.addWidget(self._titulo, 1)
        topo.addWidget(QLabel("Zona:"))
        topo.addWidget(self._combo_zona)

        self._tabela = QTableWidget(0, 6)
        self._tabela.setHorizontalHeaderLabels(ROTULOS_MUNICIPIO)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cabecalho = self._tabela.horizontalHeader()
        cabecalho.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for coluna in (0, 1, 4, 5):
            cabecalho.setSectionResizeMode(coluna, QHeaderView.ResizeMode.ResizeToContents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(topo)
        layout.addWidget(self._tabela, 1)
        layout.addWidget(self._nota)
        self._modo_vazio(True)

    def _modo_vazio(self, vazio: bool) -> None:
        """Sem dados, esconde a tabela e destaca a mensagem no centro do painel."""
        self._tabela.setVisible(not vazio)
        self._nota.setVisible(True)
        self._nota.setStyleSheet(
            "color:#444444; font-size:14px; padding:24px;"
            if vazio
            else "color:#666666;"
        )

    def atualizar(
        self, fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int | None
    ) -> None:
        self._ano = ano
        self._titulo.setText(
            f"Votos por seção eleitoral · {escopo.titulo} · {ano}"
        )
        self._dados = pd.DataFrame()
        self._modo_nacional = escopo.tipo != TIPO_MUNICIPIO
        self._combo_zona.setVisible(False)
        self._combo_zona.blockSignals(True)
        self._combo_zona.clear()
        self._combo_zona.addItem("Todas as zonas", None)
        self._combo_zona.blockSignals(False)
        self._tabela.setRowCount(0)
        if ano not in (2024, 2026) or cargo_cd is None:
            self._modo_vazio(True)
            self._nota.setText(
                "Seções eleitorais disponíveis nas eleições de 2024 (municipais) "
                "e 2026 (gerais). Selecione o ano 2024 ou 2026 — no município a "
                "tabela traz os votos de cada candidato; em UF, região ou Brasil, "
                "as seções mais votadas do escopo."
            )
            return
        if self._modo_nacional:
            self._atualizar_escopo(fonte, escopo, ano, cargo_cd)
            return
        self._tabela.setHorizontalHeaderLabels(ROTULOS_MUNICIPIO)
        secoes = fonte.secoes_municipio(escopo, ano, cargo_cd)
        if secoes.empty:
            self._modo_vazio(True)
            self._nota.setText(status_pendencia(ano, escopo.uf))
            return
        totais = (
            secoes.groupby(["NR_ZONA", "NR_SECAO"], observed=True)["votos"]
            .sum()
            .rename("total_secao")
        )
        quadro = secoes.merge(
            totais, left_on=["NR_ZONA", "NR_SECAO"], right_index=True
        )
        try:
            votos = fonte.votos(ano)
            partidos = (
                votos[votos["cargo_cd"] == cargo_cd]
                .drop_duplicates("candidato_urna")
                .set_index("candidato_urna")["partido"]
                .astype(str)
            )
            quadro["partido"] = quadro["NM_VOTAVEL"].map(partidos).fillna("—")
        except Exception:  # noqa: BLE001
            quadro["partido"] = "—"
        quadro = quadro.sort_values(
            ["NR_ZONA", "NR_SECAO", "votos"], ascending=[True, True, False]
        )
        self._dados = quadro
        zonas = sorted(int(z) for z in quadro["NR_ZONA"].dropna().unique())
        if len(zonas) > 1:
            self._combo_zona.blockSignals(True)
            for zona in zonas:
                self._combo_zona.addItem(f"Zona {zona}", zona)
            self._combo_zona.blockSignals(False)
            self._combo_zona.setVisible(True)
        self._modo_vazio(False)
        self._preencher()

    def _atualizar_escopo(
        self, fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int | None
    ) -> None:
        """Visão UF/região/Brasil: seções mais votadas agregando os caches por UF."""
        self._tabela.setHorizontalHeaderLabels(ROTULOS_ESCOPO)
        quadro = fonte.secoes_escopo(escopo, ano, cargo_cd)
        if quadro.empty:
            self._modo_vazio(True)
            if ano == 2024 and escopo.tipo != TIPO_UF:
                self._nota.setText(status_pendencia(ano, "BR"))
            else:
                self._nota.setText(status_pendencia(ano, str(escopo.uf or "BR")))
            return
        self._dados = quadro
        # filtro de zona só no modo UF (os números de zona se repetem entre UFs)
        zonas = (
            sorted(int(z) for z in quadro["NR_ZONA"].dropna().unique())
            if escopo.tipo == TIPO_UF
            else []
        )
        if len(zonas) > 1:
            self._combo_zona.blockSignals(True)
            for zona in zonas:
                self._combo_zona.addItem(f"Zona {zona}", zona)
            self._combo_zona.blockSignals(False)
            self._combo_zona.setVisible(True)
        self._modo_vazio(False)
        self._preencher()

    @staticmethod
    def _inteiro(valor) -> str:
        """str(int(valor)) tolerante a NA/float (evita quebrar o preenchimento)."""
        try:
            return str(int(valor))
        except (TypeError, ValueError):
            return "—"

    def _preencher(self) -> None:
        quadro = self._dados
        self._tabela.setRowCount(0)
        if quadro.empty:
            return
        zona = self._combo_zona.currentData()
        if zona is not None:
            quadro = quadro[quadro["NR_ZONA"] == int(zona)]
        total_linhas = len(quadro)
        visivel = quadro.head(LIMITE_LINHAS)
        self._tabela.setRowCount(len(visivel))
        if self._modo_nacional:
            self._preencher_escopo(visivel, quadro, total_linhas)
        else:
            self._preencher_municipio(visivel, quadro, total_linhas)

    def _preencher_municipio(self, visivel: pd.DataFrame, quadro: pd.DataFrame, total_linhas: int) -> None:
        for indice, linha in enumerate(visivel.itertuples()):
            pct_secao = (
                100.0 * linha.votos / linha.total_secao if linha.total_secao else 0.0
            )
            itens = [
                self._inteiro(linha.NR_ZONA),
                self._inteiro(linha.NR_SECAO),
                str(linha.NM_VOTAVEL),
                str(linha.partido),
                br(linha.votos),
                f"{pct_secao:.1f}%",
            ]
            for coluna, texto in enumerate(itens):
                item = QTableWidgetItem(texto)
                if coluna in (0, 1, 4, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._tabela.setItem(indice, coluna, item)
        total_secoes = int(
            self._dados[["NR_ZONA", "NR_SECAO"]].drop_duplicates().shape[0]
        )
        texto = (
            f"{len(self._dados):,} linhas · {total_secoes} seções · "
            "voto nominal de cada candidato em cada seção eleitoral "
            f"(turno decisivo; fonte: TSE votação por seção {self._ano})."
        )
        if total_linhas > LIMITE_LINHAS:
            texto += (
                f" Exibindo as primeiras {LIMITE_LINHAS:,} linhas — use o filtro "
                "de zona ou os cabeçalhos da tabela para reordenar."
            )
        self._nota.setText(texto)

    def _preencher_escopo(self, visivel: pd.DataFrame, quadro: pd.DataFrame, total_linhas: int) -> None:
        total_escopo = float(quadro["votos"].sum())
        for indice, linha in enumerate(visivel.itertuples()):
            pct = 100.0 * linha.votos / total_escopo if total_escopo else 0.0
            itens = [
                str(linha.uf),
                str(linha.municipio),
                self._inteiro(linha.NR_ZONA),
                self._inteiro(linha.NR_SECAO),
                br(linha.votos),
                f"{pct:.1f}%",
            ]
            for coluna, texto in enumerate(itens):
                item = QTableWidgetItem(texto)
                if coluna >= 2:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._tabela.setItem(indice, coluna, item)
        total_secoes = int(
            quadro[["uf", "NR_ZONA", "NR_SECAO"]].drop_duplicates().shape[0]
        )
        ufs = sorted(set(str(u) for u in quadro["uf"]))
        texto = (
            f"Seções mais votadas no escopo: {len(quadro):,} seções em "
            f"{len(ufs)} UF{'s' if len(ufs) != 1 else ''} ({', '.join(ufs[:8])}"
            f"{', …' if len(ufs) > 8 else ''}) · turno decisivo · "
            f"fonte: TSE votação por seção {self._ano}."
        )
        if len(ufs) < 27:
            texto += (
                " Caches disponíveis apenas para as UFs listadas — baixe as "
                "demais abrindo um município/UF de cada ano."
            )
        if total_linhas > LIMITE_LINHAS:
            texto += (
                f" Exibindo as {LIMITE_LINHAS:,} mais votadas — use o filtro "
                "de zona ou os cabeçalhos da tabela para reordenar."
            )
        self._nota.setText(texto)
