"""Real PostgreSQL contention for selection and exclusive order reservations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from sqlalchemy.orm import Session
from fastapi import HTTPException
from test_audit_postgres import pg


def test_concurrent_selections_and_reservations(pg):
    from app.database import Base
    from app.models import User, RoutePlan
    from app.order_models import Order, RouteOrderAssignment
    from app.services.orders import create_order
    from app.schemas.orders import OrderCreate
    from app.schemas.order_planning import SelectionChange
    from app.services.order_planning import change_selection, stop_key
    from app.services.route_orders import lock_company, reserve_orders
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        user=User(username='planning-race',password_hash='test');db.add(user);db.flush()
        order=create_order(db,user.id,OrderCreate(number='RACE'),'owner');order.status='pronto'
        db.commit();uid,oid,version=user.id,order.id,order.version
    def select(index):
        with Session(pg) as db:
            try:
                change_selection(db,uid,'owner',SelectionChange(version=0,action='add',order_ids=[oid]))
                db.commit();return 200
            except HTTPException as error:
                db.rollback();return error.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(select,range(4)))
    assert sorted(results)==[200,409,409,409]
    # A different actor's selection is independent within the same company.
    with Session(pg) as db:
        row=change_selection(db,uid,'collaborator:2',SelectionChange(version=0,action='add',order_ids=[oid]))
        assert row.order_ids==[oid];db.commit()
    def reserve(index):
        with Session(pg) as db:
            try:
                lock_company(db,uid)
                route=RoutePlan(user_id=uid,nome=f'Route {index}',status='bozza',data_giro=date(2099,1,1),orario_partenza=time(8))
                db.add(route);db.flush()
                reserve_orders(db,route,[{'order_refs':[{'id':oid,'version':version}], 'order_stop_key':stop_key(uid,oid),'customer_id':None}])
                db.commit();return 200
            except HTTPException as error:
                db.rollback();return error.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(reserve,range(4)))
    assert sorted(results)==[200,409,409,409]
    with Session(pg) as db:
        assert db.query(RouteOrderAssignment).count()==1
        assert db.query(RoutePlan).count()==1
        assert db.get(Order,oid).status=='assegnato'


def test_customer_resolution_migration_preserves_archive(pg):
    from sqlalchemy import text, inspect
    from app.migrations import run_migrations, LATEST
    run_migrations(pg)
    with pg.begin() as conn:
        conn.execute(text('ALTER TABLE orders DROP COLUMN customer_resolution'))
        conn.execute(text('DELETE FROM schema_migrations WHERE version=:v'),{'v':LATEST})
    run_migrations(pg);run_migrations(pg)
    assert 'customer_resolution' in {c['name'] for c in inspect(pg).get_columns('orders')}
    with pg.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM schema_migrations WHERE version=:v'),{'v':LATEST}).scalar()==1


def test_concurrent_customer_mapping_conflict_is_atomic(pg):
    from app.database import Base
    from app.models import User, Customer
    from app.order_models import Order, CustomerSourceMapping
    from app.services.orders import create_order, get_order
    from app.services.order_customers import resolve
    from app.services.route_orders import lock_company
    from app.schemas.orders import OrderCreate, CustomerResolution
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        owner=User(username='mapping-race',password_hash='test');db.add(owner);db.flush()
        customers=[Customer(user_id=owner.id,nome=str(i),indirizzo='Address') for i in range(2)]
        db.add_all(customers);db.flush()
        orders=[create_order(db,owner.id,OrderCreate(number=str(i)),'test') for i in range(2)]
        for order in orders: order.external_customer_id='SAME-CODE'
        db.commit();uid=owner.id;pairs=[(o.id,c.id) for o,c in zip(orders,customers)]
    def assign(pair):
        with Session(pg) as db:
            try:
                lock_company(db,uid)
                resolve(db,db.get(User,uid),get_order(db,uid,pair[0],lock=True),CustomerResolution(version=1,action='link',customer_id=pair[1]),'test')
                db.commit();return 200
            except HTTPException as error:
                db.rollback();return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(assign,pairs))
    assert sorted(results)==[200,409]
    with Session(pg) as db:
        assert db.query(CustomerSourceMapping).count()==1
        assert db.query(Order).filter(Order.customer_id.isnot(None)).count()==1
