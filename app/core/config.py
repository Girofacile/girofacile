import os
from pathlib import Path


def load_local_env():
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


load_local_env()

APP_USER = os.getenv("APP_USER", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "admin123")
# Credenziali del proprietario SaaS. Restano separate dagli account aziendali.
SUPERADMIN_USERNAME = os.getenv("SUPERADMIN_USERNAME", APP_USER).strip()
SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD", APP_PASSWORD).strip()
APP_SECRET = os.getenv("APP_SECRET", "dev-secret-change-me")
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
PASSWORD_PEPPER = os.getenv("PASSWORD_PEPPER", "").strip()
PASSWORD_PBKDF2_ITERATIONS = int(os.getenv("PASSWORD_PBKDF2_ITERATIONS", "260000"))
_raw_app_base_url = os.getenv("APP_BASE_URL", "https://girofacile.it").strip().rstrip("/")
_public_base_url = os.getenv("PUBLIC_BASE_URL", "https://girofacile.it").strip().rstrip("/")
if APP_ENV == "production" and (
    _raw_app_base_url.startswith("http://127.0.0.1")
    or _raw_app_base_url.startswith("https://127.0.0.1")
    or _raw_app_base_url.startswith("http://localhost")
    or _raw_app_base_url.startswith("https://localhost")
):
    APP_BASE_URL = _public_base_url
else:
    APP_BASE_URL = _raw_app_base_url or _public_base_url
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "").strip()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
GOOGLE_GEOCODING_ENABLED = os.getenv("GOOGLE_GEOCODING_ENABLED", "false").strip().lower() in ["1", "true", "yes", "si", "sì"]
GOOGLE_ROUTES_ENABLED = os.getenv("GOOGLE_ROUTES_ENABLED", "false").strip().lower() in ["1", "true", "yes", "si", "sì"]
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
LOCAL_TIMEZONE = os.getenv("GIROFACILE_TIMEZONE", "Europe/Rome")

# Notifiche errori Super Admin
ERROR_NOTIFICATIONS_ENABLED = os.getenv("ERROR_NOTIFICATIONS_ENABLED", "true").strip().lower() in ["1", "true", "yes", "si", "sì"]
ERROR_NOTIFICATIONS_EMAIL = os.getenv("ERROR_NOTIFICATIONS_EMAIL", "").strip()
ERROR_NOTIFICATION_MIN_SEVERITY = os.getenv("ERROR_NOTIFICATION_MIN_SEVERITY", "high").strip().lower()

# Prezzi piani (in centesimi per Stripe)
PLAN_PRICES = {
    "starter": {
        "name": "Starter",
        "price_eur": 19,
        "price_cents": 1900,
        "stripe_price_id": os.getenv("STRIPE_PRICE_STARTER", ""),
    },
    "business": {
        "name": "Business",
        "price_eur": 39,
        "price_cents": 3900,
        "stripe_price_id": os.getenv("STRIPE_PRICE_BUSINESS", ""),
    },
    "pro": {
        "name": "Pro",
        "price_eur": 79,
        "price_cents": 7900,
        "stripe_price_id": os.getenv("STRIPE_PRICE_PRO", ""),
    },
}

TRIAL_DAYS = 14

# Ambiente e sicurezza HTTP
