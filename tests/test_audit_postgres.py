"""Real PostgreSQL concurrency and migration tests in disposable schemas only."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time

import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session


@pytest.fixture
def pg():
    if not os.getenv('TEST_POSTGRES_URL'):
        pytest.skip('TEST_POSTGRES_URL not configured')
    admin = create_engine(os.environ['TEST_POSTGRES_URL'])
    schema = 'audit_' + uuid.uuid4().hex
    with admin.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + schema))
    engine = create_engine(os.environ['TEST_POSTGRES_URL'], connect_args={'options': '-csearch_path=' + schema})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + schema + ' CASCADE'))
        admin.dispose()


def test_migrations_are_serialized_repeatable_and_preserve_data(pg):
    from app.migrations import run_migrations, require_current_schema
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: run_migrations(pg), range(2)))
    require_current_schema(pg)
    with pg.begin() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM schema_migrations')).scalar() == 3
        conn.execute(text("UPDATE users SET company_name='preserved'"))
        conn.execute(text('CREATE TABLE activity_events (id INTEGER)'))
        conn.execute(text('INSERT INTO activity_events VALUES (1)'))
    run_migrations(pg)
    with pg.connect() as conn:
        assert conn.execute(text('SELECT company_name FROM users')).scalar() == 'preserved'
        assert conn.execute(text('SELECT COUNT(*) FROM activity_events')).scalar() == 1


def test_duplicate_legacy_statuses_stop_before_mutation(pg):
    from app.migrations import run_migrations
    with pg.begin() as conn:
        conn.execute(text('CREATE TABLE delivery_statuses (delivery_id INTEGER, route_plan_id INTEGER)'))
        conn.execute(text('INSERT INTO delivery_statuses VALUES (1,1),(1,1)'))
    with pytest.raises(RuntimeError, match='duplicati'):
        run_migrations(pg)
    assert not inspect(pg).has_table('schema_migrations')
    with pg.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM delivery_statuses')).scalar() == 2


def test_concurrent_delivery_completion_counts_once(pg):
    from app.database import Base
    from app.models import User, Customer, RoutePlan, Delivery, DeliveryStatus, RouteUsage
    from app.services.route_execution import apply_delivery_update
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        owner = User(username='audit', password_hash='test', plan='business', plan_status='active')
        db.add(owner); db.flush()
        customer = Customer(user_id=owner.id, nome='Audit', indirizzo='Test')
        route = RoutePlan(user_id=owner.id, nome='Audit', data_giro=date.today(), orario_partenza=time(8), status='in_corso')
        db.add_all([customer, route]); db.flush()
        delivery = Delivery(route_plan_id=route.id, customer_id=customer.id, cliente_nome='Audit', indirizzo='Test')
        db.add(delivery); db.commit()
        delivery_id, customer_id = delivery.id, customer.id
    def complete(_):
        with Session(pg, autoflush=False) as db:
            apply_delivery_update(db, db.get(Delivery, delivery_id), {'tempo_scarico': 20}, 'complete')
            db.commit()
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(complete, range(3)))
    with Session(pg) as db:
        assert db.query(DeliveryStatus).count() == 1
        assert db.query(RouteUsage).count() == 1
        assert db.get(Customer, customer_id).tempo_scarico_rilevazioni == 1
