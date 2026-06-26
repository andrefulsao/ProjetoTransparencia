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
                    "codigoOrgao": "26000", "pagina": 1, "tamanhoPagina": 1},
            headers={"chave-api-dados": api_key}
        )
        print(r)
        data = r.json()
        if r.status_code != 200:
            print("Erro:", data)
            return
        contrato = data[0]

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

        print("\n=== unidadeGestora ===")
        ug = contrato.get("unidadeGestora", {})
        for k, v in ug.items():
            print(f"  unidadeGestora.{k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v}")

        print("\n=== unidadeGestora.orgaoMaximo ===")
        orgao_max = ug.get("orgaoMaximo", {})
        for k, v in orgao_max.items():
            print(f"  orgaoMaximo.{k}: {v}")

asyncio.run(main())