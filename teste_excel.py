import openpyxl

arquivo = "modelo-eventos.xlsx"

wb = openpyxl.load_workbook(arquivo)
print("Arquivo aberto com sucesso!")
print("Abas encontradas:", wb.sheetnames)