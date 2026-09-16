from datetime import datetime, timedelta
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.dependencies import current_user, owned
from ..core.utils import local_now, local_today, local_today_iso, minutes_from_hhmm, parse_date_value, parse_time_value, date_to_iso, time_to_hhmm
from ..database import get_db
from ..models import Customer, Delivery, DeliveryStatus, Deposit, Driver, RoutePlan, User, Vehicle, ChatMessage
from ..optimizer import optimize_route, recalculate_manual_route, google_route_polyline
from ..schemas import ManualRoutePlanIn, RoutePlanIn
from ..services.plans import check_daily_route_limit
from ..services.error_monitor import log_exception
from ..services.api_usage import log_api_usage
from ..services.ai_assistant import ensure_company_ai_allowed, run_ai_text
from ..services.platform_settings import google_maps_api_key
import json

router = APIRouter(tags=["routes"])

DEFAULT_AVAILABILITY_PREVIEW_MINUTES = 240


def _is_route_api_configuration_error(exc: Exception) -> bool:
    """Riconosce errori operativi da notificare al Super Admin.

    Alcuni errori di pianificazione arrivano come ValueError perché vengono
    mostrati all'utente nella Dashboard. Quelli legati a servizi esterni
    o configurazioni tecniche, però, non sono semplici errori utente: vanno
    registrati nel monitoraggio.
    """
    msg = str(exc or "").lower()
    keywords = (
        "google routes",
        "routes api",
        "api key",
        "fatturazione google",
        "non disponibile",
        "non configurato",
        "google cloud",
    )
    return any(k in msg for k in keywords)


# -----------------------------------------------------------------------
# Helpers stato giro
# -----------------------------------------------------------------------

def computed_route_status(plan: RoutePlan) -> str:
    """Stato operativo del giro.

    Regola business: un giro diventa in corso solo quando l'autista
    preme “Avvia giro” dal portale autista. Non viene più promosso
    automaticamente in base all'orario pianificato.
    """
    stored = (getattr(plan, "status", None) or "programmato").lower()
    if stored in ("bozza", "programmato", "in_corso", "completato", "annullato"):
        return stored
    return "programmato"


def route_status_label(status: str) -> str:
    return {
        "bozza": "Bozza",
        "programmato": "Programmato",
        "in_corso": "In corso",
        "da_completare": "Da completare",
        "completato": "Completato",
        "annullato": "Annullato",
    }.get(status or "", "Programmato")


def _hhmm_from_minutes(total: int | None) -> str | None:
    if total is None:
        return None
    total = int(total) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _datetime_to_local_minutes(value) -> int | None:
    if not value:
        return None
    try:
        # Nel DB le date sono salvate senza timezone. Per il monitoraggio operativo
        # usiamo ora/minuto locale percepito dall'utente.
        return int(value.hour) * 60 + int(value.minute)
    except Exception:
        return None


def live_route_schedule(plan: RoutePlan, status_map: dict[int, DeliveryStatus] | None = None) -> dict:
    """Calcola orari aggiornati per le fermate e rientro.

    Mostra solo l'orario operativo aggiornato: se il giro parte in ritardo
    o una consegna viene chiusa più tardi, tutte le fermate successive
    slittano automaticamente.
    """
    deliveries = sorted(plan.deliveries or [], key=lambda x: x.ordine or 0)
    status_map = status_map or {}
    start_min = minutes_from_hhmm(plan.orario_partenza) or 0
    shift = 0
    started_at = getattr(plan, "started_at", None)
    if computed_route_status(plan) == "in_corso" and started_at:
        real_start = _datetime_to_local_minutes(started_at)
        if real_start is not None:
            shift = real_start - start_min

    # Se l'autista chiude una fermata più tardi rispetto alla partenza prevista
    # della stessa fermata, lo scostamento diventa il nuovo slittamento globale.
    for d in deliveries:
        ds = status_map.get(d.id)
        if not ds or ds.status not in ("completata", "mancata") or not ds.completata_il:
            continue
        real_done = _datetime_to_local_minutes(ds.completata_il)
        planned_done = minutes_from_hhmm(d.partenza_stimata or d.arrivo_stimato)
        if real_done is not None and planned_done is not None:
            shift = real_done - planned_done

    delivery_times = {}
    running_shift = 0
    if computed_route_status(plan) == "in_corso" and started_at:
        real_start = _datetime_to_local_minutes(started_at)
        if real_start is not None:
            running_shift = real_start - start_min

    for d in deliveries:
        ds = status_map.get(d.id)
        planned_arrival = minutes_from_hhmm(d.arrivo_stimato)
        planned_departure = minutes_from_hhmm(d.partenza_stimata or d.arrivo_stimato)
        if ds and ds.status in ("completata", "mancata") and ds.completata_il:
            real_done = _datetime_to_local_minutes(ds.completata_il)
            delivery_times[d.id] = _hhmm_from_minutes(real_done if real_done is not None else (planned_arrival or start_min) + running_shift)
            if real_done is not None and planned_departure is not None:
                running_shift = real_done - planned_departure
        else:
            delivery_times[d.id] = _hhmm_from_minutes((planned_arrival if planned_arrival is not None else start_min) + running_shift)

    rientro_min = minutes_from_hhmm(plan.orario_rientro_stimato)
    if rientro_min is None:
        try:
            rientro_min = start_min + int(float(plan.totale_minuti or 0))
        except Exception:
            rientro_min = start_min
    return {
        "delivery_times": delivery_times,
        "rientro_stimato_aggiornato": _hhmm_from_minutes(rientro_min + running_shift),
    }


# -----------------------------------------------------------------------
# Helpers disponibilità risorse
# -----------------------------------------------------------------------

def _route_interval_minutes(plan: RoutePlan):
    start = minutes_from_hhmm(plan.orario_partenza) or 0
    end = minutes_from_hhmm(plan.orario_rientro_stimato)
    if end is None:
        try:
            duration = int(float(plan.totale_minuti or 0))
        except Exception:
            duration = 0
        end = start + (duration if duration > 0 else 240)
    if end < start:
        end = start
    return start, end


def _resource_busy_maps(db, user, data_giro, start_min, end_min=None, exclude_route_id=None):
    busy_drivers = {}
    busy_vehicles = {}
    q = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.data_giro == parse_date_value(data_giro))
    if exclude_route_id:
        q = q.filter(RoutePlan.id != exclude_route_id)
    for plan in q.all():
        st = (getattr(plan, "status", None) or "programmato").lower()
        if st in ("completato", "annullato"):
            continue
        p_status = computed_route_status(plan)
        if p_status in ("bozza", "completato", "annullato"):
            continue
        p_start, p_end = _route_interval_minutes(plan)
        overlaps = (p_start <= start_min <= p_end) if end_min is None else (start_min < p_end and end_min > p_start)
        if not overlaps:
            continue
        payload = {
            "route_id": plan.id, "route_name": plan.nome,
            "busy_from": time_to_hhmm(plan.orario_partenza),
            "busy_until": time_to_hhmm(plan.orario_rientro_stimato) or f"{p_end//60:02d}:{p_end%60:02d}",
            "status": route_status_label(p_status),
        }
        if plan.driver_id:
            busy_drivers[plan.driver_id] = payload
        if plan.vehicle_id:
            busy_vehicles[plan.vehicle_id] = payload
    return busy_drivers, busy_vehicles


def _check_resource_overlap(db, user, data, start_min, end_min, exclude_route_id=None):
    busy_drivers, busy_vehicles = _resource_busy_maps(
        db, user, data.data_giro, start_min, end_min, exclude_route_id=exclude_route_id
    )
    if data.driver_id and data.driver_id in busy_drivers:
        b = busy_drivers[data.driver_id]
        raise HTTPException(400, f"Autista non disponibile: già assegnato a '{b['route_name']}' dalle {b['busy_from']} alle {b['busy_until']}")
    if data.vehicle_id and data.vehicle_id in busy_vehicles:
        b = busy_vehicles[data.vehicle_id]
        raise HTTPException(400, f"Mezzo non disponibile: già assegnato a '{b['route_name']}' dalle {b['busy_from']} alle {b['busy_until']}")


def ensure_not_past_route_date(data_giro):
    parsed = parse_date_value(data_giro)
    if not parsed:
        raise HTTPException(400, "Seleziona una data giro valida")
    if parsed < local_today():
        raise HTTPException(400, "Non puoi programmare un giro in una data precedente a oggi")


def build_vehicle_dict(vehicle):
    if not vehicle:
        return None
    return {
        "id": vehicle.id, "nome": vehicle.nome, "targa": vehicle.targa,
        "ha_sponda": bool(vehicle.ha_sponda), "accesso_ztl": bool(vehicle.accesso_ztl),
    }


# -----------------------------------------------------------------------
# Serializzazione
# -----------------------------------------------------------------------

def route_response(plan, result):
    live_sched = live_route_schedule(plan, {})
    return {
        "id": plan.id, "nome": plan.nome, "data_giro": date_to_iso(plan.data_giro),
        "orario_partenza": time_to_hhmm(plan.orario_partenza), "orario_rientro_stimato": time_to_hhmm(plan.orario_rientro_stimato),
        "started_at": (plan.started_at.isoformat() if getattr(plan, "started_at", None) else None),
        "completed_at": (plan.completed_at.isoformat() if getattr(plan, "completed_at", None) else None),
        "rientro_stimato_aggiornato": live_sched.get("rientro_stimato_aggiornato"),
        "deposit_id": plan.deposit_id, "vehicle_id": plan.vehicle_id, "driver_id": plan.driver_id,
        "vehicle_name": ((plan.vehicle.nome + (" · " + plan.vehicle.targa if plan.vehicle.targa else "")) if plan.vehicle else None),
        "driver_name": ((plan.driver.nome + (" " + plan.driver.cognome if plan.driver.cognome else "")) if plan.driver else None),
        "driver_email": (plan.driver.email if plan.driver else None),
        "rientro_deposito": plan.rientro_deposito,
        "totale_km": plan.totale_km, "totale_minuti": plan.totale_minuti,
        "litri_stimati": plan.litri_stimati, "costo_carburante": plan.costo_carburante,
        "costo_totale": plan.costo_totale, "google_maps_url": plan.google_maps_url,
        "status": computed_route_status(plan), "status_label": route_status_label(computed_route_status(plan)),
        "consegne": result["ordered"],
    }


def serialize_route(plan):
    consegne = sorted(plan.deliveries, key=lambda x: x.ordine or 0)
    status_map = {ds.delivery_id: ds for ds in getattr(plan, "delivery_statuses", [])} if hasattr(plan, "delivery_statuses") else {}
    # Fallback sicuro: la relationship non è sempre caricata nelle vecchie installazioni.
    try:
        from sqlalchemy.orm import object_session
        sess = object_session(plan)
        if sess:
            status_map = {ds.delivery_id: ds for ds in sess.query(DeliveryStatus).filter(DeliveryStatus.route_plan_id == plan.id).all()}
    except Exception:
        pass
    live_sched = live_route_schedule(plan, status_map)
    live_delivery_times = live_sched.get("delivery_times", {})
    return {
        "id": plan.id, "nome": plan.nome, "data_giro": date_to_iso(plan.data_giro),
        "orario_partenza": time_to_hhmm(plan.orario_partenza), "orario_rientro_stimato": time_to_hhmm(plan.orario_rientro_stimato),
        "started_at": (plan.started_at.isoformat() if getattr(plan, "started_at", None) else None),
        "completed_at": (plan.completed_at.isoformat() if getattr(plan, "completed_at", None) else None),
        "rientro_stimato_aggiornato": live_sched.get("rientro_stimato_aggiornato"),
        "deposit_id": plan.deposit_id, "vehicle_id": plan.vehicle_id, "driver_id": plan.driver_id,
        "vehicle_name": ((plan.vehicle.nome + (" · " + plan.vehicle.targa if plan.vehicle.targa else "")) if plan.vehicle else None),
        "driver_name": ((plan.driver.nome + (" " + plan.driver.cognome if plan.driver.cognome else "")) if plan.driver else None),
        "driver_email": (plan.driver.email if plan.driver else None),
        "rientro_deposito": plan.rientro_deposito, "prezzo_carburante_litro": plan.prezzo_carburante_litro,
        "totale_km": plan.totale_km, "totale_minuti": plan.totale_minuti,
        "litri_stimati": plan.litri_stimati, "costo_carburante": plan.costo_carburante,
        "costo_totale": plan.costo_totale, "google_maps_url": plan.google_maps_url,
        "status": computed_route_status(plan), "status_label": route_status_label(computed_route_status(plan)),
        "consegne": [{
            "id": d.id, "customer_id": d.customer_id, "cliente_nome": d.cliente_nome, "indirizzo": d.indirizzo,
            "peso_kg": d.peso_kg, "colli": d.colli,
            "scarico_mattina_da": time_to_hhmm(d.scarico_mattina_da), "scarico_mattina_a": time_to_hhmm(d.scarico_mattina_a),
            "scarico_pomeriggio_da": time_to_hhmm(d.scarico_pomeriggio_da), "scarico_pomeriggio_a": time_to_hhmm(d.scarico_pomeriggio_a),
            "tempo_scarico_min": d.tempo_scarico_min, "ztl": d.ztl, "sponda": d.sponda, "note": d.note,
            "ordine": d.ordine, "km_tappa": d.km_tappa, "minuti_tappa": d.minuti_tappa,
            "arrivo_stimato": time_to_hhmm(d.arrivo_stimato), "partenza_stimata": time_to_hhmm(d.partenza_stimata),
            "arrivo_stimato_aggiornato": live_delivery_times.get(d.id) or time_to_hhmm(d.arrivo_stimato),
            "attesa_min": d.attesa_min, "warning": d.warning,
            "delivery_status": (status_map.get(d.id).status if status_map.get(d.id) else "in_attesa"),
            "motivo_mancata": (status_map.get(d.id).motivo_mancata if status_map.get(d.id) else None),
            "tempo_scarico_effettivo": (status_map.get(d.id).tempo_scarico_effettivo if status_map.get(d.id) else None),
            "note_operatore": (status_map.get(d.id).note_operatore if status_map.get(d.id) else None),
            "completata_il": (status_map.get(d.id).completata_il.isoformat() if status_map.get(d.id) and status_map.get(d.id).completata_il else None),
            "signature_data": (status_map.get(d.id).signature_data if status_map.get(d.id) else None),
            "signed_by_name": (status_map.get(d.id).signed_by_name if status_map.get(d.id) else None),
            "signed_at": (status_map.get(d.id).signed_at.isoformat() if status_map.get(d.id) and status_map.get(d.id).signed_at else None),
            "signature_note": (status_map.get(d.id).signature_note if status_map.get(d.id) else None),
        } for d in consegne],
    }


def save_route_result(db, user, data, result, vehicle, route_id=None):
    consumo = vehicle.consumo_l_100km if vehicle else 8.5
    litri = result["total_km"] * consumo / 100
    costo_carburante = litri * data.prezzo_carburante_litro
    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first() if route_id else None
    if not plan:
        plan = RoutePlan(user_id=user.id)
        db.add(plan)
    else:
        db.query(Delivery).filter(Delivery.route_plan_id == plan.id).delete(synchronize_session=False)
    plan.nome = (data.nome or "").strip() or "Giro consegne"
    plan.data_giro = parse_date_value(data.data_giro)
    plan.orario_partenza = parse_time_value(data.orario_partenza)
    plan.orario_rientro_stimato = parse_time_value(result["return_time"])
    plan.deposit_id = data.deposit_id
    plan.vehicle_id = data.vehicle_id
    plan.driver_id = data.driver_id
    plan.rientro_deposito = data.rientro_deposito
    plan.prezzo_carburante_litro = data.prezzo_carburante_litro
    plan.totale_km = result["total_km"]
    plan.totale_minuti = result["total_min"]
    plan.litri_stimati = round(litri, 2)
    plan.costo_carburante = round(costo_carburante, 2)
    plan.costo_totale = round(costo_carburante, 2)
    plan.google_maps_url = result["google_maps_url"]
    # Il calcolo genera solo una bozza/anteprima.
    # Il giro diventa visibile tra i programmati solo quando l'utente preme “Programma giro”.
    if route_id:
        current_status = computed_route_status(plan)
        plan.status = current_status if current_status in ("programmato", "in_corso", "completato", "annullato") else "bozza"
    else:
        plan.status = "bozza"
    plan.completed_at = None
    plan.cancelled_at = None
    db.flush()
    for item in result["ordered"]:
        delivery_data = dict(item)
        for extra in ("coord", "lat", "lon", "stato_geocodifica", "indirizzo_geocodificato"):
            delivery_data.pop(extra, None)
        for _f in ["scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a", "arrivo_stimato", "partenza_stimata"]:
            if _f in delivery_data:
                delivery_data[_f] = parse_time_value(delivery_data.get(_f))
        db.add(Delivery(route_plan_id=plan.id, **delivery_data))
    db.commit()
    db.refresh(plan)
    return plan


# -----------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------

@router.get("/api/resources/availability")
def resources_availability(
    data_giro: str, orario: str,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    start_min = minutes_from_hhmm(orario)
    if not data_giro or start_min is None:
        raise HTTPException(400, "Seleziona data e orario di partenza")
    ensure_not_past_route_date(data_giro)
    preview_end_min = start_min + DEFAULT_AVAILABILITY_PREVIEW_MINUTES
    busy_drivers, busy_vehicles = _resource_busy_maps(db, user, data_giro, start_min, preview_end_min)

    vehicles = []
    for v in owned(db.query(Vehicle), Vehicle, user).order_by(Vehicle.nome.asc()).all():
        busy = busy_vehicles.get(v.id)
        vehicles.append({
            "id": v.id, "nome": v.nome, "targa": v.targa, "consumo_l_100km": v.consumo_l_100km,
            "available": busy is None,
            "status": "Disponibile" if busy is None else "In uso",
            "note": "" if busy is None else f"In uso su {busy['route_name']} fino alle {busy['busy_until']}",
            "busy": busy,
        })

    drivers = []
    for d in owned(db.query(Driver), Driver, user).order_by(Driver.nome.asc(), Driver.cognome.asc()).all():
        busy = busy_drivers.get(d.id)
        full_name = ((d.nome or "") + (" " + d.cognome if d.cognome else "")).strip()
        drivers.append({
            "id": d.id, "nome": d.nome, "cognome": d.cognome, "full_name": full_name, "patente": d.patente,
            "available": busy is None,
            "status": "Disponibile" if busy is None else "In servizio",
            "note": "" if busy is None else f"In servizio su {busy['route_name']} fino alle {busy['busy_until']}",
            "busy": busy,
        })

    return {"vehicles": vehicles, "drivers": drivers}


@router.post("/api/routes/optimize")
def create_and_optimize_route(
    data: RoutePlanIn,
    request: Request,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    ensure_not_past_route_date(data.data_giro)
    check_daily_route_limit(user, db, data.data_giro)
    deposit = owned(db.query(Deposit), Deposit, user).filter(Deposit.id == data.deposit_id).first()
    if not deposit:
        raise HTTPException(400, "Deposito non trovato")
    vehicle = owned(db.query(Vehicle), Vehicle, user).filter(Vehicle.id == data.vehicle_id).first() if data.vehicle_id else None
    if data.driver_id:
        driver = owned(db.query(Driver), Driver, user).filter(Driver.id == data.driver_id).first()
        if not driver:
            raise HTTPException(400, "Autista non trovato")
    deliveries = [c.model_dump() for c in data.consegne]
    # V89.1: se le fasce orarie sono disattivate a livello azienda, il motore
    # le ignora completamente anche se restano salvate nell'anagrafica cliente.
    # In questo modo riattivando la funzione i dati storici tornano disponibili.
    if not bool(getattr(user, "has_time_windows", True)):
        for delivery in deliveries:
            delivery["scarico_mattina_da"] = None
            delivery["scarico_mattina_a"] = None
            delivery["scarico_pomeriggio_da"] = None
            delivery["scarico_pomeriggio_a"] = None
    for delivery in deliveries:
        if delivery.get("customer_id"):
            customer = owned(db.query(Customer), Customer, user).filter(Customer.id == delivery["customer_id"]).first()
            if customer and customer.lat is not None and customer.lon is not None:
                delivery["lat"] = customer.lat
                delivery["lon"] = customer.lon
                delivery["stato_geocodifica"] = customer.stato_geocodifica
                delivery["indirizzo_geocodificato"] = customer.indirizzo_geocodificato
    started_api = time.perf_counter()
    try:
        result = optimize_route(db, deposit, deliveries, build_vehicle_dict(vehicle), data.rientro_deposito, data.orario_partenza)
        log_api_usage(db, user_id=user.id, service="google_routes_matrix", action="Calcolo giro", endpoint="/api/routes/optimize", status="success", message=f"{len(deliveries)} consegne", response_ms=int((time.perf_counter()-started_api)*1000))
    except ValueError as e:
        log_api_usage(db, user_id=user.id, service="google_routes_matrix", action="Calcolo giro", endpoint="/api/routes/optimize", status="failed", message=str(e), response_ms=int((time.perf_counter()-started_api)*1000))
        # Gli errori Google Routes/configurazione arrivano come ValueError
        # per poter essere mostrati bene in Dashboard, ma sono errori tecnici
        # importanti e devono comparire nel pannello Super Admin.
        error_id = None
        if _is_route_api_configuration_error(e):
            error_id = log_exception(
                request,
                RuntimeError(f"Errore calcolo percorso: {str(e)}"),
                severity="high",
            )
        raise HTTPException(status_code=400, detail={"message": str(e), "error_id": error_id})
    except Exception as e:
        # Questo errore viene gestito e mostrato correttamente all'utente,
        # quindi non passa dal middleware globale. Lo registriamo qui per
        # renderlo visibile al Super Admin e inviare eventuale email.
        error_id = log_exception(
            request,
            RuntimeError(f"Errore calcolo percorso: {str(e)}"),
            severity="high",
        )
        raise HTTPException(status_code=500, detail={"message": f"Errore calcolo percorso: {str(e)}", "error_id": error_id})
    start_min = minutes_from_hhmm(data.orario_partenza) or 0
    end_min = start_min + int(float(result.get("total_min") or 0))
    _check_resource_overlap(db, user, data, start_min, end_min)
    plan = save_route_result(db, user, data, result, vehicle)
    return route_response(plan, result)


@router.post("/api/routes/recalculate-manual")
def recalc_manual_route(
    data: ManualRoutePlanIn,
    request: Request,
    db: Session = Depends(get_db), user: User = Depends(current_user),
):
    ensure_not_past_route_date(data.data_giro)
    deposit = owned(db.query(Deposit), Deposit, user).filter(Deposit.id == data.deposit_id).first()
    if not deposit:
        raise HTTPException(400, "Deposito non trovato")
    vehicle = owned(db.query(Vehicle), Vehicle, user).filter(Vehicle.id == data.vehicle_id).first() if data.vehicle_id else None
    if data.driver_id:
        driver = owned(db.query(Driver), Driver, user).filter(Driver.id == data.driver_id).first()
        if not driver:
            raise HTTPException(400, "Autista non trovato")
    deliveries = [c.model_dump() for c in data.consegne]
    for delivery in deliveries:
        if delivery.get("customer_id"):
            customer = owned(db.query(Customer), Customer, user).filter(Customer.id == delivery["customer_id"]).first()
            if customer and customer.lat is not None and customer.lon is not None:
                delivery["lat"] = customer.lat
                delivery["lon"] = customer.lon
                delivery["stato_geocodifica"] = customer.stato_geocodifica
                delivery["indirizzo_geocodificato"] = customer.indirizzo_geocodificato
    started_api = time.perf_counter()
    try:
        result = recalculate_manual_route(db, deposit, deliveries, build_vehicle_dict(vehicle), data.rientro_deposito, data.orario_partenza)
        log_api_usage(db, user_id=user.id, service="google_routes_matrix", action="Ricalcolo manuale giro", endpoint="/api/routes/recalculate-manual", status="success", message=f"{len(deliveries)} consegne", response_ms=int((time.perf_counter()-started_api)*1000))
    except ValueError as e:
        log_api_usage(db, user_id=user.id, service="google_routes_matrix", action="Ricalcolo manuale giro", endpoint="/api/routes/recalculate-manual", status="failed", message=str(e), response_ms=int((time.perf_counter()-started_api)*1000))
        error_id = None
        if _is_route_api_configuration_error(e):
            error_id = log_exception(
                request,
                RuntimeError(f"Errore ricalcolo percorso: {str(e)}"),
                severity="high",
            )
        raise HTTPException(status_code=400, detail={"message": str(e), "error_id": error_id})
    except Exception as e:
        error_id = log_exception(
            request,
            RuntimeError(f"Errore ricalcolo percorso: {str(e)}"),
            severity="high",
        )
        raise HTTPException(status_code=500, detail={"message": f"Errore ricalcolo percorso: {str(e)}", "error_id": error_id})
    start_min = minutes_from_hhmm(data.orario_partenza) or 0
    end_min = start_min + int(float(result.get("total_min") or 0))
    _check_resource_overlap(db, user, data, start_min, end_min, exclude_route_id=data.route_id)
    plan = save_route_result(db, user, data, result, vehicle, data.route_id)
    return route_response(plan, result)



@router.post("/api/routes/{route_id}/ai-explanation")
def route_ai_explanation(
    route_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Spiega in modo breve perché GiroFacile ha proposto quella sequenza.

L'AI non modifica il percorso: traduce in testo i vincoli già presenti
nel giro calcolato, adattando il linguaggio al settore aziendale.
"""
    ensure_company_ai_allowed(user, db)
    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")
    stops = []
    for d in sorted(plan.deliveries or [], key=lambda x: x.ordine or 0):
        windows = []
        if d.scarico_mattina_da or d.scarico_mattina_a:
            windows.append(f"mattina {time_to_hhmm(d.scarico_mattina_da) or ''}-{time_to_hhmm(d.scarico_mattina_a) or ''}".strip())
        if d.scarico_pomeriggio_da or d.scarico_pomeriggio_a:
            windows.append(f"pomeriggio {time_to_hhmm(d.scarico_pomeriggio_da) or ''}-{time_to_hhmm(d.scarico_pomeriggio_a) or ''}".strip())
        stops.append({
            "order": d.ordine,
            "name": d.cliente_nome,
            "address": d.indirizzo,
            "arrival": time_to_hhmm(d.arrivo_stimato),
            "departure": time_to_hhmm(d.partenza_stimata),
            "km_from_previous": d.km_tappa,
            "minutes_from_previous": d.minuti_tappa,
            "wait_minutes": d.attesa_min,
            "time_windows": windows,
            "ztl": bool(d.ztl),
            "tail_lift": bool(d.sponda),
            "warning": d.warning or "",
        })
    context = {
        "sector": user.company_sector or user.company_activity_type or "Distribuzione / Cash & Carry",
        "route": {
            "name": plan.nome,
            "date": date_to_iso(plan.data_giro),
            "departure": time_to_hhmm(plan.orario_partenza),
            "return_estimated": time_to_hhmm(plan.orario_rientro_stimato),
            "total_km": plan.totale_km,
            "total_minutes": plan.totale_minuti,
            "driver": ((plan.driver.nome + (" " + plan.driver.cognome if plan.driver.cognome else "")) if plan.driver else ""),
            "vehicle": (plan.vehicle.nome if plan.vehicle else ""),
        },
        "stops": stops,
    }
    prompt = """Spiega in italiano perché GiroFacile ha proposto questa sequenza di giro.
Deve essere un testo molto breve, semplice e non tecnico, massimo 5 righe.
Adatta le parole al settore: consegne per distribuzione/e-commerce/logistica/sanitario/food, corse/prenotazioni per transfer.
Non dire che l'AI ha calcolato il percorso: il percorso è calcolato da GiroFacile e dai servizi di routing collegati.
Non inventare dati, usa solo ordine tappe, km, orari e vincoli presenti nel JSON.
"""
    return run_ai_text(
        db, task="route_explanation", user_id=user.id,
        system_prompt="Sei l'assistente AI di GiroFacile. Spieghi in modo chiaro e breve le scelte di sequenza del giro, senza modificare il percorso.",
        user_prompt=prompt + "\nCONTESTO JSON:\n" + json.dumps(context, ensure_ascii=False, default=str),
        context=context,
    )

@router.get("/api/routes/operativi")
def list_operational_routes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from_date = (local_today() - timedelta(days=7))
    rows = (
        owned(db.query(RoutePlan), RoutePlan, user)
        .filter(RoutePlan.data_giro >= from_date)
        .order_by(RoutePlan.data_giro.asc(), RoutePlan.orario_partenza.asc(), RoutePlan.created_at.desc())
        .limit(150)
        .all()
    )
    result = []
    for r in rows:
        status = computed_route_status(r)
        if status in ("bozza", "completato", "annullato"):
            continue
        delivery_ids = [d.id for d in (r.deliveries or [])]
        d_statuses = db.query(DeliveryStatus).filter(DeliveryStatus.route_plan_id == r.id).all() if delivery_ids else []
        completed_count = sum(1 for ds in d_statuses if ds.status == "completata")
        missed_count = sum(1 for ds in d_statuses if ds.status == "mancata")
        total_count = len(r.deliveries or [])
        next_delivery = None
        for d in sorted((r.deliveries or []), key=lambda x: x.ordine or 0):
            ds = next((x for x in d_statuses if x.delivery_id == d.id), None)
            if not ds or ds.status == "in_attesa":
                next_delivery = {"cliente_nome": d.cliente_nome, "indirizzo": d.indirizzo, "ordine": d.ordine}
                break
        unread_driver_messages = db.query(ChatMessage).filter(
            ChatMessage.route_plan_id == r.id,
            ChatMessage.sender_type == "driver",
            ChatMessage.read_at.is_(None)
        ).count()
        last_driver_msg = db.query(ChatMessage).filter(
            ChatMessage.route_plan_id == r.id,
            ChatMessage.sender_type == "driver"
        ).order_by(ChatMessage.created_at.desc()).first()
        live_sched = live_route_schedule(r, {ds.delivery_id: ds for ds in d_statuses})
        result.append({
            "id": r.id, "nome": r.nome, "data_giro": date_to_iso(r.data_giro),
            "orario_partenza": time_to_hhmm(r.orario_partenza), "orario_rientro_stimato": time_to_hhmm(r.orario_rientro_stimato),
            "started_at": (r.started_at.isoformat() if getattr(r, "started_at", None) else None),
            "rientro_stimato_aggiornato": live_sched.get("rientro_stimato_aggiornato"),
            "driver_name": ((r.driver.nome + (" " + r.driver.cognome if r.driver.cognome else "")) if r.driver else ""),
            "vehicle_id": r.vehicle_id, "vehicle_name": (r.vehicle.nome if r.vehicle else ""),
            "totale_km": r.totale_km, "totale_minuti": r.totale_minuti,
            "consegne_count": total_count,
            "completed_count": completed_count,
            "missed_count": missed_count,
            "remaining_count": max(total_count - completed_count - missed_count, 0),
            "progress_percent": round(((completed_count + missed_count) / total_count) * 100) if total_count else 0,
            "next_delivery": next_delivery,
            "unread_driver_messages": unread_driver_messages,
            "last_driver_message": (last_driver_msg.message if last_driver_msg else None),
            "last_driver_message_at": (last_driver_msg.created_at.isoformat() if last_driver_msg else None),
            "status": status, "status_label": route_status_label(status),
        })
    return result


@router.post("/api/routes/{route_id}/program")
def program_route(
    route_id: int,
    payload: dict = {},
    db: Session = Depends(get_db),
    user: User = Depends(current_user)
):
    import os
    import secrets as _secrets
    from datetime import datetime, timedelta
    from ..models import RouteToken
    from ..services.email import send_driver_route_assigned

    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")
    ensure_not_past_route_date(plan.data_giro)
    status = computed_route_status(plan)
    if status not in ("bozza", "programmato"):
        raise HTTPException(400, "Puoi programmare solo un giro non ancora avviato.")
    plan.status = "programmato"
    plan.completed_at = None
    plan.cancelled_at = None

    # Token legacy per portale operatore condivisibile, mantenuto per compatibilità.
    db.query(RouteToken).filter(RouteToken.route_plan_id == route_id).delete()
    token = _secrets.token_urlsafe(32)
    expires = local_now().replace(tzinfo=None) + timedelta(days=3)
    rt = RouteToken(route_plan_id=route_id, token=token, expires_at=expires)
    db.add(rt)
    db.commit()
    db.refresh(plan)

    base_url = (payload or {}).get("base_url") or os.getenv("APP_BASE_URL", "https://app.girofacile.it")
    operator_portal_url = f"{base_url}/giro/{token}"
    driver_portal_url = f"{base_url}/driver"

    # L'autista deve ricevere il link al suo portale personale, non al link pubblico del giro.
    email_sent = False
    if plan.driver and plan.driver.email:
        driver_name = ((plan.driver.nome or "") + " " + (plan.driver.cognome or "")).strip()
        try:
            email_sent = send_driver_route_assigned(
                to_email=plan.driver.email,
                driver_name=driver_name,
                company_name=user.company_name or user.username or "GiroFacile",
                route_name=plan.nome or "Giro consegne",
                data_giro=date_to_iso(plan.data_giro) or "",
                orario_partenza=time_to_hhmm(plan.orario_partenza) or "",
                n_consegne=len(plan.deliveries or []),
                km_totali=float(plan.totale_km or 0),
                portal_url=driver_portal_url,
            )
        except Exception as e:
            print(f"[EMAIL] Errore invio assegnazione autista: {e}")

    result = serialize_route(plan)
    result["portal_url"] = driver_portal_url
    result["driver_portal_url"] = driver_portal_url
    result["operator_portal_url"] = operator_portal_url
    result["portal_token"] = token
    result["email_sent"] = email_sent
    result["driver_email"] = plan.driver.email if plan.driver else None
    return result


@router.post("/api/routes/{route_id}/cancel")
def cancel_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")
    status = computed_route_status(plan)
    if status in ("completato", "annullato"):
        raise HTTPException(400, "Il giro è già chiuso.")
    plan.status = "annullato"
    plan.cancelled_at = local_now().replace(tzinfo=None)
    db.commit()
    db.refresh(plan)
    return serialize_route(plan)


@router.post("/api/routes/{route_id}/complete")
def complete_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")
    plan.status = "completato"
    plan.completed_at = local_now().replace(tzinfo=None)
    db.commit()
    return {"ok": True, "status": "completato", "status_label": "Completato"}


@router.get("/api/routes/{route_id}/map-data")
def get_route_map_data(route_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Dati sicuri per visualizzare la mappa del giro nella dashboard.

    La chiave Google arriva dalle impostazioni SaaS salvate nel database; il file
    .env resta solo fallback gestito da platform_settings. La mappa non ricalcola
    il percorso: mostra l'ordine già calcolato e salvato per il giro.
    """
    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")

    deposit = plan.deposit
    stops = []
    for d in sorted(plan.deliveries or [], key=lambda x: x.ordine or 0):
        c = d.customer
        lat = getattr(c, "lat", None) if c else None
        lon = getattr(c, "lon", None) if c else None
        stops.append({
            "id": d.id,
            "order": d.ordine,
            "name": d.cliente_nome,
            "address": d.indirizzo,
            "arrival": time_to_hhmm(d.arrivo_stimato),
            "departure": time_to_hhmm(d.partenza_stimata),
            "km": d.km_tappa,
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
        })

    route_points = []
    if deposit and deposit.lat is not None and deposit.lon is not None:
        route_points.append({"lat": float(deposit.lat), "lon": float(deposit.lon)})
    for s in stops:
        if s.get("lat") is not None and s.get("lon") is not None:
            route_points.append({"lat": s["lat"], "lon": s["lon"]})

    road_polyline = None
    if len(route_points) >= 2 and len(route_points) == (1 + len(stops)):
        road_polyline = google_route_polyline(
            route_points,
            return_depot=bool(plan.rientro_deposito),
            start_time=time_to_hhmm(plan.orario_partenza) or "08:00",
            db=db,
        )

    return {
        "api_key": google_maps_api_key(db),
        "route_id": plan.id,
        "name": plan.nome,
        "google_maps_url": plan.google_maps_url,
        "return_depot": bool(plan.rientro_deposito),
        "road_polyline": road_polyline,
        "depot": {
            "id": getattr(deposit, "id", None),
            "name": getattr(deposit, "nome", "Deposito"),
            "address": getattr(deposit, "indirizzo", ""),
            "lat": float(deposit.lat) if deposit and deposit.lat is not None else None,
            "lon": float(deposit.lon) if deposit and deposit.lon is not None else None,
        },
        "stops": stops,
    }


@router.get("/api/routes/{route_id}")
def get_route(route_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")
    return serialize_route(plan)


@router.get("/api/routes")
def list_routes(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = owned(db.query(RoutePlan), RoutePlan, user).order_by(RoutePlan.created_at.desc()).limit(200).all()
    closed_rows = [r for r in rows if computed_route_status(r) in ("completato", "annullato")][:100]
    return [{
        "id": r.id, "nome": r.nome, "data_giro": date_to_iso(r.data_giro),
        "orario_partenza": time_to_hhmm(r.orario_partenza), "orario_rientro_stimato": time_to_hhmm(r.orario_rientro_stimato),
        "totale_km": r.totale_km, "costo_carburante": r.costo_carburante,
        "google_maps_url": r.google_maps_url, "consegne_count": len(r.deliveries or []),
        "driver_id": r.driver_id,
        "driver_name": ((r.driver.nome + (" " + r.driver.cognome if r.driver.cognome else "")) if r.driver else ""),
        "vehicle_id": r.vehicle_id,
        "vehicle_name": ((r.vehicle.nome + (" · " + r.vehicle.targa if r.vehicle and r.vehicle.targa else "")) if r.vehicle else ""),
        "status": computed_route_status(r), "status_label": route_status_label(computed_route_status(r)),
    } for r in closed_rows]
