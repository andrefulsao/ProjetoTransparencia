# Guia de Testes — Fase 1

## 1. Pré-requisitos (antes de rodar qualquer coisa)

```bash
# Entrar na pasta do projeto
cd transparencia-brasil

# Verificar se o Python está ok
python --version  # precisa ser 3.11+

# Verificar se as dependências instalaram
pip list | grep -E "httpx|supabase|typer|tenacity"

# Verificar se o .env existe e tem valores
cat .env
# Deve mostrar SUPABASE_URL, SUPABASE_KEY e TRANSPARENCIA_API_KEY preenchidos
```

---

## 2. Testar conexão com Supabase

Crie um arquivo `test_conexao.py` na raiz do projeto:

```python
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

print(f"URL: {url}")
print(f"Key: {key[:20]}...")  # só os primeiros 20 chars

client = create_client(url, key)

# Tenta uma query simples na tabela parlamentares
result = client.schema("transparencia").table("parlamentares").select("*").limit(1).execute()
print(f"\nConexão OK! Registros na tabela: {len(result.data)}")
```

```bash
python test_conexao.py
```

**Se der erro:**
- `relation "transparencia.parlamentares" does not exist` → o schema SQL não foi rodado. Vá no Supabase Dashboard > SQL Editor, cole o conteúdo de `migrations/001_initial_schema.sql` e execute.
- `Invalid API key` → confira se a key no `.env` é a **service_role** (não a anon key). Está em Settings > API no dashboard.
- `Could not resolve host` → a URL do Supabase está errada.

---

## 3. Testar as APIs sem Supabase (sanidade)

```python
# test_apis.py
import httpx
import asyncio

async def test_camara():
    """Câmara dos Deputados - não precisa de autenticação"""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://dadosabertos.camara.leg.br/api/v2/deputados",
            params={"idLegislatura": 57, "itens": 3, "ordem": "ASC", "ordenarPor": "nome"}
        )
        print(f"Câmara: status {r.status_code}")
        dados = r.json()["dados"]
        for d in dados:
            print(f"  - {d['nome']} ({d['siglaPartido']}/{d['siglaUf']})")
        print(f"  Total na legislatura: {len(dados)}+ deputados\n")

async def test_senado():
    """Senado Federal - não precisa de autenticação"""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://legis.senado.leg.br/dadosabertos/senador/lista/atual",
            headers={"Accept": "application/json"}
        )
        print(f"Senado: status {r.status_code}")
        # A estrutura do JSON do Senado é aninhada
        dados = r.json()
        # Navegar na estrutura (pode variar)
        try:
            senadores = dados["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
            for s in senadores[:3]:
                ident = s["IdentificacaoParlamentar"]
                print(f"  - {ident['NomeParlamentar']} ({ident.get('SiglaPartidoParlamentar','?')}/{ident.get('UfParlamentar','?')})")
            print(f"  Total: {len(senadores)} senadores\n")
        except KeyError as e:
            print(f"  Estrutura diferente do esperado. Chave ausente: {e}")
            print(f"  Chaves do topo: {list(dados.keys())}")

async def test_transparencia():
    """Portal da Transparência - PRECISA de API key"""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("TRANSPARENCIA_API_KEY")
    if not api_key:
        print("Transparência: TRANSPARENCIA_API_KEY não configurada, pulando.\n")
        return
    
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://api.portaldatransparencia.gov.br/api-de-dados/emendas",
            params={"ano": 2024, "pagina": 1, "tamanhoPagina": 3},
            headers={"chave-api-dados": api_key}
        )
        print(f"Transparência: status {r.status_code}")
        if r.status_code == 200:
            dados = r.json()
            for e in dados[:3]:
                print(f"  - Emenda: {e.get('numero', '?')} | Autor: {e.get('nomeAutor', '?')}")
            print()
        elif r.status_code == 401:
            print("  API key inválida ou expirada!\n")
        elif r.status_code == 429:
            print("  Rate limit atingido. Aguarde 1 minuto.\n")

async def main():
    print("=== Testando APIs ===\n")
    await test_camara()
    await test_senado()
    await test_transparencia()
    print("=== Fim dos testes ===")

asyncio.run(main())
```

```bash
python test_apis.py
```

**Resultado esperado:**
```
=== Testando APIs ===

Câmara: status 200
  - Abilio Brunini (PL/MT)
  - Acácio Favacho (MDB/AP)
  - Adail Filho (REPUBLICANOS/AM)
  Total na legislatura: 3+ deputados

Senado: status 200
  - Senador Fulano (PT/SP)
  - Senador Ciclano (PL/RJ)
  - Senador Beltrano (MDB/RS)
  Total: 81 senadores

Transparência: status 200
  - Emenda: 12345 | Autor: FULANO DE TAL

=== Fim dos testes ===
```

---

## 4. Testar o módulo de normalização

```python
# test_normalizacao.py
from utils.normalization import normalizar_cpf, normalizar_cnpj, normalizar_nome

# CPF
assert normalizar_cpf("123.456.789-00") == "12345678900"
assert normalizar_cpf("12345678900") == "12345678900"
assert normalizar_cpf("1234567890") == "01234567890"  # zero-pad
assert normalizar_cpf(None) is None
assert normalizar_cpf("") is None
print("CPF: OK")

# CNPJ
assert normalizar_cnpj("12.345.678/0001-90") == "12345678000190"
assert normalizar_cnpj("12345678000190") == "12345678000190"
assert normalizar_cnpj(None) is None
print("CNPJ: OK")

# Nomes
assert normalizar_nome("José da Silva Júnior") == "JOSE DA SILVA JUNIOR"
assert normalizar_nome("  MARIA  DE   LOURDES  ") == "MARIA DE LOURDES"
assert normalizar_nome("André François") == "ANDRE FRANCOIS"
assert normalizar_nome("JOÃO") == "JOAO"
assert normalizar_nome(None) is None
print("Nomes: OK")

print("\nTodos os testes de normalização passaram!")
```

```bash
python test_normalizacao.py
```

---

## 5. Testar a coleta real (Fase 1 completa)

```bash
# Primeiro, verificar se o CLI responde
python main.py --help
python main.py coletar --help

# Rodar a coleta de parlamentares
python main.py coletar parlamentares
```

**O que observar no output:**
- Deve mostrar logs de progresso (ex: "Coletando deputados da legislatura 57...")
- Deve mostrar quantos deputados foram coletados (~513)
- Deve mostrar quantos senadores foram coletados (~81)
- Não deve ter tracebacks de erro
- No final, deve registrar sucesso no coleta_log

---

## 6. Validar os dados no Supabase

Depois da coleta, vá no **Supabase Dashboard > SQL Editor** e rode:

```sql
-- Quantos parlamentares foram inseridos?
SELECT casa, COUNT(*) as total
FROM transparencia.parlamentares
GROUP BY casa;
-- Esperado: camara ~513, senado ~81

-- Amostra de deputados
SELECT nome_parlamentar, partido, uf, id_camara
FROM transparencia.parlamentares
WHERE casa = 'camara'
ORDER BY nome_parlamentar
LIMIT 10;

-- Amostra de senadores
SELECT nome_parlamentar, partido, uf, codigo_senado
FROM transparencia.parlamentares
WHERE casa = 'senado'
ORDER BY nome_parlamentar
LIMIT 10;

-- Verificar se CPFs foram preenchidos (nem todos terão)
SELECT casa,
       COUNT(*) as total,
       COUNT(cpf) as com_cpf,
       COUNT(*) - COUNT(cpf) as sem_cpf
FROM transparencia.parlamentares
GROUP BY casa;

-- Verificar o log de coleta
SELECT fonte, endpoint, registros_coletados, registros_inseridos, status, duracao_segundos, executado_em
FROM transparencia.coleta_log
ORDER BY executado_em DESC
LIMIT 5;

-- Verificar se não tem duplicados
SELECT nome_civil, COUNT(*) as qtd
FROM transparencia.parlamentares
GROUP BY nome_civil
HAVING COUNT(*) > 1;
-- Idealmente vazio. Se tiver duplicados, o upsert não está funcionando certo.
```

---

## 7. Checklist final da Fase 1

```
[ ] .env configurado com SUPABASE_URL + SUPABASE_KEY
[ ] Schema SQL executado no Supabase (todas as tabelas existem)
[ ] pip install das dependências sem erro
[ ] test_conexao.py conecta no Supabase
[ ] test_apis.py retorna 200 da Câmara e do Senado
[ ] test_normalizacao.py passa todos os asserts
[ ] python main.py coletar parlamentares roda sem erro
[ ] ~513 deputados e ~81 senadores na tabela parlamentares
[ ] coleta_log tem registros com status 'sucesso'
[ ] Sem duplicatas na tabela parlamentares
```

**Se tudo passou, pode ir para a Fase 2.**

---

## Troubleshooting comum

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| `ModuleNotFoundError: No module named 'supabase'` | Dependências não instaladas | `pip install -r requirements.txt` |
| `schema "transparencia" does not exist` | Migration não foi rodada | Rodar SQL no Supabase Dashboard |
| `APIError: permission denied for schema transparencia` | Usando anon key em vez de service_role | Trocar key no .env |
| Senado retorna XML em vez de JSON | Faltou header Accept | Verificar se o collector envia `Accept: application/json` |
| Câmara retorna 0 deputados | idLegislatura errada | Verificar se é 57 (legislatura 2023-2027) |
| Timeout na coleta dos detalhes de deputados | São 513 requests sequenciais | Normal, pode levar 5-10min. Verificar se tem rate limiting |
| CPF vem None para todos | API da Câmara não retorna CPF no /deputados | Precisa buscar em /deputados/{id} (detalhe individual) |
