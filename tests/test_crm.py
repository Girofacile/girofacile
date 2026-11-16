"""CRM HTTP flows, permissions and isolation on disposable databases."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def crm(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('ALLOW_SQLITE_LEGACY', 'true')
    from app.database import Base, get_db
    from app.models import SuperAdminCollaborator
    from app.core.dependencies import require_superadmin
    from app.routers.admin_crm import router
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        users = [SuperAdminCollaborator(full_name=name, email=name+'@example.test', password_hash='test',
                                       permissions_json=json.dumps({'crm_access': True, 'crm_write': True})) for name in ('Anna', 'Bruno')]
        db.add_all(users); db.commit()
        actor = {'role': 'superadmin', 'username': 'owner'}
        app = FastAPI(); app.include_router(router)
        def session():
            try:
                yield db
            finally:
                db.rollback()
        app.dependency_overrides[get_db] = session
        app.dependency_overrides[require_superadmin] = lambda: actor
        with TestClient(app) as client:
            yield client, db, actor, users, app
    engine.dispose()


def company(client, **values):
    result = client.post('/api/admin/crm/companies', json={'name': 'Example company', **values})
    assert result.status_code == 201, result.text
    return result.json()


def seller(actor, user, **permissions):
    actor.clear(); actor.update(role='collaborator', username=user.email, collaborator_id=user.id,
                                permissions={'crm_access': True, 'crm_write': True, **permissions})


def test_complete_sales_workflow_and_conflicts(crm):
    client, db, actor, users, _ = crm
    parent = company(client, vat=' it 123 ', owner_id=users[0].id)
    assert parent['vat'] == 'IT123'
    response = client.post('/api/admin/crm/contacts', json={'company_id':parent['id'], 'name':'Mario Rossi', 'email':'mario@example.test'})
    assert response.status_code == 201, response.text
    response = client.post('/api/admin/crm/opportunities', json={'company_id':parent['id'], 'title':'Contratto annuale', 'amount':'1250.30', 'stage':'proposal'})
    assert response.status_code == 201, response.text
    deal = response.json()
    payload = {'company_id':parent['id'], 'title':deal['title'], 'amount':deal['amount'], 'stage':'won', 'version':deal['version']}
    won = client.put('/api/admin/crm/opportunities/'+str(deal['id']), json=payload)
    assert won.status_code == 200, won.text
    assert won.json()['closed_at'].endswith('Z') and won.json()['probability'] == 100
    assert client.put('/api/admin/crm/opportunities/'+str(deal['id']), json=payload).status_code == 409
    follow = client.post('/api/admin/crm/followups', json={'company_id':parent['id'], 'title':'Richiamare', 'due_at':'2020-01-01T10:00:00+01:00'}).json()
    assert follow['due_at'] == '2020-01-01T09:00:00Z'
    stats = client.get('/api/admin/crm/reports').json()
    assert stats['overdue_followups'] == 1 and stats['win_rate'] == 100
    data = {'name':parent['name'], 'owner_id':users[0].id, 'version':1, 'archived':True}
    assert client.put('/api/admin/crm/companies/'+str(parent['id']), json=data).status_code == 409
    done = client.put('/api/admin/crm/followups/'+str(follow['id']), json={
        'company_id':parent['id'], 'title':'Richiamare', 'due_at':follow['due_at'], 'status':'completed', 'version':follow['version']})
    assert done.status_code == 200, done.text
    assert done.json()['completed_at']
    assert client.post('/api/admin/crm/activities', json={'company_id':parent['id'], 'notes':'Demo concordata', 'kind':'call', 'occurred_at':'2026-11-16T12:00:00Z'}).status_code == 201
    history = client.get(f"/api/admin/crm/companies/{parent['id']}/history").json()
    assert any(r['action'] == 'stage:proposal->won' for r in history)
    assert client.put('/api/admin/crm/companies/'+str(parent['id']), json=data).status_code == 200
    assert client.get('/api/admin/crm/reports').json()['companies'] == 0
    assert client.get('/api/admin/crm/companies?archived=true').json()['total'] == 1


def test_assigned_scope_in_lists_records_reports_and_export(crm):
    client, db, actor, users, _ = crm
    own = company(client, name='Own company', owner_id=users[0].id)
    other = company(client, name='Other company', owner_id=users[1].id)
    contact = client.post('/api/admin/crm/contacts', json={'company_id':other['id'], 'name':'Private person'}).json()
    seller(actor, users[0], crm_export=True)
    assert client.get('/api/admin/crm/companies').json()['total'] == 1
    assert client.get('/api/admin/crm/companies/'+str(other['id'])).status_code == 404
    assert client.get('/api/admin/crm/records/contacts').json()['total'] == 0
    assert client.get('/api/admin/crm/reports').json()['companies'] == 1
    assert 'Other company' not in client.get('/api/admin/crm/export').text
    assert client.post('/api/admin/crm/contacts', json={'company_id':other['id'], 'name':'Intruder'}).status_code == 404
    assert client.put('/api/admin/crm/contacts/'+str(contact['id']), json={'company_id':own['id'], 'name':'Intruder', 'version':1}).status_code == 404
    assert client.post('/api/admin/crm/companies', json={'name':'Steal', 'owner_id':users[1].id}).status_code == 403
    created = company(client, name='Self assigned')
    assert created['owner_id'] == users[0].id


def test_permissions_are_explicit_read_only_and_origin_checked(crm):
    client, db, actor, users, app = crm
    actor.update(role='collaborator', permissions={'all': True})
    assert client.get('/api/admin/crm/reports').status_code == 403
    seller(actor, users[0], crm_write=False)
    assert client.get('/api/admin/crm/reports').status_code == 200
    assert client.post('/api/admin/crm/companies', json={'name':'Denied'}).status_code == 403
    assert client.get('/api/admin/crm/export').status_code == 403
    actor['permissions']['crm_write'] = True
    assert client.post('/api/admin/crm/companies', json={'name':'Denied'}, headers={'origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/admin/crm/companies', json={'name':'Denied'}, headers={'sec-fetch-site':'cross-site'}).status_code == 403
    actor['permissions']['crm_access'] = False
    assert client.get('/api/admin/crm/me').status_code == 403
    app.dependency_overrides.clear()
    assert client.get('/api/admin/crm/me').status_code == 401


def test_validation_duplicate_and_csv_formula(crm):
    client, db, actor, users, _ = crm
    parent = company(client, vat='123', name='=unsafe')
    assert client.post('/api/admin/crm/companies', json={'name':'Duplicate', 'vat':'123'}).status_code == 409
    assert client.post('/api/admin/crm/contacts', json={'company_id':parent['id'], 'name':'Referente', 'email':'invalid'}).status_code == 422
    assert client.post('/api/admin/crm/opportunities', json={'company_id':parent['id'], 'title':'Lost', 'stage':'lost'}).status_code == 422
    assert client.post('/api/admin/crm/opportunities', json={'company_id':parent['id'], 'title':'Wrong', 'amount':-1}).status_code == 422
    assert client.post('/api/admin/crm/followups', json={'company_id':parent['id'], 'title':'Wrong', 'due_at':'2026-11-16T10:00:00'}).status_code == 422
    assert "'=unsafe" in client.get('/api/admin/crm/export').text
    assert client.get('/api/admin/crm/companies').headers['cache-control'] == 'no-store'


def test_grants_cannot_be_self_assigned_and_tables_hidden(crm, monkeypatch):
    from app.services.crm_permissions import guard_grants
    from app.routers import admin_database
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        guard_grants({'role':'collaborator'}, {'crm_access':True})
    guard_grants({'role':'collaborator'}, {'crm_access':True}, {'crm_access':True})
    class Inspector:
        def get_table_names(self):
            return ['users', 'crm_companies', 'crm_contacts', 'crm_audit_events']
    monkeypatch.setattr(admin_database, '_db_inspector', lambda: Inspector())
    assert admin_database._allowed_database_tables() == ['users']


def test_real_cookie_revocation(crm):
    from app.core.dependencies import require_superadmin
    from app.core.security import make_superadmin_collaborator_token
    client, db, actor, users, app = crm
    app.dependency_overrides.pop(require_superadmin)
    user = users[0]
    client.cookies.set('superadmin_session', make_superadmin_collaborator_token(user.id,user.password_hash))
    assert client.get('/api/admin/crm/me').status_code == 200
    user.permissions_json = '{}'; db.commit()
    assert client.get('/api/admin/crm/me').status_code == 403
    user.is_active = False; db.commit()
    assert client.get('/api/admin/crm/me').status_code == 401


def test_delegated_manager_cannot_take_over_commercial_identity(crm, monkeypatch):
    from app.routers import admin_profile
    from fastapi import HTTPException
    client, db, actor, users, app = crm
    manager = {'role':'collaborator','username':'manager','permissions':{'manage_collaborators':True}}
    sent = []
    monkeypatch.setattr(admin_profile, 'send_superadmin_collaborator_invitation', lambda *args: sent.append(args))
    before = users[0].password_hash
    with pytest.raises(HTTPException) as denied:
        admin_profile.admin_resend_collaborator(users[0].id, db, manager)
    assert denied.value.status_code == 403
    assert users[0].password_hash == before and not sent
    with pytest.raises(HTTPException):
        admin_profile.admin_update_collaborator(users[0].id, {'permissions':{'crm_access':True}}, db, manager)
    with pytest.raises(HTTPException):
        admin_profile.admin_delete_collaborator(users[0].id, db, manager)


def test_invalid_grants_and_assigned_account_deletion(crm):
    from app.services.crm_permissions import guard_grants
    from app.routers.admin_profile import admin_delete_collaborator
    from fastapi import HTTPException
    client, db, actor, users, app = crm
    with pytest.raises(HTTPException):
        guard_grants(actor, {'crm_access':'false'})
    company(client, owner_id=users[0].id)
    with pytest.raises(HTTPException) as denied:
        admin_delete_collaborator(users[0].id, db, actor)
    assert denied.value.status_code == 409
