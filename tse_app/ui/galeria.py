from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..config import PASTA_FIGURAS


class Visualizador(QWidget):
    """Visualizador nítido dos PNGs: ajuste automático, 100% e zoom manual."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._original: QPixmap | None = None
        self._modo = "ajustar"  # "ajustar" ou "manual"
        self._fator = 1.0

        self._rotulo = QLabel("Selecione um gráfico na lista")
        self._rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rotulo.setStyleSheet("color:#666666; font-size:13px;")
        self._area = QScrollArea()
        self._area.setWidgetResizable(False)
        self._area.setWidget(self._rotulo)
        self._area.viewport().installEventFilter(self)
        self._area.installEventFilter(self)

        self._btn_ajustar = QPushButton("Ajustar à janela")
        self._btn_ajustar.clicked.connect(lambda: self._definir_modo("ajustar"))
        self._btn_100 = QPushButton("100%")
        self._btn_100.clicked.connect(lambda: self._definir_modo("manual", 1.0))
        self._btn_menos = QPushButton("−")
        self._btn_menos.setFixedWidth(32)
        self._btn_menos.clicked.connect(lambda: self._zoom(0.8))
        self._btn_mais = QPushButton("+")
        self._btn_mais.setFixedWidth(32)
        self._btn_mais.clicked.connect(lambda: self._zoom(1.25))
        self._zlabel = QLabel("")
        self._zlabel.setStyleSheet("color:#555555;")

        topo = QHBoxLayout()
        topo.addWidget(self._btn_ajustar)
        topo.addWidget(self._btn_100)
        topo.addWidget(self._btn_menos)
        topo.addWidget(self._btn_mais)
        topo.addWidget(self._zlabel)
        topo.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(topo)
        layout.addWidget(self._area, 1)

    # ------------------------------------------------------------ estado
    def mostrar(self, caminho: Path | None) -> None:
        if caminho is None or not caminho.exists():
            self._original = None
            self._rotulo.setPixmap(QPixmap())
            self._rotulo.setText("Selecione um gráfico na lista")
            self._zlabel.setText("")
            return
        self._original = QPixmap(str(caminho))
        self._modo = "ajustar"
        self._fator = 1.0
        self._atualizar()

    def _definir_modo(self, modo: str, fator: float | None = None) -> None:
        self._modo = modo
        if fator is not None:
            self._fator = fator
        self._atualizar()

    def _zoom(self, multiplicador: float) -> None:
        if self._original is None:
            return
        self._modo = "manual"
        self._fator = max(0.1, min(8.0, self._fator * multiplicador))
        self._atualizar()

    def eventFilter(self, objeto: QObject, evento: QEvent) -> bool:  # noqa: N802
        from PySide6.QtGui import QWheelEvent

        if isinstance(evento, QWheelEvent) and objeto is self._area:
            if evento.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._zoom(1.15 if evento.angleDelta().y() > 0 else 0.87)
                return True
            return False
        if (
            objeto is self._area.viewport()
            and evento.type() == QEvent.Type.Resize
            and self._modo == "ajustar"
        ):
            self._atualizar()
        return super().eventFilter(objeto, evento)

    # ------------------------------------------------------------ desenho
    def _atualizar(self) -> None:
        if self._original is None or self._original.isNull():
            return
        dpr = self.devicePixelRatioF()
        largura_px = self._original.width()
        altura_px = self._original.height()

        if self._modo == "ajustar":
            alvo = self._area.viewport().size()
            if alvo.width() > 0 and alvo.height() > 0:
                escala = min(
                    1.0,
                    min(
                        alvo.width() * dpr / largura_px,
                        alvo.height() * dpr / altura_px,
                    ),
                )
            else:
                escala = 1.0
        else:
            escala = self._fator

        novo = self._original
        if abs(escala - 1.0) > 0.001:
            novo = self._original.scaled(
                max(1, int(largura_px * escala)),
                max(1, int(altura_px * escala)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        novo.setDevicePixelRatio(dpr)
        self._rotulo.setStyleSheet("")
        self._rotulo.setPixmap(novo)
        self._rotulo.resize(int(novo.width() / dpr), int(novo.height() / dpr))
        self._zlabel.setText(f"{escala * 100:.0f}%")


class GaleriaGraficos(QWidget):
    """Galeria dos PNGs gerados pelo pipeline (outputs/figuras)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._ano: int | None = None

        self._lista = QListWidget()
        self._lista.setAlternatingRowColors(True)
        self._lista.currentItemChanged.connect(self._selecionar)
        self._lista.itemDoubleClicked.connect(self._abrir_tela_cheia)
        self._visualizador = Visualizador()

        self._abrir = QPushButton("Abrir arquivo…")
        self._abrir.clicked.connect(self._abrir_arquivo)
        self._tela_cheia = QPushButton("Tela cheia")
        self._tela_cheia.setToolTip("Expande o gráfico para a janela inteira (Esc volta)")
        self._tela_cheia.clicked.connect(self._alternar_tela_cheia)
        self._btn_ant = QPushButton("◀")
        self._btn_ant.setFixedWidth(32)
        self._btn_ant.setToolTip("Gráfico anterior")
        self._btn_ant.clicked.connect(lambda: self._mover(-1))
        self._btn_prox = QPushButton("▶")
        self._btn_prox.setFixedWidth(32)
        self._btn_prox.setToolTip("Próximo gráfico")
        self._btn_prox.clicked.connect(lambda: self._mover(1))
        self._posicao = QLabel("–/–")
        self._posicao.setStyleSheet("color:#666666; padding:0 6px;")
        topo = QHBoxLayout()
        topo.addWidget(self._abrir)
        topo.addWidget(self._tela_cheia)
        topo.addStretch(1)
        topo.addWidget(self._btn_ant)
        topo.addWidget(self._posicao)
        topo.addWidget(self._btn_prox)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.addWidget(self._lista)
        divisor.addWidget(self._visualizador)
        divisor.setSizes([230, 920])
        divisor.setStretchFactor(0, 0)
        divisor.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(topo)
        layout.addWidget(divisor, 1)

    def definir_ano(self, ano: int) -> None:
        """Lista apenas os gráficos nacionais do pipeline (outputs/figuras)."""
        self._ano = ano
        self._lista.clear()
        if not PASTA_FIGURAS.exists():
            return
        arquivos = sorted(PASTA_FIGURAS.glob(f"{ano}_*.png"))
        for caminho in arquivos:
            item = QListWidgetItem(caminho.stem.replace(f"{ano}_", "").replace("_", " "))
            item.setData(Qt.ItemDataRole.UserRole, str(caminho))
            item.setToolTip(caminho.name)
            self._lista.addItem(item)
        if not arquivos:
            item = QListWidgetItem(
                "nenhum gráfico gerado — rode: python main.py graficos"
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._lista.addItem(item)

    def definir_escopo(self, escopo, fonte, ano: int, cargo_cd: int | None, caminhos=None) -> None:
        """Gráficos do escopo no topo (primeiro auto-selecionado) + nacionais abaixo.

        `caminhos` = PNGs já prontos (a janela lista em `listar_escopo` e gera
        os faltantes em um worker — aqui nunca renderizamos figuras).
        """
        self._ano = ano
        selecionado = None
        atual = self._lista.currentItem()
        if atual is not None:
            selecionado = atual.data(Qt.ItemDataRole.UserRole)
        self._lista.blockSignals(True)
        self._lista.clear()
        alvo = None
        try:
            if caminhos is None:
                from ..graficos_locais import listar_escopo

                caminhos, _faltantes = listar_escopo(fonte, escopo, ano, cargo_cd)
            primeiro = None
            restaurar = None
            if caminhos:
                separador = QListWidgetItem(
                    f"── gráficos de {escopo.titulo} · {ano} ──"
                )
                separador.setFlags(Qt.ItemFlag.NoItemFlags)
                self._lista.addItem(separador)
                for caminho in caminhos:
                    item = QListWidgetItem(
                        "★ " + caminho.stem.split("_", 3)[-1].replace("_", " ")
                    )
                    item.setData(Qt.ItemDataRole.UserRole, str(caminho))
                    item.setToolTip(caminho.name)
                    self._lista.addItem(item)
                    if primeiro is None:
                        primeiro = item
                    if selecionado and str(caminho) == selecionado:
                        restaurar = item
            separador_nac = QListWidgetItem("── gráficos nacionais (pipeline) ──")
            separador_nac.setFlags(Qt.ItemFlag.NoItemFlags)
            self._lista.addItem(separador_nac)
            if PASTA_FIGURAS.exists():
                for caminho in sorted(PASTA_FIGURAS.glob(f"{ano}_*.png")):
                    item = QListWidgetItem(
                        caminho.stem.replace(f"{ano}_", "").replace("_", " ")
                    )
                    item.setData(Qt.ItemDataRole.UserRole, str(caminho))
                    item.setToolTip(caminho.name)
                    self._lista.addItem(item)
                    if selecionado and str(caminho) == selecionado:
                        restaurar = item
            alvo = restaurar or primeiro
            if alvo is None and self._lista.count() > 2:
                alvo = self._lista.item(2)
        finally:
            self._lista.blockSignals(False)
        if alvo is not None:
            self._lista.setCurrentItem(alvo)
        else:
            self._selecionar(None, None)

    def _selecionar(self, atual: QListWidgetItem | None, _anterior) -> None:
        caminho = atual.data(Qt.ItemDataRole.UserRole) if atual else None
        self._visualizador.mostrar(Path(caminho) if caminho else None)
        self._atualizar_posicao()

    def _itens_com_dados(self) -> list[int]:
        return [
            i
            for i in range(self._lista.count())
            if self._lista.item(i).data(Qt.ItemDataRole.UserRole)
        ]

    def _atualizar_posicao(self) -> None:
        itens = self._itens_com_dados()
        atual = self._lista.currentRow()
        posicao = itens.index(atual) + 1 if atual in itens else 0
        self._posicao.setText(f"{posicao}/{len(itens)}" if itens else "–/–")

    def _mover(self, delta: int) -> None:
        itens = self._itens_com_dados()
        if not itens:
            return
        atual = self._lista.currentRow()
        posicao = itens.index(atual) if atual in itens else 0
        novo = min(max(posicao + delta, 0), len(itens) - 1)
        self._lista.setCurrentRow(itens[novo])

    def _alternar_tela_cheia(self) -> None:
        janela = self.window()
        if janela is not None:
            if janela.isFullScreen():
                janela.showNormal()
            else:
                janela.showFullScreen()

    def _abrir_tela_cheia(self, _item: QListWidgetItem) -> None:
        janela = self.window()
        if janela is not None:
            janela.showFullScreen()

    def _abrir_arquivo(self) -> None:
        atual = self._lista.currentItem()
        inicial = (
            str(Path(atual.data(Qt.ItemDataRole.UserRole)).parent)
            if atual and atual.data(Qt.ItemDataRole.UserRole)
            else str(PASTA_FIGURAS)
        )
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir gráfico", inicial, "Imagens PNG (*.png)"
        )
        if caminho:
            self._visualizador.mostrar(Path(caminho))
