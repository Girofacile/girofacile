"""Manutenzione programmata e avvisi agli utenti (12/11/2026); nessuna chiamata esterna."""
import asyncio
from contextlib import nullcontext
from datetime import datetime

import pytest
from fastapi import HTTPException, Response

from test_agents_feature import env  # noqa: F401


def at(monkeypatch, when):
    from app.services import maintenance
    monkeypatch.setattr(maintenance, 'now_local', lambda: datetime.fromisoformat(when))


def schedule(db, **values):
    from app.services.maintenance import save_admin_settings
    save_admin_settings(db, values); db.commit()


def test_scheduled_window_turns_on_and_off_by_itself(env, monkeypatch):
    from app.services.maintenance import maintenance_state, public_status
    _, db, *_ = env
    at(monkeypatch, '2026-11-12T18:00')
    schedule(db, maintenance_start='2026-11-12T22:00', maintenance_end='2026-11-12T23:30',
             maintenance_message='Aggiorniamo il server.')
    status = public_status(db)
    assert status['maintenance'] is None
    notice = status['notices'][0]
    assert notice['kind'] == 'maintenance' and notice['remind_at'] == '2026-11-12T21:30'
    assert notice['title'] == 'Manutenzione programmata'
    assert notice['text'].startswith('Oggi dalle 22:00 alle 23:30 GiroFacile non sarà utilizzabile')
    assert notice['text'].endswith('Aggiorniamo il server.')
    at(monkeypatch, '2026-11-12T22:00')
    assert maintenance_state(db)['active']
    during = public_status(db)
    assert during['maintenance']['until_label'] == 'oggi alle 23:30' and during['notices'] == []
    at(monkeypatch, '2026-11-12T23:30')
    assert not maintenance_state(db)['active'] and public_status(db)['notices'] == []


def test_notice_can_wait_and_end_now_closes_the_window(env, monkeypatch):
    from app.services.maintenance import maintenance_state, public_status
    _, db, *_ = env
    at(monkeypatch, '2026-11-12T09:00')
    schedule(db, maintenance_start='2026-11-13T22:00', maintenance_end='2026-11-14T01:00',
             maintenance_notice_from='2026-11-13T08:00')
    assert public_status(db)['notices'] == []
    at(monkeypatch, '2026-11-13T08:00')
    assert public_status(db)['notices'][0]['text'].startswith('Oggi dalle 22:00 alle 01:00 di domani GiroFacile')
    at(monkeypatch, '2026-11-13T22:10')
    assert maintenance_state(db)['active']
    schedule(db, end_now=True)
    assert not maintenance_state(db)['active'] and public_status(db) == {'maintenance': None, 'notices': []}


def test_manual_mode_and_free_notice(env, monkeypatch):
    from app.services.maintenance import public_status
    _, db, *_ = env
    schedule(db, notice_text='Da lunedì nuova pagina Report', notice_enabled=True)
    assert [n['text'] for n in public_status(db)['notices']] == ['Da lunedì nuova pagina Report']
    schedule(db, maintenance_mode=True)
    assert public_status(db)['maintenance'] == {'until': None, 'until_label': None, 'message': ''}
    schedule(db, maintenance_mode=False, notice_text='Da lunedì nuova pagina Report', notice_enabled=False)
    assert public_status(db) == {'maintenance': None, 'notices': []}


@pytest.mark.parametrize('values,message', [
    ({'maintenance_start': '2026-11-12T22:00', 'maintenance_end': '2026-11-12T21:00'}, 'dopo l'),
    ({'maintenance_end': '2026-11-12T23:00'}, "Indica anche l'inizio"),
    ({'maintenance_start': 'ieri sera'}, 'Inizio della manutenzione non valido'),
    ({'maintenance_start': '2026-11-12T22:00', 'maintenance_notice_from': '2026-11-12T23:00'}, "prima dell'inizio"),
    ({'notice_enabled': True, 'notice_text': ' '}, "testo dell'avviso"),
])
def test_invalid_settings_are_explained(env, monkeypatch, values, message):
    _, db, *_ = env
    at(monkeypatch, '2026-11-12T18:00')
    with pytest.raises(HTTPException) as exc:
        schedule(db, **values)
    assert exc.value.status_code == 400 and message in exc.value.detail


def test_middleware_blocks_during_window_but_keeps_status_and_admin(env, monkeypatch):
    from starlette.requests import Request
    import app.database as database
    from app.main import platform_maintenance
    _, db, *_ = env
    monkeypatch.setattr(database, 'SessionLocal', lambda: nullcontext(db))
    at(monkeypatch, '2026-11-12T18:00')
    schedule(db, maintenance_start='2026-11-12T22:00', maintenance_end='2026-11-12T23:30')

    async def next_handler(request):
        return Response(status_code=204)

    def request(path):
        return asyncio.run(platform_maintenance(Request({'type': 'http', 'path': path, 'headers': []}), next_handler))

    assert request('/api/routes').status_code == 204
    at(monkeypatch, '2026-11-12T22:30')
    assert request('/api/routes').status_code == 503
    for path in ('/api/public/status', '/api/admin/maintenance', '/dashboard'):
        assert request(path).status_code == 204


def test_public_status_endpoint_has_no_cache(env):
    from app.routers.public_status import router
    client, db, *_ = env
    client.app.include_router(router)
    response = client.get('/api/public/status')
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json() == {'maintenance': None, 'notices': []}
