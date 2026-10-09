"""Explicit, locked, versioned schema upgrades: python -m app.migrations."""
from datetime import datetime
from sqlalchemy import inspect, text

LATEST = '20261009_01'
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
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_01', 'now': datetime.utcnow()})
            if '20261004_02' not in applied:
                with engine.begin() as conn:
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_delivery_status_event_idx ON delivery_statuses (delivery_id, route_plan_id)'))
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_02', 'now': datetime.utcnow()})
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
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_03', 'now': datetime.utcnow()})
            if '20261004_04' not in applied:
                from .models import DeliveryTrackingLink
                with engine.begin() as conn:
                    DeliveryTrackingLink.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261004_04', 'now': datetime.utcnow()})
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
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': '20261006_01', 'now': datetime.utcnow()})
            if LATEST not in applied:
                from .models import CompanyCollaborator
                with engine.begin() as conn:
                    CompanyCollaborator.__table__.create(conn, checkfirst=True)
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': LATEST, 'now': datetime.utcnow()})
        finally:
            if postgres:
                lock.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': LOCK_ID})
                lock.commit()


if __name__ == '__main__':
    from .database import engine
    run_migrations(engine)
    print('Schema aggiornato:', LATEST)
