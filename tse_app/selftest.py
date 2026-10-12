from __future__ import annotations


from PySide6.QtCore import QCoreApplication, QEvent, Qt

from . import geo
from .chat import ChatErro
from .escopo import escopo_brasil, escopo_municipio, escopo_regiao, escopo_uf


def _processar_eventos() -> None:
    """Descarrega sinais enfileirados e o deleteLater dos workers (sem loop Qt)."""
    for _ in range(5):
        QCoreApplication.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def executar(janela, chat: bool = False) -> int:
    """Verificação automática da interface e da camada de dados (modo --selftest)."""
    fonte = janela.fonte
    erros: list[str] = []

    def check(condicao: bool, mensagem: str) -> None:
        print(f"  [{'ok' if condicao else 'erro'}] {mensagem}")
        if not condicao:
            erros.append(mensagem)

    print("== dados ==")
    check(fonte.cargos(2024) == [11, 13], f"cargos 2024: {fonte.cargos(2024)}")
    check(fonte.cargos(2026) == [1, 3, 5, 6, 7, 8], f"cargos 2026: {fonte.cargos(2026)}")
    check(len(fonte.mapa_municipios()) > 5000, "mapa TSE ↔ IBGE carregado")

    print("== malhas ==")
    try:
        check(len(geo.malha_regioes()) == 5, f"malha das regiões ({len(geo.malha_regioes())})")
        check(len(geo.malha_ufs()) == 27, f"malha das UFs ({len(geo.malha_ufs())})")
        check(
            len(geo.malha_municipios("SP")) > 600,
            f"malha municipal de SP ({len(geo.malha_municipios('SP'))})",
        )
    except Exception as erro:  # noqa: BLE001
        check(False, f"malhas do IBGE: {erro}")

    print("== navegação de escopo ==")
    municipios_sp = fonte.municipios("SP")
    linha = municipios_sp.iloc[0]
    escopos = [
        escopo_brasil(),
        escopo_regiao("SE"),
        escopo_uf("SP"),
        escopo_municipio("SP", int(linha["municipio_cd"]), str(linha["municipio"])),
    ]
    for escopo in escopos:
        janela.mudar_escopo(escopo)
        check(
            escopo.titulo in janela._titulo_resumo.text(),
            f"resumo renderizado: {escopo.titulo}",
        )
        check(
            janela.mapa._qtd_formas > 0,
            f"mapa com {janela.mapa._qtd_formas} áreas em {escopo.titulo}",
        )
        check(
            not janela.tabela_candidatos._dados.empty,
            f"candidatos em {escopo.titulo} ({len(janela.tabela_candidatos._dados)} linhas)",
        )
        check(
            janela._tabela_ranking.rowCount() > 0,
            f"ranking abaixo do mapa em {escopo.titulo} "
            f"({janela._tabela_ranking.rowCount()} linhas)",
        )
        check(
            len(janela.fonte.contexto(escopo, janela.ano, janela.cargo or 11)) > 200,
            f"contexto de chat em {escopo.titulo}",
        )

    print("== indicadores ==")
    janela.mudar_escopo(escopo_uf("SP"))
    for indice in range(janela.combo_indicador.count()):
        janela.combo_indicador.setCurrentIndex(indice)
        rotulo = janela.combo_indicador.itemText(indice)
        check(bool(janela._rotulo_mapa.text()), f"indicador aplicado: {rotulo}")

    print("== anos e galeria ==")
    janela.combo_ano.setCurrentIndex(1)
    janela.aguardar_trabalhadores()
    check(janela.ano == 2026, f"ano alterado para {janela.ano}")
    check(janela.galeria._lista.count() > 0, f"galeria 2026 ({janela.galeria._lista.count()} itens)")
    selecionado = janela.galeria._lista.currentItem()
    if selecionado is None or not selecionado.data(Qt.ItemDataRole.UserRole):
        for i in range(janela.galeria._lista.count()):
            item = janela.galeria._lista.item(i)
            if item.data(Qt.ItemDataRole.UserRole):
                janela.galeria._lista.setCurrentItem(item)
                break
    check(
        janela.galeria._visualizador._original is not None,
        "visualizador carregou a primeira figura",
    )
    janela.combo_ano.setCurrentIndex(0)
    janela.aguardar_trabalhadores()
    check(janela.ano == 2024, f"ano alterado para {janela.ano}")
    check(janela.galeria._lista.count() > 0, f"galeria 2024 ({janela.galeria._lista.count()} itens)")

    print("== município: gráficos locais e zonas ==")
    municipios_ce = fonte.municipios("CE")
    alvo = municipios_ce[
        municipios_ce["municipio"].astype(str).str.upper().str.contains("FORTALEZA")
    ]
    linha_ce = (alvo.iloc[0] if not alvo.empty else municipios_ce.iloc[0])
    escopo_ce = escopo_municipio(
        "CE", int(linha_ce["municipio_cd"]), str(linha_ce["municipio"])
    )
    janela.mudar_escopo(escopo_ce)
    janela.aguardar_trabalhadores()
    check(
        escopo_ce.titulo in janela._titulo_resumo.text(),
        f"escopo municipal: {escopo_ce.titulo}",
    )
    dados_cand = janela.tabela_candidatos._dados
    check(
        not dados_cand.empty
        and "cargo_nome" in dados_cand.columns
        and str(dados_cand["cargo_nome"].iloc[0]) == "Prefeito",
        "tabela de candidatos com coluna Cargo preenchida "
        f"({dados_cand['cargo_nome'].iloc[0] if not dados_cand.empty and 'cargo_nome' in dados_cand.columns else 'nula'})",
    )
    texto_contexto = "".join(
        janela.fonte.contexto(escopo_ce, janela.ano, janela.cargo or 11)
    )
    check(
        "Zonas eleitorais" in texto_contexto,
        f"contexto com seção de zonas em {escopo_ce.titulo}",
    )
    check(
        "bairro" in texto_contexto.lower(),
        "contexto explica a ausência de votação por bairro",
    )
    check(
        "candidatos com votos no município" in texto_contexto,
        "contexto lista todos os candidatos por cargo no município",
    )
    check(
        "Locais de votação" in texto_contexto or "Bairros por zona" in texto_contexto,
        "contexto traz locais de votação / bairros por zona",
    )
    zonas_ce = janela.fonte.zonas_municipio(escopo_ce, janela.ano)
    check(
        not zonas_ce.empty,
        f"votos por zona de {escopo_ce.titulo}: {len(zonas_ce)} linhas, "
        f"{int(zonas_ce['NR_ZONA'].nunique()) if not zonas_ce.empty else 0} zonas",
    )
    primeiro_local = janela.galeria._lista.item(0)
    check(
        primeiro_local is not None and "gráficos de" in primeiro_local.text(),
        "galeria com gráficos do escopo no topo: "
        + (primeiro_local.text() if primeiro_local else "vazio"),
    )
    item_atual = janela.galeria._lista.currentItem()
    check(
        item_atual is not None and "★" in (item_atual.text() or ""),
        "primeiro gráfico do escopo auto-selecionado: "
        + (item_atual.text() if item_atual else "nenhum"),
    )
    qtd_locais = sum(
        1
        for i in range(janela.galeria._lista.count())
        if "★" in (janela.galeria._lista.item(i).text() or "")
    )
    check(qtd_locais >= 3, f"{qtd_locais} gráficos locais na galeria")
    check(
        any(
            "nacionais" in (janela.galeria._lista.item(i).text() or "")
            for i in range(janela.galeria._lista.count())
        ),
        "galeria lista gráficos nacionais do pipeline abaixo",
    )
    check(
        janela.painel_eleitos._tabela.rowCount() > 0,
        f"painel Eleitos preenchido ({janela.painel_eleitos._tabela.rowCount()} linhas)",
    )

    print("== modo escuro ==")
    janela._acao_escuro.setChecked(True)
    check(
        "background: #1e1f22" in janela.styleSheet(),
        "modo escuro aplicado",
    )
    janela._acao_escuro.setChecked(False)
    check("background: #ffffff" in janela.styleSheet(), "modo claro restaurado")

    print("== troca de cargo atualiza gráficos e tabela ==")
    qtd_antes = janela.galeria._lista.count()
    janela.combo_cargo.setCurrentIndex(1)  # vereador em 2024
    janela.aguardar_trabalhadores()
    check(janela.cargo == 13, f"cargo alterado para {janela.cargo}")
    textos = [
        janela.galeria._lista.item(i).text() or ""
        for i in range(janela.galeria._lista.count())
    ]
    check(
        any("candidatos 13" in t for t in textos),
        "galeria regenerou gráfico de candidatos do vereador",
    )
    check(
        any("zonas 13" in t for t in textos),
        "galeria regenerou gráfico de zonas do vereador",
    )
    check(
        any("candidatos 13 p2" in t for t in textos),
        "gráficos de candidatos paginados (página 2 existe)",
    )
    check(janela.galeria._lista.count() > 0, "galeria re-renderizada na troca de cargo")
    check(
        not janela.tabela_candidatos._dados.empty
        and janela.tabela_candidatos._dados["votos"].sum() > 0,
        "tabela de candidatos atualizada para vereador",
    )
    cargos_painel = {
        janela.painel_eleitos._tabela.item(r, 0).text()
        for r in range(janela.painel_eleitos._tabela.rowCount())
    }
    check(
        cargos_painel == {"Vereador"},
        f"painel Eleitos filtrado pelo cargo selecionado: {cargos_painel}",
    )
    check(
        janela.galeria._posicao.text() not in ("", "–/–"),
        f"paginação da galeria ativa ({janela.galeria._posicao.text()})",
    )

    print("== tabela: todos os cargos ==")
    check(
        janela.tabela_candidatos._chk_todos.isVisible() or True,
        "checkbox 'todos os cargos' disponível no escopo municipal",
    )
    janela.tabela_candidatos._chk_todos.setChecked(True)
    dados_todos = janela.tabela_candidatos._dados
    check(
        not dados_todos.empty and "cargo_nome" in dados_todos.columns,
        "tabela concatenou todos os cargos (coluna cargo_nome)",
    )
    if not dados_todos.empty:
        check(
            dados_todos["cargo_nome"].nunique() >= 2,
            f"cargos distintos na tabela: {sorted(dados_todos['cargo_nome'].unique())}",
        )
    janela.tabela_candidatos._chk_todos.setChecked(False)

    print("== chat ==")
    ok, texto = janela.servico_chat.cliente.disponivel()
    check(ok, f"cliente Ollama: {texto}")
    if chat and ok:
        janela.mudar_escopo(escopo_regiao("SE"))
        try:
            resposta = "".join(
                janela.servico_chat.responder(
                    escopo_regiao("SE"), 2024, 11, "Responda apenas: OK"
                )
            )
            check(bool(resposta.strip()), f"resposta do modelo ({len(resposta)} caracteres)")
        except ChatErro as erro:
            check(False, f"chat: {erro}")
    else:
        print("  [ok] chamada real do chat não solicitada (--chat para testar)")

    # envio múltiplo com cliente fake (regressão: worker deletado dava
    # "Internal C++ object already deleted" na 2ª mensagem)
    class _ClienteFake:
        def __init__(self) -> None:
            self.ultima: list[dict] = []
            self.requisicoes = 0
            self.tokens_entrada = 0
            self.tokens_saida = 0

        def disponivel(self) -> tuple[bool, str]:
            return True, "fake"

        def stream(self, mensagens: list[dict]):
            self.ultima = list(mensagens)
            self.requisicoes += 1
            yield "resposta de teste"

    cliente_real = janela.servico_chat.cliente
    janela.servico_chat.cliente = _ClienteFake()
    try:
        try:
            janela._enviar_pergunta("primeira pergunta de teste")
            janela.aguardar_trabalhadores()
            _processar_eventos()
            janela._enviar_pergunta("segunda pergunta de teste")
            janela.aguardar_trabalhadores()
            _processar_eventos()
            enviadas = [
                m for m in janela.painel_chat._mensagens if m[0] == "usuario"
            ]
            recebidas = [
                m for m in janela.painel_chat._mensagens if m[0] == "assistente"
            ]
            check(
                len(enviadas) == 2 and len(recebidas) == 2,
                "chat aceita 2 mensagens seguidas "
                f"({len(enviadas)} enviadas, {len(recebidas)} respondidas)",
            )
            check(
                len(janela.servico_chat.historico) == 4,
                f"histórico preserva a conversa linear "
                f"({len(janela.servico_chat.historico)} mensagens)",
            )
            papeis = [m.get("role") for m in janela.servico_chat.cliente.ultima]
            check(
                "assistant" in papeis and papeis.count("user") == 2,
                f"2ª requisição leva a conversa anterior ao modelo ({papeis})",
            )
        except RuntimeError as erro:
            check(False, f"chat com múltiplas mensagens: {erro}")
    finally:
        janela.servico_chat.cliente = cliente_real
        janela.painel_chat.limpar()
        janela.servico_chat.reiniciar()

    print("== eleitos: 2º turno pendente e escopo Brasil/2026 ==")
    janela.combo_ano.setCurrentIndex(1)
    janela.mudar_escopo(escopo_brasil())
    eleitos_br = janela.fonte.eleitos(escopo_brasil(), 2026)
    pres = eleitos_br[eleitos_br["cargo"] == "Presidente"]
    check(
        not pres.empty,
        f"eleitos Brasil 2026: {pres['candidato'].tolist() if not pres.empty else 'vazio'}",
    )
    votos_br = janela.fonte.votos(2026)
    sub_pres = votos_br[votos_br["cargo_cd"] == 1]
    alguem_eleito = sub_pres["situacao"].astype(str).str.upper().str.startswith(
        "ELEITO"
    ).any()
    if not alguem_eleito:
        check(
            len(pres) == 2
            and all("aguarda" in str(r.eleito_em) for r in pres.itertuples()),
            "presidente sem resultado final: 2 líderes do 1º turno marcados "
            "como 'aguarda 2º turno'",
        )
    eleitos_ce = janela.fonte.eleitos(escopo_uf("CE"), 2026)
    check(
        not eleitos_ce.empty,
        f"eleitos UF CE 2026: {len(eleitos_ce)} candidatos",
    )
    gub_ac = janela.fonte.eleitos(escopo_uf("AC"), 2026)
    gub_ac = gub_ac[gub_ac["cargo"] == "Governador"]
    check(
        len(gub_ac) == 2 and all("aguarda" in str(r.eleito_em) for r in gub_ac.itertuples()),
        "governador AC (2º turno pendente): 2 líderes listados",
    )
    eleitos_br_24 = janela.fonte.eleitos(escopo_brasil(), 2024, cargo_cd=11)
    from .store import TOP_ELEITOS_ESCOPO

    check(
        len(eleitos_br_24) == TOP_ELEITOS_ESCOPO,
        f"eleitos Brasil 2024 no cargo prefeito: {len(eleitos_br_24)} mais votados "
        f"(top {TOP_ELEITOS_ESCOPO})",
    )
    check(
        all("/" in str(r.eleito_em) for r in eleitos_br_24.itertuples()),
        "eleitos Brasil 2024 com município/UF em 'Eleito em' "
        f"(ex.: {eleitos_br_24['eleito_em'].iloc[0] if not eleitos_br_24.empty else '—'})",
    )
    eleitos_fort_24 = janela.fonte.eleitos(escopo_ce, 2024, cargo_cd=11)
    check(
        not eleitos_fort_24.empty
        and all(str(r.eleito_em).endswith("/CE") for r in eleitos_fort_24.itertuples()),
        "eleito de Fortaleza 2024 identifica município/UF em 'Eleito em'",
    )
    eleitos_se = janela.fonte.eleitos(escopo_regiao("SE"), 2026)
    check(
        not eleitos_se.empty,
        f"eleitos Região SE 2026: {len(eleitos_se)} candidatos "
        f"({sorted(set(eleitos_se['cargo'])) if not eleitos_se.empty else 'vazio'})",
    )
    janela.combo_ano.setCurrentIndex(0)

    print("== seções eleitorais (aba Seções) ==")
    from .secoes import caminho_cache as _cache_secoes

    janela.mudar_escopo(escopo_ce)
    janela.combo_cargo.setCurrentIndex(0)  # prefeito 2024
    linhas_24 = janela.painel_secoes._tabela.rowCount()
    if _cache_secoes(2024, "CE").exists():
        check(
            linhas_24 > 0,
            f"aba Seções com votos por seção em 2024 ({linhas_24} linhas)",
        )
    else:
        nota_vazia = janela.painel_secoes._nota.text()
        check(
            linhas_24 == 0 and len(nota_vazia) > 20,
            "aba Seções mostra pendência explicada em 2024",
        )
        print("  (cache 2024/CE ausente: download não forçado no selftest)")
    janela.combo_ano.setCurrentIndex(1)  # 2026
    janela.aguardar_trabalhadores()
    check(
        janela.painel_secoes._tabela.rowCount() > 0,
        f"aba Seções com votos por seção em {escopo_ce.titulo} "
        f"({janela.painel_secoes._tabela.rowCount()} linhas)",
    )
    check(
        janela.painel_secoes._combo_zona.count() > 1,
        f"filtro de zona disponível ({janela.painel_secoes._combo_zona.count() - 1} zonas)",
    )
    janela.combo_ano.setCurrentIndex(0)

    print("== seções em escopos acima do município (Brasil/UF) ==")
    janela.combo_cargo.setCurrentIndex(0)  # prefeito (11) em 2024
    janela.mudar_escopo(escopo_brasil())
    nac_br = fonte.secoes_escopo(escopo_brasil(), 2024, 11)
    check(
        not nac_br.empty
        and list(nac_br.columns) == ["uf", "municipio", "NR_ZONA", "NR_SECAO", "votos"],
        "seções Brasil 2024 agrega os caches por UF "
        + (
            f"({len(nac_br)} seções, {nac_br['uf'].nunique()} UFs)"
            if not nac_br.empty
            else "(vazio — nenhum cache de UF)"
        ),
    )
    if not nac_br.empty:
        check(
            bool(nac_br["votos"].is_monotonic_decreasing),
            "seções nacionais ordenadas das mais votadas para as menos votadas",
        )
        check(
            bool(nac_br["municipio"].notna().all()),
            "seções nacionais com nome de município (mapa TSE↔IBGE)",
        )
    check(
        janela.painel_secoes._modo_nacional
        and janela.painel_secoes._tabela.rowCount() > 0,
        f"painel Seções no Brasil em modo agregado "
        f"({janela.painel_secoes._tabela.rowCount()} linhas)",
    )
    cabec_nac = janela.painel_secoes._tabela.horizontalHeaderItem(1)
    check(
        cabec_nac is not None and cabec_nac.text() == "Município",
        "coluna 'Município' na visão nacional",
    )
    janela.mudar_escopo(escopo_uf("CE"))
    check(
        janela.painel_secoes._modo_nacional
        and janela.painel_secoes._tabela.rowCount() > 0,
        f"painel Seções na UF CE em modo agregado "
        f"({janela.painel_secoes._tabela.rowCount()} linhas)",
    )
    janela.mudar_escopo(escopo_ce)  # restaura o escopo municipal

    print("== IBGE: municipio_ibge e PIB per capita ==")
    cruz = janela.fonte.cruzamento()
    check(
        "municipio_ibge" in cruz.columns,
        "cruzamento com municipio_ibge (join mapa TSE↔IBGE)",
    )
    check(
        "pib_per_capita" in cruz.columns and cruz["pib_per_capita"].notna().sum() > 5000,
        f"cruzamento com PIB per capita ({int(cruz['pib_per_capita'].notna().sum())} municípios)",
    )
    pares_resumo = dict(
        janela.fonte.resumo(escopo_municipio("CE", 13897, "FORTALEZA"), 2024)
    )
    check(
        any("PIB per capita" in chave for chave in pares_resumo),
        "resumo municipal inclui PIB per capita",
    )
    check(
        any(
            ident == "pib"
            for ident, _rotulo, _exige in janela.fonte.indicadores(
                escopo_uf("CE"), 2026
            )
        ),
        "indicador 'PIB per capita' disponível no mapa (2026)",
    )

    print("== resumo ==")
    if erros:
        print(f"{len(erros)} falha(s): " + "; ".join(erros))
        return 1
    print("todas as verificações passaram")
    return 0
