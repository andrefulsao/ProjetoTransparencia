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
                print(f"  Emenda: {e.get('numeroEmenda', '?')}")
                print(f"  Autor:  {e.get('nomeAutor', '?')}")
                print(f"  Tipo:   {e.get('tipoEmenda', '?')}")
                print(f"  Pago:   R$ {e.get('valorPago', 0)}")
                print()
        elif r.status_code == 401:
            print("❌ API key inválida ou expirada")
        elif r.status_code == 429:
            print("⚠️ Rate limit atingido, aguarde 1 minuto")
        else:
            print(f"❌ Erro inesperado: {r.text[:300]}")

asyncio.run(main())