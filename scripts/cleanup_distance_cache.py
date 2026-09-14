"""Pulizia cache Google Routes di GiroFacile.

Elimina automaticamente le tratte salvate da più di N giorni.
Default: 15 giorni, configurabile con DISTANCE_CACHE_TTL_DAYS.

Uso:
    python scripts/cleanup_distance_cache.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.distance_cache import cleanup_expired, cleanup_older_than, cache_ttl_days


def main() -> int:
    days = cache_ttl_days()
    with SessionLocal() as db:
        expired = cleanup_expired(db)
        old = cleanup_older_than(db, days=days)
    print(f"[CACHE] Pulizia completata: scadenza={days} giorni, righe_scadute={expired}, righe_vecchie={old}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
