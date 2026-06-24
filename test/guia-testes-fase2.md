# Guia de Testes — Fase 2

> **Pré-requisito:** Fase 1 concluída. Tabela `parlamentares` com ~513 deputados e ~81 senadores.

---

## 1. Verificar pré-condições da Fase 1

```sql
-- Rodar no Supabase Dashboard > SQL Editor
SELECT casa, COUNT(*) as total, COUNT(cpf) as com_cpf
FROM transparencia.parlamentares
GROUP BY casa;
```

Esperado:
```
camara  | ~513 | algum número > 0
senado  | ~81  | algum número > 0
```

Se `com_cpf` for 0 para ambos, o resolver vai depender 100% de fuzzy match por nome — funciona, mas com mais risco de erro.

---

## 2. Testar a API do Portal da Transparência (emendas)

```python
# test_api_emendas.py
import os, asyncio, httpx
from dotenv import load_dotenv
load_dotenv()

async def main():
    api_key = os.getenv("TRANSPARENCIA_API_KEY")
    if not api_key:
        print("❌ TRANSPARENCIA_API_KEY não configurada no .env")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://api.portaldatransparencia.gov.br/api-de-dados/emendas",
            params={"ano": 2024, "pagina": 1, "tamanhoPagina": 5},
            headers={"chave-api-dados": api_key}
        )
        print(f"Status: {r.status_code}")

        if r.status_code == 200:
            dados = r.json()
            print(f"Registros retornados: {len(dados)}\n")
            for e in dados[:3]:
                print(f"  Emenda: {e.get('numero', '?')}")
                print(f"  Autor:  {e.get('nomeAutor', '?')}")
                print(f"  Tipo:   {e.get('tipoEmenda', '?')}")
                print(f"  Pago:   R$ {e.get('valorPago', 0):,.2f}")
                print()
        elif r.status_code == 401:
            print("❌ API key inválida ou expirada")
        elif r.status_code == 429:
            print("⚠️ Rate limit atingido, aguarde 1 minuto")
        else:
            print(f"❌ Erro inesperado: {r.text[:300]}")

asyncio.run(main())
```

```bash
python test_api_emendas.py
```

---

## 3. Testar a API de cota parlamentar (CEAP)

```python
# test_api_cota.py
import asyncio, httpx

async def main():
    # Pegar o primeiro deputado da legislatura pra testar
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://dadosabertos.camara.leg.br/api/v2/deputados",
            params={"idLegislatura": 57, "itens": 1}
        )
        deputado = r.json()["dados"][0]
        dep_id = deputado["id"]
        dep_nome = deputado["nome"]
        print(f"Testando cota de: {dep_nome} (id={dep_id})\n")

        # Buscar despesas
        r2 = await client.get(
            f"https://dadosabertos.camara.leg.br/api/v2/deputados/{dep_id}/despesas",
            params={"ano": 2024, "itens": 5, "ordem": "DESC", "ordenarPor": "dataDocumento"}
        )
        print(f"Status: {r2.status_code}")
        despesas = r2.json()["dados"]
        print(f"Registros retornados: {len(despesas)}\n")

        for d in despesas[:3]:
            print(f"  Tipo:        {d.get('tipoDespesa', '?')}")
            print(f"  Fornecedor:  {d.get('nomeFornecedor', '?')}")
            print(f"  CNPJ/CPF:    {d.get('cnpjCpfFornecedor', '?')}")
            print(f"  Valor:       R$ {d.get('valorLiquido', 0):,.2f}")
            print(f"  Data:        {d.get('dataDocumento', '?')}")
            print()

asyncio.run(main())
```

```bash
python test_api_cota.py
```

---

## 4. Testar a coleta de emendas

```bash
# Coletar emendas de um único ano para testar
python main.py coletar emendas --ano 2024
```

**O que observar:**
- Logs mostrando paginação (página 1, 2, 3...)
- Sem tracebacks
- No final, total de registros inseridos

**Validar no Supabase:**

```sql
-- Quantas emendas foram coletadas?
SELECT COUNT(*) as total,
       COUNT(parlamentar_id) as com_parlamentar,
       COUNT(*) - COUNT(parlamentar_id) as sem_parlamentar
FROM transparencia.emendas
WHERE ano = 2024;

-- Amostra de emendas
SELECT e.numero_emenda, e.autor, e.tipo, e.valor_pago,
       p.nome_parlamentar
FROM transparencia.emendas e
LEFT JOIN transparencia.parlamentares p ON p.id = e.parlamentar_id
WHERE e.ano = 2024
ORDER BY e.valor_pago DESC NULLS LAST
LIMIT 10;

-- Distribuição por tipo de emenda
SELECT tipo, COUNT(*) as qtd, SUM(valor_pago) as total_pago
FROM transparencia.emendas
WHERE ano = 2024
GROUP BY tipo
ORDER BY total_pago DESC;
-- tipo 1=individual, 2=bancada, 3=comissão, 6=relator, 7=pix

-- Verificar coleta_log
SELECT fonte, registros_coletados, registros_inseridos, status, duracao_segundos
FROM transparencia.coleta_log
WHERE fonte = 'portal_transparencia'
ORDER BY executado_em DESC
LIMIT 3;
```

---

## 5. Testar a coleta de cota parlamentar

```bash
# Primeiro com um único deputado (pegar um id_camara da tabela)
python main.py coletar cota --deputado-id 204554 --ano 2024

# Se funcionar, testar com todos (demora 15-30 min)
# python main.py coletar cota --ano 2024
```

**Validar no Supabase:**

```sql
-- Quantas despesas de cota foram coletadas?
SELECT COUNT(*) as total
FROM transparencia.cota_parlamentar
WHERE ano = 2024;

-- Top 10 deputados por gasto de cota
SELECT p.nome_parlamentar, p.partido, p.uf,
       SUM(c.valor_liquido) as total_gasto,
       COUNT(*) as qtd_despesas
FROM transparencia.cota_parlamentar c
JOIN transparencia.parlamentares p ON p.id = c.parlamentar_id
WHERE c.ano = 2024
GROUP BY p.id
ORDER BY total_gasto DESC
LIMIT 10;

-- Tipos de despesa mais comuns
SELECT tipo_despesa, COUNT(*) as qtd, SUM(valor_liquido) as total
FROM transparencia.cota_parlamentar
WHERE ano = 2024
GROUP BY tipo_despesa
ORDER BY total DESC;

-- Verificar checkpoint (se parou no meio, quantos deputados foram processados?)
SELECT registros_coletados, registros_inseridos, status, erro
FROM transparencia.coleta_log
WHERE endpoint LIKE '%cota%' OR endpoint LIKE '%despesas%'
ORDER BY executado_em DESC
LIMIT 5;
```

---

## 6. Testar o resolver de parlamentares

```bash
# Ver quantos estão pendentes antes do resolver
python main.py cruzar resolver-parlamentares
```

**O que observar no output:**
- Quantas emendas estavam sem `parlamentar_id`
- Quantas foram resolvidas por CPF exato
- Quantas foram resolvidas por nome exato
- Quantas foram resolvidas por fuzzy match
- Quantas permanecem sem vínculo
- Se houver matches ambíguos, deve listar para revisão

**Validar no Supabase:**

```sql
-- Comparar antes/depois do resolver
-- (Quantas emendas agora têm parlamentar vinculado?)
SELECT COUNT(*) as total,
       COUNT(parlamentar_id) as vinculadas,
       COUNT(*) - COUNT(parlamentar_id) as pendentes,
       ROUND(100.0 * COUNT(parlamentar_id) / COUNT(*), 1) as pct_vinculadas
FROM transparencia.emendas
WHERE ano = 2024;
-- Objetivo: pct_vinculadas > 70%

-- Quais autores não foram resolvidos?
SELECT DISTINCT autor, COUNT(*) as qtd_emendas
FROM transparencia.emendas
WHERE parlamentar_id IS NULL AND ano = 2024
GROUP BY autor
ORDER BY qtd_emendas DESC
LIMIT 20;
-- Comum: emendas de bancada, comissões e relatores não terão match (esperado)

-- Verificar se não houve match errado (spot check)
SELECT e.autor as autor_emenda,
       p.nome_parlamentar as parlamentar_vinculado,
       p.partido, p.uf
FROM transparencia.emendas e
JOIN transparencia.parlamentares p ON p.id = e.parlamentar_id
WHERE e.ano = 2024
ORDER BY RANDOM()
LIMIT 15;
-- Verificar manualmente: os nomes batem? Faz sentido o vínculo?
```

---

## 7. Teste de resiliência (opcional mas recomendado)

```bash
# Simular falha: desconecte a internet e rode
python main.py coletar emendas --ano 2024
# Deve mostrar retries e falhar graciosamente (sem traceback feio)
# Reconecte e rode de novo — deve continuar de onde parou (idempotente)
```

```bash
# Simular rate limit: rode duas instâncias simultâneas
python main.py coletar emendas --ano 2023 &
python main.py coletar emendas --ano 2024 &
# O rate limiter deve evitar HTTP 429
```

---

## 8. Checklist final da Fase 2

```
[ ] API do Transparência retorna 200 com emendas
[ ] API da Câmara retorna despesas de cota (CEAP)
[ ] python main.py coletar emendas --ano 2024 roda sem erro
[ ] Emendas aparecem na tabela com valores corretos
[ ] python main.py coletar cota --deputado-id XXXXX --ano 2024 roda sem erro
[ ] Despesas de cota aparecem na tabela
[ ] python main.py cruzar resolver-parlamentares executa
[ ] >70% das emendas individuais vinculadas a parlamentares
[ ] Spot check manual: vínculos fazem sentido
[ ] coleta_log registra todas as coletas com status correto
[ ] Sem duplicatas (rodar coleta 2x não duplica registros)
```

**Se tudo passou, pode ir para a Fase 3.**

---

## Troubleshooting

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| `401` no Transparência | API key inválida | Recadastrar em portaldatransparencia.gov.br |
| `429 Too Many Requests` | Rate limit excedido | Reduzir `RATE_LIMIT_TRANSPARENCIA` no .env |
| Emendas com valor_pago = 0 | Normal, nem toda emenda é paga | Filtrar por `valor_pago > 0` nas análises |
| Resolver vincula 0 emendas | Nomes não batem (formatação) | Verificar `normalizar_nome` com nomes reais do raw_data |
| Cota demora muito | São ~513 deputados × várias páginas | Testar com 1 deputado, depois rodar completo com paciência |
| `parlamentar_id NULL` em emendas de bancada | Esperado — emendas de bancada não têm autor individual | Não é bug |
