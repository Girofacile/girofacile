import base64
import hmac
import os
import time
import json
import secrets
import re
import unicodedata
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


COMMON_PASSWORDS = {
    "password", "password1", "password123", "password2026",
    "admin", "admin123", "admin2026", "administrator",
    "girofacile", "girofacile123", "girofacile2026",
    "12345678", "123456789", "1234567890", "qwerty", "qwerty123",
    "abcdefghi", "letmein", "welcome", "benvenuto", "changeme",
}
RISKY_PASSWORD_SEQUENCES = (
    "123456", "654321", "abcdef", "fedcba", "qwerty", "asdfgh", "zxcvbn", "qazwsx",
)


def _password_compact(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch.lower() for ch in normalized if ch.isalnum())


def _password_context_terms(context_values=None) -> set[str]:
    terms: set[str] = set()
    for value in context_values or ():
        raw = str(value or "").strip()
        if not raw:
            continue
        compact = _password_compact(raw)
        if len(compact) >= 6:
            terms.add(compact)
        for token in re.split(r"[^A-Za-zÀ-ÖØ-öø-ÿ0-9]+", raw):
            token = _password_compact(token)
            if len(token) >= 4:
                terms.add(token)
    return terms


def password_strength(password: str, context_values=None) -> dict:
    """Valuta la password con la stessa policy usata da registrazione e reset.

    La lunghezza minima e i requisiti di composizione sono vincoli espliciti
    del prodotto. Il punteggio aggiunge un controllo contro password formalmente
    valide ma prevedibili o basate sui dati dell'account/azienda.
    """
    password = password or ""
    compact = _password_compact(password)
    checks = {
        "length": len(password) >= 8,
        "uppercase": any(ch.isupper() for ch in password),
        "lowercase": any(ch.islower() for ch in password),
        "special": any(not ch.isalnum() and not ch.isspace() for ch in password),
        "no_outer_spaces": password.strip() == password,
    }

    risks: list[str] = []
    common_pattern = re.fullmatch(r"(?:password|admin|utente|user|azienda)\d{0,6}", compact or "")
    if compact in COMMON_PASSWORDS or common_pattern or "girofacile" in compact or "qwerty" in compact:
        risks.append("common")
    if any(sequence in compact for sequence in RISKY_PASSWORD_SEQUENCES):
        risks.append("sequence")
    if re.search(r"(.)\1{3,}", password, flags=re.IGNORECASE) or re.search(r"(.{2,4})\1{2,}", password, flags=re.IGNORECASE):
        risks.append("repeated")

    context_terms = _password_context_terms(context_values)
    if compact and any(term in compact for term in context_terms):
        risks.append("context")

    points = 0
    if checks["length"]:
        points += 1
    if checks["uppercase"] and checks["lowercase"]:
        points += 1
    if checks["special"]:
        points += 1
    if any(ch.isdigit() for ch in password):
        points += 1
    if len(password) >= 12:
        points += 1
    if len(password) >= 16:
        points += 1
    if len(set(password.casefold())) >= 5:
        points += 1

    hard_ok = all(checks.values())
    if risks:
        points = min(points, 1)

    if risks:
        level, label = "very_weak", "Molto debole"
    elif not hard_ok or points < 4:
        level, label = "weak", "Debole"
    elif points >= 6:
        level, label = "strong", "Forte"
    else:
        level, label = "good", "Buona"

    acceptable = hard_ok and not risks and points >= 4

    if not checks["length"]:
        message = "La password deve contenere almeno 8 caratteri"
    elif not checks["uppercase"]:
        message = "La password deve contenere almeno una lettera maiuscola"
    elif not checks["lowercase"]:
        message = "La password deve contenere almeno una lettera minuscola"
    elif not checks["special"]:
        message = "La password deve contenere almeno un carattere speciale"
    elif not checks["no_outer_spaces"]:
        message = "La password non può iniziare o terminare con spazi"
    elif "context" in risks:
        message = "La password non deve contenere nome azienda, nome utente, email o altri dati dell'account"
    elif "common" in risks:
        message = "Questa password è troppo comune o prevedibile"
    elif "sequence" in risks:
        message = "Evita sequenze prevedibili come 123456, abcdef o qwerty"
    elif "repeated" in risks:
        message = "Evita caratteri o gruppi ripetuti troppe volte"
    elif not acceptable:
        message = "La password è ancora troppo debole: rendila meno prevedibile"
    else:
        message = "Password accettabile"

    return {
        "acceptable": acceptable,
        "level": level,
        "label": label,
        "score": points,
        "checks": checks,
        "risks": risks,
        "message": message,
    }


def validate_password_strength(password: str, context_values=None) -> None:
    result = password_strength(password, context_values=context_values)
    if not result["acceptable"]:
        raise ValueError(result["message"])

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


def make_account_token(role: str, account_id: int, password_hash: str) -> str:
    now = int(time.time())
    data = {'v': 2, 'role': role, 'id': account_id, 'iat': now,
            'exp': now + 86400 * (7 if role in ('user', 'collaborator') else 30),
            'nonce': secrets.token_hex(16),
            'credential': _sign(f'{role}:{account_id}:{password_hash}')}
    body = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return f'{body}.{_sign(body)}'


def read_account_token(token, role, password_hash=None):
    try:
        body, sig = token.rsplit('.', 1)
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        data = json.loads(base64.urlsafe_b64decode(body))
        now = int(time.time())
        if data['v'] != 2 or data['role'] != role or not data['iat'] <= now < data['exp']:
            return None
        if password_hash is not None and not hmac.compare_digest(
                data['credential'], _sign(f"{role}:{data['id']}:{password_hash}")):
            return None
        return data
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def make_token(user_id: int, password_hash: str) -> str:
    return make_account_token('user', user_id, password_hash)


def verify_token(token: str | None) -> int | None:
    data = read_account_token(token, 'user')
    return data['id'] if data else None


# -----------------------------------------------------------------------
# Token sessione Super Admin SaaS
# -----------------------------------------------------------------------
def make_superadmin_token(username: str) -> str:
    raw = f"superadmin:{username}:{int(time.time())}:{secrets.token_hex(16)}"
    token = base64.urlsafe_b64encode(raw.encode()).decode()
    return f"{token}.{_sign(token)}"


def make_superadmin_collaborator_token(collaborator_id: int) -> str:
    raw = f"superadmin_collaborator:{int(collaborator_id)}:{int(time.time())}:{secrets.token_hex(16)}"
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
        kind, username, ts, *_nonce = raw.split(":")
        if kind not in ("superadmin", "superadmin_collaborator"):
            return None
        if not 0 <= int(time.time()) - int(ts) < 60 * 60 * 24 * 7:
            return None
        if kind == "superadmin_collaborator":
            return f"collab:{username}"
        return username
    except Exception:
        return None
