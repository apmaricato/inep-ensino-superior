"""
Extrai os CSVs de MICRODADOS_CADASTRO_CURSOS e MICRODADOS_*_IES de dentro
dos zips oficiais do Censo da Educação Superior (INEP) para a pasta Dados/.

O nome do arquivo de IES e o nome da pasta raiz dentro do zip mudam de ano
para ano, então localizamos os arquivos por padrão (regex) em vez de path fixo.

Uso:
    py scripts/extract_inep.py               # extrai de todos os zips *.zip na raiz do projeto
    py scripts/extract_inep.py --anos 2024    # só um ano específico
"""

import argparse
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DADOS_DIR = ROOT / "Dados"

CURSOS_RE = re.compile(r"MICRODADOS_CADASTRO_CURSOS_(\d{4})\.CSV$", re.IGNORECASE)
IES_RE = re.compile(r"MICRODADOS_(?:CADASTRO_IES|ED_SUP_IES)_(\d{4})\.CSV$", re.IGNORECASE)


def extract_from_zip(zip_path: Path, anos_filtro=None) -> list[str]:
    extraidos = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            base = name.split("/")[-1]
            m = CURSOS_RE.search(base) or IES_RE.search(base)
            if not m:
                continue
            ano = m.group(1)
            if anos_filtro and ano not in anos_filtro:
                continue
            dest = DADOS_DIR / base
            if dest.exists():
                continue
            DADOS_DIR.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as out:
                out.write(src.read())
            extraidos.append(base)
    return extraidos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--anos", nargs="*", help="Anos específicos a extrair (ex: 2024)")
    args = parser.parse_args()

    zips = sorted(ROOT.glob("microdados_censo_da_educacao_superior_*.zip"))
    if not zips:
        print("Nenhum zip encontrado na raiz do projeto.")
        return

    for zip_path in zips:
        print(f"Lendo {zip_path.name}...")
        extraidos = extract_from_zip(zip_path, set(args.anos) if args.anos else None)
        if extraidos:
            for f in extraidos:
                print(f"  extraído: {f}")
        else:
            print("  (nada novo a extrair, já presente em Dados/)")


if __name__ == "__main__":
    main()
