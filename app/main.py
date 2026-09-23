"""
GiroFacile SaaS - main.py
Setup applicazione + inclusione router.
Tutta la logica è nei moduli app/routers/ e app/services/.
"""
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .core.config import APP_PASSWORD, APP_USER
from .core.http_security import IS_PRODUCTION, login_rate_limit_middleware
from .core.security import hash_password
from .database import Base, engine, get_db
from .models import Agent, Customer, Deposit, Driver, RoutePlan, User, Vehicle, PasswordResetToken, DistanceCache
from .routers import (
    admin, agents, auth, billing, customers,
    deposits, reports, routes, operator, notifications, activity, settings, support, transfer_portal, driver as driver_router_module, agent as agent_router_module,
)
from .routers.vehicles_drivers import drivers_router, vehicles_router
from .services.geocoding import search_address_autocomplete
from .services.api_usage import log_api_usage

# -----------------------------------------------------------------------
# App
# -----------------------------------------------------------------------
app = FastAPI(
    title="GiroFacile SaaS",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)

# Protezione centralizzata contro tentativi ripetuti sui login.
app.middleware("http")(login_rate_limit_middleware)


@app.middleware("http")
async def system_error_monitor(request: Request, call_next):
    """Registra gli errori tecnici veri e avvisa il Super Admin.

    Non intercetta errori ordinari come password errata o 404/401, perché FastAPI
    li gestisce come risposte HTTP previste.
    """
    try:
        return await call_next(request)
    except Exception as exc:
        from .services.error_monitor import log_exception
        error_id = log_exception(request, exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Errore interno. Il Super Admin è stato avvisato.",
                "error_id": error_id,
            },
        )

static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# -----------------------------------------------------------------------
# Include router
# -----------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(deposits.router)
app.include_router(agents.router)
app.include_router(customers.router)
app.include_router(vehicles_router)
app.include_router(drivers_router)
app.include_router(routes.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(operator.router)
app.include_router(notifications.router)
app.include_router(activity.router)
app.include_router(settings.router)
app.include_router(support.router)
app.include_router(transfer_portal.router)
app.include_router(driver_router_module.router)
app.include_router(agent_router_module.router)


# -----------------------------------------------------------------------
# Endpoint pagine HTML
# -----------------------------------------------------------------------
@app.get("/")
def index(request_headers: dict = None):
    # La landing page pubblica è il punto di ingresso
    return FileResponse(
        static_dir / "landing" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )




@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serve la favicon ufficiale GiroFacile in formato ICO."""
    return FileResponse(
        static_dir / "favicon.ico",
        media_type="image/x-icon",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/login")
def unified_login():
    return FileResponse(
        static_dir / "dashboard" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/dashboard")
def dashboard():
    return FileResponse(
        static_dir / "dashboard" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/mobile")
def mobile():
    return FileResponse(
        static_dir / "mobile" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/reset-password/{token}")
def reset_password_page(token: str):
    return FileResponse(
        static_dir / "dashboard" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/prenota/{slug}")
def transfer_booking_page(slug: str):
    return FileResponse(
        static_dir / "transfer_booking" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/privacy-policy")
def privacy_policy_page():
    return FileResponse(static_dir / "legal" / "privacy-policy.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/cookie-policy")
def cookie_policy_page():
    return FileResponse(static_dir / "legal" / "cookie-policy.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/termini-condizioni")
def terms_page():
    return FileResponse(static_dir / "legal" / "termini-condizioni.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/sicurezza")
def security_page():
    return FileResponse(static_dir / "legal" / "sicurezza.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/dpa-responsabile-trattamento")
def dpa_page():
    return FileResponse(static_dir / "legal" / "dpa-responsabile-trattamento.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/subprocessors")
def subprocessors_page():
    return FileResponse(static_dir / "legal" / "subprocessors.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


# -----------------------------------------------------------------------
# Autocomplete indirizzi
# -----------------------------------------------------------------------
from .core.dependencies import current_user
from .models import User as UserModel


@app.get("/api/address/search")
def address_search(
    q: str, comune: str = "", provincia: str = "",
    db: Session = Depends(get_db),
    _user: UserModel = Depends(current_user),
):
    import time
    started = time.perf_counter()
    try:
        result = search_address_autocomplete(q, comune, provincia)
        log_api_usage(db, user_id=_user.id, service="google_geocoding", action="Autocomplete indirizzi", endpoint="/api/address/search", status="success", message=f"{len(result or [])} risultati", response_ms=int((time.perf_counter()-started)*1000))
        return result
    except Exception as exc:
        log_api_usage(db, user_id=_user.id, service="google_geocoding", action="Autocomplete indirizzi", endpoint="/api/address/search", status="failed", message=str(exc), response_ms=int((time.perf_counter()-started)*1000))
        raise


# -----------------------------------------------------------------------
# Migrazione DB e utente default
# -----------------------------------------------------------------------
def migrate_database():
    """Crea e aggiorna il database in modo compatibile SQLite/PostgreSQL.

    La versione precedente usava alcune istruzioni SQL specifiche di SQLite
    (es. AUTOINCREMENT e DATETIME nei raw CREATE TABLE). Questa funzione usa
    SQLAlchemy per creare le tabelle e compila i tipi in base al database in
    uso, così GiroFacile può partire sia con SQLite locale sia con PostgreSQL
    in produzione.
    """
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    dialect = engine.dialect
    preparer = dialect.identifier_preparer

    def table_columns(table_name: str) -> set[str]:
        # Usa un Inspector fresco: SQLAlchemy può mettere in cache la struttura
        # letta all'avvio e, dopo un ALTER TABLE, continuare a vedere lo schema
        # precedente. Questo causava /api/vehicles -> 500 sui DB locali aggiornati
        # da versioni più vecchie.
        fresh_insp = inspect(engine)
        if not fresh_insp.has_table(table_name):
            return set()
        return {c["name"] for c in fresh_insp.get_columns(table_name)}

    def q(name: str) -> str:
        return preparer.quote(name)

    def add_column(table_name: str, column_name: str, type_sql: str, default_sql: str | None = None):
        cols = table_columns(table_name)
        if column_name in cols:
            return
        sql = f"ALTER TABLE {q(table_name)} ADD COLUMN {q(column_name)} {type_sql}"
        if default_sql is not None:
            sql += f" DEFAULT {default_sql}"
        with engine.begin() as conn:
            conn.execute(text(sql))

    def sql_type(sqlalchemy_type) -> str:
        return sqlalchemy_type.compile(dialect=dialect)

    from sqlalchemy import Boolean, DateTime, Date, Time, Float, Integer, String, Text

    # Colonne legacy comuni
    for table in ["customers", "deposits", "vehicles", "route_plans", "drivers", "agents"]:
        if insp.has_table(table):
            add_column(table, "user_id", sql_type(Integer()))

    if inspect(engine).has_table("vehicles"):
        # Riparazione completa dello schema Vehicle. Non affidiamoci al fatto che
        # il database provenga da una versione specifica: ogni colonna usata dal
        # modello ORM viene verificata prima che /api/vehicles venga interrogato.
        add_column("vehicles", "is_active", sql_type(Boolean()), "1" if dialect.name == "sqlite" else "true")
        add_column("vehicles", "deleted_at", sql_type(DateTime()))
        add_column("vehicles", "nome", sql_type(String(150)), "''")
        add_column("vehicles", "targa", sql_type(String(50)))
        add_column("vehicles", "consumo_l_100km", sql_type(Float()), "8.5")
        add_column("vehicles", "capacita_kg", sql_type(Float()), "1000")
        add_column("vehicles", "capacita_colli", sql_type(Integer()), "100")
        add_column("vehicles", "ha_sponda", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("vehicles", "accesso_ztl", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("vehicles", "note", sql_type(Text()))
        add_column("vehicles", "photo_url", sql_type(Text()))
        add_column("vehicles", "alimentazione", sql_type(String(40)), "'gasolio'")
        add_column("vehicles", "consumo_primario_100km", sql_type(Float()), "8.5")
        add_column("vehicles", "consumo_kwh_100km", sql_type(Float()), "0")
        add_column("vehicles", "marca", sql_type(String(100)))
        add_column("vehicles", "modello", sql_type(String(160)))
        add_column("vehicles", "anno_immatricolazione", sql_type(Integer()))
        add_column("vehicles", "cilindrata_cc", sql_type(Integer()))
        add_column("vehicles", "potenza_kw", sql_type(Float()))
        add_column("vehicles", "classe_euro", sql_type(String(60)))
        add_column("vehicles", "carrozzeria", sql_type(String(100)))
        add_column("vehicles", "lookup_provider", sql_type(String(60)))
        add_column("vehicles", "lookup_at", sql_type(DateTime()))
        with engine.begin() as conn:
            conn.execute(text("UPDATE vehicles SET consumo_primario_100km = consumo_l_100km WHERE consumo_primario_100km IS NULL OR consumo_primario_100km = 0"))

    if insp.has_table("route_plans"):
        add_column("route_plans", "driver_id", sql_type(Integer()))
        add_column("route_plans", "energy_price_mode", sql_type(String(20)), "'manual'")
        add_column("route_plans", "energy_type", sql_type(String(40)))
        add_column("route_plans", "energy_unit", sql_type(String(20)))
        add_column("route_plans", "energy_price_primary", sql_type(Float()), "0")
        add_column("route_plans", "energy_price_electric", sql_type(Float()), "0")
        add_column("route_plans", "energy_consumption_primary", sql_type(Float()), "0")
        add_column("route_plans", "energy_consumption_electric", sql_type(Float()), "0")
        add_column("route_plans", "energy_quantity_primary", sql_type(Float()), "0")
        add_column("route_plans", "energy_quantity_electric", sql_type(Float()), "0")
        add_column("route_plans", "status", sql_type(String(30)), "'programmato'")
        add_column("route_plans", "started_at", sql_type(DateTime()))
        add_column("route_plans", "completed_at", sql_type(DateTime()))
        add_column("route_plans", "cancelled_at", sql_type(DateTime()))

    if insp.has_table("transfer_booking_requests"):
        add_column("transfer_booking_requests", "driver_id", sql_type(Integer()))
        add_column("transfer_booking_requests", "vehicle_id", sql_type(Integer()))
        add_column("transfer_booking_requests", "assignment_status", sql_type(String(30)), "'unassigned'")
        add_column("transfer_booking_requests", "assigned_at", sql_type(DateTime()))
        add_column("transfer_booking_requests", "accepted_at", sql_type(DateTime()))
        add_column("transfer_booking_requests", "rejected_at", sql_type(DateTime()))
        add_column("transfer_booking_requests", "estimated_minutes", sql_type(Integer()))
        add_column("transfer_booking_requests", "estimated_km", sql_type(Float()))
        add_column("transfer_booking_requests", "admin_note", sql_type(Text()))
        add_column("transfer_booking_requests", "booking_source", sql_type(String(120)))

    if insp.has_table("drivers"):
        add_column("drivers", "is_admin_driver", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")

    if insp.has_table("support_tickets"):
        add_column("support_tickets", "system_error_id", sql_type(Integer()))
        add_column("support_tickets", "notify_on_resolution", sql_type(Boolean()), "1" if dialect.name == "sqlite" else "true")
        add_column("support_tickets", "resolved_email_sent", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")

    if insp.has_table("customers"):
        add_column("customers", "agent_id", sql_type(Integer()))
        add_column("customers", "tempo_scarico_rilevazioni", sql_type(Integer()), "0")
        add_column("customers", "lat", sql_type(Float()))
        add_column("customers", "lon", sql_type(Float()))
        add_column("customers", "indirizzo_geocodificato", sql_type(String(500)))
        add_column("customers", "stato_geocodifica", sql_type(String(30)), "'da_verificare'")
        add_column("customers", "affidabilita_geocodifica", sql_type(Float()))
        add_column("customers", "fonte_geocodifica", sql_type(String(50)))
        add_column("customers", "google_place_id", sql_type(String(200)))
        add_column("customers", "geocodificato_il", sql_type(DateTime()))

    if insp.has_table("deposits"):
        add_column("deposits", "lat", sql_type(Float()))
        add_column("deposits", "lon", sql_type(Float()))

    if insp.has_table("distance_cache"):
        add_column("distance_cache", "user_id", sql_type(Integer()))
        add_column("distance_cache", "expires_at", sql_type(DateTime()))
        # Le installazioni precedenti potrebbero avere tratte senza azienda.
        # Le lasciamo nel DB ma la nuova logica usa solo cache con user_id,
        # così non si mischiano dati tra aziende. La pulizia automatica le rimuoverà.

    for table_name in ["drivers", "vehicles", "agents"]:
        if insp.has_table(table_name):
            add_column(table_name, "photo_url", sql_type(Text()))

    # v38 — soft delete: archiviamo entità operative senza rompere storico giri/report.
    for table_name in ["customers", "deposits", "vehicles", "drivers", "agents"]:
        if insp.has_table(table_name):
            add_column(table_name, "is_active", sql_type(Boolean()), "1" if dialect.name == "sqlite" else "true")
            add_column(table_name, "deleted_at", sql_type(DateTime()))

    if insp.has_table("chat_messages"):
        add_column("chat_messages", "driver_id", sql_type(Integer()))

    if insp.has_table("users"):
        add_column("users", "company_logo_url", sql_type(Text()))
        add_column("users", "company_email", sql_type(String(200)))
        add_column("users", "company_phone", sql_type(String(100)))
        add_column("users", "company_vat", sql_type(String(80)))
        add_column("users", "company_fiscal_code", sql_type(String(80)))
        add_column("users", "company_pec", sql_type(String(200)))
        add_column("users", "company_sdi", sql_type(String(20)))
        add_column("users", "company_address", sql_type(String(500)))
        add_column("users", "company_city", sql_type(String(150)))
        add_column("users", "company_zip", sql_type(String(20)))
        add_column("users", "company_country", sql_type(String(80)), "'Italia'")
        add_column("users", "company_legal_address", sql_type(String(500)))
        add_column("users", "company_billing_address", sql_type(String(500)))
        add_column("users", "company_sector", sql_type(String(120)))
        add_column("users", "company_activity_type", sql_type(String(180)))
        add_column("users", "company_size", sql_type(String(80)))
        add_column("users", "daily_deliveries", sql_type(String(80)))
        add_column("users", "has_time_windows", sql_type(Boolean()), "1" if dialect.name == "sqlite" else "true")
        add_column("users", "needs_signature", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("users", "needs_photo_proof", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("users", "has_refrigerated_goods", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("users", "has_ztl", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("users", "needs_tail_lift", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("users", "universal_features_initialized", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        # V89.2: inizializzazione UNA SOLA VOLTA delle preferenze universali per gli account esistenti.
        # Dopo questa migrazione le scelte dell’utente non vengono più sovrascritte ai riavvii.
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET has_time_windows = :tw, needs_photo_proof = :photo, has_refrigerated_goods = :cold, has_ztl = :ztl, needs_tail_lift = :tail, universal_features_initialized = :done WHERE universal_features_initialized IS NULL OR universal_features_initialized = :pending"), {"tw": True, "photo": False, "cold": False, "ztl": False, "tail": False, "done": True, "pending": False})
        add_column("users", "onboarding_completed", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("users", "onboarding_completed_at", sql_type(DateTime()))
        add_column("users", "onboarding_dismissed", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        add_column("users", "plan", sql_type(String(30)), "'starter'")
        add_column("users", "plan_status", sql_type(String(30)), "'trial'")
        add_column("users", "trial_ends_at", sql_type(DateTime()))
        add_column("users", "plan_expires_at", sql_type(DateTime()))
        add_column("users", "stripe_customer_id", sql_type(String(200)))
        add_column("users", "stripe_subscription_id", sql_type(String(200)))
        add_column("users", "delivery_signature_enabled", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
        if "agents_enabled" not in table_columns("users"):
            add_column("users", "agents_enabled", sql_type(Boolean()), "0" if dialect.name == "sqlite" else "false")
            with engine.begin() as conn:
                conn.execute(text("UPDATE users SET agents_enabled = true WHERE EXISTS (SELECT 1 FROM agents WHERE agents.user_id = users.id AND agents.deleted_at IS NULL)"))

    if insp.has_table("delivery_statuses"):
        add_column("delivery_statuses", "signature_data", sql_type(Text()))
        add_column("delivery_statuses", "signed_by_name", sql_type(String(200)))
        add_column("delivery_statuses", "signed_at", sql_type(DateTime()))
        add_column("delivery_statuses", "signature_note", sql_type(Text()))

    # v37 — tipi reali Date/Time su PostgreSQL.
    # Su SQLite manteniamo compatibilità locale perché SQLite non applica
    # rigidamente i tipi; l'applicazione normalizza comunque input/output.
    if dialect.name == "postgresql":
        def alter_type(table: str, column: str, type_sql: str, using_expr: str):
            if column not in table_columns(table):
                return
            try:
                with engine.begin() as conn:
                    conn.execute(text(f'ALTER TABLE {q(table)} ALTER COLUMN {q(column)} TYPE {type_sql} USING {using_expr}'))
            except Exception as exc:
                print(f"[DB] Avviso: impossibile convertire {table}.{column} in {type_sql}: {exc}")

        alter_type("route_plans", "data_giro", "DATE", "NULLIF(data_giro::text, '')::date")
        for col in ["orario_partenza", "orario_rientro_stimato"]:
            alter_type("route_plans", col, "TIME", f"NULLIF({col}::text, '')::time")
        for col in ["scarico_mattina_da", "scarico_mattina_a", "scarico_pomeriggio_da", "scarico_pomeriggio_a"]:
            alter_type("customers", col, "TIME", f"NULLIF({col}::text, '')::time")
            alter_type("deliveries", col, "TIME", f"NULLIF({col}::text, '')::time")
        for col in ["arrivo_stimato", "partenza_stimata"]:
            alter_type("deliveries", col, "TIME", f"NULLIF({col}::text, '')::time")
        for col in ["scadenza_patente", "scadenza_cqc"]:
            alter_type("drivers", col, "DATE", f"NULLIF({col}::text, '')::date")

def ensure_default_user():
    with Session(engine) as db:
        user = db.query(User).filter(User.username == APP_USER).first()
        if not user:
            user = User(
                username=APP_USER,
                email=None,
                company_name="Account principale",
                password_hash=hash_password(APP_PASSWORD),
                plan="pro",
                plan_status="active",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # L'admin ha sempre piano Pro attivo
            if user.plan != "pro" or user.plan_status != "active":
                user.plan = "pro"
                user.plan_status = "active"
                db.commit()

        # Migrazione sicurezza multi-azienda:
        # i vecchi database potevano avere record senza user_id.
        # Prima di rendere lo schema più rigido assegniamo quei record
        # all'account principale, così nessuna tabella tenant resta senza proprietario.
        for model in [Agent, Customer, Deposit, Vehicle, Driver, RoutePlan]:
            db.query(model).filter(model.user_id.is_(None)).update({"user_id": user.id})

        # La cache vecchia senza azienda non va riusata: potrebbe contenere tratte
        # calcolate prima della separazione multi-tenant. La eliminiamo.
        if inspect(engine).has_table("distance_cache"):
            db.query(DistanceCache).filter(DistanceCache.user_id.is_(None)).delete(synchronize_session=False)

        db.commit()


def harden_tenant_schema():
    """Rende più robusto lo schema SaaS multi-azienda.

    SQLite non permette facilmente ALTER COLUMN ... SET NOT NULL senza
    ricostruire le tabelle; in locale quindi applichiamo protezioni runtime
    e indici. Su PostgreSQL, invece, impostiamo NOT NULL a livello DB.
    """
    insp = inspect(engine)
    dialect = engine.dialect
    preparer = dialect.identifier_preparer

    def q(name: str) -> str:
        return preparer.quote(name)

    tenant_tables = [
        "customers",
        "deposits",
        "vehicles",
        "drivers",
        "agents",
        "route_plans",
        "distance_cache",
        "notifications",
        "activity_events",
    ]

    with engine.begin() as conn:
        # Indici aziendali: rendono più veloci le query sempre filtrate per azienda.
        for table in tenant_tables:
            if not insp.has_table(table):
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if "user_id" not in cols:
                continue
            idx_name = f"ix_{table}_company_id"
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {q(idx_name)} ON {q(table)} ({q('user_id')})"))
            if "deleted_at" in cols:
                idx_del = f"ix_{table}_deleted_at"
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {q(idx_del)} ON {q(table)} ({q('deleted_at')})"))

        # Indice composito reale usato dalla cache tratte: azienda + origine + destinazione.
        if insp.has_table("distance_cache"):
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {q('ix_distance_cache_company_origin_dest')} "
                f"ON {q('distance_cache')} ({q('user_id')}, {q('origin_key')}, {q('dest_key')})"
            ))

        def create_unique_index_if_clean(table: str, column: str, index_name: str):
            """Crea un vincolo unico per azienda solo se i dati esistenti sono puliti.

            La regola è tenant-safe: lo stesso codice/targa/email può esistere
            in aziende diverse, ma non può essere duplicato dentro la stessa
            azienda. I valori NULL o stringa vuota vengono ignorati. Se in un
            vecchio database esistono duplicati, non blocchiamo l'avvio: stampiamo
            un avviso e lasciamo allo script di controllo la bonifica manuale.
            """
            if not insp.has_table(table):
                return
            cols = {c["name"] for c in insp.get_columns(table)}
            if "user_id" not in cols or column not in cols:
                return
            has_deleted_at = "deleted_at" in cols
            active_filter = f" AND {q('deleted_at')} IS NULL" if has_deleted_at else ""
            dup_sql = text(
                f"SELECT {q('user_id')}, {q(column)}, COUNT(*) AS c "
                f"FROM {q(table)} "
                f"WHERE {q('user_id')} IS NOT NULL AND {q(column)} IS NOT NULL AND TRIM({q(column)}) <> ''"
                f"{active_filter} "
                f"GROUP BY {q('user_id')}, {q(column)} HAVING COUNT(*) > 1 LIMIT 5"
            )
            duplicates = conn.execute(dup_sql).fetchall()
            if duplicates:
                print(f"[DB] Vincolo unico non creato su {table}.{column}: duplicati attivi esistenti={duplicates}")
                return

            # Le vecchie versioni potevano creare indici unici senza soft delete.
            # Li rimuoviamo se esistono e ricreiamo indici parziali solo sui record attivi.
            old_names = {
                "uq_customers_company_code_idx",
                "uq_vehicles_company_targa_idx",
                "uq_drivers_company_email_idx",
                "uq_agents_company_email_idx",
                "uq_agents_company_code_idx",
            }
            if index_name in old_names:
                try:
                    conn.execute(text(f"DROP INDEX IF EXISTS {q(index_name)}"))
                except Exception as exc:
                    print(f"[DB] Avviso: indice {index_name} non eliminato: {exc}")
                if dialect.name.startswith("postgres"):
                    constraint_name = index_name.replace("_idx", "")
                    try:
                        conn.execute(text(f"ALTER TABLE {q(table)} DROP CONSTRAINT IF EXISTS {q(constraint_name)}"))
                    except Exception as exc:
                        print(f"[DB] Avviso: constraint {constraint_name} non eliminato: {exc}")

            where_clause = f"WHERE {q(column)} IS NOT NULL AND TRIM({q(column)}) <> ''"
            if has_deleted_at:
                where_clause += f" AND {q('deleted_at')} IS NULL"
            conn.execute(text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {q(index_name)} "
                f"ON {q(table)} ({q('user_id')}, {q(column)}) {where_clause}"
            ))

        # Vincoli univoci per azienda: evitano duplicati dentro lo stesso tenant,
        # ma permettono a due aziende diverse di usare lo stesso codice/targa/email.
        create_unique_index_if_clean("customers", "codice_cliente", "uq_customers_company_code_idx")
        create_unique_index_if_clean("vehicles", "targa", "uq_vehicles_company_targa_idx")
        create_unique_index_if_clean("drivers", "email", "uq_drivers_company_email_idx")
        create_unique_index_if_clean("agents", "email", "uq_agents_company_email_idx")
        create_unique_index_if_clean("agents", "codice_agente", "uq_agents_company_code_idx")

        # Bonifica sicurezza multi-tenant dei riferimenti storici creati da
        # versioni precedenti: un giro non deve mai mantenere FK verso risorse
        # appartenenti a un'altra azienda. Usiamo SET NULL per preservare lo
        # storico testuale del giro senza esporre la relazione cross-tenant.
        if insp.has_table("deliveries") and insp.has_table("route_plans") and insp.has_table("customers"):
            repaired = conn.execute(text(
                f"UPDATE {q('deliveries')} SET {q('customer_id')} = NULL "
                f"WHERE {q('customer_id')} IS NOT NULL AND EXISTS ("
                f"SELECT 1 FROM {q('route_plans')} rp JOIN {q('customers')} c "
                f"ON c.{q('id')} = {q('deliveries')}.{q('customer_id')} "
                f"WHERE rp.{q('id')} = {q('deliveries')}.{q('route_plan_id')} "
                f"AND rp.{q('user_id')} <> c.{q('user_id')})"
            ))
            if getattr(repaired, "rowcount", 0):
                print(f"[SECURITY] Rimossi {repaired.rowcount} riferimenti delivery->customer cross-tenant")

        for fk_column, target_table in (("deposit_id", "deposits"), ("vehicle_id", "vehicles"), ("driver_id", "drivers")):
            if not (insp.has_table("route_plans") and insp.has_table(target_table)):
                continue
            repaired = conn.execute(text(
                f"UPDATE {q('route_plans')} SET {q(fk_column)} = NULL "
                f"WHERE {q(fk_column)} IS NOT NULL AND EXISTS ("
                f"SELECT 1 FROM {q(target_table)} t "
                f"WHERE t.{q('id')} = {q('route_plans')}.{q(fk_column)} "
                f"AND t.{q('user_id')} <> {q('route_plans')}.{q('user_id')})"
            ))
            if getattr(repaired, "rowcount", 0):
                print(f"[SECURITY] Rimossi {repaired.rowcount} riferimenti route_plans.{fk_column} cross-tenant")

        # Su PostgreSQL possiamo rendere il vincolo obbligatorio a livello database.
        if dialect.name.startswith("postgres"):
            for table in tenant_tables:
                if not insp.has_table(table):
                    continue
                cols = {c["name"] for c in insp.get_columns(table)}
                if "user_id" in cols:
                    conn.execute(text(f"ALTER TABLE {q(table)} ALTER COLUMN {q('user_id')} SET NOT NULL"))


migrate_database()
ensure_default_user()
harden_tenant_schema()


@app.get("/admin/login")
def admin_login_page():
    return FileResponse(
        static_dir / "admin" / "login.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/admin")
def admin_panel():
    return FileResponse(
        static_dir / "admin" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/giro/{token}")
def operator_portal(token: str):
    return FileResponse(
        static_dir / "operator" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/driver")
@app.get("/driver/")
def driver_portal():
    return FileResponse(
        static_dir / "driver" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/driver/setup/{token}")
def driver_setup(token: str):
    return FileResponse(
        static_dir / "driver" / "setup.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/agent")
@app.get("/agent/")
def agent_portal():
    return FileResponse(
        static_dir / "agent" / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/agent/setup/{token}")
def agent_setup(token: str):
    return FileResponse(
        static_dir / "agent" / "setup.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
