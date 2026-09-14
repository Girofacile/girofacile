"""Controllo rapido integrità multi-azienda GiroFacile.

Esegue un check sui record SaaS principali e segnala eventuali righe senza
user_id/azienda. Utile prima e dopo migrazione PostgreSQL.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.database import engine

TABLES = [
    "customers",
    "deposits",
    "vehicles",
    "drivers",
    "agents",
    "route_plans",
    "distance_cache",
    "notifications",
    "activity_events",
]


def main():
    total_bad = 0
    with engine.begin() as conn:
        for table in TABLES:
            exists = conn.execute(text(
                "select 1 from information_schema.tables where table_name = :t"
            ), {"t": table}).scalar() if not engine.dialect.name.startswith("sqlite") else None
            if engine.dialect.name.startswith("sqlite"):
                exists = conn.execute(text("select name from sqlite_master where type='table' and name=:t"), {"t": table}).scalar()
            if not exists:
                continue
            try:
                bad = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL")).scalar() or 0
                total = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0
                print(f"{table}: {total} record, {bad} senza azienda")
                total_bad += bad
            except Exception as e:
                print(f"{table}: controllo non riuscito: {e}")
    if total_bad:
        print(f"\nATTENZIONE: trovati {total_bad} record senza user_id.")
        raise SystemExit(1)
    print("\nOK: tutti i record controllati sono associati a una azienda.")


if __name__ == "__main__":
    main()
