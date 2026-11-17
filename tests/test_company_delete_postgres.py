"""Eliminare un'azienda dal pannello toglie anche fonti e ordini importati (PostgreSQL vero)."""
from datetime import date, time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from test_audit_postgres import pg


def test_company_with_order_source_is_deleted_with_its_orders(pg):
    from app.database import Base, get_db
    from app.models import User, RoutePlan
    from app.order_models import (OrderSource, Order, OrderItem, OrderImportRun, RouteOrderAssignment)
    from app.core.dependencies import require_superadmin
    from app.routers.admin_users import router
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        company = User(username='azienda', password_hash='test'); other = User(username='altra', password_hash='test')
        db.add_all([company, other]); db.flush()
        for owner in (company, other):
            src = OrderSource(user_id=owner.id, key=f'k{owner.id}', name='Shop', kind='api', status='active', configuration={})
            db.add(src); db.flush()
            order = Order(user_id=owner.id, source_id=src.id, external_id='1', number='1', original_payload={}, operational_data={})
            db.add(order); db.flush()
            db.add(OrderItem(order_id=order.id, line_number=1, data={}))
            db.add(OrderImportRun(user_id=owner.id, source_id=src.id, status='completed', report={}))
            route = RoutePlan(user_id=owner.id, nome='Giro', data_giro=date.today(), orario_partenza=time(8))
            db.add(route); db.flush()
            db.add(RouteOrderAssignment(user_id=owner.id, order_id=order.id, route_plan_id=route.id, stop_key='a'))
        db.commit()
        company_id, other_id = company.id, other.id
    sessions = sessionmaker(bind=pg)
    app = FastAPI(); app.include_router(router)

    def session():
        db = sessions()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[require_superadmin] = lambda: {'role': 'superadmin', 'username': 'owner'}
    with TestClient(app) as client:
        assert client.delete(f'/api/admin/users/{company_id}').status_code == 200
    with Session(pg) as db:
        assert db.get(User, company_id) is None
        for model in (OrderSource, Order, OrderImportRun, RouteOrderAssignment):
            assert db.query(model).filter_by(user_id=company_id).count() == 0
            # I dati di un'altra azienda restano intatti.
            assert db.query(model).filter_by(user_id=other_id).count() == 1
        assert db.query(OrderItem).count() == 1


def test_company_with_stripe_subscription_is_not_deleted(pg):
    from app.database import Base, get_db
    from app.models import User
    from app.core.dependencies import require_superadmin
    from app.routers.admin_users import router
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        company = User(username='pagante', password_hash='test', stripe_subscription_id='sub_123')
        db.add(company); db.commit(); company_id = company.id
    sessions = sessionmaker(bind=pg)
    app = FastAPI(); app.include_router(router)

    def session():
        db = sessions()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[require_superadmin] = lambda: {'role': 'superadmin', 'username': 'owner'}
    with TestClient(app) as client:
        response = client.delete(f'/api/admin/users/{company_id}')
    assert response.status_code == 409 and 'Stripe' in response.json()['detail']
    with Session(pg) as db:
        assert db.get(User, company_id) is not None


def test_company_with_cancelled_stripe_subscription_can_be_deleted(pg):
    from app.database import Base, get_db
    from app.models import User
    from app.core.dependencies import require_superadmin
    from app.routers.admin_users import router
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        ended = [User(username=f'ex{i}', password_hash='test', stripe_subscription_id=f'sub_{i}', plan_status=status)
                 for i, status in enumerate(('cancelled', 'expired'))]
        live = User(username='attiva', password_hash='test', stripe_subscription_id='sub_live', plan_status='past_due')
        db.add_all(ended + [live]); db.commit()
        ended_ids, live_id = [u.id for u in ended], live.id
    sessions = sessionmaker(bind=pg)
    app = FastAPI(); app.include_router(router)

    def session():
        db = sessions()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[require_superadmin] = lambda: {'role': 'superadmin', 'username': 'owner'}
    with TestClient(app) as client:
        for user_id in ended_ids:
            assert client.delete(f'/api/admin/users/{user_id}').status_code == 200
        # Un abbonamento con pagamento in sospeso è ancora vivo: resta bloccato.
        assert client.delete(f'/api/admin/users/{live_id}').status_code == 409
    with Session(pg) as db:
        assert all(db.get(User, user_id) is None for user_id in ended_ids)
        assert db.get(User, live_id) is not None
