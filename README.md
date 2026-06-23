# Transparencia Brasil

Pipeline Python para coletar dados publicos brasileiros, normalizar registros e persistir em um schema `transparencia` no Supabase/PostgreSQL.

## Fase 1 implementada

- Schema SQL inicial em `migrations/001_initial_schema.sql`
- `BaseCollector` async com retry, rate limit, paginacao, upsert e log em `coleta_log`
- Collector de parlamentares da Camara dos Deputados
- Collector de parlamentares do Senado Federal
- CLI inicial para coleta e status
- Estrutura de pastas prevista no PRD

## Fase 2 implementada

- Collector de emendas do Portal da Transparencia
- Vinculo inicial de emendas com parlamentares por nome normalizado
- Collector de cota parlamentar da Camara
- Coleta de cotas para todos os deputados com checkpoint a cada 50 deputados
- Resolver de parlamentares pendentes por CPF, nome exato e fuzzy match
- Logs de matches ambiguos em `coleta_log`

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Preencha `SUPABASE_URL` e `SUPABASE_KEY` no `.env`. A chave deve ser `service_role`, porque o pipeline faz upserts e escreve logs.

Depois aplique a migration `migrations/001_initial_schema.sql` no SQL Editor do Supabase.

Para bancos que ja tinham a Fase 1 aplicada, rode tambem:

```sql
-- migrations/002_phase2_constraints.sql
```

Essa migration cria as constraints usadas pelos upserts de emendas e cota parlamentar.

## Uso

```bash
python main.py coletar parlamentares
python main.py coletar parlamentares --fonte camara
python main.py coletar parlamentares --fonte senado
python main.py coletar emendas --ano 2024
python main.py coletar cota --ano 2024
python main.py coletar cota --deputado-id 204554 --ano 2024
python main.py coletar all
python main.py cruzar resolver-parlamentares
python main.py status
python main.py status --fonte camara
```

Se `SUPABASE_URL` e `SUPABASE_KEY` nao estiverem configurados, os collectors ainda coletam e normalizam os dados, mas nao persistem os registros.

## Estrutura

```text
transparencia-brasil/
├── main.py
├── config.py
├── db.py
├── collectors/
├── crosslinkers/
├── utils/
├── migrations/
├── .env.example
├── requirements.txt
└── README.md
```

## Proximas fases

- Fase 2: emendas, cota parlamentar e resolver de parlamentares
- Fase 3: contratos e cruzamento emenda-contrato
- Fase 4: TSE e cruzamento doador-contrato
- Fase 5: votacoes, viagens e views analiticas
- Fase 6: testes e polimento da CLI
