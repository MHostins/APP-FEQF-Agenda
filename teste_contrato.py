from contrato_pdf import gerar_pdf_contrato

evento_exemplo = {
    "cliente": "Lidiane Beatriz Piotto Gomes",
    "cpf": "074.588.716-36",
    "data": "2026-05-03",
    "horario": "15h30",
    "tema": "Super Monstros",
    "quantidade_criancas": 20,
    "pacote": "oficina de customização de chapéus, oficina de fantoches e mesa de pintura livre",
    "valor_total": 3700,
    "valor_pago": 1850,
    "endereco": "SHIS UZ Lounge, Brasília/DF",
    "responsavel": "Lidiane",
    "observacao": "Os objetos que fazem parte deste contrato serão levados ao local com antecedência.",
}

pdf = gerar_pdf_contrato(evento_exemplo, "contrato_teste.pdf")
print(f"PDF gerado com sucesso em: {pdf}")