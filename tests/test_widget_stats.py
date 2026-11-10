"""Widget iPhone: numeri della piattaforma leggibili solo con la chiave dedicata del Super Admin."""
import hashlib

import pytest

from test_agents_feature import env  # noqa: F401

FIELDS = {'aggiornato_alle', 'ticket_aperti', 'ticket_nuovi_oggi', 'aziende_registrate', 'aziende_in_prova',
          'aziende_abbonate', 'nuove_aziende_mese', 'mrr_stimato', 'giri_in_corso', 'giri_oggi', 'errori_24h'}


@pytest.fixture
def widget_client(env):  # noqa: F811
    from app.routers import admin, admin_widget
    from app.core.config import SUPERADMIN_USERNAME
    from app.core.security import make_superadmin_token
    client, db, *_ = env
    client.app.include_router(admin.router)
    client.app.include_router(admin_widget.router)
    admin_widget._requests.clear()
    client.cookies.set("superadmin_session", make_superadmin_token(SUPERADMIN_USERNAME))
    return client, db


def stats(client, key=None):
    headers = {'Authorization': f'Bearer {key}'} if key else {}
    return client.get('/api/widget/stats', headers=headers)


def test_stats_need_the_widget_key(widget_client):
    client, db = widget_client
    assert stats(client).status_code == 401
    assert stats(client, 'gfw_inventata').status_code == 401
    assert client.get('/api/admin/widget-key').json()['configured'] is False

    created = client.post('/api/admin/widget-key')
    assert created.status_code == 200, created.text
    key = created.json()['key']
    assert key.startswith('gfw_') and len(key) > 30

    response = stats(client, key)
    assert response.status_code == 200, response.text
    assert set(response.json()) == FIELDS
    assert response.headers['cache-control'] == 'no-store'
    assert stats(client, key[:-1] + ('a' if key[-1] != 'a' else 'b')).status_code == 401

    # Nel database c'è solo l'impronta della chiave, mai la chiave in chiaro.
    from app.models import SaaSPlatformSetting
    stored = {row.key: row.value for row in db.query(SaaSPlatformSetting).all()}
    assert key not in stored.values()
    assert stored['widget_key_sha256'] == hashlib.sha256(key.encode()).hexdigest()
    state = client.get('/api/admin/widget-key').json()
    assert state['configured'] is True and state['last_used_at'] and 'key' not in state


def test_new_key_replaces_the_old_and_revoke_stops_it(widget_client):
    client, _ = widget_client
    old = client.post('/api/admin/widget-key').json()['key']
    new = client.post('/api/admin/widget-key').json()['key']
    assert old != new
    assert stats(client, old).status_code == 401
    assert stats(client, new).status_code == 200
    assert client.delete('/api/admin/widget-key').json()['configured'] is False
    assert stats(client, new).status_code == 401


def test_counts_follow_the_data(widget_client):
    client, db = widget_client
    from app.models import SupportTicket
    key = client.post('/api/admin/widget-key').json()['key']
    before = stats(client, key).json()
    db.add(SupportTicket(email='cliente@example.test', oggetto='Aiuto', status='aperto'))
    db.commit()
    after = stats(client, key).json()
    assert after['ticket_aperti'] == before['ticket_aperti'] + 1
    assert after['ticket_nuovi_oggi'] == before['ticket_nuovi_oggi'] + 1


def test_collaborator_without_permission_cannot_manage_the_key(widget_client):
    client, _ = widget_client
    from app.core.dependencies import require_superadmin
    client.app.dependency_overrides[require_superadmin] = lambda: {'role': 'collaborator', 'username': 'aiuto', 'permissions': {'view_server_maintenance': True}}
    try:
        assert client.get('/api/admin/widget-key').status_code == 200
        assert client.post('/api/admin/widget-key').status_code == 403
        assert client.delete('/api/admin/widget-key').status_code == 403
    finally:
        client.app.dependency_overrides.pop(require_superadmin, None)


def test_too_many_reads_are_throttled(widget_client):
    client, _ = widget_client
    for _ in range(60):
        stats(client)
    response = stats(client)
    assert response.status_code == 429 and response.headers['retry-after'] == '60'
