"""Monta a tabela gold.cliente_features a partir do historico anterior ao corte."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5434/varejo_amazonia"
CORTE = pd.Timestamp("2024-10-01")
SEGMENTO = {"Premium": 0, "Regular": 1, "VIP": 2}

FEATURES = [
    "dias_desde_cadastro",
    "mes_ultima_compra",
    "eh_fim_de_semana",
    "total_compras",
    "qtd_compras",
    "ticket_medio",
    "produtos_distintos",
    "idade",
    "desvio_valor",
    "recencia_dias",
    "freq_mensal",
    "compras_90d",
    "segmento_cod",
    "tem_ibge",
]

DOCUMENTACAO = {
    "dias_desde_cadastro": "Dias entre o cadastro do cliente e o corte de 1 de outubro de 2024.",
    "mes_ultima_compra": "Mes da ultima compra anterior ao corte.",
    "eh_fim_de_semana": "1 se essa ultima compra caiu em sabado ou domingo.",
    "total_compras": "Soma do valor das compras anteriores ao corte.",
    "qtd_compras": "Quantidade de compras anteriores ao corte.",
    "ticket_medio": "Valor medio das compras anteriores ao corte.",
    "produtos_distintos": "Quantidade de produtos diferentes no historico.",
    "idade": "Idade do cadastro, com nulos preenchidos pela mediana no ETL.",
    "desvio_valor": "Desvio padrao dos valores; zero quando ha uma compra so.",
    "recencia_dias": "Dias entre a ultima compra anterior ao corte e o corte.",
    "freq_mensal": "Compras por mes de vida do cadastro ate o corte.",
    "compras_90d": "Compras nos 90 dias imediatamente anteriores ao corte.",
    "segmento_cod": "Segmento em inteiro: Premium 0, Regular 1, VIP 2.",
    "tem_ibge": "1 se a cidade do cliente casou com um municipio da API do IBGE.",
    "churn": "1 se o cliente nao tem compra em 1 de outubro de 2024 ou depois.",
}


def construir() -> pd.DataFrame:
    engine = create_engine(URL)
    vendas = pd.read_sql(text("SELECT cliente_id, data, produto, valor FROM silver.vendas"), engine)
    clientes = pd.read_sql(text("SELECT cliente_id, segmento, data_cadastro, idade, codigo_ibge FROM silver.clientes"), engine)
    vendas["data"] = pd.to_datetime(vendas["data"])
    clientes["data_cadastro"] = pd.to_datetime(clientes["data_cadastro"])
    historico = vendas.loc[vendas["data"] < CORTE].copy()
    futuro = set(vendas.loc[vendas["data"] >= CORTE, "cliente_id"].unique())
    recente = historico.loc[historico["data"] >= CORTE - pd.Timedelta(days=90)]
    compras_90d = recente.groupby("cliente_id").size().rename("compras_90d")

    grupo = historico.groupby("cliente_id").agg(
        total_compras=("valor", "sum"),
        qtd_compras=("valor", "count"),
        ticket_medio=("valor", "mean"),
        produtos_distintos=("produto", "nunique"),
        desvio_valor=("valor", "std"),
        ultima=("data", "max"),
    ).reset_index()
    grupo["desvio_valor"] = grupo["desvio_valor"].fillna(0)
    grupo = grupo.merge(clientes, on="cliente_id", how="inner")
    grupo = grupo.merge(compras_90d, on="cliente_id", how="left")
    grupo["compras_90d"] = grupo["compras_90d"].fillna(0).astype(int)
    vida = (CORTE - grupo["data_cadastro"]).dt.days.clip(lower=1)
    grupo["dias_desde_cadastro"] = vida
    grupo["mes_ultima_compra"] = grupo["ultima"].dt.month.astype(int)
    grupo["eh_fim_de_semana"] = grupo["ultima"].dt.dayofweek.isin([5, 6]).astype(int)
    grupo["recencia_dias"] = (CORTE - grupo["ultima"]).dt.days.astype(int)
    grupo["freq_mensal"] = (grupo["qtd_compras"] / (vida / 30)).round(4)
    grupo["segmento_cod"] = grupo["segmento"].map(SEGMENTO).astype(int)
    grupo["tem_ibge"] = grupo["codigo_ibge"].notna().astype(int)
    grupo["churn"] = (~grupo["cliente_id"].isin(futuro)).astype(int)
    colunas = ["cliente_id", *FEATURES, "churn"]
    saida = grupo[colunas].copy()
    inteiros = [
        "cliente_id", "dias_desde_cadastro", "mes_ultima_compra", "eh_fim_de_semana",
        "qtd_compras", "produtos_distintos", "idade", "recencia_dias", "compras_90d",
        "segmento_cod", "tem_ibge", "churn",
    ]
    saida[inteiros] = saida[inteiros].astype(int)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE gold.cliente_features"))
        saida.to_sql("cliente_features", conn, schema="gold", if_exists="append", index=False)
    destino = Path(__file__).resolve().parents[1] / "data" / "features.csv"
    saida.to_csv(destino, index=False)
    return saida


if __name__ == "__main__":
    tabela = construir()
    print(len(tabela), "clientes", "churn", round(float(tabela["churn"].mean()), 3))
