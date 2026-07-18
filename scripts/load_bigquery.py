"""
Carrega o Parquet consolidado (gerado por transform.py) na tabela do BigQuery
que alimenta o painel Streamlit (apmaricato2.inep_ensino_superior.cursos).

Substitui a tabela inteira a cada execucao (WRITE_TRUNCATE) - o Parquet
consolidado ja contem todos os anos, entao isso mantem BigQuery e Parquet
sempre em sincronia.

Requer autenticacao previa: `gcloud auth application-default login`
(ou GOOGLE_APPLICATION_CREDENTIALS apontando para uma chave de service account
com permissao de bigquery.dataEditor no projeto).

Uso:
    py scripts/load_bigquery.py
    py scripts/load_bigquery.py --parquet data/parquet/cursos_2020_2024.parquet
"""

import argparse
import glob
from pathlib import Path

from google.cloud import bigquery

PROJECT_ID = "apmaricato2"
DATASET = "inep_ensino_superior"
TABLE = "cursos"

ROOT = Path(__file__).resolve().parent.parent
PARQUET_DIR = ROOT / "data" / "parquet"


def find_default_parquet() -> Path:
    candidates = sorted(PARQUET_DIR.glob("cursos_*_*.parquet"))
    if not candidates:
        raise FileNotFoundError(
            f"Nenhum parquet consolidado encontrado em {PARQUET_DIR}. "
            "Rode scripts/transform.py primeiro."
        )
    return candidates[-1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", help="Caminho do parquet consolidado a carregar")
    args = parser.parse_args()

    parquet_path = Path(args.parquet) if args.parquet else find_default_parquet()
    print(f"Carregando {parquet_path} em {PROJECT_ID}.{DATASET}.{TABLE} ...")

    client = bigquery.Client(project=PROJECT_ID)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    with open(parquet_path, "rb") as f:
        job = client.load_table_from_file(
            f, f"{PROJECT_ID}.{DATASET}.{TABLE}", job_config=job_config
        )
    job.result()

    table = client.get_table(f"{PROJECT_ID}.{DATASET}.{TABLE}")
    print(f"OK: {table.num_rows:,} linhas carregadas em {table.full_table_id}")


if __name__ == "__main__":
    main()
