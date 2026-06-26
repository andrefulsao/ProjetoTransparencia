import os, asyncio, httpx, json
from dotenv import load_dotenv
load_dotenv()

CODIGO_EMENDA = "202424420005"

async def main():
    api_key = os.getenv("TRANSPARENCIA_API_KEY")
    headers = {"chave-api-dados": api_key}

    async with httpx.AsyncClient(timeout=30) as client:
        for path, params in [
            ("transferencias-privadas", {"codigoEmenda": CODIGO_EMENDA, "pagina": 1, "tamanhoPagina": 3}),
            ("transferencias-voluntarias", {"codigoEmenda": CODIGO_EMENDA, "pagina": 1, "tamanhoPagina": 3}),
            ("despesas", {"codigoEmenda": CODIGO_EMENDA, "pagina": 1, "tamanhoPagina": 3}),
            ("despesas/por-emenda", {"codigoEmenda": CODIGO_EMENDA, "pagina": 1, "tamanhoPagina": 3}),
            ("favorecidos", {"codigoEmenda": CODIGO_EMENDA, "pagina": 1, "tamanhoPagina": 3}),
        ]:
            url = f"https://api.portaldatransparencia.gov.br/api-de-dados/{path}"
            r = await client.get(url, params=params, headers=headers)
            print(f"\n{path} → {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    print("Chaves:", list(data[0].keys()))
                    print(json.dumps(data[0], ensure_ascii=False, indent=2)[:600])
                else:
                    print(str(data)[:300])

asyncio.run(main())
