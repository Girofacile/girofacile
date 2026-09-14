import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


def _load_local_env() -> None:
    """Carica il file .env locale prima di inizializzare SQLAlchemy.

    Serve soprattutto in locale/produzione semplice, dove DATABASE_URL viene
    definito nel file .env e non nelle variabili di sistema del server.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
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
        # In caso di .env non leggibile, lasciamo che l'app usi i default.
        pass


def _normalize_database_url(url: str) -> str:
    """Normalizza DATABASE_URL per compatibilità con hosting e Postgres.

    Alcuni provider restituiscono URL nel formato postgres://..., mentre
    SQLAlchemy 2 preferisce postgresql+psycopg2://... quando usiamo psycopg2.
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


_load_local_env()

DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", "postgresql+psycopg2://girofacile:girofacile_local@localhost:5432/girofacile"))
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").strip().lower() in ["1", "true", "yes", "si", "sì"]

connect_args = {}
engine_kwargs = {"echo": DATABASE_ECHO, "pool_pre_ping": True, "future": True}

# v72: PostgreSQL è il database ufficiale. SQLite è stato rimosso dal flusso
# principale per evitare doppia compatibilità prima della messa in produzione.
# Lo sblocco legacy è previsto solo per lettura/migrazioni manuali temporanee.
if DATABASE_URL.startswith("sqlite") and os.getenv("ALLOW_SQLITE_LEGACY", "false").strip().lower() not in ["1", "true", "yes", "si", "sì"]:
    raise RuntimeError(
        "GiroFacile v72 usa PostgreSQL come database ufficiale. "
        "Imposta DATABASE_URL=postgresql+psycopg2://utente:password@host:5432/girofacile. "
        "SQLite è consentito solo con ALLOW_SQLITE_LEGACY=true per migrazioni temporanee."
    )

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    engine_kwargs.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
    })

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_kind() -> str:
    try:
        return make_url(DATABASE_URL).get_backend_name()
    except Exception:
        return "unknown"
