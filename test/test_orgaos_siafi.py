import os, asyncio, httpx, json
from dotenv import load_dotenv
load_dotenv()

async def main():
    api_key = os.getenv("TRANSPARENCIA_API_KEY")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://api.portaldatransparencia.gov.br/api-de-dados/orgaos-siafi",
            params={"pagina": 1, "tamanhoPagina": 3},
            headers={"chave-api-dados": api_key}
        )
        print(f"Status: {r.status_code}")
        data = r.json()
        if isinstance(data, list) and data:
            print(f"Total retornado: {len(data)}")
            print("\nChaves disponíveis:", list(data[0].keys()))
            print("\nPrimeiros 3 registros:")
            for item in data[:3]:
                print(json.dumps(item, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(data, ensure_ascii=False, indent=2))

asyncio.run(main())
