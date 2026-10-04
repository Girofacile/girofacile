"""Explicit, locked, versioned schema upgrades: python -m app.migrations."""
from datetime import datetime
from sqlalchemy import inspect, text

LATEST = '20261004_03'
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
            if LATEST not in applied:
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
                    conn.execute(text('INSERT INTO schema_migrations (version, applied_at) VALUES (:v, :now)'), {'v': LATEST, 'now': datetime.utcnow()})
        finally:
            if postgres:
                lock.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': LOCK_ID})
                lock.commit()


if __name__ == '__main__':
    from .database import engine
    run_migrations(engine)
    print('Schema aggiornato:', LATEST)
