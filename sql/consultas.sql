-- Conferencia depois do ETL e da carga de features.

SELECT 'bronze.vendas' AS tabela, COUNT(*) AS linhas FROM bronze.vendas
UNION ALL SELECT 'bronze.clientes', COUNT(*) FROM bronze.clientes
UNION ALL SELECT 'bronze.municipios', COUNT(*) FROM bronze.municipios
UNION ALL SELECT 'silver.vendas', COUNT(*) FROM silver.vendas
UNION ALL SELECT 'silver.clientes', COUNT(*) FROM silver.clientes
UNION ALL SELECT 'gold.fato_venda', COUNT(*) FROM gold.fato_venda
UNION ALL SELECT 'gold.cliente_features', COUNT(*) FROM gold.cliente_features
ORDER BY 1;

SELECT etapa, extraidos, transformados, carregados, detalhe
FROM ops.etl_log
ORDER BY id;

SELECT churn, COUNT(*) AS clientes
FROM gold.cliente_features
GROUP BY churn
ORDER BY churn;
