"""
Painel do Censo da Educação Superior (INEP) - matrículas, ingressantes,
concluintes e taxa de ocupação de vagas, 2015-2024.

Os dados vivem no BigQuery (projeto apmaricato2, dataset inep_ensino_superior,
tabela cursos). Todas as agregações rodam via SQL no servidor do BigQuery —
o app nunca carrega a tabela completa (3,48M linhas) para a memória local,
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
    "graduação no Brasil (2015-2024). Fonte: microdados oficiais do INEP "
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
if uf_sel:
    base_where_parts.append(in_clause("NO_UF", uf_sel))
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
        SUM(QT_MAT_DIURNO) AS mat_diurno,
        SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
        SUM(QT_MAT_NOTURNO) AS mat_noturno,
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

taxa_diurno = kpis["mat_diurno"] / kpis["vg_diurno"] * 100 if kpis["vg_diurno"] else None
taxa_noturno = kpis["mat_noturno"] / kpis["vg_noturno"] * 100 if kpis["vg_noturno"] else None
kpi_cols[4].metric(
    "% vagas preenchidas (diurno / noturno)",
    f"{taxa_diurno:.1f}% / {taxa_noturno:.1f}%" if taxa_diurno and taxa_noturno else "n/d",
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
""").melt(id_vars="NU_ANO_CENSO", var_name="métrica", value_name="valor")
fig_serie = px.line(serie, x="NU_ANO_CENSO", y="valor", color="métrica", markers=True)
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
    fig_uf = px.bar(por_uf, x="NO_UF", y="QT_MAT")
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
    fig_mod = px.pie(por_mod, names="TP_MODALIDADE_ENSINO_DESC", values="QT_MAT")
    evento_mod = st.plotly_chart(
        fig_mod, use_container_width=True, on_select="rerun",
        selection_mode=("points",), key="chart_mod",
    )
    clicked_mod = _first_point_value(evento_mod, "label", "x")
    if clicked_mod is not None and clicked_mod != st.session_state["cf_modalidade"]:
        st.session_state["cf_modalidade"] = clicked_mod
        st.rerun()

st.subheader("Taxa de ocupação de vagas — diurno vs. noturno, por UF")
ocup_uf = run_query(f"""
    SELECT
        NO_UF,
        SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
        SUM(QT_MAT_DIURNO) AS mat_diurno,
        SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno,
        SUM(QT_MAT_NOTURNO) AS mat_noturno
    FROM {TABLE}
    WHERE {build_where(exclude={"uf"})}
    GROUP BY NO_UF
""")
ocup_uf["taxa_diurno_%"] = (ocup_uf["mat_diurno"] / ocup_uf["vg_diurno"].replace(0, pd.NA) * 100).round(1)
ocup_uf["taxa_noturno_%"] = (ocup_uf["mat_noturno"] / ocup_uf["vg_noturno"].replace(0, pd.NA) * 100).round(1)
ocup_long = ocup_uf.melt(
    id_vars="NO_UF", value_vars=["taxa_diurno_%", "taxa_noturno_%"],
    var_name="turno", value_name="taxa_ocupacao_%",
)
fig_ocup = px.bar(ocup_long, x="NO_UF", y="taxa_ocupacao_%", color="turno", barmode="group")
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
    ranking, use_container_width=True, on_select="rerun",
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

    st.markdown("**Ocupação de vagas por área de curso**")
    st.caption(
        "% de vagas preenchidas (matrículas ÷ vagas ofertadas) por área geral de "
        "curso (classificação CINE/Unesco do INEP), uma linha por IES — para "
        "comparar em quais áreas cada instituição enche mais ou menos as vagas."
    )
    radar_df = run_query(f"""
        SELECT
            NO_IES,
            NO_CINE_AREA_GERAL,
            SUM(QT_MAT) AS qt_mat,
            SUM(QT_VG_TOTAL) AS qt_vg_total
        FROM {TABLE}
        WHERE {comp_where} AND NO_CINE_AREA_GERAL IS NOT NULL
        GROUP BY NO_IES, NO_CINE_AREA_GERAL
    """)
    if radar_df.empty:
        st.caption("Sem dados de área de curso para essa seleção.")
    else:
        radar_df["taxa_ocupacao_%"] = (
            radar_df["qt_mat"] / radar_df["qt_vg_total"].replace(0, pd.NA) * 100
        ).clip(upper=200).round(1)
        fig_radar = px.line_polar(
            radar_df.dropna(subset=["taxa_ocupacao_%"]),
            r="taxa_ocupacao_%", theta="NO_CINE_AREA_GERAL", color="NO_IES",
            line_close=True, markers=True,
            labels={"taxa_ocupacao_%": "% vagas preenchidas", "NO_CINE_AREA_GERAL": "Área"},
        )
        fig_radar.update_traces(fill="toself", opacity=0.5)
        st.plotly_chart(fig_radar, use_container_width=True)
else:
    st.caption("Selecione uma ou mais instituições acima para comparar.")

st.caption(
    "Dados agregados por curso/IES/ano — o INEP não publica microdados de aluno "
    "individual desde a reformulação do Censo em 2019 (LGPD)."
)
