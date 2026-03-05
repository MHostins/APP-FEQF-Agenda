import os
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

NOTES_FILE = "notes_store.json"

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

def rt_to_text(rich_text: List[Dict[str, Any]]) -> str:
    return "".join([x.get("plain_text", "") for x in (rich_text or [])]).strip()

def title_to_text(title: List[Dict[str, Any]]) -> str:
    return "".join([x.get("plain_text", "") for x in (title or [])]).strip()

def multi_select_to_text(ms: List[Dict[str, Any]]) -> str:
    names = [x.get("name", "") for x in (ms or []) if x.get("name")]
    return ", ".join(names).strip()

def safe_lower(s: str) -> str:
    return (s or "").lower().strip()

def classify_event(dt: datetime) -> str:
    """Retorna: today | tomorrow | week | future"""
    d = dt.date()
    today = date.today()
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

def parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    if not iso_str:
        return None

    try:
        # Se vier com hora e fuso (ex.: ...Z), vira aware
        if "T" in iso_str:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            # remove o fuso, deixando "naive" para comparar/ordenar sem erro
            return dt.replace(tzinfo=None)

        # Se vier só data (ex.: 2026-03-07), fica 00:00
        dt = datetime.fromisoformat(iso_str)
        return dt.replace(tzinfo=None)

    except Exception:
        return None
def format_dt_br(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")

# =========================
# Config
# =========================
st.set_page_config(
    page_title="Agenda FEQF",
    page_icon="🗓️",
    layout="wide"
)

# =========================
# Proteção simples por senha (com sessão)
# =========================
APP_PASSWORD = os.getenv("APP_PASSWORD") or st.secrets.get("APP_PASSWORD", None)

if "auth_ok" not in st.session_state:
    st.session_state["auth_ok"] = False

if APP_PASSWORD and not st.session_state["auth_ok"]:
    st.subheader("Acesso restrito")
    pwd = st.text_input("Chave de acesso", type="password", key="feqf_access_key", autocomplete="off")

    if st.button("Entrar"):
        if pwd == APP_PASSWORD:
            st.session_state["auth_ok"] = True
            st.success("Acesso liberado ✅")
            st.rerun()
        else:
            st.error("Senha incorreta. Tente novamente.")
    st.stop()

import os

logo_path = os.path.join("assets", "logo.png")

if os.path.exists(logo_path):
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(logo_path, width=140)
    with col_title:
        st.title("Agenda FEQF")
else:
    st.title("Agenda FEQF")

st.title("App Agenda FEQF")

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
    unsafe_allow_html=True
)

token = os.getenv("NOTION_TOKEN") or st.secrets.get("NOTION_TOKEN", None)
database_id = os.getenv("NOTION_DATABASE_ID") or st.secrets.get ("NOTION_DATABASE_ID", None)

if not token or not database_id:
    st.error("Faltou NOTION_TOKEN ou NOTION_DATABASE_ID no arquivo .env")
    st.stop()

headers = {
    "Authorization": f"Bearer {token}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# =========================
# 1) Descobrir o campo de Data (tipo date) pela estrutura da database
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
for prop_name, prop_info in db_props.items():
    if (prop_info or {}).get("type") == "date":
        date_prop_name = prop_name
        break

if not date_prop_name:
    st.error("Não encontrei nenhum campo do tipo 'date' na sua database.")
    st.stop()

# Campos do seu app
PROP_TEMA = "tema"         # title
PROP_CLIENTE = "cliente"   # rich_text
PROP_PACOTE = "pacote"     # multi_select
PROP_ENDERECO = "detalhes" # rich_text (você usará como endereço)
PROP_QTD = "número de crianças"

st.caption(f"Campo de data detectado: **{date_prop_name}**")

# =========================
# 2) Buscar eventos do Notion já filtrando "hoje em diante" + paginação
# =========================
today_iso = date.today().isoformat()

query_url = f"https://api.notion.com/v1/databases/{database_id}/query"

def fetch_all_future_events(max_pages: int = 20) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    start_cursor = None
    pages = 0

    while True:
        payload = {
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

with st.spinner("Buscando eventos (hoje em diante) no Notion..."):
    try:
        raw_results = fetch_all_future_events()
    except Exception as e:
        st.error("Erro ao consultar o Notion ❌")
        st.write(str(e))
        st.stop()

st.success(f"{len(raw_results)} eventos futuros encontrados ✅")

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

    tema = title_to_text((props.get(PROP_TEMA, {}) or {}).get("title", []))
    cliente = rt_to_text((props.get(PROP_CLIENTE, {}) or {}).get("rich_text", []))
    pacote = multi_select_to_text((props.get(PROP_PACOTE, {}) or {}).get("multi_select", []))
    endereco = rt_to_text((props.get(PROP_ENDERECO, {}) or {}).get("rich_text", []))
    qtd = (props.get(PROP_QTD, {}) or {}).get("number")

    events.append({
        "id": page_id,
        "dt": dt_start,
        "data_str": format_dt_br(dt_start),
        "tema": tema,
        "qtd": qtd,
        "cliente": cliente,
        "pacote": pacote,
        "endereco": endereco,
        "raw": item,
        
    })

# Ordenação final (após a ordenação do Notion, refinamos aqui)
events.sort(key=lambda e: (
    e["dt"],
    safe_lower(e["tema"]),
    safe_lower(e["pacote"]),
    safe_lower(e["endereco"]),
    safe_lower(e["cliente"]),
))

# =========================
# Busca + visualização
# =========================
col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input("Busca (data, tema, cliente)", placeholder="Ex.: 10/03, casamento, Ana...")
with col2:
    view_mode = st.radio("Visualização", ["Lista", "Blocos horizontais"], horizontal=True)

base_list = events_future  # padrão

if search:
    base_list = events_all  # se pesquisar, inclui passados também

    s = safe_lower(search)
    base_list = [
        e for e in base_list
        if s in safe_lower(e["data_str"])
        or s in safe_lower(e["tema"])
        or s in safe_lower(e["cliente"])
        or s in safe_lower(e["pacote"])
        or s in safe_lower(e["endereco"])
    ]

events = base_list

    # =========================
# Painel-resumo (contagem por categoria)
# =========================
counts = {"today": 0, "tomorrow": 0, "week": 0, "future": 0}
for e in events:
    counts[classify_event(e["dt"])] += 1

# =========================
# Painel-resumo estilizado
# =========================
counts = {"today": 0, "tomorrow": 0, "week": 0, "future": 0}
for e in events:
    counts[classify_event(e["dt"])] += 1

col1, col2, col3, col4 = st.columns(4)

def summary_card(title, value, color):
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
        unsafe_allow_html=True
    )

with col1:
    summary_card("HOJE", counts["today"], "rgba(255,0,0,0.08)")
with col2:
    summary_card("AMANHÃ", counts["tomorrow"], "rgba(255,165,0,0.15)")
with col3:
    summary_card("PRÓX. 7 DIAS", counts["week"], "rgba(0,128,0,0.12)")
with col4:
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

if "selected_id" not in st.session_state:
    st.session_state["selected_id"] = None

def show_details(event: Dict[str, Any]) -> None:
    st.subheader("Detalhes do Evento")
    st.write(f"**Data/Hora:** {event['data_str']}")
    st.write(f"**Tema:** {event['tema'] or '-'}")
    st.write(f"**Cliente:** {event['cliente'] or '-'}")
    st.write(f"**Pacote:** {event['pacote'] or '-'}")
    st.write(f"**Endereço:** {event['endereco'] or '-'}")

    st.divider()
    st.subheader("Observações (salvas no seu computador)")
    current = notes.get(event["id"], "")
    obs = st.text_area("Digite suas observações", value=current, height=180)

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("💾 Salvar observações"):
            notes[event["id"]] = obs
            save_notes(notes)
            st.success("Observações salvas ✅")
    with b2:
        if st.button("⬅ Voltar"):
            st.session_state["selected_id"] = None
            st.rerun()

selected = st.session_state["selected_id"]
if selected:
    ev = next((x for x in events if x["id"] == selected), None)
    if ev:
        show_details(ev)
    else:
        st.warning("Evento não encontrado (talvez por causa da busca).")
        if st.button("⬅ Voltar"):
            st.session_state["selected_id"] = None
            st.rerun()
    st.stop()

# =========================
# Render
# =========================
if not events:
    st.info("Nenhum evento futuro para exibir com o filtro/busca atual.")
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
                  <div class="event-meta muted"><b>Pacote:</b> {e["pacote"] or "-"} &nbsp;|&nbsp; <b>Endereço:</b> {e["endereco"] or "-"}</div>
                  <div class="event-meta muted"><b>Qtd:</b> {e["qtd"] if e["qtd"] is not None else "-"} &nbsp;|&nbsp; <b>Pacote:</b> {e["pacote"] or "-"} &nbsp;|&nbsp; <b>Endereço:</b> {e["endereco"] or "-"}</div>
                  st.write(f"**Quantidade (crianças):** {event['qtd'] if event['qtd'] is not None else '-'}")
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Botão sempre visível (ótimo no celular)
        if st.button("🔎 Ver detalhes", key=f"ver_{e['id']}"):
            st.session_state["selected_id"] = e["id"]
            st.rerun()
            
    with right:
        st.write("")  # dá um respiro
        if st.button("🔎 Ver", key=f"ver_{e['id']}"):
            st.session_state["selected_id"] = e["id"]
            st.rerun()

else:
    # Blocos horizontais (linha “agenda”)
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
                          <div class="event-meta muted"><b>Pacote:</b> {e["pacote"] or "-"}</div>
                          <div class="event-meta muted"><b>Endereço:</b> {e["endereco"] or "-"}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        with c2:
            if st.button("Ver", key=f"ver_card_{e['id']}"):
                st.session_state["selected_id"] = e["id"]
                st.rerun()