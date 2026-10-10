"""PostgreSQL migration, constraints and real concurrent writes in disposable schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, time
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from fastapi import HTTPException
from test_audit_postgres import pg


def test_order_migration_repeatable_and_preserves_existing_records(pg):
    from app.database import Base
    from app.models import User, Customer
    from app.order_models import ORDER_TABLES
    from app.migrations import run_migrations, require_current_schema
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        user=User(username='preserve',password_hash='test');db.add(user);db.flush()
        db.add(Customer(user_id=user.id,nome='Preserved customer',indirizzo='Existing address'));db.commit()
    with pg.begin() as conn:
        for table in reversed(ORDER_TABLES):table.drop(conn)
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)'))
        for version in ('20261004_01','20261004_02','20261004_03','20261004_04','20261006_01','20261009_01','20261009_02'):
            conn.execute(text('INSERT INTO schema_migrations VALUES (:v,:now)'),{'v':version,'now':datetime.utcnow()})
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:run_migrations(pg),range(2)))
    run_migrations(pg);require_current_schema(pg)
    assert all(inspect(pg).has_table(t.name) for t in ORDER_TABLES)
    with Session(pg) as db:assert db.query(Customer).one().nome=='Preserved customer'


def test_simultaneous_first_orders_and_version_conflicts(pg):
    from app.database import Base
    from app.models import User
    from app.order_models import OrderSource,OrderEvent
    from app.services.orders import create_order,get_order,update_order
    from app.schemas.orders import OrderCreate,OrderUpdate
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        user=User(username='concurrent',password_hash='test');db.add(user);db.commit();uid=user.id
    def create(index):
        with Session(pg) as db:
            row=create_order(db,uid,OrderCreate(number=f'O-{index}'),'test');db.commit();return row.id
    with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(create,range(4)))
    with Session(pg) as db:assert db.query(OrderSource).count()==1
    def update(index):
        with Session(pg) as db:
            try:
                row=get_order(db,uid,ids[0],lock=True)
                update_order(db,row,OrderUpdate(number='Corrected',notes=str(index),version=1),'test')
                db.commit();return 200
            except HTTPException as error:
                db.rollback();return error.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(update,range(4)))
    assert results.count(200)==1 and results.count(409)==3
    with Session(pg) as db:assert db.query(OrderEvent).filter_by(order_id=ids[0],kind='corrected').count()==1


def test_assignment_survives_delivery_recreation_and_blocks_duplicates(pg):
    from app.database import Base
    from app.models import User,RoutePlan,Delivery
    from app.order_models import RouteOrderAssignment
    from app.services.orders import create_order
    from app.schemas.orders import OrderCreate
    from sqlalchemy.exc import IntegrityError
    import pytest
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        user=User(username='assignment',password_hash='test');db.add(user);db.flush()
        row=create_order(db,user.id,OrderCreate(number='A'),'test')
        route=RoutePlan(user_id=user.id,nome='Draft',data_giro=date.today(),orario_partenza=time(8));db.add(route);db.flush()
        delivery=Delivery(route_plan_id=route.id,cliente_nome='Name',indirizzo='Address');db.add(delivery)
        db.add(RouteOrderAssignment(user_id=user.id,order_id=row.id,route_plan_id=route.id,stop_key='stable-key'));db.commit()
        db.delete(delivery);db.flush()
        db.add(Delivery(route_plan_id=route.id,cliente_nome='Name',indirizzo='Address'));db.commit()
        assert db.query(RouteOrderAssignment).one().stop_key=='stable-key'
        with pytest.raises(IntegrityError):
            db.add(RouteOrderAssignment(user_id=user.id,order_id=row.id,route_plan_id=route.id,stop_key='other'))
            db.commit()
        db.rollback()


def test_geocoding_commit_rechecks_concurrent_edit(pg,monkeypatch):
    from app.database import Base
    from app.models import User
    from app.order_models import Order
    from app.services.orders import create_order,get_order,verify_address
    from app.schemas.orders import OrderCreate
    import pytest
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        user=User(username='geocode-race',password_hash='test');db.add(user);db.flush()
        order=create_order(db,user.id,OrderCreate(number='A',delivery_address='Old address'),'test');db.commit()
        uid,oid=user.id,order.id
        def geocode(session,user_id,address):
            session.commit()  # Mirrors existing API usage logging.
            with Session(pg) as concurrent:
                row=concurrent.get(Order,oid);row.version+=1;row.delivery_address='New address';concurrent.commit()
            return {'stato_geocodifica':'verificato','lat':1,'lon':1,'indirizzo':address}
        monkeypatch.setattr('app.services.orders.verify_stop_address',geocode)
        with pytest.raises(HTTPException) as error:
            verify_address(db,get_order(db,uid,oid,lock=True),1,'test')
        assert error.value.status_code==409
        db.rollback()
        assert db.get(Order,oid).address_verification is None
