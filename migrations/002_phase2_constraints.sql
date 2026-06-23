CREATE UNIQUE INDEX IF NOT EXISTS uq_emendas_numero_ano
    ON transparencia.emendas(numero_emenda, ano);

CREATE UNIQUE INDEX IF NOT EXISTS uq_cota_natural
    ON transparencia.cota_parlamentar(
        parlamentar_id,
        ano,
        mes,
        tipo_despesa,
        fornecedor_cnpj_cpf,
        valor_documento
    );
