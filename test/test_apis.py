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