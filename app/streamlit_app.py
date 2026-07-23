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
    de distinguir quando várias IES se sobrepõem). Sem linha conectando os
    vértices — só marcadores e a área preenchida; a cor já basta pra
    diferenciar as séries."""
    for trace, color in zip(fig.data, RADAR_COLORS):
        trace.line.color = color
        trace.line.width = 0
        trace.marker.color = color
        trace.fill = "toself"
        trace.fillcolor = _hex_to_rgba(color, 0.18)
        trace.opacity = 1
    style_chart(fig)
    fig.update_layout(legend=dict(font=dict(size=13)))
    return fig


def style_chart(fig):
    """Aplica o fundo/cor de texto do modo atual (claro ou escuro) ao
    gráfico Plotly — sem isso, o gráfico ficaria com o fundo branco padrão
    do Plotly mesmo com o resto da página no modo escuro, ou vice-versa."""
    fig.update_layout(
        paper_bgcolor=TOKENS["surface"],
        plot_bgcolor=TOKENS["surface"],
        font_color=TOKENS["ink"],
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


st.set_page_config(
    page_title="Censo da Educação Superior (INEP)",
    page_icon="🎓",
    layout="wide",
)

# --- Tema (modo claro fixo) --------------------------------------------
# O painel usa só modo claro, com um plano de fundo levemente acinzentado
# (#f9f9f7) em vez de branco puro -- reduz o brilho/cansaço visual sem
# comprometer o contraste do texto. Paleta categórica validada com
# scripts/validate_palette.js da skill dataviz para a superfície clara
# (banda de luminosidade, piso de croma e separação CVD todos PASS — ver
# commit "Padroniza cores dos gráficos e filtros").
TOKENS = {
    "surface": "#fcfcfb", "page": "#f9f9f7", "ink": "#0b0b0b",
    "ink2": "#52514e", "muted": "#898781",
    "border": "rgba(11, 11, 11, 0.10)", "accent": "#2a78d6",
    "shadow": "rgba(0, 0, 0, 0.08)",
}
CATEGORICAL_PALETTE = [
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
]
RADAR_COLORS = CATEGORICAL_PALETTE[:5]

# --- CSS: tokens de design + componentes (cards, tipografia, tabelas) -----
# Sobrepõe inclusive o fundo/sidebar/chips nativos do Streamlit com os
# tokens do modo claro acima. Fonte fica no system sans (sem carregar fonte
# externa) por performance e para não depender de rede — recomendação da
# skill dataviz.
st.markdown(
    f"""
    <style>
    :root {{
        --surface-1: {TOKENS["surface"]};
        --page-plane: {TOKENS["page"]};
        --ink-primary: {TOKENS["ink"]};
        --ink-secondary: {TOKENS["ink2"]};
        --ink-muted: {TOKENS["muted"]};
        --border-hairline: {TOKENS["border"]};
        --radius-md: 0.5rem;
        --radius-lg: 0.9rem;
        --space-2: 0.5rem;
        --space-3: 0.75rem;
        --space-4: 1rem;
        --space-6: 2rem;
        --shadow-card: 0 1px 3px {TOKENS["shadow"]};
        --accent: {TOKENS["accent"]};
    }}

    html, body, [class*="css"] {{
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    }}

    /* Sobrepõe o fundo nativo do Streamlit com o plano de fundo levemente
       acinzentado do tema (não branco puro). */
    [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main {{
        background: var(--page-plane) !important;
    }}
    section[data-testid="stSidebar"] {{
        background: var(--surface-1) !important;
    }}
    body, p, span, label, [data-testid="stMarkdownContainer"] {{
        color: var(--ink-primary);
    }}
    [data-baseweb="tag"] {{
        background-color: var(--accent) !important;
    }}
    [data-baseweb="select"] {{
        background: var(--surface-1) !important;
    }}

    /* Hierarquia tipográfica: título fluido, subtítulos com respiro e trilho
       de cor de acento à esquerda para escanear o painel mais rápido. */
    h1 {{
        font-size: clamp(1.6rem, 1.1rem + 1.6vw, 2.4rem) !important;
        letter-spacing: -0.01em;
    }}
    h2, h3 {{
        letter-spacing: -0.01em;
        margin-top: var(--space-6) !important;
    }}
    h3 {{
        border-left: 3px solid var(--accent);
        padding-left: var(--space-3);
    }}

    /* Legendas (st.caption) em tom secundário, um pouco maiores que o
       padrão minúsculo do Streamlit — melhora legibilidade das explicações
       metodológicas espalhadas pelo painel. */
    [data-testid="stCaptionContainer"] {{
        color: var(--ink-secondary) !important;
        font-size: 0.92rem !important;
        line-height: 1.5;
    }}

    /* KPIs como cartões: separa visualmente os 5 números do topo do resto
       do painel, com contorno sutil em vez de fundo chapado (recessive,
       não compete com as cores das séries dos gráficos). */
    [data-testid="stMetric"] {{
        background: var(--surface-1);
        border: 1px solid var(--border-hairline);
        border-radius: var(--radius-lg);
        padding: var(--space-4);
        box-shadow: var(--shadow-card);
    }}
    [data-testid="stMetricLabel"] {{
        color: var(--ink-muted) !important;
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }}
    [data-testid="stMetricValue"] {{
        color: var(--ink-primary) !important;
        font-variant-numeric: tabular-nums;
    }}

    /* Gráficos Plotly como cartões — mesma lógica visual dos KPIs, pra dar
       sensação de "sistema" único em vez de elementos soltos na página. */
    [data-testid="stPlotlyChart"] {{
        background: var(--surface-1);
        border: 1px solid var(--border-hairline);
        border-radius: var(--radius-lg);
        padding: var(--space-3);
    }}

    /* Tabelas com cantos arredondados e contorno hairline, consistente com
       cards e gráficos. */
    [data-testid="stDataFrame"] {{
        border: 1px solid var(--border-hairline);
        border-radius: var(--radius-md);
        overflow: hidden;
    }}

    /* Chips do multiselect (filtros): cantos mais arredondados, tipografia
       menor e mais compacta — Streamlit por padrão deixa retangular. */
    [data-baseweb="tag"] {{
        border-radius: var(--radius-md) !important;
    }}

    /* Divisores (st.divider) discretos em vez da linha branca padrão. */
    hr {{
        border-color: var(--border-hairline) !important;
    }}

    /* Sidebar com leve respiro extra nas seções (st.subheader dentro dela). */
    section[data-testid="stSidebar"] h3 {{
        margin-top: var(--space-4) !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

PROJECT_ID = "apmaricato2"
TABLE = f"`{PROJECT_ID}.inep_ensino_superior.cursos`"

# CATEGORICAL_PALETTE e RADAR_COLORS já foram definidos acima. Ordem fixa:
# azul, água, amarelo, verde, violeta, vermelho, magenta, laranja — pior
# par adjacente (verde/amarelo) fica na
# faixa "floor" (ΔE ~10-12), por isso os gráficos que os usam sempre têm
# legenda/rótulo visível (nunca só a cor identifica a série).

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

    resumo_filtros_placeholder = st.empty()
    st.divider()

    filtro_specs: list[dict] = []

    def ms(label, options, default, key, **kwargs):
        """st.multiselect com key fixa (pra poder resetar via botão) que
        também registra (rótulo, chave, valor-padrão) em filtro_specs, usado
        depois pra montar o resumo "filtros ativos" no topo da sidebar.
        Inicializa o session_state manualmente em vez de passar default= pro
        widget junto com key= -- Streamlit avisa (warning visível na tela)
        quando os dois são passados ao mesmo tempo."""
        if key not in st.session_state:
            st.session_state[key] = list(default)
        valor = st.multiselect(label, options, key=key, **kwargs)
        filtro_specs.append({"label": label, "key": key, "default": list(default)})
        return valor

    st.subheader("📍 Localização")
    anos = sorted(opts["NU_ANO_CENSO"].unique())
    ano_sel = ms("Ano", anos, anos, "f_ano", placeholder="Selecione um ou mais anos")

    regioes = cascade_options(opts, "NO_REGIAO", NU_ANO_CENSO=ano_sel)
    regiao_sel = ms("Região", regioes, regioes, "f_regiao", placeholder="Selecione uma ou mais regiões")

    ufs_disponiveis = cascade_options(
        opts, "NO_UF", NU_ANO_CENSO=ano_sel, NO_REGIAO=regiao_sel,
    )
    uf_sel = ms("UF", ufs_disponiveis, [], "f_uf", placeholder="Todas as UFs (opcional)")

    municipios_filtrados = municipios[municipios["NO_REGIAO"].isin(regiao_sel)]
    if uf_sel:
        municipios_filtrados = municipios_filtrados[municipios_filtrados["NO_UF"].isin(uf_sel)]
    municipios_disponiveis = sorted(municipios_filtrados["NO_MUNICIPIO"].dropna().unique())
    municipio_sel = ms(
        "Município", municipios_disponiveis, [], "f_municipio",
        placeholder="Todos os municípios (opcional)",
        help="Subordinado a Região e UF.",
    )

    st.divider()
    st.subheader("📚 Curso")
    areas_gerais = sorted(cursos_tax["NO_CINE_AREA_GERAL"].dropna().unique())
    area_geral_sel = ms(
        "Área geral do curso", areas_gerais, [], "f_area_geral",
        placeholder="Todas as áreas (opcional)",
    )

    areas_especificas = cascade_options(
        cursos_tax, "NO_CINE_AREA_ESPECIFICA", NO_CINE_AREA_GERAL=area_geral_sel,
    )
    area_especifica_sel = ms(
        "Área específica", areas_especificas, [], "f_area_especifica",
        placeholder="Todas as áreas específicas (opcional)",
        help="Subordinado a Área geral.",
    )

    cursos_disponiveis = cascade_options(
        cursos_tax, "NO_CURSO",
        NO_CINE_AREA_GERAL=area_geral_sel, NO_CINE_AREA_ESPECIFICA=area_especifica_sel,
    )
    curso_sel = ms(
        "Nome do curso", cursos_disponiveis, [], "f_curso",
        placeholder="Todos os cursos (digite para buscar)",
        help="Subordinado a Área geral e Área específica. Digite para buscar entre milhares de cursos.",
    )

    grau_disponiveis = cascade_options(
        opts, "TP_GRAU_ACADEMICO_DESC", NU_ANO_CENSO=ano_sel,
    )
    grau_sel = ms(
        "Grau acadêmico", grau_disponiveis, [], "f_grau",
        placeholder="Todos os graus (opcional)",
        help="Bacharelado, Licenciatura, Tecnológico etc.",
    )
    nivel_disponiveis = cascade_options(
        opts, "TP_NIVEL_ACADEMICO_DESC", NU_ANO_CENSO=ano_sel, TP_GRAU_ACADEMICO_DESC=grau_sel,
    )
    nivel_sel = ms(
        "Nível acadêmico", nivel_disponiveis, [], "f_nivel",
        placeholder="Todos os níveis (opcional)",
        help="Subordinado a Grau acadêmico.",
    )

    st.divider()
    st.subheader("🏫 Instituição")
    ies_filtro_sel = ms(
        "Instituição", todas_ies, [], "f_ies",
        placeholder="Todas as instituições (digite para buscar)",
        help="Filtra todo o painel (KPIs e gráficos) por uma ou mais IES específicas.",
    )

    rede_disponiveis = cascade_options(
        opts, "TP_REDE_DESC", NU_ANO_CENSO=ano_sel, NO_REGIAO=regiao_sel,
    )
    rede_sel = ms(
        "Rede", rede_disponiveis, rede_disponiveis, "f_rede",
        placeholder="Selecione uma ou mais redes",
    )

    categoria_disponiveis = cascade_options(
        opts, "TP_CATEGORIA_ADMINISTRATIVA_DESC", TP_REDE_DESC=rede_sel,
    )
    categoria_sel = ms(
        "Categoria administrativa", categoria_disponiveis, [], "f_categoria",
        placeholder="Todas as categorias (opcional)",
        help="Subordinado a Rede (ex.: dentro de \"Pública\", Federal/Estadual/Municipal).",
    )

    organizacao_disponiveis = cascade_options(
        opts, "TP_ORGANIZACAO_ACADEMICA_DESC",
        TP_REDE_DESC=rede_sel, TP_CATEGORIA_ADMINISTRATIVA_DESC=categoria_sel,
    )
    organizacao_sel = ms(
        "Organização acadêmica", organizacao_disponiveis, [], "f_organizacao",
        placeholder="Todas as organizações (opcional)",
        help="Universidade, Centro Universitário, Faculdade, IF, CEFET.",
    )

    st.divider()
    st.subheader("⚙️ Outros atributos")
    modalidade_disponiveis = cascade_options(
        opts, "TP_MODALIDADE_ENSINO_DESC",
        TP_REDE_DESC=rede_sel, TP_ORGANIZACAO_ACADEMICA_DESC=organizacao_sel,
    )
    modalidade_sel = ms(
        "Modalidade", modalidade_disponiveis, modalidade_disponiveis, "f_modalidade",
        placeholder="Selecione uma ou mais modalidades",
    )
    gratuito_disponiveis = cascade_options(
        opts, "IN_GRATUITO_DESC", TP_MODALIDADE_ENSINO_DESC=modalidade_sel,
    )
    gratuito_sel = ms(
        "Curso gratuito?", gratuito_disponiveis, gratuito_disponiveis, "f_gratuito",
        placeholder="Selecione uma ou mais opções",
    )
    capital_disponiveis = cascade_options(
        opts, "IN_CAPITAL_DESC", IN_GRATUITO_DESC=gratuito_sel,
    )
    capital_sel = ms(
        "Localização em capital?", capital_disponiveis, capital_disponiveis, "f_capital",
        placeholder="Selecione uma ou mais opções",
    )

    # --- Resumo "filtros ativos", preenchido no topo (placeholder acima) --
    # Importante: um widget não pode ter seu session_state alterado depois
    # de já ter sido instanciado NESTE mesmo ciclo de execução (Streamlit
    # levanta StreamlitAPIException), mesmo chamando st.rerun() em seguida.
    # Por isso a limpeza acontece só dentro de on_click (roda ANTES do
    # script recomeçar do zero na próxima execução), nunca direto no corpo
    # do script como "if st.button(...): st.session_state[...] = ...".
    def _limpar_filtro(key, default):
        st.session_state[key] = default

    def _limpar_crossfilter(key):
        st.session_state[key] = None

    def _limpar_todos(specs, cf_keys):
        for spec in specs:
            st.session_state[spec["key"]] = spec["default"]
        for key in cf_keys:
            st.session_state[key] = None

    filtros_ativos = [
        spec for spec in filtro_specs
        if set(st.session_state.get(spec["key"], spec["default"])) != set(spec["default"])
    ]
    # Cliques nos gráficos (crossfilter) entram no mesmo resumo "filtros
    # ativos" que os filtros manuais -- pedido do usuário pra que uma
    # seleção feita clicando num gráfico fique tão visível/removível
    # quanto um filtro escolhido na sidebar, em vez de viver numa seção
    # separada lá embaixo.
    CROSSFILTER_LABELS = {
        "cf_ano": "Ano (clique no gráfico)",
        "cf_uf": "UF (clique no gráfico)",
        "cf_modalidade": "Modalidade (clique no gráfico)",
    }
    crossfilters_ativos = [k for k in CROSSFILTER_LABELS if st.session_state[k]]

    with resumo_filtros_placeholder.container():
        total_ativos = len(filtros_ativos) + len(crossfilters_ativos)
        if total_ativos:
            st.markdown(f"**🔎 {total_ativos} filtro(s) ativo(s)**")
            for spec in filtros_ativos:
                valor_atual = st.session_state.get(spec["key"], spec["default"])
                resumo = ", ".join(str(v) for v in valor_atual[:3])
                if len(valor_atual) > 3:
                    resumo += f" (+{len(valor_atual) - 3})"
                col_label, col_x = st.columns([5, 1])
                col_label.caption(f"**{spec['label']}:** {resumo}")
                col_x.button(
                    "✕", key=f"limpar_{spec['key']}", help=f"Remover filtro {spec['label']}",
                    on_click=_limpar_filtro, args=(spec["key"], spec["default"]),
                )
            for key in crossfilters_ativos:
                col_label, col_x = st.columns([5, 1])
                col_label.caption(f"**{CROSSFILTER_LABELS[key]}:** {st.session_state[key]}")
                col_x.button(
                    "✕", key=f"limpar_{key}", help=f"Remover {CROSSFILTER_LABELS[key]}",
                    on_click=_limpar_crossfilter, args=(key,),
                )
            st.button(
                "🔄 Limpar todos os filtros", use_container_width=True,
                on_click=_limpar_todos, args=(filtros_ativos, crossfilters_ativos),
            )
        else:
            st.caption("Nenhum filtro ativo — mostrando todos os dados disponíveis.")


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


def in_clause_or_all(col, selected, available):
    """Como in_clause(), mas quando a seleção atual cobre todas as opções
    disponíveis (estado padrão "tudo marcado"), vira TRUE em vez de um IN
    explícito. Isso importa porque várias colunas do INEP têm valor nulo
    numa fração das linhas (ex.: IN_CAPITAL não informado para ~57 mil
    linhas de cursos EAD, TP_REDE nulo em quase todo o ano de 2013) — um
    IN (...) sempre exclui NULL em SQL, então mesmo com "tudo selecionado"
    essas linhas sumiam silenciosamente do painel inteiro. Se o usuário
    de fato restringir a seleção (desmarcar alguma opção), o IN explícito
    volta a valer normalmente (excluir nulo é o comportamento esperado
    quando alguém está filtrando de propósito)."""
    if set(selected) >= set(available):
        return "TRUE"
    return in_clause(col, selected)


base_where_parts = [
    in_clause_numeric("NU_ANO_CENSO", ano_sel),
    in_clause_or_all("NO_REGIAO", regiao_sel, regioes),
    in_clause_or_all("TP_REDE_DESC", rede_sel, rede_disponiveis),
    in_clause_or_all("TP_MODALIDADE_ENSINO_DESC", modalidade_sel, modalidade_disponiveis),
    in_clause_or_all("IN_GRATUITO_DESC", gratuito_sel, gratuito_disponiveis),
    in_clause_or_all("IN_CAPITAL_DESC", capital_sel, capital_disponiveis),
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
    ("NO_IES", ies_filtro_sel),
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
style_chart(fig_serie)
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
    style_chart(fig_uf)
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
    style_chart(fig_mod)
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
style_chart(fig_ocup)
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
    "Buscar e selecionar instituições (digite parte do nome, ou clique numa linha do ranking acima) — até 3",
    todas_ies,
    placeholder="Digite o nome de uma instituição",
    max_selections=3,
    key="ies_multiselect",
)

if ies_sel:
    comp_where = build_where() + " AND " + in_clause("NO_IES", ies_sel)

    comp_serie = run_query(f"""
        SELECT NO_IES, NU_ANO_CENSO, SUM(QT_MAT) AS QT_MAT,
            SUM(QT_ING_DIURNO) AS ing_diurno, SUM(QT_VG_TOTAL_DIURNO) AS vg_diurno,
            SUM(QT_ING_NOTURNO) AS ing_noturno, SUM(QT_VG_TOTAL_NOTURNO) AS vg_noturno
        FROM {TABLE}
        WHERE {comp_where}
        GROUP BY NO_IES, NU_ANO_CENSO
        ORDER BY NU_ANO_CENSO
    """)
    # Ano/turno com poucas vagas somadas viram taxa >>100% sem significado real
    # (mesma razao do MIN_VG_CONFIAVEL usado nos radares abaixo) -- em branco
    # em vez de plotado, pra nao distorcer a leitura da linha do tempo.
    comp_serie["Diurno"] = pct(comp_serie["ing_diurno"], comp_serie["vg_diurno"])
    comp_serie["Noturno"] = pct(comp_serie["ing_noturno"], comp_serie["vg_noturno"])
    comp_serie.loc[comp_serie["vg_diurno"] < MIN_VG_CONFIAVEL, "Diurno"] = np.nan
    comp_serie.loc[comp_serie["vg_noturno"] < MIN_VG_CONFIAVEL, "Noturno"] = np.nan
    # Combinado NAO e a media simples de Diurno/Noturno -- isso pesaria os dois
    # turnos igual mesmo quando um tem muito mais vagas que o outro. E a soma de
    # ingressantes (diurno+noturno) sobre a soma de vagas (diurno+noturno),
    # ponderando pelo tamanho real de cada turno -- mesma logica do KPI
    # "% vagas preenchidas por ingressantes" no topo do painel.
    vg_combinado = comp_serie["vg_diurno"].fillna(0) + comp_serie["vg_noturno"].fillna(0)
    ing_combinado = comp_serie["ing_diurno"].fillna(0) + comp_serie["ing_noturno"].fillna(0)
    comp_serie["Combinado"] = pct(ing_combinado, vg_combinado)
    comp_serie.loc[vg_combinado < MIN_VG_CONFIAVEL, "Combinado"] = np.nan

    fig_comp_mat = px.line(
        comp_serie, x="NU_ANO_CENSO", y="QT_MAT", color="NO_IES", markers=True,
        color_discrete_sequence=CATEGORICAL_PALETTE,
        labels={"QT_MAT": "Matrículas", "NU_ANO_CENSO": "Ano", "NO_IES": "Instituição"},
    )
    style_chart(fig_comp_mat)
    st.caption(
        "Matrículas (QT_MAT): total de alunos ativos na instituição naquele "
        "ano, somando todas as turmas em curso — mede o tamanho e a tendência "
        "de crescimento ou contração de cada instituição."
    )
    st.plotly_chart(fig_comp_mat, use_container_width=True, key="chart_comp_serie_mat")

    turno_view = st.radio(
        "Turno exibido no gráfico de % de vagas preenchidas",
        ["Diurno e noturno", "Só diurno", "Só noturno", "Combinado (uma linha por IES)"],
        horizontal=True,
        key="turno_view_comp",
    )
    if turno_view == "Combinado (uma linha por IES)":
        fig_comp = px.line(
            comp_serie, x="NU_ANO_CENSO", y="Combinado", color="NO_IES", markers=True,
            color_discrete_sequence=CATEGORICAL_PALETTE,
            labels={"Combinado": "% de vagas preenchidas", "NU_ANO_CENSO": "Ano", "NO_IES": "Instituição"},
        )
        legenda_turno = (
            "Combinado: soma de ingressantes (diurno + noturno) ÷ soma de vagas "
            "(diurno + noturno) — não é a média simples das duas taxas, que "
            "daria peso igual a turnos com quantidade de vagas muito diferente; "
            "esta conta pondera pelo tamanho real de cada turno."
        )
    else:
        turnos_incluidos = {
            "Diurno e noturno": ["Diurno", "Noturno"],
            "Só diurno": ["Diurno"],
            "Só noturno": ["Noturno"],
        }[turno_view]
        comp_long = comp_serie.melt(
            id_vars=["NO_IES", "NU_ANO_CENSO"],
            value_vars=turnos_incluidos,
            var_name="Turno", value_name="taxa_ocupacao_%",
        )
        fig_comp = px.line(
            comp_long, x="NU_ANO_CENSO", y="taxa_ocupacao_%", color="NO_IES",
            line_dash="Turno" if len(turnos_incluidos) > 1 else None,
            markers=True, color_discrete_sequence=CATEGORICAL_PALETTE,
            labels={
                "taxa_ocupacao_%": "% de vagas preenchidas", "NU_ANO_CENSO": "Ano",
                "NO_IES": "Instituição", "Turno": "Turno",
            },
        )
        legenda_turno = "Diurno e noturno mostrados separadamente (uma linha para cada)."
    style_chart(fig_comp)
    st.caption(
        "% de vagas preenchidas (ingressantes daquele ano ÷ vagas ofertadas "
        f"naquele ano). {legenda_turno} Anos com menos de {MIN_VG_CONFIAVEL} "
        "vagas somadas no turno (ou combinado) ficam em branco (amostra "
        "pequena demais para ser confiável)."
    )
    st.plotly_chart(fig_comp, use_container_width=True, key="chart_comp_serie")

    st.caption(
        "De forma bem geral: o gráfico de matrículas mostra o tamanho absoluto "
        "e sua tendência; o de % de vagas preenchidas mostra se a instituição "
        "consegue atrair alunos para as vagas que oferece (pressão de "
        "demanda). Uma instituição pode encolher em matrículas e ainda manter "
        "alta ocupação, se também reduziu vagas na mesma proporção — os dois "
        "juntos evitam confundir 'ficou menor' com 'ficou menos procurada'. "
        "Não permitem, por si só, concluir causa (ex.: qualidade, preço, "
        "concorrência) — só descrevem o padrão."
    )

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
