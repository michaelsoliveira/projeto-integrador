# Projeto integrador — churn no varejo da Amazonia

Pipeline de engenharia de dados e classificacao de churn. Autor: Michael Santos de Oliveira.

O recorte e uma loja com clientes em municipios do Amapa. A pergunta do modelo e se o cliente volta a comprar a partir de 1 de outubro de 2024. Quem nao compra nessa janela recebe `churn = 1`.

## Arquitetura

```
vendas.csv + clientes.json + API IBGE
        -> bronze (carga fiel)
        -> silver (limpo e padronizado)
        -> gold (dimensoes, fato e features)
        -> treino e metricas
```

| Schema | Papel |
| --- | --- |
| `bronze` | CSV, JSON e municipios como chegaram |
| `silver` | Venda com data e valor validos; cidade casada com o codigo IBGE |
| `gold` | `dim_municipio`, `dim_produto`, `dim_cliente`, `fato_venda`, `cliente_features` |
| `ops` | Log de cada etapa do ETL |

As features de compra usam somente o historico anterior ao corte. O rotulo usa somente as compras do corte em diante.

## Fontes

1. `data/vendas.csv` — vendas, com duplicata, valor nulo, valor negativo e data invalida.
2. `data/clientes.json` — cadastro, com cidade mal escrita, idade ausente e e-mail fora do padrao.
3. API do IBGE, municipios do Amapa: `https://servicodados.ibge.gov.br/api/v1/localidades/estados/AP/municipios`. Se a rede falhar, o ETL reutiliza `data/ibge_municipios_ap.json`.

O gerador `src/gerar_fontes.py` recria as duas fontes locais com semente 42. A chance de o cliente voltar depois do corte depende da recencia, da frequencia e do segmento, com ruido. O modelo nao recebe essa formula; ele ve so as features.

## Como executar

Requisito: Docker, Python 3.12 e a porta 5434 livre para o PostgreSQL deste curso (`postgres` / `postgres`).

```bash
cd projeto-integrador
chmod +x run.sh
./run.sh
```

O script sobe o Postgres do `docker-compose.yml` da pasta pai, cria o banco `varejo_amazonia`, executa o notebook e grava `saidas/consultas.txt`.

Para rodar os passos separadamente, com o ambiente virtual ativo e a pasta do projeto no `PYTHONPATH`:

```bash
python -m src.gerar_fontes
python -m src.etl
python -m src.features
python -m src.modelo
```

## O que cada pasta guarda

| Caminho | Conteudo |
| --- | --- |
| `sql/schema.sql` | Modelagem bronze, silver, gold e log |
| `sql/consultas.sql` | Contagens para conferencia |
| `src/etl.py` | Extracao, limpeza e carga |
| `src/features.py` | Dicionario e montagem de `gold.cliente_features` |
| `src/modelo.py` | Baseline, tres classificadores, `.pkl` e F1 |
| `notebooks/pipeline.ipynb` | Analise exploratoria, features, treino e leitura do resultado |
| `modelos/modelo_churn.pkl` | Modelo de maior F1, scaler e colunas |
| `saidas/` | Metricas, relatorios e interpretacao |
| `evidencias/` | Graficos de receita, correlacao e F1 |

## Modelo

Classificacao. Modelos: regressao logistica, floresta aleatoria e gradient boosting. A referencia e a classe majoritaria do treino. O scaler e ajustado somente no treino. A metrica de escolha e o F1; accuracy tambem e reportada. O notebook escreve a leitura numerica em `saidas/interpretacao.txt`.

## Decisoes

- Tres fontes, sendo uma API publica, para a coleta nao ficar so em arquivos locais.
- Medallion em schemas do PostgreSQL, no lugar de um data lake: o requisito da disciplina e o banco relacional.
- Corte fixo em 1 de outubro de 2024 para separar feature e alvo.
- Cidades sem correspondencia no IBGE permanecem na base, com `tem_ibge = 0`, em vez de serem apagadas.
