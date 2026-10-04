-- Banco varejo_amazonia
-- Bronze: carga fiel da fonte. Silver: limpo. Gold: modelo estrela e features.

DROP SCHEMA IF EXISTS gold CASCADE;
DROP SCHEMA IF EXISTS silver CASCADE;
DROP SCHEMA IF EXISTS bronze CASCADE;
DROP SCHEMA IF EXISTS ops CASCADE;

CREATE SCHEMA bronze;
CREATE SCHEMA silver;
CREATE SCHEMA gold;
CREATE SCHEMA ops;

CREATE TABLE bronze.vendas (
    venda_id INTEGER,
    cliente_id INTEGER,
    data TEXT,
    produto TEXT,
    quantidade TEXT,
    valor TEXT
);

CREATE TABLE bronze.clientes (
    cliente_id INTEGER,
    nome TEXT,
    email TEXT,
    cidade TEXT,
    segmento TEXT,
    data_cadastro TEXT,
    idade TEXT
);

CREATE TABLE bronze.municipios (
    codigo_ibge BIGINT,
    nome TEXT,
    uf CHAR(2)
);

CREATE TABLE silver.vendas (
    venda_id INTEGER PRIMARY KEY,
    cliente_id INTEGER NOT NULL,
    data DATE NOT NULL,
    produto TEXT NOT NULL,
    quantidade INTEGER NOT NULL,
    valor NUMERIC(12,2) NOT NULL
);

CREATE TABLE silver.clientes (
    cliente_id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    email TEXT,
    cidade TEXT NOT NULL,
    segmento TEXT NOT NULL,
    data_cadastro DATE NOT NULL,
    idade INTEGER NOT NULL,
    codigo_ibge BIGINT,
    municipio_ibge TEXT
);

CREATE TABLE silver.municipios (
    codigo_ibge BIGINT PRIMARY KEY,
    nome TEXT NOT NULL,
    uf CHAR(2) NOT NULL
);

CREATE TABLE gold.dim_municipio (
    codigo_ibge BIGINT PRIMARY KEY,
    nome TEXT NOT NULL,
    uf CHAR(2) NOT NULL
);

CREATE TABLE gold.dim_produto (
    produto_id SERIAL PRIMARY KEY,
    nome TEXT UNIQUE NOT NULL
);

CREATE TABLE gold.dim_cliente (
    cliente_id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    segmento TEXT NOT NULL,
    cidade TEXT NOT NULL,
    codigo_ibge BIGINT REFERENCES gold.dim_municipio(codigo_ibge),
    data_cadastro DATE NOT NULL,
    idade INTEGER NOT NULL
);

CREATE TABLE gold.fato_venda (
    venda_id INTEGER PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES gold.dim_cliente(cliente_id),
    produto_id INTEGER NOT NULL REFERENCES gold.dim_produto(produto_id),
    data DATE NOT NULL,
    quantidade INTEGER NOT NULL,
    valor NUMERIC(12,2) NOT NULL
);

CREATE TABLE gold.cliente_features (
    cliente_id INTEGER PRIMARY KEY REFERENCES gold.dim_cliente(cliente_id),
    dias_desde_cadastro INTEGER NOT NULL,
    mes_ultima_compra INTEGER NOT NULL,
    eh_fim_de_semana INTEGER NOT NULL,
    total_compras NUMERIC(14,2) NOT NULL,
    qtd_compras INTEGER NOT NULL,
    ticket_medio NUMERIC(12,2) NOT NULL,
    produtos_distintos INTEGER NOT NULL,
    idade INTEGER NOT NULL,
    desvio_valor NUMERIC(12,2) NOT NULL,
    recencia_dias INTEGER NOT NULL,
    freq_mensal NUMERIC(12,4) NOT NULL,
    compras_90d INTEGER NOT NULL,
    segmento_cod INTEGER NOT NULL,
    tem_ibge INTEGER NOT NULL,
    churn INTEGER NOT NULL
);

CREATE TABLE ops.etl_log (
    id SERIAL PRIMARY KEY,
    etapa TEXT NOT NULL,
    extraidos INTEGER NOT NULL,
    transformados INTEGER NOT NULL,
    carregados INTEGER NOT NULL,
    detalhe TEXT,
    executado_em TIMESTAMP NOT NULL DEFAULT NOW()
);
