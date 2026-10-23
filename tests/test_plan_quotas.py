"""Commercial limits use isolated databases; no external provider calls."""
from copy import deepcopy
from datetime import datetime

from test_orders import orders, create
from test_order_ingestion import ingestion, api_source, setup
from test_company_collaborators import company


def test_manual_orders_cancellation_and_deletion_never_refund(orders, monkeypatch):
    from app.order_models import Order, OrderEvent, OrderItem
    from app.services.plan_catalog import PLAN_LIMITS
    from app.services.plans import monthly_order_usage
    client, db, owner, other = orders
    monkeypatch.setitem(PLAN_LIMITS['starter'], 'max_orders_per_month', 1)
    row = create(client)
    assert client.post(f"/api/orders/{row['id']}/status", json={'version': 1, 'status': 'annullato'}).status_code == 200
    assert client.post('/api/orders', json={'number': 'Over quota'}).status_code == 403
    db.query(OrderEvent).filter_by(order_id=row['id']).delete()
    db.query(OrderItem).filter_by(order_id=row['id']).delete()
    db.delete(db.get(Order, row['id'])); db.commit()
    assert monthly_order_usage(owner, db)['used'] == 1
    assert monthly_order_usage(other, db)['used'] == 0
    assert client.post('/api/orders', json={'number': 'Still over quota'}).status_code == 403


def test_order_month_rolls_at_italian_midnight(orders, monkeypatch):
    from app.services import plans
    from app.services.plan_catalog import PLAN_LIMITS
    client, db, owner, _ = orders
    monkeypatch.setitem(PLAN_LIMITS['starter'], 'max_orders_per_month', 1)
    monkeypatch.setattr(plans, 'utc_now', lambda: datetime(2026, 3, 31, 21, 59, 59))
    create(client, number='March')
    assert plans.monthly_order_usage(owner, db)['month'] == '2026-03'
    assert client.post('/api/orders', json={'number': 'Over March'}).status_code == 403
    monkeypatch.setattr(plans, 'utc_now', lambda: datetime(2026, 3, 31, 22))
    assert plans.monthly_order_usage(owner, db)['month'] == '2026-04'
    assert plans.monthly_order_usage(owner, db)['used'] == 0
    create(client, number='April')
    assert plans.monthly_order_usage(owner, db)['used'] == 1


def test_quota_migration_backfills_italian_months_and_preserves_existing_orders(orders):
    from sqlalchemy import text
    from app.migrations import run_migrations, require_current_schema, LATEST
    from app.order_models import OrderSource, Order, OrderMonthlyUsage
    _, db, owner, _ = orders
    source = OrderSource(user_id=owner.id, key='legacy-quota', name='Legacy', kind='manual')
    db.add(source); db.flush()
    for number, instant in [('March', datetime(2026, 3, 31, 21, 59, 59)), ('April', datetime(2026, 3, 31, 22))]:
        db.add(Order(user_id=owner.id, source_id=source.id, external_id=number, number=number,
                     original_payload={'keep': number}, operational_data={}, received_at=instant))
    db.commit()
    engine = db.get_bind()
    OrderMonthlyUsage.__table__.drop(engine)
    previous = ('20261004_01','20261004_02','20261004_03','20261004_04','20261006_01',
                '20261009_01','20261009_02','20261010_01','20261010_02','20261011_01',
                '20261011_02','20261013_01','20261013_02','20261020_01','20261020_02')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP NOT NULL)'))
        for version in previous:
            conn.execute(text('INSERT INTO schema_migrations VALUES (:v,CURRENT_TIMESTAMP)'), {'v': version})
    run_migrations(engine); run_migrations(engine); require_current_schema(engine)
    db.expire_all()
    assert db.get(OrderMonthlyUsage, (owner.id, '2026-03')).used == 1
    assert db.get(OrderMonthlyUsage, (owner.id, '2026-04')).used == 1
    assert {order.original_payload['keep'] for order in db.query(Order).all()} == {'March', 'April'}
    assert db.execute(text('SELECT COUNT(*) FROM schema_migrations WHERE version=:v'), {'v': LATEST}).scalar() == 1


def test_api_quota_counts_only_new_orders_and_batch_is_atomic(ingestion, monkeypatch):
    from app.order_models import Order
    from app.services.plan_catalog import PLAN_LIMITS
    from app.services.plans import monthly_order_usage
    client, db, owner, _ = ingestion
    owner.plan = 'business'; db.commit()
    monkeypatch.setitem(PLAN_LIMITS['business'], 'max_orders_per_month', 2)
    _, headers = api_source(ingestion)
    body = {'batch_id': 'one', 'orders': [{'external_id': 'A', 'number': 'A'}]}
    first = client.post('/api/order-ingestion', headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert client.post('/api/order-ingestion', headers=headers, json=body).json()['id'] == first.json()['id']
    updated = deepcopy(body); updated['batch_id'] = 'update'; updated['orders'][0]['notes'] = 'Updated'
    assert client.post('/api/order-ingestion', headers=headers, json=updated).status_code == 200
    assert monthly_order_usage(owner, db)['used'] == 1
    oversized = {'batch_id': 'too-many', 'orders': [
        {**updated['orders'][0], 'notes': 'Must not persist'},
        {'external_id': 'B', 'number': 'B'}, {'external_id': 'C', 'number': 'C'}]}
    rejected = client.post('/api/order-ingestion', headers=headers, json=oversized)
    assert rejected.status_code == 403, rejected.text
    assert db.query(Order).count() == 1
    assert db.query(Order).one().operational_data['notes'] == 'Updated'
    assert monthly_order_usage(owner, db)['used'] == 1
    accepted = {'batch_id': 'fits', 'orders': [updated['orders'][0], {'external_id': 'B', 'number': 'B'}]}
    assert client.post('/api/order-ingestion', headers=headers, json=accepted).status_code == 200
    assert monthly_order_usage(owner, db)['used'] == 2
    updated['batch_id'] = 'update-at-limit'; updated['orders'][0]['notes'] = 'Still editable'
    assert client.post('/api/order-ingestion', headers=headers, json=updated).status_code == 200
    assert monthly_order_usage(owner, db)['used'] == 2


def test_failed_import_rolls_back_reserved_credits(ingestion, monkeypatch):
    from app.order_models import Order
    from app.services import order_ingestion
    from app.services.plans import monthly_order_usage
    client, db, owner, _ = ingestion
    owner.plan = 'business'; db.commit()
    _, headers = api_source(ingestion)
    original = order_ingestion.apply_orders
    def fail_after_apply(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('Simulated storage failure')
    monkeypatch.setattr(order_ingestion, 'apply_orders', fail_after_apply)
    body = {'batch_id': 'fail', 'orders': [{'external_id': 'A', 'number': 'A'}]}
    result = client.post('/api/order-ingestion', headers=headers, json=body)
    assert result.status_code == 422, result.text
    assert db.query(Order).count() == 0
    assert monthly_order_usage(owner, db)['used'] == 0
    monkeypatch.setattr(order_ingestion, 'apply_orders', original)
    body['batch_id'] = 'retry'
    assert client.post('/api/order-ingestion', headers=headers, json=body).status_code == 200
    assert monthly_order_usage(owner, db)['used'] == 1


def test_file_confirmation_and_retries_share_order_quota(ingestion, monkeypatch):
    from app.services.plan_catalog import PLAN_LIMITS
    from app.services.plans import monthly_order_usage
    client, db, owner, _ = ingestion
    owner.plan = 'business'; db.commit()
    monkeypatch.setitem(PLAN_LIMITS['business'], 'max_orders_per_month', 1)
    src, rid = setup(ingestion)
    path = f"/api/order-sources/{src['id']}/runs/{rid}/commit"
    assert monthly_order_usage(owner, db)['used'] == 0
    assert client.post(path, json={'confirm': True}).status_code == 200
    assert client.post(path, json={'confirm': True}).status_code == 200
    assert monthly_order_usage(owner, db)['used'] == 1
    assert client.post('/api/orders', json={'number': 'Manual over same quota'}).status_code == 403


def test_collaborator_pending_invites_count_and_deactivation_releases_seat(company):
    from app.models import CompanyCollaborator
    from app.services.plans import collaborator_usage
    client, db, owner, _, actor, _, _, login_owner, _ = company
    owner.plan = 'starter'; db.commit(); login_owner()
    data = {'full_name': 'Pending invite', 'email': 'pending@example.test', 'permissions': []}
    invited = client.post('/api/collaborators', json=data)
    assert invited.status_code == 200, invited.text
    pending = invited.json()
    assert pending['password_setup_required']
    assert collaborator_usage(owner, db)['used'] == 2
    second = {**data, 'email': 'second@example.test'}
    assert client.post('/api/collaborators', json=second).status_code == 403
    actor_data = {'full_name': actor.full_name, 'email': actor.email, 'permissions': [], 'is_active': False}
    assert client.put(f'/api/collaborators/{actor.id}', json=actor_data).status_code == 200
    created = client.post('/api/collaborators', json=second)
    assert created.status_code == 200, created.text
    actor_data['is_active'] = True
    assert client.put(f'/api/collaborators/{actor.id}', json=actor_data).status_code == 403
    # A downgrade preserves excess accounts, while new seat allocations stop.
    db.add(CompanyCollaborator(user_id=owner.id, full_name='Historical', email='old@example.test', password_hash='x'))
    db.commit()
    assert collaborator_usage(owner, db)['over_limit']
    assert client.post('/api/collaborators', json={**data, 'email': 'blocked@example.test'}).status_code == 403
    assert db.query(CompanyCollaborator).filter_by(user_id=owner.id).count() == 4
