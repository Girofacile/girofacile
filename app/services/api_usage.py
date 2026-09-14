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
    "google_routes_matrix": 0.01,
    "google_maps_link": 0.0,
}


def estimate_cost(service: str, request_count: int = 1) -> float:
    return round(float(ESTIMATED_COSTS_EUR.get(service, 0.0)) * max(1, int(request_count or 1)), 5)


def log_api_usage(
    db: Session,
    *,
    user_id: int | None = None,
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
):
    try:
        row = ApiUsageLog(
            user_id=user_id,
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
        db.add(row)
        db.commit()
        return row
    except Exception:
        try:
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
    rows = q.order_by(ApiUsageLog.created_at.desc()).limit(250).all()
    total_calls = sum(int(r.request_count or 1) for r in rows)
    total_cost = round(sum(float(r.estimated_cost_eur or 0) for r in rows), 4)
    success = sum(int(r.request_count or 1) for r in rows if r.status == "success")
    failed = sum(int(r.request_count or 1) for r in rows if r.status != "success")
    by_service: dict[str, dict] = {}
    by_company: dict[int, dict] = {}
    users = {u.id: u for u in db.query(User).all()}
    for r in rows:
        item = by_service.setdefault(r.service, {"service": r.service, "calls": 0, "cost": 0, "errors": 0})
        item["calls"] += int(r.request_count or 1)
        item["cost"] = round(item["cost"] + float(r.estimated_cost_eur or 0), 4)
        if r.status != "success":
            item["errors"] += 1
        if r.user_id:
            u = users.get(r.user_id)
            comp = by_company.setdefault(r.user_id, {"user_id": r.user_id, "company_name": (u.company_name if u else "") or (u.username if u else f"Azienda #{r.user_id}"), "calls": 0, "cost": 0, "errors": 0})
            comp["calls"] += int(r.request_count or 1)
            comp["cost"] = round(comp["cost"] + float(r.estimated_cost_eur or 0), 4)
            if r.status != "success":
                comp["errors"] += 1

    def row_to_dict(r: ApiUsageLog):
        u = users.get(r.user_id) if r.user_id else None
        return {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "company_name": (u.company_name if u else "") or (u.username if u else "Sistema"),
            "user_id": r.user_id,
            "provider": r.provider,
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
