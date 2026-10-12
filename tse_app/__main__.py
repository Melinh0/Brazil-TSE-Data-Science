from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .config import ANOS
from .store import FonteDados
from .ui.janela import JanelaPrincipal


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tse_app",
        description="App desktop com mapa, candidatos, gráficos e chat dos resultados do TSE.",
    )
    parser.add_argument("--ano", type=int, default=2024, choices=ANOS, help="ano inicial")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="roda as verificações da interface/dados e encerra",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="com --selftest, também faz uma chamada real ao Ollama Cloud",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = criar_parser().parse_args(argv)
    aplicacao = QApplication.instance() or QApplication(sys.argv)
    aplicacao.setApplicationName("Brazil TSE — Visualizador")
    fonte = FonteDados()
    janela = JanelaPrincipal(fonte, ano=args.ano)
    if args.selftest:
        from .selftest import executar

        codigo = executar(janela, chat=args.chat)
        janela.aguardar_trabalhadores(timeout_ms=60_000)
        janela.close()
        return codigo
    janela.show()
    return aplicacao.exec()


if __name__ == "__main__":
    sys.exit(main())
