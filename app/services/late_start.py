"""Giri programmati non avviati in orario: tolleranza, ritardo e giri da riprogrammare.

- fino a LATE_TOLERANCE_MIN dopo la partenza: nessun avviso, il giro si avvia normalmente;
- oltre: «in ritardo». L'autista può avviare solo se, partendo adesso, fasce orarie, turno e
  pause reggono ancora (stesse tratte salvate, nessuna nuova richiesta di percorso);
- oltre RESCHEDULE_AFTER_MIN, oppure appena il ritardo rende il giro irrealizzabile:
  «da riprogrammare». L'autista non può avviare: l'ufficio sposta la partenza ad adesso
  (orari ricalcolati, ritardi accettati), riprogramma il giro o lo annulla;
- un giro di un giorno passato mai avviato è «non avviato».
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from ..core.utils import local_now

# Spento solo nei test che non riguardano i ritardi (tests/conftest.py), perché usano orari fissi.
ENABLED = True
LATE_TOLERANCE_MIN = 15
RESCHEDULE_AFTER_MIN = 30

LABELS = {"in_ritardo": "In ritardo", "da_riprogrammare": "Da riprogrammare", "non_avviato": "Non avviato"}


def _now(now=None):
    return (now or local_now()).replace(tzinfo=None, second=0, microsecond=0)


def planned_start(plan):
    if not plan.data_giro or not plan.orario_partenza:
        return None
    return datetime.combine(plan.data_giro, plan.orario_partenza)


def _legs(plan, snapshot):
    """Tratte salvate del giro in secondi: con traffico se aggiornate, altrimenti stradali."""
    from .route_enrichment import json_data
    traffic = json_data(plan.traffic_result_json).get("legs") or [] if plan.traffic_status == "updated" else []
    base = snapshot.get("base_legs") or []
    if traffic and len(traffic) >= len(snapshot.get("deliveries") or []):
        return [{"duration": float(leg.get("duration") or 0)} for leg in traffic]
    return [{"duration": float(leg.get("min") or 0) * 60} for leg in base]


def problems_if_started(plan, start):
    """Cosa salta partendo all'orario start: consegne fuori fascia e turno dell'autista.

    None se non ci sono i dati per verificarlo (giri salvati prima delle tratte memorizzate).
    """
    from .route_enrichment import evaluate_legs, json_data
    snapshot = json_data(plan.routing_snapshot_json)
    if not snapshot.get("deliveries"):
        return None
    legs = _legs(plan, snapshot)
    if len(legs) < len(snapshot["deliveries"]):
        return None
    timed = SimpleNamespace(rientro_deposito=plan.rientro_deposito, vehicle=plan.vehicle,
                            driver_schedule=getattr(plan, "driver_schedule", None) or {},
                            orario_partenza=start.strftime("%H:%M"))
    try:
        result = evaluate_legs(snapshot, legs, timed)
    except (KeyError, TypeError, ValueError):
        return None
    late = [stop.get("cliente_nome") for stop in result["ordered"] if stop.get("time_window_violation")]
    problems = []
    if late:
        problems.append(f"{len(late)} {'consegna fuori fascia' if len(late) == 1 else 'consegne fuori fascia'}: " + ", ".join(filter(None, late[:3])))
    if result.get("driver_schedule_error"):
        problems.append(result["driver_schedule_error"])
    return problems


def late_state(plan, now=None, check=True):
    """Stato del giro programmato non ancora avviato; None se è in orario o già partito."""
    if not ENABLED or (plan.status or "").lower() != "programmato" or plan.started_at:
        return None
    start = planned_start(plan)
    if start is None:
        return None
    current = _now(now)
    delay = int((current - start).total_seconds() // 60)
    if plan.data_giro < current.date():
        return {"state": "non_avviato", "label": LABELS["non_avviato"], "delay_min": delay, "problems": []}
    if delay <= LATE_TOLERANCE_MIN:
        return None
    problems = problems_if_started(plan, current) if check else None
    state = "da_riprogrammare" if delay > RESCHEDULE_AFTER_MIN or problems else "in_ritardo"
    return {"state": state, "label": LABELS[state], "delay_min": delay, "problems": problems or []}


def ensure_can_start(plan, now=None):
    """L'autista avvia un giro in ritardo solo se regge ancora; altrimenti decide l'ufficio."""
    from fastapi import HTTPException
    state = late_state(plan, now)
    if state and state["state"] in ("da_riprogrammare", "non_avviato"):
        detail = "; ".join(state["problems"]) if state["problems"] else f"partenza prevista superata di {state['delay_min']} minuti"
        raise HTTPException(409, f"Giro da riprogrammare ({detail}). Contatta l'ufficio: può spostare la partenza ad adesso o riprogrammare il giro.")
    return state


def departure_now(now=None):
    """Nuova partenza: adesso, arrotondata ai 5 minuti successivi."""
    current = _now(now)
    rounded = current + timedelta(minutes=(-current.minute) % 5)
    return rounded.time()
