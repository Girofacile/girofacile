import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..core.dependencies import current_user, owned
from ..core.utils import parse_date_value, date_to_iso, time_to_hhmm
from ..database import get_db
from ..models import RoutePlan, User, DeliveryStatus
from ..routers.routes import computed_route_status, route_status_label
from ..services.plans import require_feature
from ..services.agents_feature import agents_enabled
from ..services.ai_assistant import ensure_company_ai_allowed, run_ai_text
import json

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _report_label_agent(customer) -> str:
    if customer and customer.agent:
        from ..routers.agents import agent_full_name
        return agent_full_name(customer.agent)
    return "Cliente interno"


def _report_delivery_matches(delivery, agent_id: str = "", customer_id: str = "") -> bool:
    if customer_id:
        try:
            if int(customer_id) != (delivery.customer_id or 0):
                return False
        except Exception:
            pass
    if agent_id == "interno":
        if delivery.customer and delivery.customer.agent_id:
            return False
    elif agent_id:
        try:
            if not delivery.customer or int(agent_id) != (delivery.customer.agent_id or 0):
                return False
        except Exception:
            pass
    return True



def _actual_route_minutes(route) -> float:
    """Durata reale del giro chiuso, quando disponibile.

    Per i report preferiamo sempre i dati finali raccolti durante
    l'esecuzione: started_at/completed_at. Se il giro è vecchio o manca
    uno dei due valori, usiamo il valore salvato come fallback.
    """
    try:
        if route.started_at and route.completed_at:
            diff = (route.completed_at - route.started_at).total_seconds() / 60
            if diff >= 0:
                return float(diff)
    except Exception:
        pass
    return float(route.totale_minuti or 0)


def _actual_route_km(route, deliveries=None) -> float:
    """Km finali da usare nei report.

    Al momento GiroFacile non riceve un odometro/GPS finale dal telefono
    dell'autista. Quindi il dato finale più affidabile disponibile è il
    totale salvato sul giro al momento del calcolo/conferma, eventualmente
    ricalcolato con Google Routes. Se in futuro salveremo km reali da GPS,
    questo helper sarà l'unico punto da aggiornare.
    """
    return float(route.totale_km or 0)


def _actual_route_liters(route, km: float) -> float:
    # Compatibilità report legacy: per mezzi elettrici non sommiamo kWh nella colonna "Litri".
    try:
        if getattr(route, "energy_type", None) == "elettrico":
            return 0.0
        if getattr(route, "energy_quantity_primary", 0):
            return float(route.energy_quantity_primary or 0)
        consumo = float(route.vehicle.consumo_l_100km or 0) if route.vehicle else 0
        if consumo > 0:
            return (km * consumo) / 100
    except Exception:
        pass
    return float(route.litri_stimati or 0)


def _actual_route_cost(route, liters: float) -> float:
    try:
        # Dalla V89.5 il costo salvato è lo snapshot storico di carburante + eventuale energia elettrica.
        if getattr(route, "energy_type", None):
            return float(route.costo_carburante or 0)
        price = float(route.prezzo_carburante_litro or 0)
        if price > 0:
            return liters * price
    except Exception:
        pass
    return float(route.costo_carburante or 0)


def build_report_data(
    db: Session, user: User,
    date_from: str = "", date_to: str = "",
    agent_id: str = "", customer_id: str = "",
    driver_id: str = "", vehicle_id: str = "",
    status: str = "",
) -> dict:
    show_agents = agents_enabled(user)
    if not show_agents:
        agent_id = ""
    query = owned(db.query(RoutePlan), RoutePlan, user)
    if date_from:
        query = query.filter(RoutePlan.data_giro >= parse_date_value(date_from))
    if date_to:
        query = query.filter(RoutePlan.data_giro <= parse_date_value(date_to))
    if driver_id:
        try:
            query = query.filter(RoutePlan.driver_id == int(driver_id))
        except Exception:
            pass
    if vehicle_id:
        try:
            query = query.filter(RoutePlan.vehicle_id == int(vehicle_id))
        except Exception:
            pass

    raw_routes = query.order_by(RoutePlan.data_giro.asc(), RoutePlan.orario_partenza.asc()).all()
    selected_routes = []
    route_deliveries = {}

    for route in raw_routes:
        st = computed_route_status(route)
        # I report operativi usano solo giri conclusi: i valori dei giri
        # programmati/in corso sono stime di pianificazione, non consuntivi.
        if st != "completato":
            continue
        if status and status != "completato":
            continue
        deliveries = [d for d in sorted(route.deliveries or [], key=lambda x: x.ordine or 0)
                      if _report_delivery_matches(d, agent_id, customer_id)]
        if (agent_id or customer_id) and not deliveries:
            continue
        if not (agent_id or customer_id):
            deliveries = sorted(route.deliveries or [], key=lambda x: x.ordine or 0)
        selected_routes.append(route)
        route_deliveries[route.id] = deliveries

    route_actuals = {}

    def actuals_for(route, deliveries=None):
        if route.id not in route_actuals:
            km = _actual_route_km(route, deliveries)
            minutes = _actual_route_minutes(route)
            liters = _actual_route_liters(route, km)
            cost = _actual_route_cost(route, liters)
            route_actuals[route.id] = {"km": km, "min": minutes, "litri": liters, "costo": cost}
        return route_actuals[route.id]

    def add_metric(group, key, deliveries_count, route):
        actual = actuals_for(route)
        row = group.setdefault(key, {"nome": key, "giri": set(), "consegne": 0, "km": 0.0, "ore": 0.0, "litri": 0.0, "costo": 0.0})
        row["giri"].add(route.id)
        row["consegne"] += deliveries_count
        row["km"] += actual["km"]
        row["ore"] += actual["min"] / 60
        row["litri"] += actual["litri"]
        row["costo"] += actual["costo"]

    by_day, by_agent, by_driver, by_vehicle, by_customer = {}, {}, {}, {}, {}
    status_counts = {}
    total_deliveries = 0

    for route in selected_routes:
        deliveries = route_deliveries.get(route.id, [])
        status_rows = db.query(DeliveryStatus).filter(DeliveryStatus.route_plan_id == route.id).all()
        status_map = {x.delivery_id: x for x in status_rows}
        handled_deliveries = [d for d in deliveries if (status_map.get(d.id).status if status_map.get(d.id) else None) in ("completata", "mancata")]
        dc = len(handled_deliveries) if handled_deliveries else len(deliveries)
        total_deliveries += dc
        st = "completato"
        status_counts[st] = status_counts.get(st, 0) + 1
        actual = actuals_for(route, deliveries)
        day = date_to_iso(route.data_giro) or "-"
        day_row = by_day.setdefault(day, {"data": day, "consegne": 0, "km": 0.0, "costo": 0.0})
        day_row["consegne"] += dc
        day_row["km"] += actual["km"]
        day_row["costo"] += actual["costo"]
        driver_name = ((route.driver.nome + (" " + route.driver.cognome if route.driver.cognome else "")) if route.driver else "Non assegnato")
        vehicle_name = ((route.vehicle.nome + (f" · {route.vehicle.targa}" if route.vehicle and route.vehicle.targa else "")) if route.vehicle else "Nessun mezzo")
        add_metric(by_driver, driver_name, dc, route)
        add_metric(by_vehicle, vehicle_name, dc, route)
        seen_agents = set()
        for d in deliveries:
            ag = _report_label_agent(d.customer)
            cust = d.cliente_nome or (d.customer.nome if d.customer else "Cliente")
            c_row = by_customer.setdefault(cust, {"nome": cust, "consegne": 0, "giri": set(), "km": 0.0})
            c_row["consegne"] += 1
            c_row["giri"].add(route.id)
            c_row["km"] += float(d.km_tappa or 0)
            seen_agents.add(ag)
        for ag in seen_agents or {"Cliente interno"}:
            count_agent = sum(1 for d in deliveries if _report_label_agent(d.customer) == ag)
            add_metric(by_agent, ag, count_agent, route)

    total_routes = len(selected_routes)
    total_km = sum(actuals_for(r)["km"] for r in selected_routes)
    total_min = sum(actuals_for(r)["min"] for r in selected_routes)
    total_litri = sum(actuals_for(r)["litri"] for r in selected_routes)
    total_cost = sum(actuals_for(r)["costo"] for r in selected_routes)

    def finalize_group(group, limit=None):
        rows = []
        for row in group.values():
            giri_count = len(row.get("giri", []))
            rows.append({
                "nome": row["nome"], "giri": giri_count, "consegne": int(row["consegne"]),
                "km": round(row["km"], 2), "ore": round(row["ore"], 2),
                "litri": round(row["litri"], 2), "costo": round(row["costo"], 2),
                "costo_medio_giro": round(row["costo"] / giri_count, 2) if giri_count else 0,
                "consegne_per_giro": round(row["consegne"] / giri_count, 2) if giri_count else 0,
            })
        rows.sort(key=lambda x: (x["consegne"], x["km"]), reverse=True)
        return rows[:limit] if limit else rows

    top_customers = sorted([
        {"nome": row["nome"], "consegne": row["consegne"], "giri": len(row["giri"]), "km_tappe": round(row["km"], 2)}
        for row in by_customer.values()
    ], key=lambda x: x["consegne"], reverse=True)

    detail_routes = sorted([{
        "id": route.id, "nome": route.nome, "data_giro": date_to_iso(route.data_giro),
        "orario_partenza": time_to_hhmm(route.orario_partenza), "orario_rientro_stimato": time_to_hhmm(route.orario_rientro_stimato),
        "status": computed_route_status(route), "status_label": route_status_label(computed_route_status(route)),
        "driver_name": ((route.driver.nome + (" " + route.driver.cognome if route.driver.cognome else "")) if route.driver else "Non assegnato"),
        "vehicle_name": (route.vehicle.nome if route.vehicle else "Nessun mezzo"),
        "consegne": len(route_deliveries.get(route.id, [])),
        "km": round(actuals_for(route)["km"], 2), "ore": round(actuals_for(route)["min"] / 60, 2),
        "litri": round(actuals_for(route)["litri"], 2), "costo": round(actuals_for(route)["costo"], 2),
    } for route in selected_routes], key=lambda r: (r["data_giro"], r["orario_partenza"]), reverse=True)

    days = [by_day[k] for k in sorted(by_day.keys())]
    for d in days:
        d["km"] = round(d["km"], 2)
        d["costo"] = round(d["costo"], 2)

    status_labels = {"programmato": "Programmato", "in_corso": "In corso", "da_completare": "Da completare", "completato": "Completato", "annullato": "Annullato"}

    return {
        "filters": {"date_from": date_from, "date_to": date_to, "agent_id": agent_id, "customer_id": customer_id, "driver_id": driver_id, "vehicle_id": vehicle_id, "status": status},
        "metrics": {
            "giri_effettuati": total_routes, "consegne_totali": total_deliveries,
            "km_totali": round(total_km, 2), "ore_totali": round(total_min / 60, 2),
            "litri_stimati": round(total_litri, 2), "costo_carburante": round(total_cost, 2),
            "costo_medio_giro": round(total_cost / total_routes, 2) if total_routes else 0,
            "costo_medio_consegna": round(total_cost / total_deliveries, 2) if total_deliveries else 0,
            "km_medi_giro": round(total_km / total_routes, 2) if total_routes else 0,
            "consegne_medie_giro": round(total_deliveries / total_routes, 2) if total_routes else 0,
        },
        "charts": {
            "andamento": days,
            "agenti": finalize_group(by_agent, 8) if show_agents else [],
            "autisti": finalize_group(by_driver, 8),
            "mezzi": finalize_group(by_vehicle, 8),
            "clienti": top_customers[:10],
            "stati": [{"nome": status_labels.get(k, k), "valore": v} for k, v in status_counts.items()],
        },
        "tables": {
            "agenti": finalize_group(by_agent) if show_agents else [],
            "autisti": finalize_group(by_driver),
            "mezzi": finalize_group(by_vehicle),
            "clienti": top_customers,
            "giri": detail_routes,
        },
        "insights": [
            {"titolo": "Media consegne per giro", "testo": f"{round(total_deliveries / total_routes, 2) if total_routes else 0} consegne medie per giro nel periodo selezionato."},
            {"titolo": "Costo medio consegna", "testo": f"€ {round(total_cost / total_deliveries, 2) if total_deliveries else 0} di carburante consuntivo per consegna."},
            {"titolo": "Utilizzo risorse", "testo": f"{len(by_driver)} autisti e {len(by_vehicle)} mezzi presenti nei giri completati filtrati."},
        ],
    }


@router.get("/summary")
def reports_summary(
    date_from: str = "", date_to: str = "",
    agent_id: str = "", customer_id: str = "",
    driver_id: str = "", vehicle_id: str = "", status: str = "",
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    require_feature(user, "has_reports")
    return build_report_data(db, user, date_from, date_to, agent_id, customer_id, driver_id, vehicle_id, status)



@router.get("/ai-summary")
def reports_ai_summary(
    date_from: str = "", date_to: str = "",
    agent_id: str = "", customer_id: str = "",
    driver_id: str = "", vehicle_id: str = "", status: str = "",
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    require_feature(user, "has_reports")
    ensure_company_ai_allowed(user, db)
    data = build_report_data(db, user, date_from, date_to, agent_id, customer_id, driver_id, vehicle_id, status)
    context = {
        "sector": user.company_sector or user.company_activity_type or "",
        "metrics": data.get("metrics"),
        "insights": data.get("insights"),
        "top_drivers": (data.get("charts") or {}).get("autisti", [])[:5],
        "top_vehicles": (data.get("charts") or {}).get("mezzi", [])[:5],
        "top_customers": (data.get("charts") or {}).get("clienti", [])[:5],
        "routes": (data.get("tables") or {}).get("giri", [])[:10],
    }
    prompt = """Genera un breve report operativo in italiano per l'azienda GiroFacile.
Massimo 8 righe. Evidenzia numeri principali, eventuali criticità e 1-2 suggerimenti pratici.
Adatta il linguaggio al settore aziendale. Non inventare dati e non usare tono pubblicitario.
"""
    return run_ai_text(
        db, task="report_summary", user_id=user.id,
        system_prompt="Sei l'assistente AI di GiroFacile per report operativi aziendali. Scrivi in modo chiaro, breve e pratico.",
        user_prompt=prompt + "\nCONTESTO JSON:\n" + json.dumps(context, ensure_ascii=False, default=str),
        context=context,
    )

@router.get("/export")
def reports_export(
    date_from: str = "", date_to: str = "",
    agent_id: str = "", customer_id: str = "",
    driver_id: str = "", vehicle_id: str = "", status: str = "",
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    require_feature(user, "has_export")
    data = build_report_data(db, user, date_from, date_to, agent_id, customer_id, driver_id, vehicle_id, status)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Data", "Giro", "Stato", "Autista", "Mezzo", "Consegne", "Km", "Ore", "Litri", "Costo carburante"])
    for row in data["tables"]["giri"]:
        writer.writerow([row["data_giro"], row["nome"], row["status_label"], row["driver_name"], row["vehicle_name"], row["consegne"], row["km"], row["ore"], row["litri"], row["costo"]])
    return Response(
        content=output.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report_girofacile.csv"},
    )
