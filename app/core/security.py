import base64
import hmac
import os
import time
from hashlib import pbkdf2_hmac, sha256

from .config import APP_SECRET, PASSWORD_PBKDF2_ITERATIONS, PASSWORD_PEPPER


PASSWORD_SCHEME = "pbkdf2_sha256"
LEGACY_SHA256_HEX_LENGTH = 64


def _password_bytes(password: str) -> bytes:
    """Applica un pepper opzionale server-side prima dell'hash.

    Il pepper non viene salvato nel database: resta in .env e aumenta la
    protezione in caso di furto del solo database. Se PASSWORD_PEPPER non è
    configurato, il sistema resta compatibile con gli hash già presenti.
    """
    return f"{PASSWORD_PEPPER}{password}".encode("utf-8")


def hash_password(password: str) -> str:
    """Hash password professionale con salt univoco e PBKDF2-SHA256.

    Formato nuovo:
    pbkdf2_sha256$<iterazioni>$<salt_b64>$<digest_b64>

    Il vecchio formato "salt:digest" resta verificabile per compatibilità.
    """
    salt = os.urandom(16)
    iterations = max(int(PASSWORD_PBKDF2_ITERATIONS or 260000), 120000)
    digest = pbkdf2_hmac("sha256", _password_bytes(password), salt, iterations)
    return "$".join([
        PASSWORD_SCHEME,
        str(iterations),
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    ])


def _verify_pbkdf2_new(password: str, stored: str) -> bool:
    try:
        scheme, iterations_raw, salt_b64, digest_b64 = stored.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        got = pbkdf2_hmac("sha256", _password_bytes(password), salt, iterations)
        if hmac.compare_digest(got, expected):
            return True
        # Fallback di migrazione: consente il login agli hash creati prima
        # dell'introduzione del pepper, poi password_needs_rehash potrà
        # portarli al formato corrente al primo reset/login dove previsto.
        if PASSWORD_PEPPER:
            got_without_pepper = pbkdf2_hmac("sha256", password.encode(), salt, iterations)
            return hmac.compare_digest(got_without_pepper, expected)
        return False
    except Exception:
        return False


def _verify_pbkdf2_legacy(password: str, stored: str) -> bool:
    # Compatibilità con il formato precedente: salt_b64:digest_b64, senza pepper.
    try:
        salt_b64, digest_b64 = stored.split(":", 1)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        got = pbkdf2_hmac("sha256", password.encode(), salt, 120000)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def is_legacy_sha256_hash(stored: str | None) -> bool:
    if not stored or len(stored) != LEGACY_SHA256_HEX_LENGTH:
        return False
    allowed = set("0123456789abcdef")
    return all(ch in allowed for ch in stored.lower())


def verify_legacy_sha256_password(password: str, stored: str | None) -> bool:
    if not is_legacy_sha256_hash(stored):
        return False
    return hmac.compare_digest(sha256(password.encode()).hexdigest(), stored or "")


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith(PASSWORD_SCHEME + "$"):
        return _verify_pbkdf2_new(password, stored)
    if ":" in stored:
        return _verify_pbkdf2_legacy(password, stored)
    if is_legacy_sha256_hash(stored):
        return verify_legacy_sha256_password(password, stored)
    return False


def password_needs_rehash(stored: str | None) -> bool:
    """True se l'hash è vecchio o usa iterazioni inferiori alla policy attuale."""
    if not stored:
        return True
    if stored.startswith(PASSWORD_SCHEME + "$"):
        try:
            _, iterations_raw, _, _ = stored.split("$", 3)
            return int(iterations_raw) < int(PASSWORD_PBKDF2_ITERATIONS or 260000)
        except Exception:
            return True
    return True


def validate_password_strength(password: str) -> None:
    """Policy minima per nuove password e reset.

    Non blocca gli account esistenti: vale solo quando una password viene
    creata o reimpostata.
    """
    password = password or ""
    if len(password) < 8:
        raise ValueError("La password deve contenere almeno 8 caratteri")
    if password.strip() != password:
        raise ValueError("La password non può iniziare o terminare con spazi")
    if password.lower() in {"password", "password123", "girofacile", "girofacile123", "admin123", "12345678"}:
        raise ValueError("Scegli una password meno prevedibile")


def mask_sensitive_value(value: str | None, visible_start: int = 4, visible_end: int = 4) -> str:
    """Maschera chiavi, token e hash prima di mostrarli in interfacce admin."""
    if not value:
        return ""
    text = str(value)
    if len(text) <= visible_start + visible_end + 4:
        return "•" * min(len(text), 12)
    return f"{text[:visible_start]}{'•' * 12}{text[-visible_end:]}"


def _sign(value: str) -> str:
    return hmac.new(APP_SECRET.encode(), value.encode(), sha256).hexdigest()


def make_token(user_id: int) -> str:
    raw = f"{user_id}:{int(time.time())}"
    token = base64.urlsafe_b64encode(raw.encode()).decode()
    return f"{token}.{_sign(token)}"


def verify_token(token: str | None) -> int | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        raw = base64.urlsafe_b64decode(body.encode()).decode()
        user_id, ts = raw.split(":")
        if int(time.time()) - int(ts) > 60 * 60 * 24 * 7:
            return None
        return int(user_id)
    except Exception:
        return None


# -----------------------------------------------------------------------
# Token sessione Super Admin SaaS
# -----------------------------------------------------------------------
def make_superadmin_token(username: str) -> str:
    raw = f"superadmin:{username}:{int(time.time())}"
    token = base64.urlsafe_b64encode(raw.encode()).decode()
    return f"{token}.{_sign(token)}"


def make_superadmin_collaborator_token(collaborator_id: int) -> str:
    raw = f"superadmin_collaborator:{int(collaborator_id)}:{int(time.time())}"
    token = base64.urlsafe_b64encode(raw.encode()).decode()
    return f"{token}.{_sign(token)}"


def verify_superadmin_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(body)):
        return None
    try:
        raw = base64.urlsafe_b64decode(body.encode()).decode()
        kind, username, ts = raw.split(":", 2)
        if kind not in ("superadmin", "superadmin_collaborator"):
            return None
        if int(time.time()) - int(ts) > 60 * 60 * 24 * 7:
            return None
        if kind == "superadmin_collaborator":
            return f"collab:{username}"
        return username
    except Exception:
        return None
