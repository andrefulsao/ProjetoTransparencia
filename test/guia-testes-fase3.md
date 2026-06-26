# Guia de Testes — Fase 3

> **Pré-requisito:** Fase 2 concluída. Emendas coletadas e parlamentares resolvidos.

---

## 1. Verificar pré-condições da Fase 2

```sql
-- Rodar no Supabase Dashboard > SQL Editor

-- Emendas existem?
SELECT ano, COUNT(*) as total,
       SUM(valor_pago) as total_pago,
       COUNT(parlamentar_id) as vinculadas
FROM transparencia.emendas
GROUP BY ano;

-- Tem emendas com valor pago > 0? (são essas que cruzam com contratos)
SELECT COUNT(*) as emendas_pagas
FROM transparencia.emendas
WHERE valor_pago > 0 AND ano = 2024;
-- Se for 0, o cruzamento não vai encontrar nada
```

---

## 2. Testar a API de contratos

```python
# test_api_contratos.py
import os, asyncio, httpx
from dotenv import load_dotenv
load_dotenv()

async def main():
    api_key = os.getenv("TRANSPARENCIA_API_KEY")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://api.portaldatransparencia.gov.br/api-de-dados/contratos",
            params={
                "dataInicial": "01/01/2024",
                "dataFinal": "31/12/2024",
                "pagina": 1,
                "tamanhoPagina": 5
            },
            headers={"chave-api-dados": api_key}
        )
        print(f"Status: {r.status_code}\n")

        if r.status_code == 200:
            dados = r.json()
            print(f"Registros retornados: {len(dados)}\n")
            for c in dados[:3]:
                print(f"  Número:      {c.get('numero', '?')}")
                print(f"  Órgão:       {c.get('orgaoSuperior', {}).get('nome', '?')}")
                print(f"  Fornecedor:  {c.get('fornecedor', {}).get('nome', '?')}")
                print(f"  CNPJ:        {c.get('fornecedor', {}).get('cnpjFormatado', '?')}")
                print(f"  Valor:       R$ {c.get('valorFinal', 0):,.2f}")
                print(f"  Vigência:    {c.get('dataInicioVigencia', '?')} a {c.get('dataFimVigencia', '?')}")
                print(f"  Objeto:      {str(c.get('objeto', '?'))[:80]}...")
                print()
        else:
            print(f"Erro: {r.text[:300]}")

asyncio.run(main())
```

```bash
python test_api_contratos.py
```

**Atenção ao formato de resposta:** a API retorna objetos aninhados (`fornecedor.nome`, `orgaoSuperior.nome`). Verifique se o collector está extraindo os campos corretamente, não armazenando o dict inteiro como string.

---

## 3. Verificar mapeamento dos campos

Compare o JSON real da API com o schema da tabela. Coisas comuns de dar errado:

```python
# test_mapeamento_contrato.py
import os, asyncio, httpx, json
from dotenv import load_dotenv
load_dotenv()

async def main():
    api_key = os.getenv("TRANSPARENCIA_API_KEY")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://api.portaldatransparencia.gov.br/api-de-dados/contratos",
            params={"dataInicial": "01/01/2024", "dataFinal": "31/12/2024",
                    "pagina": 1, "tamanhoPagina": 1},
            headers={"chave-api-dados": api_key}
        )
        contrato = r.json()[0]

        # Mostrar todas as chaves para verificar mapeamento
        print("=== Chaves do topo ===")
        for k, v in contrato.items():
            tipo = type(v).__name__
            preview = str(v)[:60] if not isinstance(v, dict) else json.dumps(v, ensure_ascii=False)[:80]
            print(f"  {k} ({tipo}): {preview}")

        # Campos aninhados comuns
        print("\n=== Fornecedor ===")
        forn = contrato.get("fornecedor", {})
        for k, v in forn.items():
            print(f"  fornecedor.{k}: {v}")

        print("\n=== Órgão Superior ===")
        orgao = contrato.get("orgaoSuperior", {})
        for k, v in orgao.items():
            print(f"  orgaoSuperior.{k}: {v}")

        print("\n=== Órgão Subordinado ===")
        orgao_sub = contrato.get("orgaoSubordinado", {})
        for k, v in orgao_sub.items():
            print(f"  orgaoSubordinado.{k}: {v}")

asyncio.run(main())
```

```bash
python test_mapeamento_contrato.py
```

Isso mostra a estrutura exata — use pra confirmar que o collector extrai `fornecedor.cnpjFormatado` (ou `fornecedor.cnpj`) e não tenta ler `cnpj` direto do topo.

---

## 4. Testar a coleta de contratos

```bash
# Coleta de um ano
python main.py coletar contratos --ano 2024
```

**O que observar:**
- Logs de paginação (pode ter muitas páginas — contratos federais são milhares)
- Sem tracebacks
- Duração razoável (pode levar 5-15 min dependendo do volume)

**Validar no Supabase:**

```sql
-- Quantos contratos foram coletados?
SELECT COUNT(*) as total
FROM transparencia.contratos;

-- Amostra
SELECT numero, orgao_superior, fornecedor_nome, fornecedor_cnpj,
       valor_inicial, valor_final, data_inicio, data_fim, situacao
FROM transparencia.contratos
ORDER BY valor_final DESC NULLS LAST
LIMIT 10;

-- Distribuição por órgão (top 10)
SELECT orgao_superior, COUNT(*) as qtd, SUM(valor_final) as total_valor
FROM transparencia.contratos
GROUP BY orgao_superior
ORDER BY total_valor DESC NULLS LAST
LIMIT 10;

-- CNPJs estão normalizados? (devem ter 14 dígitos, sem formatação)
SELECT fornecedor_cnpj, LENGTH(fornecedor_cnpj) as tamanho
FROM transparencia.contratos
WHERE fornecedor_cnpj IS NOT NULL
LIMIT 10;
-- Se vier "12.345.678/0001-90" em vez de "12345678000190", a normalização falhou

-- Verificar coleta_log
SELECT fonte, endpoint, registros_coletados, registros_inseridos,
       status, duracao_segundos
FROM transparencia.coleta_log
WHERE endpoint LIKE '%contrato%'
ORDER BY executado_em DESC
LIMIT 3;

-- Verificar se não tem duplicatas
SELECT numero, orgao_subordinado, fornecedor_cnpj, COUNT(*) as qtd
FROM transparencia.contratos
GROUP BY numero, orgao_subordinado, fornecedor_cnpj
HAVING COUNT(*) > 1;
```

---

## 5. Preparar tabela de link (se não foi criada pelo Codex)

```sql
-- Verificar se a tabela de link existe
SELECT EXISTS (
    SELECT FROM information_schema.tables
    WHERE table_schema = 'transparencia'
    AND table_name = 'emenda_contrato_link'
);

-- Se não existir, criar:
CREATE TABLE IF NOT EXISTS transparencia.emenda_contrato_link (
    emenda_id UUID REFERENCES transparencia.emendas(id),
    contrato_id UUID REFERENCES transparencia.contratos(id),
    tipo_vinculo TEXT,
    confianca NUMERIC(3,2),
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (emenda_id, contrato_id)
);
```

---

## 6. Testar o cruzamento emenda ↔ contrato

```bash
python main.py cruzar emenda-contrato --ano 2024
```

**O que observar no output:**
- Quantas emendas pagas foram analisadas
- Quantos CNPJs de favorecidos foram extraídos das emendas
- Quantos matches com contratos foram encontrados
- Valor total cruzado

**Validar no Supabase:**

```sql
-- Quantos links foram criados?
SELECT COUNT(*) as total_links
FROM transparencia.emenda_contrato_link;

-- Ver os cruzamentos encontrados
SELECT e.numero_emenda, e.autor, e.valor_pago as valor_emenda,
       c.fornecedor_nome, c.fornecedor_cnpj, c.valor_final as valor_contrato,
       c.objeto, c.orgao_superior
FROM transparencia.emenda_contrato_link ecl
JOIN transparencia.emendas e ON e.id = ecl.emenda_id
JOIN transparencia.contratos c ON c.id = ecl.contrato_id
ORDER BY c.valor_final DESC
LIMIT 20;

-- Top fornecedores que aparecem em emendas E contratos
SELECT c.fornecedor_nome, c.fornecedor_cnpj,
       COUNT(DISTINCT ecl.emenda_id) as qtd_emendas,
       SUM(e.valor_pago) as total_emendas,
       COUNT(DISTINCT ecl.contrato_id) as qtd_contratos,
       SUM(c.valor_final) as total_contratos
FROM transparencia.emenda_contrato_link ecl
JOIN transparencia.emendas e ON e.id = ecl.emenda_id
JOIN transparencia.contratos c ON c.id = ecl.contrato_id
GROUP BY c.fornecedor_nome, c.fornecedor_cnpj
ORDER BY total_contratos DESC
LIMIT 15;

-- Quais parlamentares têm mais emendas vinculadas a contratos?
SELECT p.nome_parlamentar, p.partido, p.uf,
       COUNT(DISTINCT ecl.emenda_id) as emendas_com_contrato,
       SUM(e.valor_pago) as total_emendas_vinculadas
FROM transparencia.emenda_contrato_link ecl
JOIN transparencia.emendas e ON e.id = ecl.emenda_id
JOIN transparencia.parlamentares p ON p.id = e.parlamentar_id
JOIN transparencia.contratos c ON c.id = ecl.contrato_id
GROUP BY p.id
ORDER BY total_emendas_vinculadas DESC
LIMIT 15;
```

---

## 7. Validar qualidade do cruzamento

O cruzamento pode encontrar poucos matches ou matches falsos. Isso é normal na primeira rodada.

```sql
-- Taxa de match: quantas emendas pagas foram cruzadas?
SELECT
    (SELECT COUNT(*) FROM transparencia.emendas WHERE valor_pago > 0 AND ano = 2024) as emendas_pagas,
    (SELECT COUNT(DISTINCT emenda_id) FROM transparencia.emenda_contrato_link) as emendas_cruzadas,
    ROUND(100.0 *
        (SELECT COUNT(DISTINCT emenda_id) FROM transparencia.emenda_contrato_link) /
        NULLIF((SELECT COUNT(*) FROM transparencia.emendas WHERE valor_pago > 0 AND ano = 2024), 0)
    , 1) as pct_cruzadas;

-- Spot check: pegar 5 cruzamentos aleatórios e verificar se fazem sentido
SELECT e.autor, e.numero_emenda, e.valor_pago,
       c.fornecedor_nome, c.objeto,
       c.data_inicio, c.data_fim
FROM transparencia.emenda_contrato_link ecl
JOIN transparencia.emendas e ON e.id = ecl.emenda_id
JOIN transparencia.contratos c ON c.id = ecl.contrato_id
ORDER BY RANDOM()
LIMIT 5;
```

**Taxas esperadas:**
- <5% é baixo, mas pode ser normal — emendas e contratos muitas vezes passam por intermediários (ex: fundo municipal) e não têm CNPJ direto em comum
- 5-20% é um bom resultado
- \>50% provavelmente indica match muito frouxo (conferir se está filtrando por período)

---

## 8. Checklist final da Fase 3

```
[ ] API de contratos retorna 200 com dados
[ ] Campos aninhados (fornecedor, órgão) extraídos corretamente
[ ] CNPJs normalizados (14 dígitos, sem formatação)
[ ] python main.py coletar contratos --ano 2024 roda sem erro
[ ] Contratos aparecem na tabela com valores corretos
[ ] Sem duplicatas na tabela contratos
[ ] Tabela emenda_contrato_link existe
[ ] python main.py cruzar emenda-contrato --ano 2024 executa
[ ] Links criados na tabela emenda_contrato_link
[ ] Spot check: cruzamentos fazem sentido (conferência manual)
[ ] coleta_log registra tudo com status correto
```

**Se tudo passou, pode ir para a Fase 4.**

---

## Troubleshooting

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| API retorna lista vazia | Período sem contratos ou formato de data errado | Confirmar formato `dd/MM/yyyy` (01/01/2024) |
| `fornecedor_cnpj` com pontuação | `normalizar_cnpj` não aplicado | Verificar se o collector chama normalização antes do upsert |
| Cruzamento encontra 0 matches | CNPJs da emenda vs contrato em formatos diferentes | Comparar amostras: `SELECT DISTINCT fornecedor_cnpj FROM contratos LIMIT 5` vs campo CNPJ no raw_data das emendas |
| ON CONFLICT erro | Contratos sem número ou sem CNPJ (NULL) | Adicionar fallback: usar hash do raw_data como chave se campos-chave forem nulos |
| Coleta muito lenta | Muitas páginas de contratos | Normal — contratos federais podem ser >100k registros. Filtrar por órgão se precisar de algo específico |
| `KeyError: 'fornecedor'` | Alguns contratos não têm fornecedor no JSON | Adicionar `.get("fornecedor", {})` com fallback |
