"""Deleghe del pannello Super Admin, protezione delle impostazioni email e prezzo carburante a zero."""
import json
import ssl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def panel(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('ALLOW_SQLITE_LEGACY', 'true')
    from app.database import Base, get_db
    from app.models import SuperAdminCollaborator
    from app.core.dependencies import require_superadmin
    from app.routers import admin_profile
    monkeypatch.setattr(admin_profile, 'send_superadmin_collaborator_invitation', lambda *a, **k: True)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        delegate = SuperAdminCollaborator(full_name='Delegato', email='delegato@example.test', password_hash='x',
                                          permissions_json=json.dumps({'manage_collaborators': True, 'view_tickets': True,
                                                                       'manage_platform': True}))
        helper = SuperAdminCollaborator(full_name='Assistenza', email='assistenza@example.test', password_hash='x',
                                        permissions_json=json.dumps({'view_tickets': True}))
        backups = SuperAdminCollaborator(full_name='Backup', email='backup@example.test', password_hash='x',
                                         permissions_json=json.dumps({'download_backups': True}))
        db.add_all([delegate, helper, backups]); db.commit()
        actor = {'role': 'collaborator', 'collaborator_id': delegate.id, 'username': delegate.email,
                 'permissions': json.loads(delegate.permissions_json)}
        app = FastAPI(); app.include_router(admin_profile.router)

        def session():
            try:
                yield db
            finally:
                db.rollback()
        app.dependency_overrides[get_db] = session
        app.dependency_overrides[require_superadmin] = lambda: actor
        with TestClient(app) as client:
            yield client, actor, delegate, helper, backups


def update(client, target, permissions):
    return client.put(f'/api/admin/collaborators/{target.id}', json={'full_name': target.full_name, 'permissions': permissions})


def test_delegate_cannot_escalate_privileges(panel):
    client, actor, delegate, helper, backups = panel
    # Non può darsi permessi da solo, né modificare il proprio account.
    assert update(client, delegate, {'manage_collaborators': True, 'download_backups': True}).status_code == 403
    # Non può assegnare permessi riservati al titolare o che non possiede.
    assert update(client, helper, {'view_tickets': True, 'download_backups': True}).status_code == 403
    assert update(client, helper, {'view_tickets': True, 'manage_service_keys': True}).status_code == 403
    assert update(client, helper, {'view_tickets': True, 'view_errors': True}).status_code == 403
    created = client.post('/api/admin/collaborators', json={'full_name': 'Nuovo', 'email': 'nuovo@example.test',
                                                            'permissions': {'manage_collaborators': True}})
    assert created.status_code == 403
    # Non può prendere il controllo di chi ha già permessi sensibili (password, modifica, eliminazione).
    assert client.post(f'/api/admin/collaborators/{backups.id}/resend').status_code == 403
    assert update(client, backups, {}).status_code == 403
    assert client.delete(f'/api/admin/collaborators/{backups.id}').status_code == 403
    # Resta possibile delegare i permessi ordinari che possiede.
    assert update(client, helper, {'view_tickets': True}).status_code == 200


def test_owner_keeps_full_control(panel):
    client, actor, delegate, helper, backups = panel
    actor.clear(); actor.update({'role': 'superadmin', 'username': 'owner', 'permissions': {'all': True}})
    assert update(client, helper, {'download_backups': True, 'manage_service_keys': True}).status_code == 200
    assert update(client, delegate, {'manage_collaborators': True}).status_code == 200


def test_email_server_requires_service_keys_permission(panel, monkeypatch):
    client, actor, *_ = panel
    from app.services import email
    current = {'host': 'smtp.ionos.it', 'port': 587, 'user': 'info@example.test', 'password': 'segreta',
               'from': 'info@example.test', 'from_name': 'GiroFacile'}
    monkeypatch.setattr(email, 'smtp_config', lambda: dict(current))
    same = {'platform_name': 'GiroFacile', 'smtp_host': 'smtp.ionos.it', 'smtp_port': '587', 'smtp_user': 'info@example.test',
            'smtp_from': 'info@example.test', 'smtp_from_name': 'GiroFacile'}
    # Salvare le altre impostazioni con i campi email invariati resta permesso.
    assert client.put('/api/admin/platform-settings', json=same).status_code == 200
    # Cambiare server o mittente richiede il permesso sulle chiavi; anche l'invio di prova.
    assert client.put('/api/admin/platform-settings', json={**same, 'smtp_host': 'smtp.altro.test'}).status_code == 403
    assert client.put('/api/admin/platform-settings', json={**same, 'smtp_from_name': 'Altro'}).status_code == 403
    assert client.post('/api/admin/platform-settings/test-email', json={'to': 'a@example.test'}).status_code == 403


def test_smtp_verifies_server_certificate(monkeypatch):
    from app.services import email
    seen = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, context=None): seen['context'] = context
        def login(self, *a): pass
        def sendmail(self, *a): pass
    monkeypatch.setattr(email.smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setattr(email, 'smtp_config', lambda: {'host': 'h', 'port': 587, 'user': 'u@x.test', 'password': 'p',
                                                       'from': 'u@x.test', 'from_name': 'G'})
    assert email._send('a@example.test', 'Prova', '<p>ok</p>')
    context = seen['context']
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_zero_fuel_price_is_kept():
    from app.schemas import RoutePlanIn
    from app.routers.routes import primary_energy_price
    assert primary_energy_price(RoutePlanIn(consegne=[], data_giro="2026-11-18", deposit_id=1, energy_price_primary=0, prezzo_carburante_litro=1.75)) == 0
    assert primary_energy_price(RoutePlanIn(consegne=[], data_giro="2026-11-18", deposit_id=1, prezzo_carburante_litro=1.62)) == 1.62


def test_terms_prices_match_plan_catalog():
    from pathlib import Path
    from app.services.plan_catalog import PLAN_PRICES
    terms = (Path(__file__).resolve().parents[1] / 'static/legal/termini-condizioni.html').read_text(encoding='utf-8')
    for plan in PLAN_PRICES.values():
        assert f"<td>{plan['name']}</td><td>{plan['price_eur']} € al mese</td>" in terms
    assert 'IVA' not in terms.split('<h2>5.')[1].split('<h2>7.')[0]


@pytest.mark.parametrize('value', ['false', 'true', 'False', '0', '1', 1, 0, None, [], {}])
def test_non_boolean_permissions_are_rejected_before_saving(panel, value):
    client, actor, delegate, helper, backups = panel
    created = client.post('/api/admin/collaborators', json={
        'full_name': 'Nuovo', 'email': 'nuovo@example.test',
        'permissions': {'download_backups': value, 'manage_service_keys': value}})
    assert created.status_code == 422
    assert update(client, helper, {'view_tickets': True, 'download_backups': value}).status_code == 422


def test_saved_permissions_match_what_was_checked(panel):
    client, actor, delegate, helper, backups = panel
    from app.routers.admin_helpers import clean_permissions
    assert clean_permissions({'download_backups': False, 'view_tickets': True})['download_backups'] is False
    created = client.post('/api/admin/collaborators', json={
        'full_name': 'Nuovo', 'email': 'nuovo2@example.test', 'permissions': {'view_tickets': True, 'download_backups': False}})
    assert created.status_code == 200
    perms = created.json()['permissions']
    assert perms['view_tickets'] is True and not any(perms[key] for key in perms if key != 'view_tickets')
