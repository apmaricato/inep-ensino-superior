"""
Painel do Censo da Educação Superior (INEP) - matrículas, ingressantes,
concluintes e taxa de ocupação de vagas, 2020-2024.

Os dados vivem no BigQuery (projeto apmaricato2, dataset inep_ensino_superior,
tabela cursos). Todas as agregações rodam via SQL no servidor do BigQuery —
o app nunca carrega a tabela completa (2,75M linhas) para a memória local,
o que é essencial no free tier do Streamlit Community Cloud (1GB de RAM).

Roda localmente com:
    streamlit run app/streamlit_app.py
(usa .streamlit/secrets.toml local com a chave da service account)
"""

from google.cloud import bigquery
from google.oauth2 import service_account
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Censo da Educação Superior (INEP)",
    page_icon="🎓",
    layout="wide",
)

PROJECT_ID = "apmaricato2"
TABLE = f"`{PROJECT_ID}.inep_ensino_superior.cursos`"


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
    return run_query(f"""
        SELECT DISTINCT
            NU_ANO_CENSO, NO_REGIAO, NO_UF, TP_REDE_DESC,
            TP_MODALIDADE_ENSINO_DESC, IN_GRATUITO_DESC, IN_CAPITAL_DESC
        FROM {TABLE}
    """)


@st.cache_data
def load_ies_names() -> list[str]:
    df = run_query(f"SELECT DISTINCT NO_IES FROM {TABLE} WHERE NO_IES IS NOT NULL")
    return sorted(df["NO_IES"].tolist())


opts = load_filter_options()
todas_ies = load_ies_names()

st.title("🎓 Censo da Educação Superior — INEP")
st.caption(
    "Matrículas, ingressantes, concluintes e taxa de ocupação de vagas em cursos de "
    "graduação no Brasil (2020-2024). Fonte: microdados oficiais do INEP "
    "(MICRODADOS_CADASTRO_CURSOS), servidos via BigQuery."
)

with st.sidebar:
    st.header("Filtros")

    anos = sorted(opts["NU_ANO_CENSO"].unique())
    ano_sel = st.multiselect("Ano", anos, default=anos)

    regioes = sorted(opts["NO_REGIAO"].dropna().unique())
    regiao_sel = st.multiselect("Região", regioes, default=regioes)

    ufs_disponiveis = sorted(
        opts.loc[opts["NO_REGIAO"].isin(regiao_sel), "NO_UF"].dropna().unique()
    )
    uf_sel = st.multiselect("UF", ufs_disponiveis, default=[])

    rede_sel = st.multiselect(
        "Rede", sorted(opts["TP_REDE_DESC"].dropna().unique()),
        default=sorted(opts["TP_REDE_DESC"].dropna().unique()),
    )
    modalidade_sel = st.multiselect(
        "Modalidade", sorted(opts["TP_MODALIDADE_ENSINO_DESC"].dropna().unique()),
        default=sorted(opts["TP_MODALIDADE_ENSINO_DESC"].dropna().unique()),
    )
    gratuito_sel = st.multiselect(
        "Curso gratuito?", sorted(opts["IN_GRATUITO_DESC"].dropna().unique()),
        default=sorted(opts["IN_GRATUITO_DESC"].dropna().unique()),
    )
    capital_sel = st.multiselect(
        "Localização em capital?", sorted(opts["IN_CAPITAL_DESC"].dropna().unique()),
        default=sorted(opts["IN_CAPITAL_DESC"].dropna().unique()),
    )


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


where_parts = [
    in_clause_numeric("NU_ANO_CENSO", ano_sel),
    in_clause("NO_REGIAO", regiao_sel),
    in_clause("TP_REDE_DESC", rede_sel),
    in_clause("TP_MODALIDADE_ENSINO_DESC", modalidade_sel),
    in_clause("IN_GRATUITO_DESC", gratuito_sel),
    in_clause("IN_CAPITAL_DESC", capital_sel),
]
if uf_sel:
    where_parts.append(in_clause("NO_UF", uf_sel))
where_clause = " AND ".join(where_parts)

# --- KPIs (uma única query agregada) ------------------------------------
kpis = run_query(f"""
    SELECT
        SUM(QT_MAT) AS qt_mat,
        SUM(QT_ING) AS qt_ing,
        SUM(QT_CONC) AS qt_conc,
        COUNT(DISTINCT CO_IES) AS n_ies,
        SUM(QT_MAT_DIURNO) AS mat_diurno,
        SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
        SUM(QT_MAT_NOTURNO) AS mat_noturno,
        SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno
    FROM {TABLE}
    WHERE {where_clause}
""").iloc[0]

if pd.isna(kpis["qt_mat"]):
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

kpi_cols = st.columns(5)
kpi_cols[0].metric("Matrículas (QT_MAT)", f"{kpis['qt_mat']:,.0f}".replace(",", "."))
kpi_cols[1].metric("Ingressantes (QT_ING)", f"{kpis['qt_ing']:,.0f}".replace(",", "."))
kpi_cols[2].metric("Concluintes (QT_CONC)", f"{kpis['qt_conc']:,.0f}".replace(",", "."))
kpi_cols[3].metric("IES distintas", f"{kpis['n_ies']:,.0f}".replace(",", "."))

taxa_diurno = kpis["mat_diurno"] / kpis["vg_diurno"] * 100 if kpis["vg_diurno"] else None
taxa_noturno = kpis["mat_noturno"] / kpis["vg_noturno"] * 100 if kpis["vg_noturno"] else None
kpi_cols[4].metric(
    "% vagas preenchidas (diurno / noturno)",
    f"{taxa_diurno:.1f}% / {taxa_noturno:.1f}%" if taxa_diurno and taxa_noturno else "n/d",
)

st.divider()

# --- Série temporal (agregada via SQL) -----------------------------------
st.subheader("Evolução anual")
serie = run_query(f"""
    SELECT NU_ANO_CENSO, SUM(QT_MAT) AS QT_MAT, SUM(QT_ING) AS QT_ING, SUM(QT_CONC) AS QT_CONC
    FROM {TABLE}
    WHERE {where_clause}
    GROUP BY NU_ANO_CENSO
    ORDER BY NU_ANO_CENSO
""").melt(id_vars="NU_ANO_CENSO", var_name="métrica", value_name="valor")
fig_serie = px.line(serie, x="NU_ANO_CENSO", y="valor", color="métrica", markers=True)
st.plotly_chart(fig_serie, use_container_width=True)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Matrículas por UF")
    por_uf = run_query(f"""
        SELECT NO_UF, SUM(QT_MAT) AS QT_MAT
        FROM {TABLE}
        WHERE {where_clause}
        GROUP BY NO_UF
        ORDER BY QT_MAT DESC
    """)
    fig_uf = px.bar(por_uf, x="NO_UF", y="QT_MAT")
    st.plotly_chart(fig_uf, use_container_width=True)

with col_b:
    st.subheader("Presencial x EAD (matrículas)")
    por_mod = run_query(f"""
        SELECT TP_MODALIDADE_ENSINO_DESC, SUM(QT_MAT) AS QT_MAT
        FROM {TABLE}
        WHERE {where_clause}
        GROUP BY TP_MODALIDADE_ENSINO_DESC
    """)
    fig_mod = px.pie(por_mod, names="TP_MODALIDADE_ENSINO_DESC", values="QT_MAT")
    st.plotly_chart(fig_mod, use_container_width=True)

st.subheader("Taxa de ocupação de vagas — diurno vs. noturno, por UF")
ocup_uf = run_query(f"""
    SELECT
        NO_UF,
        SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
        SUM(QT_MAT_DIURNO) AS mat_diurno,
        SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno,
        SUM(QT_MAT_NOTURNO) AS mat_noturno
    FROM {TABLE}
    WHERE {where_clause}
    GROUP BY NO_UF
""")
ocup_uf["taxa_diurno_%"] = (ocup_uf["mat_diurno"] / ocup_uf["vg_diurno"].replace(0, pd.NA) * 100).round(1)
ocup_uf["taxa_noturno_%"] = (ocup_uf["mat_noturno"] / ocup_uf["vg_noturno"].replace(0, pd.NA) * 100).round(1)
ocup_long = ocup_uf.melt(
    id_vars="NO_UF", value_vars=["taxa_diurno_%", "taxa_noturno_%"],
    var_name="turno", value_name="taxa_ocupacao_%",
)
fig_ocup = px.bar(ocup_long, x="NO_UF", y="taxa_ocupacao_%", color="turno", barmode="group")
st.plotly_chart(fig_ocup, use_container_width=True)

st.subheader("Ranking de IES por matrículas")
top_n = st.slider("Top N instituições", 5, 50, 20)
ranking = run_query(f"""
    SELECT NO_IES, SUM(QT_MAT) AS QT_MAT, SUM(QT_ING) AS QT_ING, SUM(QT_CONC) AS QT_CONC
    FROM {TABLE}
    WHERE {where_clause}
    GROUP BY NO_IES
    ORDER BY QT_MAT DESC
    LIMIT {int(top_n)}
""")
st.dataframe(ranking, use_container_width=True)

st.divider()

# --- Comparação entre IES específicas -----------------------------------
st.subheader("Comparar IES por nome")
ies_sel = st.multiselect(
    "Buscar e selecionar instituições (digite parte do nome)",
    todas_ies,
    default=ranking["NO_IES"].head(3).tolist() if not ranking.empty else [],
)

if ies_sel:
    comp_where = where_clause + " AND " + in_clause("NO_IES", ies_sel)

    comp_serie = run_query(f"""
        SELECT NO_IES, NU_ANO_CENSO, SUM(QT_MAT) AS QT_MAT, SUM(QT_ING) AS QT_ING, SUM(QT_CONC) AS QT_CONC
        FROM {TABLE}
        WHERE {comp_where}
        GROUP BY NO_IES, NU_ANO_CENSO
        ORDER BY NU_ANO_CENSO
    """)
    fig_comp = px.line(
        comp_serie, x="NU_ANO_CENSO", y="QT_MAT", color="NO_IES", markers=True,
        labels={"QT_MAT": "Matrículas", "NU_ANO_CENSO": "Ano", "NO_IES": "IES"},
    )
    st.plotly_chart(fig_comp, use_container_width=True)

    comp_resumo = run_query(f"""
        SELECT
            NO_IES,
            SUM(QT_MAT) AS QT_MAT,
            SUM(QT_ING) AS QT_ING,
            SUM(QT_CONC) AS QT_CONC,
            SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
            SUM(QT_MAT_DIURNO) AS mat_diurno,
            SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno,
            SUM(QT_MAT_NOTURNO) AS mat_noturno
        FROM {TABLE}
        WHERE {comp_where}
        GROUP BY NO_IES
        ORDER BY QT_MAT DESC
    """)
    comp_resumo["taxa_ocupacao_diurno_%"] = (
        comp_resumo["mat_diurno"] / comp_resumo["vg_diurno"].replace(0, pd.NA) * 100
    ).round(1)
    comp_resumo["taxa_ocupacao_noturno_%"] = (
        comp_resumo["mat_noturno"] / comp_resumo["vg_noturno"].replace(0, pd.NA) * 100
    ).round(1)
    st.dataframe(
        comp_resumo[[
            "NO_IES", "QT_MAT", "QT_ING", "QT_CONC",
            "taxa_ocupacao_diurno_%", "taxa_ocupacao_noturno_%",
        ]],
        use_container_width=True,
    )
else:
    st.caption("Selecione uma ou mais instituições acima para comparar.")

st.caption(
    "Dados agregados por curso/IES/ano — o INEP não publica microdados de aluno "
    "individual desde a reformulação do Censo em 2019 (LGPD)."
)
