"""One-time compatibility migration for databases preceding versioned migrations."""
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from .database import Base, engine
from .models import Agent, Customer, Deposit, Driver, RoutePlan, User, Vehicle, PasswordResetToken, DistanceCache
from .core.config import APP_USER, APP_PASSWORD
from .core.security import hash_password

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

    if insp.has_table("deliveries"):
        add_column("deliveries", "optimizer_details", sql_type(Text()))

    if insp.has_table("api_usage_logs"):
        add_column("api_usage_logs", "route_plan_id", sql_type(Integer()))

    if insp.has_table("route_plans"):
        add_column("route_plans", "started_at_utc", sql_type(DateTime()))
        add_column("route_plans", "completed_at_utc", sql_type(DateTime()))
        add_column("route_plans", "base_routing_provider", sql_type(String(30)))
        add_column("route_plans", "routing_snapshot_json", sql_type(Text()))
        add_column("route_plans", "traffic_provider", sql_type(String(30)))
        add_column("route_plans", "traffic_calculated_at", sql_type(DateTime()))
        add_column("route_plans", "traffic_departure_at", sql_type(DateTime(timezone=True)))
        add_column("route_plans", "traffic_status", sql_type(String(30)))
        add_column("route_plans", "traffic_version", sql_type(Integer()), "0")
        add_column("route_plans", "traffic_result_json", sql_type(Text()))
        add_column("route_plans", "road_geometry_json", sql_type(Text()))
        add_column("route_plans", "toll_provider", sql_type(String(30)))
        add_column("route_plans", "toll_status", sql_type(String(30)))
        add_column("route_plans", "toll_estimated_eur", sql_type(Float()))
        add_column("route_plans", "toll_details_json", sql_type(Text()))

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
        add_column("vehicles", "toll_class", sql_type(String(10)), "'B'")
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
        add_column("deposits", "updated_at", sql_type(DateTime()))
        add_column("deposits", "lat", sql_type(Float()))
        add_column("deposits", "lon", sql_type(Float()))

    if insp.has_table("distance_cache"):
        add_column("distance_cache", "user_id", sql_type(Integer()))
        add_column("distance_cache", "expires_at", sql_type(DateTime()))
    if insp.has_table("distance_cache"):
        # Legacy traffic cache is disposable; saved tours are never touched.
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM distance_cache WHERE origin_key LIKE '%|departure=%' OR dest_key LIKE '%|departure=%'"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_distance_cache_road_pair ON distance_cache(user_id, origin_key, dest_key)"))
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

    if insp.has_table("superadmin_profiles"):
        add_column("superadmin_profiles", "notify_new_payments", sql_type(Boolean()), "1" if dialect.name == "sqlite" else "true")

    if insp.has_table("users"):
        add_column("users", "customer_number", sql_type(Integer()))
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_customer_number ON users (customer_number) WHERE customer_number IS NOT NULL"))
        add_column("users", "customer_number", sql_type(Integer()))
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_customer_number ON users (customer_number) WHERE customer_number IS NOT NULL"))
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
        for column in ("billing_source", "billing_pending_plan", "billing_checkout_plan"):
            add_column("users", column, sql_type(String(30)))
        add_column("users", "billing_change_key", sql_type(String(40)))
        add_column("users", "billing_checkout_id", sql_type(String(200)))
        add_column("users", "billing_checkout_url", sql_type(Text()))
        for column in ("billing_grace_until", "billing_checkout_expires"):
            add_column("users", column, sql_type(DateTime()))
        add_column("users", "billing_cancel_at_period_end", sql_type(Boolean()), "false")
        add_column("users", "billing_suspended", sql_type(Boolean()), "false")
        add_column("billing_invoices", "stripe_invoice_id", sql_type(String(200)))
        add_column("billing_invoices", "is_test", sql_type(Boolean()), "true")
        add_column("billing_payments", "is_test", sql_type(Boolean()), "true")
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_stripe_invoice ON billing_invoices (stripe_invoice_id)"))
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
                raise RuntimeError(f"Conversione schema fallita: {table}.{column}") from exc

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

    from app.services.usage_limits import backfill_started_routes
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        backfill_started_routes(db)


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


