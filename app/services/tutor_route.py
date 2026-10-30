"""Giro di prova della guida: si calcola davvero, ma alla programmazione sparisce.

Non passa da program_route: niente email all'autista, niente limiti del piano
(il consumo si conta solo all'avvio) e nessuna traccia tra giri e bozze.
Deposito, mezzo, autista e clienti restano.
"""
from fastapi import HTTPException

from ..core.dependencies import owned
from ..models import ApiUsageLog, ChatMessage, Delivery, DeliveryStatus, DeliveryTrackingLink, RoutePlan, RoutePosition, RouteToken
from . import route_orders


def discard_test_route(db, user, route_id):
    from ..routers.routes import computed_route_status
    route_orders.lock_company(db, user.id)
    plan = owned(db.query(RoutePlan), RoutePlan, user).filter(RoutePlan.id == route_id).with_for_update().first()
    if not plan:
        raise HTTPException(404, "Giro non trovato")
    if computed_route_status(plan) != "bozza":
        raise HTTPException(400, "Il giro di prova deve essere ancora in bozza.")
    # Eventuali ordini tornano da pianificare.
    route_orders.sync_route_orders(db, plan, "cancelled")
    deliveries = db.query(Delivery.id).filter(Delivery.route_plan_id == plan.id)
    db.query(DeliveryTrackingLink).filter(DeliveryTrackingLink.delivery_id.in_(deliveries)).delete(synchronize_session=False)
    # Anche su SQLite senza vincoli attivi: niente righe orfane collegate al giro.
    for model in (DeliveryStatus, Delivery, RoutePosition, RouteToken, ChatMessage):
        db.query(model).filter(model.route_plan_id == plan.id).delete(synchronize_session=False)
    db.query(ApiUsageLog).filter(ApiUsageLog.route_plan_id == plan.id).update({"route_plan_id": None}, synchronize_session=False)
    db.expire(plan)
    db.query(RoutePlan).filter(RoutePlan.id == plan.id).delete(synchronize_session=False)
    db.flush()
