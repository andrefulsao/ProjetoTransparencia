import asyncio, json
from db import Database
from utils.normalization import normalize_cnpj

db = Database()

# Emendas 2024
emendas = db.select("emendas", columns="id,valor_pago,raw_data", filters={"ano": 2024})
print(f"Total emendas 2024: {len(emendas)}")
pagas = [e for e in emendas if e.get("valor_pago") and float(e["valor_pago"]) > 0]
print(f"Com valor_pago > 0: {len(pagas)}")
if pagas:
    print("\nExemplo raw_data (1ª emenda paga):")
    print(json.dumps(pagas[0].get("raw_data"), ensure_ascii=False, indent=2)[:800])

# Contratos
contratos = db.select("contratos", columns="id,fornecedor_cnpj,data_inicio,data_fim")
print(f"\nTotal contratos: {len(contratos)}")
com_cnpj = [c for c in contratos if c.get("fornecedor_cnpj")]
print(f"Com fornecedor_cnpj preenchido: {len(com_cnpj)}")
if com_cnpj:
    print("\nExemplos CNPJs dos contratos:")
    for c in com_cnpj[:5]:
        print(f"  {c['fornecedor_cnpj']}")
