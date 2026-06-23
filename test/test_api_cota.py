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