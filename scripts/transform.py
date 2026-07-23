"""
Le os CSVs brutos do INEP (MICRODADOS_CADASTRO_CURSOS_{ano}.CSV +
MICRODADOS_*_IES_{ano}.CSV) em Dados/, decodifica colunas de codigo,
calcula taxas de ocupacao de vagas e grava Parquet consolidado em
data/parquet/.

Uso:
    py scripts/transform.py                  # processa todos os anos encontrados
    py scripts/transform.py --anos 2022 2023  # so anos especificos
"""

import argparse
import re
from pathlib import Path

import pandas as pd

import dicionario_mapping as dic

ROOT = Path(__file__).resolve().parent.parent
DADOS_DIR = ROOT / "Dados"
PARQUET_DIR = ROOT / "data" / "parquet"

CURSOS_COLS = [
    "NU_ANO_CENSO",
    "NO_REGIAO",
    "SG_UF",
    "NO_UF",
    "NO_MUNICIPIO",
    "CO_MUNICIPIO",
    "IN_CAPITAL",
    "CO_IES",
    "TP_ORGANIZACAO_ACADEMICA",
    "TP_REDE",
    "TP_CATEGORIA_ADMINISTRATIVA",
    "CO_CURSO",
    "NO_CURSO",
    "NO_CINE_AREA_GERAL",
    "NO_CINE_AREA_ESPECIFICA",
    "TP_GRAU_ACADEMICO",
    "IN_GRATUITO",
    "TP_MODALIDADE_ENSINO",
    "TP_NIVEL_ACADEMICO",
    "QT_VG_TOTAL",
    "QT_VG_TOTAL_DIURNO",
    "QT_VG_TOTAL_NOTURNO",
    "QT_VG_TOTAL_EAD",
    "QT_ING",
    "QT_ING_DIURNO",
    "QT_ING_NOTURNO",
    "QT_MAT",
    "QT_MAT_DIURNO",
    "QT_MAT_NOTURNO",
    "QT_CONC",
    "QT_CONC_DIURNO",
    "QT_CONC_NOTURNO",
]

IES_COLS = ["CO_IES", "NO_IES", "SG_IES"]

CODE_MAPS = {
    "TP_REDE": dic.TP_REDE,
    "TP_CATEGORIA_ADMINISTRATIVA": dic.TP_CATEGORIA_ADMINISTRATIVA,
    "TP_ORGANIZACAO_ACADEMICA": dic.TP_ORGANIZACAO_ACADEMICA,
    "TP_MODALIDADE_ENSINO": dic.TP_MODALIDADE_ENSINO,
    "TP_GRAU_ACADEMICO": dic.TP_GRAU_ACADEMICO,
    "TP_NIVEL_ACADEMICO": dic.TP_NIVEL_ACADEMICO,
    "IN_CAPITAL": dic.IN_CAPITAL,
    "IN_GRATUITO": dic.IN_GRATUITO,
}


def _clean_text(s: pd.Series) -> pd.Series:
    """Remove espaco na ponta e colapsa espaco duplo interno (sujeira de
    digitacao do proprio INEP, encontrada em milhares de linhas de NO_IES e
    NO_CURSO) -- roda antes de qualquer normalizacao de caixa/acento pra nao
    ser tratada como diferenca substantiva mais adiante."""
    return s.str.strip().str.replace(r"\s{2,}", " ", regex=True)


def _dedup_key(s: pd.Series) -> pd.Series:
    """Chave de agrupamento tolerante a caixa e acentuacao (MAIUSCULO + NFKD
    sem diacriticos). O INEP alterna grafia acentuada/sem acento do mesmo nome
    entre anos (ex.: "ADMINISTRACAO" vs "ADMINISTRAÇÃO"), o que fragmentaria a
    mesma entidade em duas linhas de GROUP BY se a chave fosse so .str.upper()."""
    return (
        s.str.upper()
        .str.normalize("NFKD")
        .str.encode("ascii", errors="ignore")
        .str.decode("ascii")
    )


def canonicalize_by_code(
    df: pd.DataFrame, code_col: str, value_cols: list[str], ano_col: str = "NU_ANO_CENSO"
) -> pd.DataFrame:
    """Uniformiza value_cols (ex.: NO_IES, NO_MUNICIPIO) usando a grafia do ano
    mais recente disponivel para cada codigo estavel (CO_IES, CO_MUNICIPIO).
    Mesma ideia de normalize_curso_names() -- reaproveita a decisao editorial
    mais recente do INEP em vez de inventar uma regra de capitalizacao propria
    -- mas usando o codigo (que ja identifica a entidade de forma inequivoca)
    em vez de uma chave de texto aproximada. Resolve tanto deriva de
    acentuacao entre anos (ex.: CO_IES=2 "UNIVERSIDADE DE BRASILIA" em 2009 vs
    "UNIVERSIDADE DE BRASÍLIA" nos anos seguintes) quanto correcoes pontuais de
    grafia (ex.: CO_MUNICIPIO=5107800 "Santo Antônio de Leverger" vs "...do
    Leverger"), sem risco de colisao entre nomes parecidos de entidades
    diferentes que uma chave de texto teria."""
    valid = df.dropna(subset=[code_col]).sort_values(ano_col)
    for col in value_cols:
        latest = (
            valid.dropna(subset=[col])
            .drop_duplicates(subset=code_col, keep="last")
            .set_index(code_col)[col]
        )
        mapped = df[code_col].map(latest)
        df[col] = mapped.where(mapped.notna(), df[col])
    return df


# O CO_IES do INEP nao e estavel entre 2009-2024: algumas instituicoes foram
# recadastradas com um codigo novo em algum ano, o que fragmenta a mesma IES em
# duas entradas "diferentes" em qualquer filtro/ranking por instituicao (mesmo
# depois de canonicalize_by_code() uniformizar a grafia dentro de cada codigo).
# Nao da pra detectar isso automaticamente sem risco: nome igual + codigo
# diferente tanto pode ser recadastro (mesma IES) quanto duas IES distintas com
# nome parecido/rede de franquia (ex.: "FACULDADE METROPOLITANA" existe em
# Porto Velho/RO E em Lauro de Freitas/BA -- mesclar teria juntado duas escolas
# sem nenhuma relacao). Os 61 casos encontrados foram revisados manualmente em
# 2026-07-20 (nome identico ignorando acento/caixa + cidade primaria + anos de
# atividade) e so os 23 com ALTA confianca -- mesma cidade primaria E intervalos
# de ano sem sobreposicao, i.e. um codigo claramente "assume" onde o outro parou
# -- entram aqui. Os 13 de confianca MEDIA (mesma cidade mas anos sobrepostos) e
# os 25 de confianca BAIXA (cidades diferentes) foram deixados como estao por
# risco de mesclar instituicoes distintas. Cada entrada mapeia o codigo antigo
# para o codigo que continuou em uso no ano mais recente.
CO_IES_MERGES = {
    329: 1221,  # ESCOLA SUPERIOR DE AGRONOMIA DE PARAGUAÇU PAULISTA (Paraguaçu Paulista/SP)
    5375: 12625,  # ESCOLA SUPERIOR DE AVIAÇÃO CIVIL (Campina Grande/PB)
    5031: 11289,  # ESCOLA SUPERIOR NACIONAL DE SEGUROS DE SÃO PAULO (São Paulo/SP)
    24287: 25452,  # FACULDADE BIOPARK (Toledo/PR)
    5101: 11007,  # FACULDADE CENTRO OESTE DO PARANÁ (Laranjeiras do Sul/PR)
    3484: 14236,  # FACULDADE DE CIÊNCIAS GERENCIAIS (Cláudio/MG)
    13498: 28986,  # FACULDADE DE TECNOLOGIA DE BARRETOS (Barretos/SP)
    5536: 12005,  # FACULDADE DE TECNOLOGIA INED - UNIDADE VENDA NOVA (Belo Horizonte/MG)
    1638: 23984,  # FACULDADE DO AMAZONAS (Manaus/AM)
    5180: 11817,  # FACULDADE DO POVO (São Paulo/SP)
    5094: 11841,  # FACULDADE EVOLUÇÃO ALTO OESTE POTIGUAR (Pau dos Ferros/RN)
    5265: 12346,  # FACULDADE METROPOLITANA SÃO CARLOS (Quissamã/RJ)
    5181: 12522,  # FACULDADE MOGIANA DO ESTADO DE SÃO PAULO (Mogi Guaçu/SP)
    4848: 10016,  # FACULDADE OBOÉ - FACO (Fortaleza/CE)
    5360: 12249,  # FACULDADE PADRE ANCHIETA DE VÁRZEA PAULISTA (Várzea Paulista/SP)
    5447: 16881,  # FACULDADE PARA O DESENVOLVIMENTO DO SUDESTE TOCANTINENSE (Dianópolis/TO)
    5033: 12189,  # FACULDADE PRISMA (Montes Claros/MG)
    4667: 16781,  # FACULDADE RIO SONO (Pedro Afonso/TO)
    5112: 10836,  # FACULDADE UNIÃO ARARUAMA DE ENSINO S/S LTDA. (Araruama/RJ)
    3683: 17165,  # FACULDADE UNILAGOS (Mangueirinha/PR)
    5306: 14201,  # INSTITUTO SUPERIOR DE CIÊNCIAS AGRÁRIAS (Pitangui/MG)
    3976: 14005,  # INSTITUTO SUPERIOR DE CIÊNCIAS HUMANAS E SOCIAIS APLICADAS DE ABAETÉ (Abaeté/MG)
    14237: 3483,  # INSTITUTO SUPERIOR DE EDUCAÇÃO DE CLÁUDIO (Cláudio/MG)
}


def merge_recadastered_ies(df: pd.DataFrame) -> pd.DataFrame:
    """Substitui CO_IES pelo codigo canonico para os pares em CO_IES_MERGES,
    unificando linhas da mesma instituicao recadastrada sob um so codigo antes
    de canonicalize_by_code() escolher a grafia do ano mais recente."""
    df["CO_IES"] = df["CO_IES"].replace(CO_IES_MERGES)
    return df


def find_ies_file(ano: str) -> Path | None:
    candidates = [
        DADOS_DIR / f"MICRODADOS_ED_SUP_IES_{ano}.CSV",
        DADOS_DIR / f"MICRODADOS_CADASTRO_IES_{ano}.CSV",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def load_cursos(ano: str) -> pd.DataFrame:
    path = DADOS_DIR / f"MICRODADOS_CADASTRO_CURSOS_{ano}.CSV"
    header = pd.read_csv(path, sep=";", encoding="latin1", nrows=0).columns
    usecols = [c for c in CURSOS_COLS if c in header]
    missing = sorted(set(CURSOS_COLS) - set(usecols))
    if missing:
        print(f"  [aviso {ano}] colunas ausentes em CADASTRO_CURSOS: {missing}")
    df = pd.read_csv(path, sep=";", encoding="latin1", usecols=usecols, low_memory=False)
    for col in set(CURSOS_COLS) - set(df.columns):
        df[col] = pd.NA
    for col in ("NO_MUNICIPIO", "NO_CURSO"):
        if col in df.columns:
            df[col] = _clean_text(df[col])
    return df[CURSOS_COLS]


def load_ies(ano: str) -> pd.DataFrame:
    path = find_ies_file(ano)
    if path is None:
        print(f"  [aviso {ano}] arquivo de IES nao encontrado, NO_IES ficara vazio")
        return pd.DataFrame(columns=IES_COLS)
    header = pd.read_csv(path, sep=";", encoding="latin1", nrows=0).columns
    usecols = [c for c in IES_COLS if c in header]
    df = pd.read_csv(path, sep=";", encoding="latin1", usecols=usecols, low_memory=False)
    # O INEP não uniformiza a caixa dos nomes/siglas de IES entre instituições
    # (ex.: "Universidade Pitágoras Unopar Anhanguera" convive com
    # "UNIVERSIDADE ESTÁCIO DE SÁ" no mesmo ano) -- padroniza em MAIÚSCULO
    # pra não fragmentar a mesma instituição em entradas "diferentes" nos
    # filtros/gráficos. Aplicado aqui pra valer automaticamente em qualquer
    # atualização futura com dados novos do INEP, sem precisar lembrar de
    # rodar uma correção à parte. Isso só resolve divergência DENTRO do mesmo
    # ano -- divergência de acentuação ENTRE anos para a mesma IES (ex.:
    # "UNIVERSIDADE DE BRASILIA" em 2009 vs "UNIVERSIDADE DE BRASÍLIA" depois)
    # é resolvida à parte em canonicalize_by_code(), sobre o dataframe
    # consolidado, já que exige olhar todos os anos ao mesmo tempo.
    df["NO_IES"] = _clean_text(df["NO_IES"]).str.upper()
    df["SG_IES"] = _clean_text(df["SG_IES"]).str.upper()
    return df.drop_duplicates(subset="CO_IES")


def apply_labels(df: pd.DataFrame) -> pd.DataFrame:
    for col, mapping in CODE_MAPS.items():
        df[col + "_DESC"] = df[col].map(mapping)
    return df


def add_derived_metrics(df: pd.DataFrame) -> pd.DataFrame:
    def rate(num, den):
        numerator = df[num].astype("float64")
        denominator = df[den].astype("float64").replace(0, pd.NA)
        return numerator / denominator

    # Taxa de ocupação = ingressantes daquele ano / vagas oferecidas naquele
    # ano (QT_ING, não QT_MAT). QT_MAT soma todos os alunos ativos no curso
    # (todas as turmas, "Cursando"/"Formado"), enquanto QT_VG_TOTAL é só a
    # vaga de calouro daquele ciclo -- comparar QT_MAT com QT_VG_TOTAL dá
    # >100% em qualquer curso plurianual com matrícula estável, mesmo sem
    # nenhuma vaga sobrando. Ver dicionário de dados do INEP (campo
    # "Categoria" de QT_ING e QT_MAT).
    df["TAXA_OCUPACAO_DIURNO"] = rate("QT_ING_DIURNO", "QT_VG_TOTAL_DIURNO")
    df["TAXA_OCUPACAO_NOTURNO"] = rate("QT_ING_NOTURNO", "QT_VG_TOTAL_NOTURNO")
    df["TAXA_OCUPACAO_TOTAL"] = rate("QT_ING", "QT_VG_TOTAL")
    return df


def normalize_curso_names(df: pd.DataFrame) -> pd.DataFrame:
    """O INEP mudou a convenção de maiúsculas de NO_CURSO em 2021 (de TUDO
    MAIÚSCULO para Title Case), fragmentando o mesmo curso real em duas
    grafias diferentes ao longo da série histórica -- ex.: "CIÊNCIA DA
    COMPUTAÇÃO" (2010-2020) vs "Ciência Da Computação" (2021-2024) viram
    duas entidades diferentes em qualquer GROUP BY/filtro por nome de
    curso. O INEP também alterna grafia acentuada/sem acento entre anos
    ("ADMINISTRACAO" vs "ADMINISTRAÇÃO"), então a chave usada pra agrupar
    (_dedup_key) ignora
    caixa E acentuação -- só a chave, não o valor final. Afeta só NO_CURSO
    (NO_UF, NO_CINE_AREA_* já vêm consistentes em todos os anos; NO_IES e
    NO_MUNICIPIO são tratados à parte em canonicalize_by_code(), que usa o
    código estável em vez de uma chave de texto). Usa a grafia do ano mais
    recente disponível para cada curso como canônica e reescreve os anos
    mais antigos para bater com ela -- não inventa uma regra de
    capitalização própria (erraria acentuação/preposições como "de"/"da"),
    só reaproveita a decisão editorial mais recente do próprio INEP."""
    chave = _dedup_key(df["NO_CURSO"])
    grafia_mais_recente = (
        df.assign(_chave=chave)
        .sort_values("NU_ANO_CENSO")
        .drop_duplicates(subset="_chave", keep="last")
        .set_index("_chave")["NO_CURSO"]
    )
    df["NO_CURSO"] = chave.map(grafia_mais_recente)
    return df


def process_year(ano: str) -> pd.DataFrame:
    print(f"Processando {ano}...")
    cursos = load_cursos(ano)
    ies = load_ies(ano)
    df = cursos.merge(ies, on="CO_IES", how="left")
    df = apply_labels(df)
    df = add_derived_metrics(df)

    out_path = PARQUET_DIR / f"cursos_{ano}.parquet"
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"  gravado {out_path} ({len(df):,} linhas)")
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--anos", nargs="*", help="Anos especificos a processar")
    args = parser.parse_args()

    if args.anos:
        anos = args.anos
    else:
        anos = sorted(
            m.group(1)
            for f in DADOS_DIR.glob("MICRODADOS_CADASTRO_CURSOS_*.CSV")
            if (m := re.search(r"(\d{4})", f.name))
        )

    if not anos:
        print("Nenhum CSV de cursos encontrado em Dados/.")
        return

    frames = [process_year(ano) for ano in anos]
    combined = pd.concat(frames, ignore_index=True)

    n_ies_antes = combined["CO_IES"].nunique()
    combined = merge_recadastered_ies(combined)
    n_ies_depois = combined["CO_IES"].nunique()
    print(f"Mesclados codigos de IES recadastradas: {n_ies_antes:,} -> {n_ies_depois:,} CO_IES distintos ({len(CO_IES_MERGES)} pares)")

    for label, code_col, value_cols in (
        ("NO_IES/SG_IES", "CO_IES", ["NO_IES", "SG_IES"]),
        ("NO_MUNICIPIO", "CO_MUNICIPIO", ["NO_MUNICIPIO"]),
    ):
        n_antes_cod = sum(combined[c].nunique() for c in value_cols)
        combined = canonicalize_by_code(combined, code_col, value_cols)
        n_depois_cod = sum(combined[c].nunique() for c in value_cols)
        print(f"Uniformizada grafia de {label} por {code_col}: {n_antes_cod:,} -> {n_depois_cod:,} nomes distintos")

    n_antes = combined["NO_CURSO"].nunique()
    combined = normalize_curso_names(combined)
    n_depois = combined["NO_CURSO"].nunique()
    print(f"Uniformizada grafia de NO_CURSO: {n_antes:,} -> {n_depois:,} nomes distintos")

    combined_path = PARQUET_DIR / f"cursos_{anos[0]}_{anos[-1]}.parquet"
    combined.to_parquet(combined_path, index=False)
    print(f"Consolidado gravado em {combined_path} ({len(combined):,} linhas, {len(anos)} anos)")


if __name__ == "__main__":
    main()
