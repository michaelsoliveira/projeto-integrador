# %% [markdown]
# Projeto Integrador — Pipeline de churn no varejo da Amazonia
#
# Autor: Michael Santos de Oliveira
#
# O alvo e prever se um cliente deixa de comprar a partir de 1 de outubro de 2024.
# O rotulo usa somente compras dessa data em diante. As features usam somente o historico anterior,
# para nao vazar o futuro para o treino.
#
# Fontes: CSV de vendas, JSON de clientes e a API de municipios do IBGE (Amapa).
# Caminho: fontes -> bronze -> silver -> gold (estrela + features) -> classificacao.

# %%
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sqlalchemy import create_engine, text

ROOT = Path.cwd()
if not (ROOT / "requirements.txt").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
pd.set_option("display.max_columns", 20)
pd.set_option("display.width", 120)
URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5434/varejo_amazonia"
print("raiz", ROOT)

# %% [markdown]
# ## Fontes
#
# O gerador cria 400 clientes e o historico de 2024, depois suja a amostra de proposito:
# duplicatas, valor nulo, valor negativo, data invalida, cidade mal escrita e idade ausente.
# A terceira fonte nao e gerada: o ETL consulta os 16 municipios do Amapa no IBGE.

# %%
from src.gerar_fontes import main as gerar_fontes

gerar_fontes()
vendas_brutas = pd.read_csv(ROOT / "data" / "vendas.csv")
clientes_brutos = pd.read_json(ROOT / "data" / "clientes.json")
print("linhas de vendas", len(vendas_brutas), "clientes", len(clientes_brutos))
print("valores nulos nas vendas", int(vendas_brutas["valor"].isna().sum()))
print("idades nulas", int(clientes_brutos["idade"].isna().sum()))

# %% [markdown]
# ## ETL e modelagem
#
# Bronze guarda a carga fiel. Silver descarta duplicata, data invalida e valor nao positivo,
# preenche idade com a mediana e casa a cidade com o municipio do IBGE.
# Gold separa dimensao de municipio, produto e cliente, o fato de venda e a tabela de features.
# Cada etapa grava contagem em `ops.etl_log`.

# %%
from src.etl import executar

metricas_etl = executar()
print(metricas_etl)
engine = create_engine(URL)
contagens = pd.read_sql(text("""
    SELECT 'bronze.vendas' AS tabela, COUNT(*) AS linhas FROM bronze.vendas
    UNION ALL SELECT 'silver.vendas', COUNT(*) FROM silver.vendas
    UNION ALL SELECT 'silver.clientes', COUNT(*) FROM silver.clientes
    UNION ALL SELECT 'gold.fato_venda', COUNT(*) FROM gold.fato_venda
    UNION ALL SELECT 'gold.dim_cliente', COUNT(*) FROM gold.dim_cliente
    UNION ALL SELECT 'gold.dim_municipio', COUNT(*) FROM gold.dim_municipio
"""), engine)
contagens

# %%
log = pd.read_sql(text("SELECT etapa, extraidos, transformados, carregados, detalhe FROM ops.etl_log ORDER BY id"), engine)
log

# %% [markdown]
# ## Analise exploratoria
#
# A receita mensal mostra a serie antes e depois do corte. O corte nao entra nas features:
# ele so define quem voltou a comprar.

# %%
fato = pd.read_sql(text("""
    SELECT f.data, f.valor, c.cidade, c.segmento, p.nome AS produto
    FROM gold.fato_venda f
    JOIN gold.dim_cliente c ON c.cliente_id = f.cliente_id
    JOIN gold.dim_produto p ON p.produto_id = f.produto_id
"""), engine)
fato["data"] = pd.to_datetime(fato["data"])
mensal = fato.set_index("data").resample("MS")["valor"].sum()
fig, ax = plt.subplots(figsize=(8, 3.5))
mensal.plot(ax=ax, color="#0f766e")
ax.axvline(pd.Timestamp("2024-10-01"), color="#b45309", linestyle="--", label="corte")
ax.set_title("Receita mensal")
ax.legend()
fig.tight_layout()
(ROOT / "evidencias").mkdir(parents=True, exist_ok=True)
fig.savefig(ROOT / "evidencias" / "receita_mensal.png", dpi=120)
plt.show()

# %%
por_cidade = fato.groupby("cidade")["valor"].sum().sort_values(ascending=False)
fig, ax = plt.subplots(figsize=(7, 3.5))
por_cidade.plot(kind="bar", ax=ax, color="#0369a1")
ax.set_title("Receita por cidade")
fig.tight_layout()
fig.savefig(ROOT / "evidencias" / "receita_cidade.png", dpi=120)
plt.show()
print("clientes sem municipio IBGE", metricas_etl["clientes_sem_ibge"])

# %% [markdown]
# ## Features
#
# Quinze colunas, contando o alvo. Todas as agregacoes de compra param em 30 de setembro de 2024.
# `compras_90d` conta os 90 dias anteriores ao corte, nao os dias posteriores.

# %%
from src.features import DOCUMENTACAO, construir

features = construir()
for nome, texto in DOCUMENTACAO.items():
    print(f"- {nome}: {texto}")
print("clientes", len(features), "taxa de churn", round(float(features["churn"].mean()), 4))
features.describe().round(2)

# %%
correlacao = features.drop(columns=["cliente_id"]).corr(numeric_only=True)["churn"].drop("churn").sort_values()
fig, ax = plt.subplots(figsize=(7, 4))
correlacao.plot(kind="barh", ax=ax, color="#0f766e")
ax.set_title("Correlacao de cada feature com o churn")
fig.tight_layout()
fig.savefig(ROOT / "evidencias" / "correlacao_churn.png", dpi=120)
plt.show()
correlacao.round(3)

# %% [markdown]
# ## Modelo
#
# Tres classificadores, comparados com a classe majoritaria do treino.
# O `StandardScaler` e ajustado so no treino. A metrica principal e o F1 da classe churn,
# porque accuracy sozinha favorece quem apenas repete a classe mais comum.
# O arquivo `modelos/modelo_churn.pkl` guarda o modelo de maior F1, o scaler e a lista de colunas.

# %%
from src.modelo import treinar

resultado = treinar()
resultado

# %%
ranking = pd.DataFrame(resultado["modelos"]).sort_values("f1", ascending=False)
ranking

# %% [markdown]
# ## Leitura do resultado
#
# A celula seguinte escreve a interpretacao com os numeros desta execucao.
# Recencia alta e poucas compras recentes aumentam a chance de churn; o desenho do rotulo
# segue essa ideia, com ruido, para o modelo ter o que aprender sem ser uma regra fixa.

# %%
melhor = ranking.iloc[0]
maior = correlacao.abs().sort_values(ascending=False).head(3)
texto = (
    f"O melhor modelo no teste foi {melhor['modelo']} "
    f"com accuracy {melhor['accuracy']:.3f} e F1 {melhor['f1']:.3f}. "
    f"A classe majoritaria acertou accuracy {resultado['baseline_accuracy']:.3f} "
    f"e F1 {resultado['baseline_f1']:.3f}. "
    f"As tres features de maior correlacao absoluta com o alvo foram "
    + ", ".join(f"{nome} ({valor:.3f})" for nome, valor in maior.items())
    + f". A base tem {resultado['clientes']} clientes, taxa de churn {resultado['churn_rate']:.3f}, "
    f"treino {resultado['treino']} e teste {resultado['teste']}."
)
print(texto)
(ROOT / "saidas" / "interpretacao.txt").write_text(texto + "\n", encoding="utf-8")
