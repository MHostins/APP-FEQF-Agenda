import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

load_dotenv()

NOTIFIED_FILE = "notified_events.json"
BR_TZ = ZoneInfo("America/Sao_Paulo")


def load_notified_ids(filepath: str = NOTIFIED_FILE) -> List[str]:
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data]
            if isinstance(data, dict):
                return [str(x) for x in data.get("notified_ids", [])]
    except Exception:
        pass
    return []


def save_notified_ids(ids: List[str], filepath: str = NOTIFIED_FILE) -> None:
    # Mantem ordem unica
    seen = set()
    unique_ids = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            unique_ids.append(x)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "notified_ids": unique_ids,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


DEFAULT_CONFIG = {
    "GREENAPI_ID_INSTANCE": "710722812475",
    "GREENAPI_API_TOKEN": "ee7187ad6cae48998e4aa7370af31a328c7d1e6700af4b83ac",
    "GREENAPI_CHAT_IDS": "120363024209992567@g.us",
}


def get_config_value(key: str) -> str:
    val = os.getenv(key, "")
    if val:
        return str(val).strip()
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return DEFAULT_CONFIG.get(key, "")


def normalize_greenapi_chat_id(raw_target: str) -> str:
    target = raw_target.strip()
    if not target:
        return ""
    if "@c.us" in target or "@g.us" in target:
        return target
    # Remove +, espacos, tracos, parenteses
    digits = "".join(ch for ch in target if ch.isdigit())
    if not digits:
        return ""
    # Se o usuario digitou apenas DDD + numero (10 ou 11 digitos), adiciona 55 do Brasil
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    return f"{digits}@c.us"


def formatar_mensagem_evento(event: Dict[str, Any], app_url: str = "") -> str:
    data_str = event.get("data_str") or "-"
    tema = event.get("tema") or "-"
    cliente = event.get("cliente") or "-"
    qtd = event.get("qtd")
    qtd_str = f"{int(qtd)} crianças" if qtd is not None and str(qtd) != "" else "-"
    pacote = event.get("pacote") or "-"
    endereco = event.get("endereco") or "-"
    responsavel = event.get("responsavel") or ""
    observacao = event.get("observacoes_notion") or event.get("observacao") or ""

    linhas = [
        "🎉 *NOVO EVENTO CADASTRADO - FEQF*",
        "",
        f"📅 *Data/Hora:* {data_str}",
        f"🎨 *Tema:* {tema}",
        f"👤 *Cliente:* {cliente}",
        f"🧒 *Qtd:* {qtd_str}",
        f"📦 *Pacote:* {pacote}",
        f"📍 *Endereço:* {endereco}",
    ]

    if responsavel:
        linhas.append(f"👩‍🎨 *Responsável:* {responsavel}")
    if observacao:
        linhas.append(f"📝 *Obs:* {observacao}")
    if app_url:
        linhas.extend(["", f"🔗 *Agenda:* {app_url}"])

    return "\n".join(linhas)


def enviar_via_greenapi(mensagem: str) -> List[Tuple[str, bool, str]]:
    id_instance = get_config_value("GREENAPI_ID_INSTANCE")
    api_token = get_config_value("GREENAPI_API_TOKEN")
    raw_chats = get_config_value("GREENAPI_CHAT_IDS")

    if not (id_instance and api_token and raw_chats):
        return []

    resultados: List[Tuple[str, bool, str]] = []
    api_host = get_config_value("GREENAPI_API_URL") or f"https://{id_instance[:4]}.api.greenapi.com"
    api_host = api_host.rstrip("/")
    url = f"{api_host}/waInstance{id_instance}/sendMessage/{api_token}"

    for item in raw_chats.split(","):
        chat_id = normalize_greenapi_chat_id(item)
        if not chat_id:
            continue
        try:
            resp = requests.post(
                url,
                json={"chatId": chat_id, "message": mensagem},
                timeout=20,
            )
            if resp.status_code == 200:
                resultados.append((f"GreenAPI ({chat_id})", True, "Enviado com sucesso"))
            else:
                resultados.append(
                    (f"GreenAPI ({chat_id})", False, f"HTTP {resp.status_code}: {resp.text}")
                )
        except Exception as e:
            resultados.append((f"GreenAPI ({chat_id})", False, str(e)))

    return resultados


def enviar_via_callmebot(mensagem: str) -> List[Tuple[str, bool, str]]:
    """
    Formato de CALLMEBOT_RECIPIENTS:
    5561999999999:123456,5561888888888:654321
    """
    raw_recipients = get_config_value("CALLMEBOT_RECIPIENTS")
    if not raw_recipients:
        return []

    resultados: List[Tuple[str, bool, str]] = []
    texto_encoded = quote_plus(mensagem)

    for par in raw_recipients.split(","):
        par = par.strip()
        if ":" not in par:
            continue
        phone, apikey = par.split(":", 1)
        phone_digits = "".join(ch for ch in phone if ch.isdigit())
        apikey = apikey.strip()
        if not phone_digits or not apikey:
            continue

        url = (
            f"https://api.callmebot.com/whatsapp.php"
            f"?phone={phone_digits}&apikey={apikey}&text={texto_encoded}"
        )
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200 and "error" not in resp.text.lower():
                resultados.append((f"CallMeBot ({phone_digits})", True, "Enviado com sucesso"))
            else:
                resultados.append(
                    (f"CallMeBot ({phone_digits})", False, f"HTTP {resp.status_code}: {resp.text[:200]}")
                )
        except Exception as e:
            resultados.append((f"CallMeBot ({phone_digits})", False, str(e)))

    return resultados


def whatsapp_configurado() -> bool:
    has_green = bool(
        get_config_value("GREENAPI_ID_INSTANCE")
        and get_config_value("GREENAPI_API_TOKEN")
        and get_config_value("GREENAPI_CHAT_IDS")
    )
    has_callmebot = bool(get_config_value("CALLMEBOT_RECIPIENTS"))
    return has_green or has_callmebot


def enviar_notificacao_whatsapp(mensagem: str) -> Tuple[bool, List[Tuple[str, bool, str]]]:
    resultados: List[Tuple[str, bool, str]] = []
    resultados.extend(enviar_via_greenapi(mensagem))
    resultados.extend(enviar_via_callmebot(mensagem))

    if not resultados:
        return False, [("Configuração", False, "Nenhum destinatário WhatsApp configurado (Green-API ou CallMeBot).")]

    sucesso = any(ok for _, ok, _ in resultados)
    return sucesso, resultados


def notificar_evento_whatsapp(event: Dict[str, Any], registrar_id: bool = True) -> Tuple[bool, List[Tuple[str, bool, str]]]:
    app_url = get_config_value("APP_URL")
    msg = formatar_mensagem_evento(event, app_url=app_url)
    ok, resultados = enviar_notificacao_whatsapp(msg)

    if ok and registrar_id and event.get("id"):
        ids = load_notified_ids()
        if event["id"] not in ids:
            ids.append(event["id"])
            save_notified_ids(ids)

    return ok, resultados


# =========================
# Monitor automatico do Notion
# =========================
def _rt_to_text(rich_text: List[Dict[str, Any]]) -> str:
    return "".join([x.get("plain_text", "") for x in (rich_text or [])]).strip()


def _parse_iso(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_prop_text(props: Dict[str, Any], prop_name: str, db_props: Dict[str, Any]) -> str:
    if prop_name not in props or prop_name not in db_props:
        return ""
    ptype = (db_props.get(prop_name) or {}).get("type")
    pval = props.get(prop_name) or {}

    if ptype == "title":
        return _rt_to_text(pval.get("title", []))
    if ptype == "rich_text":
        return _rt_to_text(pval.get("rich_text", []))
    if ptype == "select":
        return (pval.get("select") or {}).get("name", "") or ""
    if ptype == "multi_select":
        names = [x.get("name", "") for x in (pval.get("multi_select") or []) if x.get("name")]
        return ", ".join(names).strip()
    if ptype == "phone_number":
        return pval.get("phone_number", "") or ""
    if ptype == "number":
        v = pval.get("number")
        return "" if v is None else str(v)
    return ""


def fetch_all_notion_pages(token: str, database_id: str) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    db_resp = requests.get(f"https://api.notion.com/v1/databases/{database_id}", headers=headers, timeout=20)
    db_resp.raise_for_status()
    db_props = db_resp.json().get("properties", {})

    date_prop_name = None
    for pname, pinfo in db_props.items():
        if (pinfo or {}).get("type") == "date":
            date_prop_name = pname
            break

    if not date_prop_name:
        raise RuntimeError("Campo de data não encontrado na database do Notion.")

    results: List[Dict[str, Any]] = []
    start_cursor = None
    query_url = f"https://api.notion.com/v1/databases/{database_id}/query"

    while True:
        payload: Dict[str, Any] = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        resp = requests.post(query_url, headers=headers, json=payload, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")

    return db_props, date_prop_name, results


def verificar_e_notificar_novos_eventos(min_age_minutes: float = 2.0, seed_only: bool = False) -> int:
    token = get_config_value("NOTION_TOKEN")
    database_id = get_config_value("NOTION_DATABASE_ID")

    if not token or not database_id:
        raise RuntimeError("NOTION_TOKEN ou NOTION_DATABASE_ID não configurados.")

    db_props, date_prop_name, pages = fetch_all_notion_pages(token, database_id)
    notified_ids = load_notified_ids()
    notified_set = set(notified_ids)

    if seed_only:
        for item in pages:
            pid = item.get("id")
            if pid and pid not in notified_set:
                notified_ids.append(pid)
                notified_set.add(pid)
        save_notified_ids(notified_ids)
        print(f"Base inicial sincronizada com {len(notified_ids)} eventos existentes.")
        return 0

    prop_endereco = "endereço" if "endereço" in db_props else "detalhes"
    prop_obs = "observações" if "observações" in db_props else "observacoes"
    now_utc = datetime.now(timezone.utc)
    enviados = 0

    for item in pages:
        page_id = item.get("id", "")
        if not page_id or page_id in notified_set:
            continue

        props = item.get("properties", {})
        date_info = (props.get(date_prop_name, {}) or {}).get("date")
        start_iso = (date_info or {}).get("start")
        dt_start = _parse_iso(start_iso)
        if not dt_start:
            # Ainda sem data preenchida no Notion
            continue

        if dt_start.tzinfo:
            dt_local = dt_start.astimezone(BR_TZ).replace(tzinfo=None)
        else:
            dt_local = dt_start

        tema = _extract_prop_text(props, "tema", db_props)
        cliente = _extract_prop_text(props, "cliente", db_props)

        # So notifica quando pelo menos Tema ou Cliente estiver preenchido (evita linha recem-criada em branco)
        if not tema and not cliente:
            continue

        # Aguarda min_age_minutes desde a ultima edicao no Notion para a pessoa terminar de preencher a linha
        last_edited = _parse_iso(item.get("last_edited_time"))
        if last_edited and min_age_minutes > 0:
            age_minutes = (now_utc - last_edited).total_seconds() / 60.0
            if age_minutes < min_age_minutes:
                print(
                    f"Evento '{tema or cliente}' ({page_id}) editado há {age_minutes:.1f} min; "
                    f"aguardando finalizar preenchimento ({min_age_minutes} min)."
                )
                continue

        qtd = (props.get("número de crianças", {}) or {}).get("number")
        pacote = _extract_prop_text(props, "pacote", db_props)
        endereco = _extract_prop_text(props, prop_endereco, db_props)
        responsavel = _extract_prop_text(props, "responsavel", db_props)
        obs_notion = _extract_prop_text(props, prop_obs, db_props)

        event_dict = {
            "id": page_id,
            "data_str": dt_local.strftime("%d/%m/%Y %H:%M"),
            "tema": tema,
            "cliente": cliente,
            "qtd": qtd,
            "pacote": pacote,
            "endereco": endereco,
            "responsavel": responsavel,
            "observacoes_notion": obs_notion,
        }

        ok, resultados = notificar_evento_whatsapp(event_dict, registrar_id=False)
        for destino, status, detalhe in resultados:
            print(f"[{page_id}] {destino}: {'OK' if status else 'ERRO'} - {detalhe}")

        if ok:
            notified_ids.append(page_id)
            notified_set.add(page_id)
            enviados += 1

    if enviados > 0:
        save_notified_ids(notified_ids)

    print(f"Verificação concluída. Novos eventos notificados: {enviados}")
    return enviados


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor de novos eventos do Notion para WhatsApp")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Apenas marca todos os eventos atuais do Notion como já notificados (sem enviar mensagens).",
    )
    parser.add_argument(
        "--min-age-minutes",
        type=float,
        default=2.0,
        help="Tempo mínimo (em minutos) após a última edição no Notion antes de enviar o aviso.",
    )
    args = parser.parse_args()
    verificar_e_notificar_novos_eventos(min_age_minutes=args.min_age_minutes, seed_only=args.seed)
