CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS transparencia;

CREATE TABLE IF NOT EXISTS transparencia.parlamentares (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nome_civil TEXT NOT NULL,
    nome_parlamentar TEXT,
    cpf TEXT UNIQUE,
    casa TEXT CHECK (casa IN ('camara', 'senado')),
    partido TEXT,
    uf CHAR(2),
    legislatura INT,
    id_camara INT UNIQUE,
    codigo_senado INT UNIQUE,
    foto_url TEXT,
    email TEXT,
    situacao TEXT,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparencia.emendas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    parlamentar_id UUID REFERENCES transparencia.parlamentares(id),
    numero_emenda TEXT,
    tipo INT,
    ano INT NOT NULL,
    autor TEXT,
    localidade_gasto TEXT,
    cod_funcao TEXT,
    cod_subfuncao TEXT,
    valor_empenhado NUMERIC(18,2),
    valor_liquidado NUMERIC(18,2),
    valor_pago NUMERIC(18,2),
    valor_resto_pago NUMERIC(18,2),
    fonte TEXT DEFAULT 'portal_transparencia',
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_emendas_numero_ano
    ON transparencia.emendas(numero_emenda, ano);

CREATE TABLE IF NOT EXISTS transparencia.cota_parlamentar (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    parlamentar_id UUID REFERENCES transparencia.parlamentares(id),
    ano INT,
    mes INT,
    tipo_despesa TEXT,
    descricao TEXT,
    fornecedor_nome TEXT,
    fornecedor_cnpj_cpf TEXT,
    valor_documento NUMERIC(18,2),
    valor_glosa NUMERIC(18,2),
    valor_liquido NUMERIC(18,2),
    url_documento TEXT,
    fonte TEXT DEFAULT 'camara',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cota_natural
    ON transparencia.cota_parlamentar(
        parlamentar_id,
        ano,
        mes,
        tipo_despesa,
        fornecedor_cnpj_cpf,
        valor_documento
    );

CREATE TABLE IF NOT EXISTS transparencia.contratos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    numero TEXT,
    orgao_superior TEXT,
    orgao_subordinado TEXT,
    fornecedor_nome TEXT,
    fornecedor_cnpj TEXT,
    objeto TEXT,
    valor_inicial NUMERIC(18,2),
    valor_final NUMERIC(18,2),
    data_inicio DATE,
    data_fim DATE,
    situacao TEXT,
    modalidade_licitacao TEXT,
    fonte TEXT DEFAULT 'portal_transparencia',
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparencia.votacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    casa TEXT CHECK (casa IN ('camara', 'senado')),
    id_votacao TEXT,
    data DATE,
    hora TIME,
    proposicao_tipo TEXT,
    proposicao_numero TEXT,
    proposicao_ano INT,
    proposicao_ementa TEXT,
    resultado TEXT,
    fonte TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparencia.votos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    votacao_id UUID REFERENCES transparencia.votacoes(id),
    parlamentar_id UUID REFERENCES transparencia.parlamentares(id),
    voto TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparencia.bens_declarados (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    parlamentar_id UUID REFERENCES transparencia.parlamentares(id),
    cpf_candidato TEXT,
    ano_eleicao INT,
    tipo_bem TEXT,
    descricao TEXT,
    valor NUMERIC(18,2),
    fonte TEXT DEFAULT 'tse',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparencia.receitas_campanha (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    parlamentar_id UUID REFERENCES transparencia.parlamentares(id),
    cpf_candidato TEXT,
    ano_eleicao INT,
    tipo_receita TEXT,
    doador_nome TEXT,
    doador_cnpj_cpf TEXT,
    valor NUMERIC(18,2),
    fonte TEXT DEFAULT 'tse',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparencia.viagens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nome_servidor TEXT,
    cpf TEXT,
    cargo TEXT,
    orgao TEXT,
    destino TEXT,
    data_inicio DATE,
    data_fim DATE,
    valor_passagens NUMERIC(18,2),
    valor_diarias NUMERIC(18,2),
    motivo TEXT,
    fonte TEXT DEFAULT 'portal_transparencia',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transparencia.coleta_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    fonte TEXT NOT NULL,
    endpoint TEXT,
    parametros JSONB,
    registros_coletados INT,
    registros_inseridos INT,
    registros_atualizados INT,
    status TEXT CHECK (status IN ('sucesso', 'erro', 'parcial')),
    erro TEXT,
    duracao_segundos NUMERIC(10,2),
    executado_em TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_parlamentares_cpf ON transparencia.parlamentares(cpf);
CREATE INDEX IF NOT EXISTS idx_parlamentares_nome ON transparencia.parlamentares USING gin(nome_civil gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_emendas_parlamentar ON transparencia.emendas(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_emendas_ano ON transparencia.emendas(ano);
CREATE INDEX IF NOT EXISTS idx_cota_parlamentar_id ON transparencia.cota_parlamentar(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_contratos_cnpj ON transparencia.contratos(fornecedor_cnpj);
CREATE INDEX IF NOT EXISTS idx_votos_parlamentar ON transparencia.votos(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_bens_parlamentar ON transparencia.bens_declarados(parlamentar_id);
CREATE INDEX IF NOT EXISTS idx_receitas_doador ON transparencia.receitas_campanha(doador_cnpj_cpf);
