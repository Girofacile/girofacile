#!/usr/bin/env python3
"""Migrazione dati da SQLite a PostgreSQL per GiroFacile.

Uso tipico:
python scripts/migrate_sqlite_to_postgres.py --sqlite data/girofacile.db --postgres postgresql+psycopg2://girofacile:password@localhost:5432/girofacile

Nota: esegui prima un backup. Lo script crea le tabelle nel database PostgreSQL
usando i modelli SQLAlchemy e importa i dati principali preservando gli ID.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import Session

import sys
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base  # noqa: E402
import app.models  # noqa: F401,E402  # importa tutti i modelli


ORDERED_TABLES = [
    "users", "deposits", "agents", "customers", "vehicles", "drivers",
    "route_plans", "deliveries", "delivery_statuses", "route_tokens",
    "driver_accounts", "driver_setup_tokens", "agent_accounts", "agent_setup_tokens",
    "password_reset_tokens", "chat_messages", "support_tickets",
]


def normalize_pg(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True, help="Percorso file SQLite, es. data/girofacile.db")
    parser.add_argument("--postgres", required=True, help="DATABASE_URL PostgreSQL")
    parser.add_argument("--replace", action="store_true", help="Svuota le tabelle PostgreSQL prima dell'import")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        raise FileNotFoundError(sqlite_path)

    src_engine = create_engine(f"sqlite:///{sqlite_path}", future=True)
    dst_engine = create_engine(normalize_pg(args.postgres), future=True)

    Base.metadata.create_all(bind=dst_engine)
    src_meta = MetaData()
    src_meta.reflect(bind=src_engine)
    dst_meta = MetaData()
    dst_meta.reflect(bind=dst_engine)

    with dst_engine.begin() as dst_conn:
        if args.replace:
            for table_name in reversed(ORDERED_TABLES):
                if table_name in dst_meta.tables:
                    dst_conn.execute(dst_meta.tables[table_name].delete())

        for table_name in ORDERED_TABLES:
            if table_name not in src_meta.tables or table_name not in dst_meta.tables:
                continue
            src_table = src_meta.tables[table_name]
            dst_table = dst_meta.tables[table_name]
            rows = []
            with src_engine.connect() as src_conn:
                for row in src_conn.execute(select(src_table)).mappings():
                    data = {k: v for k, v in dict(row).items() if k in dst_table.c}
                    rows.append(data)
            if rows:
                dst_conn.execute(dst_table.insert(), rows)
                print(f"[MIGRAZIONE] {table_name}: {len(rows)} righe")

    print("[MIGRAZIONE] Completata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
