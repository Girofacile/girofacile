"""Indirizzo del database costruito dai pezzi (Docker Compose).

Compose non sa codificare la password dentro un URL: con caratteri come @ : / # l'indirizzo
si spezza (es. «audit@password» diventa l'host «password@postgres»). Se DATABASE_URL è vuoto
e c'è POSTGRES_HOST, l'indirizzo si costruisce qui con la password codificata; PostgreSQL
riceve invece la password originale, quindi le due restano uguali.
"""
import os


def compose_database_url(env=None) -> str:
    env = os.environ if env is None else env
    explicit = (env.get("DATABASE_URL") or "").strip()
    host = (env.get("POSTGRES_HOST") or "").strip()
    if explicit or not host:
        return explicit
    from sqlalchemy.engine import URL
    return URL.create(
        "postgresql+psycopg2",
        username=(env.get("POSTGRES_USER") or "girofacile").strip(),
        password=env.get("POSTGRES_PASSWORD") or "",
        host=host,
        port=int((env.get("POSTGRES_PORT") or "5432").strip()),
        database=(env.get("POSTGRES_DB") or "girofacile").strip(),
    ).render_as_string(hide_password=False)


def apply_composed_database_url() -> None:
    """Scrive l'indirizzo costruito in DATABASE_URL, così tutto il resto lo legge come sempre."""
    url = compose_database_url()
    if url and not (os.environ.get("DATABASE_URL") or "").strip():
        os.environ["DATABASE_URL"] = url
