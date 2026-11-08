"""Superadmin routing diagnostics and server maintenance."""


from datetime import datetime
import os
import platform
import json
import shutil
import socket
import sys
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ..core.config import APP_BASE_URL
from ..core import links
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


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/routing-health")
def admin_routing_health(db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_server_maintenance")
    _require_perm(superadmin, "test_service_connections")
    from ..services.routing_health import routing_health
    return routing_health(db)


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
            "backup_frequency": "manuale",
            "backup_storage_target": "locale",
            "server_console_url": _setting_value(db, "server_console_url", ""),
        },
        "services": _service_key_status(db),
        "backups": backups,
        "last_backup": backups[0] if backups else None,
    }


@router.put("/server-maintenance/settings")
def admin_server_maintenance_settings(payload: dict, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_server_maintenance")
    if payload.get("stripe_secret_key"):
        raise HTTPException(400, "La chiave Stripe si configura nell’ambiente del server; il pannello non la modifica")
    if payload.get("backup_frequency", "manuale") != "manuale" or payload.get("backup_storage_target", "locale") != "locale":
        raise HTTPException(400, "Dal pannello sono disponibili soltanto backup manuali locali; automazione e storage remoto richiedono configurazione di deploy")
    # Impostazioni generali server: richiedono permesso piattaforma/manutenzione.
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
    if payload.get("stripe_secret_key"):
        raise HTTPException(400, "La chiave Stripe si configura nell’ambiente del server; il pannello non la modifica")
    if payload.get("backup_frequency", "manuale") != "manuale" or payload.get("backup_storage_target", "locale") != "locale":
        raise HTTPException(400, "Dal pannello sono disponibili soltanto backup manuali locali; automazione e storage remoto richiedono configurazione di deploy")
    allowed = {"google_maps_api_key", "openai_api_key", "shopify_domain"}
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


# ---------------------------------------------------------------- indirizzi per i test in locale



def _network_addresses() -> list[dict]:
    """Indirizzi IPv4 di questo computer raggiungibili da altri dispositivi (Wi-Fi, Tailscale)."""
    found: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))  # nessun pacchetto inviato: serve solo a sapere l'interfaccia principale
        found.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass

    def kind(ip: str) -> str:
        first, second = (int(part) for part in ip.split(".")[:2])
        if first == 100 and 64 <= second <= 127:
            return "Tailscale"
        if first == 192 and second == 168 or first == 10 or first == 172 and 16 <= second <= 31:
            return "Rete locale (Wi-Fi o cavo)"
        return "Altra rete"
    return [{"ip": ip, "kind": kind(ip)} for ip in sorted(found) if not ip.startswith(("127.", "169.254.", "0."))]


def _local_addresses_payload(request: Request) -> dict:
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    suffix = "" if port in (80, 443) else f":{port}"
    custom_portals = links.current_portals()
    return {
        "enabled": links.local_override_allowed(),
        "current": links.base_url(),
        "custom": links.current_override(),
        "default": APP_BASE_URL,
        "this_page": f"{request.url.scheme}://{request.url.hostname}{suffix}",
        "suggestions": [{**item, "url": f"http://{item['ip']}{suffix}"} for item in _network_addresses()],
        "portals": [{"key": key, "name": name, "hint": hint, "custom": custom_portals.get(key, ""),
                     "base": links.base_url(portal=key), "url": links.base_url(portal=key) + path}
                    for key, (name, path, hint) in links.PORTALS.items()],
    }


@router.get("/local-addresses")
def admin_local_addresses(request: Request, superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_server_maintenance")
    return _local_addresses_payload(request)


@router.put("/local-addresses")
def admin_local_addresses_save(payload: dict, request: Request, db: Session = Depends(get_db), superadmin: dict = Depends(require_superadmin)):
    _require_perm(superadmin, "view_server_maintenance")
    if not links.local_override_allowed():
        raise HTTPException(403, "In produzione i link usano sempre l'indirizzo ufficiale")
    try:
        value = links.normalize(payload.get("base_url"))
        portals = links.normalize_portals(payload.get("portals")) if "portals" in payload else links.current_portals()
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    _set_setting_value(db, links.LOCAL_BASE_URL_KEY, value)
    _set_setting_value(db, links.LOCAL_PORTAL_URLS_KEY, json.dumps(portals))
    detail = ", ".join(f"{links.PORTALS[key][0]} {url}" for key, url in portals.items())
    _activity(db, superadmin.get("username"), "local_base_url_updated",
              f"Indirizzi per i test: {value or 'predefinito'}" + (f" · {detail}" if detail else ""), "info")
    db.commit()
    links.set_override(value, portals)
    return _local_addresses_payload(request)
