"""Indirizzo usato nei link che GiroFacile manda fuori (inviti, email, tracking, QR).

In produzione è sempre APP_BASE_URL. Fuori produzione il portale admin può impostare
un indirizzo per i test in locale (es. http://192.168.1.20:8000), così i link si aprono
anche dal telefono collegato alla stessa rete. Il valore è salvato tra le impostazioni
della piattaforma (chiave LOCAL_BASE_URL_KEY) e caricato all'avvio.
"""
import re

from . import config

LOCAL_BASE_URL_KEY = "local_test_base_url"
_URL_RE = re.compile(r"^https?://[A-Za-z0-9.\-\[\]:]+(?::\d{1,5})?$")
_override = ""


def local_override_allowed() -> bool:
    return config.APP_ENV != "production"


def base_url(default: str | None = None) -> str:
    """Indirizzo per i link: quello per i test se impostato (mai in produzione), altrimenti il default."""
    if _override and local_override_allowed():
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


def set_override(value: str | None) -> None:
    global _override
    _override = normalize(value) if local_override_allowed() else ""


def current_override() -> str:
    return _override if local_override_allowed() else ""


def load(db) -> None:
    """Legge l'indirizzo per i test salvato dal portale admin (all'avvio dell'app)."""
    from ..models import SaaSPlatformSetting
    row = db.query(SaaSPlatformSetting).filter(SaaSPlatformSetting.key == LOCAL_BASE_URL_KEY).first()
    try:
        set_override(row.value if row else "")
    except ValueError:
        set_override("")
