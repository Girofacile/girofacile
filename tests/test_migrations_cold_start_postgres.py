"""Exercise the deployment CLI without pytest's already-imported model registry."""
import os
import subprocess
import sys

from sqlalchemy import inspect, text
from test_audit_postgres import pg


def test_existing_database_before_orders_upgrades_in_fresh_process(pg):
    from app.migrations import run_migrations, require_current_schema
    from app.order_models import ORDER_TABLES, OrderPlanningSelection
    run_migrations(pg)
    with pg.begin() as conn:
        schema = conn.execute(text('SELECT current_schema()')).scalar_one()
        conn.execute(text("UPDATE users SET company_name='Preserved during CLI upgrade'"))
        existing_users = conn.execute(text('SELECT id, username, company_name FROM users ORDER BY id')).all()
        OrderPlanningSelection.__table__.drop(conn)
        for table in reversed(ORDER_TABLES):
            table.drop(conn)
        conn.execute(text("DELETE FROM schema_migrations WHERE version >= '20261010_01'"))
    url = pg.url.update_query_dict({'options': '-csearch_path=' + schema}).render_as_string(hide_password=False)
    env = dict(os.environ, DATABASE_URL=url, APP_ENV='development')
    # Both first upgrade and repeated startup must work without importing app.models first.
    for _ in range(2):
        result = subprocess.run([sys.executable, '-m', 'app.migrations'], env=env,
                                capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stderr
        assert 'Schema aggiornato:' in result.stdout
    require_current_schema(pg)
    assert {t.name for t in ORDER_TABLES} <= set(inspect(pg).get_table_names())
    with pg.connect() as conn:
        assert conn.execute(text('SELECT id, username, company_name FROM users ORDER BY id')).all() == existing_users
        fk = next(f for f in inspect(conn).get_foreign_keys('order_sources') if f['constrained_columns'] == ['user_id'])
        assert fk['referred_table'] == 'users'
