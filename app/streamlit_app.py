"""
Painel do Censo da Educação Superior (INEP) - matrículas, ingressantes,
concluintes e taxa de ocupação de vagas, 2020-2024.

Roda localmente com:
    streamlit run app/streamlit_app.py
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Censo da Educação Superior (INEP)",
    page_icon="🎓",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent.parent
PARQUET_GLOB = str(ROOT / "data" / "parquet" / "cursos_2020_2024.parquet")


@st.cache_resource
def get_con():
    return duckdb.connect()


con = get_con()


@st.cache_data
def load_filter_options():
    df = con.sql(f"""
        SELECT DISTINCT
            NU_ANO_CENSO, NO_REGIAO, NO_UF, TP_REDE_DESC,
            TP_MODALIDADE_ENSINO_DESC, IN_GRATUITO_DESC, IN_CAPITAL_DESC
        FROM '{PARQUET_GLOB}'
    """).df()
    return df


opts = load_filter_options()

st.title("🎓 Censo da Educação Superior — INEP")
st.caption(
    "Matrículas, ingressantes, concluintes e taxa de ocupação de vagas em cursos de "
    "graduação no Brasil (2020-2024). Fonte: microdados oficiais do INEP "
    "(MICRODADOS_CADASTRO_CURSOS)."
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
    vals = ", ".join(f"'{v}'" for v in values)
    return f"{col} IN ({vals})"


where_parts = [
    in_clause("NU_ANO_CENSO", ano_sel),
    in_clause("NO_REGIAO", regiao_sel),
    in_clause("TP_REDE_DESC", rede_sel),
    in_clause("TP_MODALIDADE_ENSINO_DESC", modalidade_sel),
    in_clause("IN_GRATUITO_DESC", gratuito_sel),
    in_clause("IN_CAPITAL_DESC", capital_sel),
]
if uf_sel:
    where_parts.append(in_clause("NO_UF", uf_sel))
where_clause = " AND ".join(where_parts)


@st.cache_data
def query_filtered(where_clause: str) -> pd.DataFrame:
    return con.sql(f"""
        SELECT *
        FROM '{PARQUET_GLOB}'
        WHERE {where_clause}
    """).df()


df = query_filtered(where_clause)

if df.empty:
    st.warning("Nenhum registro para os filtros selecionados.")
    st.stop()

# --- KPIs -------------------------------------------------------------
kpi_cols = st.columns(5)
kpi_cols[0].metric("Matrículas (QT_MAT)", f"{df['QT_MAT'].sum():,.0f}".replace(",", "."))
kpi_cols[1].metric("Ingressantes (QT_ING)", f"{df['QT_ING'].sum():,.0f}".replace(",", "."))
kpi_cols[2].metric("Concluintes (QT_CONC)", f"{df['QT_CONC'].sum():,.0f}".replace(",", "."))
kpi_cols[3].metric("IES distintas", f"{df['CO_IES'].nunique():,.0f}".replace(",", "."))

taxa_diurno = df["QT_MAT_DIURNO"].sum() / df["QT_VG_TOTAL_DIURNO"].sum() * 100 if df["QT_VG_TOTAL_DIURNO"].sum() else None
taxa_noturno = df["QT_MAT_NOTURNO"].sum() / df["QT_VG_TOTAL_NOTURNO"].sum() * 100 if df["QT_VG_TOTAL_NOTURNO"].sum() else None
kpi_cols[4].metric(
    "% vagas preenchidas (diurno / noturno)",
    f"{taxa_diurno:.1f}% / {taxa_noturno:.1f}%" if taxa_diurno and taxa_noturno else "n/d",
)

st.divider()

# --- Série temporal -----------------------------------------------------
st.subheader("Evolução anual")
serie = (
    df.groupby("NU_ANO_CENSO")[["QT_MAT", "QT_ING", "QT_CONC"]]
    .sum()
    .reset_index()
    .melt(id_vars="NU_ANO_CENSO", var_name="métrica", value_name="valor")
)
fig_serie = px.line(serie, x="NU_ANO_CENSO", y="valor", color="métrica", markers=True)
st.plotly_chart(fig_serie, use_container_width=True)

col_a, col_b = st.columns(2)

with col_a:
    st.subheader("Matrículas por UF")
    por_uf = df.groupby("NO_UF", as_index=False)["QT_MAT"].sum().sort_values("QT_MAT", ascending=False)
    fig_uf = px.bar(por_uf, x="NO_UF", y="QT_MAT")
    st.plotly_chart(fig_uf, use_container_width=True)

with col_b:
    st.subheader("Presencial x EAD (matrículas)")
    por_mod = df.groupby("TP_MODALIDADE_ENSINO_DESC", as_index=False)["QT_MAT"].sum()
    fig_mod = px.pie(por_mod, names="TP_MODALIDADE_ENSINO_DESC", values="QT_MAT")
    st.plotly_chart(fig_mod, use_container_width=True)

st.subheader("Taxa de ocupação de vagas — diurno vs. noturno, por UF")
ocup_uf = (
    df.groupby("NO_UF")
    .agg(
        vg_diurno=("QT_VG_TOTAL_DIURNO", "sum"),
        mat_diurno=("QT_MAT_DIURNO", "sum"),
        vg_noturno=("QT_VG_TOTAL_NOTURNO", "sum"),
        mat_noturno=("QT_MAT_NOTURNO", "sum"),
    )
    .reset_index()
)
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
ranking = (
    df.groupby("NO_IES", as_index=False)
    .agg(QT_MAT=("QT_MAT", "sum"), QT_ING=("QT_ING", "sum"), QT_CONC=("QT_CONC", "sum"))
    .sort_values("QT_MAT", ascending=False)
    .head(top_n)
)
st.dataframe(ranking, use_container_width=True)

st.caption(
    "Dados agregados por curso/IES/ano — o INEP não publica microdados de aluno "
    "individual desde a reformulação do Censo em 2019 (LGPD)."
)
