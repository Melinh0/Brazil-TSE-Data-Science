from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import AMBIENTE, ODSELE_BASE, PASTA_JSON, RESULTADOS_BASE, ROTULOS_CARGO
from .http import ClienteHTTP, log

URL_CONFIG_ELEICOES = f"{RESULTADOS_BASE}/{AMBIENTE}/comum/config/ele-c.json"


def _numero(valor) -> float | int:
    if valor is None:
        return 0
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (int, float)):
        return valor
    texto = str(valor).strip()
    if not texto:
        return 0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = float(texto)
    except ValueError:
        return 0
    return int(numero) if numero.is_integer() and abs(numero) < 1e15 else numero


def obter_config(cliente: ClienteHTTP, force: bool = False) -> dict:
    destino = PASTA_JSON / "ele-c.json"
    if destino.exists() and not force:
        return json.loads(destino.read_text(encoding="utf-8"))
    dados = cliente.get_json(URL_CONFIG_ELEICOES)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados


def eleicoes(config: dict, ano: int | None = None) -> list[dict]:
    encontradas: list[dict] = []
    for pleito in config.get("pl", []):
        ciclo = pleito.get("c", "")
        if ano is not None and not ciclo.endswith(str(ano)):
            continue
        for eleicao in pleito.get("e", []):
            cargos = [
                {"cd": int(cargo["cd"]), "ds": cargo.get("ds", "")}
                for abr in eleicao.get("abr", [])
                for cargo in abr.get("cp", [])
            ]
            ufs = sorted({abr.get("cd") for abr in eleicao.get("abr", []) if abr.get("cd")})
            encontradas.append(
                {
                    "ano": int(ciclo.replace("ele", "")) if ciclo.replace("ele", "").isdigit() else None,
                    "ciclo": ciclo,
                    "pleito": int(pleito["cd"]),
                    "codigo": int(eleicao["cd"]),
                    "nome": eleicao.get("nm", ""),
                    "turno": eleicao.get("t", ""),
                    "data": pleito.get("dt", ""),
                    "cargos": cargos,
                    "ufs": ufs,
                }
            )
    return encontradas


def _pasta_eleicao(ciclo: str, codigo: int) -> Path:
    return PASTA_JSON / ciclo / str(codigo)


def url_config_municipios(ciclo: str, codigo: int) -> str:
    return f"{RESULTADOS_BASE}/{AMBIENTE}/{ciclo}/{codigo}/config/mun-e{codigo:06d}-cm.json"


def url_acompanhamento(ciclo: str, codigo: int, uf: str) -> str:
    return f"{RESULTADOS_BASE}/{AMBIENTE}/{ciclo}/{codigo}/dados/{uf}/{uf}-e{codigo:06d}-ab.json"


def url_resultado_unificado(
    ciclo: str,
    codigo: int,
    uf: str,
    cod_municipio: str,
    cargo: int,
    zona: str | None = None,
) -> str:
    base = f"{uf}{cod_municipio.zfill(5)}"
    if zona:
        base += f"-z{zona.zfill(4)}"
    return (
        f"{RESULTADOS_BASE}/{AMBIENTE}/{ciclo}/{codigo}/dados/{uf}/"
        f"{base}-c{cargo:04d}-e{codigo:06d}-u.json"
    )


def _baixar_json(cliente: ClienteHTTP, url: str, destino: Path, force: bool) -> tuple[Path | None, Exception | None]:
    try:
        return cliente.baixar(url, destino, force=force, progresso=False), None
    except Exception as erro:  # noqa: BLE001 - rede instavel e toleravel
        return None, erro


def _status_http(erro: Exception | None) -> int | None:
    resposta = getattr(erro, "response", None)
    return getattr(resposta, "status_code", None)


def baixar_divulgacao(
    cliente: ClienteHTTP,
    ano: int,
    tipos: tuple[str, ...] = ("config", "acompanhamento"),
    codigo: int | None = None,
    force: bool = False,
    trabalhadores: int = 6,
) -> list[Path]:
    config = obter_config(cliente, force=force)
    alvos = [item for item in eleicoes(config, ano) if codigo is None or item["codigo"] == codigo]
    if not alvos:
        log(f"  [aviso] nenhuma eleicao de {ano} encontrada na configuracao do TSE")
        return []

    pendentes: list[tuple[str, Path]] = []
    for item in alvos:
        ciclo, eleicao = item["ciclo"], item["codigo"]
        pasta = _pasta_eleicao(ciclo, eleicao)
        if "config" in tipos:
            pendentes.append((url_config_municipios(ciclo, eleicao), pasta / f"mun-e{eleicao:06d}-cm.json"))
        if "acompanhamento" in tipos:
            for uf in ["br", *[u.lower() for u in item["ufs"]]]:
                pendentes.append((url_acompanhamento(ciclo, eleicao, uf), pasta / f"{uf}-e{eleicao:06d}-ab.json"))
    if not pendentes:
        return []

    baixados: list[Path] = []
    existentes = sum(
        1 for _, destino in pendentes if not force and destino.exists() and destino.stat().st_size > 0
    )
    if not force:
        pendentes = [
            (url, destino)
            for url, destino in pendentes
            if not (destino.exists() and destino.stat().st_size > 0)
        ]
    if not pendentes:
        log(f"  [ok] arquivos da divulgacao de {ano}: {existentes} ja existentes, nada a baixar")
        return []

    if trabalhadores > 1 and len(pendentes) > 4:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        novos, nao_publicados, falhas = 0, 0, 0
        with ThreadPoolExecutor(max_workers=trabalhadores) as pool:
            futuros = {
                pool.submit(_baixar_json, cliente, url, destino, force): (url, destino)
                for url, destino in pendentes
            }
            for futuro in as_completed(futuros):
                url, _destino = futuros[futuro]
                caminho, erro = futuro.result()
                if caminho is None:
                    if _status_http(erro) == 404:
                        nao_publicados += 1
                    else:
                        falhas += 1
                        log(f"  [aviso] indisponivel ({erro.__class__.__name__}): {url}")
                else:
                    novos += 1
                    baixados.append(caminho)
        log(
            f"  [ok] arquivos da divulgacao de {ano}: {novos} baixados, {existentes} ja existentes, "
            f"{nao_publicados} nao publicados (404), {falhas} falhas"
        )
        return baixados

    for url, destino in pendentes:
        try:
            baixados.append(cliente.baixar(url, destino, force))
        except Exception as erro:
            log(f"  [aviso] indisponivel ({erro.__class__.__name__}): {url}")
    return baixados


def parse_acompanhamento(dados: dict) -> pd.DataFrame:
    linhas = []
    for item in dados.get("abr", []) or []:
        bloco_s = item.get("s") or {}
        bloco_e = item.get("e") or {}
        linhas.append(
            {
                "codigo_abrangencia": item.get("cdabr", ""),
                "tipo_abrangencia": item.get("tpabr", ""),
                "andamento": item.get("and", ""),
                "data": item.get("dt", ""),
                "hora": item.get("ht", ""),
                "secoes_totais": _numero(bloco_s.get("ts")),
                "secoes_totalizadas": _numero(bloco_s.get("st")),
                "pct_secoes": _numero(bloco_s.get("pst")),
                "eleitores": _numero(bloco_e.get("te")),
                "comparecimento": _numero(bloco_e.get("c")),
                "pct_comparecimento": _numero(bloco_e.get("pc")),
                "abstencao": _numero(bloco_e.get("a")),
                "pct_abstencao": _numero(bloco_e.get("pa")),
                "votos_brancos": _numero(bloco_e.get("cb")),
                "votos_nulos": _numero(bloco_e.get("nb")),
            }
        )
    return pd.DataFrame(linhas)


def carregar_acompanhamento(ano: int, codigo: int, uf: str = "br") -> pd.DataFrame | None:
    config = json.loads((PASTA_JSON / "ele-c.json").read_text(encoding="utf-8"))
    item = next((x for x in eleicoes(config, ano) if x["codigo"] == codigo), None)
    if item is None:
        return None
    caminho = _pasta_eleicao(item["ciclo"], codigo) / f"{uf}-e{codigo:06d}-ab.json"
    if not caminho.exists():
        return None
    return parse_acompanhamento(json.loads(caminho.read_text(encoding="utf-8")))


def carregar_todos_acompanhamentos(ano: int) -> pd.DataFrame | None:
    config_caminho = PASTA_JSON / "ele-c.json"
    if not config_caminho.exists():
        return None
    config = json.loads(config_caminho.read_text(encoding="utf-8"))
    quadros = []
    for item in eleicoes(config, ano):
        quadro = carregar_acompanhamento(ano, item["codigo"], "br")
        if quadro is not None and not quadro.empty:
            quadro.insert(0, "codigo_eleicao", item["codigo"])
            quadro.insert(0, "nome_eleicao", item["nome"])
            quadro.insert(0, "ano", ano)
            quadros.append(quadro)
    if not quadros:
        return None
    return pd.concat(quadros, ignore_index=True)


def carregar_config_municipios(codigo: int) -> list[dict]:
    config = json.loads((PASTA_JSON / "ele-c.json").read_text(encoding="utf-8"))
    item = next((x for x in eleicoes(config) if x["codigo"] == codigo), None)
    if item is None:
        return []
    caminho = _pasta_eleicao(item["ciclo"], codigo) / f"mun-e{codigo:06d}-cm.json"
    if not caminho.exists():
        return []
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    linhas = []
    for uf in dados.get("abr", []) or []:
        for municipio in uf.get("mu", []) or []:
            linhas.append(
                {
                    "uf": uf.get("cd", "").upper(),
                    "cod_municipio": municipio.get("cd", ""),
                    "cod_ibge": municipio.get("cdi", ""),
                    "municipio": municipio.get("nm", ""),
                    "zonas": municipio.get("z", []),
                }
            )
    return linhas


def baixar_resultados_unificados(
    cliente: ClienteHTTP,
    codigo: int,
    cargos: list[int],
    ufs: list[str] | None = None,
    limite: int | None = None,
    force: bool = False,
) -> tuple[int, int]:
    municipios = carregar_config_municipios(codigo)
    if not municipios:
        log("  [erro] configuracao de municipios (EA12) ausente; rode 'baixar --fonte json' primeiro")
        return 0, 0

    config = json.loads((PASTA_JSON / "ele-c.json").read_text(encoding="utf-8"))
    item = next((x for x in eleicoes(config) if x["codigo"] == codigo), None)
    if item is None:
        log(f"  [erro] eleicao {codigo} desconhecida")
        return 0, 0
    ciclo = item["ciclo"]

    selecao = [m for m in municipios if ufs is None or m["uf"] in {u.upper() for u in ufs}]
    total = len(selecao) * len(cargos)
    if limite:
        selecao = selecao[: max(1, limite // max(len(cargos), 1))]

    baixados, falhas = 0, 0
    for municipio in selecao:
        for cargo in cargos:
            destino = (
                _pasta_eleicao(ciclo, codigo)
                / "resultado"
                / municipio["uf"]
                / f"{municipio['uf']}{municipio['cod_municipio']}-c{cargo:04d}-e{codigo:06d}-u.json"
            )
            url = url_resultado_unificado(ciclo, codigo, municipio["uf"], municipio["cod_municipio"], cargo)
            try:
                cliente.baixar(url, destino, force=force)
                baixados += 1
            except Exception:
                falhas += 1
    log(f"  [ok] resultados unificados: {baixados} baixados, {falhas} falhas de {total} alvos")
    return baixados, falhas


def parse_resultado_unificado(dados: dict) -> pd.DataFrame:
    linhas = []
    for cargo in dados.get("carg", []) or []:
        cd = str(cargo.get("cd", ""))
        nome_cargo = ROTULOS_CARGO.get(cd, cargo.get("nmn", cd))
        for agrupamento in cargo.get("agr", []) or []:
            for partido in agrupamento.get("par", []) or []:
                for candidato in partido.get("cand", []) or []:
                    linhas.append(
                        {
                            "cargo_cd": int(cd) if cd.isdigit() else cd,
                            "cargo": nome_cargo,
                            "agremiacao": agrupamento.get("nm", ""),
                            "partido": partido.get("sg", ""),
                            "partido_nome": partido.get("nm", ""),
                            "candidato": candidato.get("nm", ""),
                            "urna": candidato.get("nmu", ""),
                            "votos": _numero(candidato.get("vap")),
                            "pct": _numero(candidato.get("pvap")),
                            "eleito": candidato.get("e", ""),
                            "situacao": candidato.get("st", ""),
                        }
                    )
    return pd.DataFrame(linhas)


def carregar_resultados_unificados(codigo: int, cargos: list[int] | None = None) -> pd.DataFrame:
    config = json.loads((PASTA_JSON / "ele-c.json").read_text(encoding="utf-8"))
    item = next((x for x in eleicoes(config) if x["codigo"] == codigo), None)
    if item is None:
        return pd.DataFrame()
    raiz = _pasta_eleicao(item["ciclo"], codigo) / "resultado"
    if not raiz.exists():
        return pd.DataFrame()
    quadros = []
    for caminho in sorted(raiz.rglob("*.json")):
        nome = caminho.stem
        if "-c" not in nome:
            continue
        cargo = int(nome.split("-c")[1][:4])
        if cargos and cargo not in cargos:
            continue
        quadro = parse_resultado_unificado(json.loads(caminho.read_text(encoding="utf-8")))
        if quadro.empty:
            continue
        uf = caminho.parent.name
        cod_municipio = nome.split("-c")[0][2:7]
        quadro.insert(0, "uf", uf)
        quadro.insert(0, "cod_municipio", cod_municipio)
        quadros.append(quadro)
    if not quadros:
        return pd.DataFrame()
    return pd.concat(quadros, ignore_index=True)


def base_odsele() -> str:
    return ODSELE_BASE
