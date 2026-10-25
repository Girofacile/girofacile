"""Nuovi ordini automatici: notifica interna e contatore nel menu Ordini."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def notifications(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('ALLOW_SQLITE_LEGACY', 'true')
    from app.database import Base, get_db
    from app.models import User
    from app.routers.notifications import router
    from app.core.dependencies import current_user
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    event.listen(engine, 'connect', lambda conn, _: conn.execute('PRAGMA foreign_keys=ON'))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner=User(username='notify-owner',password_hash='test',plan_status='active')
        other=User(username='notify-other',password_hash='test',plan_status='active')
        db.add_all([owner,other]);db.commit()
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:db
        app.dependency_overrides[current_user]=lambda:owner
        with TestClient(app) as client: yield client,db,owner,other
    engine.dispose()


def add_order(db, user, kind, number, status='nuovo'):
    from app.order_models import Order, OrderSource
    source=db.query(OrderSource).filter_by(user_id=user.id, key=kind).first()
    if not source:
        source=OrderSource(user_id=user.id, key=kind, name='Negozio '+kind, kind=kind, status='active')
        db.add(source);db.flush()
    order=Order(user_id=user.id, source_id=source.id, external_id=number, number=number,
                recipient_name='Mario Rossi', original_payload={}, operational_data={}, status=status)
    db.add(order);db.commit()
    return order


def test_automatic_orders_notify_and_badge_clears_by_type(notifications):
    client,db,owner,other=notifications
    from datetime import timedelta
    from app.core.clock import utc_now
    add_order(db, owner, 'api', 'WEB-1')
    # Gli ordini via API arrivano già «da verificare» (controllo indirizzo).
    add_order(db, owner, 'api', 'WEB-2', status='da_verificare')
    add_order(db, owner, 'api', 'WEB-3', status='assegnato')
    vecchio = add_order(db, owner, 'api', 'WEB-OLD', status='da_verificare')
    vecchio.received_at = utc_now() - timedelta(days=5); db.commit()
    add_order(db, owner, 'manual', 'MAN-1')
    add_order(db, owner, 'file', 'CSV-1')
    add_order(db, other, 'api', 'ALTRO-1')
    data=client.get('/api/notifications').json()
    orders=[n for n in data['items'] if n['type']=='order_new']
    assert sorted(n['message'].split()[1] for n in orders)==['WEB-1','WEB-2']
    assert all(n['action_tab']=='ordini' for n in orders)
    assert data['orders_unread']==2 and data['unread']==2
    # Una seconda lettura non duplica le notifiche.
    assert client.get('/api/notifications').json()['orders_unread']==2
    assert client.post('/api/notifications/read-all?type=order_new').json()['updated']==2
    data=client.get('/api/notifications').json()
    assert data['orders_unread']==0 and data['unread']==0
