"""Provider generations serialize on disposable PostgreSQL, with real lock evidence."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as clock_time, timedelta
from threading import Barrier, Event, Lock
from types import SimpleNamespace
import pytest
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_audit_postgres import pg


@pytest.mark.parametrize("force", [False, True], ids=["program", "force-refresh"])
def test_overlapping_enrichment_reuses_one_attempt(pg, monkeypatch, force):
    from app.database import Base
    from app.models import ApiUsageLog, Delivery, RoutePlan, User
    from app.services import route_enrichment as re
    from app.services.api_usage import log_api_usage
    Base.metadata.create_all(pg)
    old_at, calculated_at = datetime(2020, 1, 1), datetime(2030, 1, 1)
    monkeypatch.setattr(re, "utc_now", lambda: calculated_at)
    def forbidden(*args, **kwargs):
        pytest.fail("Unmocked external API call")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(re.road_routing, "road_route", lambda *args, **kwargs: {"geometries": ["saved-road"]})
    monkeypatch.setattr(re, "get_toll_calculator", lambda db: SimpleNamespace(
        estimate=lambda *args, **kwargs: {"provider": "internal-osm", "status": "estimated", "amount_eur": .3, "version": 1}))
    with Session(pg, autoflush=False) as db:
        owner = User(username="enrichment-owner", password_hash="test")
        db.add(owner)
        db.flush()
        plan = RoutePlan(user_id=owner.id, nome="Concurrent enrichment", data_giro=date(2099, 1, 15),
            orario_partenza=clock_time(8), rientro_deposito=False,
            status="programmato" if force else "bozza", totale_km=1, totale_minuti=10,
            routing_snapshot_json=json.dumps({
                "revision": 1, "points": [{"lat": 45, "lon": 9}, {"lat": 45.1, "lon": 9.1}],
                "deliveries": [{"cliente_nome": "Customer", "indirizzo": "Address", "ordine": 1,
                                "tempo_scarico_min": 0, "km_tappa": 1, "minuti_tappa": 10}],
                "base_legs": [{"km": 1, "min": 10}], "base_total_min": 10, "base_return_time": "08:10"}),
            traffic_status="updated" if force else "not_requested", traffic_version=1 if force else 0,
            traffic_calculated_at=old_at if force else None,
            traffic_result_json=json.dumps({"provider": "mapbox", "legs": [{"duration": 600}]}) if force else None)
        plan.deliveries.append(Delivery(cliente_nome="Customer", indirizzo="Address", ordine=1,
                                       tempo_scarico_min=0, km_tappa=1, minuti_tappa=10))
        db.add(plan)
        db.commit()
        route_id = plan.id
    ready, entered, release, duplicate = Barrier(2), Event(), Event(), Event()
    mutex, calls, pids, state = Lock(), [], {}, {}

    class Provider:
        name = "mapbox"
        def calculate(self, points, departure, *, db, user_id, route_id, **kwargs):
            with mutex:
                calls.append(route_id)
                first = len(calls) == 1
                if first:
                    state["provider_pid"] = db.info["backend_pid"]
                else:
                    duplicate.set()
            assert log_api_usage(db, user_id=user_id, route_id=route_id, provider="mapbox",
                service="mapbox_traffic", request_count=1, status="success", commit=False) is not None
            if first:
                entered.set()
            assert release.wait(10)
            return {"provider": "mapbox", "departure_time": departure,
                    "legs": [{"duration": 1200}], "geometries": ["traffic-road"], "version": 1}
    monkeypatch.setattr(re, "get_traffic_provider", lambda db: Provider())

    def enrich(worker):
        with Session(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout = '10000ms'"))
            plan = db.get(RoutePlan, route_id)
            assert plan.traffic_calculated_at == (old_at if force else None)
            pid = db.execute(text("SELECT pg_backend_pid()")).scalar_one()
            db.info["backend_pid"] = pid
            with mutex:
                pids[worker] = pid
            ready.wait(timeout=5)
            re.enrich_final_route(db, plan, force=force)
            result = plan.traffic_status, plan.traffic_version, plan.traffic_calculated_at
            db.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(enrich, worker) for worker in range(2)]
        try:
            assert entered.wait(5)
            with mutex:
                provider_pid = state["provider_pid"]
                waiting_pid = next(pid for pid in pids.values() if pid != provider_pid)
            deadline = time.monotonic() + 5
            with Session(pg) as observer:
                while True:
                    assert not duplicate.is_set(), "Overlapping provider call"
                    blockers = observer.execute(text("SELECT pg_blocking_pids(:pid)"),
                                                {"pid": waiting_pid}).scalar_one()
                    if provider_pid in blockers:
                        break
                    assert time.monotonic() < deadline, "No PostgreSQL lock wait observed"
                    release.wait(.01)
                assert len(calls) == 1
                assert observer.query(ApiUsageLog).count() == 0
        finally:
            release.set()
        results = [f.result(timeout=10) for f in futures]
    assert results == [("updated", 1, calculated_at)] * 2
    assert calls == [route_id]
    with Session(pg, autoflush=False) as db:
        saved = db.get(RoutePlan, route_id)
        assert saved.totale_minuti == saved.deliveries[0].minuti_tappa == 20
        assert db.query(ApiUsageLog).count() == 1
    if force:
        later = calculated_at + timedelta(seconds=1)
        monkeypatch.setattr(re, "utc_now", lambda: later)
        with Session(pg, autoflush=False) as db:
            re.enrich_final_route(db, db.get(RoutePlan, route_id), force=True)
            db.commit()
        assert calls == [route_id, route_id]
        with Session(pg, autoflush=False) as db:
            assert db.get(RoutePlan, route_id).traffic_calculated_at == later
            assert db.query(ApiUsageLog).count() == 2
