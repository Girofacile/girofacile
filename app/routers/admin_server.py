"""Admin server: extracted from the SaaS administration router."""
from datetime import datetime
import os
import platform
import shutil
import sys
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..core.config import APP_BASE_URL
from ..core.dependencies import require_superadmin
from ..database import get_db, engine

from .admin_helpers import (
    _activity,
    _bool_to_str,
    _database_kind_label,
    _list_backups,
    _mask_secret,
    _project_root,
    _require_perm,
    _safe_backup_name,
    _service_key_status,
    _set_setting_value,
    _setting_value,
    _str_to_bool,
)

router = APIRouter()


@router.get("/server-maintenance")
def admin_server_maintenance(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_server_maintenance")
    root = _project_root()
    usage = shutil.disk_usage(root)
    backups = _list_backups()
    return {
        "environment": os.getenv("APP_ENV", "locale/produzione"),
        "version": "v72",
        "app": {
            "status": "online",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "root": str(root),
            "base_url": APP_BASE_URL,
        },
        "database": {
            "status": "raggiungibile",
            "type": _database_kind_label(),
            "url_masked": _mask_secret(os.getenv("DATABASE_URL", ""), left=18, right=12),
            "host": getattr(engine.url, "host", None),
            "database": getattr(engine.url, "database", None),
            "pool_size": os.getenv("DB_POOL_SIZE", "5"),
        },
        "disk": {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        },
        "settings": {
            "maintenance_mode": _str_to_bool(_setting_value(db, "maintenance_mode", "false")),
            "backup_frequency": _setting_value(db, "backup_frequency", "manuale"),
            "backup_storage_target": _setting_value(db, "backup_storage_target", "locale"),
            "server_console_url": _setting_value(db, "server_console_url", ""),
        },
        "services": _service_key_status(db),
        "backups": backups,
        "last_backup": backups[0] if backups else None,
    }


@router.put("/server-maintenance/settings")
def admin_server_maintenance_settings(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    # Impostazioni generali server: richiedono permesso piattaforma/manutenzione.
    _require_perm(superadmin, "view_server_maintenance")
    if "maintenance_mode" in payload:
        _require_perm(superadmin, "toggle_maintenance")
        _set_setting_value(db, "maintenance_mode", _bool_to_str(payload.get("maintenance_mode")))
        _activity(db, superadmin.get("username"), "maintenance_mode_updated", f"Modalità manutenzione: {bool(payload.get('maintenance_mode'))}", "warning")
    if "backup_frequency" in payload:
        _require_perm(superadmin, "create_backups")
        _set_setting_value(db, "backup_frequency", str(payload.get("backup_frequency") or "manuale")[:80])
    if "backup_storage_target" in payload:
        _require_perm(superadmin, "create_backups")
        _set_setting_value(db, "backup_storage_target", str(payload.get("backup_storage_target") or "locale")[:120])
    if "server_console_url" in payload:
        _require_perm(superadmin, "advanced_server_access")
        _set_setting_value(db, "server_console_url", str(payload.get("server_console_url") or "")[:500])
    db.commit()
    return admin_server_maintenance(db, superadmin)


@router.put("/server-maintenance/keys")
def admin_server_maintenance_keys(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "manage_service_keys")
    allowed = {"google_maps_api_key", "openai_api_key", "stripe_secret_key", "shopify_domain"}
    changed = []
    for key in allowed:
        if key in payload:
            _set_setting_value(db, key, str(payload.get(key) or "").strip())
            changed.append(key)
    _activity(db, superadmin.get("username"), "service_keys_updated", "Aggiornate chiavi servizi: " + ", ".join(changed), "warning")
    db.commit()
    return {"ok": True, "services": _service_key_status(db)}


@router.post("/server-maintenance/test-service")
def admin_server_test_service(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "test_service_connections")
    service = (payload.get("service") or "").strip().lower()
    statuses = {s["key"]: s for s in _service_key_status(db)}
    if service not in statuses:
        raise HTTPException(400, "Servizio non riconosciuto")
    row = statuses[service]
    ok = bool(row.get("configured"))
    _activity(db, superadmin.get("username"), "service_connection_test", f"Test servizio {row.get('name')}: {'ok' if ok else 'non configurato'}")
    return {
        "service": service,
        "ok": ok,
        "message": "Configurazione presente. Il test reale API può essere esteso nella prossima versione." if ok else "Servizio non configurato o chiave mancante.",
    }


@router.post("/server-maintenance/backups")
def admin_create_backup(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "create_backups")
    import subprocess
    result = subprocess.run([sys.executable, "scripts/backup_database.py"], cwd=str(_project_root()), capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise HTTPException(400, result.stderr.strip() or result.stdout.strip() or "Backup PostgreSQL non riuscito")
    backups_now = _list_backups()
    if not backups_now:
        raise HTTPException(400, "Backup completato ma file non trovato nella cartella backup")
    out = _safe_backup_name(backups_now[0]["filename"])
    _activity(db, superadmin.get("username"), "database_backup_created", f"Creato backup PostgreSQL {out.name}")
    db.commit()
    return {"ok": True, "backup": {"filename": out.name, "size_bytes": out.stat().st_size, "created_at": datetime.fromtimestamp(out.stat().st_mtime).isoformat()}, "backups": _list_backups()}


@router.get("/server-maintenance/backups/{filename}")
def admin_download_backup(filename: str, superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "download_backups")
    path = _safe_backup_name(filename)
    return FileResponse(str(path), media_type="application/octet-stream", filename=path.name)


@router.post("/server-maintenance/restart-app")
def admin_restart_app(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "restart_application")
    _activity(db, superadmin.get("username"), "restart_requested", "Richiesto riavvio applicazione da Super Admin", "warning")
    db.commit()
    return {"ok": True, "message": "Richiesta registrata. In produzione il comando reale va collegato a systemd con permessi limitati."}


@router.post("/server-maintenance/advanced-access")
def admin_advanced_server_access(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "advanced_server_access")
    host = (payload.get("host") or "").strip()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not host or not username or not password:
        raise HTTPException(400, "Inserisci host, username e password server")
    _activity(db, superadmin.get("username"), "advanced_server_access_attempt", f"Accesso avanzato richiesto per {username}@{host}", "warning")
    db.commit()
    return {
        "ok": True,
        "message": "Accesso validato lato pannello. Per aprire una console reale collega un terminale esterno protetto e imposta l'URL nella sezione Server / Manutenzione. La password non viene salvata.",
    }
