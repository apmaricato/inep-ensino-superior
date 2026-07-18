# AGENTS.md — Contexto para continuar este projeto

Este arquivo existe para que qualquer agente de IA (ou humano) que abra
esta pasta depois consiga entender o projeto, o estado atual, e como
continuar sem precisar redescobrir tudo do zero. Se você é uma IA lendo
isso pela primeira vez: leia este arquivo inteiro antes de sugerir
mudanças ou tocar em `scripts/` ou `app/streamlit_app.py`.

## O que é este projeto

Pipeline + painel público (Streamlit) que consolida os microdados oficiais
do Censo da Educação Superior (INEP), 2009-2024, num banco consultável
(BigQuery), para analisar matrículas, ingressantes, concluintes e taxa de
ocupação de vagas do ensino superior brasileiro.

- **Autor:** Antonio Pedro de Melo Maricato (GitHub: `apmaricato`)
- **Repositório:** https://github.com/apmaricato/inep-ensino-superior
- **Painel público:** Streamlit Community Cloud — URL a confirmar (o autor
  ainda não passou o link final; ver seção "Pendências" abaixo).
- **Projeto GCP:** `apmaricato2` (conta Google `apmaricato2@gmail.com`)
- **BigQuery:** `apmaricato2.inep_ensino_superior.cursos`

**Leia primeiro, nesta ordem:**
1. Este arquivo (visão geral + como continuar)
2. `README.md` (como rodar o pipeline localmente, comandos exatos)
3. `docs/METODOLOGIA.md` (definições de métricas, decisões metodológicas,
   limitações conhecidas, achados já extraídos)

## Estado atual (última atualização: 2026-07-18)

- Dados carregados: **2009 a 2024** (16 anos), 3.851.933 linhas na tabela
  BigQuery.
- Fonte: `MICRODADOS_CADASTRO_CURSOS_{ano}.CSV` + `MICRODADOS_CADASTRO_IES_{ano}.CSV`
  / `MICRODADOS_ED_SUP_IES_{ano}.CSV` (o nome do arquivo de IES muda entre
  anos — `scripts/extract_inep.py` já lida com isso via regex).
- Painel Streamlit funcional: filtros hierárquicos em cascata (localização,
  curso, instituição, outros atributos), crossfilter por clique nos
  gráficos, comparação de até 5 IES com gráficos radar de ocupação por
  área/curso, ranking de IES.
- Métrica de "taxa de ocupação de vagas" foi corrigida de `QT_MAT/QT_VG_TOTAL`
  para `QT_ING/QT_VG_TOTAL` (ver `docs/METODOLOGIA.md` seção 4.1 para o
  raciocínio completo — **não reverta isso sem entender por quê**).
- Conteúdo editorial já produzido: `docs/METODOLOGIA.md`,
  `docs/INSTAGRAM_10_POSTAGENS.md`, `docs/LINKEDIN_10_POSTAGENS.md`.

## Pendências conhecidas

- [ ] Confirmar a URL pública final do painel no Streamlit Cloud (o autor
  mencionou que a primeira URL tentada pedia login — pode ter mudado o
  app ou a configuração de visibilidade). Necessário para completar a
  referência ABNT em `docs/METODOLOGIA.md` seção 8 e para os links "na
  bio"/"nos comentários" das postagens em `docs/`.
- [ ] Criar página de metodologia + "como citar" dentro do próprio site
  Streamlit (multi-page app, `app/pages/`) — ainda não implementada,
  ficou represada esperando a URL acima. O conteúdo já existe em
  `docs/METODOLOGIA.md`, é só adaptar pra uma página Streamlit.
- [ ] `TP_REDE_DESC` de 2013 está 98% nulo no dado bruto do INEP (ver
  `docs/METODOLOGIA.md` seção 5) — não é bug nosso, é o CSV oficial daquele
  ano. Qualquer análise por rede deve excluir ou marcar 2013 com cautela.

## Como continuar o pipeline de dados

Setup de autenticação (uma vez por máquina):
```powershell
gcloud auth login          # conta apmaricato2@gmail.com
gcloud auth application-default login
gcloud config set project apmaricato2
```

Adicionar um novo ano do Censo (quando o INEP publicar):
```powershell
py -m pip install -r requirements.txt
Invoke-WebRequest -Uri "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_AAAA.zip" -OutFile "microdados_censo_da_educacao_superior_AAAA.zip"
py scripts\extract_inep.py --anos AAAA
py scripts\transform.py          # reprocessa TODOS os anos e regrava o parquet consolidado
bq load --source_format=PARQUET --replace apmaricato2:inep_ensino_superior.cursos "data/parquet/cursos_2009_AAAA.parquet"
```

**Importante:** `scripts/transform.py` sempre reprocessa a série completa
(todos os CSVs presentes em `Dados/`) e gera um único parquet consolidado
com o nome `cursos_{ano_min}_{ano_max}.parquet`. Ao adicionar um ano, o
nome do arquivo consolidado muda — apague o parquet consolidado antigo em
`data/parquet/` antes de rodar `bq load` para não confundir qual é o
mais recente (o `.gitignore` já exclui `data/parquet/` do versionamento,
então isso é só limpeza local).

Antes de considerar qualquer mudança no pipeline "pronta": rode
`scripts/transform.py`, confira as contagens impressas no terminal contra
o ano anterior (crescimento ano a ano deve ser suave, sem saltos ou
quedas bruscas inexplicadas), depois `bq load`, depois teste o app
localmente (`py -m streamlit run app/streamlit_app.py`) antes de fazer
push. Ver `README.md` para o passo a passo completo com autenticação do
Streamlit local (`.streamlit/secrets.toml`, não versionado).

## Schema da tabela BigQuery (`apmaricato2.inep_ensino_superior.cursos`)

Colunas principais (todas vindas de `scripts/transform.py`, ver
`CURSOS_COLS` nesse arquivo para a lista exata mantida do CSV bruto):

**Dimensões geográficas:** `NU_ANO_CENSO`, `NO_REGIAO`, `SG_UF`, `NO_UF`,
`NO_MUNICIPIO`, `CO_MUNICIPIO`, `IN_CAPITAL` (+ `_DESC` decodificado)

**Dimensões institucionais:** `CO_IES`, `NO_IES`, `SG_IES`,
`TP_ORGANIZACAO_ACADEMICA`, `TP_REDE`, `TP_CATEGORIA_ADMINISTRATIVA` (+ `_DESC`)

**Dimensões de curso:** `CO_CURSO`, `NO_CURSO`, `NO_CINE_AREA_GERAL`,
`NO_CINE_AREA_ESPECIFICA`, `TP_GRAU_ACADEMICO`, `IN_GRATUITO`,
`TP_MODALIDADE_ENSINO`, `TP_NIVEL_ACADEMICO` (+ `_DESC`)

**Métricas (todas somáveis, nível curso/IES/ano):** `QT_VG_TOTAL(_DIURNO/_NOTURNO/_EAD)`,
`QT_ING(_DIURNO/_NOTURNO)`, `QT_MAT(_DIURNO/_NOTURNO)`, `QT_CONC(_DIURNO/_NOTURNO)`

**Colunas derivadas (calculadas em `transform.py`, ver `add_derived_metrics`):**
`TAXA_OCUPACAO_DIURNO/NOTURNO/TOTAL` = `QT_ING/QT_VG_TOTAL` por turno.
**Atenção:** o app Streamlit hoje recalcula essas taxas ao vivo via SQL
(`SUM(QT_ING)/SUM(QT_VG_TOTAL)` agregado por filtro) em vez de ler essas
colunas pré-calculadas — elas existem na tabela mas não são lidas pelo
app atualmente. Se for usá-las diretamente, releia a seção 4 de
`docs/METODOLOGIA.md` primeiro.

**NÃO estão na base** (não foram mantidas do CSV bruto do INEP, mas
existem no microdado original se precisar adicionar): quebras por sexo
(`QT_MAT_FEM/MASC`), cor/raça (`QT_MAT_BRANCA/PRETA/PARDA/...`), faixa
etária (`QT_MAT_18_24` etc.), financiamento estudantil (`QT_MAT_FIES`,
`QT_MAT_PROUNII/P`). Se for adicionar alguma, editar `CURSOS_COLS` em
`scripts/transform.py`, reprocessar tudo e recarregar o BigQuery.

## Ideias de expansão (verificar antes de implementar, não assumir viabilidade)

Pedido explícito do autor: outras IAs devem poder "alimentar, verificar
dados, complementar estatísticas, cruzar com outras bases". Ideias
concretas de onde buscar, na ordem que parecem mais viáveis:

1. **IBGE — população e PIB por município/UF:** para normalizar
   matrículas per capita ou por PIB, em vez de só números absolutos.
   Disponível via SIDRA/API do IBGE, chave de junção seria `CO_MUNICIPIO`
   (mesmo código IBGE de 7 dígitos que já usamos).
2. **RAIS/CAGED (Ministério do Trabalho) ou Painel de Empregabilidade:**
   para cruzar área de curso com inserção no mercado de trabalho —
   pediria trabalho de matching por área/ocupação, não é uma chave direta.
3. **Microdados do ENEM (INEP):** perfil socioeconômico de quem presta o
   exame vs. quem de fato ingressa — outra base do próprio INEP, mesma
   fonte, mas arquivo/estrutura totalmente diferente.
4. **e-MEC / Conceito Preliminar de Curso (CPC), IGC:** indicador de
   qualidade por curso/IES do próprio INEP — permitiria cruzar "cresceu
   muito" com "manteve qualidade". Verificar se está em formato de
   microdado aberto ou só consulta unitária no site.
5. **CAPES (pós-graduação):** fora do escopo atual (só graduação), mas
   mesma família de dados se um dia quiser expandir.

Antes de implementar qualquer cruzamento: confirmar que a base nova tem
uma chave de junção confiável com o que já temos (`CO_MUNICIPIO`,
`CO_IES` do e-MEC, ou nome normalizado), e documentar a fonte + data de
acesso em `docs/METODOLOGIA.md`, seguindo o mesmo padrão já usado ali.

## Convenções deste projeto (seguir ao continuar)

- **Nunca commitar `.streamlit/secrets.toml`** nem qualquer chave de
  service account — já está no `.gitignore`, mas confira antes de
  `git add -A`.
- **Sempre testar localmente antes de dar push:** rodar o app com
  `streamlit run app/streamlit_app.py`, verificar que carrega sem erro,
  antes de subir pro GitHub (o deploy no Streamlit Cloud é automático a
  cada push na branch `master`).
- **Mudanças em métricas/fórmulas exigem verificação numérica antes de
  aceitar como corretas** — o padrão estabelecido neste projeto foi
  sempre cruzar contra o dicionário de dados oficial do INEP e, quando
  possível, contra uma segunda fonte (ex.: a tabela dinâmica em Excel já
  existente na pasta) antes de confiar em um número. Ver o histórico da
  correção da taxa de ocupação em `docs/METODOLOGIA.md` como exemplo do
  nível de rigor esperado.
- **Dados brutos (`Dados/`, `*.zip`, `*.CSV`) e tratados (`data/parquet/`)
  não são versionados no Git** — só os scripts, o app, e os dados no
  BigQuery são a fonte de verdade "viva". Isso é intencional (ver
  `README.md`, seção "Por que BigQuery").
- **Mensagens de commit em português, explicando o "porquê"** — seguir o
  padrão já usado no histórico do repositório (`git log` para ver
  exemplos).

## Arquivos e o que cada um faz

```
AGENTS.md                          — este arquivo
README.md                          — como rodar o pipeline e o app localmente
requirements.txt                   — dependências Python do app
scripts/
  extract_inep.py                  — extrai CSVs de dentro dos zips do INEP
  transform.py                     — trata, decodifica, calcula métricas, gera parquet
  load_bigquery.py                 — carrega o parquet consolidado no BigQuery (via lib Python)
  dicionario_mapping.py            — mapas código -> rótulo (extraídos do dicionário INEP)
app/
  streamlit_app.py                 — o painel em si (única página até agora)
data/parquet/                      — saída tratada, local, não versionada
Dados/                             — CSVs brutos extraídos, local, não versionada
docs/
  METODOLOGIA.md                   — metodologia completa + achados, base para artigo
  INSTAGRAM_10_POSTAGENS.md        — 10 posts prontos para Instagram
  LINKEDIN_10_POSTAGENS.md         — 10 posts prontos para LinkedIn
```
