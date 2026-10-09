"""Calendar-month operational quotas, independent from invoices and draft routes."""
from datetime import datetime, timezone
from sqlalchemy import func
from fastapi import HTTPException
from ..core.utils import local_now
from ..models import User, RouteUsage
from .plans import get_plan_limits, require_active_plan, vehicle_usage


def backfill_started_routes(db):
    """Preserve usage of historical started routes, without changing their state."""
    from datetime import time
    from ..models import SaaSPlatformSetting, RoutePlan, Delivery
    marker = "billing_usage_backfill_v1"
    if db.query(SaaSPlatformSetting).filter_by(key=marker).first():
        return
    rows = db.query(RoutePlan.id, RoutePlan.user_id, RoutePlan.started_at, RoutePlan.completed_at, RoutePlan.data_giro).filter(
        (RoutePlan.started_at.isnot(None)) | (RoutePlan.status.in_(("in_corso", "completato")))).all()
    for route_id, user_id, started_at, completed_at, day in rows:
        if not user_id or db.get(RouteUsage, route_id):
            continue
        started = started_at or completed_at or datetime.combine(day, time())
        count = db.query(Delivery).filter_by(route_plan_id=route_id).count()
        db.add(RouteUsage(route_id=route_id, user_id=user_id, month=started.strftime("%Y-%m"), deliveries=count, started_at=started))
    db.add(SaaSPlatformSetting(key=marker, value="done"))
    db.commit()


def usage_summary(db, user):
    month = local_now().strftime("%Y-%m")
    routes, deliveries = db.query(func.count(RouteUsage.route_id), func.coalesce(func.sum(RouteUsage.deliveries), 0)).filter(
        RouteUsage.user_id == user.id, RouteUsage.month == month).one()
    limits = get_plan_limits(user.plan)
    def quota(used, maximum):
        return {"used": int(used), "limit": maximum, "percent": round(100 * used / maximum, 1), "warning": used >= maximum * .8}
    from ..models import Customer, Vehicle, Driver, Deposit
    resources = {}
    for model, key in ((Customer, "customers"), (Driver, "drivers"), (Deposit, "deposits")):
        count = db.query(model).filter(model.user_id == user.id, model.deleted_at.is_(None)).count()
        resources[key] = quota(count, limits["max_" + key])
    fleet = vehicle_usage(user, db)
    maximum = fleet["total_limit"]
    resources["vehicles"] = {
        **fleet, "used": fleet["total_used"], "limit": maximum,
        "percent": round(100 * fleet["total_used"] / maximum, 1) if maximum else 0,
        "warning": fleet["over_limit"] or (
            maximum is not None and fleet["total_used"] >= maximum * .8
        ),
    }
    return {"month": month, "routes": quota(routes, limits["max_routes_per_month"]),
            "deliveries": quota(deliveries, limits["max_deliveries_per_month"]), "resources": resources}


def start_route_usage(db, route):
    owner = db.query(User).filter(User.id == route.user_id).with_for_update().populate_existing().one()
    if route.status == "annullato":
        raise HTTPException(409, "Il giro è annullato")
    if db.get(RouteUsage, route.id):
        return  # A running route can always be completed, even after expiry.
    legacy_started = bool(route.started_at or route.status in ("in_corso", "completato"))
    if not legacy_started:
        require_active_plan(owner)
        usage = usage_summary(db, owner)
        if usage["routes"]["used"] + 1 > usage["routes"]["limit"]:
            raise HTTPException(403, "Quota mensile giri raggiunta: i giri già avviati restano operativi")
        if usage["deliveries"]["used"] + len(route.deliveries) > usage["deliveries"]["limit"]:
            raise HTTPException(403, "Il giro supera le consegne disponibili questo mese")
    started = route.started_at or local_now().replace(tzinfo=None)
    if not route.started_at:
        route.started_at_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(RouteUsage(route_id=route.id, user_id=owner.id, month=started.strftime("%Y-%m"),
                      deliveries=len(route.deliveries), started_at=started))
    route.started_at = started
    if route.status != "completato":
        route.status = "in_corso"
    db.flush()


def guard_company_write(request, user):
    """Expired companies retain reading, exports, billing and running-route closure."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    path = request.url.path
    if request.method == 'PUT' and path.startswith('/api/collaborators/'):
        # Only the owner can reach these routes; access revocation must remain
        # available when the company's subscription has expired.
        return
    if path.startswith(("/api/billing/", "/api/support", "/api/password-reset", "/api/logout")):
        return
    if path.startswith("/api/routes/") and path.endswith(("/complete", "/cancel")):
        return  # The endpoint checks whether this is an already-started route.
    require_active_plan(user)
