"""ETL: CSV de vendas, JSON de clientes e API do IBGE -> PostgreSQL."""
from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SQL = ROOT / "sql" / "schema.sql"
SAIDAS = ROOT / "saidas"
URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5434/varejo_amazonia"
ADMIN = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5434/postgres"
IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/AP/municipios"


def _norm(valor) -> str:
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return " ".join(texto.strip().lower().split())


def _engine_admin():
    return create_engine(ADMIN, isolation_level="AUTOCOMMIT")


def preparar_banco() -> None:
    admin = _engine_admin()
    with admin.connect() as conn:
        existe = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'varejo_amazonia'")).scalar()
        if not existe:
            conn.execute(text("CREATE DATABASE varejo_amazonia"))
    engine = create_engine(URL)
    script = SQL.read_text(encoding="utf-8")
    bruto = engine.raw_connection()
    try:
        cursor = bruto.cursor()
        cursor.execute(script)
        bruto.commit()
        cursor.close()
    finally:
        bruto.close()


def _log(conn, etapa, extraidos, transformados, carregados, detalhe):
    conn.execute(text("""
        INSERT INTO ops.etl_log (etapa, extraidos, transformados, carregados, detalhe)
        VALUES (:etapa, :extraidos, :transformados, :carregados, :detalhe)
    """), {
        "etapa": etapa,
        "extraidos": int(extraidos),
        "transformados": int(transformados),
        "carregados": int(carregados),
        "detalhe": detalhe,
    })


def extrair() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    vendas = pd.read_csv(DATA / "vendas.csv")
    clientes = pd.read_json(DATA / "clientes.json")
    try:
        resposta = requests.get(IBGE, timeout=30)
        resposta.raise_for_status()
        payload = resposta.json()
        origem = "api_ibge"
    except requests.RequestException:
        cache = DATA / "ibge_municipios_ap.json"
        if not cache.exists():
            raise
        payload = json.loads(cache.read_text(encoding="utf-8"))
        origem = "cache_local"
    else:
        (DATA / "ibge_municipios_ap.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    municipios = pd.DataFrame([
        {
            "codigo_ibge": item["id"],
            "nome": item["nome"],
            "uf": item["microrregiao"]["mesorregiao"]["UF"]["sigla"],
        }
        for item in payload
    ])
    return vendas, clientes, municipios, origem


def transformar(vendas, clientes, municipios) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    metricas = {"vendas_extraidas": int(len(vendas)), "clientes_extraidos": int(len(clientes))}
    vendas = vendas.copy()
    vendas["data"] = pd.to_datetime(vendas["data"], errors="coerce")
    vendas["valor"] = pd.to_numeric(vendas["valor"], errors="coerce")
    vendas["quantidade"] = pd.to_numeric(vendas["quantidade"], errors="coerce")
    antes = len(vendas)
    vendas = vendas.drop_duplicates()
    metricas["duplicatas_removidas"] = int(antes - len(vendas))
    vendas = vendas.dropna(subset=["data", "valor", "cliente_id", "produto"])
    vendas = vendas.loc[(vendas["valor"] > 0) & (vendas["quantidade"] > 0)].copy()
    vendas["quantidade"] = vendas["quantidade"].astype(int)
    vendas["data"] = vendas["data"].dt.date
    metricas["vendas_validas"] = int(len(vendas))

    clientes = clientes.copy()
    clientes["idade"] = pd.to_numeric(clientes["idade"], errors="coerce")
    clientes["idade"] = clientes["idade"].fillna(clientes["idade"].median()).astype(int)
    clientes["data_cadastro"] = pd.to_datetime(clientes["data_cadastro"], errors="coerce").dt.date
    clientes["email"] = clientes["email"].fillna("").map(lambda v: str(v).strip().lower())
    clientes["cidade_norm"] = clientes["cidade"].map(_norm)
    municipios = municipios.copy()
    municipios["cidade_norm"] = municipios["nome"].map(_norm)
    clientes = clientes.merge(
        municipios[["cidade_norm", "codigo_ibge", "nome"]],
        on="cidade_norm",
        how="left",
    )
    clientes = clientes.rename(columns={"nome_x": "nome", "nome_y": "municipio_ibge"})
    clientes["cidade"] = clientes["cidade"].map(lambda v: " ".join(str(v).split()).title() if pd.notna(v) else "Desconhecida")
    clientes = clientes.dropna(subset=["data_cadastro"])
    clientes["codigo_ibge"] = clientes["codigo_ibge"].map(lambda v: None if pd.isna(v) else int(v))
    clientes["municipio_ibge"] = clientes["municipio_ibge"].where(clientes["municipio_ibge"].notna(), None)
    metricas["clientes_validos"] = int(len(clientes))
    metricas["clientes_sem_ibge"] = int(clientes["codigo_ibge"].isna().sum())
    return vendas, clientes, metricas


def carregar(vendas_raw, clientes_raw, municipios, vendas, clientes, origem, metricas) -> dict:
    engine = create_engine(URL)
    vendas_raw.astype(object).where(vendas_raw.notna(), None).to_sql(
        "vendas", engine, schema="bronze", if_exists="append", index=False
    )
    clientes_raw.astype(object).where(clientes_raw.notna(), None).to_sql(
        "clientes", engine, schema="bronze", if_exists="append", index=False
    )
    municipios_sql = municipios[["codigo_ibge", "nome", "uf"]]
    municipios_sql.to_sql("municipios", engine, schema="bronze", if_exists="append", index=False)
    municipios_sql.to_sql("municipios", engine, schema="silver", if_exists="append", index=False)

    vendas_sql = vendas[["venda_id", "cliente_id", "data", "produto", "quantidade", "valor"]]
    vendas_sql.to_sql("vendas", engine, schema="silver", if_exists="append", index=False)

    clientes_sql = clientes[["cliente_id", "nome", "email", "cidade", "segmento", "data_cadastro", "idade", "codigo_ibge", "municipio_ibge"]]
    clientes_sql.to_sql("clientes", engine, schema="silver", if_exists="append", index=False)

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO gold.dim_municipio (codigo_ibge, nome, uf)
            SELECT codigo_ibge, nome, uf FROM silver.municipios
        """))
        conn.execute(text("""
            INSERT INTO gold.dim_produto (nome)
            SELECT DISTINCT produto FROM silver.vendas ORDER BY produto
        """))
        conn.execute(text("""
            INSERT INTO gold.dim_cliente (cliente_id, nome, segmento, cidade, codigo_ibge, data_cadastro, idade)
            SELECT c.cliente_id, c.nome, c.segmento, c.cidade, c.codigo_ibge, c.data_cadastro, c.idade
            FROM silver.clientes c
            WHERE EXISTS (SELECT 1 FROM silver.vendas v WHERE v.cliente_id = c.cliente_id)
        """))
        conn.execute(text("""
            INSERT INTO gold.fato_venda (venda_id, cliente_id, produto_id, data, quantidade, valor)
            SELECT v.venda_id, v.cliente_id, p.produto_id, v.data, v.quantidade, v.valor
            FROM silver.vendas v
            JOIN gold.dim_produto p ON p.nome = v.produto
            JOIN gold.dim_cliente c ON c.cliente_id = v.cliente_id
        """))
        _log(conn, "vendas_csv", metricas["vendas_extraidas"], metricas["vendas_validas"], metricas["vendas_validas"], f"duplicatas={metricas['duplicatas_removidas']}")
        _log(conn, "clientes_json", metricas["clientes_extraidos"], metricas["clientes_validos"], metricas["clientes_validos"], f"sem_ibge={metricas['clientes_sem_ibge']}")
        _log(conn, "ibge_api", int(len(municipios)), int(len(municipios)), int(len(municipios)), origem)
    metricas["origem_ibge"] = origem
    metricas["municipios"] = int(len(municipios))
    metricas["executado_em"] = datetime.now().isoformat(timespec="seconds")
    SAIDAS.mkdir(parents=True, exist_ok=True)
    (SAIDAS / "etl.json").write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")
    return metricas


def executar() -> dict:
    preparar_banco()
    vendas_raw, clientes_raw, municipios, origem = extrair()
    vendas, clientes, metricas = transformar(vendas_raw, clientes_raw, municipios)
    return carregar(vendas_raw, clientes_raw, municipios, vendas, clientes, origem, metricas)


if __name__ == "__main__":
    print(executar())
