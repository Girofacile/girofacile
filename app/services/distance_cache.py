"""Persistent, directed road legs, isolated by company and coordinate/version keys."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import or_, tuple_
from sqlalchemy.orm import Session

from ..models import DistanceCache


def cache_ttl_days() -> int:
    try:
        return max(0, int(os.getenv("DISTANCE_CACHE_TTL_DAYS", "0")))
    except (TypeError, ValueError):
        return 0


def cache_expires_at(now: datetime | None = None) -> datetime | None:
    days = cache_ttl_days()
    return (now or datetime.utcnow()) + timedelta(days=days) if days else None


def _company_prefix(user_id) -> str:
    return f"company:{int(user_id)}" if user_id is not None else "company:0"


def customer_key(customer_id, user_id=None) -> str:
    base = f"customer:{customer_id}"
    return f"{_company_prefix(user_id)}:{base}" if user_id is not None else base


def deposit_key(deposit_id, user_id=None) -> str:
    base = f"deposit:{deposit_id}"
    return f"{_company_prefix(user_id)}:{base}" if user_id is not None else base


def geo_key(lat, lon, user_id=None) -> str:
    base = f"geo:{float(lat):.7f},{float(lon):.7f}"
    return f"{_company_prefix(user_id)}:{base}" if user_id is not None else base


def point_key(deposit_id=None, customer_id=None, lat=None, lon=None, user_id=None) -> str:
    if deposit_id is not None:
        base = deposit_key(deposit_id, user_id=user_id)
    elif customer_id is not None:
        base = customer_key(customer_id, user_id=user_id)
    else:
        return geo_key(lat, lon, user_id=user_id)
    # Also protects imports/direct edits that do not pass through the API invalidator.
    return f"{base}|coord={float(lat):.7f},{float(lon):.7f}" if lat is not None and lon is not None else base


def _chunks(values, size=400):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def get_pairs(db: Session, user_id: int, pairs: list[tuple[str, str]]) -> dict:
    unique = list({p for p in pairs if not any("|departure=" in k for k in p)})
    now, result = datetime.utcnow(), {}
    for batch in _chunks(unique):
        rows = (db.query(DistanceCache).filter(DistanceCache.user_id == user_id)
                .filter(tuple_(DistanceCache.origin_key, DistanceCache.dest_key).in_(batch))
                .filter(or_(DistanceCache.expires_at.is_(None), DistanceCache.expires_at > now)).all())
        result.update({(r.origin_key, r.dest_key): {"km": r.km, "min": r.min} for r in rows})
    return result


def save_pairs(db: Session, user_id: int, entries: list[tuple[str, str, float, float]]):
    # Atomic upsert: concurrent optimizations must not fail on the same pair.
    entries = {(o, d): (km, minutes) for o, d, km, minutes in entries
               if "|departure=" not in o and "|departure=" not in d}
    if not entries:
        return
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    now = datetime.utcnow()
    rows = [dict(user_id=user_id, origin_key=o, dest_key=d, km=km, min=minutes,
                 updated_at=now, expires_at=cache_expires_at(now))
            for (o, d), (km, minutes) in entries.items()]
    for batch in _chunks(rows, 100):
        statement = insert(DistanceCache).values(batch)
        db.execute(statement.on_conflict_do_update(
            index_elements=["user_id", "origin_key", "dest_key"],
            set_={name: getattr(statement.excluded, name) for name in
                  ("km", "min", "updated_at", "expires_at")}))
    db.commit()


def invalidate_key(db: Session, key: str, user_id: int | None = None):
    q = db.query(DistanceCache).filter(or_(
        DistanceCache.origin_key == key, DistanceCache.dest_key == key,
        DistanceCache.origin_key.startswith(key + "|", autoescape=True),
        DistanceCache.dest_key.startswith(key + "|", autoescape=True)))
    if user_id is not None:
        q = q.filter(DistanceCache.user_id == user_id)
    q.delete(synchronize_session=False)
    db.commit()


def cleanup_expired(db: Session, user_id: int | None = None) -> int:
    now = datetime.utcnow()
    q = db.query(DistanceCache).filter(or_(
        DistanceCache.origin_key.contains("|departure=", autoescape=True),
        DistanceCache.dest_key.contains("|departure=", autoescape=True),
        (DistanceCache.expires_at.is_not(None) & (DistanceCache.expires_at <= now))))
    if user_id is not None:
        q = q.filter(DistanceCache.user_id == user_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def cleanup_older_than(db: Session, days: int = 15, user_id: int | None = None) -> int:
    cutoff = datetime.utcnow() - timedelta(days=max(1, int(days)))
    q = db.query(DistanceCache).filter(or_(DistanceCache.updated_at.is_(None), DistanceCache.updated_at < cutoff))
    if user_id is not None:
        q = q.filter(DistanceCache.user_id == user_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def invalidate_company(db: Session, user_id: int) -> int:
    deleted = db.query(DistanceCache).filter(DistanceCache.user_id == user_id).delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)
