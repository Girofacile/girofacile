"""Giri programmati partiti in ritardo: tolleranza, «in ritardo», «da riprogrammare», partenza spostata."""
from datetime import date, datetime, time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import late_start
from test_agents_feature import env  # noqa: F401  (fixture)
from test_routing_architecture import routing_env, saved_route  # noqa: F401


def plan(start="08:00", day=date(2026, 11, 9), status="programmato", started=None):
    return SimpleNamespace(status=status, started_at=started, data_giro=day,
                           orario_partenza=time.fromisoformat(start))


def at(hhmm, day=date(2026, 11, 9)):
    return datetime.combine(day, time.fromisoformat(hhmm))


def test_tolerance_late_and_reschedule_thresholds(monkeypatch):
    monkeypatch.setattr(late_start, "problems_if_started", lambda plan, start: [])
    assert late_start.late_state(plan(), at("08:15")) is None  # entro la tolleranza
    late = late_start.late_state(plan(), at("08:20"))
    assert late["state"] == "in_ritardo" and late["delay_min"] == 20
    assert late_start.late_state(plan(), at("08:31"))["state"] == "da_riprogrammare"
    # Già avviato, annullato o in bozza: nessuno stato di ritardo.
    assert late_start.late_state(plan(started=at("08:40")), at("09:00")) is None
    assert late_start.late_state(plan(status="annullato"), at("09:00")) is None
    # Giorno passato mai avviato.
    assert late_start.late_state(plan(day=date(2026, 11, 8)), at("07:00"))["state"] == "non_avviato"


def test_infeasible_delay_needs_the_office_before_thirty_minutes(monkeypatch):
    monkeypatch.setattr(late_start, "problems_if_started", lambda plan, start: ["1 consegna fuori fascia: Bar Roma"])
    state = late_start.late_state(plan(), at("08:20"))
    assert state["state"] == "da_riprogrammare" and "Bar Roma" in state["problems"][0]
    with pytest.raises(HTTPException) as blocked:
        late_start.ensure_can_start(plan(), at("08:20"))
    assert blocked.value.status_code == 409 and "Bar Roma" in blocked.value.detail
    # In ritardo ma ancora realizzabile: l'autista avvia.
    monkeypatch.setattr(late_start, "problems_if_started", lambda plan, start: [])
    assert late_start.ensure_can_start(plan(), at("08:20"))["state"] == "in_ritardo"


def test_departure_now_rounds_to_the_next_five_minutes():
    assert late_start.departure_now(at("09:12")) == time(9, 15)
    assert late_start.departure_now(at("09:15")) == time(9, 15)


def test_saved_legs_detect_window_violations_when_leaving_now(routing_env):
    ctx = routing_env
    draft = saved_route(ctx, two=True)
    from app.models import RoutePlan
    route = ctx[1].get(RoutePlan, draft["id"])
    # Prima fermata con fascia 09:00–10:00, tratte da 10 minuti: alle 08:00 regge, alle 10:00 no.
    assert late_start.problems_if_started(route, at("08:00")) == []
    problems = late_start.problems_if_started(route, at("10:30"))
    assert problems and "fuori fascia" in problems[0]


def test_depart_now_moves_the_departure_of_a_late_route(routing_env, monkeypatch):
    ctx = routing_env
    client, db = ctx[0], ctx[1]
    draft = saved_route(ctx, two=True)
    assert client.post(f"/api/routes/{draft['id']}/program", json={}).status_code == 200
    from app.models import RoutePlan
    from app.routers import routes
    route = db.get(RoutePlan, draft["id"])
    today = date(2099, 1, 15)
    monkeypatch.setattr(routes, "local_today", lambda: today)
    monkeypatch.setattr(late_start, "local_now", lambda: datetime.combine(today, time(8, 47)))
    route.orario_partenza = time(8, 0)
    db.commit()
    listed = next(r for r in client.get("/api/routes/operativi").json() if r["id"] == route.id)
    assert listed["late_start"]["state"] == "da_riprogrammare" and listed["late_start"]["delay_min"] == 47
    moved = client.post(f"/api/routes/{route.id}/depart-now")
    assert moved.status_code == 200, moved.text
    assert moved.json()["orario_partenza"] == "08:50" and moved.json()["late_start"] is None
    # Un giro di un altro giorno non si sposta: va riprogrammato o annullato.
    route.data_giro = date(2099, 1, 14)
    db.commit()
    assert client.post(f"/api/routes/{route.id}/depart-now").status_code == 409


def test_office_can_still_close_a_late_route(routing_env, monkeypatch):
    ctx = routing_env
    client, db = ctx[0], ctx[1]
    draft = saved_route(ctx, two=True)
    assert client.post(f"/api/routes/{draft['id']}/program", json={}).status_code == 200
    from app.models import RoutePlan
    route = db.get(RoutePlan, draft["id"])
    from datetime import timedelta
    from app.core.utils import local_today
    route.data_giro = local_today() - timedelta(days=1)  # giorno passato, mai avviato
    db.commit()
    assert late_start.late_state(route)["state"] == "non_avviato"
    closed = client.post(f"/api/routes/{route.id}/complete", json={})
    assert closed.status_code == 200, closed.text
