"""Gera as duas fontes locais: CSV de vendas e JSON de clientes."""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CORTE = date(2024, 10, 1)
PRODUTOS = ["Notebook", "Mouse", "Teclado", "Monitor", "Cadeira", "Livro IA"]
CIDADES = ["Macapa", "Santana", "Laranjal do Jari", "Oiapoque", "Mazagao", "Porto Grande"]
SEGMENTOS = ["Premium", "Regular", "VIP"]
NOMES = ["Maria", "Joao", "Ana", "Pedro", "Lucia", "Carlos", "Fernanda", "Ricardo", "Beatriz", "Hugo"]


def _retorno(recencia: int, freq: int, segmento: str) -> float:
    ajuste = 0.35 if segmento == "Premium" else (-0.15 if segmento == "Regular" else 0.1)
    z = 1.4 - 0.028 * recencia + 0.42 * freq + ajuste
    return 1 / (1 + math.exp(-z))


def gerar(seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    random.seed(seed)
    clientes = []
    vendas = []
    venda_id = 1
    for cliente_id in range(1, 401):
        cadastro = date(2021, 6, 1) + timedelta(days=random.randint(0, 900))
        segmento = random.choice(SEGMENTOS)
        cidade = random.choice(CIDADES)
        idade = random.randint(21, 70)
        nome = f"{random.choice(NOMES)} {cliente_id}"
        clientes.append({
            "cliente_id": cliente_id,
            "nome": nome,
            "email": f"cliente{cliente_id}@varejoamazonia.com",
            "cidade": cidade,
            "segmento": segmento,
            "data_cadastro": cadastro.isoformat(),
            "idade": idade,
        })
        frequencia = random.randint(2, 9)
        ultima = cadastro
        for _ in range(frequencia):
            dia = date(2024, 1, 2) + timedelta(days=random.randint(0, 260))
            ultima = max(ultima, dia)
            vendas.append({
                "venda_id": venda_id,
                "cliente_id": cliente_id,
                "data": dia.isoformat(),
                "produto": random.choice(PRODUTOS),
                "quantidade": random.randint(1, 4),
                "valor": round(random.uniform(40, 2400), 2),
            })
            venda_id += 1
        recencia = (CORTE - ultima).days
        if random.random() < _retorno(recencia, frequencia, segmento):
            dia = CORTE + timedelta(days=random.randint(1, 80))
            vendas.append({
                "venda_id": venda_id,
                "cliente_id": cliente_id,
                "data": dia.isoformat(),
                "produto": random.choice(PRODUTOS),
                "quantidade": random.randint(1, 3),
                "valor": round(random.uniform(40, 2400), 2),
            })
            venda_id += 1

    vendas_df = pd.DataFrame(vendas)
    clientes_df = pd.DataFrame(clientes)
    sujas = []
    for i in range(20):
        sujas.append(dict(vendas_df.iloc[i]))
    for i in range(15):
        linha = dict(vendas_df.iloc[40 + i])
        linha["venda_id"] = venda_id
        linha["valor"] = None
        venda_id += 1
        sujas.append(linha)
    for i in range(8):
        linha = dict(vendas_df.iloc[70 + i])
        linha["venda_id"] = venda_id
        linha["valor"] = -abs(float(linha["valor"]))
        venda_id += 1
        sujas.append(linha)
    for i, ruim in enumerate(["32/13/2024", "nao-e-data", "", "2024-13-40", "00/00/0000"]):
        linha = dict(vendas_df.iloc[90 + i])
        linha["venda_id"] = venda_id
        linha["data"] = ruim
        venda_id += 1
        sujas.append(linha)
    vendas_df = pd.concat([vendas_df, pd.DataFrame(sujas)], ignore_index=True)
    clientes_df.loc[clientes_df.index % 23 == 0, "cidade"] = clientes_df.loc[clientes_df.index % 23 == 0, "cidade"].map(
        lambda v: random.choice([" macapa ", "MACAPA", "santana", "Cidade Inexistente"])
    )
    clientes_df.loc[clientes_df.index % 29 == 0, "idade"] = None
    clientes_df.loc[clientes_df.index % 31 == 0, "email"] = clientes_df.loc[clientes_df.index % 31 == 0, "email"].map(
        lambda v: f"  {str(v).upper()}  "
    )
    return vendas_df, clientes_df


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    vendas, clientes = gerar()
    vendas.to_csv(DATA / "vendas.csv", index=False)
    (DATA / "clientes.json").write_text(clientes.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    print(f"vendas={len(vendas)} clientes={len(clientes)}")


if __name__ == "__main__":
    main()
