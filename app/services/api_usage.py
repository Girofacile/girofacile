"""Registro consumi API esterne per il pannello Super Admin."""
from __future__ import annotations

from datetime import datetime, timedelta
import calendar
import json
import math
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import ApiUsageLog, SaaSPlatformSetting, User

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


# ---------------------------------------------------------------------------
# Cost dashboard / free-tier monitoring
# ---------------------------------------------------------------------------

API_COST_SETTINGS_KEY = "api_cost_profiles_json"

# Defaults reviewed on 2026-10-06. They are intentionally editable from the
# Super Admin because provider pricing can change without an application deploy.
# Currency is kept in the provider's billing currency to avoid pretending that
# an exchange-rate conversion is exact.
API_COST_DEFAULTS = {
    "google_geocoding": {
        "provider": "Google",
        "label": "Google Geocoding",
        "services": ["google_geocoding"],
        "unit_label": "richieste",
        "quota_period": "monthly",
        "free_quota": 10000,
        "currency": "USD",
        "billing_model": "tiered",
        # Conservative public-list estimate after the free allowance.
        "tiers": [{"up_to": None, "price_per_1000": 5.0}],
        "pricing_note": "10.000 richieste/mese gratuite; oltre quota stima standard $5/1.000.",
        "source_updated": "2026-10-06",
    },
    "mapbox_traffic": {
        "provider": "Mapbox",
        "label": "Mapbox Directions / traffico",
        "services": ["mapbox_traffic"],
        "unit_label": "richieste",
        "quota_period": "monthly",
        "free_quota": 100000,
        "currency": "USD",
        "billing_model": "tiered",
        "tiers": [
            {"up_to": 500000, "price_per_1000": 2.0},
            {"up_to": 1000000, "price_per_1000": 1.6},
            {"up_to": None, "price_per_1000": 1.2},
        ],
        "pricing_note": "100.000 richieste/mese gratuite; scaglioni Mapbox Directions.",
        "source_updated": "2026-10-06",
    },
    "openai": {
        "provider": "OpenAI",
        "label": "OpenAI · funzioni AI",
        "services": [
            "openai_route_explanation",
            "openai_support_ticket_text",
            "openai_admin_error_analysis",
            "openai_report_summary",
        ],
        "unit_label": "chiamate",
        "quota_period": "monthly",
        "free_quota": 0,
        "currency": "USD",
        "billing_model": "logged_cost",
        "tiers": [],
        "pricing_note": "Costo calcolato dai token restituiti dal provider per il modello configurato.",
        "source_updated": "2026-10-06",
    },
    "mycarplate": {
        "provider": "MyCarPlate",
        "label": "MyCarPlate · lookup targa",
        "services": ["mycarplate_vehicle"],
        "unit_label": "lookup",
        "quota_period": "daily",
        "free_quota": 25,
        "currency": "GBP",
        "billing_model": "subscription",
        "tiers": [],
        "subscription_price": 49.0,
        "subscription_units": 2500,
        "pricing_note": "25 lookup/giorno gratuiti; piano Pro pubblico £49/mese per 2.500 lookup.",
        "source_updated": "2026-10-06",
    },
    "openapi_vehicle": {
        "provider": "OpenAPI",
        "label": "OpenAPI Automotive · lookup targa",
        "services": ["openapi_vehicle"],
        "unit_label": "lookup",
        "quota_period": "monthly",
        "free_quota": 0,
        "currency": "EUR",
        "billing_model": "tiered",
        "tiers": [{"up_to": None, "price_per_1000": 400.0}],
        "pricing_note": "Stima base €0,40 per lookup; eventuali piani/volumi possono ridurre il prezzo.",
        "source_updated": "2026-10-06",
    },
}


def _coerce_number(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else float(default)
    except (TypeError, ValueError):
        return float(default)


def _deep_merge_profile(default: dict, override: dict | None) -> dict:
    merged = json.loads(json.dumps(default))
    if not isinstance(override, dict):
        return merged
    for key in ("free_quota", "currency", "quota_period", "pricing_note", "subscription_price", "subscription_units"):
        if key in override:
            merged[key] = override[key]
    if isinstance(override.get("tiers"), list):
        clean_tiers = []
        for item in override["tiers"]:
            if not isinstance(item, dict):
                continue
            up_to = item.get("up_to")
            if up_to not in (None, ""):
                try:
                    up_to = int(up_to)
                except (TypeError, ValueError):
                    continue
                if up_to <= 0:
                    continue
            price = _coerce_number(item.get("price_per_1000"), 0)
            clean_tiers.append({"up_to": up_to, "price_per_1000": price})
        if clean_tiers:
            merged["tiers"] = clean_tiers
    merged["free_quota"] = int(_coerce_number(merged.get("free_quota"), 0))
    merged["currency"] = str(merged.get("currency") or default.get("currency") or "EUR").upper()[:8]
    merged["quota_period"] = str(merged.get("quota_period") or default.get("quota_period") or "monthly")
    return merged


def get_api_cost_profiles(db: Session | None = None) -> dict[str, dict]:
    overrides = {}
    if db is not None:
        try:
            row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == API_COST_SETTINGS_KEY).first()
            if row and row.value:
                parsed = json.loads(row.value)
                if isinstance(parsed, dict):
                    overrides = parsed
        except Exception:
            overrides = {}
    return {key: _deep_merge_profile(value, overrides.get(key)) for key, value in API_COST_DEFAULTS.items()}


def save_api_cost_profiles(db: Session, payload: dict) -> dict[str, dict]:
    if not isinstance(payload, dict):
        raise ValueError("Configurazione costi API non valida")
    current = get_api_cost_profiles(db)
    overrides = {}
    for key, default in API_COST_DEFAULTS.items():
        requested = payload.get(key)
        if requested is None:
            continue
        merged = _deep_merge_profile(default, requested)
        overrides[key] = {
            "free_quota": merged["free_quota"],
            "currency": merged["currency"],
            "quota_period": merged["quota_period"],
            "tiers": merged.get("tiers", []),
            "pricing_note": str(merged.get("pricing_note") or "")[:500],
            "subscription_price": _coerce_number(merged.get("subscription_price"), 0),
            "subscription_units": int(_coerce_number(merged.get("subscription_units"), 0)),
        }
    row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == API_COST_SETTINGS_KEY).first()
    value = json.dumps(overrides, ensure_ascii=False)
    if row:
        row.value = value
    else:
        db.add(SaaSPlatformSetting(key=API_COST_SETTINGS_KEY, value=value))
    db.commit()
    return get_api_cost_profiles(db)


def _tiered_cost(total_units: int, profile: dict) -> float:
    units = max(0, int(total_units or 0))
    free = max(0, int(profile.get("free_quota") or 0))
    if units <= free:
        return 0.0
    cursor = free
    cost = 0.0
    for tier in profile.get("tiers") or []:
        upper = tier.get("up_to")
        price = _coerce_number(tier.get("price_per_1000"), 0)
        if upper is None:
            quantity = units - cursor
        else:
            upper = max(cursor, int(upper))
            quantity = max(0, min(units, upper) - cursor)
        cost += quantity / 1000 * price
        cursor += quantity
        if cursor >= units:
            break
    return round(cost, 6)


def _cost_for_profile(total_units: int, profile: dict, logged_cost: float = 0.0) -> float | None:
    model = profile.get("billing_model")
    if model == "logged_cost":
        return round(max(0.0, float(logged_cost or 0)), 6)
    if model == "tiered":
        return _tiered_cost(total_units, profile)
    # Subscription providers do not expose a deterministic PAYG cost after the
    # free quota. Show the quota and public subscription price, but do not invent
    # a per-call bill.
    return None


def _status_from_percent(percent: float | None, billable_units: int) -> str:
    if billable_units > 0:
        return "paid"
    if percent is None:
        return "info"
    if percent >= 90:
        return "warning"
    if percent >= 70:
        return "watch"
    return "ok"


def _month_bounds(reference: datetime) -> tuple[datetime, datetime]:
    start = reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _month_key(value: str | None, now: datetime) -> datetime:
    if not value:
        return now
    try:
        parsed = datetime.strptime(value[:7], "%Y-%m")
        return parsed.replace(day=1)
    except (TypeError, ValueError):
        return now


def api_cost_dashboard(db: Session, month: str = "") -> dict:
    now = datetime.utcnow()
    ref = _month_key(month, now)
    month_start, month_end = _month_bounds(ref)
    profiles = get_api_cost_profiles(db)

    service_to_profile = {
        service: key
        for key, profile in profiles.items()
        for service in profile.get("services", [])
    }

    rows = (
        db.query(
            ApiUsageLog.service,
            ApiUsageLog.user_id,
            ApiUsageLog.status,
            func.sum(ApiUsageLog.request_count),
            func.sum(ApiUsageLog.estimated_cost_eur),
        )
        .filter(ApiUsageLog.created_at >= month_start, ApiUsageLog.created_at < month_end)
        .group_by(ApiUsageLog.service, ApiUsageLog.user_id, ApiUsageLog.status)
        .all()
    )

    usage = {key: {"calls": 0, "errors": 0, "logged_cost": 0.0, "by_company": {}} for key in profiles}
    user_ids = set()
    for service, user_id, status, calls, logged_cost in rows:
        profile_key = service_to_profile.get(service)
        if not profile_key:
            continue
        calls = int(calls or 0)
        item = usage[profile_key]
        item["calls"] += calls
        item["logged_cost"] += float(logged_cost or 0)
        if status != "success":
            item["errors"] += calls
        if user_id:
            user_ids.add(user_id)
            item["by_company"][user_id] = item["by_company"].get(user_id, 0) + calls

    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    is_current_month = month_start.year == now.year and month_start.month == now.month
    days_in_month = calendar.monthrange(month_start.year, month_start.month)[1]
    elapsed_days = max(1, now.day if is_current_month else days_in_month)

    daily_usage = {}
    if is_current_month:
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_rows = (
            db.query(ApiUsageLog.service, func.sum(ApiUsageLog.request_count))
            .filter(ApiUsageLog.created_at >= day_start, ApiUsageLog.created_at <= now)
            .group_by(ApiUsageLog.service)
            .all()
        )
        for service, calls in daily_rows:
            key = service_to_profile.get(service)
            if key:
                daily_usage[key] = daily_usage.get(key, 0) + int(calls or 0)

    services = []
    cost_totals = {}
    projected_totals = {}
    company_raw = {}
    for key, profile in profiles.items():
        item = usage[key]
        calls = item["calls"]
        period_usage = daily_usage.get(key, 0) if profile.get("quota_period") == "daily" else calls
        free = max(0, int(profile.get("free_quota") or 0))
        remaining = max(0, free - period_usage) if free else 0
        billable = max(0, period_usage - free) if profile.get("billing_model") != "subscription" else max(0, period_usage - free)
        percent = round(period_usage / free * 100, 1) if free else None
        cost = _cost_for_profile(calls, profile, item["logged_cost"])
        projected_calls = int(round(calls / elapsed_days * days_in_month)) if is_current_month else calls
        projected_logged = item["logged_cost"] / elapsed_days * days_in_month if is_current_month else item["logged_cost"]
        projected_cost = _cost_for_profile(projected_calls, profile, projected_logged)
        currency = profile.get("currency") or "EUR"
        if cost is not None:
            cost_totals[currency] = round(cost_totals.get(currency, 0) + cost, 6)
        if projected_cost is not None:
            projected_totals[currency] = round(projected_totals.get(currency, 0) + projected_cost, 6)

        services.append({
            "key": key,
            "provider": profile.get("provider"),
            "label": profile.get("label"),
            "calls_month": calls,
            "errors_month": item["errors"],
            "quota_period": profile.get("quota_period"),
            "quota_usage": period_usage,
            "free_quota": free,
            "free_remaining": remaining,
            "free_percent": percent,
            "billable_units": billable,
            "unit_label": profile.get("unit_label"),
            "currency": currency,
            "estimated_cost": cost,
            "projected_calls": projected_calls,
            "projected_cost": projected_cost,
            "status": _status_from_percent(percent, billable),
            "pricing_note": profile.get("pricing_note"),
            "subscription_price": profile.get("subscription_price"),
            "subscription_units": profile.get("subscription_units"),
            "source_updated": profile.get("source_updated"),
            "tiers": profile.get("tiers", []),
        })

        for user_id, company_calls in item["by_company"].items():
            comp = company_raw.setdefault(user_id, {"calls": 0, "by_service": {}})
            comp["calls"] += company_calls
            comp["by_service"][key] = company_calls

    companies = []
    for user_id, raw in company_raw.items():
        user = users.get(user_id)
        attributed = {}
        for key, company_calls in raw["by_service"].items():
            total_service_calls = max(1, usage[key]["calls"])
            service_profile = profiles[key]
            service_cost = _cost_for_profile(usage[key]["calls"], service_profile, usage[key]["logged_cost"])
            if service_cost is not None:
                currency = service_profile.get("currency") or "EUR"
                attributed[currency] = round(
                    attributed.get(currency, 0) + service_cost * company_calls / total_service_calls, 6
                )
        companies.append({
            "user_id": user_id,
            "company_name": (user.company_name if user else "") or (user.username if user else f"Azienda #{user_id}"),
            "calls": raw["calls"],
            "cost_attribution": attributed,
        })
    companies.sort(key=lambda item: item["calls"], reverse=True)

    # Six-month trend; intentionally recalculated from call counts rather than
    # old estimated_cost_eur values so free tiers are represented correctly.
    history = []
    cursor = month_start
    for _ in range(6):
        hist_start, hist_end = _month_bounds(cursor)
        hist_rows = (
            db.query(ApiUsageLog.service, func.sum(ApiUsageLog.request_count), func.sum(ApiUsageLog.estimated_cost_eur))
            .filter(ApiUsageLog.created_at >= hist_start, ApiUsageLog.created_at < hist_end)
            .group_by(ApiUsageLog.service)
            .all()
        )
        profile_usage = {key: {"calls": 0, "logged_cost": 0.0} for key in profiles}
        for service, calls, logged_cost in hist_rows:
            key = service_to_profile.get(service)
            if key:
                profile_usage[key]["calls"] += int(calls or 0)
                profile_usage[key]["logged_cost"] += float(logged_cost or 0)
        costs = {}
        total_calls = 0
        for key, hist_item in profile_usage.items():
            total_calls += hist_item["calls"]
            price = _cost_for_profile(hist_item["calls"], profiles[key], hist_item["logged_cost"])
            if price is not None:
                currency = profiles[key].get("currency") or "EUR"
                costs[currency] = round(costs.get(currency, 0) + price, 6)
        history.append({"month": hist_start.strftime("%Y-%m"), "calls": total_calls, "costs": costs})
        cursor = hist_start - timedelta(days=1)
    history.reverse()

    total_calls = sum(item["calls"] for item in usage.values())
    highest = max(
        (service for service in services if service["free_percent"] is not None),
        key=lambda item: item["free_percent"],
        default=None,
    )
    alerts = []
    for service in services:
        if service["status"] == "paid":
            alerts.append({
                "level": "danger",
                "service": service["label"],
                "message": f"{service['billable_units']} {service['unit_label']} oltre la quota gratuita.",
            })
        elif service["status"] in ("watch", "warning"):
            alerts.append({
                "level": "warning" if service["status"] == "warning" else "watch",
                "service": service["label"],
                "message": f"Quota gratuita utilizzata al {service['free_percent']}%.",
            })

    return {
        "month": month_start.strftime("%Y-%m"),
        "is_current_month": is_current_month,
        "days_in_month": days_in_month,
        "elapsed_days": elapsed_days,
        "total_calls": total_calls,
        "estimated_costs": cost_totals,
        "projected_costs": projected_totals,
        "services": services,
        "companies": companies[:30],
        "history": history,
        "alerts": alerts,
        "highest_free_tier": highest,
        "settings": profiles,
    }
