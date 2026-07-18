"""
Painel do Censo da Educação Superior (INEP) - matrículas, ingressantes,
concluintes e taxa de ocupação de vagas, 2009-2024.

Os dados vivem no BigQuery (projeto apmaricato2, dataset inep_ensino_superior,
tabela cursos). Todas as agregações rodam via SQL no servidor do BigQuery —
o app nunca carrega a tabela completa (3,85M linhas) para a memória local,
o que é essencial no free tier do Streamlit Community Cloud (1GB de RAM).

Os gráficos e a tabela de ranking têm crossfilter: clicar num ano, numa UF,
numa fatia de modalidade ou numa linha do ranking filtra o resto do painel,
além dos filtros manuais da barra lateral.

Roda localmente com:
    streamlit run app/streamlit_app.py
(usa .streamlit/secrets.toml local com a chave da service account)
"""

from google.cloud import bigquery
from google.oauth2 import service_account
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


def pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """% seguro para NA/0, evitando o TypeError do pandas .round() em dtypes
    nullable (Int64/Float64) quando há pd.NA envolvido."""
    num = numerator.astype("float64")
    den = denominator.astype("float64").replace(0, np.nan)
    return (num / den * 100).round(1)


def pct_scalar(numerator, denominator):
    if pd.isna(numerator) or pd.isna(denominator) or float(denominator) == 0:
        return None
    return float(numerator) / float(denominator) * 100


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def style_radar(fig):
    """Aplica a paleta de alto contraste RADAR_COLORS e preenchimento
    translúcido na cor da própria linha (em vez do preenchimento
    semi-transparente padrão do Plotly, que deixa cores próximas difíceis
    de distinguir quando várias IES se sobrepõem). Espessura de linha e
    tamanho de marcador ficam no padrão do Plotly — só a cor muda."""
    for trace, color in zip(fig.data, RADAR_COLORS):
        trace.line.color = color
        trace.marker.color = color
        trace.fill = "toself"
        trace.fillcolor = _hex_to_rgba(color, 0.18)
        trace.opacity = 1
    fig.update_layout(legend=dict(font=dict(size=13)))
    return fig

st.set_page_config(
    page_title="Censo da Educação Superior (INEP)",
    page_icon="🎓",
    layout="wide",
)

# --- CSS: tokens de design + componentes (cards, tipografia, tabelas) -----
# Segue os mesmos tokens de cor do fundo escuro em references/palette.md da
# skill dataviz (chart surface #1a1a19, page plane #0d0d0d, ink primário
# #ffffff, ink secundário #c3c2b7, muted #898781, hairline rgba(255,255,255,.10)).
# Fonte fica no system sans (sem carregar fonte externa) por performance e
# para não depender de rede — mesma recomendação da skill.
st.markdown(
    """
    <style>
    :root {
        --surface-1: #1a1a19;
        --page-plane: #0d0d0d;
        --ink-primary: #ffffff;
        --ink-secondary: #c3c2b7;
        --ink-muted: #898781;
        --border-hairline: rgba(255, 255, 255, 0.10);
        --radius-md: 0.5rem;
        --radius-lg: 0.9rem;
        --space-2: 0.5rem;
        --space-3: 0.75rem;
        --space-4: 1rem;
        --space-6: 2rem;
        --shadow-card: 0 1px 3px rgba(0, 0, 0, 0.35);
        --accent: #3987e5;
    }

    html, body, [class*="css"] {
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }

    /* Hierarquia tipográfica: título fluido, subtítulos com respiro e trilho
       de cor de acento à esquerda para escanear o painel mais rápido. */
    h1 {
        font-size: clamp(1.6rem, 1.1rem + 1.6vw, 2.4rem) !important;
        letter-spacing: -0.01em;
    }
    h2, h3 {
        letter-spacing: -0.01em;
        margin-top: var(--space-6) !important;
    }
    h3 {
        border-left: 3px solid var(--accent);
        padding-left: var(--space-3);
    }

    /* Legendas (st.caption) em tom secundário, um pouco maiores que o
       padrão minúsculo do Streamlit — melhora legibilidade das explicações
       metodológicas espalhadas pelo painel. */
    [data-testid="stCaptionContainer"] {
        color: var(--ink-secondary) !important;
        font-size: 0.92rem !important;
        line-height: 1.5;
    }

    /* KPIs como cartões: separa visualmente os 5 números do topo do resto
       do painel, com contorno sutil em vez de fundo chapado (recessive,
       não compete com as cores das séries dos gráficos). */
    [data-testid="stMetric"] {
        background: var(--surface-1);
        border: 1px solid var(--border-hairline);
        border-radius: var(--radius-lg);
        padding: var(--space-4);
        box-shadow: var(--shadow-card);
    }
    [data-testid="stMetricLabel"] {
        color: var(--ink-muted) !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }
    [data-testid="stMetricValue"] {
        color: var(--ink-primary) !important;
        font-variant-numeric: tabular-nums;
    }

    /* Gráficos Plotly como cartões — mesma lógica visual dos KPIs, pra dar
       sensação de "sistema" único em vez de elementos soltos na página. */
    [data-testid="stPlotlyChart"] {
        background: var(--surface-1);
        border: 1px solid var(--border-hairline);
        border-radius: var(--radius-lg);
        padding: var(--space-3);
    }

    /* Tabelas com cantos arredondados e contorno hairline, consistente com
       cards e gráficos. */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--border-hairline);
        border-radius: var(--radius-md);
        overflow: hidden;
    }

    /* Chips do multiselect (filtros): cantos mais arredondados, tipografia
       menor e mais compacta — Streamlit por padrão deixa retangular. */
    [data-baseweb="tag"] {
        border-radius: var(--radius-md) !important;
    }

    /* Divisores (st.divider) discretos em vez da linha branca padrão. */
    hr {
        border-color: var(--border-hairline) !important;
    }

    /* Sidebar com leve respiro extra nas seções (st.subheader dentro dela). */
    section[data-testid="stSidebar"] h3 {
        margin-top: var(--space-4) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

PROJECT_ID = "apmaricato2"
TABLE = f"`{PROJECT_ID}.inep_ensino_superior.cursos`"

# Paleta categórica (8 slots, ordem fixa) validada com scripts/validate_palette.js
# da skill dataviz para o fundo escuro do app (#1a1a19): banda de luminosidade,
# piso de croma e separação CVD (daltonismo) todos PASS; pior par adjacente
# (verde/amarelo) fica na faixa "floor" (ΔE 10.3), por isso os gráficos que os
# usam sempre têm legenda/rótulo visível (nunca só a cor identifica a série).
# Ordem: azul, água, amarelo, verde, violeta, vermelho, magenta, laranja.
CATEGORICAL_PALETTE = [
    "#3987e5", "#199e70", "#c98500", "#008300",
    "#9085e9", "#e66767", "#d55181", "#d95926",
]
RADAR_COLORS = CATEGORICAL_PALETTE[:5]

# Abaixo desse total de vagas somadas, a taxa de ocupação vira ruído
# estatístico: um curso/campus/ano com só 1-2 vagas formalmente abertas mas
# vários ingressantes por outras vias (vaga remanescente, transferência) já
# produz uma taxa de centenas de % que não representa nada de real.
MIN_VG_CONFIAVEL = 10


@st.cache_resource
def get_client():
    creds_info = st.secrets["gcp_service_account"]
    credentials = service_account.Credentials.from_service_account_info(creds_info)
    return bigquery.Client(credentials=credentials, project=PROJECT_ID)


client = get_client()


@st.cache_data
def run_query(sql: str) -> pd.DataFrame:
    return client.query(sql).to_dataframe()


@st.cache_data
def load_filter_options() -> pd.DataFrame:
    """Combinações distintas das dimensões geográficas/institucionais/atributo
    (~23 mil linhas) — usada para encadear cada filtro da sidebar às escolhas
    já feitas nos filtros anteriores (cascata)."""
    return run_query(f"""
        SELECT DISTINCT
            NU_ANO_CENSO, NO_REGIAO, NO_UF,
            TP_REDE_DESC, TP_CATEGORIA_ADMINISTRATIVA_DESC, TP_ORGANIZACAO_ACADEMICA_DESC,
            TP_MODALIDADE_ENSINO_DESC, TP_NIVEL_ACADEMICO_DESC, TP_GRAU_ACADEMICO_DESC,
            IN_GRATUITO_DESC, IN_CAPITAL_DESC
        FROM {TABLE}
    """)


@st.cache_data
def load_ies_names() -> list[str]:
    df = run_query(f"SELECT DISTINCT NO_IES FROM {TABLE} WHERE NO_IES IS NOT NULL")
    return sorted(df["NO_IES"].tolist())


@st.cache_data
def load_municipios() -> pd.DataFrame:
    return run_query(f"""
        SELECT DISTINCT NO_REGIAO, NO_UF, NO_MUNICIPIO
        FROM {TABLE}
        WHERE NO_MUNICIPIO IS NOT NULL
    """)


@st.cache_data
def load_curso_taxonomy() -> pd.DataFrame:
    """Combinações distintas de área geral / área específica / nome do curso
    (~3,6 mil linhas) — encadeadas entre si (área geral -> específica -> curso)."""
    return run_query(f"""
        SELECT DISTINCT NO_CINE_AREA_GERAL, NO_CINE_AREA_ESPECIFICA, NO_CURSO
        FROM {TABLE}
        WHERE NO_CINE_AREA_GERAL IS NOT NULL
    """)


def cascade_options(df: pd.DataFrame, column: str, **filtros: list) -> list:
    """Opções distintas de `column` em `df`, restritas por todo filtro (nome
    da coluna -> lista de valores selecionados) já aplicado antes dele. Uma
    lista vazia em `filtros` é tratada como "sem restrição ainda"."""
    sub = df
    for col, selecionados in filtros.items():
        if selecionados:
            sub = sub[sub[col].isin(selecionados)]
    return sorted(sub[column].dropna().unique())


opts = load_filter_options()
todas_ies = load_ies_names()
municipios = load_municipios()
cursos_tax = load_curso_taxonomy()

st.title("🎓 Censo da Educação Superior — INEP")
st.caption(
    "Matrículas, ingressantes, concluintes e taxa de ocupação de vagas em cursos de "
    "graduação no Brasil (2009-2024). Fonte: microdados oficiais do INEP "
    "(MICRODADOS_CADASTRO_CURSOS), servidos via BigQuery. Clique num ano, numa UF, "
    "numa fatia do gráfico de modalidade ou numa linha do ranking para filtrar o "
    "restante do painel por aquele valor (crossfilter)."
)

# --- Crossfilter: estado das seleções feitas clicando nos gráficos --------
for key, default in [("cf_ano", None), ("cf_uf", None), ("cf_modalidade", None)]:
    if key not in st.session_state:
        st.session_state[key] = default


def _selection_of(event):
    """Normaliza o retorno de on_select do Streamlit (objeto ou dict) num dict."""
    if event is None:
        return {}
    sel = getattr(event, "selection", None)
    if sel is None and isinstance(event, dict):
        sel = event.get("selection", {})
    if sel is None:
        return {}
    if isinstance(sel, dict):
        return sel
    return {"points": getattr(sel, "points", []), "rows": getattr(sel, "rows", [])}


def _first_point_value(event, *keys):
    sel = _selection_of(event)
    points = sel.get("points", [])
    if not points:
        return None
    p = points[0]
    for k in keys:
        val = p.get(k) if isinstance(p, dict) else getattr(p, k, None)
        if val is not None:
            return val
    return None


with st.sidebar:
    st.header("Filtros")
    st.caption(
        "Cada filtro abaixo é subordinado aos anteriores — a lista de opções "
        "se restringe conforme você vai escolhendo, do mais geral pro mais "
        "específico."
    )

    st.subheader("📍 Localização")
    anos = sorted(opts["NU_ANO_CENSO"].unique())
    ano_sel = st.multiselect("Ano", anos, default=anos, placeholder="Selecione um ou mais anos")

    regioes = cascade_options(opts, "NO_REGIAO", NU_ANO_CENSO=ano_sel)
    regiao_sel = st.multiselect("Região", regioes, default=regioes, placeholder="Selecione uma ou mais regiões")

    ufs_disponiveis = cascade_options(
        opts, "NO_UF", NU_ANO_CENSO=ano_sel, NO_REGIAO=regiao_sel,
    )
    uf_sel = st.multiselect("UF", ufs_disponiveis, default=[], placeholder="Todas as UFs (opcional)")

    municipios_filtrados = municipios[municipios["NO_REGIAO"].isin(regiao_sel)]
    if uf_sel:
        municipios_filtrados = municipios_filtrados[municipios_filtrados["NO_UF"].isin(uf_sel)]
    municipios_disponiveis = sorted(municipios_filtrados["NO_MUNICIPIO"].dropna().unique())
    municipio_sel = st.multiselect(
        "Município", municipios_disponiveis, default=[],
        placeholder="Todos os municípios (opcional)",
        help="Subordinado a Região e UF.",
    )

    st.divider()
    st.subheader("📚 Curso")
    areas_gerais = sorted(cursos_tax["NO_CINE_AREA_GERAL"].dropna().unique())
    area_geral_sel = st.multiselect(
        "Área geral do curso", areas_gerais, default=[],
        placeholder="Todas as áreas (opcional)",
    )

    areas_especificas = cascade_options(
        cursos_tax, "NO_CINE_AREA_ESPECIFICA", NO_CINE_AREA_GERAL=area_geral_sel,
    )
    area_especifica_sel = st.multiselect(
        "Área específica", areas_especificas, default=[],
        placeholder="Todas as áreas específicas (opcional)",
        help="Subordinado a Área geral.",
    )

    cursos_disponiveis = cascade_options(
        cursos_tax, "NO_CURSO",
        NO_CINE_AREA_GERAL=area_geral_sel, NO_CINE_AREA_ESPECIFICA=area_especifica_sel,
    )
    curso_sel = st.multiselect(
        "Nome do curso", cursos_disponiveis, default=[],
        placeholder="Todos os cursos (digite para buscar)",
        help="Subordinado a Área geral e Área específica. Digite para buscar entre milhares de cursos.",
    )

    grau_disponiveis = cascade_options(
        opts, "TP_GRAU_ACADEMICO_DESC", NU_ANO_CENSO=ano_sel,
    )
    grau_sel = st.multiselect(
        "Grau acadêmico", grau_disponiveis, default=[],
        placeholder="Todos os graus (opcional)",
        help="Bacharelado, Licenciatura, Tecnológico etc.",
    )
    nivel_disponiveis = cascade_options(
        opts, "TP_NIVEL_ACADEMICO_DESC", NU_ANO_CENSO=ano_sel, TP_GRAU_ACADEMICO_DESC=grau_sel,
    )
    nivel_sel = st.multiselect(
        "Nível acadêmico", nivel_disponiveis, default=[],
        placeholder="Todos os níveis (opcional)",
        help="Subordinado a Grau acadêmico.",
    )

    st.divider()
    st.subheader("🏫 Instituição")
    rede_disponiveis = cascade_options(
        opts, "TP_REDE_DESC", NU_ANO_CENSO=ano_sel, NO_REGIAO=regiao_sel,
    )
    rede_sel = st.multiselect(
        "Rede", rede_disponiveis, default=rede_disponiveis,
        placeholder="Selecione uma ou mais redes",
    )

    categoria_disponiveis = cascade_options(
        opts, "TP_CATEGORIA_ADMINISTRATIVA_DESC", TP_REDE_DESC=rede_sel,
    )
    categoria_sel = st.multiselect(
        "Categoria administrativa", categoria_disponiveis, default=[],
        placeholder="Todas as categorias (opcional)",
        help="Subordinado a Rede (ex.: dentro de \"Pública\", Federal/Estadual/Municipal).",
    )

    organizacao_disponiveis = cascade_options(
        opts, "TP_ORGANIZACAO_ACADEMICA_DESC",
        TP_REDE_DESC=rede_sel, TP_CATEGORIA_ADMINISTRATIVA_DESC=categoria_sel,
    )
    organizacao_sel = st.multiselect(
        "Organização acadêmica", organizacao_disponiveis, default=[],
        placeholder="Todas as organizações (opcional)",
        help="Universidade, Centro Universitário, Faculdade, IF, CEFET.",
    )

    st.divider()
    st.subheader("⚙️ Outros atributos")
    modalidade_disponiveis = cascade_options(
        opts, "TP_MODALIDADE_ENSINO_DESC",
        TP_REDE_DESC=rede_sel, TP_ORGANIZACAO_ACADEMICA_DESC=organizacao_sel,
    )
    modalidade_sel = st.multiselect(
        "Modalidade", modalidade_disponiveis, default=modalidade_disponiveis,
        placeholder="Selecione uma ou mais modalidades",
    )
    gratuito_disponiveis = cascade_options(
        opts, "IN_GRATUITO_DESC", TP_MODALIDADE_ENSINO_DESC=modalidade_sel,
    )
    gratuito_sel = st.multiselect(
        "Curso gratuito?", gratuito_disponiveis, default=gratuito_disponiveis,
        placeholder="Selecione uma ou mais opções",
    )
    capital_disponiveis = cascade_options(
        opts, "IN_CAPITAL_DESC", IN_GRATUITO_DESC=gratuito_sel,
    )
    capital_sel = st.multiselect(
        "Localização em capital?", capital_disponiveis, default=capital_disponiveis,
        placeholder="Selecione uma ou mais opções",
    )

    st.divider()
    st.caption("Crossfilter (cliques nos gráficos)")
    cf_ativo = any(st.session_state[k] for k in ("cf_ano", "cf_uf", "cf_modalidade"))
    if st.session_state["cf_ano"]:
        st.write(f"🔹 Ano = **{st.session_state['cf_ano']}**")
    if st.session_state["cf_uf"]:
        st.write(f"🔹 UF = **{st.session_state['cf_uf']}**")
    if st.session_state["cf_modalidade"]:
        st.write(f"🔹 Modalidade = **{st.session_state['cf_modalidade']}**")
    if not cf_ativo:
        st.caption("(nenhuma seleção de gráfico ativa)")
    if st.button("🔄 Limpar cliques nos gráficos", disabled=not cf_ativo):
        st.session_state["cf_ano"] = None
        st.session_state["cf_uf"] = None
        st.session_state["cf_modalidade"] = None
        st.rerun()


def in_clause(col, values):
    if not values:
        return "TRUE"
    vals = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"{col} IN ({vals})"


def in_clause_numeric(col, values):
    if not values:
        return "TRUE"
    vals = ", ".join(str(int(v)) for v in values)
    return f"{col} IN ({vals})"


base_where_parts = [
    in_clause_numeric("NU_ANO_CENSO", ano_sel),
    in_clause("NO_REGIAO", regiao_sel),
    in_clause("TP_REDE_DESC", rede_sel),
    in_clause("TP_MODALIDADE_ENSINO_DESC", modalidade_sel),
    in_clause("IN_GRATUITO_DESC", gratuito_sel),
    in_clause("IN_CAPITAL_DESC", capital_sel),
]
optional_filters = [
    ("NO_UF", uf_sel),
    ("NO_MUNICIPIO", municipio_sel),
    ("NO_CINE_AREA_GERAL", area_geral_sel),
    ("NO_CINE_AREA_ESPECIFICA", area_especifica_sel),
    ("NO_CURSO", curso_sel),
    ("TP_GRAU_ACADEMICO_DESC", grau_sel),
    ("TP_NIVEL_ACADEMICO_DESC", nivel_sel),
    ("TP_CATEGORIA_ADMINISTRATIVA_DESC", categoria_sel),
    ("TP_ORGANIZACAO_ACADEMICA_DESC", organizacao_sel),
]
for coluna, selecionados in optional_filters:
    if selecionados:
        base_where_parts.append(in_clause(coluna, selecionados))
where_clause = " AND ".join(base_where_parts)


def build_where(exclude: set[str] = frozenset()) -> str:
    """Filtro base da sidebar + crossfilters ativos, exceto a dimensão do
    próprio gráfico que está sendo desenhado (para ele continuar clicável)."""
    parts = [where_clause]
    if "ano" not in exclude and st.session_state["cf_ano"]:
        parts.append(in_clause_numeric("NU_ANO_CENSO", [st.session_state["cf_ano"]]))
    if "uf" not in exclude and st.session_state["cf_uf"]:
        parts.append(in_clause("NO_UF", [st.session_state["cf_uf"]]))
    if "modalidade" not in exclude and st.session_state["cf_modalidade"]:
        parts.append(in_clause("TP_MODALIDADE_ENSINO_DESC", [st.session_state["cf_modalidade"]]))
    return " AND ".join(parts)


# --- KPIs (uma única query agregada, com todos os crossfilters) ----------
kpis = run_query(f"""
    SELECT
        SUM(QT_MAT) AS qt_mat,
        SUM(QT_ING) AS qt_ing,
        SUM(QT_CONC) AS qt_conc,
        COUNT(DISTINCT CO_IES) AS n_ies,
        SUM(QT_ING_DIURNO) AS ing_diurno,
        SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
        SUM(QT_ING_NOTURNO) AS ing_noturno,
        SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno
    FROM {TABLE}
    WHERE {build_where()}
""").iloc[0]

if pd.isna(kpis["qt_mat"]):
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

kpi_cols = st.columns(5)
kpi_cols[0].metric("Matrículas (QT_MAT)", f"{kpis['qt_mat']:,.0f}".replace(",", "."))
kpi_cols[1].metric("Ingressantes (QT_ING)", f"{kpis['qt_ing']:,.0f}".replace(",", "."))
kpi_cols[2].metric("Concluintes (QT_CONC)", f"{kpis['qt_conc']:,.0f}".replace(",", "."))
kpi_cols[3].metric("IES distintas", f"{kpis['n_ies']:,.0f}".replace(",", "."))

taxa_diurno = pct_scalar(kpis["ing_diurno"], kpis["vg_diurno"])
taxa_noturno = pct_scalar(kpis["ing_noturno"], kpis["vg_noturno"])
kpi_cols[4].metric(
    "% vagas preenchidas por ingressantes (diurno / noturno)",
    f"{taxa_diurno:.1f}% / {taxa_noturno:.1f}%"
    if taxa_diurno is not None and taxa_noturno is not None else "n/d",
    help=(
        "QT_ING ÷ QT_VG_TOTAL (ingressantes daquele ano ÷ vagas oferecidas "
        "naquele ano). Não usamos QT_MAT (matrículas) no denominador junto "
        "com vagas porque QT_MAT soma TODOS os alunos ativos no curso "
        "(calouros a formandos, situação 'Cursando'/'Formado'), enquanto "
        "QT_VG_TOTAL é só a vaga de calouro daquele ano — cursos de vários "
        "anos dariam >100% mesmo sem nenhuma vaga sobrando, por definição."
    ),
)

st.divider()

# --- Série temporal (clicável -> filtra por ano) --------------------------
st.subheader("Evolução anual")
st.caption("Clique num ponto do gráfico para fixar o ano em todo o painel.")
serie = run_query(f"""
    SELECT NU_ANO_CENSO, SUM(QT_MAT) AS QT_MAT, SUM(QT_ING) AS QT_ING, SUM(QT_CONC) AS QT_CONC
    FROM {TABLE}
    WHERE {build_where(exclude={"ano"})}
    GROUP BY NU_ANO_CENSO
    ORDER BY NU_ANO_CENSO
""").rename(columns={
    "QT_MAT": "Matrículas", "QT_ING": "Ingressantes", "QT_CONC": "Concluintes",
}).melt(id_vars="NU_ANO_CENSO", var_name="Métrica", value_name="Quantidade")
fig_serie = px.line(
    serie, x="NU_ANO_CENSO", y="Quantidade", color="Métrica", markers=True,
    color_discrete_map={
        "Matrículas": CATEGORICAL_PALETTE[0],
        "Ingressantes": CATEGORICAL_PALETTE[1],
        "Concluintes": CATEGORICAL_PALETTE[2],
    },
    labels={"NU_ANO_CENSO": "Ano"},
)
evento_serie = st.plotly_chart(
    fig_serie, use_container_width=True, on_select="rerun",
    selection_mode=("points",), key="chart_serie",
)
clicked_ano = _first_point_value(evento_serie, "x")
if clicked_ano is not None and int(clicked_ano) != st.session_state["cf_ano"]:
    st.session_state["cf_ano"] = int(clicked_ano)
    st.rerun()

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Matrículas por UF")
    st.caption("Clique numa barra para fixar a UF.")
    por_uf = run_query(f"""
        SELECT NO_UF, SUM(QT_MAT) AS QT_MAT
        FROM {TABLE}
        WHERE {build_where(exclude={"uf"})}
        GROUP BY NO_UF
        ORDER BY QT_MAT DESC
    """)
    fig_uf = px.bar(
        por_uf, x="NO_UF", y="QT_MAT", color_discrete_sequence=[CATEGORICAL_PALETTE[0]],
        labels={"NO_UF": "UF", "QT_MAT": "Matrículas"},
    )
    evento_uf = st.plotly_chart(
        fig_uf, use_container_width=True, on_select="rerun",
        selection_mode=("points",), key="chart_uf",
    )
    clicked_uf = _first_point_value(evento_uf, "x")
    if clicked_uf is not None and clicked_uf != st.session_state["cf_uf"]:
        st.session_state["cf_uf"] = clicked_uf
        st.rerun()

with col_b:
    st.subheader("Presencial x EAD (matrículas)")
    st.caption("Clique numa fatia para fixar a modalidade.")
    por_mod = run_query(f"""
        SELECT TP_MODALIDADE_ENSINO_DESC, SUM(QT_MAT) AS QT_MAT
        FROM {TABLE}
        WHERE {build_where(exclude={"modalidade"})}
        GROUP BY TP_MODALIDADE_ENSINO_DESC
    """)
    fig_mod = px.pie(
        por_mod, names="TP_MODALIDADE_ENSINO_DESC", values="QT_MAT",
        color="TP_MODALIDADE_ENSINO_DESC",
        color_discrete_map={
            "Presencial": CATEGORICAL_PALETTE[0],
            "Curso a distância": CATEGORICAL_PALETTE[1],
        },
        labels={"TP_MODALIDADE_ENSINO_DESC": "Modalidade", "QT_MAT": "Matrículas"},
    )
    evento_mod = st.plotly_chart(
        fig_mod, use_container_width=True, on_select="rerun",
        selection_mode=("points",), key="chart_mod",
    )
    clicked_mod = _first_point_value(evento_mod, "label", "x")
    if clicked_mod is not None and clicked_mod != st.session_state["cf_modalidade"]:
        st.session_state["cf_modalidade"] = clicked_mod
        st.rerun()

st.subheader("Taxa de ocupação de vagas — diurno vs. noturno, por UF")
st.caption(
    "Ingressantes daquele ano ÷ vagas oferecidas naquele ano (não usamos "
    "matrículas totais aqui — ver explicação no ícone (?) do KPI acima)."
)
ocup_uf = run_query(f"""
    SELECT
        NO_UF,
        SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
        SUM(QT_ING_DIURNO) AS ing_diurno,
        SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno,
        SUM(QT_ING_NOTURNO) AS ing_noturno
    FROM {TABLE}
    WHERE {build_where(exclude={"uf"})}
    GROUP BY NO_UF
""")
ocup_uf["Diurno"] = pct(ocup_uf["ing_diurno"], ocup_uf["vg_diurno"])
ocup_uf["Noturno"] = pct(ocup_uf["ing_noturno"], ocup_uf["vg_noturno"])
ocup_long = ocup_uf.melt(
    id_vars="NO_UF", value_vars=["Diurno", "Noturno"],
    var_name="Turno", value_name="% de vagas preenchidas",
)
fig_ocup = px.bar(
    ocup_long, x="NO_UF", y="% de vagas preenchidas", color="Turno", barmode="group",
    color_discrete_map={
        "Diurno": CATEGORICAL_PALETTE[0],
        "Noturno": CATEGORICAL_PALETTE[1],
    },
    labels={"NO_UF": "UF"},
)
evento_ocup = st.plotly_chart(
    fig_ocup, use_container_width=True, on_select="rerun",
    selection_mode=("points",), key="chart_ocup",
)
clicked_uf_ocup = _first_point_value(evento_ocup, "x")
if clicked_uf_ocup is not None and clicked_uf_ocup != st.session_state["cf_uf"]:
    st.session_state["cf_uf"] = clicked_uf_ocup
    st.rerun()

st.subheader("Ranking de IES por matrículas")
st.caption("Clique numa ou mais linhas da tabela para comparar essas IES na seção abaixo.")
top_n = st.slider("Top N instituições", 5, 50, 20)
ranking = run_query(f"""
    SELECT NO_IES, SUM(QT_MAT) AS QT_MAT, SUM(QT_ING) AS QT_ING, SUM(QT_CONC) AS QT_CONC
    FROM {TABLE}
    WHERE {build_where()}
    GROUP BY NO_IES
    ORDER BY QT_MAT DESC
    LIMIT {int(top_n)}
""")
evento_ranking = st.dataframe(
    ranking.rename(columns={
        "NO_IES": "Instituição", "QT_MAT": "Matrículas",
        "QT_ING": "Ingressantes", "QT_CONC": "Concluintes",
    }),
    use_container_width=True, on_select="rerun",
    selection_mode="multi-row", key="ranking_df",
)

if "ies_multiselect" not in st.session_state:
    st.session_state["ies_multiselect"] = ranking["NO_IES"].head(3).tolist() if not ranking.empty else []

linhas_selecionadas = _selection_of(evento_ranking).get("rows", [])
if linhas_selecionadas:
    ies_da_tabela = ranking.iloc[linhas_selecionadas]["NO_IES"].tolist()
    if set(ies_da_tabela) != set(st.session_state["ies_multiselect"]):
        st.session_state["ies_multiselect"] = ies_da_tabela
        st.rerun()

st.divider()

# --- Comparação entre IES específicas -----------------------------------
st.subheader("Comparar IES por nome")
ies_sel = st.multiselect(
    "Buscar e selecionar instituições (digite parte do nome, ou clique numa linha do ranking acima)",
    todas_ies,
    placeholder="Digite o nome de uma instituição",
    key="ies_multiselect",
)

if ies_sel:
    comp_where = build_where() + " AND " + in_clause("NO_IES", ies_sel)

    comp_serie = run_query(f"""
        SELECT NO_IES, NU_ANO_CENSO, SUM(QT_MAT) AS QT_MAT, SUM(QT_ING) AS QT_ING, SUM(QT_CONC) AS QT_CONC
        FROM {TABLE}
        WHERE {comp_where}
        GROUP BY NO_IES, NU_ANO_CENSO
        ORDER BY NU_ANO_CENSO
    """)
    fig_comp = px.line(
        comp_serie, x="NU_ANO_CENSO", y="QT_MAT", color="NO_IES", markers=True,
        color_discrete_sequence=CATEGORICAL_PALETTE,
        labels={"QT_MAT": "Matrículas", "NU_ANO_CENSO": "Ano", "NO_IES": "Instituição"},
    )
    st.plotly_chart(fig_comp, use_container_width=True, key="chart_comp_serie")

    comp_resumo = run_query(f"""
        SELECT
            NO_IES,
            SUM(QT_MAT) AS QT_MAT,
            SUM(QT_ING) AS QT_ING,
            SUM(QT_CONC) AS QT_CONC,
            SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
            SUM(QT_ING_DIURNO) AS ing_diurno,
            SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno,
            SUM(QT_ING_NOTURNO) AS ing_noturno
        FROM {TABLE}
        WHERE {comp_where}
        GROUP BY NO_IES
        ORDER BY QT_MAT DESC
    """)
    comp_resumo["taxa_ocupacao_diurno_%"] = pct(comp_resumo["ing_diurno"], comp_resumo["vg_diurno"])
    comp_resumo["taxa_ocupacao_noturno_%"] = pct(comp_resumo["ing_noturno"], comp_resumo["vg_noturno"])
    comp_resumo.loc[comp_resumo["vg_diurno"] < MIN_VG_CONFIAVEL, "taxa_ocupacao_diurno_%"] = np.nan
    comp_resumo.loc[comp_resumo["vg_noturno"] < MIN_VG_CONFIAVEL, "taxa_ocupacao_noturno_%"] = np.nan
    st.caption(
        f"Taxas de ocupação com menos de {MIN_VG_CONFIAVEL} vagas somadas no "
        "turno aparecem em branco (amostra pequena demais para ser confiável)."
    )
    st.dataframe(
        comp_resumo[[
            "NO_IES", "QT_MAT", "QT_ING", "QT_CONC",
            "taxa_ocupacao_diurno_%", "taxa_ocupacao_noturno_%",
        ]].rename(columns={
            "NO_IES": "Instituição", "QT_MAT": "Matrículas",
            "QT_ING": "Ingressantes", "QT_CONC": "Concluintes",
            "taxa_ocupacao_diurno_%": "% vagas preenchidas (diurno)",
            "taxa_ocupacao_noturno_%": "% vagas preenchidas (noturno)",
        }),
        use_container_width=True,
    )

    MAX_IES_RADAR = 5
    ies_radar = ies_sel[:MAX_IES_RADAR]
    radar_where = build_where() + " AND " + in_clause("NO_IES", ies_radar)
    if len(ies_sel) > MAX_IES_RADAR:
        st.caption(
            f"⚠️ Os radares abaixo mostram só as {MAX_IES_RADAR} primeiras IES "
            f"selecionadas ({', '.join(ies_radar)}) — com mais linhas o gráfico "
            "fica ilegível. Remova alguma IES da seleção acima para comparar outras."
        )

    st.markdown("**Ocupação de vagas por área de curso**")
    st.caption(
        "% de vagas preenchidas (ingressantes daquele ano ÷ vagas ofertadas "
        "naquele ano) por área geral de curso (classificação CINE/Unesco do "
        f"INEP), uma linha por IES. Combinações com menos de {MIN_VG_CONFIAVEL} "
        "vagas somadas no período/filtro selecionado ficam de fora — com "
        "amostra tão pequena, um único curso/campus/ano com poucas vagas "
        "formalmente abertas mas vários ingressantes por outras vias "
        "(vagas remanescentes, transferência) já produz uma taxa >>100% que "
        "não representa nada de real."
    )
    radar_df = run_query(f"""
        SELECT
            NO_IES,
            NO_CINE_AREA_GERAL,
            SUM(QT_ING) AS qt_ing,
            SUM(QT_VG_TOTAL) AS qt_vg_total
        FROM {TABLE}
        WHERE {radar_where} AND NO_CINE_AREA_GERAL IS NOT NULL
        GROUP BY NO_IES, NO_CINE_AREA_GERAL
    """)
    if radar_df.empty:
        st.caption("Sem dados de área de curso para essa seleção.")
    else:
        radar_df["taxa_ocupacao_%"] = pct(radar_df["qt_ing"], radar_df["qt_vg_total"])
        radar_df.loc[radar_df["qt_vg_total"] < MIN_VG_CONFIAVEL, "taxa_ocupacao_%"] = np.nan
        fig_radar = px.line_polar(
            radar_df.dropna(subset=["taxa_ocupacao_%"]),
            r="taxa_ocupacao_%", theta="NO_CINE_AREA_GERAL", color="NO_IES",
            line_close=True, markers=True, color_discrete_sequence=RADAR_COLORS,
            labels={
                "taxa_ocupacao_%": "% de vagas preenchidas",
                "NO_CINE_AREA_GERAL": "Área do curso",
                "NO_IES": "Instituição",
            },
        )
        style_radar(fig_radar)
        st.plotly_chart(fig_radar, use_container_width=True, key="chart_radar_area")

    st.markdown("**Ocupação de vagas por curso específico**")
    st.caption("% de vagas preenchidas = ingressantes daquele ano ÷ vagas ofertadas naquele ano.")
    MAX_CURSOS_RADAR = 15
    if not curso_sel:
        st.caption(
            "Esse radar por curso individual só aparece quando você filtra "
            "**\"Nome do curso\"** na barra lateral (dentro de 📚 Curso) — sem "
            "esse filtro, existem milhares de cursos distintos e o gráfico "
            "ficaria ilegível. Estreite por Área geral/específica primeiro "
            "para achar os cursos mais rápido, depois escolha até "
            f"~{MAX_CURSOS_RADAR} cursos para comparar aqui."
        )
    else:
        cursos_radar = curso_sel[:MAX_CURSOS_RADAR]
        if len(curso_sel) > MAX_CURSOS_RADAR:
            st.caption(
                f"⚠️ Mostrando só os {MAX_CURSOS_RADAR} primeiros cursos "
                "selecionados, para manter o gráfico legível."
            )
        radar_curso_df = run_query(f"""
            SELECT
                NO_IES,
                NO_CURSO,
                SUM(QT_ING) AS qt_ing,
                SUM(QT_VG_TOTAL) AS qt_vg_total
            FROM {TABLE}
            WHERE {radar_where} AND {in_clause("NO_CURSO", cursos_radar)}
            GROUP BY NO_IES, NO_CURSO
        """)
        if radar_curso_df.empty:
            st.caption("Sem dados para essa combinação de cursos e IES.")
        else:
            radar_curso_df["taxa_ocupacao_%"] = pct(
                radar_curso_df["qt_ing"], radar_curso_df["qt_vg_total"]
            )
            radar_curso_df.loc[
                radar_curso_df["qt_vg_total"] < MIN_VG_CONFIAVEL, "taxa_ocupacao_%"
            ] = np.nan
            fig_radar_curso = px.line_polar(
                radar_curso_df.dropna(subset=["taxa_ocupacao_%"]),
                r="taxa_ocupacao_%", theta="NO_CURSO", color="NO_IES",
                line_close=True, markers=True, color_discrete_sequence=RADAR_COLORS,
                labels={
                    "taxa_ocupacao_%": "% de vagas preenchidas",
                    "NO_CURSO": "Curso",
                    "NO_IES": "Instituição",
                },
            )
            style_radar(fig_radar_curso)
            st.plotly_chart(fig_radar_curso, use_container_width=True, key="chart_radar_curso")
else:
    st.caption("Selecione uma ou mais instituições acima para comparar.")

st.caption(
    "Dados agregados por curso/IES/ano — o INEP não publica microdados de aluno "
    "individual desde a reformulação do Censo em 2019 (LGPD)."
)
