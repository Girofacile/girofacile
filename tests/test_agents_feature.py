"""Agent preference behavior against an isolated database, never production."""
import asyncio
import io
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.database import Base, get_db
    from app.core.dependencies import current_user
    from app.models import User, Agent, AgentAccount, AgentSetupToken, Customer
    from app.routers import settings, customers, agents, agent, reports, notifications

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = User(username="owner", password_hash="test", plan="business", plan_status="active")
        other = User(username="other", password_hash="test", plan="business", plan_status="active")
        db.add_all([owner, other])
        db.flush()
        seller = Agent(user_id=owner.id, nome="Mario", codice_agente="A1", email="agent@example.test")
        foreign = Agent(user_id=other.id, nome="Altro")
        db.add_all([seller, foreign])
        db.flush()
        account = AgentAccount(agent_id=seller.id, email=seller.email, password_hash="test", is_active=True)
        token = AgentSetupToken(agent_id=seller.id, token="setup-test", expires_at=datetime.utcnow()+timedelta(days=1))
        customer = Customer(user_id=owner.id, nome="Esistente", codice_cliente="C1", indirizzo="Via Roma", agent_id=seller.id)
        db.add_all([account, token, customer])
        db.commit()
        app = FastAPI()
        for module in [settings, customers, agents, agent, reports, notifications]:
            app.include_router(module.router)
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[current_user] = lambda: owner
        with TestClient(app) as client:
            yield client, db, owner, other, seller, foreign, customer, account, tmp_path
    engine.dispose()


def test_settings_default_partial_updates_and_company_isolation(env):
    client, db, owner, other, *_ = env
    assert client.get('/api/settings').json()['agents_enabled'] is False
    assert client.put('/api/settings', json={'agents_enabled': True}).json()['agents_enabled'] is True
    assert other.agents_enabled is False
    client.put('/api/settings', json={'delivery_signature_enabled': True})
    assert owner.agents_enabled and owner.delivery_signature_enabled
    client.put('/api/settings', json={'agents_enabled': False})
    assert owner.delivery_signature_enabled and not owner.agents_enabled
    assert client.put('/api/settings', json={'agents_enabled': 'false'}).status_code == 422


def test_plan_entitlement_cannot_be_bypassed(env):
    client, db, owner, *_ = env
    owner.plan = 'starter'
    db.commit()
    assert client.put('/api/settings', json={'agents_enabled': True}).status_code == 403
    assert not owner.agents_enabled
    assert client.put('/api/settings', json={'agents_enabled': False}).status_code == 200


def test_disabled_creates_unassigned_and_preserves_existing_assignment(env):
    client, db, owner, other, seller, foreign, existing, *_ = env
    payload = {'nome': 'Nuovo', 'indirizzo': 'Via Milano', 'agent_id': seller.id, 'stato_geocodifica': 'da_verificare'}
    created = client.post('/api/customers', json=payload)
    assert created.status_code == 200
    assert created.json()['agent_id'] is None
    payload.update(nome=existing.nome, indirizzo=existing.indirizzo, agent_id=None)
    assert client.put(f'/api/customers/{existing.id}', json=payload).json()['agent_id'] == seller.id
    assert len(client.get('/api/customers?agent_id=interno').json()) == 2


def test_enabled_customer_assignment_filter_and_cross_company_validation(env):
    client, db, owner, other, seller, foreign, existing, *_ = env
    client.put('/api/settings', json={'agents_enabled': True})
    payload = {'nome': 'Nuovo', 'indirizzo': 'Via Milano', 'agent_id': seller.id, 'stato_geocodifica': 'da_verificare'}
    created = client.post('/api/customers', json=payload).json()
    assert created['agent_id'] == seller.id
    assert client.get('/api/customers?agent_id=interno').json() == []
    payload['agent_id'] = foreign.id
    assert client.post('/api/customers', json=payload).status_code == 400
    payload['agent_id'] = None
    assert client.put(f'/api/customers/{created["id"]}', json=payload).json()['agent_id'] is None


@pytest.mark.parametrize('enabled', [False, True])
def test_import_respects_preference_and_preserves_existing_links(env, monkeypatch, enabled):
    from fastapi import UploadFile
    from app.routers import customers
    client, db, owner, other, seller, foreign, existing, account, tmp = env
    owner.agents_enabled = enabled
    db.commit()
    # Redirect this legacy importer's temporary path into the test directory.
    monkeypatch.setattr(customers, 'Path', lambda _: tmp)
    data = b'codice_cliente,nome,indirizzo,codice_agente\nC1,Esistente,Via Roma,A1\nC2,Nuovo,Via Milano,A1\n'
    upload = UploadFile(filename='agents.csv', file=io.BytesIO(data))
    result = asyncio.run(customers.import_customers(upload, db, owner))
    assert result == {'created': 1, 'updated': 1}
    from app.models import Customer
    fresh = db.query(Customer).filter_by(codice_cliente='C2').one()
    assert fresh.agent_id == (seller.id if enabled else None)
    assert existing.agent_id == seller.id


def test_agent_management_portal_and_invites_disable_and_resume(env):
    from app.routers.agent import make_session_token
    client, db, owner, other, seller, foreign, existing, account, *_ = env
    client.cookies.set('agent_session', make_session_token(account))
    for path in ['/api/agents', '/api/agent/customers', '/api/agent/me', '/api/agent/setup/setup-test']:
        assert client.get(path).status_code == 403
    client.put('/api/settings', json={'agents_enabled': True})
    assert client.get('/api/agents').status_code == 200
    assert client.get('/api/agent/customers').json()[0]['id'] == existing.id
    assert client.get('/api/agent/setup/setup-test').status_code == 200
    client.put('/api/settings', json={'agents_enabled': False})
    assert client.post(f'/api/agents/{seller.id}/invite', json={}).status_code == 403
    assert client.get('/api/agent/customers').status_code == 403
    assert account.is_active and existing.agent_id == seller.id


def test_report_ignores_hidden_agent_filter_and_omits_breakdowns(env):
    client, db, owner, *_ = env
    data = client.get('/api/reports/summary?agent_id=999').json()
    assert data['filters']['agent_id'] == ''
    assert data['charts']['agenti'] == [] and data['tables']['agenti'] == []
    client.put('/api/settings', json={'agents_enabled': True})
    assert client.get('/api/reports/summary?agent_id=999').json()['filters']['agent_id'] == '999'


def test_agent_notifications_hidden_with_matching_unread_count(env):
    client, db, owner, *_ = env
    client.put('/api/settings', json={'agents_enabled': True})
    enabled = client.get('/api/notifications').json()
    assert any(x['type'] == 'agent_customer' for x in enabled['items'])
    client.put('/api/settings', json={'agents_enabled': False})
    disabled = client.get('/api/notifications').json()
    assert not any(x['type'] == 'agent_customer' for x in disabled['items'])
    assert client.get('/api/notifications/count').json()['unread'] == disabled['unread']


def test_existing_database_migration_preserves_usage_and_runs_only_once(env):
    import ast
    from pathlib import Path
    import sqlalchemy
    from app.database import Base
    client, db, owner, other, seller, foreign, *_ = env
    owner_id, other_id = owner.id, other.id
    foreign.deleted_at = datetime.utcnow()
    db.commit()
    engine = db.get_bind()
    db.close()
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text('ALTER TABLE users DROP COLUMN agents_enabled'))
    # Run the real migration function without importing main's startup side effects.
    tree = ast.parse(Path('app/main.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'migrate_database')
    namespace = {**vars(sqlalchemy), 'Base': Base, 'engine': engine}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'app/main.py', 'exec'), namespace)
    namespace['migrate_database']()
    with engine.begin() as conn:
        values = dict(conn.execute(sqlalchemy.text('SELECT id, agents_enabled FROM users')).all())
        assert values[owner_id] == 1 and values[other_id] == 0
        conn.execute(sqlalchemy.text('UPDATE users SET agents_enabled = false'))
    namespace['migrate_database']()
    with engine.connect() as conn:
        assert not any(conn.execute(sqlalchemy.text('SELECT agents_enabled FROM users')).scalars())
