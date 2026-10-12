from __future__ import annotations

import pandas as pd
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..store import TOP_ELEITOS_ESCOPO, br


class PainelEleitos(QWidget):
    """Painel de candidatos eleitos relevantes ao escopo corrente."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._titulo = QLabel("Candidatos eleitos")
        self._titulo.setStyleSheet("font-size:16px; font-weight:600;")
        self._nota = QLabel("")
        self._nota.setWordWrap(True)
        self._nota.setStyleSheet("color:#666666;")

        self._tabela = QTableWidget(0, 6)
        self._tabela.setHorizontalHeaderLabels(
            ["Cargo", "Eleito / líder", "Partido", "Votos no escopo", "Eleito em", "Situação"]
        )
        self._tabela.setAlternatingRowColors(True)
        self._tabela.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        cabecalho = self._tabela.horizontalHeader()
        # Cargo e Partido: ajustam ao conteúdo
        cabecalho.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        cabecalho.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        # Votos no escopo: ajustam ao conteúdo
        cabecalho.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        # Eleito / líder: estica para preencher espaço
        cabecalho.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Eleito em e Situação: interativos com largura mínima (scroll horizontal se necessário)
        cabecalho.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        cabecalho.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self._tabela.setColumnWidth(4, 220)
        self._tabela.setColumnWidth(5, 280)
        self._tabela.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        topo = QHBoxLayout()
        topo.addWidget(self._titulo, 1)
        layout.addLayout(topo)
        layout.addWidget(self._tabela, 1)
        layout.addWidget(self._nota)

    def atualizar_dados(self, dados: pd.DataFrame, escopo_titulo: str, ano: int) -> None:
        self._titulo.setText(f"Eleitos · {escopo_titulo} · {ano}")
        self._tabela.setRowCount(0)
        if dados is None or dados.empty:
            self._nota.setText(
                "Nenhum dado de eleição para este escopo/ano neste recorte."
            )
            return
        self._tabela.setRowCount(len(dados))
        for linha, registro in enumerate(dados.itertuples()):
            situacao = str(getattr(registro, "situacao", "") or "")
            pendente = "2º turno" in situacao or "aguarda" in str(registro.eleito_em)
            itens = [
                str(registro.cargo),
                str(registro.candidato),
                str(registro.partido),
                br(registro.votos_escopo),
                str(registro.eleito_em),
                situacao,
            ]
            for coluna, texto in enumerate(itens):
                item = QTableWidgetItem(texto)
                item.setToolTip(texto)
                if coluna == 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if pendente:
                    item.setForeground(QColor("#b45309"))
                self._tabela.setItem(linha, coluna, item)
        tem_pendente = any(
            "2º turno" in str(r.situacao) or "aguarda" in str(r.eleito_em)
            for r in dados.itertuples()
        )
        nota = (
            "Cargos majoritários: maior total de votos no turno decisivo "
            "(funciona com 2º turno encerrado). Proporcionais (vereador, senador, "
            "deputados): situação 'ELEITO' do TSE (senador: 3 maiores). "
            "'Votos no escopo' = votos que o candidato recebeu na unidade selecionada; "
            "'Eleito em' = município/UF, UF ou Brasil em que foi eleito. "
            "Quando o escopo é maior que a unidade da eleição (ex.: prefeito no Brasil, "
            f"governador na região), a lista traz os {TOP_ELEITOS_ESCOPO} eleitos mais "
            "votados dentro do escopo."
        )
        if tem_pendente:
            nota += (
                "  ·  Linhas em amarelo: eleições que ainda dependem de 2º turno "
                "(apenas o 1º turno está disponível) — mostramos os 2 líderes."
            )
        self._nota.setText(nota)
