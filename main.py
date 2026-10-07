#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tse_ds import analysis, ckan, charts, divulga, relatorio
from tse_ds.config import ANOS_PADRAO, PADROES_ARQUIVO, PASTA_ZIP, RECURSOS_OBRIGATORIOS, garantir_pastas
from tse_ds.http import ClienteHTTP, log


def _anos(valores: list[int] | None) -> tuple[int, ...]:
    return tuple(valores) if valores else ANOS_PADRAO


def _caminho_recurso(ano: int, nome: str) -> Path:
    padrao = PADROES_ARQUIVO.get(nome, "{recurso}_{ano}.zip")
    return PASTA_ZIP / padrao.format(ano=ano, recurso=nome)


def cmd_meta(args: argparse.Namespace) -> int:
    cliente = ClienteHTTP(rps=args.rps)
    garantir_pastas()
    for ano in _anos(args.ano):
        log(f"== Fontes de dados para {ano} ==")
        for recurso in ckan.listar_fontes(cliente, ano):
            situacao = "disponivel" if recurso.disponivel else "indisponivel (previsto pelo padrao do TSE)"
            log(f"  {recurso.nome_logico:28} {recurso.arquivo:45} {situacao}")
            log(f"  {'':28} {recurso.url}")
        try:
            config = divulga.obter_config(cliente)
            for item in divulga.eleicoes(config, ano):
                cargos = ", ".join(f"{c['ds']} ({c['cd']})" for c in item["cargos"])
                log(f"  divulgacao {ano}: codigo {item['codigo']} turno {item['turno']} - {item['nome']}")
                log(f"     cargos: {cargos}")
        except Exception as erro:
            log(f"  [aviso] plataforma de divulgacao indisponivel: {erro}")
        log("")
    return 0


def cmd_baixar(args: argparse.Namespace) -> int:
    cliente = ClienteHTTP(rps=args.rps)
    garantir_pastas()
    anos = _anos(args.ano)
    fonte = args.fonte
    tipos = tuple(t.strip() for t in args.tipo.split(",") if t.strip())

    if fonte in ("csv", "tudo"):
        for ano in anos:
            log(f"== Baixando CSVs {ano} ==")
            alvos = tuple(args.recurso) if args.recurso else RECURSOS_OBRIGATORIOS[ano]
            faltando = [
                nome
                for nome in alvos
                if args.force or not _caminho_recurso(ano, nome).exists()
            ]
            if not faltando:
                log(f"  [ok] todos os CSVs de {ano} ja estao em {PASTA_ZIP}")
                continue
            log(f"  [info] consultando o CKAN apenas para: {', '.join(faltando)}")
            recursos = ckan.resolver_recursos(cliente, ano, apenas=tuple(faltando))
            for recurso in recursos:
                try:
                    cliente.baixar(recurso.url, PASTA_ZIP / recurso.arquivo, force=args.force)
                except Exception as erro:
                    log(f"  [erro] {recurso.arquivo}: {erro}")
                    if recurso.disponivel:
                        return 1
                    log("  [aviso] recurso ainda nao publicado pelo TSE; seguindo")

    if fonte in ("json", "tudo"):
        for ano in anos:
            log(f"== Baixando arquivos JSON da divulgacao {ano} ==")
            baixar = [t for t in tipos if t in ("config", "acompanhamento")]
            if baixar:
                divulga.baixar_divulgacao(cliente, ano, tipos=tuple(baixar), codigo=args.eleicao, force=args.force)
            if "resultado" in tipos:
                codigo = args.eleicao or _primeira_eleicao(ano)
                if codigo is None:
                    log(f"  [erro] codigo de eleicao nao encontrado para {ano}")
                    return 1
                cargos = [int(c) for c in args.cargos.split(",") if c.strip()]
                ufs = [u.strip().upper() for u in args.ufs.split(",") if u.strip()] if args.ufs else None
                divulga.baixar_divulgacao(cliente, ano, tipos=("config",), codigo=codigo, force=False)
                log(f"== Resultados unificados (EA20) eleicao {codigo} cargos {cargos} ==")
                divulga.baixar_resultados_unificados(
                    cliente,
                    codigo,
                    cargos,
                    ufs=ufs,
                    limite=args.limite,
                    force=args.force,
                )
    return 0


def _primeira_eleicao(ano: int) -> int | None:
    try:
        config = divulga.obter_config(ClienteHTTP())
    except Exception:
        return None
    itens = divulga.eleicoes(config, ano)
    return itens[0]["codigo"] if itens else None


def cmd_analisar(args: argparse.Namespace) -> int:
    garantir_pastas()
    analysis.executar(_anos(args.ano), force=args.force)
    return 0


def _carregar_pacotes(anos: tuple[int, ...], force: bool = False) -> dict[int, dict]:
    return {ano: analysis.montar_pacote(ano, force=force) for ano in anos}


def cmd_graficos(args: argparse.Namespace) -> int:
    garantir_pastas()
    pacotes = _carregar_pacotes(_anos(args.ano), force=False)
    charts.gerar_graficos(pacotes)
    return 0


def cmd_relatorio(args: argparse.Namespace) -> int:
    garantir_pastas()
    pacotes = _carregar_pacotes(_anos(args.ano), force=False)
    relatorio.gerar(pacotes)
    return 0


def cmd_tudo(args: argparse.Namespace) -> int:
    status = cmd_baixar(args)
    if status:
        return status
    garantir_pastas()
    pacotes = analysis.executar(_anos(args.ano), force=args.force)
    charts.gerar_graficos(pacotes)
    relatorio.gerar(pacotes)
    return 0


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Bot de coleta e analise de dados abertos do TSE (eleicoes 2024 e 2026).",
    )
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--rps", type=float, default=8.0, help="requisicoes por segundo (limite do TSE: 100)")
    sub = parser.add_subparsers(dest="comando", required=True)

    meta = sub.add_parser("meta", parents=[comum], help="lista as fontes de dados disponiveis para cada ano")
    meta.add_argument("--ano", type=int, nargs="+", action="extend", help="anos (padrao: 2024 2026)")
    meta.set_defaults(funcao=cmd_meta)

    baixar = sub.add_parser("baixar", parents=[comum], help="baixa os arquivos do TSE")
    baixar.add_argument("--ano", type=int, nargs="+", action="extend", help="anos (padrao: 2024 2026)")
    baixar.add_argument("--fonte", choices=("csv", "json", "tudo"), default="tudo")
    baixar.add_argument("--recurso", nargs="+", help="restrange aos recursos CSV nomeados (ex.: consulta_cand)")
    baixar.add_argument(
        "--tipo",
        default="config,acompanhamento",
        help="tipos de arquivo JSON: config, acompanhamento, resultado (ex.: 'config,acompanhamento,resultado')",
    )
    baixar.add_argument("--eleicao", type=int, help="codigo da eleicao (ex.: 6257 presidencia 2026)")
    baixar.add_argument("--cargos", default="1", help="cargos para o modo resultado (ex.: '1,3')")
    baixar.add_argument("--ufs", help="restringe o modo resultado a UFs (ex.: 'SP,RJ')")
    baixar.add_argument("--limite", type=int, help="maximo de municipios no modo resultado")
    baixar.add_argument("--force", action="store_true", help="refaz download mesmo se o arquivo existir")
    baixar.set_defaults(funcao=cmd_baixar)

    analisar = sub.add_parser("analisar", parents=[comum], help="gera as tabelas tratadas")
    analisar.add_argument("--ano", type=int, nargs="+", action="extend")
    analisar.add_argument("--force", action="store_true")
    analisar.set_defaults(funcao=cmd_analisar)

    graficos = sub.add_parser("graficos", parents=[comum], help="gera os graficos PNG")
    graficos.add_argument("--ano", type=int, nargs="+", action="extend")
    graficos.set_defaults(funcao=cmd_graficos)

    relatorio_cmd = sub.add_parser("relatorio", parents=[comum], help="gera o relatorio em markdown")
    relatorio_cmd.add_argument("--ano", type=int, nargs="+", action="extend")
    relatorio_cmd.set_defaults(funcao=cmd_relatorio)

    tudo = sub.add_parser("tudo", parents=[comum], help="pipeline completo: baixar, analisar, graficos e relatorio")
    tudo.add_argument("--ano", type=int, nargs="+", action="extend")
    tudo.add_argument("--fonte", choices=("csv", "json", "tudo"), default="tudo")
    tudo.add_argument("--recurso", nargs="+")
    tudo.add_argument("--tipo", default="config,acompanhamento")
    tudo.add_argument("--eleicao", type=int)
    tudo.add_argument("--cargos", default="1")
    tudo.add_argument("--ufs", help="restringe o modo resultado a UFs (ex.: 'SP,RJ')")
    tudo.add_argument("--limite", type=int)
    tudo.add_argument("--force", action="store_true")
    tudo.set_defaults(funcao=cmd_tudo)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = criar_parser().parse_args(argv)
    return args.funcao(args)


if __name__ == "__main__":
    sys.exit(main())
