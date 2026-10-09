"""POD upgrades on PostgreSQL, only in the disposable audit fixture schema."""
from sqlalchemy import inspect, text
from test_audit_postgres import pg


def test_pod_migration_preserves_legacy_and_is_idempotent(pg):
    from app.migrations import run_migrations, LATEST
    with pg.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)'))
        conn.execute(text("INSERT INTO users VALUES (1,'legacy-owner')"))
        conn.execute(text('CREATE TABLE deliveries (id INTEGER PRIMARY KEY)'))
        conn.execute(text('CREATE TABLE delivery_statuses (id INTEGER PRIMARY KEY, delivery_id INTEGER, route_plan_id INTEGER, signature_data TEXT, signature_note TEXT)'))
        conn.execute(text("INSERT INTO delivery_statuses VALUES (1,1,1,'legacy-signature','nota')"))
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in ('20261004_01','20261004_02'):
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v':version})
    run_migrations(pg); run_migrations(pg)
    columns = {c['name'] for c in inspect(pg).get_columns('delivery_statuses')}
    assert {'signature_object_key','delivery_photo_object_key','pod_object_key','pod_created_at'} <= columns
    assert any(fk['referred_table'] == 'users' and fk['constrained_columns'] == ['user_id']
               for fk in inspect(pg).get_foreign_keys('company_collaborators'))
    with pg.connect() as conn:
        assert conn.execute(text('SELECT username FROM users')).scalar() == 'legacy-owner'
        assert conn.execute(text('SELECT signature_data FROM delivery_statuses')).scalar() == 'legacy-signature'
        assert conn.execute(text('SELECT COUNT(*) FROM schema_migrations WHERE version=:v'), {'v':LATEST}).scalar() == 1
