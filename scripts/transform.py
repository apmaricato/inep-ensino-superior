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
    return df[CURSOS_COLS]


def load_ies(ano: str) -> pd.DataFrame:
    path = find_ies_file(ano)
    if path is None:
        print(f"  [aviso {ano}] arquivo de IES nao encontrado, NO_IES ficara vazio")
        return pd.DataFrame(columns=IES_COLS)
    header = pd.read_csv(path, sep=";", encoding="latin1", nrows=0).columns
    usecols = [c for c in IES_COLS if c in header]
    df = pd.read_csv(path, sep=";", encoding="latin1", usecols=usecols, low_memory=False)
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
    curso. Afeta só NO_CURSO (NO_IES, NO_UF, NO_MUNICIPIO, NO_CINE_AREA_*
    já vêm consistentes em todos os anos -- verificado antes de escrever
    isto). Usa a grafia do ano mais recente disponível para cada curso
    como canônica e reescreve os anos mais antigos para bater com ela --
    não inventa uma regra de capitalização própria (erraria acentuação/
    preposições como "de"/"da"), só reaproveita a decisão editorial mais
    recente do próprio INEP."""
    chave = df["NO_CURSO"].str.upper()
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

    n_antes = combined["NO_CURSO"].nunique()
    combined = normalize_curso_names(combined)
    n_depois = combined["NO_CURSO"].nunique()
    print(f"Uniformizada grafia de NO_CURSO: {n_antes:,} -> {n_depois:,} nomes distintos")

    combined_path = PARQUET_DIR / f"cursos_{anos[0]}_{anos[-1]}.parquet"
    combined.to_parquet(combined_path, index=False)
    print(f"Consolidado gravado em {combined_path} ({len(combined):,} linhas, {len(anos)} anos)")


if __name__ == "__main__":
    main()
