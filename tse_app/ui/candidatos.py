from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

LIMITE_LINHAS = 1000

COLUNAS = [
    ("#", 44),
    ("Candidato", 190),
    ("Cargo", 130),
    ("Nome completo", 220),
    ("Partido", 150),
    ("Votos", 95),
    ("%", 70),
    ("Situação", 130),
    ("Município", 160),
    ("Nº", 60),
    ("Idade", 55),
    ("Gênero", 95),
    ("Escolaridade", 180),
]


class _ItemOrdenavel(QTableWidgetItem):
    """Item que ordena numericamente quando o valor numérico está em UserRole."""

    def __lt__(self, outro: QTableWidgetItem) -> bool:
        a = self.data(Qt.ItemDataRole.UserRole)
        b = outro.data(Qt.ItemDataRole.UserRole)
        if a is not None and b is not None:
            try:
                return float(a) < float(b)
            except (TypeError, ValueError):
                pass
        return self.text() < outro.text()


class TabelaCandidatos(QWidget):
    """Lista de candidatos do cargo/escopo corrente com filtros e ordenação."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dados = pd.DataFrame()
        self.ao_trocar_todos_cargos = None  # callable definido pela janela

        self._titulo = QLabel("Selecione um escopo para ver os candidatos")
        self._titulo.setWordWrap(True)
        self._chk_todos = QCheckBox("Todos os cargos do ano")
        self._chk_todos.setToolTip(
            "Lista prefeito, vereadores, deputados, senadores, governadores e "
            "presidentes de uma vez (escopo municipal)"
        )
        self._chk_todos.toggled.connect(self._trocar_todos)
        self._chk_todos.setVisible(False)
        self._busca = QLineEdit()
        self._busca.setPlaceholderText(
            "Filtrar por candidato, partido ou município…"
        )
        self._busca.textChanged.connect(self._aplicar)
        self._contagem = QLabel("")

        topo = QHBoxLayout()
        topo.addWidget(self._chk_todos)
        topo.addStretch(1)

        self._tabela = QTableWidget(0, len(COLUNAS))
        self._tabela.setHorizontalHeaderLabels([nome for nome, _ in COLUNAS])
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setAlternatingRowColors(True)
        self._tabela.verticalHeader().setVisible(False)
        cabecalho = self._tabela.horizontalHeader()
        cabecalho.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cabecalho.setStretchLastSection(True)
        for indice, (_, largura) in enumerate(COLUNAS):
            self._tabela.setColumnWidth(indice, largura)
        self._tabela.setSortingEnabled(True)

        rodape = QWidget()
        rodape_l = QVBoxLayout(rodape)
        rodape_l.setContentsMargins(0, 0, 0, 0)
        rodape_l.addWidget(self._contagem)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._titulo)
        layout.addLayout(topo)
        layout.addWidget(self._busca)
        layout.addWidget(self._tabela, 1)
        layout.addWidget(rodape)

    @property
    def todos_cargos(self) -> bool:
        return self._chk_todos.isChecked()

    def definir_todos_cargos_disponivel(self, visivel: bool) -> None:
        self._chk_todos.setVisible(visivel)
        if not visivel and self._chk_todos.isChecked():
            self._chk_todos.blockSignals(True)
            self._chk_todos.setChecked(False)
            self._chk_todos.blockSignals(False)

    def _trocar_todos(self, _marcado: bool) -> None:
        if self.ao_trocar_todos_cargos is not None:
            self.ao_trocar_todos_cargos()

    def atualizar(self, dados: pd.DataFrame, titulo: str) -> None:
        self._dados = dados.copy() if dados is not None else pd.DataFrame()
        self._titulo.setText(titulo)
        self._busca.clear()
        self._aplicar()

    def _aplicar(self) -> None:
        quadro = self._dados
        termo = self._busca.text().strip().upper()
        if termo and not quadro.empty:
            alvo = quadro[
                [
                    c
                    for c in ("candidato_urna", "candidato", "partido", "municipio")
                    if c in quadro.columns
                ]
            ].astype(str)
            mascara = alvo.apply(
                lambda coluna: coluna.str.upper().str.contains(termo, na=False)
            ).any(axis=1)
            quadro = quadro[mascara]

        self._tabela.setSortingEnabled(False)
        self._tabela.setRowCount(0)
        if quadro.empty:
            self._contagem.setText("nenhum candidato encontrado")
            return

        visivel = quadro.head(LIMITE_LINHAS)
        self._tabela.setRowCount(len(visivel))
        for linha, (_, registro) in enumerate(visivel.iterrows()):
            valores = [
                str(linha + 1),
                str(registro.get("candidato_urna") or ""),
                str(registro.get("cargo_nome") or registro.get("cargo") or ""),
                str(registro.get("candidato") or ""),
                f"{registro.get('partido') or ''}",
                f"{int(registro.get('votos') or 0):,}".replace(",", "."),
                f"{float(registro.get('pct') or 0):.2f}".replace(".", ","),
                str(registro.get("situacao") or ""),
                str(registro.get("municipio") or ""),
                str(registro.get("candidato_nr") or ""),
                _idade(registro.get("idade")),
                str(registro.get("genero") or ""),
                str(registro.get("escolaridade") or ""),
            ]
            for coluna, valor in enumerate(valores):
                item = _ItemOrdenavel(valor)
                if coluna in (0, 5, 6, 9, 10):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                    item.setData(Qt.ItemDataRole.UserRole, _numerico(valores, coluna))
                self._tabela.setItem(linha, coluna, item)
        self._tabela.setSortingEnabled(True)
        total = len(quadro)
        texto = f"{total:,} candidato{'s' if total != 1 else ''}".replace(",", ".")
        if total > LIMITE_LINHAS:
            texto += f" · exibindo os {LIMITE_LINHAS:,} primeiros".replace(",", ".")
        if "turno" in quadro.columns and len(quadro):
            texto += f" · votos do {int(quadro['turno'].iloc[0])}º turno"
        self._contagem.setText(texto)


def _idade(valor) -> str:
    try:
        return str(int(valor))
    except (TypeError, ValueError):
        return "—"


def _numerico(valores: list[str], coluna: int):
    texto = valores[coluna].replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0
