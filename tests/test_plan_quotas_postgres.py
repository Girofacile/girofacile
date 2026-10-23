"""Real row-lock contention for the final company quota slot."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy.orm import Session
from test_audit_postgres import pg


def test_manual_and_api_creation_share_the_last_order_credit(pg, monkeypatch):
    from app.database import Base
    from app.models import User
    from app.order_models import Order, OrderSource, OrderMonthlyUsage
    from app.schemas.orders import OrderCreate
    from app.schemas.order_sources import Acquisition
    from app.services.orders import create_order
    from app.services.order_ingestion import acquire, source
    from app.services.plan_catalog import PLAN_LIMITS
    Base.metadata.create_all(pg)
    monkeypatch.setitem(PLAN_LIMITS['business'], 'max_orders_per_month', 1)
    with Session(pg) as db:
        owner = User(username='quota-race', password_hash='test', plan='business', plan_status='active')
        db.add(owner); db.flush()
        src = OrderSource(user_id=owner.id, key='quota-api', name='API', kind='api', status='active', configuration={'mapping': {}})
        db.add(src); db.commit(); uid, sid = owner.id, src.id
    barrier = Barrier(2)
    def create(kind):
        with Session(pg) as db:
            barrier.wait(timeout=10)
            try:
                if kind == 'manual':
                    create_order(db, uid, OrderCreate(number='Manual'), 'owner')
                else:
                    acquire(db, source(db, uid, sid, lock=True),
                            Acquisition(batch_id='race', orders=[{'external_id': 'API', 'number': 'API'}]))
                db.commit(); return 201
            except HTTPException as exc:
                db.rollback(); return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, ('manual', 'api'))) == [201, 403]
    with Session(pg) as db:
        assert db.query(Order).count() == 1
        assert db.query(OrderMonthlyUsage).one().used == 1


def test_two_pending_invites_cannot_take_the_same_collaborator_seat(pg, monkeypatch):
    from app.database import Base
    from app.models import User, CompanyCollaborator
    from app.routers.collaborators import save, CollaboratorIn
    from app.services.plan_catalog import PLAN_LIMITS
    Base.metadata.create_all(pg)
    monkeypatch.setitem(PLAN_LIMITS['starter'], 'max_collaborators', 1)
    monkeypatch.setattr('app.services.email.send_collaborator_invitation', lambda *args, **kwargs: True)
    with Session(pg) as db:
        owner = User(username='collaborator-quota-race', password_hash='test', plan='starter', plan_status='active')
        db.add(owner); db.commit(); uid = owner.id
    barrier = Barrier(2)
    def invite(index):
        with Session(pg) as db:
            owner = db.get(User, uid)
            barrier.wait(timeout=10)
            try:
                save(CollaboratorIn(full_name=f'Collaborator {index}', email=f'quota-{index}@example.test', permissions=[]), owner, db)
                return 200
            except HTTPException as exc:
                db.rollback(); return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(invite, (1, 2))) == [200, 403]
    with Session(pg) as db:
        actor = db.query(CompanyCollaborator).one()
        assert actor.is_active and actor.password_setup_required
