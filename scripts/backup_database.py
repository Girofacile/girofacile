#!/usr/bin/env python3
"""Backup PostgreSQL GiroFacile v72.

SQLite non è più il database ufficiale. Questo script usa pg_dump.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def normalize_database_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url[len("postgresql+psycopg2://"):]
    return url


def backup_dir() -> Path:
    raw = os.getenv("BACKUP_DIR", "./backups")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_old_backups(folder: Path) -> None:
    try:
        days = int(os.getenv("BACKUP_RETENTION_DAYS", "14"))
    except Exception:
        days = 14
    if days <= 0:
        return
    cutoff = datetime.now() - timedelta(days=days)
    for item in list(folder.glob("girofacile_postgres_*")):
        try:
            if datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                item.unlink()
        except Exception:
            pass


def backup_postgres(database_url: str, folder: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = folder / f"girofacile_postgres_{stamp}.dump"
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        raise RuntimeError("pg_dump non trovato. Installa PostgreSQL client / postgresql-client.")
    url = normalize_database_url(database_url)
    if not url.startswith("postgresql://"):
        raise RuntimeError("DATABASE_URL deve essere PostgreSQL in v72.")
    cmd = [pg_dump, "--format=custom", "--no-owner", "--no-acl", "--dbname", url, "--file", str(dest)]
    subprocess.run(cmd, check=True)
    return dest


def main() -> int:
    load_env()
    database_url = os.getenv("DATABASE_URL", "").strip()
    try:
        out = backup_postgres(database_url, backup_dir())
        cleanup_old_backups(out.parent)
        print(f"[BACKUP] Creato: {out}")
        return 0
    except Exception as exc:
        print(f"[BACKUP] Errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
