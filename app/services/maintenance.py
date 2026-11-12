"""Manutenzione della piattaforma e avvisi agli utenti (12/11/2026).

La manutenzione è attiva se il Super Admin la accende a mano oppure durante la
finestra programmata (inizio/fine in ora italiana). La fine programmata la spegne
da sola; «Termina manutenzione» la spegne prima. Gli avvisi si leggono dal servizio
pubblico /api/public/status, che resta raggiungibile anche durante la manutenzione.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from .platform_settings import get_platform_setting, set_platform_setting, setting_bool

ROME = ZoneInfo("Europe/Rome")
REMIND_BEFORE = timedelta(minutes=30)
MESSAGE_MAX = 300
DAYS = ("lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica")
MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
          "settembre", "ottobre", "novembre", "dicembre")


def now_local() -> datetime:
    return datetime.now(ROME).replace(tzinfo=None, second=0, microsecond=0)


def parse_local(value) -> datetime | None:
    """«2026-11-12T22:00» in ora italiana; valori vuoti o non validi diventano None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ROME).replace(tzinfo=None)
    return parsed.replace(second=0, microsecond=0)


def _iso(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%dT%H:%M") if value else None


def _day_label(day: datetime, today: datetime) -> str:
    delta = (day.date() - today.date()).days
    if delta == 0:
        return "oggi"
    if delta == 1:
        return "domani"
    return f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"


def window_label(start: datetime, end: datetime | None, today: datetime) -> str:
    """«oggi dalle 22:00 alle 23:30», «domani dalle 22:00», «lunedì 16 novembre dalle 22:00 alle 01:00 di martedì»."""
    label = f"{_day_label(start, today)} dalle {start:%H:%M}"
    if end:
        label += f" alle {end:%H:%M}"
        if end.date() != start.date():
            label += f" di {_day_label(end, today)}"
    return label


def maintenance_state(db) -> dict:
    manual = setting_bool(db, "maintenance_mode")
    start = parse_local(get_platform_setting(db, "maintenance_start"))
    end = parse_local(get_platform_setting(db, "maintenance_end"))
    message = get_platform_setting(db, "maintenance_message")[:MESSAGE_MAX]
    notice_from = parse_local(get_platform_setting(db, "maintenance_notice_from"))
    now = now_local()
    if start and end and end <= start:
        end = None
    expired = bool(start and end and now >= end)
    scheduled_active = bool(start and not expired and start <= now)
    upcoming = bool(start and not expired and now < start)
    return {
        "active": manual or scheduled_active,
        "manual": manual,
        "scheduled_active": scheduled_active,
        "upcoming": upcoming,
        "start": _iso(start) if start and not expired else None,
        "end": _iso(end) if end and not expired else None,
        "message": message,
        "notice_from": _iso(notice_from) if start and not expired else None,
        "show_notice": upcoming and (notice_from is None or now >= notice_from),
        "now": _iso(now),
    }


def maintenance_active(db) -> bool:
    return maintenance_state(db)["active"]


def _notice_id(*parts) -> str:
    return hashlib.sha256("|".join(str(p or "") for p in parts).encode()).hexdigest()[:16]


def public_status(db) -> dict:
    """Quello che ogni pagina mostra: pagina di manutenzione o avvisi. Nessun dato riservato."""
    state = maintenance_state(db)
    now = parse_local(state["now"])
    notices = []
    start = parse_local(state["start"])
    end = parse_local(state["end"])
    if state["show_notice"] and start:
        when = window_label(start, end, now)
        text = f"{when[0].upper()}{when[1:]} GiroFacile non sarà utilizzabile fino alla fine dei lavori."
        if state["message"]:
            text += " " + state["message"]
        notices.append({"id": _notice_id("maintenance", state["start"], state["end"], state["message"]),
                        "kind": "maintenance", "title": "Manutenzione programmata", "text": text,
                        "starts_at": state["start"], "remind_at": _iso(start - REMIND_BEFORE)})
    if setting_bool(db, "platform_notice_enabled"):
        text = get_platform_setting(db, "platform_notice_text")[:MESSAGE_MAX]
        if text:
            notices.append({"id": _notice_id("info", text), "kind": "info", "title": "Avviso", "text": text,
                            "starts_at": None, "remind_at": None})
    maintenance = None
    if state["active"]:
        until = parse_local(state["end"]) if state["scheduled_active"] or state["end"] else None
        maintenance = {"until": _iso(until),
                       "until_label": f"{_day_label(until, now)} alle {until:%H:%M}" if until else None,
                       "message": state["message"]}
    return {"maintenance": maintenance, "notices": notices}


def admin_settings(db) -> dict:
    from ..models import RoutePlan
    state = maintenance_state(db)
    running = db.query(RoutePlan).filter(RoutePlan.status == "in_corso").count()
    return {**state,
            "notice_enabled": setting_bool(db, "platform_notice_enabled"),
            "notice_text": get_platform_setting(db, "platform_notice_text")[:MESSAGE_MAX],
            "running_routes": running}


def save_admin_settings(db, payload: dict) -> list[str]:
    """Salva solo i campi presenti. Ritorna le descrizioni per il registro attività."""
    changes = []
    if "maintenance_mode" in payload:
        on = bool(payload.get("maintenance_mode"))
        set_platform_setting(db, "maintenance_mode", "true" if on else "false")
        changes.append(f"Manutenzione immediata: {'attiva' if on else 'spenta'}")
    if payload.get("end_now"):
        # A lavori finiti: spegne la manutenzione manuale e chiude la finestra programmata.
        for key in ("maintenance_mode", "maintenance_start", "maintenance_end", "maintenance_notice_from"):
            set_platform_setting(db, key, "false" if key == "maintenance_mode" else "")
        changes.append("Manutenzione terminata")
    if "maintenance_start" in payload or "maintenance_end" in payload:
        start = parse_local(payload.get("maintenance_start"))
        end = parse_local(payload.get("maintenance_end"))
        notice_from = parse_local(payload.get("maintenance_notice_from"))
        if payload.get("maintenance_start") and not start:
            raise HTTPException(400, "Inizio della manutenzione non valido.")
        if payload.get("maintenance_end") and not end:
            raise HTTPException(400, "Fine della manutenzione non valida.")
        if end and not start:
            raise HTTPException(400, "Indica anche l'inizio della manutenzione.")
        if start and end and end <= start:
            raise HTTPException(400, "La fine della manutenzione deve essere dopo l'inizio.")
        if start and end and end <= now_local():
            raise HTTPException(400, "La manutenzione programmata è già finita: scegli un orario futuro.")
        if notice_from and start and notice_from >= start:
            raise HTTPException(400, "L'avviso deve comparire prima dell'inizio della manutenzione.")
        set_platform_setting(db, "maintenance_start", _iso(start) or "")
        set_platform_setting(db, "maintenance_end", _iso(end) or "")
        set_platform_setting(db, "maintenance_notice_from", _iso(notice_from) if start else "")
        changes.append(f"Manutenzione programmata: {_iso(start) or 'nessuna'} → {_iso(end) or 'senza fine'}")
    if "maintenance_message" in payload:
        set_platform_setting(db, "maintenance_message", str(payload.get("maintenance_message") or "").strip()[:MESSAGE_MAX])
    if "notice_enabled" in payload or "notice_text" in payload:
        text = str(payload.get("notice_text") or "").strip()[:MESSAGE_MAX]
        enabled = bool(payload.get("notice_enabled"))
        if enabled and not text:
            raise HTTPException(400, "Scrivi il testo dell'avviso prima di attivarlo.")
        set_platform_setting(db, "platform_notice_text", text)
        set_platform_setting(db, "platform_notice_enabled", "true" if enabled else "false")
        changes.append(f"Avviso agli utenti: {'attivo' if enabled else 'spento'}")
    return changes
