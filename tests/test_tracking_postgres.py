"""Tracking schema and concurrent link creation on a disposable PG schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time, timedelta
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from test_audit_postgres import pg


def test_tracking_upgrade_is_repeatable_and_preserves_delivery(pg):
    from app.database import Base
    from app.models import DeliveryTrackingLink, Delivery, RoutePlan, User
    from app.migrations import run_migrations, require_current_schema
    Base.metadata.create_all(pg)
    DeliveryTrackingLink.__table__.drop(pg)
    with pg.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in ('20261004_01', '20261004_02', '20261004_03'):
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v':version})
    with Session(pg) as db:
        user = User(username='tracking', password_hash='test'); db.add(user); db.flush()
        plan = RoutePlan(user_id=user.id, nome='Preserved', data_giro=date.today(), orario_partenza=time(8))
        db.add(plan); db.flush()
        delivery = Delivery(route_plan_id=plan.id, cliente_nome='Preserved', indirizzo='Private')
        db.add(delivery); db.commit()
    run_migrations(pg); run_migrations(pg); require_current_schema(pg)
    assert inspect(pg).has_table('delivery_tracking_links')
    with Session(pg) as db:
        assert db.query(Delivery).one().cliente_nome == 'Preserved'


def test_concurrent_creation_and_delivery_delete(pg):
    from app.database import Base
    from app.models import User, RoutePlan, Delivery, DeliveryTrackingLink
    from app.services.delivery_tracking import owned_delivery, ensure_link, credential
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        user = User(username='tracking', password_hash='test'); db.add(user); db.flush()
        plan = RoutePlan(user_id=user.id, nome='Test', data_giro=date.today()+timedelta(days=1),
                         orario_partenza=time(8), status='programmato')
        db.add(plan); db.flush()
        delivery = Delivery(route_plan_id=plan.id, cliente_nome='Test', indirizzo='Test')
        db.add(delivery); db.commit()
        user_id, delivery_id = user.id, delivery.id
    def create(_):
        with Session(pg) as db:
            delivery, plan = owned_delivery(db, db.get(User,user_id), delivery_id)
            token = credential(ensure_link(db,delivery,plan))
            db.commit()
            return token
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(create,range(4)))) == 1
    with Session(pg) as db:
        assert db.query(DeliveryTrackingLink).count() == 1
        db.delete(db.get(Delivery,delivery_id)); db.commit()
        assert db.query(DeliveryTrackingLink).count() == 0
