from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from num2words import num2words
from weasyprint import HTML


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
ASSETS_DIR = BASE_DIR / "assets"


def formatar_data_br(data_str: str) -> str:
    """
    Converte data ISO (YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS) para DD/MM/YYYY.
    Se vier vazia ou inválida, devolve como está.
    """
    if not data_str:
        return ""

    try:
        return datetime.fromisoformat(str(data_str)).strftime("%d/%m/%Y")
    except ValueError:
        try:
            return datetime.fromisoformat(str(data_str).replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except ValueError:
            return str(data_str)


def formatar_moeda(valor: Any) -> str:
    """
    Converte número em formato brasileiro.
    Ex.: 3700 -> R$ 3.700,00
    """
    try:
        numero = float(valor or 0)
        texto = f"R$ {numero:,.2f}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "R$ 0,00"


def valor_por_extenso(valor: Any) -> str:
    """
    Converte valor numérico para extenso simples em português.
    Ex.: 3700 -> três mil e setecentos
    """
    try:
        numero = float(valor or 0)
        inteiro = int(numero)
        centavos = int(round((numero - inteiro) * 100))

        if centavos > 0:
            return f"{num2words(inteiro, lang='pt_BR')} reais e {num2words(centavos, lang='pt_BR')} centavos"

        return f"{num2words(inteiro, lang='pt_BR')} reais"
    except Exception:
        return ""


def montar_texto_valor(valor: Any) -> str:
    """
    Junta moeda formatada + valor por extenso.
    Ex.: R$ 3.700,00 (três mil e setecentos reais)
    """
    valor_formatado = formatar_moeda(valor)
    valor_extenso = valor_por_extenso(valor)

    if valor_extenso:
        return f"{valor_formatado} ({valor_extenso})"

    return valor_formatado


def montar_objeto_contrato(evento: dict[str, Any]) -> str:
    """
    Monta um texto mais natural e profissional para a cláusula OBJETO.
    """
    pacote = str(evento.get("pacote", "") or "").strip()
    quantidade = evento.get("quantidade_criancas", "")
    tema = str(evento.get("tema", "") or "").strip()

    texto = "Prestação de serviços de atividades recreativas"

    if pacote:
        texto += f", incluindo {pacote}"

    if quantidade not in ("", None):
        texto += f", para aproximadamente {quantidade} crianças"

    if tema:
        texto += f", conforme o tema \"{tema}\""

    if not texto.endswith("."):
        texto += "."

    return texto


def gerar_html_contrato(evento: dict[str, Any]) -> str:
    """
    Renderiza o HTML do contrato com os dados do evento.
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml"])
    )

    template = env.get_template("contrato.html")

    logo_path = (ASSETS_DIR / "logo.png").resolve().as_uri()
    valor_total = evento.get("valor_total")

    contexto = {
        "logo_path": logo_path,
        "cliente": evento.get("cliente", ""),
        "cpf": evento.get("cpf", ""),
        "telefone": evento.get("telefone", ""),
        "objeto_contrato": montar_objeto_contrato(evento),
        "valor_total_extenso_curto": montar_texto_valor(valor_total),
        "valor_pago": formatar_moeda(evento.get("valor_pago")) if evento.get("valor_pago") not in (None, "", 0, 0.0) else "",
        "endereco": evento.get("endereco", ""),
        "data_evento": formatar_data_br(evento.get("data", "")),
        "horario": evento.get("horario", ""),
        "observacao": evento.get("observacao", ""),
        "data_geracao": datetime.now().strftime("%d de %B de %Y"),
    }

    return template.render(**contexto)


def gerar_pdf_contrato(evento: dict[str, Any], caminho_saida: str | Path) -> Path:
    """
    Gera o PDF final do contrato.
    """
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    html_renderizado = gerar_html_contrato(evento)

    HTML(string=html_renderizado, base_url=str(BASE_DIR)).write_pdf(caminho_saida)

    return caminho_saida