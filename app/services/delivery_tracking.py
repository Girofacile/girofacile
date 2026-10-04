"""Read-only customer projection and revocable, delivery-scoped capabilities.

The database stores a random selector, not a bearer credential. The HMAC uses
a domain-separated application secret so authorized staff can reopen the same
link without storing its signature. No public endpoint accepts delivery IDs.
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from ..core.config import APP_SECRET, LOCAL_TIMEZONE
from ..models import Delivery, DeliveryStatus, DeliveryTrackingLink, RoutePlan
from .route_schedule import route_schedule_datetimes

LOCAL = ZoneInfo(LOCAL_TIMEZONE)
PUBLIC_HEADERS = {
    'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
    'X-Robots-Tag': 'noindex, nofollow, noarchive',
    'X-Content-Type-Options': 'nosniff',
}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def credential(link):
    message = f'delivery-tracking:v1:{link.selector}'.encode()
    signature = hmac.new(APP_SECRET.encode(), message, hashlib.sha256).hexdigest()
    return f'{link.selector}.{signature}'


def expiry_for(plan):
    # Seven full days after the scheduled day, expressed in UTC in storage.
    end = datetime.combine(plan.data_giro + timedelta(days=8), time.min, LOCAL)
    return end.astimezone(timezone.utc).replace(tzinfo=None)


def owned_delivery(db, user, delivery_id):
    row = db.query(Delivery, RoutePlan).join(RoutePlan, Delivery.route_plan_id == RoutePlan.id).filter(
        Delivery.id == delivery_id, RoutePlan.user_id == user.id,
    ).with_for_update(of=RoutePlan).first()
    if not row:
        raise HTTPException(404, 'Consegna non trovata')
    return row


def ensure_link(db, delivery, plan):
    if plan.status not in ('programmato', 'in_corso', 'completato', 'annullato'):
        raise HTTPException(409, 'Programma il giro prima di condividere il tracking')
    existing = db.query(DeliveryTrackingLink).filter_by(delivery_id=delivery.id).first()
    if existing and existing.expires_at > utcnow():
        return existing
    if plan.status in ('completato', 'annullato') or expiry_for(plan) <= utcnow():
        raise HTTPException(409, 'Non è possibile generare un link per questa consegna chiusa o scaduta')
    if existing:
        db.delete(existing)
        db.flush()
    link = DeliveryTrackingLink(delivery_id=delivery.id, selector=secrets.token_hex(32), expires_at=expiry_for(plan))
    db.add(link)
    db.flush()
    return link


def resolve_link(db, token):
    error = HTTPException(404, 'Link non disponibile o scaduto', headers=PUBLIC_HEADERS)
    if not re.fullmatch(r'[0-9a-f]{64}\.[0-9a-f]{64}', token or ''):
        raise error
    selector = token.split('.')[0]
    link = db.query(DeliveryTrackingLink).filter_by(selector=selector).first()
    if not link or not hmac.compare_digest(credential(link), token) or link.expires_at <= utcnow():
        raise error
    row = db.query(Delivery, RoutePlan).join(RoutePlan, Delivery.route_plan_id == RoutePlan.id).filter(Delivery.id == link.delivery_id).first()
    if not row or row[1].status == 'bozza':
        raise error
    return row


def public_projection(db, delivery, plan, now=None):
    now = now or datetime.now(LOCAL)
    statuses = {s.delivery_id: s for s in db.query(DeliveryStatus).filter_by(route_plan_id=plan.id)}
    own = statuses.get(delivery.id)
    status = own.status if own else 'in_attesa'
    if status not in ('completata', 'mancata'):
        status = {'programmato': 'programmata', 'in_corso': 'in_consegna',
                  'annullato': 'annullata'}.get(plan.status, 'non_disponibile')
    terminal = status in ('completata', 'mancata', 'annullata', 'non_disponibile')
    schedule = route_schedule_datetimes(plan, statuses)
    entry = schedule['deliveries'].get(delivery.id, {})
    eta = entry.get('arrival') if not terminal else None
    if eta and eta <= now:
        eta = None  # Never present an expired prediction as a live ETA.
    before = None
    if status == 'in_consegna':
        ordered = sorted(plan.deliveries, key=lambda d: (d.ordine or 0, d.id))
        before = 0
        for stop in ordered:
            if stop.id == delivery.id:
                break
            ds = statuses.get(stop.id)
            if not ds or ds.status not in ('completata', 'mancata'):
                before += 1
    def iso(value):
        return value.isoformat() if value else None
    completed = own.completata_il.replace(tzinfo=LOCAL) if own and own.completata_il else None
    # Explicit allowlist: do not add internal route/delivery serialization here.
    return {
        'status': status, 'scheduled_date': plan.data_giro.isoformat(), 'timezone': LOCAL_TIMEZONE,
        'eta': {'at': iso(eta), 'source': entry.get('source') if eta else None,
                'updated_at': iso(entry.get('updated_at')) if not terminal else None},
        'stops_before': before, 'completed_at': iso(completed),
        'refresh_after_seconds': 0 if terminal else 30,
    }
