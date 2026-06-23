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