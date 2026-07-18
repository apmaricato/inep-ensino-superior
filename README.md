# Painel — Censo da Educação Superior (INEP)

Pipeline e painel para analisar matrículas, ingressantes, concluintes e taxa de
ocupação de vagas do ensino superior brasileiro, a partir dos **microdados
oficiais do INEP** (Censo da Educação Superior), 2009-2024.

Confirmado que o INEP disponibiliza `MICRODADOS_CADASTRO_CURSOS`/`MICRODADOS_CADASTRO_IES`
com o mesmo layout de colunas desde **2009** — o ano mais antigo publicado
nesse formato (o INEP republicou os ciclos 2009-2019 em formato simplificado/
compatível com o modelo atual por conta da LGPD; não há dados do Censo da
Educação Superior anteriores a 2009 nesse layout).

## Como funciona

```
Dados/ (CSVs brutos do INEP, não versionados)
   │  scripts/extract_inep.py  → extrai CSVs de dentro dos zips oficiais
   │  scripts/transform.py     → limpa, decodifica códigos, calcula taxas
   ▼
data/parquet/  (local, não versionado — só um passo intermediário)
   │  scripts/load_bigquery.py → carrega o parquet consolidado no BigQuery
   ▼
BigQuery — apmaricato2.inep_ensino_superior.cursos (3,85M linhas, 2009-2024)
   │
   ▼
app/streamlit_app.py → painel interativo (consultas SQL agregadas, sem
                        carregar a tabela inteira em memória)
```

Os dados vêm direto do `MICRODADOS_CADASTRO_CURSOS_{ano}.CSV` (dados por
curso/IES) cruzado com `MICRODADOS_ED_SUP_IES_{ano}.CSV` / `MICRODADOS_CADASTRO_IES_{ano}.CSV`
(cadastro da instituição, nome da IES). O INEP não publica mais microdados de
aluno individual desde a reformulação do Censo em 2019 (LGPD) — este é o nível
de granularidade mais fino disponível publicamente.

### Por que BigQuery em vez de só Parquet no GitHub?

A primeira versão deste projeto guardava os dados tratados como Parquet
versionado no próprio repositório, lidos localmente via DuckDB. Isso quebrou
em produção: o Streamlit Community Cloud tem só 1GB de RAM no plano grátis, e
carregar as 2,75M linhas inteiras na memória do processo Python estourava esse
limite. Migrar os dados tratados para o BigQuery resolve isso na raiz — todas
as agregações (somas, group by) rodam nos servidores do Google, e o app só
recebe de volta os resultados já agregados (pequenos).

**Atenção:** o projeto `apmaricato2` não tem billing habilitado, então o
BigQuery roda no modo sandbox (grátis, 1TB de consulta/mês, 10GB de
armazenamento) — mas tabelas sem atividade por 60 dias são apagadas
automaticamente. Rodar `scripts/load_bigquery.py` periodicamente (ex: ao
atualizar com um novo ano do Censo) evita isso.

## Rodando localmente

```powershell
py -m pip install -r requirements.txt

# autenticação com o GCP (uma vez)
gcloud auth application-default login

# (opcional) baixar/atualizar um novo ano do INEP
py scripts\extract_inep.py --anos 2025
py scripts\transform.py
py scripts\load_bigquery.py

# rodar o painel (precisa de .streamlit/secrets.toml com a chave da
# service account streamlit-inep-reader@apmaricato2.iam.gserviceaccount.com)
py -m streamlit run app\streamlit_app.py
```

## Métricas principais

- `QT_MAT`, `QT_MAT_DIURNO`, `QT_MAT_NOTURNO` — matrículas totais e por turno
  (todos os alunos ativos no curso naquele ano — calouros a formandos)
- `QT_ING`, `QT_ING_DIURNO`, `QT_ING_NOTURNO` — ingressantes (só quem entrou
  naquele ano, via processo seletivo de 01/jan ou 01/jul)
- `QT_CONC` — concluintes
- `QT_VG_TOTAL_DIURNO` / `QT_VG_TOTAL_NOTURNO` — vagas ofertadas no processo
  seletivo daquele ano
- `TAXA_OCUPACAO_DIURNO` / `TAXA_OCUPACAO_NOTURNO` = **ingressantes** ÷ vagas
  ofertadas por turno (`QT_ING / QT_VG_TOTAL`, não `QT_MAT / QT_VG_TOTAL`).

  A planilha original (`INEP Taxa de Ocupaçaão Cursos Não Gratuitos
  2022.docx`) usava matrículas ÷ vagas, o que dá >100% em qualquer curso
  plurianual com matrícula estável — `QT_MAT` soma *todos* os alunos ativos
  no curso (todas as turmas), enquanto `QT_VG_TOTAL` é só a vaga de calouro
  daquele ano; comparar as duas é comparar um estoque acumulado com um
  fluxo de um ano só. `QT_ING / QT_VG_TOTAL` compara fluxo com fluxo
  (ingressantes daquele ano ÷ vagas daquele ano) e reflete melhor "quanto
  das vagas abertas naquele processo seletivo foi de fato preenchido".
  Confirmado no dicionário de dados oficial do INEP (campo "Categoria" de
  `QT_ING`: *"soma do número de alunos com data de ingresso de 01 de
  janeiro e 01 de julho do ano de referência do censo"*; de `QT_MAT`:
  *"soma do número de alunos com situação de vínculo ao curso igual a:
  Cursando e/ou Formado"*).

Dimensões de corte disponíveis: ano, região, UF, capital ou não, rede
(pública/privada), gratuidade, modalidade (presencial/EAD), IES, área CINE.

## Deploy gratuito (Streamlit Community Cloud)

1. Push deste repositório para o GitHub (já feito — `apmaricato/inep-ensino-superior`).
2. Em [share.streamlit.io](https://share.streamlit.io), logar com a conta do
   GitHub, criar um app apontando para `app/streamlit_app.py` (branch `master`).
3. Em **Advanced settings → Secrets**, colar o conteúdo do arquivo de
   credenciais da service account no formato TOML (chave `[gcp_service_account]`
   com os campos do JSON gerado por `gcloud iam service-accounts keys create`).
   **Nunca commitar essa chave no GitHub** — ela só vive nos Secrets do
   Streamlit Cloud e no `.streamlit/secrets.toml` local (ambos fora do git).
4. Deploy. A URL pública fica disponível e atualiza automaticamente a cada
   `git push` — mas os *dados* só atualizam quando `scripts/load_bigquery.py`
   for rodado de novo (o app sempre lê o BigQuery ao vivo).

## Atualizando com um novo ano do Censo

Quando o INEP publicar um novo ciclo (normalmente entre novembro e janeiro):

```powershell
Invoke-WebRequest -Uri "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_AAAA.zip" -OutFile "microdados_censo_da_educacao_superior_AAAA.zip"

py scripts\extract_inep.py --anos AAAA
py scripts\transform.py
py scripts\load_bigquery.py
```

Não precisa de `git push` nem redeploy — o painel lê o BigQuery ao vivo, então
os dados novos aparecem assim que `load_bigquery.py` terminar.
