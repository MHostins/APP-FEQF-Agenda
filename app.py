import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pytz
import requests
import streamlit as st
from dotenv import load_dotenv

from gerador_excel import gerar_excel
from contrato_pdf import gerar_pdf_contrato

load_dotenv()

NOTES_FILE = "notes_store.json"
BR_TZ = ZoneInfo("America/Sao_Paulo")


# =========================
# Config inicial
# =========================
st.set_page_config(
    page_title="Agenda FEQF",
    page_icon="🗓️",
    layout="wide",
)

fuso = pytz.timezone("America/Sao_Paulo")
agora = datetime.now(fuso)

st.sidebar.write("Horário do sistema:")
st.sidebar.write(agora.strftime("%d/%m/%Y %H:%M:%S"))


# =========================
# Utils (notes)
# =========================
def load_notes() -> Dict[str, str]:
    if not os.path.exists(NOTES_FILE):
        return {}
    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_notes(notes: Dict[str, str]) -> None:
    with open(NOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)


# =========================
# Utils (text / notion props)
# =========================
def rt_to_text(rich_text: List[Dict[str, Any]]) -> str:
    return "".join([x.get("plain_text", "") for x in (rich_text or [])]).strip()


def title_to_text(title: List[Dict[str, Any]]) -> str:
    return "".join([x.get("plain_text", "") for x in (title or [])]).strip()


def multi_select_to_text(ms: List[Dict[str, Any]]) -> str:
    names = [x.get("name", "") for x in (ms or []) if x.get("name")]
    return ", ".join(names).strip()


def safe_lower(s: str) -> str:
    return (s or "").lower().strip()


def parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.astimezone(BR_TZ).replace(tzinfo=None)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def format_dt_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


def classify_event(dt: datetime) -> str:
    d = dt.date()
    today = datetime.now(BR_TZ).date()
    delta = (d - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if 2 <= delta <= 7:
        return "week"
    return "future"


def badge_html(kind: str) -> str:
    if kind == "today":
        return '<span class="event-badge b-today">HOJE</span>'
    if kind == "tomorrow":
        return '<span class="event-badge b-tomorrow">AMANHÃ</span>'
    if kind == "week":
        return '<span class="event-badge b-week">PRÓX. 7 DIAS</span>'
    return '<span class="event-badge b-future">FUTURO</span>'


def bar_color(kind: str) -> str:
    if kind == "today":
        return "background: rgba(255,0,0,0.75);"
    if kind == "tomorrow":
        return "background: rgba(255,165,0,0.85);"
    if kind == "week":
        return "background: rgba(0,128,0,0.70);"
    return "background: rgba(0,0,0,0.22);"


def get_prop_type(prop_name: str, db_props: Dict[str, Any]) -> Optional[str]:
    prop = db_props.get(prop_name, {})
    return prop.get("type")


def get_prop_text(props: Dict[str, Any], prop_name: str, db_props: Dict[str, Any]) -> str:
    if prop_name not in props or prop_name not in db_props:
        return ""

    prop_type = get_prop_type(prop_name, db_props)
    prop_value = props.get(prop_name, {}) or {}

    if prop_type == "title":
        return title_to_text(prop_value.get("title", []))
    if prop_type == "rich_text":
        return rt_to_text(prop_value.get("rich_text", []))
    if prop_type == "select":
        return (prop_value.get("select") or {}).get("name", "") or ""
    if prop_type == "multi_select":
        return multi_select_to_text(prop_value.get("multi_select", []))
    if prop_type == "phone_number":
        return prop_value.get("phone_number", "") or ""
    if prop_type == "number":
        value = prop_value.get("number")
        return "" if value is None else str(value)

    return ""


def get_prop_number(props: Dict[str, Any], prop_name: str) -> Optional[float]:
    if prop_name not in props:
        return None
    return (props.get(prop_name, {}) or {}).get("number")


def split_pacotes(texto: str) -> List[str]:
    itens = [x.strip() for x in (texto or "").split(",")]
    return [x for x in itens if x]


def build_property_value(
    prop_name: str,
    value: Any,
    db_props: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if prop_name not in db_props:
        return None

    prop_type = get_prop_type(prop_name, db_props)

    if prop_type == "title":
        return {"title": [{"text": {"content": str(value or "")}}]}

    if prop_type == "rich_text":
        return {"rich_text": [{"text": {"content": str(value or "")}}]}

    if prop_type == "number":
        if value in ("", None):
            return {"number": None}
        return {"number": float(value)}

    if prop_type == "select":
        if not value:
            return {"select": None}
        return {"select": {"name": str(value)}}

    if prop_type == "multi_select":
        nomes = split_pacotes(value) if isinstance(value, str) else value
        return {"multi_select": [{"name": str(x)} for x in nomes if str(x).strip()]}

    if prop_type == "phone_number":
        return {"phone_number": str(value or "")}

    if prop_type == "date":
        if not value:
            return {"date": None}
        return {"date": {"start": value}}

    return None


# =========================
# Utils (excel)
# =========================
def format_money(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def sanitize_filename(texto: str) -> str:
    texto = (texto or "").strip()
    if not texto:
        return "evento"
    proibidos = '\\/:*?"<>|'
    for ch in proibidos:
        texto = texto.replace(ch, "_")
    texto = texto.replace(" ", "_")
    return texto


def montar_evento_para_excel(event: Dict[str, Any], observacao: str) -> Dict[str, str]:
    qtd = ""
    if event.get("qtd") is not None:
        qtd = f"{int(event['qtd'])} crianças"

    return {
        "quantidade": qtd,
        "data_horario": event.get("data_str", ""),
        "endereco": event.get("endereco", "") or "",
        "tema": event.get("tema", "") or "",
        "cliente": event.get("cliente", "") or "",
        "pacote": event.get("pacote", "") or "",
        "observacao": observacao or "",
        "total": format_money(event.get("total")),
    }


def montar_evento_para_contrato(event: Dict[str, Any], observacao: str) -> Dict[str, Any]:
    data_iso = event.get("dt").strftime("%Y-%m-%d") if event.get("dt") else ""
    horario = event.get("dt").strftime("%Hh%M") if event.get("dt") else ""

    return {
        "cliente": event.get("cliente", "") or "",
        "cpf": "",
        "telefone": event.get("telefone", "") or "",
        "data": data_iso,
        "horario": horario,
        "tema": event.get("tema", "") or "",
        "quantidade_criancas": int(event["qtd"]) if event.get("qtd") is not None else "",
        "pacote": event.get("pacote", "") or "",
        "valor_total": event.get("total") or 0,
        "valor_pago": event.get("valor_pago") or 0,
        "endereco": event.get("endereco", "") or "",
        "responsavel": event.get("responsavel", "") or "",
        "observacao": observacao or "",
    }



# =========================
# Senhas / acesso
# =========================
APP_PASSWORD = os.getenv("APP_PASSWORD") or st.secrets.get("APP_PASSWORD", None)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or st.secrets.get("ADMIN_PASSWORD", None)

if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False

if "selected_id" not in st.session_state:
    st.session_state["selected_id"] = None

if "editing_id" not in st.session_state:
    st.session_state["editing_id"] = None


# =========================
# Logo + título
# =========================
logo_path = os.path.join("assets", "logo.png")

if os.path.exists(logo_path):
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(logo_path, width=140)
    with col_title:
        st.title("Agenda FEQF")
else:
    st.title("Agenda FEQF")


# =========================
# Área administrativa
# =========================
with st.expander("Área administrativa"):
    pwd = st.text_input("Senha admin", type="password", key="admin_pwd")

    col_admin1, col_admin2 = st.columns(2)

    with col_admin1:
        if st.button("Entrar como admin", key="btn_admin_login"):
            if ADMIN_PASSWORD and pwd == ADMIN_PASSWORD:
                st.session_state["is_admin"] = True
                st.success("Modo administrador ativado")
                st.rerun()
            else:
                st.error("Senha incorreta")

    with col_admin2:
        if st.session_state["is_admin"]:
            if st.button("Sair do modo admin", key="btn_admin_logout"):
                st.session_state["is_admin"] = False
                st.session_state["editing_id"] = None
                st.rerun()

if st.session_state["is_admin"]:
    st.success("Administrador conectado")


# =========================
# CSS
# =========================
st.markdown(
    """
    <style>
      .event-card {
        border-radius: 14px;
        padding: 14px 14px 10px 14px;
        margin: 10px 0;
        background: #ffffff;
        border: 1px solid rgba(0,0,0,0.08);
        box-shadow: 0 1px 6px rgba(0,0,0,0.06);
      }
      .event-row {
        display: flex;
        gap: 14px;
        align-items: flex-start;
        justify-content: space-between;
      }
      .event-left {
        flex: 1;
        min-width: 0;
      }
      .event-title {
        font-size: 18px;
        font-weight: 700;
        margin: 0 0 6px 0;
        line-height: 1.2;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .event-meta {
        font-size: 14px;
        opacity: 0.9;
        margin: 2px 0;
      }
      .event-badge {
        display: inline-block;
        font-size: 12px;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 999px;
        margin-left: 8px;
        border: 1px solid rgba(0,0,0,0.10);
        background: rgba(0,0,0,0.03);
      }
      .b-today { background: rgba(255,0,0,0.08); border-color: rgba(255,0,0,0.18); }
      .b-tomorrow { background: rgba(255,165,0,0.12); border-color: rgba(255,165,0,0.22); }
      .b-week { background: rgba(0,128,0,0.10); border-color: rgba(0,128,0,0.20); }
      .b-future { background: rgba(0,0,0,0.03); border-color: rgba(0,0,0,0.10); }

      .bar {
        width: 7px;
        border-radius: 999px;
        margin-right: 12px;
      }
      .wrap {
        display: flex;
        align-items: stretch;
      }
      .muted { opacity: 0.75; }
      .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================
# Token / database
# =========================
token = os.getenv("NOTION_TOKEN") or st.secrets.get("NOTION_TOKEN", None)
database_id = os.getenv("NOTION_DATABASE_ID") or st.secrets.get("NOTION_DATABASE_ID", None)

if not token or not database_id:
    st.error("Faltou NOTION_TOKEN ou NOTION_DATABASE_ID no arquivo .env / secrets.")
    st.stop()

headers = {
    "Authorization": f"Bearer {token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


# =========================
# Ler estrutura da database
# =========================
db_url = f"https://api.notion.com/v1/databases/{database_id}"
db_resp = requests.get(db_url, headers=headers)

if db_resp.status_code != 200:
    st.error("Erro ao ler a estrutura da database no Notion ❌")
    st.write("Status:", db_resp.status_code)
    st.write(db_resp.text)
    st.stop()

db_info = db_resp.json()
db_props = db_info.get("properties", {})

date_prop_name = None
title_prop_name = None

for prop_name, prop_info in db_props.items():
    prop_type = (prop_info or {}).get("type")
    if prop_type == "date" and date_prop_name is None:
        date_prop_name = prop_name
    if prop_type == "title" and title_prop_name is None:
        title_prop_name = prop_name

if not date_prop_name:
    st.error("Não encontrei nenhum campo do tipo 'date' na sua database.")
    st.stop()

if not title_prop_name:
    st.error("Não encontrei nenhum campo do tipo 'title' na sua database.")
    st.stop()


# =========================
# Nomes dos campos no Notion
# =========================
PROP_DATA = date_prop_name
PROP_TEMA = "tema"
PROP_CLIENTE = "cliente"
PROP_QTD = "número de crianças"
PROP_PACOTE = "pacote"
PROP_ENDERECO = "detalhes"
PROP_TOTAL = "total"
PROP_VALOR_PAGO = "valor pago"
PROP_RESPONSAVEL = "responsavel"
PROP_TELEFONE = "telefone"

st.caption(f"Campo de data detectado: **{date_prop_name}**")
st.caption(f"Campo de título detectado: **{title_prop_name}**")


# =========================
# Cadastro de novo evento
# =========================
if st.session_state["is_admin"]:
    st.subheader("Cadastrar novo evento")

    responsavel_options = []
    if PROP_RESPONSAVEL in db_props and get_prop_type(PROP_RESPONSAVEL, db_props) == "select":
        responsavel_options = [
            opt.get("name", "")
            for opt in db_props[PROP_RESPONSAVEL].get("select", {}).get("options", [])
            if opt.get("name")
        ]

    with st.form("form_novo_evento", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            data_evento = st.date_input("Data")
        with col2:
            hora_evento = st.time_input("Horário")

        col3, col4 = st.columns(2)
        with col3:
            cliente = st.text_input("Nome do cliente")
        with col4:
            telefone = st.text_input("Telefone")

        tema = st.text_input("Tema")
        pacote = st.text_input("Pacote(s) — se houver mais de um, separar por vírgula")
        numero = st.number_input("Quantidade", min_value=0, step=1)

        detalhes = st.text_area("Endereço / detalhes", height=100)

        col5, col6, col7 = st.columns(3)
        with col5:
            total = st.number_input("Total", min_value=0.0, step=50.0, format="%.2f")
        with col6:
            valor_pago = st.number_input("Valor pago", min_value=0.0, step=50.0, format="%.2f")
        with col7:
            if responsavel_options:
                responsavel = st.selectbox("Responsável", [""] + responsavel_options)
            else:
                responsavel = st.text_input("Responsável")

        salvar = st.form_submit_button("Salvar evento no Notion")

        if salvar:
            if not cliente.strip():
                st.error("Preencha o nome do cliente.")
            else:
                dt_completa = datetime.combine(data_evento, hora_evento)
                data_iso = dt_completa.isoformat()

                propriedades: Dict[str, Any] = {}

                if title_prop_name == PROP_CLIENTE:
                    valor_titulo = cliente
                elif title_prop_name == PROP_TEMA:
                    valor_titulo = tema if tema.strip() else cliente
                else:
                    valor_titulo = cliente

                title_value = build_property_value(title_prop_name, valor_titulo, db_props)
                if title_value:
                    propriedades[title_prop_name] = title_value

                campos_para_salvar = {
                    PROP_DATA: data_iso,
                    PROP_TEMA: tema,
                    PROP_CLIENTE: cliente,
                    PROP_QTD: numero,
                    PROP_PACOTE: pacote,
                    PROP_ENDERECO: detalhes,
                    PROP_TOTAL: total,
                    PROP_VALOR_PAGO: valor_pago,
                    PROP_RESPONSAVEL: responsavel,
                    PROP_TELEFONE: telefone,
                }

                for campo, valor in campos_para_salvar.items():
                    if campo == title_prop_name:
                        continue
                    prop_value = build_property_value(campo, valor, db_props)
                    if prop_value is not None:
                        propriedades[campo] = prop_value

                create_url = "https://api.notion.com/v1/pages"
                payload = {
                    "parent": {"database_id": database_id},
                    "properties": propriedades,
                }

                resp = requests.post(create_url, headers=headers, json=payload)

                if resp.status_code == 200:
                    st.success("Evento salvo no Notion com sucesso ✅")
                    st.rerun()
                else:
                    st.error("Não foi possível salvar o evento no Notion.")
                    st.write("Status:", resp.status_code)
                    st.write(resp.text)

    st.divider()


# =========================
# Buscar eventos do Notion
# =========================
query_url = f"https://api.notion.com/v1/databases/{database_id}/query"


def fetch_all_events(max_pages: int = 50) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    start_cursor = None
    pages = 0

    while True:
        payload: Dict[str, Any] = {
            "page_size": 100,
            "sorts": [{"property": date_prop_name, "direction": "ascending"}],
        }
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(query_url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"{resp.status_code} - {resp.text}")

        data = resp.json()
        results.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        start_cursor = data.get("next_cursor")
        pages += 1
        if pages >= max_pages:
            break

    return results


with st.spinner("Buscando eventos no Notion..."):
    try:
        raw_results = fetch_all_events()
    except Exception as e:
        st.error("Erro ao consultar o Notion ❌")
        st.write(str(e))
        st.stop()

st.success(f"{len(raw_results)} eventos carregados ✅")


# =========================
# Transformar em lista limpa
# =========================
events: List[Dict[str, Any]] = []
for item in raw_results:
    props = item.get("properties", {})
    page_id = item.get("id", "")

    date_info = (props.get(date_prop_name, {}) or {}).get("date")
    start_iso = (date_info or {}).get("start")
    dt_start = parse_iso_datetime(start_iso) if start_iso else None
    if not dt_start:
        continue

    tema = get_prop_text(props, PROP_TEMA, db_props)
    cliente = get_prop_text(props, PROP_CLIENTE, db_props)
    pacote = get_prop_text(props, PROP_PACOTE, db_props)
    endereco = get_prop_text(props, PROP_ENDERECO, db_props)
    responsavel = get_prop_text(props, PROP_RESPONSAVEL, db_props)
    telefone = get_prop_text(props, PROP_TELEFONE, db_props)

    qtd = get_prop_number(props, PROP_QTD)
    total_evento = get_prop_number(props, PROP_TOTAL)
    valor_pago_evento = get_prop_number(props, PROP_VALOR_PAGO)

    events.append(
        {
            "id": page_id,
            "dt": dt_start,
            "data_str": format_dt_br(dt_start),
            "tema": tema,
            "qtd": qtd,
            "cliente": cliente,
            "pacote": pacote,
            "endereco": endereco,
            "responsavel": responsavel,
            "telefone": telefone,
            "total": total_evento,
            "valor_pago": valor_pago_evento,
            "raw": item,
        }
    )

events.sort(
    key=lambda e: (
        e["dt"],
        safe_lower(e["tema"]),
        safe_lower(e["pacote"]),
        safe_lower(e["endereco"]),
        safe_lower(e["cliente"]),
    )
)


# =========================
# Separação: todos vs futuros
# =========================
events_all = events[:]
today_local = datetime.now(BR_TZ).date()
events_future = [e for e in events_all if e.get("dt") and e["dt"].date() >= today_local]


# =========================
# Busca + visualização
# =========================
col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input(
        "Busca (data, tema, cliente)",
        placeholder="Ex.: 10/03, aniversário, Hanny...",
    )
with col2:
    view_mode = st.radio("Visualização", ["Lista", "Blocos horizontais"], horizontal=True)

base_list = events_future

if search:
    base_list = events_all
    s = safe_lower(search)
    base_list = [
        e
        for e in base_list
        if s in safe_lower(e["data_str"])
        or s in safe_lower(e["tema"])
        or s in safe_lower(e["cliente"])
        or s in safe_lower(e["pacote"])
        or s in safe_lower(e["endereco"])
        or s in safe_lower(e["responsavel"])
        or s in safe_lower(e["telefone"])
    ]

events = base_list


# =========================
# Painel-resumo
# =========================
counts = {"today": 0, "tomorrow": 0, "week": 0, "future": 0}
for e in events:
    counts[classify_event(e["dt"])] += 1

colA, colB, colC, colD = st.columns(4)


def summary_card(title: str, value: int, color: str) -> None:
    st.markdown(
        f"""
        <div style="
            border-radius:12px;
            padding:14px;
            background:{color};
            color:#000;
            text-align:center;
            font-weight:600;
        ">
            <div style="font-size:13px; opacity:0.7;">{title}</div>
            <div style="font-size:24px; margin-top:6px;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


with colA:
    summary_card("HOJE", counts["today"], "rgba(255,0,0,0.08)")
with colB:
    summary_card("AMANHÃ", counts["tomorrow"], "rgba(255,165,0,0.15)")
with colC:
    summary_card("PRÓX. 7 DIAS", counts["week"], "rgba(0,128,0,0.12)")
with colD:
    summary_card("FUTURO", counts["future"], "rgba(0,0,0,0.05)")

if counts["today"] > 0:
    st.warning(f"🔴 Você tem {counts['today']} evento(s) HOJE.")
elif counts["tomorrow"] > 0:
    st.info(f"🟠 Amanhã: {counts['tomorrow']} evento(s).")

st.divider()


# =========================
# Detalhes + Observações
# =========================
notes = load_notes()


def update_notion_event(page_id: str, campos: Dict[str, Any]) -> None:
    propriedades: Dict[str, Any] = {}

    for campo, valor in campos.items():
        prop_value = build_property_value(campo, valor, db_props)
        if prop_value is not None:
            propriedades[campo] = prop_value

    update_url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": propriedades}

    resp = requests.patch(update_url, headers=headers, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} - {resp.text}")


def show_details(event: Dict[str, Any]) -> None:
    st.subheader("Detalhes do Evento")

    is_admin = st.session_state.get("is_admin", False)
    editing_this_event = st.session_state.get("editing_id") == event["id"]

    if is_admin and not editing_this_event:
        col_edit, col_space = st.columns([1, 5])
        with col_edit:
            if st.button("✏️ Editar cadastro", key=f"editar_{event['id']}"):
                st.session_state["editing_id"] = event["id"]
                st.rerun()

    if is_admin and editing_this_event:
        st.info("Modo de edição")

        responsavel_options = []
        if PROP_RESPONSAVEL in db_props and get_prop_type(PROP_RESPONSAVEL, db_props) == "select":
            responsavel_options = [
                opt.get("name", "")
                for opt in db_props[PROP_RESPONSAVEL].get("select", {}).get("options", [])
                if opt.get("name")
            ]

        with st.form(f"form_edicao_{event['id']}"):
            st.write(f"**Data/Hora:** {event['data_str']}")

            tema_edit = st.text_input("Tema", value=event.get("tema", "") or "")
            cliente_edit = st.text_input("Cliente", value=event.get("cliente", "") or "")
            telefone_edit = st.text_input("Telefone", value=event.get("telefone", "") or "")
            pacote_edit = st.text_input("Pacote", value=event.get("pacote", "") or "")
            endereco_edit = st.text_area("Endereço", value=event.get("endereco", "") or "", height=100)

            if responsavel_options:
                indice_padrao = 0
                valor_atual = event.get("responsavel", "") or ""
                if valor_atual in responsavel_options:
                    indice_padrao = responsavel_options.index(valor_atual) + 1
                responsavel_edit = st.selectbox(
                    "Responsável",
                    [""] + responsavel_options,
                    index=indice_padrao,
                )
            else:
                responsavel_edit = st.text_input("Responsável", value=event.get("responsavel", "") or "")

            qtd_inicial = int(event["qtd"]) if event.get("qtd") is not None else 0
            qtd_edit = st.number_input("Quantidade", min_value=0, step=1, value=qtd_inicial)

            total_inicial = float(event["total"]) if event.get("total") is not None else 0.0
            valor_pago_inicial = float(event["valor_pago"]) if event.get("valor_pago") is not None else 0.0

            total_edit = st.number_input("Total", min_value=0.0, step=50.0, format="%.2f", value=total_inicial)
            valor_pago_edit = st.number_input("Valor pago", min_value=0.0, step=50.0, format="%.2f", value=valor_pago_inicial)

            c1, c2 = st.columns(2)
            with c1:
                salvar = st.form_submit_button("💾 Salvar alterações")
            with c2:
                cancelar = st.form_submit_button("Cancelar")

        if cancelar:
            st.session_state["editing_id"] = None
            st.rerun()

        if salvar:
            try:
                campos = {
                    PROP_TEMA: tema_edit,
                    PROP_CLIENTE: cliente_edit,
                    PROP_TELEFONE: telefone_edit,
                    PROP_PACOTE: pacote_edit,
                    PROP_ENDERECO: endereco_edit,
                    PROP_RESPONSAVEL: responsavel_edit,
                    PROP_QTD: qtd_edit,
                    PROP_TOTAL: total_edit,
                    PROP_VALOR_PAGO: valor_pago_edit,
                }

                update_notion_event(event["id"], campos)

                st.success("Cadastro atualizado com sucesso ✅")
                st.session_state["editing_id"] = None
                st.rerun()
            except Exception as e:
                st.error("Erro ao atualizar o evento no Notion.")
                st.write(str(e))

        st.divider()

    st.write(f"**Data/Hora:** {event['data_str']}")
    st.write(f"**Tema:** {event['tema'] or '-'}")
    st.write(f"**Cliente:** {event['cliente'] or '-'}")
    st.write(f"**Telefone:** {event['telefone'] or '-'}")
    st.write(f"**Pacote:** {event['pacote'] or '-'}")
    st.write(f"**Endereço:** {event['endereco'] or '-'}")
    st.write(f"**Responsável:** {event['responsavel'] or '-'}")
    st.write(f"**Quantidade:** {int(event['qtd']) if event['qtd'] is not None else '-'}")

    if is_admin:
        st.write(f"**Total:** {format_money(event['total'])}")
        st.write(f"**Valor pago:** {format_money(event['valor_pago'])}")

        if event["total"] is not None and event["valor_pago"] is not None:
            saldo = event["total"] - event["valor_pago"]
            st.write(f"**Saldo pendente:** {format_money(saldo)}")

    st.divider()
    st.subheader("Observações (salvas no seu computador)")
    current = notes.get(event["id"], "")
    obs = st.text_area(
        "Digite suas observações",
        value=current,
        height=180,
        key=f"obs_{event['id']}"
    )

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("💾 Salvar observações", key=f"salvar_obs_{event['id']}"):
            notes[event["id"]] = obs
            save_notes(notes)
            st.success("Observações salvas ✅")
    with b2:
        if st.button("⬅ Voltar", key=f"voltar_{event['id']}"):
            st.session_state["selected_id"] = None
            st.session_state["editing_id"] = None
            st.rerun()

    if is_admin:
        st.divider()
        st.subheader("Ficha do evento em Excel")

        observacao_excel = notes.get(event["id"], obs)
        evento_excel = montar_evento_para_excel(event, observacao_excel)

        nome_cliente = sanitize_filename(event.get("cliente", "cliente"))
        data_arquivo = event["dt"].strftime("%Y-%m-%d")
        nome_arquivo = f"ficha_evento_{data_arquivo}_{nome_cliente}.xlsx"

        if st.button("📄 Gerar ficha do evento", key=f"gerar_excel_{event['id']}"):
            try:
                caminho_arquivo = gerar_excel(evento_excel, nome_arquivo=nome_arquivo)
                st.session_state[f"excel_path_{event['id']}"] = caminho_arquivo
                st.success("Ficha gerada com sucesso ✅")
            except Exception as e:
                st.error("Erro ao gerar a ficha Excel.")
                st.write(str(e))

        caminho_salvo = st.session_state.get(f"excel_path_{event['id']}")

        if caminho_salvo and os.path.exists(caminho_salvo):
            with open(caminho_salvo, "rb") as f:
                st.download_button(
                    label="⬇️ Baixar ficha em Excel",
                    data=f.read(),
                    file_name=os.path.basename(caminho_salvo),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_excel_{event['id']}",
                )


        st.divider()
        st.subheader("Contrato em PDF")

        observacao_contrato = notes.get(event["id"], obs)
        evento_contrato = montar_evento_para_contrato(event, observacao_contrato)

        nome_cliente_pdf = sanitize_filename(event.get("cliente", "cliente"))
        data_pdf = event["dt"].strftime("%d-%m-%Y") if event.get("dt") else "sem-data"
        nome_pdf = f"Contrato_{data_pdf}_{nome_cliente_pdf}.pdf"

        pasta_contratos = "contratos"
        if not os.path.exists(pasta_contratos):
            os.makedirs(pasta_contratos)

        caminho_pdf = os.path.join(pasta_contratos, nome_pdf)

        if st.button("📄 Gerar contrato", key=f"gerar_contrato_{event['id']}"):
            try:
                gerar_pdf_contrato(evento_contrato, caminho_pdf)
                st.session_state[f"pdf_path_{event['id']}"] = caminho_pdf
                st.success("Contrato gerado com sucesso ✅")
            except Exception as e:
                st.error("Erro ao gerar o contrato em PDF.")
                st.write(str(e))

        caminho_pdf_salvo = st.session_state.get(f"pdf_path_{event['id']}")

        if caminho_pdf_salvo and os.path.exists(caminho_pdf_salvo):
            with open(caminho_pdf_salvo, "rb") as f:
                st.download_button(
                    label="⬇️ Baixar contrato em PDF",
                    data=f.read(),
                    file_name=os.path.basename(caminho_pdf_salvo),
                    mime="application/pdf",
                    key=f"download_pdf_{event['id']}",
                )


selected = st.session_state["selected_id"]
if selected:
    ev = next((x for x in events_all if x["id"] == selected), None)
    if ev:
        show_details(ev)
    else:
        st.warning("Evento não encontrado.")
        if st.button("⬅ Voltar", key="voltar_evento_nao_encontrado"):
            st.session_state["selected_id"] = None
            st.session_state["editing_id"] = None
            st.rerun()
    st.stop()


# =========================
# Render
# =========================
if not events:
    st.info("Nenhum evento para exibir com o filtro/busca atual.")
    st.stop()

if view_mode == "Lista":
    for e in events:
        kind = classify_event(e["dt"])
        badge = badge_html(kind)
        bar = bar_color(kind)

        st.markdown(
            f"""
            <div class="event-card">
              <div class="wrap">
                <div class="bar" style="{bar}"></div>
                <div class="event-left">
                  <div class="event-title">
                    <span class="mono">{e["data_str"]}</span>
                    {badge}
                  </div>
                  <div class="event-meta"><b>Tema:</b> {e["tema"] or "-"}</div>
                  <div class="event-meta"><b>Cliente:</b> {e["cliente"] or "-"}</div>
                  <div class="event-meta muted"><b>Qtd:</b> {int(e["qtd"]) if e["qtd"] is not None else "-"} &nbsp;|&nbsp; <b>Pacote:</b> {e["pacote"] or "-"} &nbsp;|&nbsp; <b>Endereço:</b> {e["endereco"] or "-"}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🔎 Ver detalhes", key=f"ver_{e['id']}"):
            st.session_state["selected_id"] = e["id"]
            st.session_state["editing_id"] = None
            st.rerun()

else:
    for e in events:
        kind = classify_event(e["dt"])
        badge = badge_html(kind)
        bar = bar_color(kind)

        c1, c2 = st.columns([8, 1])
        with c1:
            st.markdown(
                f"""
                <div class="event-card">
                  <div class="wrap">
                    <div class="bar" style="{bar}"></div>
                    <div class="event-left">
                      <div class="event-title">
                        <span class="mono">{e["data_str"]}</span> {badge}
                      </div>
                      <div class="event-row">
                        <div class="event-left">
                          <div class="event-meta"><b>Tema:</b> {e["tema"] or "-"}</div>
                          <div class="event-meta"><b>Cliente:</b> {e["cliente"] or "-"}</div>
                          <div class="event-meta muted"><b>Qtd:</b> {int(e["qtd"]) if e["qtd"] is not None else "-"}</div>
                          <div class="event-meta muted"><b>Pacote:</b> {e["pacote"] or "-"}</div>
                          <div class="event-meta muted"><b>Endereço:</b> {e["endereco"] or "-"}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("Ver", key=f"ver_card_{e['id']}"):
                st.session_state["selected_id"] = e["id"]
                st.session_state["editing_id"] = None
                st.rerun()