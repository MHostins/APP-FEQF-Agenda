from gerador_excel import gerar_excel

evento_teste = {
    "quantidade": "20 crianças",
    "data_horario": "10/04/2026 - 14h00",
    "endereco": "Rua Exemplo, 123",
    "tema": "Tema Safari",
    "cliente": "Maria Silva",
    "pacote": "Oficina de Slime",
    "observacao": "Cliente pediu atenção com crianças menores.",
    "total": "R$ 850,00"
}

arquivo = gerar_excel(evento_teste)

print("Arquivo gerado:", arquivo)