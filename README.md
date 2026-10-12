# Brazil TSE Data Science

Bot de coleta e análise de dados abertos do **Tribunal Superior Eleitoral (TSE)** para as
eleições brasileiras de **2024** e **2026**. O projeto baixa os arquivos oficiais, transforma
os dados em tabelas tratadas e gera gráficos + um relatório em Markdown.

Tudo em português, sem APIs bloqueadas: apenas fontes abertas e testadas
(Portal de Dados Abertos CKAN, CDN do TSE e plataforma de divulgação de resultados).

## Fontes de dados

| Fonte | URL | Uso |
|---|---|---|
| Portal de Dados Abertos (CKAN) | `https://dadosabertos.tse.jus.br` | descoberta automática dos recursos (`package_show`) |
| CDN SEAD/ODSELE | `https://cdn.tse.jus.br/estatistica/sead/odsele/...` | zips com CSVs de votação e candidaturas |
| Plataforma de divulgação | `https://resultados.tse.jus.br/oficial/...` | JSONs de configuração (EA11/EA12) e comparecimento por UF (EA14) |
| SIDRA/IBGE | `https://servicodados.ibge.gov.br/api/v3/agregados` | Censo 2022: população por município/idade e renda domiciliar per capita (cruzamento TSE × IBGE) |

Arquivos usados:

- `votacao_candidato_munzona_{ano}.zip` — votos por município/zona/candidato (2024 e 2026);
- `consulta_cand_{ano}.zip` — candidaturas registradas (partido, gênero, nascimento etc.);
- `detalhe_votacao_munzona_2024.zip` e `votacao_partido_munzona_2024.zip` — eleitorado e apuração 2024;
- `perfil_eleitorado_2024.zip` — perfil socioeconômico dos eleitores aptos (gênero, idade,
  escolaridade, raça/cor, estado civil e identidade de gênero) por UF;
- `votacao_secao_2026_BR.zip` — **votos para presidente em 2026** (o arquivo municipal 2026 só
  traz as eleições estaduais, cargos 3/5/6/7/8);
- `votacao_secao_2024_{UF}.zip` — votos por seção eleitoral nas municipais de 2024 (um zip
  por UF, baixado sob demanda pela aba Seções do app);
- JSONs `ele-c.json`, `mun-e{cod}-cm.json` e `{uf}-e{cod}-ab.json` — eleições cadastradas,
  municípios e comparecimento/abstenção por UF;
- tabelas SIDRA do Censo 2022 (4714, 9514 e 10295) — população e renda, cacheadas em `data/ibge/`.

Limitações conhecidas (verificadas em 06/10/2026):

- os JSONs de resultados de 2024 foram apagados do bucket → 2024 é analisado só via CSV;
- `votacao_partido_munzona_2026.zip` e `detalhe_votacao_munzona_2026.zip` ainda não existem (404);
- `divulgacandcontas.tse.jus.br` bloqueia acesso automatizado (HTTP 403) → usado o CSV `consulta_cand`;
- voto exterior (UF `ZZ`) entra nos dados da presidência, mas é excluído dos gráficos por estado.

## Instalação

Requer Python 3.10+.

Com **uv** (recomendado — cria o `.venv` e trava as versões no `uv.lock`):

```bash
uv sync
uv run python -m tse_app          # app desktop
uv run python -m tse_app --selftest
```

Ou com pip no Python do sistema:

```bash
pip install -r requirements.txt
python -m tse_app
```

> Nota nesta máquina: o Smart App Control do Windows bloqueia wheels não
> assinadas sem reputação (ex.: shapely 2.2.0 e pyarrow 26) — por isso
> `requirements.txt` e `pyproject.toml` fixam as versões testadas.

## Uso

```bash
# lista as fontes disponíveis para cada ano
python main.py meta --ano 2024 --ano 2026

# pipeline completo: baixa, analisa, gráficos e relatório
python main.py tudo --ano 2024 --ano 2026

# etapas separadas
python main.py baixar --fonte csv --ano 2026      # CSVs (~320 MB)
python main.py baixar --fonte json --ano 2026      # JSONs da divulgação (downloads paralelos)
python main.py analisar --ano 2024 --ano 2026      # tabelas tratadas + caches
python main.py graficos --ano 2024 --ano 2026      # PNGs
python main.py relatorio --ano 2024 --ano 2026     # outputs/relatorio.md e listas de eleitos
```

O bot evita trabalho repetido:

- se todos os CSVs do ano já estão em `data/zip/`, a etapa de download nem consulta o CKAN;
- os JSONs da divulgação são baixados em paralelo (6 requisições simultâneas respeitando o
  `--rps`), e arquivos 404 são contados em um só resumo em vez de poluir o log;
- as tabelas geradas ficam em cache (`outputs/tabelas/`): `analisar`, `graficos` e
  `relatorio` reutilizam os parquet/csv quando já existem e só reconstruem se um cargo
  pedido não estiver coberto pelo cache.

Opções úteis:

- `--rps 8` — limite de requisições por segundo (o TSE aceita até 100/s);
- `--recurso votacao_secao` — baixa somente um recurso específico;
- `--force` — refaz downloads e caches;
- `--tipo config,acompanhamento,resultado` — tipos de JSON da divulgação;
- `--eleicao 6257 --cargos 1 --limite 200` — baixa os JSONs unificados de resultado (EA20)
  para uma eleição/cargo, com limite de municípios.

Saída:

```
data/zip/      # zips brutos do TSE (ignorado pelo git)
data/json/     # JSONs da divulgação (ignorado pelo git)
data/ibge/     # respostas brutas e parquets do SIDRA/IBGE (ignorado pelo git)

outputs/tabelas/votos_municipio_{ano}.parquet   # votos agregados por município/candidato
outputs/tabelas/candidatos_{ano}.parquet        # candidaturas com idade/gênero
outputs/tabelas/apuracao_uf_{ano}.csv           # eleitorado e comparecimento por UF
outputs/tabelas/partidos_nacional_{ano}.csv     # TODOS os partidos, total do país, por cargo
outputs/tabelas/partidos_uf_{ano}.csv         # TODOS os partidos em cada estado, por cargo
outputs/tabelas/eleitos_{ano}.csv               # todos os eleitos: partido, idade e gênero
outputs/tabelas/mais_votados_{ano}.csv          # top 20 nacional e top 10 por UF
outputs/tabelas/segundo_turno_{ano}.csv         # disputas de 2º turno, votos, % e margem
outputs/tabelas/perfil_eleitorado_2024.parquet  # perfil do eleitorado em formato longo
outputs/tabelas/idade_tse_ibge_2024.csv         # eleitores (TSE) × população 16+ (IBGE) por faixa
outputs/tabelas/cruzamento_municipios_2024.csv  # apuração TSE × renda/população IBGE × resultado

outputs/figuras/      # 38 gráficos PNG (24 de 2024 e 14 de 2026), incluindo painéis executivos (BI)
outputs/relatorio.md  # relatório completo
outputs/eleitos_2024.md / eleitos_2026.md       # listas nominais completas dos eleitos
```

Cobertura das listas de eleitos:

| Ano | Cargos | Eleitos na base |
|---|---|---|
| 2024 | prefeito, vereador | 5.564 prefeitos e 58.165 vereadores |
| 2026 | presidente, governador, senador, deputado federal | 513 depfed, 54 senadores e 20 governadores (7 UFs e a presidência ainda sem resultado final na base) |

## App desktop (tse_app)

Interface PySide6 com mapa navegável (Brasil → região → UF → município), tabela de
candidatos por cargo, galeria dos 38 gráficos e chat de IA contextualizado no escopo
atual (ano, cargo e região selecionados).

```bash
python -m tse_app                   # abre a janela (2024)
python -m tse_app --ano 2026        # abre já em 2026
python -m tse_app --selftest        # verifica dados, malhas, navegação e UI sem abrir janela
python -m tse_app --selftest --chat # selftest + uma chamada real ao modelo
```

- **Chat**: chaves do Ollama Cloud em `data/app/ollama_keys.txt` (uma por linha ou
  separadas por vírgula; a pasta `data/` é ignorada pelo git). O cliente rotaciona as
  chaves a cada requisição, aplica cooldown automático em 429/401 e usa `gpt-oss:120b`.
- **Mapa**: malhas do IBGE baixadas sob demanda e cacheadas em `data/geo/`; a ponte
  TSE ↔ IBGE dos municípios fica em `data/app/mapa_municipios.csv`.
- **Votos**: na primeira carga o ano é filtrado (eleição principal + turno decisivo,
  sem `ZZ`) e salvo em `data/app/votos_{ano}.parquet`.

## Estrutura

```
main.py            # CLI (argparse): meta, baixar, analisar, graficos, relatorio, tudo
tse_ds/
  config.py        # URLs, pastas, recursos e cargos por ano
  http.py          # cliente HTTP com retry, rate limit e download com progresso
  ckan.py          # descoberta de recursos no Portal de Dados Abertos
  odsele.py        # leitura de zips/CSV (latin-1, separador ";", por membro)
  divulga.py       # clientes JSON da plataforma de divulgação (EA11/EA12/EA14/EA20)
  loaders.py       # carga e agregação dos CSVs do TSE
  ibge.py          # SIDRA/IBGE (Censo 2022): população e renda, com cache em data/ibge/
  analysis.py      # tabelas tidy + caches em parquet/csv
  charts.py        # 38 figuras (matplotlib/seaborn, backend Agg)
  relatorio.py     # relatório em Markdown
tse_app/
  __main__.py      # entry point: python -m tse_app
  config.py        # paths, chaves do Ollama, nomes de regiões/UFs/cargos
  escopo.py        # Escopo (Brasil/Região/UF/Município) e migalha de navegação
  geo.py           # malhas do IBGE (região/UF/município) com cache em data/geo/
  store.py         # agregações por escopo + contexto de texto para o chat
  chat.py          # cliente Ollama Cloud (rotação de chaves, cooldown, streaming)
  zonas.py         # votos nominais por zona eleitoral (cache em data/app/zonas/)
  bairros.py       # geocodificação dos locais de votação em bairros
  secoes.py        # votos por seção eleitoral (2024/2026, cache em data/app/zonas/)
  graficos_locais.py  # PNGs locais por escopo na galeria
  selftest.py      # verificações usadas por --selftest
  ui/              # mapa.py, janela.py, candidatos.py, eleitos.py, galeria.py, secoes.py, chat_ui.py
```

## Detalhes técnicos

- Os zips têm membros `*_UF.csv` + `*_BRASIL.csv` + `*_BR.csv`; o `BRASIL.csv` é a união
  exata das UFs (verificado contando linhas), então a leitura usa `BRASIL` + `BR` e nunca
  todos os membros juntos (isso duplicaria os votos).
- Leitura em *chunks* com agregação parcial por município — o arquivo de votação de 2026 tem
  6,6 milhões de linhas e não cabe com folga em memória bruta.
- `consulta_cand` não possui colunas de município: elas são derivadas de `SG_UE`/`NM_UE`.
- Votos brancos e nulos do arquivo de seção (`SQ_CANDIDATO = -1`, `NR_VOTAVEL` 95/96) são
  descartados para que "votos válidos" signifique votos em candidatos.
- Os cargos analisados são prefeito/vereador (2024) e presidente/governador/senador/
  deputado federal (2026); filtros por cargo evitam carregar os 6,6 milhões de linhas completos.
- O arquivo municipal de 2026 não traz o cargo 1 (presidente): esses votos vêm de
  `votacao_secao_2026_BR.zip`, agregados por município e com a situação do candidato
  recuperada do cadastro.
- O arquivo de seções de 2026 é um consolidado `BR`, enquanto o de 2024 vem um zip por UF
  (`votacao_secao_2024_{UF}.zip`, 4–475 MB): o app baixa o zip da UF sob demanda ao abrir a
  aba Seções e cacheia o recorte em `data/app/zonas/secoes_{ano}_{UF}.parquet`.
- Idade = anos completos na data do pleito (04/10/2026 e 06/10/2024).
- O cruzamento TSE × IBGE une por `UF|NOME_NORMALIZADO` (sem acento/caixa) com um dicionário
  de correções para homônimos divergentes; o Censo 2022 tem 5.570 municípios e a apuração
  municipal do TSE traz 5.569, restando 3 municípios criados depois do levantamento sem
  contrapartida (reportados no log).
- As consultas ao SIDRA ficam cacheadas como JSON bruto (`data/ibge/`) e como parquet agregado,
  então o cruzamento roda offline depois da primeira execução.

## Resultados principais

Ver `outputs/relatorio.md` após rodar o pipeline. Resumo do último processamento:

- **2024**: 155,9 mi de eleitores, 78,0% de comparecimento (CE 85,7% > RJ 73,7%),
  5.568 municípios com dados e 447.726 candidaturas (34,7% femininas);
  5.564 prefeitos e 58.165 vereadores eleitos listados com partido, idade e gênero;
- **2026**: 157,8 mi de eleitores, 79,2% de comparecimento (CE 84,5% > MS 76,1%),
  5.571 municípios com dados e 20.065 candidaturas nos cargos principais (35,2% femininas);
  513 deputados federais e 54 senadores eleitos listados (mais 20 governadores; a
  presidência e 7 governos estaduais ainda sem resultado final na base baixada).

## Licença

Código do repositório sob MIT. Os dados são do Tribunal Superior Eleitoral
(dados abertos do Governo Federal).
