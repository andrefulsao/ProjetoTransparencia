-- Unique index on contratos for upsert conflict resolution
CREATE UNIQUE INDEX IF NOT EXISTS uq_contratos_natural
    ON transparencia.contratos(numero, orgao_subordinado, fornecedor_cnpj);

-- Licitacoes table
CREATE TABLE IF NOT EXISTS transparencia.licitacoes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    numero TEXT,
    objeto TEXT,
    orgao TEXT,
    fornecedor_nome TEXT,
    fornecedor_cnpj TEXT,
    modalidade TEXT,
    situacao TEXT,
    data_abertura DATE,
    valor_estimado NUMERIC(18,2),
    fonte TEXT DEFAULT 'portal_transparencia',
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_licitacoes_natural
    ON transparencia.licitacoes(numero, orgao);

CREATE INDEX IF NOT EXISTS idx_licitacoes_cnpj ON transparencia.licitacoes(fornecedor_cnpj);

-- Emenda <-> contrato link table
CREATE TABLE IF NOT EXISTS transparencia.emenda_contrato_link (
    emenda_id UUID REFERENCES transparencia.emendas(id),
    contrato_id UUID REFERENCES transparencia.contratos(id),
    tipo_vinculo TEXT,
    confianca NUMERIC(3,2),
    PRIMARY KEY (emenda_id, contrato_id)
);

CREATE INDEX IF NOT EXISTS idx_eclink_emenda ON transparencia.emenda_contrato_link(emenda_id);
CREATE INDEX IF NOT EXISTS idx_eclink_contrato ON transparencia.emenda_contrato_link(contrato_id);
