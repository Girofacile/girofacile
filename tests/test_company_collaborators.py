"""Delegation integration tests on an isolated database; no production writes."""
import json
from datetime import datetime, timedelta
import pytest


@pytest.fixture
def company(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("ALLOW_SQLITE_LEGACY", "true")
    monkeypatch.setenv("OBJECT_STORAGE_ENABLED", "false")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.database import Base, get_db
    from app.models import User, Customer, CompanyCollaborator
    from app.core.security import hash_password, make_token, make_account_token
    from app.services.sessions import credential
    from app.routers import auth, collaborators, customers, deposits, routes, settings, billing, operator
    from app.routers.vehicles_drivers import vehicles_router, drivers_router
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner=User(username='owner-test', email='owner@example.test', company_name='Demo', password_hash=hash_password('Orbit!River47Cedar#'), plan='business', plan_status='active')
        other=User(username='other-test', password_hash='different', plan='business', plan_status='active')
        db.add_all([owner,other]);db.flush()
        actor=CompanyCollaborator(user_id=owner.id, full_name='Operatore Test',email='operator@example.test',password_hash=hash_password('Orbit!River47Cedar#'),permissions_json='[]')
        first=Customer(user_id=owner.id,nome='Owned',indirizzo='Via Uno',codice_cliente='A1')
        foreign=Customer(user_id=other.id,nome='Foreign',indirizzo='Via Due',codice_cliente='B1')
        db.add_all([actor,first,foreign]);db.commit()
        app=FastAPI()
        for module in (auth,collaborators,customers,deposits,routes,settings,billing,operator):app.include_router(module.router)
        app.include_router(vehicles_router);app.include_router(drivers_router)
        app.dependency_overrides[get_db]=lambda:db
        with TestClient(app) as client:
            def login_owner():client.cookies.set('session',make_token(owner.id,owner.password_hash))
            def login_actor(grants=()):
                actor.permissions_json=json.dumps(grants);db.commit()
                client.cookies.set('session',make_account_token('collaborator',actor.id,credential(actor)))
            yield client,db,owner,other,actor,first,foreign,login_owner,login_actor
    engine.dispose()


def test_owner_can_create_edit_and_isolate_company_accounts(company):
    client,db,owner,other,actor,_,_,login_owner,login_actor=company
    login_owner()
    data={'full_name':'Planner','email':'planner@example.test','password':'Orbit!River47Cedar#','permissions':['routes.program']}
    result=client.post('/api/collaborators',json=data)
    assert result.status_code==200,result.text
    saved=result.json()
    assert {'routes.program','routes.plan','customers.read','vehicles.read'} <= set(saved['permissions'])
    assert 'password_hash' not in saved
    assert client.post('/api/collaborators',json=dict(data,email='owner@example.test')).status_code==409
    assert client.post('/api/collaborators',json=dict(data,email='bad@example.test',permissions=['all'])).status_code==422
    assert client.post('/api/collaborators',json=dict(data,email='bad@example.test',user_id=other.id)).status_code==422
    from app.models import CompanyCollaborator
    foreign=CompanyCollaborator(user_id=other.id,full_name='Other',email='foreign@example.test',password_hash='x')
    db.add(foreign);db.commit()
    assert foreign.id not in [r['id'] for r in client.get('/api/collaborators').json()]
    assert client.put(f'/api/collaborators/{foreign.id}',json=data).status_code==404
    login_actor(['customers.read'])
    for path in ('/api/collaborators','/api/collaborators/permissions','/api/billing/data-export','/api/account-profile'):
        assert client.get(path).status_code==403,path
    assert client.post('/api/collaborators',json=data).status_code==403


def test_read_only_cannot_mutate_or_cross_tenants(company):
    client,db,owner,other,actor,first,foreign,_,login_actor=company
    login_actor(['customers.read'])
    response=client.get('/api/customers')
    assert response.status_code==200,response.text
    assert [r['id'] for r in response.json()]==[first.id]
    assert client.delete(f'/api/customers/{first.id}').status_code==403
    assert client.get('/api/deposits').status_code==403
    assert client.put('/api/settings',json={}).status_code==403
    login_actor(['customers.read','customers.delete'])
    assert client.delete(f'/api/customers/{foreign.id}').status_code==404
    assert db.get(type(foreign),foreign.id).deleted_at is None
    # Changes to grants are enforced against the current database on the next request.
    actor.permissions_json='[]';db.commit()
    assert client.get('/api/customers').status_code==403


def test_login_logout_disable_and_reenable_do_not_reuse_old_session(company):
    client,db,owner,_,actor,_,_,login_owner,login_actor=company
    response=client.post('/api/login',json={'username':actor.email,'password':'Orbit!River47Cedar#'})
    assert response.status_code==200,response.text
    assert response.json()['is_collaborator'] is True
    assert response.json()['is_admin'] is False
    me=client.get('/api/me').json()
    assert me['username']==actor.full_name and me['company_name']==owner.company_name
    old=client.cookies.get('session')
    assert client.post('/api/logout').status_code==200
    client.cookies.set('session',old)
    assert client.get('/api/me').json()['authenticated'] is False
    client.cookies.clear();login_actor()
    old=client.cookies.get('session');login_owner()
    payload={'full_name':actor.full_name,'email':actor.email,'permissions':[],'is_active':False}
    assert client.put(f'/api/collaborators/{actor.id}',json=payload).status_code==200
    payload['is_active']=True
    assert client.put(f'/api/collaborators/{actor.id}',json=payload).status_code==200
    client.cookies.clear();client.cookies.set('session',old)
    assert client.get('/api/me').json()['authenticated'] is False


def test_collaborator_profile_never_updates_owner_and_password_revokes_sessions(company):
    client,db,owner,_,actor,_,_,_,login_actor=company
    login_actor()
    assert client.get('/api/collaborator/account').json()['email']==actor.email
    assert client.put('/api/collaborator/account',json={'username':'New name','email':actor.email}).status_code==200
    assert owner.username=='owner-test'
    assert client.put('/api/collaborator/account',json={'permissions':['all']}).status_code==422
    old=client.cookies.get('session')
    result=client.post('/api/collaborator/password',json={'current_password':'Orbit!River47Cedar#','new_password':'Silver&Falcon93Maple!','confirm_password':'Silver&Falcon93Maple!'})
    assert result.status_code==200,result.text
    client.cookies.clear();client.cookies.set('session',old)
    assert client.get('/api/me').json()['authenticated'] is False
    from app.core.security import verify_password
    assert verify_password('Orbit!River47Cedar#',owner.password_hash)


def test_password_reset_cannot_reactivate_disabled_collaborator(company):
    client,db,_,_,actor,*_=company
    from app.routers.auth import _create_reset_token, _find_reset_accounts
    token=_create_reset_token(db,'collaborator',actor.id,actor.email);db.commit()
    assert ('collaborator',actor) in _find_reset_accounts(actor.email,db)
    actor.is_active=False;db.commit()
    assert _find_reset_accounts(actor.email,db)==[]
    assert client.post('/api/password-reset/confirm',json={'token':token.token,'password':'Silver&Falcon93Maple!'}).status_code==404


def test_planner_cannot_program_or_manage_routes_without_explicit_grant(company):
    client,db,_,_,actor,_,_,_,login_actor=company
    from app.services.company_permissions import normalize_permissions
    login_actor(normalize_permissions(['routes.plan']))
    assert client.get('/api/vehicles').status_code==200
    for action in ('program','cancel','complete','generate-token'):
        assert client.post(f'/api/routes/999/{action}',json={}).status_code==403,action
    assert client.post('/api/vehicles',json={}).status_code==403


def test_new_or_unlisted_company_endpoints_fail_closed(company):
    from fastapi import Depends
    from app.core.dependencies import current_user
    client,*rest=company
    @client.app.get('/api/future-feature')
    def future(user=Depends(current_user)):return {'secret':True}
    rest[-1](['routes.read','company.update','settings.update'])
    assert client.get('/api/future-feature').status_code==403


def test_email_change_revokes_existing_session_and_reset_link(company):
    client,db,_,_,actor,_,_,login_owner,login_actor=company
    from app.routers.auth import _create_reset_token
    login_actor();old=client.cookies.get('session')
    reset=_create_reset_token(db,'collaborator',actor.id,actor.email);db.commit()
    login_owner()
    assert client.put(f'/api/collaborators/{actor.id}',json={'full_name':actor.full_name,'email':'changed@example.test','permissions':[]}).status_code==200
    assert reset.used_at is not None
    client.cookies.clear();client.cookies.set('session',old)
    assert client.get('/api/me').json()['authenticated'] is False


def test_planner_cannot_rewrite_a_scheduled_route(company):
    from app.models import RoutePlan
    from datetime import date, time
    from app.services.company_permissions import normalize_permissions
    client,db,owner,_,_,_,_,_,login_actor=company
    route=RoutePlan(user_id=owner.id,nome='Scheduled',status='programmato',data_giro=date(2099,1,1),orario_partenza=time(8))
    db.add(route);db.commit()
    login_actor(normalize_permissions(['routes.plan']))
    response=client.post('/api/routes/recalculate-manual',json={'route_id':route.id,'data_giro':'2099-01-01','deposit_id':1,'consegne':[]})
    assert response.status_code==403,response.text
    assert route.status=='programmato'


def test_additive_migration_preserves_accounts_and_is_repeatable(company):
    from sqlalchemy import create_engine, text, inspect
    from app.migrations import run_migrations, require_current_schema, LATEST
    engine=create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)'))
        conn.execute(text("INSERT INTO users VALUES (1,'existing-owner')"))
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in ('20261004_01','20261004_02','20261004_03','20261004_04','20261006_01'):
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'),{'v':version})
    run_migrations(engine);run_migrations(engine);require_current_schema(engine)
    assert inspect(engine).has_table('company_collaborators')
    with engine.connect() as conn:
        assert conn.execute(text('SELECT username FROM users')).scalar()=='existing-owner'
        assert conn.execute(text('SELECT COUNT(*) FROM schema_migrations WHERE version=:v'),{'v':LATEST}).scalar()==1
    engine.dispose()


def test_permission_rules_match_registered_endpoints(company):
    from app.main import app
    from app.services.company_permissions import RULES
    registered={(method,route.path) for route in app.routes for method in getattr(route,'methods',())}
    assert set(RULES) <= registered, set(RULES)-registered


def test_expired_company_can_revoke_access_but_collaborator_cannot_write(company):
    client,db,owner,_,actor,_,_,login_owner,login_actor=company
    owner.plan_status='cancelled';owner.billing_suspended=True;db.commit()
    login_actor(['customers.read','customers.create'])
    assert client.post('/api/customers',json={'nome':'Blocked','indirizzo':'Via Uno'}).status_code==403
    login_owner()
    result=client.put(f'/api/collaborators/{actor.id}',json={'full_name':actor.full_name,'email':actor.email,'permissions':[],'is_active':False})
    assert result.status_code==200,result.text
    assert not actor.is_active


def test_presets_are_explicit_dependency_complete_and_do_not_grant_future_keys(monkeypatch):
    from app.services import company_permissions as policy
    presets = policy.permission_presets()
    assert [item["key"] for item in presets] == ["operator", "planner", "read_only"]
    operator = next(item for item in presets if item["key"] == "operator")
    assert set(operator["permissions"]) == policy.VALID
    for item in presets:
        assert item["permissions"] == policy.normalize_permissions(item["permissions"])
        assert len(item["permissions"]) == len(set(item["permissions"]))
        assert not any(key.startswith(("billing.", "collaborators.", "subscription.", "admin."))
                       for key in item["permissions"])
    monkeypatch.setattr(policy, "VALID", policy.VALID | {"future.read"})
    monkeypatch.setattr(policy, "CATALOG", policy.CATALOG + [
        {"key": "future.read", "group": "Nuova funzione", "label": "Visualizza"}])
    assert "future.read" not in next(
        item for item in policy.permission_presets() if item["key"] == "operator")["permissions"]
    operator["permissions"].clear()
    assert policy.permission_presets()[0]["permissions"]


def test_operator_preset_authorizes_every_current_delegable_operation():
    from types import SimpleNamespace
    from starlette.requests import Request
    from app.services.company_permissions import RULES, authorize, permission_presets
    grants = next(item["permissions"] for item in permission_presets() if item["key"] == "operator")
    actor = SimpleNamespace(permissions_json=json.dumps(grants))
    for (method, template), required in RULES.items():
        request = Request({"type": "http", "method": method, "path": template,
                           "route": SimpleNamespace(path=template), "headers": []})
        authorize(request, actor)


def test_preset_metadata_is_owner_only_and_does_not_change_existing_accounts(company):
    client, db, _, _, actor, _, _, login_owner, login_actor = company
    from app.services.company_permissions import permission_presets
    before = actor.permissions_json
    login_owner()
    response = client.get("/api/collaborators/permissions")
    assert response.status_code == 200, response.text
    assert response.json()["presets"] == permission_presets()
    assert actor.permissions_json == before
    login_actor(permission_presets()[0]["permissions"])
    assert client.get("/api/collaborators/permissions").status_code == 403


def test_operator_can_edit_company_settings_but_cannot_cross_company(company):
    client, db, owner, other, _, first, foreign, _, login_actor = company
    from app.services.company_permissions import permission_presets
    login_actor(permission_presets()[0]["permissions"])
    for path in ("/api/customers", "/api/deposits", "/api/vehicles", "/api/drivers",
                 "/api/settings", "/api/company-profile"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
    other_name = other.company_name
    other_signature = other.delivery_signature_enabled
    result = client.put("/api/company-profile", json={"company_name": "Azienda aggiornata"})
    assert result.status_code == 200, result.text
    assert owner.company_name == "Azienda aggiornata"
    assert other.company_name == other_name
    result = client.put("/api/settings", json={"delivery_signature_enabled": True})
    assert result.status_code == 200, result.text
    assert owner.delivery_signature_enabled is True
    assert other.delivery_signature_enabled == other_signature
    result = client.put(f"/api/customers/{first.id}",
                        json={"nome": "Cliente aggiornato", "indirizzo": "Via Uno", "codice_cliente": "A1"})
    assert result.status_code == 200, result.text
    assert first.nome == "Cliente aggiornato"
    result = client.put(f"/api/customers/{foreign.id}",
                        json={"nome": "Accesso vietato", "indirizzo": "Via Due", "codice_cliente": "B1"})
    assert result.status_code == 404, result.text
    assert foreign.nome == "Foreign"
    assert client.delete(f"/api/customers/{foreign.id}").status_code == 404
    assert foreign.deleted_at is None


def test_operator_cannot_access_owner_billing_subscription_or_collaborators(company):
    client, _, _, _, actor, _, _, _, login_actor = company
    from app.services.company_permissions import permission_presets
    login_actor(permission_presets()[0]["permissions"])
    for path in ("/api/billing/overview", "/api/billing/my-plan", "/api/billing/data-export",
                 "/api/billing/invoices/999/download", "/api/collaborators",
                 "/api/collaborators/permissions", "/api/account-profile", "/api/onboarding/status"):
        response = client.get(path)
        assert response.status_code == 403, (path, response.text)
    for action in ("select-plan", "create-checkout-session", "cancel-checkout", "sync",
                   "change-preview", "change-plan", "cancel", "resume", "portal"):
        response = client.post(f"/api/billing/{action}", json={"plan": "pro"})
        assert response.status_code == 403, (action, response.text)
    assert client.put("/api/billing/billing-details", json={"company_name": "Forbidden"}).status_code == 403
    payload = {"full_name": actor.full_name, "email": actor.email, "permissions": []}
    assert client.post("/api/collaborators", json=payload).status_code == 403
    assert client.put(f"/api/collaborators/{actor.id}", json=payload).status_code == 403


def test_owner_can_replace_a_preset_with_manual_permissions_without_role_escalation(company):
    client, db, _, _, actor, _, _, login_owner, login_actor = company
    from app.services.company_permissions import normalize_permissions, permission_presets
    login_owner()
    payload = {"full_name": actor.full_name, "email": actor.email,
               "permissions": permission_presets()[0]["permissions"]}
    assert client.put(f"/api/collaborators/{actor.id}", json=payload).status_code == 200
    payload["permissions"] = ["customers.read"]
    result = client.put(f"/api/collaborators/{actor.id}", json=payload)
    assert result.status_code == 200, result.text
    expected = normalize_permissions(["customers.read"])
    assert result.json()["permissions"] == expected
    assert json.loads(actor.permissions_json) == expected
    assert client.put(f"/api/collaborators/{actor.id}",
                      json=dict(payload, permissions=["operator"])).status_code == 422
    assert client.put(f"/api/collaborators/{actor.id}",
                      json=dict(payload, role="operator")).status_code == 422
    login_actor(expected)
    assert client.get("/api/customers").status_code == 200
    assert client.delete(f"/api/customers/{actor.id}").status_code == 403
    assert client.put("/api/company-profile", json={"company_name": "Forbidden"}).status_code == 403
    assert client.put("/api/settings", json={}).status_code == 403


@pytest.mark.parametrize("preset_key", ["planner", "read_only"])
def test_other_presets_do_not_modify_anagraphics_or_company_settings(company, preset_key):
    client, _, _, _, _, first, _, _, login_actor = company
    from app.services.company_permissions import permission_presets
    grants = next(item["permissions"] for item in permission_presets() if item["key"] == preset_key)
    login_actor(grants)
    assert client.get("/api/customers").status_code == 200
    assert client.delete(f"/api/customers/{first.id}").status_code == 403
    assert client.put("/api/company-profile", json={"company_name": "Forbidden"}).status_code == 403
    assert client.put("/api/settings", json={}).status_code == 403
