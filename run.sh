#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

docker compose --project-directory .. -f ../docker-compose.yml up -d postgres
for _ in $(seq 1 30); do
  if docker exec posdb-postgres pg_isready -U postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
python -m ipykernel install --user --name projeto-integrador >/dev/null

python - <<'PY'
from pathlib import Path
import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

fonte = Path("notebooks/pipeline_fonte.py").read_text(encoding="utf-8").splitlines()
celulas = []
tipo = None
buffer = []

def flush():
    if tipo is None:
        return
    texto = "\n".join(buffer).strip("\n")
    if not texto.strip():
        return
    if tipo == "markdown":
        linhas = []
        for linha in texto.splitlines():
            if linha.startswith("# "):
                linhas.append(linha[2:])
            elif linha == "#":
                linhas.append("")
            else:
                linhas.append(linha)
        celulas.append(new_markdown_cell("\n".join(linhas)))
    else:
        celulas.append(new_code_cell(texto))

for linha in fonte:
    if linha.startswith("# %%"):
        flush()
        buffer = []
        tipo = "markdown" if "markdown" in linha else "code"
        continue
    buffer.append(linha)
flush()
nb = new_notebook(cells=celulas, metadata={"kernelspec": {
    "display_name": "projeto-integrador",
    "language": "python",
    "name": "projeto-integrador",
}})
Path("notebooks/pipeline.ipynb").write_text(nbformat.writes(nb), encoding="utf-8")
PY

jupyter nbconvert --to notebook --execute --inplace notebooks/pipeline.ipynb \
  --ExecutePreprocessor.kernel_name=projeto-integrador \
  --ExecutePreprocessor.timeout=300

python - <<'PY'
from pathlib import Path
from sqlalchemy import create_engine, text
engine = create_engine("postgresql+psycopg2://postgres:postgres@127.0.0.1:5434/varejo_amazonia")
script = Path("sql/consultas.sql").read_text(encoding="utf-8")
partes = []
with engine.connect() as conn:
    for comando in script.split(";"):
        if not comando.strip():
            continue
        frame = conn.execute(text(comando)).mappings().all()
        partes.append(comando.strip())
        partes.extend(str(dict(linha)) for linha in frame)
        partes.append("")
Path("saidas/consultas.txt").write_text("\n".join(partes), encoding="utf-8")
print("consultas gravadas")
PY
