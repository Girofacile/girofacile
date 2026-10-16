"""Actual row locking, idempotency and upgrade from phase-three schema."""
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session
from sqlalchemy import text,inspect
from fastapi import HTTPException
from test_audit_postgres import pg


def test_concurrent_ingestion_and_conflicting_keys(pg):
    from app.database import Base
    from app.models import User
    from app.order_models import OrderSource,Order,OrderImportRun
    from app.services.order_ingestion import source,acquire
    from app.schemas.order_sources import Acquisition
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        user=User(username='ingestion-race',password_hash='test',plan_status='active');db.add(user);db.flush()
        src=OrderSource(user_id=user.id,key='race',name='Race',kind='api',status='active',configuration={'mapping':{}})
        db.add(src);db.commit();uid,sid=user.id,src.id
    def send(args):
        batch,number=args
        with Session(pg) as db:
            try:
                row=source(db,uid,sid,lock=True)
                item=acquire(db,row,Acquisition(batch_id=batch,orders=[{'external_id':'ONE','number':number}]))
                db.commit();return item.status
            except HTTPException as exc:db.rollback();return exc.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(send,[('same','ONE')]*4))==['completed']*4
    with Session(pg) as db:
        assert db.query(Order).count()==1 and db.query(OrderImportRun).count()==1
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(send,[(f'new-{i}','ONE') for i in range(4)]))==['completed']*4
    assert send(('same','CHANGED'))==409
    with Session(pg) as db:
        assert db.query(Order).count()==1 and db.query(OrderImportRun).count()==5
        assert db.query(Order).one().original_payload['number']=='ONE'


def test_ingestion_migration_is_additive_and_repeatable(pg):
    from app.migrations import run_migrations, require_current_schema
    from app.models import User
    from app.order_models import OrderSource, Order

    # Recreate the schema immediately before this specific upgrade. LATEST may
    # refer to an unrelated migration as the application evolves.
    ingestion_version = '20261011_02'
    additions = {
        'order_sources': ['version'],
        'orders': ['ingested_payload'],
        'order_import_runs': [
            'idempotency_key', 'payload_hash', 'payload', 'expires_at', 'source_version',
        ],
    }
    history_sql = text('SELECT version, applied_at FROM schema_migrations ORDER BY version')
    run_migrations(pg)
    with pg.connect() as conn:
        original_history = dict(conn.execute(history_sql).all())
    assert ingestion_version in original_history
    with Session(pg) as db:
        user = db.query(User).first()
        src = OrderSource(user_id=user.id, key='legacy', name='Legacy', kind='manual')
        db.add(src)
        db.flush()
        order = Order(
            user_id=user.id, source_id=src.id, external_id='legacy', number='Legacy',
            original_payload={'number': 'Keep'}, operational_data={},
        )
        db.add(order)
        db.commit()
        oid, sid = order.id, src.id
    with pg.begin() as conn:
        conn.execute(text('ALTER TABLE order_import_runs DROP CONSTRAINT IF EXISTS uq_order_import_request'))
        conn.execute(text('DROP INDEX IF EXISTS uq_order_import_request'))
        for table, fields in additions.items():
            for field in fields:
                conn.execute(text(f'ALTER TABLE {table} DROP COLUMN {field}'))
        conn.execute(
            text('DELETE FROM schema_migrations WHERE version=:v'),
            {'v': ingestion_version},
        )
    run_migrations(pg)
    require_current_schema(pg)
    with pg.connect() as conn:
        applied_once = conn.execute(history_sql).all()
    assert set(dict(applied_once)) == set(original_history)
    assert {
        version: applied_at for version, applied_at in applied_once
        if version != ingestion_version
    } == {
        version: applied_at for version, applied_at in original_history.items()
        if version != ingestion_version
    }
    run_migrations(pg)
    require_current_schema(pg)
    with pg.connect() as conn:
        assert conn.execute(history_sql).all() == applied_once
    with Session(pg) as db:
        restored = db.get(Order, oid)
        assert restored.source_id == sid
        assert restored.original_payload == {'number': 'Keep'}
        assert restored.ingested_payload is None
        assert db.get(OrderSource, sid).version == 1
    inspector = inspect(pg)
    for table, fields in additions.items():
        assert set(fields) <= {column['name'] for column in inspector.get_columns(table)}
    version_column = next(
        column for column in inspector.get_columns('order_sources')
        if column['name'] == 'version'
    )
    assert version_column['nullable'] is False
    assert version_column['default'] is not None
    request_index = next(
        index for index in inspector.get_indexes('order_import_runs')
        if index['name'] == 'uq_order_import_request'
    )
    assert request_index['unique']
    assert request_index['column_names'] == ['source_id', 'idempotency_key']
