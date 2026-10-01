"""Road/traffic/toll architecture regressions. All provider calls are mocked."""
import ast
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from app import optimizer
from app.models import ApiUsageLog, Customer, Deposit, DistanceCache, RoutePlan, SaaSPlatformSetting, Vehicle
from app.services import distance_cache, road_routing, traffic_provider
from app.services.route_enrichment import json_data
from app.services.toll_provider import InternalOSMTollCalculator
from test_agents_feature import env


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


@pytest.fixture
def routing_env(env, monkeypatch):
    from app.routers import routes, deposits
    client, db, owner, other, _, _, customer, *_ = env
    client.app.include_router(routes.router)
    client.app.include_router(deposits.router)
    customer.lat, customer.lon, customer.stato_geocodifica = 45.1, 9.1, "verificato"
    depot = Deposit(user_id=owner.id, nome="Depot", indirizzo="Depot", lat=45, lon=9)
    vehicle = Vehicle(user_id=owner.id, nome="Van", consumo_primario_100km=8,
                      consumo_l_100km=8, toll_class="B")
    db.add_all([depot, vehicle])
    db.commit()
    monkeypatch.setenv("OSRM_URL", "http://osrm.test")
    monkeypatch.setenv("DISTANCE_CACHE_TTL_DAYS", "0")
    monkeypatch.setenv("TRAFFIC_PROVIDER", "mapbox")
    monkeypatch.setenv("MAPBOX_ACCESS_TOKEN", "test-secret-token")
    monkeypatch.setenv("MAPBOX_TRAFFIC_COST_EUR", "0.002")
    def forbidden(*args, **kwargs):
        pytest.fail("Unmocked external API call")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    calls = []
    def fake_get(url, params=None, **kwargs):
        calls.append((url, deepcopy(params)))
        if "/table/" in url:
            sources = [int(i) for i in params["sources"].split(";")]
            targets = [int(i) for i in params["destinations"].split(";")]
            return Response({"code": "Ok",
                "distances": [[0 if i == j else 1000 for j in targets] for i in sources],
                "durations": [[0 if i == j else 600 for j in targets] for i in sources]})
        count = len(url.rsplit("/", 1)[-1].split(";")) - 1
        if "api.mapbox.com" in url:
            durations = [1200, 1800, 900]
            return Response({"code": "Ok", "routes": [{"geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
                "legs": [{"duration": durations[i % 3], "distance": 1000} for i in range(count)]}]})
        assert "/route/v1/driving/" in url
        return Response({"code": "Ok", "routes": [{"geometry": "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
            "legs": [{"duration": 600, "distance": 1000,
                      "osm_segments": [{"distance": 1000, "tags": {"toll": "yes"}}]}
                     for _ in range(count)]}]})
    monkeypatch.setattr(requests, "get", fake_get)
    return client, db, owner, other, customer, depot, vehicle, calls


def payload(ctx, *, two=False, day="2099-01-15"):
    _, _, _, _, customer, depot, vehicle, _ = ctx
    rows = [dict(customer_id=customer.id, cliente_nome=customer.nome, indirizzo=customer.indirizzo,
                 tempo_scarico_min=20, scarico_mattina_da="09:00", scarico_mattina_a="10:00")]
    if two:
        rows.append(dict(cliente_nome="Second", indirizzo="Second", lat=45.2, lon=9.2, tempo_scarico_min=15))
    return dict(nome="Test", data_giro=day, orario_partenza="08:00", deposit_id=depot.id,
                vehicle_id=vehicle.id, energy_price_primary=1.75, consegne=rows)


def saved_route(ctx, *, two=False, endpoint="recalculate-manual"):
    response = ctx[0].post("/api/routes/" + endpoint, json=payload(ctx, two=two))
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("endpoint", ["optimize", "recalculate-manual"])
def test_optimizer_never_calls_google_matrix_or_mapbox(routing_env, endpoint, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "google-test")
    result = saved_route(routing_env, two=True, endpoint=endpoint)
    client, db, _, _, _, _, _, calls = routing_env
    assert result["status"] == "bozza"
    assert result["eta_type"] == "road"
    assert len(calls) == 1 and "/table/" in calls[0][0]
    assert calls[0][1]["annotations"] == "distance,duration"
    assert db.query(DistanceCache).count() == 6
    assert db.query(ApiUsageLog).count() == 0
    for path in (f"/api/routes/{result['id']}", f"/api/routes/{result['id']}/map-data"):
        assert client.get(path).status_code == 200
    assert len(calls) == 1


def test_cache_reused_across_companies_dates_and_directions(routing_env):
    ctx = routing_env
    saved_route(ctx)
    rows = ctx[1].query(DistanceCache).all()
    assert len(rows) == 2 and all(row.expires_at is None for row in rows)
    reverse_pairs = {(r.origin_key, r.dest_key) for r in rows}
    assert all((b, a) in reverse_pairs for a, b in reverse_pairs)
    first = ctx[0].post("/api/routes/optimize", json=payload(ctx, day="2099-07-16"))
    assert first.status_code == 200, first.text
    data = payload(ctx, day="2100-02-01")
    data["orario_partenza"] = "11:00"
    assert ctx[0].post("/api/routes/optimize", json=data).status_code == 200
    assert len(ctx[-1]) == 1
    keys = list(reverse_pairs)
    assert distance_cache.get_pairs(ctx[1], ctx[3].id, keys) == {}
    distance_cache.save_pairs(ctx[1], ctx[3].id, [(keys[0][0], keys[0][1], 50, 90)])
    assert distance_cache.get_pairs(ctx[1], ctx[2].id, keys)[keys[0]]["km"] == 1
    assert distance_cache.get_pairs(ctx[1], ctx[3].id, keys)[keys[0]]["km"] == 50


@pytest.mark.parametrize("address_change,new_coordinates", [(True, False), (True, True), (False, True)])
def test_address_and_coordinate_changes_invalidate_all_customer_legs(routing_env, address_change, new_coordinates):
    saved_route(routing_env)
    client, db, _, _, customer, *_ = routing_env
    data = dict(nome=customer.nome, indirizzo="New" if address_change else customer.indirizzo,
                lat=46 if new_coordinates else None, lon=10 if new_coordinates else None,
                stato_geocodifica="verificato" if new_coordinates else "da_verificare")
    response = client.put(f"/api/customers/{customer.id}", json=data)
    assert response.status_code == 200, response.text
    assert db.query(DistanceCache).count() == 0


def test_depot_address_change_invalidates_directional_pairs(routing_env):
    saved_route(routing_env)
    client, db, _, _, _, depot, *_ = routing_env
    assert client.put(f"/api/deposits/{depot.id}", json={"nome": "Depot", "indirizzo": "New"}).status_code == 200
    assert db.query(DistanceCache).count() == 0
    assert depot.lat is None and depot.lon is None


def test_osrm_table_units_subset_and_unreachable_fallback(routing_env, monkeypatch):
    _, db, owner, *_ = routing_env
    points = [{"lat": 45, "lon": 9}, {"lat": 46, "lon": 10}, {"lat": 47, "lon": 11}]
    calls = []
    def get(url, params, **kwargs):
        calls.append(params)
        return Response({"code": "Ok", "distances": [[None, 2500]], "durations": [[None, 150]]})
    monkeypatch.setattr(requests, "get", get)
    legs = road_routing.osrm_table(points, pairs=[(0, 1), (0, 2)], db=db)
    assert legs == {(0, 2): {"km": 2.5, "min": 2.5}}
    assert calls[0]["sources"] == "0" and calls[0]["destinations"] == "1;2"
    monkeypatch.setattr(road_routing, "osrm_table", lambda *args, **kwargs: legs)
    matrix = road_routing.build_matrix(db, owner.id, points, ["p0", "p1", "p2"])
    assert matrix.source == "mixed"
    assert len(matrix) == 6
    assert db.query(DistanceCache).count() == 1


def test_osrm_timeout_does_not_pollute_cache_and_can_recover(routing_env, monkeypatch):
    original = requests.get
    def unavailable(url, **kwargs):
        if "/table/" in url:
            raise requests.Timeout("OSRM down")
        return original(url, **kwargs)
    monkeypatch.setattr(requests, "get", unavailable)
    result = saved_route(routing_env, endpoint="optimize")
    assert result["eta_type"] == "approximate"
    assert routing_env[1].query(DistanceCache).count() == 0
    monkeypatch.setattr(requests, "get", original)
    restored = saved_route(routing_env, endpoint="optimize")
    assert restored["eta_type"] == "road"
    assert routing_env[1].query(DistanceCache).count() == 2


def test_mapbox_legs_recalculate_wait_unloading_and_return(routing_env):
    ctx = routing_env
    draft = saved_route(ctx, two=True)
    response = ctx[0].post(f"/api/routes/{draft['id']}/program", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    first, second = result["consegne"]
    assert [d["cliente_nome"] for d in result["consegne"]] == [d["cliente_nome"] for d in draft["consegne"]]
    assert (first["arrivo_fisico"], first["attesa_min"], first["arrivo_stimato"], first["partenza_stimata"]) == ("08:20", 40, "09:00", "09:20")
    assert (second["arrivo_stimato"], second["partenza_stimata"]) == ("09:50", "10:05")
    assert result["orario_rientro_stimato"] == "10:20" and result["totale_minuti"] == 140
    assert len(result["traffic_legs"]) == 3
    assert result["traffic_provider"] == "mapbox" and result["traffic_status"] == "updated"
    assert result["traffic_departure_at"].startswith("2099-01-15T07:00")
    assert first["service_start_at"].startswith("2099-01-15T09:00")
    assert result["toll_estimated_eur"] == 0.30
    assert result["costo_carburante"] == draft["costo_carburante"]
    assert result["costo_totale"] == pytest.approx(draft["costo_carburante"] + 0.30)
    logs = ctx[1].query(ApiUsageLog).all()
    assert len(logs) == 1
    assert (logs[0].provider, logs[0].service, logs[0].user_id, logs[0].route_plan_id) == ("mapbox", "mapbox_traffic", ctx[2].id, draft["id"])
    assert logs[0].request_count == 1 and logs[0].response_ms is not None
    assert logs[0].estimated_cost_eur == 0.002
    assert all(row.min == 10 for row in ctx[1].query(DistanceCache).all())


def test_open_programmed_route_and_map_uses_saved_results_only(routing_env):
    ctx = routing_env
    draft = saved_route(ctx, two=True)
    assert ctx[0].post(f"/api/routes/{draft['id']}/program", json={}).status_code == 200
    count = len(ctx[-1])
    for _ in range(2):
        result = ctx[0].get(f"/api/routes/{draft['id']}").json()
        map_data = ctx[0].get(f"/api/routes/{draft['id']}/map-data").json()
        assert result["eta_type"] == "traffic"
        assert map_data["road_polyline"]["encoded_polylines"]
    assert ctx[0].post(f"/api/routes/{draft['id']}/program", json={}).status_code == 200
    assert len(ctx[-1]) == count
    customer = ctx[4]
    assert ctx[0].put(f"/api/customers/{customer.id}", json={"nome": customer.nome, "indirizzo": "Moved", "lat": 48, "lon": 12}).status_code == 200
    assert ctx[0].get(f"/api/routes/{draft['id']}/map-data").json()["stops"][0]["lat"] == 45.1
    assert len(ctx[-1]) == count


def test_mapbox_fallback_programs_successfully_and_real_refresh_retries(routing_env, monkeypatch):
    ctx = routing_env
    draft = saved_route(ctx, two=True)
    original = requests.get
    def unavailable(url, **kwargs):
        if "api.mapbox.com" in url:
            raise requests.Timeout("https://api.mapbox.com/?access_token=test-secret-token")
        return original(url, **kwargs)
    monkeypatch.setattr(requests, "get", unavailable)
    response = ctx[0].post(f"/api/routes/{draft['id']}/program", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "programmato" and result["traffic_status"] == "unavailable"
    assert result["eta_type"] == "road"
    assert result["orario_rientro_stimato"] == draft["orario_rientro_stimato"]
    assert "test-secret-token" not in ctx[1].query(ApiUsageLog).first().message
    monkeypatch.setattr(requests, "get", original)
    refresh = ctx[0].post(f"/api/routes/{draft['id']}/refresh-traffic")
    assert refresh.status_code == 200 and refresh.json()["traffic_status"] == "updated"
    assert ctx[1].query(ApiUsageLog).count() == 2


def test_none_provider_never_calls_traffic(routing_env, monkeypatch):
    monkeypatch.setenv("TRAFFIC_PROVIDER", "none")
    draft = saved_route(routing_env)
    assert routing_env[0].post(f"/api/routes/{draft['id']}/program", json={}).status_code == 200
    assert all("api.mapbox.com" not in url for url, _ in routing_env[-1])
    assert routing_env[1].query(ApiUsageLog).count() == 0


@pytest.mark.parametrize("count,configured,sizes", [(25, None, [25]), (26, None, [25, 2]), (51, "100", [25, 25, 3]), (23, "10", [10, 10, 5])])
def test_mapbox_over_waypoint_limit_preserves_all_directed_legs(routing_env, monkeypatch, count, configured, sizes):
    monkeypatch.delenv("MAPBOX_MAX_COORDINATES", raising=False)
    if configured:
        monkeypatch.setenv("MAPBOX_MAX_COORDINATES", configured)
    calls = []
    def get(url, params, **kwargs):
        coordinates = [tuple(map(float, value.split(","))) for value in url.rsplit("/", 1)[-1].split(";")]
        calls.append((coordinates, params["depart_at"]))
        return Response({"code": "Ok", "routes": [{"geometry": "g", "legs":
            [{"duration": destination[0] * 60} for destination in coordinates[1:]]}]})
    monkeypatch.setattr(requests, "get", get)
    points = [{"lat": 45, "lon": i} for i in range(count)]
    result = traffic_provider.MapboxTrafficProvider().calculate(points, "2099-01-15T07:00:00Z")
    assert [len(chunk) for chunk, _ in calls] == sizes
    assert all(a[0][-1] == b[0][0] for a, b in zip(calls, calls[1:]))
    assert [leg["duration"] for leg in result["legs"]] == [i * 60 for i in range(1, count)]
    assert [p for chunk, _ in calls for p in chunk[1:]] == [(i, 45) for i in range(1, count)]


def test_failed_later_traffic_segment_falls_back_as_a_whole(routing_env, monkeypatch):
    monkeypatch.setenv("MAPBOX_MAX_COORDINATES", "10")
    counter = 0
    def get(url, **kwargs):
        nonlocal counter
        counter += 1
        if counter == 2:
            raise requests.Timeout()
        return Response({"code": "Ok", "routes": [{"legs": [{"duration": 60}] * 9}]})
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(traffic_provider.TrafficUnavailable):
        traffic_provider.MapboxTrafficProvider().calculate([{"lat": 45, "lon": i} for i in range(12)], "2099-01-15T07:00:00Z")


def test_toll_estimate_rates_fixed_tariffs_and_unknown_coverage(routing_env, tmp_path, monkeypatch):
    calculator = InternalOSMTollCalculator()
    road = {"legs": [{"osm_segments": [
        {"distance": 10000, "tags": {"toll": "yes"}},
        {"distance": 5000, "tags": {"toll": "no"}}]}]}
    assert calculator.estimate(road, "B")["amount_eur"] == 1
    assert calculator.estimate(road, "3")["amount_eur"] == 1.40
    dataset = tmp_path / "osm-tolls.json"
    dataset.write_text(json.dumps({"version": "test", "edges": {
        "1,2": {"tags": {"toll": "yes"}, "charge_id": "a", "fixed_eur_by_class": {"B": 4.50}},
        "2,3": {"tags": {"toll": "yes"}, "charge_id": "a", "fixed_eur_by_class": {"B": 4.50}},
    }}))
    monkeypatch.setenv("TOLL_DATASET_PATH", str(dataset))
    mapped = calculator.estimate({"legs": [{"annotation": {"nodes": [1, 2, 3], "distance": [1000, 2000]}}]}, "B")
    assert mapped["amount_eur"] == 4.50 and mapped["status"] == "estimated"
    road["legs"][0]["osm_segments"].append({"distance": 700})
    assert calculator.estimate(road)["status"] == "partial"
    unknown = calculator.estimate({"legs": [{"steps": [{"distance": 2000, "name": "A1", "osm_tags": {"highway": "motorway"}}]}]})
    assert unknown["amount_eur"] is None and unknown["status"] == "unavailable"


def test_custom_osrm_toll_class_is_used(routing_env):
    road = {"legs": [{"steps": [{"distance": 12000, "intersections": [{"classes": ["toll", "motorway"]}]}]}]}
    result = InternalOSMTollCalculator().estimate(road)
    assert result["amount_eur"] == 1.20


def test_traffic_and_saved_route_cannot_cross_company_boundaries(routing_env):
    from app.core.dependencies import current_user
    ctx = routing_env
    draft = saved_route(ctx)
    count = len(ctx[-1])
    ctx[0].app.dependency_overrides[current_user] = lambda: ctx[3]
    for path, method in [(f"/api/routes/{draft['id']}", "get"),
                         (f"/api/routes/{draft['id']}/map-data", "get"),
                         (f"/api/routes/{draft['id']}/refresh-traffic", "post")]:
        assert getattr(ctx[0], method)(path).status_code == 404
    assert len(ctx[-1]) == count


@pytest.mark.parametrize("fuel_type,primary,electric,expected", [
    ("gasolio", 8, 0, 0.28), ("benzina", 8, 0, 0.28), ("elettrico", 0, 20, 0.12),
    ("ibrido_plugin_benzina", 4, 10, 0.20),
])
@pytest.mark.parametrize("two", [False, True])
def test_energy_calculations_are_preserved(routing_env, fuel_type, primary, electric, expected, two):
    ctx = routing_env
    vehicle = ctx[6]
    vehicle.alimentazione = fuel_type
    vehicle.consumo_primario_100km = primary
    vehicle.consumo_l_100km = primary
    vehicle.consumo_kwh_100km = electric
    ctx[1].commit()
    data = payload(ctx, two=two)
    data["energy_price_electric"] = 0.30
    response = ctx[0].post("/api/routes/recalculate-manual", json=data)
    assert response.status_code == 200, response.text
    # 2 km round trip, diesel 1.75 EUR/L, electric 0.30 EUR/kWh.
    result = response.json()
    km = 3 if two else 2
    assert result["totale_km"] == km
    assert result["energy_quantity_primary"] == round(km * primary / 100, 3)
    assert result["energy_quantity_electric"] == round(km * electric / 100, 3)
    assert result["costo_carburante"] == round(expected * km / 2, 2)


def test_public_osrm_requires_explicit_development_setting(monkeypatch):
    from app.services.platform_settings import osrm_url
    monkeypatch.setenv("OSRM_URL", "https://router.project-osrm.org")
    monkeypatch.setenv("OSRM_ALLOW_PUBLIC_FALLBACK", "true")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValueError, match="istanza propria"):
        osrm_url()
    monkeypatch.setenv("APP_ENV", "development")
    assert osrm_url() == "https://router.project-osrm.org"


def test_routing_migrations_are_additive_idempotent_and_preserve_saved_tours(routing_env):
    import sqlalchemy
    from app.database import Base
    ctx = routing_env
    route_id = saved_route(ctx)["id"]
    db, engine = ctx[1], ctx[1].get_bind()
    db.close()
    with engine.begin() as conn:
        for column in ("traffic_provider", "routing_snapshot_json", "toll_estimated_eur"):
            conn.execute(sqlalchemy.text("ALTER TABLE route_plans DROP COLUMN " + column))
        conn.execute(sqlalchemy.text("ALTER TABLE vehicles DROP COLUMN toll_class"))
    module = ast.parse(Path("app/main.py").read_text(encoding="utf-8"))
    function = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "migrate_database")
    namespace = {**vars(sqlalchemy), "Base": Base, "engine": engine}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "app/main.py", "exec"), namespace)
    namespace["migrate_database"]()
    namespace["migrate_database"]()
    saved = db.get(RoutePlan, route_id)
    assert saved.totale_km == 2 and saved.costo_carburante == 0.28
    assert saved.traffic_provider is None and saved.toll_estimated_eur is None
    assert len(saved.deliveries) == 1


def test_api_summary_counts_entire_period_and_actual_provider_requests(routing_env):
    from app.services.api_usage import api_usage_summary, estimate_cost, log_api_usage
    ctx = routing_env
    for _ in range(270):
        ctx[1].add(ApiUsageLog(user_id=ctx[2].id, provider="mapbox", service="mapbox_traffic",
                             request_count=1, status="success", estimated_cost_eur=0.002))
    ctx[1].commit()
    result = api_usage_summary(ctx[1])
    assert result["total_calls"] == 270 and result["estimated_cost_eur"] == 0.54
    assert len(result["recent"]) == 100 and result["by_service"][0]["provider"] == "mapbox"
    assert estimate_cost("google_routes_matrix") == 0


def test_segment_departures_include_unloading_and_window_waits(routing_env, monkeypatch):
    monkeypatch.setenv("MAPBOX_MAX_COORDINATES", "10")
    ctx = routing_env
    data = payload(ctx)
    data["consegne"] += [dict(cliente_nome=f"Stop {i}", indirizzo=f"Address {i}", lat=45 + i / 1000,
                             lon=9 + i / 1000, tempo_scarico_min=5) for i in range(2, 12)]
    draft = ctx[0].post("/api/routes/recalculate-manual", json=data)
    assert draft.status_code == 200, draft.text
    route_id = draft.json()["id"]
    response = ctx[0].post(f"/api/routes/{route_id}/program", json={})
    assert response.status_code == 200, response.text
    result = response.json()
    traffic_calls = [params for url, params in ctx[-1] if "api.mapbox.com" in url]
    assert len(traffic_calls) == 2
    assert traffic_calls[1]["depart_at"].startswith("2099-01-15T11:55")
    assert len(result["traffic_legs"]) == 12
    assert result["orario_rientro_stimato"] == "14:10"
    assert [d["cliente_nome"] for d in result["consegne"]] == [d["cliente_nome"] for d in draft.json()["consegne"]]
    assert ctx[1].query(ApiUsageLog).count() == 2


def test_osrm_table_splits_large_matrices_into_bounded_blocks(routing_env, monkeypatch):
    monkeypatch.setenv("OSRM_TABLE_MAX_COORDINATES", "4")
    points = [{"lat": 45 + i / 1000, "lon": 9 + i / 1000} for i in range(7)]
    result = road_routing.osrm_table(points)
    assert len(result) == 42
    for url, params in routing_env[-1]:
        assert "/table/" in url
        assert len(url.rsplit("/", 1)[-1].split(";")) <= 4
        assert len(params["sources"].split(";")) <= 2
        assert len(params["destinations"].split(";")) <= 2


def test_geocoding_logs_real_http_requests_once_with_company(routing_env, monkeypatch):
    ctx = routing_env
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "google-test")
    def get(url, **kwargs):
        assert url == "https://maps.googleapis.com/maps/api/geocode/json"
        return Response({"status": "OK", "results": [{"geometry": {
            "location": {"lat": 45, "lng": 9}, "location_type": "ROOFTOP"}, "formatted_address": "Test"}]})
    monkeypatch.setattr(requests, "get", get)
    result = ctx[0].post("/api/customers/verify-address-preview", json={"nome": "Test", "indirizzo": "Test"})
    assert result.status_code == 200, result.text
    logs = ctx[1].query(ApiUsageLog).all()
    assert len(logs) == 1 and logs[0].provider == "google"
    assert logs[0].service == "google_geocoding" and logs[0].user_id == ctx[2].id
    assert logs[0].estimated_cost_eur == 0.005


def test_platform_settings_override_env_for_traffic(routing_env, monkeypatch):
    ctx = routing_env
    ctx[1].add(SaaSPlatformSetting(key="traffic_provider", value="none"))
    ctx[1].commit()
    assert traffic_provider.get_traffic_provider(ctx[1]).name == "none"
    assert traffic_provider.get_traffic_provider().name == "mapbox"


def test_traffic_refresh_preserves_ztl_and_tail_lift_warnings(routing_env):
    ctx = routing_env
    ctx[2].has_ztl = True
    ctx[2].needs_tail_lift = True
    ctx[1].commit()
    data = payload(ctx)
    data["consegne"][0].update(ztl=True, sponda=True)
    response = ctx[0].post("/api/routes/recalculate-manual", json=data)
    assert response.status_code == 200, response.text
    programmed = ctx[0].post(f"/api/routes/{response.json()['id']}/program", json={})
    assert programmed.status_code == 200, programmed.text
    warning = programmed.json()["consegne"][0]["warning"]
    assert "Serve sponda ma il mezzo selezionato non la possiede" in warning
    assert "Cliente in ZTL: verificare accesso mezzo" in warning
