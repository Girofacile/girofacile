#!/usr/bin/env python3
"""Inizializza PostgreSQL GiroFacile con schema e dati demo minimi.

Uso:
  python scripts/init_postgres_demo.py

Richiede DATABASE_URL PostgreSQL nel file .env.
"""
from __future__ import annotations

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Importare app.main esegue migrate_database(), ensure_default_user() e harden_tenant_schema().
import app.main  # noqa: F401

print("[OK] Schema PostgreSQL creato/aggiornato e account demo verificato.")
print("Login demo:")
print(f"  APP_USER={os.getenv('APP_USER', 'azienda_demo')}")
print("  APP_PASSWORD=valore nel file .env")
