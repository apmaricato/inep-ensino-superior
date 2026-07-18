# Metodologia — Painel do Censo da Educação Superior (INEP)

*Documento de apoio para artigo. Autoria: Antonio Pedro de Melo Maricato.*

## 1. Objetivo

Consolidar em uma base única, tratada e consultável, os microdados oficiais
do Censo da Educação Superior (INEP) desde o primeiro ano em que o layout
atual está disponível (2009), permitindo analisar a evolução de matrículas,
ingressantes, concluintes e ocupação de vagas do ensino superior brasileiro
ao longo de 16 anos, com recortes por região, UF, município, rede,
categoria administrativa, modalidade, área de conhecimento e curso.

## 2. Fonte dos dados

- **Origem:** Instituto Nacional de Estudos e Pesquisas Educacionais Anísio
  Teixeira (INEP), Censo da Educação Superior, microdados públicos
  (`download.inep.gov.br/microdados/`).
- **Período coberto:** 2009 a 2024 (16 ciclos anuais). 2009 é o ano mais
  antigo disponível nesse layout — o INEP republicou os ciclos 2009-2019 em
  formato simplificado/compatível com o modelo atual em decorrência da Lei
  Geral de Proteção de Dados (LGPD).
- **Arquivos utilizados por ano:** `MICRODADOS_CADASTRO_CURSOS_{ano}.CSV`
  (dados agregados por curso/IES: vagas, inscritos, ingressantes,
  matrículas, concluintes, por turno) e `MICRODADOS_CADASTRO_IES_{ano}.CSV`
  / `MICRODADOS_ED_SUP_IES_{ano}.CSV` (cadastro da instituição — nome,
  sigla, localização).
- **Nível de granularidade:** curso × IES × ano. O INEP não publica mais
  microdados de aluno individual desde a reformulação do Censo em 2019
  (LGPD); os dados são agregados por curso, com contagens por sexo, cor/
  raça, faixa etária, turno e outras dimensões *dentro* de cada linha
  curso/IES/ano — não usamos essas subdivisões demográficas nesta primeira
  versão do painel.

## 3. Pipeline de dados

```
INEP (download.inep.gov.br)
   │  zip anual por ciclo do censo
   ▼
scripts/extract_inep.py   → localiza e extrai os CSVs de dentro dos zips
                             (nome do arquivo de IES e da pasta raiz mudam
                             ano a ano; localizados por padrão/regex)
scripts/transform.py      → lê os CSVs (latin1, delimitador ";"), decodifica
                             colunas de código usando o dicionário de dados
                             oficial do INEP, cruza cursos com IES por
                             CO_IES, calcula métricas derivadas
   ▼
Parquet consolidado (local, passo intermediário)
   │  scripts/load_bigquery.py
   ▼
BigQuery (apmaricato2.inep_ensino_superior.cursos) — 3.851.933 linhas,
16 anos, ~1,9 GB
   ▼
Streamlit (app/streamlit_app.py) — consultas SQL agregadas sob demanda,
sem carregar a tabela inteira em memória
```

**Por que BigQuery em vez de arquivo local servido direto:** a primeira
versão do painel usava Parquet lido localmente via DuckDB, hospedado no
Streamlit Community Cloud (grátis). Isso falhou em produção porque o plano
gratuito tem só 1 GB de RAM, e carregar a tabela inteira na memória do
processo Python estourava esse limite. Mover os dados tratados para o
BigQuery resolveu na raiz: as agregações (somas, agrupamentos) rodam nos
servidores do Google, e o app só recebe de volta resultados já resumidos.

**Validação do pipeline:** os números tratados foram conferidos contra uma
tabela dinâmica montada manualmente em Excel a partir do mesmo microdado
bruto de 2022, batendo exatamente (ex.: matrículas, vagas e ingressantes
por turno para uma IES específica, diurno e noturno).

## 4. Definições metodológicas das métricas-chave

Conforme o dicionário de dados oficial do INEP:

| Métrica | Definição oficial | Natureza |
|---|---|---|
| `QT_VG_TOTAL` | Vagas totais oferecidas no processo seletivo *daquele ano* | Fluxo (1 ano) |
| `QT_ING` | Soma de alunos com data de ingresso em 01/jan ou 01/jul *do ano de referência do censo* | Fluxo (1 ano) |
| `QT_MAT` | Soma de alunos com situação de vínculo "Cursando" e/ou "Formado" — **todos** os alunos ativos no curso, de qualquer ano de ingresso | Estoque (acumulado) |
| `QT_CONC` | Concluintes daquele ano | Fluxo (1 ano) |

### 4.1. A correção da taxa de ocupação de vagas

A primeira versão do painel replicava uma planilha Excel anterior, que
calculava "taxa de ocupação" como `QT_MAT ÷ QT_VG_TOTAL` (matrículas
totais dividido por vagas ofertadas). Essa fórmula produzia taxas acima de
100% em **43,7%** das linhas da base (média 167,7%, mediana 84%) — um
resultado que levantou a suspeita de erro de cálculo.

A investigação, feita cruzando o resultado com o dicionário de dados
oficial do INEP, mostrou que o problema era conceitual: `QT_MAT` é um
**estoque** (soma de todos os alunos ativos no curso, de todas as turmas —
calouro a formando), enquanto `QT_VG_TOTAL` é um **fluxo de um único ano**
(vaga de calouro daquele processo seletivo). Num curso de 4 anos com
matrícula estável, `QT_MAT` é matematicamente ~4x `QT_VG_TOTAL` de um ano
qualquer, mesmo sem nenhuma vaga sobrando — não é sinal de superlotação.

A correção adotada foi trocar o numerador para `QT_ING` (ingressantes
daquele ano), comparando fluxo com fluxo: `QT_ING ÷ QT_VG_TOTAL` responde
"quanto das vagas abertas naquele processo seletivo foi de fato
preenchido por gente que entrou por elas". Após a correção, apenas **2,7%**
das linhas ficam acima de 100% (média 40,8%, mediana 31,4%).

### 4.2. Amostras pequenas ainda distorcem taxas em recortes muito finos

Mesmo com a fórmula corrigida, recortes muito específicos (um curso, um
campus, um ano) ainda podem produzir taxas de centenas de % quando o
número de vagas formalmente reportado é muito baixo (ex.: 1 vaga aberta,
mas 6 ingressantes por vias não capturadas em `QT_VG_TOTAL`, como vaga
remanescente ou transferência). O painel exclui da exibição (em vez de
apenas limitar visualmente) qualquer combinação com menos de 10 vagas
somadas no recorte selecionado, por não ser estatisticamente confiável.

### 4.3. Vagas de EAD são nominalmente muito maiores que a demanda real

Ao segmentar por modalidade, cursos a distância têm taxa de ocupação
(`QT_ING`/`QT_VG_TOTAL`) muito mais baixa (~17%) que presenciais (~32%).
Isso não indica baixa procura — reflete que instituições de EAD costumam
reportar números de vagas nominalmente muito altos (por vezes,
praticamente sem limite físico de sala de aula), sem relação direta com
capacidade real ou demanda esperada. É uma característica conhecida dos
dados do INEP para essa modalidade, não uma inconsistência do pipeline.

## 5. Limitações conhecidas

- **2013 tem cobertura incompleta de `TP_REDE`:** 98% das linhas desse ano
  têm rede (pública/privada) não informada no microdado bruto do INEP.
  Comparações que segmentam por rede devem excluir ou tratar 2013 com
  cautela.
- **Sem dados demográficos individuais:** por LGPD, o INEP não publica
  mais microdados de aluno desde 2019; não é possível cruzar, por exemplo,
  evasão por perfil de aluno.
- **Concluintes/ingressantes não é uma medida de evasão real:** comparar
  `QT_CONC` e `QT_ING` do mesmo ano civil mistura coortes diferentes (quem
  se formou nesse ano entrou anos antes); não é uma taxa de conclusão de
  coorte, só um indicador aproximado de proporção.
- **Filtros de curso não cruzam com geografia:** por volume de
  combinações, os filtros de Área geral/específica/Nome do curso no
  painel não se restringem por UF/instituição já selecionada (mas as
  consultas aos gráficos sempre combinam todos os filtros corretamente).

## 6. Arquitetura e stack

- **Extração/tratamento:** Python (pandas), rodando localmente.
- **Armazenamento analítico:** Google BigQuery (sandbox gratuito, sem
  billing habilitado — 1 TB de consulta/mês, 10 GB de armazenamento).
- **Painel:** Streamlit, hospedado gratuitamente no Streamlit Community
  Cloud, conectado ao BigQuery via service account somente leitura.
- **Versionamento:** GitHub (`apmaricato/inep-ensino-superior`) — apenas
  scripts e o app são versionados; os dados brutos e tratados não entram
  no repositório (Parquet seria grande demais e os dados "vivem" no
  BigQuery).

## 7. Achados preliminares (2009–2024)

Números levantados diretamente da base consolidada, para uso no artigo:

- **Virada histórica do EAD em 2024:** pela primeira vez, matrículas em
  cursos a distância (5.189.391) superaram as de cursos presenciais
  (5.037.875) no Brasil. Em 2009, EAD era só 14% do total; em 2024, é 51%.
- **Setor privado capturou quase todo o crescimento:** matrículas em IES
  privadas cresceram 83% entre 2009 e 2024 (4,46M → 8,16M), contra 35% nas
  públicas (1,53M → 2,07M).
- **Região Norte foi a que mais cresceu proporcionalmente:** 2,17x mais
  matrículas em 2024 que em 2009 (397.912 → 863.969) — maior taxa de
  crescimento entre as 5 regiões, provavelmente puxada pela expansão do
  EAD em áreas com menor oferta presencial histórica.
- **Saúde e bem-estar quase triplicou:** de 860.980 para 2.345.749
  matrículas (+172%) — a área que mais cresceu em termos absolutos depois
  de Negócios/administração/direito.
- **Computação/TIC quase triplicou também:** de 276.489 para 800.222
  matrículas (+189%).
- **Concentração em poucos grupos educacionais no EAD:** em 2024, a
  Universidade Pitágoras Unopar Anhanguera sozinha tem 836.889 matrículas
  em EAD — mais que o total de matrículas de toda a Região Centro-Oeste em
  2009 (543.819) ou Norte em 2009 (397.912).
- **Ingressantes cresceram mais que concluintes:** ingressantes mais que
  dobraram (2,08M → 5,01M, +141%), enquanto concluintes cresceram 38%
  (967.558 → 1.333.988) — a proporção concluintes/ingressantes do mesmo
  ano caiu de 46% para 27% (ver limitação 5, não é medida de evasão real).

## 8. Como citar

```
MARICATO, Antonio Pedro de Melo. Censo da Educação Superior — INEP.
[S. l.], 2026. Disponível em: <URL do painel — a confirmar>.
Acesso em: [dd mês. aaaa].
```

*(A URL pública final do painel ainda precisa ser confirmada para
completar esta referência.)*
