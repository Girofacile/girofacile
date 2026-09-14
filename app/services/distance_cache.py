"""
Cache aziendale delle distanze/tempi tra due punti (clienti/depositi).

Obiettivi:
- ridurre le chiamate a Google Routes;
- tenere separate le tratte di ogni azienda;
- evitare che la cache cresca all'infinito.

Ogni tratta è collegata a user_id, cioè all'azienda proprietaria dei dati.
Le chiavi includono anche il prefisso azienda per restare sicure anche su
installazioni che avevano già un vecchio vincolo UNIQUE(origin_key, dest_key).
La cache scade dopo 15 giorni di default.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, tuple_
from sqlalchemy.orm import Session

from ..models import DistanceCache


def cache_ttl_days() -> int:
    try:
        return max(1, int(os.getenv("DISTANCE_CACHE_TTL_DAYS", "15")))
    except Exception:
        return 15


def cache_expires_at(now: datetime | None = None) -> datetime:
    now = now or datetime.utcnow()
    return now + timedelta(days=cache_ttl_days())


def _company_prefix(user_id) -> str:
    return f"company:{int(user_id)}" if user_id is not None else "company:0"


def customer_key(customer_id, user_id=None) -> str:
    base = f"customer:{customer_id}"
    return f"{_company_prefix(user_id)}:{base}" if user_id is not None else base


def deposit_key(deposit_id, user_id=None) -> str:
    base = f"deposit:{deposit_id}"
    return f"{_company_prefix(user_id)}:{base}" if user_id is not None else base


def geo_key(lat, lon, user_id=None) -> str:
    base = f"geo:{float(lat):.5f},{float(lon):.5f}"
    return f"{_company_prefix(user_id)}:{base}" if user_id is not None else base


def point_key(deposit_id=None, customer_id=None, lat=None, lon=None, user_id=None) -> str:
    """Costruisce la chiave più stabile disponibile per un punto del giro."""
    if deposit_id is not None:
        return deposit_key(deposit_id, user_id=user_id)
    if customer_id is not None:
        return customer_key(customer_id, user_id=user_id)
    return geo_key(lat, lon, user_id=user_id)


def get_pairs(db: Session, user_id: int, pairs: list[tuple[str, str]]) -> dict:
    """Ritorna dict {(origin_key, dest_key): {km, min}} per coppie valide e non scadute."""
    if not pairs:
        return {}
    unique_pairs = list({p for p in pairs})
    now = datetime.utcnow()
    rows = (
        db.query(DistanceCache)
        .filter(DistanceCache.user_id == user_id)
        .filter(tuple_(DistanceCache.origin_key, DistanceCache.dest_key).in_(unique_pairs))
        .filter(or_(DistanceCache.expires_at.is_(None), DistanceCache.expires_at > now))
        .all()
    )
    return {(r.origin_key, r.dest_key): {"km": r.km, "min": r.min} for r in rows}


def save_pairs(db: Session, user_id: int, entries: list[tuple[str, str, float, float]]):
    """Salva/aggiorna una lista di (origin_key, dest_key, km, min) nella cache aziendale."""
    if not entries:
        return
    keys = [(o, d) for o, d, _, _ in entries]
    existing = {
        (r.origin_key, r.dest_key): r
        for r in db.query(DistanceCache)
        .filter(DistanceCache.user_id == user_id)
        .filter(tuple_(DistanceCache.origin_key, DistanceCache.dest_key).in_(list({k for k in keys})))
        .all()
    }
    now = datetime.utcnow()
    expires_at = cache_expires_at(now)
    for origin_key, dest_key, km, minutes in entries:
        row = existing.get((origin_key, dest_key))
        if row:
            row.km = km
            row.min = minutes
            row.updated_at = now
            row.expires_at = expires_at
        else:
            row = DistanceCache(
                user_id=user_id,
                origin_key=origin_key,
                dest_key=dest_key,
                km=km,
                min=minutes,
                updated_at=now,
                expires_at=expires_at,
            )
            db.add(row)
            existing[(origin_key, dest_key)] = row
    db.commit()


def invalidate_key(db: Session, key: str, user_id: int | None = None):
    """Cancella tutte le tratte cachate che coinvolgono questo punto.

    Da chiamare quando un cliente o un deposito cambia indirizzo/coordinate.
    Se user_id è passato, la cancellazione resta confinata all'azienda.
    """
    q = db.query(DistanceCache).filter(or_(DistanceCache.origin_key == key, DistanceCache.dest_key == key))
    if user_id is not None:
        q = q.filter(DistanceCache.user_id == user_id)
    q.delete(synchronize_session=False)
    db.commit()


def cleanup_expired(db: Session, user_id: int | None = None) -> int:
    """Elimina tratte cache scadute. Ritorna il numero indicativo di righe eliminate."""
    now = datetime.utcnow()
    q = db.query(DistanceCache).filter(DistanceCache.expires_at.is_not(None), DistanceCache.expires_at <= now)
    if user_id is not None:
        q = q.filter(DistanceCache.user_id == user_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def cleanup_older_than(db: Session, days: int = 15, user_id: int | None = None) -> int:
    """Elimina tratte aggiornate da più di N giorni, anche se expires_at non era valorizzato."""
    cutoff = datetime.utcnow() - timedelta(days=max(1, int(days)))
    q = db.query(DistanceCache).filter(
        or_(DistanceCache.updated_at.is_(None), DistanceCache.updated_at < cutoff)
    )
    if user_id is not None:
        q = q.filter(DistanceCache.user_id == user_id)
    deleted = q.delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)


def invalidate_company(db: Session, user_id: int) -> int:
    """Cancella tutta la cache tratte di una singola azienda."""
    deleted = db.query(DistanceCache).filter(DistanceCache.user_id == user_id).delete(synchronize_session=False)
    db.commit()
    return int(deleted or 0)
