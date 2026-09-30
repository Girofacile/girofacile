"""Registro consumi API esterne per il pannello Super Admin."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import ApiUsageLog, User

# Stime conservative e modificabili in futuro quando collegheremo Google Cloud Billing.
# Sono usate solo per un primo controllo interno dei consumi.
ESTIMATED_COSTS_EUR = {
    "google_geocoding": 0.005,
    "google_maps_link": 0.0,
}


def estimate_cost(service: str, request_count: int = 1) -> float:
    return round(float(ESTIMATED_COSTS_EUR.get(service, 0.0)) * max(1, int(request_count or 1)), 5)


def log_api_usage(
    db: Session,
    *,
    user_id: int | None = None,
    route_id: int | None = None,
    provider: str = "google",
    service: str = "google_geocoding",
    action: str = "",
    endpoint: str = "",
    request_count: int = 1,
    status: str = "success",
    message: str = "",
    response_ms: int | None = None,
    estimated_cost_eur: float | None = None,
    meta: dict[str, Any] | None = None,
    commit: bool = True,
):
    try:
        row = ApiUsageLog(
            user_id=user_id,
            route_plan_id=route_id,
            provider=(provider or "google")[:80],
            service=(service or "google")[:120],
            action=(action or "")[:180],
            endpoint=(endpoint or "")[:240],
            request_count=max(1, int(request_count or 1)),
            status=(status or "success")[:30],
            message=(message or "")[:2000],
            response_ms=response_ms,
            estimated_cost_eur=estimate_cost(service, request_count) if estimated_cost_eur is None else float(estimated_cost_eur or 0),
            meta_json=json.dumps(meta or {}, ensure_ascii=False) if meta else None,
        )
        with db.begin_nested():
            db.add(row)
            db.flush()
        if commit:
            db.commit()
        return row
    except Exception:
        try:
            if commit:
                db.rollback()
        except Exception:
            pass
        return None


def range_from_filter(period: str = "today", start: str = "", end: str = ""):
    now = datetime.utcnow()
    period = (period or "today").strip().lower()
    if period == "live":
        return now - timedelta(hours=1), now
    if period in ("24h", "last24"):
        return now - timedelta(hours=24), now
    if period in ("7d", "week"):
        return now - timedelta(days=7), now
    if period in ("30d", "month"):
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
    if period == "previous_month":
        first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_prev = first_this - timedelta(seconds=1)
        first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return first_prev, first_this
    if period == "custom" and start:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", ""))
            end_dt = datetime.fromisoformat(end.replace("Z", "")) if end else now
            return start_dt, end_dt
        except Exception:
            pass
    return now.replace(hour=0, minute=0, second=0, microsecond=0), now


def api_usage_summary(db: Session, period: str = "today", service: str = "", start: str = "", end: str = "") -> dict:
    start_dt, end_dt = range_from_filter(period, start, end)
    q = db.query(ApiUsageLog).filter(ApiUsageLog.created_at >= start_dt, ApiUsageLog.created_at <= end_dt)
    if service:
        q = q.filter(ApiUsageLog.service == service)
    rows = q.order_by(ApiUsageLog.created_at.desc()).limit(100).all()
    # Aggregate in SQL over the entire period; recent rows are just the drill-down.
    aggregates = q.with_entities(
        ApiUsageLog.provider, ApiUsageLog.service, ApiUsageLog.user_id, ApiUsageLog.status,
        func.sum(ApiUsageLog.request_count), func.sum(ApiUsageLog.estimated_cost_eur)
    ).group_by(ApiUsageLog.provider, ApiUsageLog.service, ApiUsageLog.user_id, ApiUsageLog.status).all()
    user_ids = {a[2] for a in aggregates if a[2]} | {r.user_id for r in rows if r.user_id}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    total_calls, total_cost, success, failed = 0, 0.0, 0, 0
    by_service, by_company = {}, {}
    for provider, service_name, company_id, status, calls, cost in aggregates:
        calls, cost = int(calls or 0), float(cost or 0)
        total_calls += calls
        total_cost += cost
        success += calls if status == "success" else 0
        failed += calls if status != "success" else 0
        item = by_service.setdefault((provider, service_name), {
            "provider": provider, "service": service_name, "calls": 0, "cost": 0, "errors": 0})
        item["calls"] += calls
        item["cost"] = round(item["cost"] + cost, 4)
        item["errors"] += calls if status != "success" else 0
        if company_id:
            u = users.get(company_id)
            comp = by_company.setdefault(company_id, {"user_id": company_id,
                "company_name": (u.company_name if u else "") or (u.username if u else f"Azienda #{company_id}"),
                "calls": 0, "cost": 0, "errors": 0})
            comp["calls"] += calls
            comp["cost"] = round(comp["cost"] + cost, 4)
            comp["errors"] += calls if status != "success" else 0
    total_cost = round(total_cost, 4)

    def row_to_dict(r: ApiUsageLog):
        u = users.get(r.user_id) if r.user_id else None
        return {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "company_name": (u.company_name if u else "") or (u.username if u else "Sistema"),
            "user_id": r.user_id,
            "provider": r.provider,
            "route_id": r.route_plan_id,
            "service": r.service,
            "action": r.action or "",
            "endpoint": r.endpoint or "",
            "request_count": r.request_count or 1,
            "status": r.status,
            "message": r.message or "",
            "response_ms": r.response_ms,
            "estimated_cost_eur": round(float(r.estimated_cost_eur or 0), 4),
        }

    return {
        "period": period,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "total_calls": total_calls,
        "success_calls": success,
        "failed_calls": failed,
        "estimated_cost_eur": total_cost,
        "by_service": sorted(by_service.values(), key=lambda x: x["calls"], reverse=True),
        "by_company": sorted(by_company.values(), key=lambda x: x["calls"], reverse=True)[:20],
        "recent": [row_to_dict(r) for r in rows[:100]],
    }
