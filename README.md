# Painel — Censo da Educação Superior (INEP)

Pipeline e painel para analisar matrículas, ingressantes, concluintes e taxa de
ocupação de vagas do ensino superior brasileiro, a partir dos **microdados
oficiais do INEP** (Censo da Educação Superior), 2020-2024.

## Como funciona

```
Dados/ (CSVs brutos do INEP, não versionados)
   │  scripts/extract_inep.py  → extrai CSVs de dentro dos zips oficiais
   │  scripts/transform.py     → limpa, decodifica códigos, calcula taxas
   ▼
data/parquet/  (versionado no git — ~50MB para 5 anos, ~2,7M linhas)
   │
   ▼
app/streamlit_app.py  → painel interativo (filtros, KPIs, gráficos, ranking)
```

Os dados vêm direto do `MICRODADOS_CADASTRO_CURSOS_{ano}.CSV` (dados por
curso/IES) cruzado com `MICRODADOS_ED_SUP_IES_{ano}.CSV` / `MICRODADOS_CADASTRO_IES_{ano}.CSV`
(cadastro da instituição, nome da IES). O INEP não publica mais microdados de
aluno individual desde a reformulação do Censo em 2019 (LGPD) — este é o nível
de granularidade mais fino disponível publicamente.

## Rodando localmente

```powershell
py -m pip install -r requirements.txt

# (opcional) baixar/atualizar um novo ano do INEP
py scripts\extract_inep.py --anos 2025
py scripts\transform.py

# rodar o painel
py -m streamlit run app\streamlit_app.py
```

## Métricas principais

- `QT_MAT`, `QT_MAT_DIURNO`, `QT_MAT_NOTURNO` — matrículas totais e por turno
- `QT_ING`, `QT_ING_DIURNO`, `QT_ING_NOTURNO` — ingressantes
- `QT_CONC` — concluintes
- `QT_VG_TOTAL_DIURNO` / `QT_VG_TOTAL_NOTURNO` — vagas ofertadas
- `TAXA_OCUPACAO_DIURNO` / `TAXA_OCUPACAO_NOTURNO` = matrículas ÷ vagas ofertadas
  por turno — replica a análise já feita manualmente em
  `INEP Taxa de Ocupaçaão Cursos Não Gratuitos 2022.docx`

Dimensões de corte disponíveis: ano, região, UF, capital ou não, rede
(pública/privada), gratuidade, modalidade (presencial/EAD), IES, área CINE.

## Deploy gratuito (Streamlit Community Cloud)

1. Criar um repositório no GitHub e dar push deste projeto:
   ```powershell
   git remote add origin <url-do-seu-repo>
   git push -u origin main
   ```
2. Entrar em [share.streamlit.io](https://share.streamlit.io), logar com a
   conta do GitHub e conectar o repositório, apontando para `app/streamlit_app.py`.
3. O deploy é gratuito, gera uma URL pública compartilhável, e é atualizado
   automaticamente a cada `git push`.

## Atualizando com um novo ano do Censo

Quando o INEP publicar um novo ciclo (normalmente entre novembro e janeiro):

```powershell
# baixar o zip do ano novo (ver URL em
# https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-da-educacao-superior)
Invoke-WebRequest -Uri "https://download.inep.gov.br/microdados/microdados_censo_da_educacao_superior_AAAA.zip" -OutFile "microdados_censo_da_educacao_superior_AAAA.zip"

py scripts\extract_inep.py --anos AAAA
py scripts\transform.py
git add data/parquet
git commit -m "Adiciona dados do Censo AAAA"
git push
```

O Streamlit Cloud re-implanta automaticamente ao detectar o push.
