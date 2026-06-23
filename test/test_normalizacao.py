# test_normalizacao.py
from utils.normalization import normalize_cpf, normalize_cnpj, normalize_name

# CPF
assert normalize_cpf("123.456.789-00") == "12345678900"
assert normalize_cpf("12345678900") == "12345678900"
assert normalize_cpf("1234567890") == "01234567890"  # zero-pad
assert normalize_cpf(None) is None
assert normalize_cpf("") is None
print("CPF: OK")

# CNPJ
assert normalize_cnpj("12.345.678/0001-90") == "12345678000190"
assert normalize_cnpj("12345678000190") == "12345678000190"
assert normalize_cnpj(None) is None
print("CNPJ: OK")

# Nomes
assert normalize_name("José da Silva Júnior") == "JOSE DA SILVA JUNIOR"
assert normalize_name("  MARIA  DE   LOURDES  ") == "MARIA DE LOURDES"
assert normalize_name("André François") == "ANDRE FRANCOIS"
assert normalize_name("JOÃO") == "JOAO"
assert normalize_name(None) is None
print("Nomes: OK")

print("\nTodos os testes de normalização passaram!")