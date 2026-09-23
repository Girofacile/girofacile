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
from urllib.parse import urlsplit, unquote
import uuid
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
    sys.path.insert(0, str(ROOT))
    from app.services.backups import backup_directory
    return backup_directory()


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


def postgres_connection(database_url):
    parsed = urlsplit(normalize_database_url(database_url))
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip('/'):
        raise RuntimeError("DATABASE_URL PostgreSQL non valido")
    # Libpq accepts a password-free URI; preserve SSL/query options.
    from urllib.parse import urlunsplit
    host = parsed.hostname
    if ':' in host:
        host = '[' + host + ']'
    if parsed.port:
        host += ':' + str(parsed.port)
    if parsed.username:
        host = parsed.username + '@' + host
    safe_url = urlunsplit((parsed.scheme, host, parsed.path, parsed.query, ''))
    env = os.environ.copy()
    if parsed.password:
        env['PGPASSWORD'] = unquote(parsed.password)
    return safe_url, env


def backup_postgres(database_url: str, folder: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = folder / f"girofacile_postgres_{stamp}_{uuid.uuid4().hex[:8]}.dump"
    partial = dest.with_suffix('.partial')
    pg_dump, pg_restore = shutil.which("pg_dump"), shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        raise RuntimeError("Client PostgreSQL mancante: servono pg_dump e pg_restore")
    url, env = postgres_connection(database_url)
    try:
        subprocess.run([pg_dump, "--format=custom", "--no-owner", "--no-acl", "--dbname", url,
                        "--file", str(partial)], env=env, check=True, capture_output=True, timeout=240)
        if not partial.is_file() or partial.stat().st_size == 0:
            raise RuntimeError("Archivio backup vuoto")
        subprocess.run([pg_restore, "--list", str(partial)], check=True, capture_output=True, timeout=30)
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise RuntimeError("Backup PostgreSQL non riuscito o archivio non valido. Verifica connessione, spazio e versione del client.") from None
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
