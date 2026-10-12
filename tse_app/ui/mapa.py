from __future__ import annotations

from collections.abc import Callable

from matplotlib import colormaps
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
    QWidget,
)
from shapely.geometry import Polygon

Cor = tuple[float, float, float]


def _cor_padrao(valor: float | None, vmin: float, vmax: float, raiz: bool = False) -> QColor:
    if valor is None:
        return QColor(214, 214, 214)
    frac = (valor - vmin) / (vmax - vmin) if vmax > vmin else 0.5
    if raiz:
        frac = frac**0.5
    frac = min(max(frac, 0.0), 1.0)
    r, g, b, _ = colormaps["YlOrRd"](frac)
    return QColor.fromRgbF(r, g, b)


class ItemMapa(QGraphicsPathItem):
    def __init__(self, codigo: str, nome: str, caminho: QPainterPath):
        super().__init__(caminho)
        self.codigo = codigo
        self.nome = nome
        self._ao_clicar: Callable[[str, str], None] | None = None
        self._mapa_view: MapaView | None = None
        self._caneta_px = 0.9
        self._caneta_cor = QColor(255, 255, 255)
        self._caneta_base = QPen(self._caneta_cor, self._caneta_px)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, evento):  # noqa: N802
        if (
            self._ao_clicar is not None
            and evento.button() == Qt.MouseButton.LeftButton
        ):
            self._ao_clicar(self.codigo, self.nome)
            evento.accept()
            return
        super().mousePressEvent(evento)

    def hoverEnterEvent(self, evento):  # noqa: N802
        self.setPen(self._caneta_hover())
        super().hoverEnterEvent(evento)

    def hoverLeaveEvent(self, evento):  # noqa: N802
        self.setPen(self._caneta_base)
        super().hoverLeaveEvent(evento)

    def _caneta_hover(self) -> QPen:
        escala = 1.0
        if self._mapa_view is not None:
            escala = abs(self._mapa_view.transform().m11()) or 1.0
        return QPen(QColor(30, 30, 30), 1.6 / escala)


class MapaView(QGraphicsView):
    """Mapa navegável: Brasil → região → UF → município (clique para aprofundar)."""

    clicou = Signal(str, str)  # código, nome

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._cena = QGraphicsScene(self)
        self.setScene(self._cena)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(247, 249, 251)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._itens: list[ItemMapa] = []
        self._rotulos_tela: list[tuple[QPointF, str]] = []
        self._zoom_manual = False
        self._qtd_formas = -1

    # ------------------------------------------------------------- desenho
    def mostrar(
        self,
        formas: list[tuple[str, str, list[list[tuple[float, float]]]]],
        valores: dict[str, float | None],
        formato: Callable[[float], str] | None = None,
        destaque: str | None = None,
        rotulos: dict[str, str] | None = None,
        raiz: bool = False,
    ) -> None:
        self._cena.clear()
        self._itens.clear()
        self._rotulos_tela.clear()
        formatar = formato or (lambda v: f"{v:,.0f}")
        presentes = [v for k, v in valores.items() if v is not None and k in {f[0] for f in formas}]
        vmin = min(presentes) if presentes else 0.0
        vmax = max(presentes) if presentes else 1.0

        for codigo, nome, poligonos in formas:
            caminho = QPainterPath()
            maior_area = 0.0
            centro_maior = QPointF()
            for anel in poligonos:
                if len(anel) < 4:
                    continue
                caminho.moveTo(anel[0][0], anel[0][1])
                for x, y in anel[1:]:
                    caminho.lineTo(x, y)
                caminho.closeSubpath()
                area = _area(anel)
                if area > maior_area:
                    maior_area = area
                    centro_maior = _centroide(anel)
            if caminho.isEmpty():
                continue
            valor = valores.get(codigo)
            item = ItemMapa(codigo, nome, caminho)
            item._mapa_view = self
            cor = _cor_padrao(valor, vmin, vmax, raiz)
            item.setBrush(QBrush(cor))
            if destaque and codigo == destaque:
                item._caneta_px = 2.6
                item._caneta_cor = QColor(20, 20, 20)
            self._atualizar_caneta(item)
            if valor is None:
                texto = f"{nome}\nsem dado disponível"
            else:
                texto = f"{nome}\n{formatar(valor)}"
            item.setToolTip(texto)
            item._ao_clicar = self.clicou.emit
            self._cena.addItem(item)
            self._itens.append(item)

            if rotulos and codigo in rotulos:
                self._rotulos_tela.append(
                    (QPointF(centro_maior), str(rotulos[codigo]))
                )

        # clear() no PySide6 mantém um sceneRect obsoleto; o ajustar recalcula
        if len(formas) != self._qtd_formas:
            self._zoom_manual = False
            self._qtd_formas = len(formas)
        if not self._zoom_manual:
            self.ajustar()
        else:
            self.viewport().update()

    def ajustar(self) -> None:
        retangulo = self._cena.itemsBoundingRect()
        if retangulo.isEmpty() or self.viewport().width() == 0:
            return
        self._cena.setSceneRect(retangulo)
        self.resetTransform()
        self.fitInView(retangulo, Qt.AspectRatioMode.KeepAspectRatio)
        self._atualizar_canetas()

    # -------------------------------------------------------- espessuras
    def _escala(self) -> float:
        return abs(self.transform().m11()) or 1.0

    def _atualizar_caneta(self, item: ItemMapa) -> None:
        item._caneta_base = QPen(item._caneta_cor, item._caneta_px / self._escala())
        item.setPen(item._caneta_base)

    def _atualizar_canetas(self) -> None:
        for item in self._itens:
            self._atualizar_caneta(item)
        self.viewport().update()

    # ---------------------------------------------------- rótulos em tela
    def paintEvent(self, evento):  # noqa: N802
        super().paintEvent(evento)
        if not self._rotulos_tela:
            return
        pintor = QPainter(self.viewport())
        fonte = QFont("Segoe UI")
        fonte.setPixelSize(12)
        fonte.setWeight(QFont.Weight.Bold)
        pintor.setFont(fonte)
        metrica = pintor.fontMetrics()
        limite = self.viewport().rect().adjusted(-240, -240, 240, 240)
        for cena_pt, texto in self._rotulos_tela:
            ponto = self.mapFromScene(cena_pt)
            if not limite.contains(ponto):
                continue
            retangulo = metrica.boundingRect(texto)
            retangulo.moveCenter(ponto)
            pintor.setPen(
                QPen(
                    QColor(255, 255, 255, 235),
                    3.0,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.SquareCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            pintor.drawText(retangulo, Qt.AlignmentFlag.AlignCenter, texto)
            pintor.setPen(QColor(30, 30, 30))
            pintor.drawText(retangulo, Qt.AlignmentFlag.AlignCenter, texto)
        pintor.end()

    # ---------------------------------------------------------- interações
    def wheelEvent(self, evento):  # noqa: N802
        self._zoom_manual = True
        fator = 1.25 if evento.angleDelta().y() > 0 else 0.8
        self.scale(fator, fator)
        self._atualizar_canetas()

    def resizeEvent(self, evento):  # noqa: N802
        super().resizeEvent(evento)
        if not self._zoom_manual and not self._cena.itemsBoundingRect().isEmpty():
            self.ajustar()


class Legenda(QWidget):
    """Barra de gradiente com rótulo em cima e mínimo/máximo embaixo."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(64)
        self._min: float | None = None
        self._max: float | None = None
        self._rotulo = ""
        self._formato: Callable[[float], str] = lambda v: f"{v:,.0f}"
        self._sem_dados = False

    def definir(
        self,
        vmin: float | None,
        vmax: float | None,
        rotulo: str,
        formato: Callable[[float], str] | None = None,
        sem_dados: bool = False,
    ) -> None:
        self._min = vmin
        self._max = vmax
        self._rotulo = rotulo
        if formato:
            self._formato = formato
        self._sem_dados = sem_dados
        self.update()

    def paintEvent(self, evento):  # noqa: N802
        super().paintEvent(evento)
        pintor = QPainter(self)
        margem = 12
        largura = self.width() - 2 * margem

        pintor.setPen(QColor(45, 45, 45))
        pintor.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        pintor.drawText(
            QRectF(margem, 2, largura, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._rotulo or "Indicador",
        )

        barra = QRectF(margem, 24, max(largura, 40), 14)
        if self._sem_dados or self._min is None or self._max is None:
            pintor.fillRect(barra, QColor(214, 214, 214))
            pintor.setPen(QColor(120, 120, 120))
            pintor.drawText(
                barra, Qt.AlignmentFlag.AlignCenter, "sem dados disponíveis"
            )
        else:
            gradiente = colormaps["YlOrRd"]
            for i in range(int(barra.width())):
                frac = i / max(barra.width() - 1, 1)
                r, g, b, _ = gradiente(frac)
                pintor.fillRect(
                    QRectF(barra.x() + i, barra.y(), 1, barra.height()),
                    QColor.fromRgbF(r, g, b),
                )
            pintor.setPen(QColor(90, 90, 90))
            pintor.setFont(QFont("Segoe UI", 8.5))
            pintor.drawText(
                QRectF(barra.x(), barra.y() + 16, barra.width(), 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._formato(self._min),
            )
            pintor.drawText(
                QRectF(barra.x(), barra.y() + 16, barra.width(), 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._formato(self._max),
            )
        pintor.end()


def _area(anel: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(anel) - 1):
        x1, y1 = anel[i]
        x2, y2 = anel[i + 1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _centroide(anel: list[tuple[float, float]]) -> QPointF:
    """Centro do polígono: centroide de área, com fallback para ponto interno."""
    try:
        poligono = Polygon(anel)
        if not poligono.is_valid:
            poligono = poligono.buffer(0)
        ponto = poligono.centroid
        if ponto.is_empty or not poligono.contains(ponto):
            ponto = poligono.representative_point()
        return QPointF(ponto.x, ponto.y)
    except Exception:  # noqa: BLE001
        xs = [p[0] for p in anel]
        ys = [p[1] for p in anel]
        return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))
