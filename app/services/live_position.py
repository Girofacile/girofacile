"""Bounded GPS snapshot shared by web and future native driver clients.

No paid APIs, geocoding, route optimization or persistent coordinate cache.
All mutations serialize on the route, including completion/cancellation.
"""
import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime

from ..models import RoutePlan, RoutePosition, DeliveryStatus, Driver
from .road_routing import osrm_table
from .route_enrichment import json_data

FRESH_SECONDS = 90
ETA_SECONDS = 120


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PositionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float = Field(ge=0, le=10000)
    captured_at: AwareDatetime


def next_stop(plan, statuses):
    return next((d for d in sorted(plan.deliveries, key=lambda d: (d.ordine or 0, d.id))
                 if not statuses.get(d.id) or statuses[d.id].status not in ('completata', 'mancata')), None)


def coordinates(delivery):
    saved = json_data(delivery.optimizer_details)
    customer = delivery.customer
    lat = saved.get('lat', getattr(customer, 'lat', None))
    lon = saved.get('lon', getattr(customer, 'lon', None))
    try:
        lat, lon = float(lat), float(lon)
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return {'lat': lat, 'lon': lon}
    except (TypeError, ValueError):
        pass
    return None


def position_view(plan, now=None):
    now = now or utcnow()
    row = plan.position if plan.status == 'in_corso' else None
    if not row or row.driver_id != plan.driver_id:
        return {'state': 'unavailable', 'position': None}
    age = (now - row.captured_at).total_seconds()
    return {'state': 'fresh' if 0 <= age <= FRESH_SECONDS else 'stale', 'position': {
        'latitude': row.latitude, 'longitude': row.longitude, 'accuracy': row.accuracy,
        'captured_at': row.captured_at.isoformat() + 'Z',
        'received_at': row.received_at.isoformat() + 'Z',
    }}


def record_position(db, plan, payload):
    expected_owner, expected_driver = plan.user_id, plan.driver_id
    if expected_driver is not None:
        driver = db.query(Driver).filter_by(id=expected_driver).with_for_update().populate_existing().first()
        if not driver or driver.user_id != expected_owner or not driver.is_active or driver.deleted_at:
            raise HTTPException(404, 'Autista non disponibile per questo giro')
    # Refresh after locking: an upload racing with completion cannot revive tracking.
    plan = db.query(RoutePlan).filter_by(id=plan.id).with_for_update().populate_existing().one()
    if (plan.user_id, plan.driver_id) != (expected_owner, expected_driver):
        raise HTTPException(409, 'Assegnazione giro modificata')
    if plan.status != 'in_corso':
        raise HTTPException(409, 'GPS disponibile solo durante un giro in corso')
    now = utcnow()
    captured = payload.captured_at.astimezone(timezone.utc).replace(tzinfo=None)
    age = (now - captured).total_seconds()
    if age < -10 or age > FRESH_SECONDS or payload.accuracy > 150:
        return {'accepted': False, 'reason': 'unusable', 'retry_after_seconds': 30}
    row = db.get(RoutePosition, plan.id)
    if row and row.driver_id != plan.driver_id:
        db.delete(row); db.flush(); row = None
    if row and (captured <= row.captured_at or (now - row.received_at).total_seconds() < 20):
        return {'accepted': False, 'reason': 'throttled', 'retry_after_seconds': 30}
    if row is None:
        if plan.driver_id is not None:
            db.query(RoutePosition).filter(RoutePosition.driver_id == plan.driver_id,
                                           RoutePosition.route_plan_id != plan.id).delete(synchronize_session='fetch')
        row = RoutePosition(route_plan_id=plan.id, driver_id=plan.driver_id)
        db.add(row)
    row.latitude, row.longitude, row.accuracy = payload.latitude, payload.longitude, payload.accuracy
    row.captured_at, row.received_at = captured, now
    statuses = {s.delivery_id: s for s in db.query(DeliveryStatus).filter_by(route_plan_id=plan.id)}
    stop = next_stop(plan, statuses)
    # Bound even failed attempts; polling and public reads never contact OSRM.
    if not row.eta_attempted_at or (now - row.eta_attempted_at).total_seconds() >= ETA_SECONDS:
        row.eta_attempted_at = now
        row.eta_at = row.eta_calculated_at = row.eta_delivery_id = None
        destination = coordinates(stop) if stop else None
        if destination:
            try:
                legs = osrm_table([{'lat': row.latitude, 'lon': row.longitude}, destination], pairs=[(0, 1)], db=db)
            except ValueError:
                # Invalid OSRM configuration must not discard a valid position.
                legs = {}
            if (0, 1) in legs:
                row.eta_at = captured + timedelta(minutes=legs[0, 1]['min'])
                row.eta_calculated_at = captured
                row.eta_delivery_id = stop.id
    db.commit()
    return {'accepted': True, 'retry_after_seconds': 30, 'captured_at': captured.isoformat() + 'Z'}


def clear_position(plan):
    # delete-orphan performs cleanup in the same transaction as the closing event.
    plan.position = None


def cleanup_positions(db):
    """Safety net for abandoned routes: run with the existing daily cleanup job."""
    terminal = db.query(RoutePlan.id).filter(RoutePlan.status != 'in_corso')
    count = db.query(RoutePosition).filter(
        (RoutePosition.received_at < utcnow() - timedelta(hours=24)) |
        RoutePosition.route_plan_id.in_(terminal)
    ).delete(synchronize_session=False)
    db.commit()
    return count
