"""Indirizzi usati nei link che GiroFacile manda fuori (inviti, email, tracking, QR).

In produzione è sempre APP_BASE_URL. Fuori produzione il portale admin può impostare
indirizzi per i test in locale: uno generale (es. http://192.168.1.20:8000) e, se serve,
uno diverso per ogni portale (es. l'app autista su Tailscale). Ordine: indirizzo del
portale → indirizzo generale → APP_BASE_URL. Salvati tra le impostazioni della piattaforma
e caricati all'avvio.
"""
import json
import re

from . import config

LOCAL_BASE_URL_KEY = "local_test_base_url"
LOCAL_PORTAL_URLS_KEY = "local_test_portal_urls"
# Chiave → (nome, percorso, a cosa servono i suoi link)
PORTALS = {
    "app": ("Gestionale", "/login", "Ufficio; anche reimpostazione password, collaboratori, pagamenti e giri condivisi"),
    "mobile": ("Portale da telefono", "/mobile", "Il gestionale sul telefono"),
    "driver": ("App autista", "/driver", "Inviti e avvisi agli autisti"),
    "agent": ("Portale agenti", "/agent", "Inviti agli agenti"),
    "tracking": ("Tracking clienti", "/tracking", "Link «segui la consegna» per i clienti"),
    "admin": ("Super Admin", "/admin", "Email e accessi del pannello Super Admin"),
}
_URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-\[\]:]+(?::\d{1,5})?$")
_override = ""
_portals: dict[str, str] = {}


def local_override_allowed() -> bool:
    return config.APP_ENV != "production"


def base_url(default: str | None = None, portal: str | None = None) -> str:
    """Indirizzo per i link di un portale: quello per i test se impostato (mai in produzione), altrimenti il default."""
    if local_override_allowed():
        if portal and _portals.get(portal):
            return _portals[portal]
        if _override:
            return _override
    return (default if default is not None else config.APP_BASE_URL).rstrip("/")


def normalize(value: str | None) -> str:
    """«192.168.1.20:8000» → «http://192.168.1.20:8000»; vuoto = nessun indirizzo per i test."""
    text = (value or "").strip().rstrip("/")
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    if not _URL_RE.match(text):
        raise ValueError("Scrivi solo l'indirizzo e la porta, ad esempio http://192.168.1.20:8000")
    return text


def normalize_portals(values: dict | None) -> dict[str, str]:
    result = {}
    for key, value in (values or {}).items():
        if key not in PORTALS:
            raise ValueError(f"Portale sconosciuto: {key}")
        try:
            clean = normalize(value)
        except ValueError as exc:
            raise ValueError(f"{PORTALS[key][0]}: {exc}") from exc
        if clean:
            result[key] = clean
    return result


def set_override(value: str | None, portals: dict | None = None) -> None:
    global _override, _portals
    allowed = local_override_allowed()
    _override = normalize(value) if allowed else ""
    if portals is not None:
        _portals = normalize_portals(portals) if allowed else {}


def current_override() -> str:
    return _override if local_override_allowed() else ""


def current_portals() -> dict[str, str]:
    return dict(_portals) if local_override_allowed() else {}


def load(db) -> None:
    """Legge gli indirizzi per i test salvati dal portale admin (all'avvio dell'app)."""
    from ..models import SaaSPlatformSetting
    rows = {row.key: row.value for row in db.query(SaaSPlatformSetting).filter(
        SaaSPlatformSetting.key.in_([LOCAL_BASE_URL_KEY, LOCAL_PORTAL_URLS_KEY]))}
    try:
        portals = json.loads(rows.get(LOCAL_PORTAL_URLS_KEY) or "{}")
        set_override(rows.get(LOCAL_BASE_URL_KEY) or "", portals if isinstance(portals, dict) else {})
    except (ValueError, TypeError):
        set_override("", {})
