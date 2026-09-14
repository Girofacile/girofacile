"""Funzioni AI assistite per GiroFacile v67.

L'AI non prende decisioni operative e non invia messaggi automaticamente:
produce solo testi brevi e modificabili dall'utente/Super Admin.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
import requests
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import ApiUsageLog, SaaSPlatformSetting, User
from ..services.api_usage import log_api_usage
from ..services.platform_settings import ai_enabled as db_ai_enabled, openai_api_key, openai_model
from ..services.plans import get_user_plan_status

AI_ALLOWED_PLANS = {"business", "pro"}
AI_DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AI_COSTS_EUR_PER_1M = {
    # stime interne conservative, modificabili quando si aggiorna listino
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}


def _setting(db: Session, key: str, default: str = "") -> str:
    try:
        row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == key).first()
        return row.value if row and row.value is not None else default
    except Exception:
        return default


def ai_enabled(db: Session) -> bool:
    return db_ai_enabled(db)


def get_ai_key(db: Session) -> str:
    # Priorità: impostazioni salvate dal Super Admin nel database, poi .env
    return openai_api_key(db)


def get_ai_model(db: Session) -> str:
    return openai_model(db)


def ensure_company_ai_allowed(user: User, db: Session):
    if not ai_enabled(db):
        raise HTTPException(403, "AI non attiva nelle impostazioni SaaS")
    if get_user_plan_status(user) not in ("active", "trial"):
        raise HTTPException(403, "AI disponibile solo con piano attivo")
    if (user.plan or "starter").lower() not in AI_ALLOWED_PLANS:
        raise HTTPException(403, "Funzione AI disponibile solo nei piani Business e Pro")


def estimate_ai_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = AI_COSTS_EUR_PER_1M.get(model, AI_COSTS_EUR_PER_1M.get("gpt-4o-mini"))
    return round((max(0, input_tokens) / 1_000_000) * rates["input"] + (max(0, output_tokens) / 1_000_000) * rates["output"], 6)


def _local_fallback(task: str, context: dict[str, Any]) -> str:
    sector = (context.get("sector") or "").lower()
    if task == "route_explanation":
        stops = context.get("stops") or []
        first = stops[0]["name"] if stops else "la prima tappa"
        tight = [s for s in stops if s.get("time_windows")]
        sector_word = "consegne"
        if "transfer" in sector:
            sector_word = "corse/prenotazioni"
        elif "food" in sector:
            sector_word = "ritiri e consegne food"
        elif "e-commerce" in sector or "ecommerce" in sector:
            sector_word = "ordini"
        elif "farm" in sector or "sanit" in sector:
            sector_word = "consegne sanitarie"
        reason = f"La sequenza è stata proposta per gestire le {sector_word} in modo progressivo, partendo da {first} e riducendo gli spostamenti inutili."
        if tight:
            reason += f" Alcune tappe sono state posizionate prima perché hanno vincoli orari più precisi, ad esempio {tight[0]['name']}."
        reason += " Il testo è una spiegazione assistita: il percorso resta calcolato da GiroFacile e dai servizi di routing collegati."
        return reason
    if task == "support_ticket_text":
        return "Stavo utilizzando GiroFacile quando si è verificato un errore tecnico collegato a questa operazione. Chiedo assistenza per verificare la causa e ripristinare il corretto funzionamento della funzione interessata."
    if task == "admin_error_analysis":
        return "Problema rilevato: errore tecnico collegato al ticket o alla funzione indicata.\n\nPossibile causa: configurazione servizio esterno, dati mancanti oppure anomalia temporanea del server.\n\nCome risolvere: controllare i dettagli tecnici dell'errore, verificare eventuali API coinvolte e riprovare l'operazione con l'account azienda interessato.\n\nRisposta suggerita: abbiamo ricevuto la segnalazione e stiamo verificando la causa tecnica del problema."
    if task == "report_summary":
        m = context.get("metrics") or {}
        return f"Nel periodo selezionato risultano {m.get('giri_effettuati', 0)} giri completati e {m.get('consegne_totali', 0)} consegne gestite. I km totali sono circa {m.get('km_totali', 0)} e il costo carburante stimato è € {m.get('costo_carburante', 0)}. Valuta eventuali clienti o risorse ricorrenti con tempi più alti per migliorare i prossimi giri."
    return "Testo assistito generato da GiroFacile."


def run_ai_text(db: Session, *, task: str, system_prompt: str, user_prompt: str, user_id: int | None = None, context: dict[str, Any] | None = None) -> dict:
    model = get_ai_model(db)
    key = get_ai_key(db)
    context = context or {}
    if not ai_enabled(db):
        raise HTTPException(403, "AI non attiva nelle impostazioni SaaS")

    if not key:
        text = _local_fallback(task, context)
        log_api_usage(db, user_id=user_id, provider="openai", service=f"openai_{task}", action="AI fallback locale", endpoint="/ai/fallback", status="failed", message="OpenAI API key non configurata", estimated_cost_eur=0, meta={"task": task, "model": model})
        return {"text": text, "model": model, "configured": False, "fallback": True, "estimated_cost_eur": 0}

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 450,
    }
    try:
        started = datetime.utcnow()
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=30,
        )
        response_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
        if resp.status_code >= 400:
            msg = resp.text[:1000]
            log_api_usage(db, user_id=user_id, provider="openai", service=f"openai_{task}", action="Chiamata AI", endpoint="/v1/chat/completions", status="failed", message=msg, response_ms=response_ms, estimated_cost_eur=0, meta={"task": task, "model": model})
            raise HTTPException(502, f"Errore OpenAI: {msg}")
        data = resp.json()
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        cost = estimate_ai_cost(model, input_tokens, output_tokens)
        log_api_usage(db, user_id=user_id, provider="openai", service=f"openai_{task}", action="Chiamata AI", endpoint="/v1/chat/completions", request_count=1, status="success", message=f"{input_tokens} input token, {output_tokens} output token", response_ms=response_ms, estimated_cost_eur=cost, meta={"task": task, "model": model, "input_tokens": input_tokens, "output_tokens": output_tokens})
        return {"text": text.strip(), "model": model, "configured": True, "fallback": False, "input_tokens": input_tokens, "output_tokens": output_tokens, "estimated_cost_eur": cost}
    except HTTPException:
        raise
    except Exception as exc:
        log_api_usage(db, user_id=user_id, provider="openai", service=f"openai_{task}", action="Chiamata AI", endpoint="/v1/chat/completions", status="failed", message=str(exc), estimated_cost_eur=0, meta={"task": task, "model": model})
        raise HTTPException(502, f"Servizio AI non disponibile: {exc}")
