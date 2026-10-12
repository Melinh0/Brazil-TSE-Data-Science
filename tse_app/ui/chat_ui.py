from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PainelChat(QWidget):
    """Conversa com o assistente, usando o contexto da região selecionada."""

    enviar = Signal(str)
    limpou = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._mensagens: list[tuple[str, str]] = []
        self._parcial = ""
        self._contexto_aberto = False

        self._texto = QTextEdit()
        self._texto.setReadOnly(True)
        self._texto.setAcceptRichText(True)
        self._texto.setPlaceholderText(
            "Pergunte sobre a região selecionada… (ex.: qual a correlação entre renda e "
            "comparecimento aqui?)"
        )

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #555555; font-size: 11px;")

        self._entrada = QLineEdit()
        self._entrada.setPlaceholderText("Digite sua pergunta sobre o escopo atual…")
        self._entrada.returnPressed.connect(self._disparar)
        self._enviar = QPushButton("Enviar")
        self._enviar.clicked.connect(self._disparar)
        self._limpar = QPushButton("Limpar")
        self._limpar.clicked.connect(self.limpar)
        self._ver_contexto = QPushButton("Ver contexto")
        self._ver_contexto.clicked.connect(self.alternar_contexto)

        linha = QHBoxLayout()
        linha.addWidget(self._entrada, 1)
        linha.addWidget(self._enviar)
        linha.addWidget(self._limpar)
        linha.addWidget(self._ver_contexto)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._texto, 1)
        layout.addWidget(self._status)
        layout.addLayout(linha)

        self._contexto: str = ""

    # ------------------------------------------------------------ estado
    def definir_contexto(self, texto: str) -> None:
        self._contexto = texto
        if self._contexto_aberto:
            self._renderizar()

    def definir_status(self, texto: str) -> None:
        self._status.setText(texto)

    def usuario(self, texto: str) -> None:
        self._mensagens.append(("usuario", texto))
        self._renderizar()

    def iniciar_resposta(self) -> None:
        self._parcial = "▍"
        self._renderizar()

    def acrescentar(self, pedaco: str) -> None:
        if self._parcial.endswith("▍"):
            self._parcial = self._parcial[:-1]
        self._parcial += pedaco + "▍"
        self._renderizar()

    def concluir(self, texto: str) -> None:
        self._parcial = ""
        if texto.strip():
            self._mensagens.append(("assistente", texto.strip()))
        self._renderizar()

    def falha(self, erro: str) -> None:
        self._parcial = ""
        self._mensagens.append(("erro", f"⚠ {erro}"))
        self._renderizar()

    def limpar(self) -> None:
        self._mensagens.clear()
        self._parcial = ""
        self._contexto_aberto = False
        self._renderizar()
        self.limpou.emit()  # o serviço descarta o histórico junto com a UI

    def alternar_contexto(self) -> None:
        self._contexto_aberto = not self._contexto_aberto
        self._ver_contexto.setText("Fechar contexto" if self._contexto_aberto else "Ver contexto")
        self._renderizar()

    # ------------------------------------------------------------ render
    def _renderizar(self) -> None:
        partes: list[str] = []
        if self._contexto_aberto:
            partes.append("### 📄 Contexto enviado ao modelo\n")
            partes.append("```\n" + self._contexto.strip() + "\n```\n")
        for papel, texto in self._mensagens:
            if papel == "usuario":
                partes.append(f"**👤 Você:** {texto}\n")
            elif papel == "assistente":
                partes.append(f"**🤖 Assistente:**\n\n{texto}\n")
            else:
                partes.append(f"*{texto}*\n")
        if self._parcial:
            partes.append(f"**🤖 Assistente:**\n\n{self._parcial}\n")
        self._texto.setMarkdown("\n---\n".join(partes))
        barra = self._texto.verticalScrollBar()
        barra.setValue(barra.maximum())

    def _disparar(self) -> None:
        texto = self._entrada.text().strip()
        if not texto:
            return
        self._entrada.clear()
        self.enviar.emit(texto)
