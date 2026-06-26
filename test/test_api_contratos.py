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
                "codigoOrgao": "26000",  # Ministério da Educação
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
                print(f"  Órgão:       {c.get('unidadeGestora', {}).get('orgaoMaximo', {}).get('nome', '?')}")
                print(f"  Fornecedor:  {c.get('fornecedor', {}).get('nome', '?')}")
                print(f"  CNPJ:        {c.get('fornecedor', {}).get('cnpjFormatado', '?')}")
                print(f"  Valor:       R$ {c.get('valorFinalCompra', 0):,.2f}")
                print(f"  Vigência:    {c.get('dataInicioVigencia', '?')} a {c.get('dataFimVigencia', '?')}")
                print(f"  Objeto:      {str(c.get('objeto', '?'))[:80]}...")
                print()
        else:
            print(f"Erro: {r.text[:300]}")

asyncio.run(main())