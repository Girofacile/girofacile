"""Explicit, locked, versioned schema upgrades: python -m app.migrations."""
from datetime import datetime
from .core.clock import utc_now
from sqlalchemy import inspect, text

LATEST = '20261027_02'
LOCK_ID = 7640152404


def require_current_schema(engine):
    if not inspect(engine).has_table('schema_migrations'):
        raise RuntimeError('Database da aggiornare: eseguire python -m app.migrations prima di avviare il server')
    with engine.connect() as conn:
        if not conn.execute(text('SELECT version FROM schema_migrations WHERE version=:v'), {'v': LATEST}).first():
            raise RuntimeError('Migrazioni pendenti: eseguire python -m app.migrations')


def _preflight(engine):
    inspector = inspect(engine)
    with engine.connect() as conn:
        if inspector.has_table('delivery_statuses'):
            duplicate = conn.execute(text('SELECT delivery_id FROM delivery_statuses GROUP BY delivery_id, route_plan_id HAVING COUNT(*) > 1 LIMIT 1')).first()
            if duplicate:
                raise RuntimeError('Stati consegna duplicati: riconciliare le evidenze prima della migrazione; nessun dato è stato cancellato')


def run_migrations(engine):
    # Register every referenced table even when older migrations are already applied.
    # A fresh CLI process otherwise loads order_models without users/customers/routes,
    # leaving inferred foreign-key column types unresolved (NullType).
    from . import models  # noqa: F401

    # A dedicated session lock serializes complete upgrades across deployments/workers.
    with engine.connect() as lock:
        postgres = engine.dialect.name == 'postgresql'
        if postgres:
            lock.execute(text('SELECT pg_advisory_lock(:key)'), {'key': LOCK_ID})
            lock.commit()
        try:
            _preflight(engine)
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)'))
                applied = set(conn.execute(text('SELECT version FROM schema_migrations')).scalars())
            if '20261004_01' not in applied:
                from . import legacy_schema
                legacy_schema.engine = engine
                legacy_schema.migrate_database()
                legacy_schema.ensure_default_user()
                legacy_schema.harden_tenant_schema()
                with engine.begin() as conn:
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_01', 'now': utc_now()})
            if '20261004_02' not in applied:
                with engine.begin() as conn:
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_status_event_idx ON delivery_statuses (delivery_id, route_plan_id)'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_02', 'now': utc_now()})
            if '20261004_03' not in applied:
                from .models import DeliveryStatus
                with engine.begin() as conn:
                    table = DeliveryStatus.__table__
                    columns = ('signature_object_key', 'signature_size', 'signature_sha256', 'signature_content_type',
                               'delivery_photo_object_key', 'delivery_photo_size', 'delivery_photo_sha256',
                               'delivery_photo_content_type', 'pod_object_key', 'pod_size', 'pod_sha256', 'pod_created_at')
                    existing = {c['name'] for c in inspect(conn).get_columns(table.name)}
                    for name in columns:
                        if name not in existing:
                            sql_type = table.c[name].type.compile(dialect=engine.dialect)
                            conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {name} {sql_type}'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_03', 'now': utc_now()})
            if '20261004_04' not in applied:
                from .models import DeliveryTrackingLink
                with engine.begin() as conn:
                    DeliveryTrackingLink.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_04', 'now': utc_now()})
            if '20261005_01' not in applied and '20261006_01' not in applied:
                # Fresh installs can apply this structural step as part of the
                # current schema without recording an otherwise redundant
                # intermediate version. Existing upgraded databases keep their
                # historical 20261005_01 marker untouched.
                from .models import RoutePosition
                with engine.begin() as conn:
                    inspector = inspect(conn)
                    required_tables = ('route_plans', 'drivers', 'deliveries')
                    if all(inspector.has_table(name) for name in required_tables):
                        RoutePosition.__table__.create(conn, checkfirst=True)
            if '20261006_01' not in applied:
                with engine.begin() as conn:
                    inspector = inspect(conn)
                    if inspector.has_table('users'):
                        user_columns = {col['name'] for col in inspector.get_columns('users')}
                        if 'company_sector' in user_columns:
                            conn.execute(text("UPDATE users SET company_sector='other' WHERE company_sector IN ('transfer', 'transfer_service')"))
                    for table_name in (
                        'transfer_booking_events',
                        'transfer_booking_requests',
                        'transfer_operational_settings',
                        'transfer_booking_portal_settings',
                    ):
                        conn.execute(text(f'DROP TABLE IF EXISTS {table_name}'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261006_01', 'now': utc_now()})
            if '20261009_01' not in applied:
                from .models import CompanyCollaborator
                with engine.begin() as conn:
                    CompanyCollaborator.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261009_01', 'now': utc_now()})
            if '20261009_02' not in applied:
                from .models import CollaboratorInvitation
                with engine.begin() as conn:
                    existing = {col['name'] for col in inspect(conn).get_columns('company_collaborators')}
                    if 'password_setup_required' not in existing:
                        # Existing password-based accounts remain initialized.
                        conn.execute(text('ALTER TABLE company_collaborators ADD COLUMN password_setup_required BOOLEAN NOT NULL DEFAULT FALSE'))
                    CollaboratorInvitation.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261009_02', 'now': utc_now()})
            if '20261010_01' not in applied:
                from .order_models import ORDER_TABLES
                with engine.begin() as conn:
                    for table in ORDER_TABLES:
                        table.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261010_01', 'now': utc_now()})
            if '20261010_02' not in applied:
                from .order_models import OrderPlanningSelection
                with engine.begin() as conn:
                    OrderPlanningSelection.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261010_02', 'now': utc_now()})
            if '20261011_01' not in applied:
                with engine.begin() as conn:
                    if 'customer_resolution' not in {c['name'] for c in inspect(conn).get_columns('orders')}:
                        conn.execute(text("ALTER TABLE orders ADD COLUMN customer_resolution VARCHAR(30) NOT NULL DEFAULT 'pending'"))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261011_01', 'now': utc_now()})
            if '20261011_02' not in applied:
                with engine.begin() as conn:
                    additions = {'order_sources': {'version': "INTEGER NOT NULL DEFAULT 1"},
                                 'orders': {'ingested_payload': 'JSON'},
                                 'order_import_runs': {'idempotency_key': 'VARCHAR(160)', 'payload_hash': 'VARCHAR(64)', 'payload': 'JSON', 'expires_at': 'TIMESTAMP', 'source_version': 'INTEGER'}}
                    for table, columns in additions.items():
                        existing = {c['name'] for c in inspect(conn).get_columns(table)}
                        for name, ddl in columns.items():
                            if name not in existing: conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_order_import_request ON order_import_runs (source_id, idempotency_key)'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261011_02', 'now': utc_now()})
            if '20261013_01' not in applied:
                from .fleet_models import FleetPlan
                with engine.begin() as conn:
                    FleetPlan.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261013_01', 'now': utc_now()})
            if '20261013_02' not in applied:
                with engine.begin() as conn:
                    tables=set(inspect(conn).get_table_names())
                    for table,columns in {'drivers':['work_schedule'],'route_plans':['driver_schedule','driver_breaks']}.items():
                        # Tabella assente (schema parziale o legacy): nessuna colonna da aggiungere.
                        if table not in tables: continue
                        existing={c['name'] for c in inspect(conn).get_columns(table)}
                        for column in columns:
                            if column not in existing: conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} JSON'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261013_02', 'now': utc_now()})
            if '20261020_01' not in applied:
                with engine.begin() as conn:
                    tables = set(inspect(conn).get_table_names())
                    for table in ('customers', 'deliveries'):
                        if table not in tables:
                            continue  # Database legacy parziale, come nelle migrazioni precedenti.
                        columns = {c['name'] for c in inspect(conn).get_columns(table)}
                        if 'pedestrian_area' not in columns:
                            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN pedestrian_area BOOLEAN NOT NULL DEFAULT FALSE'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261020_01', 'now': utc_now()})
            if '20261020_02' not in applied:
                # Targhe salvate prima della normalizzazione ("gr 552 gg"): stesso formato
                # usato oggi al salvataggio. Se due mezzi dell'azienda collidono, restano invariati.
                with engine.begin() as conn:
                    if 'vehicles' in set(inspect(conn).get_table_names()):
                        rows = conn.execute(text('SELECT id, user_id, targa FROM vehicles WHERE targa IS NOT NULL')).all()
                        taken = {(r.user_id, r.targa) for r in rows}
                        for r in rows:
                            plate = ''.join(ch for ch in r.targa.upper() if ch.isalnum()) or None
                            if plate == r.targa or (r.user_id, plate) in taken:
                                continue
                            conn.execute(text('UPDATE vehicles SET targa=:t WHERE id=:id'), {'t': plate, 'id': r.id})
                            taken.discard((r.user_id, r.targa))
                            taken.add((r.user_id, plate))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261020_02', 'now': utc_now()})
            if '20261023_01' not in applied:
                from collections import Counter
                from datetime import timezone
                from zoneinfo import ZoneInfo
                from .order_models import Order, OrderMonthlyUsage
                with engine.begin() as conn:
                    OrderMonthlyUsage.__table__.create(conn, checkfirst=True)
                    rome = ZoneInfo('Europe/Rome')
                    counts = Counter()
                    rows = (conn.execute(Order.__table__.select().with_only_columns(Order.user_id, Order.received_at))
                            if inspect(conn).has_table('orders') else ())
                    for uid, received in rows:
                        instant = received.replace(tzinfo=timezone.utc) if received.tzinfo is None else received
                        counts[uid, instant.astimezone(rome).strftime('%Y-%m')] += 1
                    for (uid, month), used in counts.items():
                        existing = conn.execute(OrderMonthlyUsage.__table__.select().where(
                            OrderMonthlyUsage.user_id == uid, OrderMonthlyUsage.month == month)).first()
                        if existing is None:
                            conn.execute(OrderMonthlyUsage.__table__.insert().values(user_id=uid, month=month, used=used))
                        elif existing.used < used:
                            conn.execute(OrderMonthlyUsage.__table__.update().where(
                                OrderMonthlyUsage.user_id == uid, OrderMonthlyUsage.month == month).values(used=used))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261023_01', 'now': utc_now()})
            if '20261027_01' not in applied:
                # Giri in bozza: pianificazioni lasciate prima della programmazione.
                from .order_models import PlanningDraft
                with engine.begin() as conn:
                    PlanningDraft.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261027_01', 'now': utc_now()})
            if '20261027_02' not in applied:
                # Giri in bozza: fase in cui è stato lasciato il giro e anteprima della suddivisione.
                with engine.begin() as conn:
                    existing = {c['name'] for c in inspect(conn).get_columns('planning_drafts')}
                    if 'stage' not in existing:
                        conn.execute(text("ALTER TABLE planning_drafts ADD COLUMN stage VARCHAR(20) NOT NULL DEFAULT 'configurazione'"))
                    if 'fleet_plan_id' not in existing:
                        conn.execute(text('ALTER TABLE planning_drafts ADD COLUMN fleet_plan_id INTEGER'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261027_02', 'now': utc_now()})
        finally:
            if postgres:
                lock.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': LOCK_ID})
                lock.commit()


if __name__ == '__main__':
    from .database import engine
    run_migrations(engine)
    print('Schema aggiornato:', LATEST)
