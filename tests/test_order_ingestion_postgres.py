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
    from app.migrations import run_migrations,LATEST
    from app.models import User
    from app.order_models import OrderSource,Order
    run_migrations(pg)
    with Session(pg) as db:
        user=db.query(User).first()
        src=OrderSource(user_id=user.id,key='legacy',name='Legacy',kind='manual');db.add(src);db.flush()
        order=Order(user_id=user.id,source_id=src.id,external_id='legacy',number='Legacy',original_payload={'number':'Keep'},operational_data={})
        db.add(order);db.commit();oid=order.id
    with pg.begin() as conn:
        conn.execute(text('ALTER TABLE order_import_runs DROP CONSTRAINT IF EXISTS uq_order_import_request'))
        conn.execute(text('DROP INDEX IF EXISTS uq_order_import_request'))
        for table,fields in {'order_sources':['version'],'orders':['ingested_payload'],'order_import_runs':['idempotency_key','payload_hash','payload','expires_at','source_version']}.items():
            for field in fields:conn.execute(text(f'ALTER TABLE {table} DROP COLUMN {field}'))
        conn.execute(text('DELETE FROM schema_migrations WHERE version=:v'),{'v':LATEST})
    run_migrations(pg);run_migrations(pg)
    with Session(pg) as db:
        assert db.get(Order,oid).original_payload=={'number':'Keep'}
        assert db.get(Order,oid).ingested_payload is None
        assert db.query(OrderSource).filter_by(key='legacy').one().version==1
    assert 'uq_order_import_request' in {x['name'] for x in inspect(pg).get_indexes('order_import_runs')}
