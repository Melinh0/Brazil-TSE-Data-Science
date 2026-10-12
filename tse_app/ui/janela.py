from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import pandas as pd

from .. import geo
from ..chat import ChatErro, ServicoChat
from ..config import NOMES_REGIAO, NOMES_UF, ANOS, gravar_estado, ler_estado
from ..escopo import (
    TIPO_BR,
    TIPO_MUNICIPIO,
    TIPO_REGIAO,
    TIPO_UF,
    Escopo,
    escopo_brasil,
    escopo_municipio,
    escopo_regiao,
    escopo_uf,
    trilha,
)
from ..store import FonteDados, br, moeda, pct
from .candidatos import TabelaCandidatos
from .chat_ui import PainelChat
from .eleitos import PainelEleitos
from .galeria import GaleriaGraficos
from .mapa import Legenda, MapaView
from .secoes import PainelSecoes

ESTILO_APP = """
QMainWindow { background: #ffffff; }
QToolBar {
    spacing: 8px; padding: 4px 8px;
    background: #f6f8fa; border-bottom: 1px solid #d8dee4;
}
QToolBar QLabel { color: #333333; font-weight: 600; font-size: 12px; }
QToolBar QComboBox {
    font-weight: 600; font-size: 13px;
    min-height: 24px; padding: 2px 8px;
}
QTabWidget::pane { border: 1px solid #d8dee4; }
QTabBar::tab { padding: 6px 14px; margin-right: 2px; font-size: 12px; }
QTabBar::tab:selected { background: #ffffff; font-weight: 600; }
QTableWidget { gridline-color: #e3e6ea; font-size: 12px; }
QHeaderView::section {
    background: #f0f2f5; color: #333333;
    padding: 4px; border: none; font-weight: 600;
}
QStatusBar { background: #f6f8fa; }
QComboBox, QLineEdit { padding: 2px 4px; }
QPushButton { padding: 3px 8px; }
"""

ESTILO_APP_ESCURO = """
QMainWindow { background: #1e1f22; }
QToolBar {
    spacing: 8px; padding: 4px 8px;
    background: #2a2c31; border-bottom: 1px solid #3a3d42;
}
QToolBar QLabel { color: #e6e6e6; font-weight: 600; font-size: 12px; }
QToolBar QComboBox {
    font-weight: 600; font-size: 13px;
    min-height: 24px; padding: 2px 8px;
}
QWidget { background: transparent; color: #e6e6e6; }
QTabWidget::pane { border: 1px solid #3a3d42; background: #1e1f22; }
QTabBar::tab { background: #2a2c31; color: #cfcfcf; padding: 6px 14px; margin-right: 2px; font-size: 12px; }
QTabBar::tab:selected { background: #1e1f22; color: #ffffff; font-weight: 600; }
QTableWidget {
    gridline-color: #3a3d42; font-size: 12px;
    background: #232529; color: #e6e6e6; alternate-background-color: #2a2c31;
}
QHeaderView::section {
    background: #2a2c31; color: #e6e6e6;
    padding: 4px; border: none; font-weight: 600;
}
QStatusBar { background: #2a2c31; color: #cfcfcf; }
QComboBox, QLineEdit {
    background: #2a2c31; color: #e6e6e6; border: 1px solid #3a3d42; padding: 2px 4px;
}
QComboBox QAbstractItemView {
    background: #2a2c31; color: #e6e6e6; selection-background-color: #3d6185;
}
QPushButton {
    background: #3a3d42; color: #e6e6e6; border: none; padding: 3px 8px;
}
QPushButton:hover { background: #4a4e55; }
QLabel { color: #e6e6e6; }
QListWidget { background: #232529; color: #e6e6e6; alternate-background-color: #2a2c31; }
QScrollArea { border: none; }
QCheckBox { color: #e6e6e6; }
QScrollBar:vertical { background: #1e1f22; width: 12px; }
QScrollBar::handle:vertical { background: #3a3d42; min-height: 24px; border-radius: 5px; }
QScrollBar:horizontal { background: #1e1f22; height: 12px; }
QScrollBar::handle:horizontal { background: #3a3d42; min-width: 24px; border-radius: 5px; }
"""


def _rodando(trabalhador) -> bool:
    """True se o QThread existe e ainda está rodando (tolera C++ já deletado)."""
    if trabalhador is None:
        return False
    try:
        return bool(trabalhador.isRunning())
    except RuntimeError:  # deleteLater destruiu o objeto C++ — não está rodando
        return False


class TrabalhadorChat(QThread):
    pedaco = Signal(str)
    concluido = Signal(str)
    erro = Signal(str)

    def __init__(
        self,
        servico: ServicoChat,
        escopo: Escopo,
        ano: int,
        cargo: int,
        pergunta: str,
    ):
        super().__init__()
        self._servico = servico
        self._escopo = escopo
        self._ano = ano
        self._cargo = cargo
        self._pergunta = pergunta

    def run(self) -> None:  # noqa: D102
        partes: list[str] = []
        try:
            for pedaco in self._servico.responder(
                self._escopo, self._ano, self._cargo, self._pergunta
            ):
                partes.append(pedaco)
                self.pedaco.emit(pedaco)
            self.concluido.emit("".join(partes))
        except ChatErro as erro:
            self.erro.emit(str(erro))
        except Exception as erro:  # noqa: BLE001
            self.erro.emit(f"falha inesperada: {erro}")


class TrabalhadorBairros(QThread):
    """Mapeia bairro→zona em segundo plano (geocoding Nominatim + OSM Overpass)."""

    terminou = Signal()
    erro = Signal(str)

    def __init__(self, uf: str, municipio_cd: int, municipio: str):
        super().__init__()
        self._uf = uf
        self._municipio_cd = municipio_cd
        self._municipio = municipio

    def run(self) -> None:  # noqa: D102
        try:
            from ..bairros import bairros_zonas, extrair_locais

            extrair_locais()
            bairros_zonas(self._uf, self._municipio_cd, self._municipio)
            self.terminou.emit()
        except Exception as erro:  # noqa: BLE001
            self.erro.emit(str(erro))


class TrabalhadorSecoes(QThread):
    """Baixa/extrai votos por seção eleitoral (2024/2026) em segundo plano."""

    terminou = Signal()
    erro = Signal(str)

    def __init__(self, uf: str, ano: int):
        super().__init__()
        self._uf = uf
        self._ano = ano

    def run(self) -> None:  # noqa: D102
        try:
            from ..secoes import extrair_uf

            extrair_uf(self._uf, self._ano)
            self.terminou.emit()
        except Exception as erro:  # noqa: BLE001
            self.erro.emit(str(erro))


class TrabalhadorZonas(QThread):
    """Extrai o cache de votos por zona da UF em segundo plano."""

    terminou = Signal()
    erro = Signal(str)

    def __init__(self, fonte: FonteDados, ano: int, uf: str):
        super().__init__()
        self._fonte = fonte
        self._ano = ano
        self._uf = uf

    def run(self) -> None:  # noqa: D102
        try:
            self._fonte.extrair_zonas(self._ano, self._uf)
            self.terminou.emit()
        except Exception as erro:  # noqa: BLE001
            self.erro.emit(str(erro))


class TrabalhadorFiguras(QThread):
    """Gera os PNGs faltantes do escopo em segundo plano."""

    terminou = Signal()
    erro = Signal(str)

    def __init__(self, fonte: FonteDados, escopo: Escopo, ano: int, cargo_cd: int | None):
        super().__init__()
        self._fonte = fonte
        self._escopo = escopo
        self._ano = ano
        self._cargo_cd = cargo_cd

    def run(self) -> None:  # noqa: D102
        try:
            from ..graficos_locais import gerar_escopo

            gerar_escopo(self._fonte, self._escopo, self._ano, self._cargo_cd)
            self.terminou.emit()
        except Exception as erro:  # noqa: BLE001
            self.erro.emit(str(erro))


class JanelaPrincipal(QMainWindow):
    """Janela central: mapa navegável + resumo, candidatos, gráficos e chat."""

    def __init__(self, fonte: FonteDados, ano: int = 2024):
        super().__init__()
        self.fonte = fonte
        self.ano = ano
        self.escopo: Escopo = escopo_brasil()
        self.cargo: int | None = None
        self.indicador = "votos"
        self._formas_uf: dict[str, list] = {}
        self._nome_por_tse: dict[int, str] = {}
        self._trabalhador: TrabalhadorChat | None = None
        self._trabalhador_bairros: TrabalhadorBairros | None = None
        self._trabalhador_secoes: TrabalhadorSecoes | None = None
        self._trabalhador_zonas: TrabalhadorZonas | None = None
        self._trabalhador_figuras: TrabalhadorFiguras | None = None
        self._figuras_tentadas: set[str] = set()
        self._atualizando = False

        self.servico_chat = ServicoChat(fonte)
        self.setWindowTitle("Brazil TSE — Resultados e Análise (2024 · 2026)")
        self.resize(1560, 940)
        self._construir()

    # ------------------------------------------------------------------ UI
    def _construir(self) -> None:
        barra = QToolBar("Filtros")
        barra.setMovable(False)
        barra.setFloatable(False)
        self.addToolBar(barra)

        barra.addWidget(QLabel(" Ano: "))
        self.combo_ano = QComboBox()
        rotulos_ano = {
            2024: "2024 — eleições municipais",
            2026: "2026 — eleições gerais",
        }
        for ano in ANOS:
            self.combo_ano.addItem(rotulos_ano.get(ano, str(ano)), ano)
        self.combo_ano.setMinimumWidth(210)
        self.combo_ano.setCurrentIndex(list(ANOS).index(self.ano))
        self.combo_ano.currentIndexChanged.connect(self._trocar_ano)
        barra.addWidget(self.combo_ano)

        barra.addSeparator()
        barra.addWidget(QLabel(" Cargo: "))
        self.combo_cargo = QComboBox()
        self.combo_cargo.setMinimumWidth(190)
        self.combo_cargo.currentIndexChanged.connect(self._trocar_cargo)
        barra.addWidget(self.combo_cargo)

        barra.addSeparator()
        barra.addWidget(QLabel(" Indicador do mapa: "))
        self.combo_indicador = QComboBox()
        self.combo_indicador.setMinimumWidth(230)
        self.combo_indicador.currentIndexChanged.connect(self._trocar_indicador)
        barra.addWidget(self.combo_indicador)

        barra.addSeparator()
        barra.addWidget(QLabel(" Ir para município: "))
        self.combo_municipio = QComboBox()
        self.combo_municipio.setEditable(True)
        self.combo_municipio.setMinimumWidth(230)
        self.combo_municipio.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_municipio.textActivated.connect(self._buscar_municipio)
        self.combo_municipio.hide()
        barra.addWidget(self.combo_municipio)

        acao_recarregar = QAction("Recarregar dados", self)
        acao_recarregar.triggered.connect(self._atualizar_tudo)
        barra.addAction(acao_recarregar)

        self._acao_escuro = QAction("Modo escuro", self)
        self._acao_escuro.setCheckable(True)
        self._acao_escuro.toggled.connect(self._alternar_escuro)
        barra.addSeparator()
        barra.addAction(self._acao_escuro)

        central = QWidget()
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(6, 4, 6, 4)
        raiz.setSpacing(4)

        self._migalha = QFrame()
        self._migalha.setFrameShape(QFrame.Shape.StyledPanel)
        layout_migalha = QHBoxLayout(self._migalha)
        layout_migalha.setContentsMargins(6, 2, 6, 2)
        raiz.addWidget(self._migalha)

        self.mapa = MapaView()
        self.legenda = Legenda()
        self._rotulo_mapa = QLabel("")
        self._rotulo_mapa.setStyleSheet("font-size:12px; padding:2px;")

        esquerda = QWidget()
        esquerda_l = QVBoxLayout(esquerda)
        esquerda_l.setContentsMargins(0, 0, 0, 0)
        esquerda_l.addWidget(self.mapa, 1)
        esquerda_l.addWidget(self.legenda)
        esquerda_l.addWidget(self._rotulo_mapa)
        esquerda_l.addWidget(self._criar_ranking())

        self.abas = QTabWidget()
        self._aba_resumo = self._criar_resumo()
        self.painel_eleitos = PainelEleitos()
        self.painel_secoes = PainelSecoes()
        self.tabela_candidatos = TabelaCandidatos()
        self.tabela_candidatos.ao_trocar_todos_cargos = self._atualizar_candidatos
        self.galeria = GaleriaGraficos()
        self.painel_chat = PainelChat()
        self.painel_chat.enviar.connect(self._enviar_pergunta)
        self.painel_chat.limpou.connect(self.servico_chat.reiniciar)
        self.abas.addTab(self._aba_resumo, "Resumo")
        self.abas.addTab(self.painel_eleitos, "Eleitos")
        self.abas.addTab(self.painel_secoes, "Seções")
        self.abas.addTab(self.tabela_candidatos, "Candidatos")
        self.abas.addTab(self.galeria, "Gráficos")
        self.abas.addTab(self.painel_chat, "Chat IA")
        self.abas.currentChanged.connect(self._aba_trocada)

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.addWidget(esquerda)
        divisor.addWidget(self.abas)
        divisor.setSizes([820, 760])
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 3)
        raiz.addWidget(divisor, 1)

        self.setCentralWidget(central)

        status = QStatusBar()
        self.setStatusBar(status)
        self._rotulo_status = QLabel("")
        status.addWidget(self._rotulo_status, 1)

        self.mapa.clicou.connect(self._ao_clicar_mapa)

        self.setStyleSheet(ESTILO_APP)
        estado = ler_estado()
        if estado.get("modo_escuro"):
            self._acao_escuro.setChecked(True)  # dispara _alternar_escuro
        self._atualizar_tudo()

    def _criar_ranking(self) -> QWidget:
        quadro = QWidget()
        layout = QVBoxLayout(quadro)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(2)
        self._rotulo_ranking = QLabel("Valores por área")
        self._rotulo_ranking.setStyleSheet("font-weight:bold; font-size:12px; padding:2px;")
        self._tabela_ranking = QTableWidget(0, 2)
        self._tabela_ranking.setHorizontalHeaderLabels(["Área", "Valor"])
        self._tabela_ranking.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._tabela_ranking.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tabela_ranking.verticalHeader().setVisible(False)
        self._tabela_ranking.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._tabela_ranking.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._tabela_ranking.setAlternatingRowColors(True)
        self._tabela_ranking.setMaximumHeight(230)
        self._tabela_ranking.setMinimumHeight(90)
        self._tabela_ranking.setToolTip(
            "Maiores valores do indicador no mapa — duplo clique para navegar até a área"
        )
        self._tabela_ranking.itemDoubleClicked.connect(self._navegar_ranking)
        layout.addWidget(self._rotulo_ranking)
        layout.addWidget(self._tabela_ranking)
        return quadro

    def _atualizar_ranking(self, valores, formas) -> None:
        nomes = {codigo: nome for codigo, nome, _ in formas}
        linhas = [
            (codigo, nomes[codigo], valor)
            for codigo, valor in valores.items()
            if valor is not None and codigo in nomes
        ]
        linhas.sort(key=lambda linha: -linha[2])
        linhas = linhas[:15]
        formato = self._formato_indicador()
        rotulo_indicador = next(
            (
                r
                for i, r, _ in self.fonte.indicadores(self.escopo, self.ano)
                if i == self.indicador
            ),
            self.indicador,
        )
        self._rotulo_ranking.setText(
            f"Top {len(linhas)} — {rotulo_indicador} (duplo clique para navegar)"
        )
        self._tabela_ranking.setRowCount(len(linhas))
        for posicao, (codigo, nome, valor) in enumerate(linhas):
            item_nome = QTableWidgetItem(nome)
            item_nome.setData(Qt.ItemDataRole.UserRole, str(codigo))
            item_valor = QTableWidgetItem(formato(valor))
            item_valor.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._tabela_ranking.setItem(posicao, 0, item_nome)
            self._tabela_ranking.setItem(posicao, 1, item_valor)

    def _navegar_ranking(self, item: QTableWidgetItem) -> None:
        codigo = item.data(Qt.ItemDataRole.UserRole)
        nome = self._tabela_ranking.item(item.row(), 0).text()
        if codigo:
            self._ao_clicar_mapa(str(codigo), nome)

    def _criar_resumo(self) -> QWidget:
        painel = QWidget()
        layout = QVBoxLayout(painel)
        layout.setContentsMargins(6, 6, 6, 6)
        self._titulo_resumo = QLabel("Selecione um escopo")
        self._titulo_resumo.setStyleSheet("font-size:15px; font-weight:bold;")
        self._titulo_resumo.setWordWrap(True)
        self._nota_resumo = QLabel("")
        self._nota_resumo.setWordWrap(True)
        self._nota_resumo.setStyleSheet("color:#555555;")
        self._tabela_resumo = QTableWidget(0, 2)
        self._tabela_resumo.setHorizontalHeaderLabels(["Indicador", "Valor"])
        self._tabela_resumo.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._tabela_resumo.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tabela_resumo.verticalHeader().setVisible(False)
        self._tabela_resumo.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._tabela_resumo.setAlternatingRowColors(True)
        layout.addWidget(self._titulo_resumo)
        layout.addWidget(self._nota_resumo)
        layout.addWidget(self._tabela_resumo, 1)
        return painel

    # ------------------------------------------------------------- ações
    def _alternar_escuro(self, marcado: bool) -> None:
        self.setStyleSheet(ESTILO_APP_ESCURO if marcado else ESTILO_APP)
        estado = ler_estado()
        estado["modo_escuro"] = bool(marcado)
        gravar_estado(estado)

    def _trocar_ano(self) -> None:
        self.ano = int(self.combo_ano.currentData())
        self._carregar_cargos()
        self._atualizar_tudo()

    def _trocar_cargo(self) -> None:
        if self._atualizando:
            return
        dados = self.combo_cargo.currentData()
        if dados is None:
            return
        self.cargo = int(dados)
        self._carregar_indicadores()
        self._atualizar_mapa()
        self._atualizar_eleitos()
        self._atualizar_secoes()
        self._atualizar_candidatos()
        self._atualizar_contexto()
        self._atualizar_galeria()

    def _trocar_indicador(self) -> None:
        if self._atualizando:
            return
        dados = self.combo_indicador.currentData()
        if dados is None:
            return
        self.indicador = str(dados)
        self._atualizar_mapa()

    def _ao_clicar_mapa(self, codigo: str, nome: str) -> None:
        if self.escopo.tipo == TIPO_BR:
            self.mudar_escopo(escopo_regiao(codigo))
        elif self.escopo.tipo == TIPO_REGIAO:
            self.mudar_escopo(escopo_uf(codigo))
        else:
            uf = self.escopo.uf or codigo
            if self.escopo.tipo == TIPO_MUNICIPIO and str(codigo) == self.escopo.codigo:
                return
            self.mudar_escopo(escopo_municipio(uf, codigo, nome))

    def _buscar_municipio(self, texto: str) -> None:
        uf = self.escopo.uf
        if not uf:
            return
        alvo = str(texto).strip().upper()
        municipios = self.fonte.municipios(uf)
        coincidencias = municipios[municipios["municipio"].str.upper() == alvo]
        if coincidencias.empty:
            coincidencias = municipios[
                municipios["municipio"].str.upper().str.startswith(alvo)
            ]
        if coincidencias.empty:
            return
        linha = coincidencias.iloc[0]
        self.mudar_escopo(
            escopo_municipio(uf, int(linha["municipio_cd"]), str(linha["municipio"]))
        )

    def mudar_escopo(self, escopo: Escopo) -> None:
        if escopo == self.escopo:
            return
        self.escopo = escopo
        self._atualizar_tudo()

    def _clicar_migalha(self, escopo: Escopo) -> None:
        self.mudar_escopo(escopo)

    # --------------------------------------------------------- atualizações
    def _atualizar_tudo(self, gerar_figuras: bool = True) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._carregar_cargos()
            self._carregar_indicadores()
            self._atualizar_migalha()
            self._atualizar_mapa()
            self._atualizar_resumo()
            self._atualizar_eleitos()
            self._atualizar_secoes()
            self._atualizar_candidatos()
            self._atualizar_busca_municipio()
            self._atualizar_galeria(gerar=gerar_figuras)
            self._atualizar_contexto()
            self._atualizar_status()
        finally:
            QApplication.restoreOverrideCursor()
        self._disparar_pre_carregamentos()

    def _atualizar_galeria(self, gerar: bool = True) -> None:
        """Lista PNGs prontos (rápido) e dispara a geração dos faltantes em worker."""
        try:
            from ..graficos_locais import listar_escopo

            existentes, faltantes = listar_escopo(
                self.fonte, self.escopo, self.ano, self.cargo
            )
        except Exception:  # noqa: BLE001
            existentes, faltantes = [], []
        self.galeria.definir_escopo(
            self.escopo, self.fonte, self.ano, self.cargo, caminhos=existentes
        )
        if not gerar:
            return
        novos = [c for c in faltantes if str(c) not in self._figuras_tentadas]
        if not novos:
            return
        if self._trabalhador_figuras is not None and self._trabalhador_figuras.isRunning():
            return  # o worker atual reavalia ao terminar
        for caminho in novos:
            self._figuras_tentadas.add(str(caminho))
        self._trabalhador_figuras = TrabalhadorFiguras(
            self.fonte, self.escopo, self.ano, self.cargo
        )
        self._trabalhador_figuras.terminou.connect(self._figuras_prontas)
        self._trabalhador_figuras.erro.connect(self._figuras_falharam)
        self._atualizar_status()
        self._trabalhador_figuras.start()

    def _figuras_prontas(self) -> None:
        self._atualizar_galeria()
        self._atualizar_status()

    def _figuras_falharam(self, mensagem: str) -> None:
        self._rotulo_status.setText(f"falha ao gerar gráficos ({mensagem})")
        self._atualizar_galeria()

    def _atualizar_eleitos(self) -> None:
        try:
            dados = self.fonte.eleitos(self.escopo, self.ano, self.cargo)
        except Exception as erro:  # noqa: BLE001
            self.painel_eleitos.atualizar_dados(pd.DataFrame(), self.escopo.titulo, self.ano)
            self.painel_eleitos._nota.setText(f"falha ao calcular eleitos: {erro}")
            return
        self.painel_eleitos.atualizar_dados(dados, self.escopo.titulo, self.ano)

    def _atualizar_secoes(self) -> None:
        try:
            self.painel_secoes.atualizar(self.fonte, self.escopo, self.ano, self.cargo)
        except Exception as erro:  # noqa: BLE001
            self.painel_secoes._nota.setText(f"falha ao carregar seções: {erro}")

    def _carregar_cargos(self) -> None:
        self._atualizando = True
        try:
            self.combo_cargo.clear()
            cargos = self.fonte.cargos(self.ano)
            for codigo in cargos:
                self.combo_cargo.addItem(self.fonte.nome_cargo(codigo), codigo)
            if self.cargo not in cargos:
                self.cargo = cargos[0] if cargos else None
            indice = cargos.index(self.cargo) if self.cargo in cargos else 0
            self.combo_cargo.setCurrentIndex(indice)
        finally:
            self._atualizando = False

    def _carregar_indicadores(self) -> None:
        self._atualizando = True
        try:
            self.combo_indicador.clear()
            opcoes = self.fonte.indicadores(self.escopo, self.ano)
            if not opcoes:
                self.indicador = None
                return
            for identificador, rotulo, exige_cargo in opcoes:
                rotulo_final = (
                    f"{rotulo} — {self.fonte.nome_cargo(self.cargo)}"
                    if exige_cargo and self.cargo
                    else rotulo
                )
                self.combo_indicador.addItem(rotulo_final, identificador)
            indice = next(
                (
                    i
                    for i, opcao in enumerate(opcoes)
                    if opcao[0] == self.indicador
                ),
                0,
            )
            if indice == 0 and self.indicador not in [o[0] for o in opcoes]:
                self.indicador = opcoes[0][0]
            self.combo_indicador.setCurrentIndex(indice)
            self.indicador = str(self.combo_indicador.currentData() or self.indicador)
        finally:
            self._atualizando = False

    def _atualizar_migalha(self) -> None:
        while self._migalha.layout().count():
            item = self._migalha.layout().takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        caminho = trilha(self.escopo)
        for indice, escopo in enumerate(caminho):
            botao = QPushButton(escopo.titulo)
            botao.setFlat(True)
            botao.setCursor(Qt.CursorShape.PointingHandCursor)
            botao.setStyleSheet(
                "font-weight:bold; padding:2px 4px;"
                if indice == len(caminho) - 1
                else "padding:2px 4px;"
            )
            botao.clicked.connect(lambda _=False, e=escopo: self._clicar_migalha(e))
            self._migalha.layout().addWidget(botao)
            if indice < len(caminho) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("color:#888888; padding:0 2px;")
                self._migalha.layout().addWidget(sep)
        self._migalha.layout().addStretch(1)

    def _formas_mapa(self):
        escopo = self.escopo
        if escopo.tipo == TIPO_BR:
            formas = [
                (codigo, NOMES_REGIAO.get(codigo, codigo), poligonos)
                for codigo, poligonos in geo.malha_regioes()
            ]
            rotulos = {codigo: NOMES_REGIAO.get(codigo, codigo) for codigo, _, _ in formas}
            return formas, rotulos, None
        if escopo.tipo == TIPO_REGIAO:
            ufs = {uf for uf, reg in _ufs_por_regiao().items() if reg == escopo.codigo}
            formas = [
                (codigo, NOMES_UF.get(codigo, codigo), poligonos)
                for codigo, poligonos in geo.malha_ufs()
                if codigo in ufs
            ]
            rotulos = {codigo: codigo for codigo, _, _ in formas}
            return formas, rotulos, None

        uf = escopo.uf or ""
        if uf not in self._formas_uf:
            mapa = self.fonte.mapa_municipios()
            sub = mapa[mapa["uf"] == uf]
            ibge_para_tse = dict(zip(sub["municipio_ibge"], sub["municipio_cd"]))
            self._nome_por_tse = dict(zip(sub["municipio_cd"], sub["municipio"]))
            formas = []
            for cod_ibge, poligonos in geo.malha_municipios(uf):
                tse = ibge_para_tse.get(int(cod_ibge)) if str(cod_ibge).isdigit() else None
                if tse is None:
                    continue
                formas.append(
                    (str(int(tse)), str(self._nome_por_tse.get(int(tse), cod_ibge)), poligonos)
                )
            self._formas_uf[uf] = formas
        formas = self._formas_uf[uf]
        ordenado = sorted(formas, key=lambda f: -sum(_area(a) for a in f[2]))
        rotulos = {codigo: nome for codigo, nome, _ in ordenado[:12]}
        destaque = escopo.codigo if escopo.tipo == TIPO_MUNICIPIO else None
        if destaque:
            rotulos[destaque] = dict((c, n) for c, n, _ in formas).get(destaque, "")
        return formas, rotulos, destaque

    def _formato_indicador(self):
        if self.indicador in ("comparecimento", "eleitores_pop", "invalidos"):
            return lambda v: pct(v)
        if self.indicador == "renda":
            return lambda v: moeda(v)
        return lambda v: br(v)

    def _atualizar_mapa(self) -> None:
        cargo = self.cargo or 0
        try:
            valores = self.fonte.serie(self.escopo, self.ano, self.indicador, cargo)
        except FileNotFoundError as erro:
            self._rotulo_mapa.setText(str(erro))
            return
        formas, rotulos, destaque = self._formas_mapa()
        formato = self._formato_indicador()
        raiz = self.indicador in ("votos", "candidatos")
        self.mapa.mostrar(formas, valores, formato, destaque, rotulos, raiz)
        self._atualizar_ranking(valores, formas)
        presentes = [
            v
            for cod, v in valores.items()
            if v is not None and any(cod == f[0] for f in formas)
        ]
        rotulo_indicador = next(
            (
                r
                for i, r, _ in self.fonte.indicadores(self.escopo, self.ano)
                if i == self.indicador
            ),
            self.indicador,
        )
        if presentes:
            self.legenda.definir(min(presentes), max(presentes), rotulo_indicador, formato)
        else:
            self.legenda.definir(None, None, rotulo_indicador, formato, sem_dados=True)
        nivel = {
            TIPO_BR: "Brasil (clique em uma região)",
            TIPO_REGIAO: f"{self.escopo.nome} (clique em um estado)",
            TIPO_UF: f"{self.escopo.nome} — municípios (clique para ver os candidatos)",
            TIPO_MUNICIPIO: f"{self.escopo.titulo} destacado em {NOMES_UF.get(self.escopo.uf or '', '')}",
        }[self.escopo.tipo]
        nota_escala = " · cor em escala √" if raiz else ""
        self._rotulo_mapa.setText(
            f"{nivel} · {len(formas)} áreas · indicador: {rotulo_indicador}"
            f"{nota_escala} · arraste para mover, roda do mouse para zoom"
        )

    def _atualizar_resumo(self) -> None:
        self._titulo_resumo.setText(
            f"{self.escopo.titulo} — eleições de {self.ano}"
        )
        pares = self.fonte.resumo(self.escopo, self.ano)
        self._tabela_resumo.setRowCount(len(pares))
        for linha, (rotulo, valor) in enumerate(pares):
            self._tabela_resumo.setItem(linha, 0, QTableWidgetItem(rotulo))
            self._tabela_resumo.setItem(linha, 1, QTableWidgetItem(valor))
        notas = [
            "Votos contados no turno decisivo de cada município "
            "(eleições suplementares/2º turno prevalecem)."
        ]
        if self.ano == 2026:
            notas.append(
                "Em 2026 os dados municipais cobrem presidente, governador, senador e "
                "deputados; comparecimento e renda só existem para 2024 (Censo 2022)."
            )
        if self.escopo.tipo == TIPO_MUNICIPIO and self.ano == 2026:
            notas.append(
                "O TSE não publicou detalhe municipal de apuração em 2026 "
                "(`detalhe_votacao_munzona_2026.zip` indisponível)."
            )
        self._nota_resumo.setText(" ".join(notas))

    def _atualizar_candidatos(self) -> None:
        municipal = self.escopo.tipo == TIPO_MUNICIPIO
        self.tabela_candidatos.definir_todos_cargos_disponivel(municipal)
        todos = municipal and self.tabela_candidatos.todos_cargos
        if todos:
            quadros = []
            for cargo in self.fonte.cargos(self.ano):
                dados = self.fonte.candidatos(self.escopo, self.ano, cargo)
                if dados.empty:
                    continue
                dados = dados.copy()
                dados["cargo_nome"] = self.fonte.nome_cargo(cargo)
                quadros.append(dados)
            dados = (
                pd.concat(quadros, ignore_index=True)
                if quadros
                else pd.DataFrame()
            )
            if not dados.empty:
                dados = dados.sort_values(["cargo_nome", "votos"], ascending=[True, False])
            titulo = f"Todos os cargos · {self.escopo.titulo} · {self.ano}"
            if dados.empty:
                titulo += " — sem dados para este recorte"
            self.tabela_candidatos.atualizar(dados, titulo)
            return
        if self.cargo is None:
            self.tabela_candidatos.atualizar(pd.DataFrame(), "Nenhum cargo disponível")
            return
        dados = self.fonte.candidatos(self.escopo, self.ano, self.cargo)
        if not dados.empty:
            dados = dados.copy()
            dados["cargo_nome"] = self.fonte.nome_cargo(self.cargo)
        titulo = (
            f"{self.fonte.nome_cargo(self.cargo)} · {self.escopo.titulo} · {self.ano}"
        )
        if dados.empty:
            titulo += " — sem dados para este recorte"
        self.tabela_candidatos.atualizar(dados, titulo)

    def _atualizar_busca_municipio(self) -> None:
        uf = self.escopo.uf
        self.combo_municipio.blockSignals(True)
        self.combo_municipio.clear()
        if uf:
            municipios = self.fonte.municipios(uf)
            nomes = list(municipios["municipio"])
            self.combo_municipio.addItems(nomes)
            completador = QCompleter(nomes, self.combo_municipio)
            completador.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completador.setFilterMode(Qt.MatchFlag.MatchContains)
            self.combo_municipio.setCompleter(completador)
            self.combo_municipio.show()
        else:
            self.combo_municipio.hide()
        self.combo_municipio.blockSignals(False)

    def _atualizar_contexto(self) -> None:
        if self.cargo is None:
            return
        contexto = self.fonte.contexto(self.escopo, self.ano, self.cargo)
        self.painel_chat.definir_contexto(contexto)

    def _atualizar_status(self) -> None:
        ok, texto = self.servico_chat.cliente.disponivel()
        prefixo = "●" if ok else "○"
        extra = ""
        if self._trabalhador_bairros is not None and self._trabalhador_bairros.isRunning():
            extra += " · mapeando bairros ↔ zonas (geocoding em 2º plano)…"
        if self._trabalhador_secoes is not None and self._trabalhador_secoes.isRunning():
            extra += f" · extraindo seções eleitorais {self.ano} em 2º plano…"
        if self._trabalhador_zonas is not None and self._trabalhador_zonas.isRunning():
            extra += " · extraindo votos por zona em 2º plano…"
        if self._trabalhador_figuras is not None and self._trabalhador_figuras.isRunning():
            extra += " · gerando gráficos em 2º plano…"
        self._rotulo_status.setText(
            f"{prefixo} {texto} · requisições: {self.servico_chat.cliente.requisicoes} · "
            f"tokens: {self.servico_chat.cliente.tokens_entrada} entrada / "
            f"{self.servico_chat.cliente.tokens_saida} saída · escopo: {self.escopo.titulo}"
            f"{extra}"
        )

    # ------------------------------------------------------- pré-carregamentos
    def _disparar_pre_carregamentos(self) -> None:
        """Gera caches (bairros↔zonas, zonas, seções) em segundo plano quando ausentes."""
        self._disparar_mapeamento_bairros()
        self._disparar_extracao_zonas()
        self._disparar_extracao_secoes()

    def _disparar_extracao_zonas(self) -> None:
        """Extrai o cache de votos por zona da UF em segundo plano quando ausente."""
        if not self.fonte.precisa_extrair_zonas(self.escopo, self.ano):
            return
        if self._trabalhador_zonas is not None and self._trabalhador_zonas.isRunning():
            return
        self._trabalhador_zonas = TrabalhadorZonas(
            self.fonte, self.ano, str(self.escopo.uf)
        )
        self._trabalhador_zonas.terminou.connect(self._zonas_prontas)
        self._trabalhador_zonas.erro.connect(self._bairros_falhou)
        self._atualizar_status()
        self._trabalhador_zonas.start()

    def _zonas_prontas(self) -> None:
        self._figuras_tentadas.clear()
        self._atualizar_resumo()
        self._atualizar_contexto()
        self._atualizar_galeria()
        self._atualizar_status()

    def aguardar_trabalhadores(self, timeout_ms: int = 120_000) -> None:
        """Espera os workers de fundo e sincroniza a UI (uso em selftest/fechamento)."""
        nomes = (
            "_trabalhador_figuras",
            "_trabalhador_zonas",
            "_trabalhador_secoes",
            "_trabalhador_bairros",
            "_trabalhador",
        )
        for _rodada in range(12):
            rodando = [
                getattr(self, nome)
                for nome in nomes
                if _rodando(getattr(self, nome))
            ]
            if not rodando:
                break
            for trabalhador in rodando:
                trabalhador.wait(timeout_ms)
            # a atualização pode iniciar novos workers (ex.: figuras do escopo
            # recém-aberto) — o laço espera de novo na próxima rodada
            self._atualizar_tudo()
        # listagem final sem disparar novas gerações
        self._atualizar_tudo(gerar_figuras=False)

    def closeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        """Encerra workers pendentes antes de fechar (evita crash 0xC0000409)."""
        for nome in (
            "_trabalhador",
            "_trabalhador_bairros",
            "_trabalhador_secoes",
            "_trabalhador_zonas",
            "_trabalhador_figuras",
        ):
            trabalhador = getattr(self, nome, None)
            if _rodando(trabalhador):
                trabalhador.wait(30_000)
        super().closeEvent(evento)

    def _disparar_mapeamento_bairros(self) -> None:
        """Gera o cache bairro→zona em segundo plano quando ainda não existe."""
        if not self.fonte.precisa_mapear_bairros(self.escopo):
            return
        if self._trabalhador_bairros is not None and self._trabalhador_bairros.isRunning():
            return
        if not self.escopo.uf:
            return
        self._trabalhador_bairros = TrabalhadorBairros(
            self.escopo.uf,
            int(self.escopo.codigo),
            str(self.escopo.titulo).split("/")[0],
        )
        self._trabalhador_bairros.terminou.connect(self._bairros_prontos)
        self._trabalhador_bairros.erro.connect(self._bairros_falhou)
        self._atualizar_status()
        self._trabalhador_bairros.start()

    def _aba_trocada(self, indice: int) -> None:
        """Ao abrir a aba Seções, dispara o download/extração pendente do ano."""
        if self.abas.widget(indice) is self.painel_secoes:
            self._disparar_extracao_secoes()

    def _disparar_extracao_secoes(self) -> None:
        """Baixa/extrai votos por seção eleitoral (2024/2026) quando a aba está aberta."""
        if self.ano not in (2024, 2026):
            return
        if self.abas.currentWidget() is not self.painel_secoes:
            return
        if not self.fonte.precisa_extrair_secoes(self.escopo, self.ano):
            return
        if _rodando(self._trabalhador_secoes):
            return
        ano = self.ano
        # município/UF: zip da própria UF; Brasil/região: consolidado nacional (2026)
        if self.escopo.tipo in (TIPO_MUNICIPIO, TIPO_UF) and self.escopo.uf:
            uf = str(self.escopo.uf)
        else:
            uf = "BR"
        self._trabalhador_secoes = TrabalhadorSecoes(uf, ano)
        self._trabalhador_secoes.terminou.connect(self._bairros_prontos)
        self._trabalhador_secoes.erro.connect(
            lambda mensagem, ano=ano, uf=uf: self._secoes_falhou(ano, uf, mensagem)
        )
        self._atualizar_status()
        self._trabalhador_secoes.start()

    def _secoes_falhou(self, ano: int, uf: str, mensagem: str) -> None:
        """Mostra a falha de download/extração de seções na barra e no painel."""
        self._rotulo_status.setText(f"seções {ano}/{uf} indisponíveis ({mensagem})")
        if self.painel_secoes._tabela.rowCount() == 0:
            self.painel_secoes._nota.setText(
                f"Falha ao baixar/extrair as seções de {ano}/{uf}: {mensagem}"
            )

    def _bairros_prontos(self) -> None:
        self._figuras_tentadas.clear()
        self._atualizar_resumo()
        self._atualizar_eleitos()
        self._atualizar_contexto()
        self._atualizar_secoes()
        self._atualizar_galeria()
        self._atualizar_status()

    def _bairros_falhou(self, mensagem: str) -> None:
        self._rotulo_status.setText(
            f"pré-carregamento indisponível ({mensagem}) — "
            "contexto usa locais de votação como referência"
        )

    # ----------------------------------------------------------------- chat
    def _enviar_pergunta(self, pergunta: str) -> None:
        if self.cargo is None:
            self.painel_chat.falha("nenhum cargo disponível")
            return
        if _rodando(self._trabalhador):
            self.painel_chat.falha("aguarde a resposta atual terminar antes de perguntar de novo")
            return
        ok, texto = self.servico_chat.cliente.disponivel()
        if not ok:
            self.painel_chat.usuario(pergunta)
            self.painel_chat.falha(f"Ollama Cloud indisponível: {texto}")
            return
        self.painel_chat.usuario(pergunta)
        self.painel_chat.iniciar_resposta()
        self.painel_chat.definir_status("consultando o Ollama Cloud…")
        trabalhador = TrabalhadorChat(
            self.servico_chat, self.escopo, self.ano, self.cargo, pergunta
        )
        self._trabalhador = trabalhador
        trabalhador.pedaco.connect(self.painel_chat.acrescentar)
        trabalhador.concluido.connect(
            lambda texto, t=trabalhador: self._chat_concluido(texto, t)
        )
        trabalhador.erro.connect(
            lambda mensagem, t=trabalhador: self._chat_falhou(mensagem, t)
        )
        trabalhador.finished.connect(trabalhador.deleteLater)
        trabalhador.start()

    def _chat_concluido(self, texto: str, trabalhador=None) -> None:
        # só limpa a referência se quem concluiu é o worker atual
        if trabalhador is None or self._trabalhador is trabalhador:
            self._trabalhador = None
        self.painel_chat.concluir(texto)
        self.painel_chat.definir_status("resposta concluída")
        self._atualizar_status()

    def _chat_falhou(self, erro: str, trabalhador=None) -> None:
        if trabalhador is None or self._trabalhador is trabalhador:
            self._trabalhador = None
        self.painel_chat.falha(erro)
        self.painel_chat.definir_status("falha — tente de novo em instantes")
        self._atualizar_status()

    def keyPressEvent(self, evento) -> None:  # noqa: N802
        if evento.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
            return
        super().keyPressEvent(evento)


def _ufs_por_regiao() -> dict[str, str]:
    from ..config import UF_REGIAO

    return UF_REGIAO


def _area(anel: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(anel) - 1):
        x1, y1 = anel[i]
        x2, y2 = anel[i + 1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0
