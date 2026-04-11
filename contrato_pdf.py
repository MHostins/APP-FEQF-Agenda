from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from pathlib import Path
from datetime import datetime


def gerar_pdf_contrato(evento, caminho_saida):
    doc = SimpleDocTemplate(str(caminho_saida), pagesize=A4)

    styles = getSampleStyleSheet()

    elementos = []

    # Título
    elementos.append(Paragraph("CONTRATO DE PRESTAÇÃO DE SERVIÇOS", styles["Title"]))
    elementos.append(Spacer(1, 12))

    # Contratante
    texto_contratante = f"""
    <b>CONTRATANTE:</b><br/>
    {evento.get("cliente","")}<br/>
    CPF: {evento.get("cpf","")}<br/>
    Telefone: {evento.get("telefone","")}
    """
    elementos.append(Paragraph(texto_contratante, styles["Normal"]))
    elementos.append(Spacer(1, 12))

    # Objeto
    texto_objeto = f"""
    <b>OBJETO:</b><br/>
    Prestação de serviços para {evento.get("quantidade_criancas","")} crianças,
    tema "{evento.get("tema","")}".
    """
    elementos.append(Paragraph(texto_objeto, styles["Normal"]))
    elementos.append(Spacer(1, 12))

    # Data e local
    texto_evento = f"""
    <b>DATA E LOCAL:</b><br/>
    {evento.get("data","")} às {evento.get("horario","")}<br/>
    {evento.get("endereco","")}
    """
    elementos.append(Paragraph(texto_evento, styles["Normal"]))
    elementos.append(Spacer(1, 12))

    # Valores
    texto_valor = f"""
    <b>VALOR:</b><br/>
    R$ {evento.get("valor_total","")}
    """
    elementos.append(Paragraph(texto_valor, styles["Normal"]))
    elementos.append(Spacer(1, 24))

    # Data final
    hoje = datetime.now().strftime("%d/%m/%Y")

    elementos.append(Paragraph(f"Brasília, {hoje}", styles["Normal"]))

    doc.build(elementos)

    return caminho_saida