"""Persist final-route traffic, road geometry, tolls and timing without changing order."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from ..core.utils import LOCAL_TZ, parse_time_value, time_to_hhmm
from . import road_routing
from .traffic_provider import get_traffic_provider, TrafficUnavailable
from .toll_provider import get_toll_calculator


TIMING_DETAILS = ("arrivo_fisico", "inizio_servizio", "lateness_min", "time_window_violation",
                  "arrival_at", "service_start_at", "departure_at", "lat", "lon")


def json_data(value, default=None):
    try:
        return json.loads(value) if value else ({} if default is None else default)
    except (ValueError, TypeError):
        return {} if default is None else default


def _dump(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def initialize_snapshot(plan, result):
    previous = json_data(plan.routing_snapshot_json)
    ordered = [dict(d) for d in result["ordered"]]
    depot = result.get("depot_coord") or (
        {"lat": plan.deposit.lat, "lon": plan.deposit.lon} if plan.deposit else None)
    points = [depot] + [d.get("coord") or {"lat": d.get("lat"), "lon": d.get("lon")} for d in ordered]
    if any(not p or p.get("lat") is None or p.get("lon") is None for p in points):
        points = []
    if plan.rientro_deposito and ordered and points:
        points.append(dict(depot))
    base_legs = [{"km": d.get("km_tappa") or 0, "min": d.get("minuti_tappa") or 0} for d in ordered]
    if plan.rientro_deposito and ordered:
        base_legs.append(result.get("base_return_leg") or {
            "km": max(0, result["total_km"] - sum(d["km"] for d in base_legs)),
            "min": max(0, result["total_min"] - sum(d["min"] for d in base_legs) -
                       sum(float(d.get("tempo_scarico_min") or 0) + float(d.get("attesa_min") or 0) for d in ordered))})
    plan.routing_snapshot_json = _dump({
        "revision": int(previous.get("revision") or 0) + 1,
        "points": points, "deliveries": ordered, "base_legs": base_legs,
        "base_total_min": result["total_min"], "base_return_time": result["return_time"]})
    plan.base_routing_provider = result.get("base_routing_provider", "osrm")
    plan.traffic_provider = "none"
    plan.traffic_status = "stale" if plan.status == "programmato" else "not_requested"
    plan.traffic_calculated_at = None
    plan.traffic_departure_at = None
    plan.traffic_version = 0
    plan.traffic_result_json = None
    plan.road_geometry_json = None
    plan.toll_provider = "internal-osm"
    plan.toll_status = "unavailable"
    plan.toll_estimated_eur = None
    plan.toll_details_json = None


def routing_metadata(plan):
    status = plan.traffic_status or "legacy"
    base = plan.base_routing_provider or "legacy"
    traffic = status == "updated"
    label = ("ETA con traffico aggiornato" if traffic else
             "Tempi approssimativi: routing stradale non disponibile" if base in ("estimated", "mixed") else
             "ETA storico salvato" if base == "legacy" else "Tempi stradali stimati senza traffico")
    result = json_data(plan.traffic_result_json)
    toll = json_data(plan.toll_details_json)
    calculated_at = plan.traffic_calculated_at
    return {
        "base_routing_provider": base, "traffic_provider": plan.traffic_provider or "none",
        "traffic_status": status, "traffic_calculated_at": (calculated_at.isoformat() + "Z") if calculated_at else None,
        "traffic_departure_at": plan.traffic_departure_at.isoformat() if plan.traffic_departure_at else None,
        "traffic_version": plan.traffic_version or 0, "traffic_legs": result.get("legs") or [],
        "eta_type": "traffic" if traffic else ("approximate" if base in ("estimated", "mixed") else "road" if base == "osrm" else "legacy"),
        "eta_label": label, "toll_provider": plan.toll_provider or "internal-osm",
        "toll_status": plan.toll_status or "unavailable", "toll_estimated_eur": plan.toll_estimated_eur,
        "toll_label": "Pedaggio stimato", "toll_details": toll,
        "costo_carburante": plan.costo_carburante, "costo_totale": plan.costo_totale,
        "operating_cost_status": "estimated" if plan.toll_status == "estimated" else "partial",
    }


def _legacy_snapshot(plan):
    # Used only by explicit programming/refresh, never by a read of historical data.
    ordered = []
    for d in sorted(plan.deliveries or [], key=lambda d: d.ordine or 0):
        item = {name: getattr(d, name) for name in (
            "customer_id", "cliente_nome", "indirizzo", "tempo_scarico_min", "peso_kg", "colli",
            "ztl", "sponda", "ordine", "km_tappa", "minuti_tappa", "attesa_min")}
        for name in ("scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a"):
            item[name] = time_to_hhmm(getattr(d, name))
        saved = json_data(d.optimizer_details)
        if saved.get("lat") is not None and saved.get("lon") is not None:
            item["coord"] = {"lat": saved["lat"], "lon": saved["lon"]}
        elif d.customer and d.customer.user_id == plan.user_id:
            item["coord"] = {"lat": d.customer.lat, "lon": d.customer.lon}
        ordered.append(item)
    initialize_snapshot(plan, {"ordered": ordered, "total_km": plan.totale_km,
                               "total_min": plan.totale_minuti,
                               "return_time": time_to_hhmm(plan.orario_rientro_stimato),
                               "base_routing_provider": "legacy"})
    return json_data(plan.routing_snapshot_json)


def evaluate_legs(snapshot, legs, plan, *, return_depot=None):
    from ..optimizer import _evaluate_fixed_sequence
    rows = [dict(d, _matrix_index=i + 1) for i, d in enumerate(snapshot["deliveries"])]
    matrix = {(i, i + 1): {"km": snapshot["base_legs"][i]["km"], "min": leg["duration"] / 60}
              for i, leg in enumerate(legs[:len(rows)])}
    if plan.rientro_deposito and len(legs) > len(rows):
        matrix[len(rows), 0] = {"km": snapshot["base_legs"][-1]["km"], "min": legs[-1]["duration"] / 60}
    include_return = plan.rientro_deposito if return_depot is None else return_depot
    return _evaluate_fixed_sequence(rows[:min(len(rows), len(legs))], matrix, [],
                                    return_depot=include_return, start_time=plan.orario_partenza)


def _persist_timing(plan, result, departure):
    cursor = datetime.fromisoformat(departure.replace("Z", "+00:00"))
    deliveries = sorted(plan.deliveries or [], key=lambda d: d.ordine or 0)
    for saved, timing in zip(deliveries, result["ordered"]):
        for name in ("minuti_tappa", "attesa_min", "warning"):
            setattr(saved, name, timing.get(name))
        saved.arrivo_stimato = parse_time_value(timing["arrivo_stimato"])
        saved.partenza_stimata = parse_time_value(timing["partenza_stimata"])
        cursor += timedelta(minutes=float(timing["minuti_tappa"]))
        details = json_data(saved.optimizer_details)
        details.update({key: timing[key] for key in TIMING_DETAILS if key in timing})
        details["arrival_at"] = cursor.astimezone(LOCAL_TZ).isoformat()
        cursor += timedelta(minutes=float(timing.get("attesa_min") or 0))
        details["service_start_at"] = cursor.astimezone(LOCAL_TZ).isoformat()
        cursor += timedelta(minutes=float(timing.get("tempo_scarico_min") or 0))
        details["departure_at"] = cursor.astimezone(LOCAL_TZ).isoformat()
        saved.optimizer_details = _dump(details)
    plan.totale_minuti = result["total_min"]
    plan.orario_rientro_stimato = parse_time_value(result["return_time"])


def enrich_final_route(db, plan, *, force=False):
    """Caller owns the transaction/row lock. One traffic request per valid segment."""
    from ..optimizer import _route_departure_time_iso
    snapshot = json_data(plan.routing_snapshot_json) or _legacy_snapshot(plan)
    revision = int(snapshot.get("revision") or 1)
    if not force and plan.traffic_version == revision and plan.traffic_status in ("updated", "unavailable", "disabled"):
        return
    departure = _route_departure_time_iso(plan.orario_partenza, plan.data_giro)
    points = snapshot.get("points") or []
    # Capture geometry/tolls once per revision. Failed attempts are persisted too.
    if not plan.toll_details_json:
        try:
            road = road_routing.road_route(points, db=db) if points else {}
            plan.road_geometry_json = _dump(road.get("geometries") or [])
            toll = get_toll_calculator(db).estimate(road, getattr(plan.vehicle, "toll_class", "B"), db=db)
        except (OSError, ValueError, TypeError, KeyError, road_routing.requests.RequestException):
            toll = {"provider": "internal-osm", "status": "unavailable", "amount_eur": None,
                    "label": "Pedaggio stimato", "version": 1}
        toll["calculated_at"] = datetime.now(timezone.utc).isoformat()
        plan.toll_provider, plan.toll_status = toll["provider"], toll["status"]
        plan.toll_estimated_eur = toll["amount_eur"]
        plan.toll_details_json = _dump(toll)
    plan.costo_totale = round(float(plan.costo_carburante or 0) + float(plan.toll_estimated_eur or 0), 2)
    traffic, failure = None, False
    try:
        provider = get_traffic_provider(db)
        def advance(legs):
            partial = evaluate_legs(snapshot, legs, plan, return_depot=False)
            return (datetime.fromisoformat(departure.replace("Z", "+00:00")) +
                    timedelta(minutes=partial["total_min"])).isoformat()
        if points and snapshot.get("deliveries"):
            traffic = provider.calculate(points, departure, db=db, user_id=plan.user_id,
                                         route_id=plan.id, advance_departure=advance)
        elif provider.name != "none":
            failure = True
    except (TrafficUnavailable, ValueError, KeyError, TypeError):
        failure = True
    if traffic:
        result = evaluate_legs(snapshot, traffic["legs"], plan)
        plan.traffic_status, plan.traffic_provider = "updated", traffic["provider"]
        plan.traffic_result_json = _dump(traffic)
        if not json_data(plan.road_geometry_json, []):
            plan.road_geometry_json = _dump(traffic.get("geometries") or [])
    else:
        # Restore OSRM timings after a failed real refresh; preserve the original order.
        base = [{"duration": leg["min"] * 60} for leg in snapshot["base_legs"]]
        result = evaluate_legs(snapshot, base, plan)
        plan.traffic_status = "unavailable" if failure else "disabled"
        plan.traffic_provider = "none"
        plan.traffic_result_json = _dump({"status": plan.traffic_status, "departure_time": departure,
                                         "legs": base, "version": 1})
    _persist_timing(plan, result, departure)
    plan.traffic_calculated_at = datetime.utcnow()
    plan.traffic_departure_at = datetime.fromisoformat(departure.replace("Z", "+00:00"))
    plan.traffic_version = revision
