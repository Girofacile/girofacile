"""Correzioni dalla revisione del 25/11/2026: permessi dei collaboratori, bozze, «Parti adesso», importazioni."""
import json
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_company_collaborators import company  # noqa: F401  (fixture)
from test_agents_feature import env  # noqa: F401  (fixture)
from test_routing_architecture import routing_env, saved_route  # noqa: F401


def _route(db, owner, **fields):
    from app.models import RoutePlan
    from app.core.utils import local_today
    route = RoutePlan(**{'user_id': owner.id, 'nome': 'Giro', 'status': 'programmato', 'data_giro': local_today(),
                         'orario_partenza': time(8), **fields})
    db.add(route)
    db.commit()
    return route


def test_read_only_collaborator_never_receives_the_operator_link(company):
    from app.models import RouteToken
    client, db, owner, _, _, _, _, login_owner, login_actor = company
    route = _route(db, owner)
    db.add(RouteToken(route_plan_id=route.id, token='segreto-operatore', expires_at=datetime.utcnow() + timedelta(days=1)))
    db.commit()
    login_actor(['routes.read'])
    live = client.get(f'/api/routes/{route.id}/live')
    assert live.status_code == 200, live.text
    assert live.json()['token_attivo'] is None and live.json()['link_operatore'] is None
    assert 'segreto-operatore' not in live.text
    login_actor(['routes.read', 'routes.tracking'])
    assert client.get(f'/api/routes/{route.id}/live').json()['token_attivo'] == 'segreto-operatore'
    login_owner()
    assert client.get(f'/api/routes/{route.id}/live').json()['token_attivo'] == 'segreto-operatore'


def test_driver_messages_need_the_chat_permission(company):
    from app.models import ChatMessage
    client, db, owner, _, _, _, _, login_owner, login_actor = company
    route = _route(db, owner)
    db.add(ChatMessage(route_plan_id=route.id, sender_type='driver', sender_name='Autista', message='Messaggio riservato'))
    db.commit()
    login_actor(['routes.read'])
    row = next(r for r in client.get('/api/routes/operativi').json() if r['id'] == route.id)
    assert row['last_driver_message'] is None and row['unread_driver_messages'] == 0
    login_actor(['routes.read', 'chat.read', 'drivers.read'])
    row = next(r for r in client.get('/api/routes/operativi').json() if r['id'] == route.id)
    assert row['last_driver_message'] == 'Messaggio riservato' and row['unread_driver_messages'] == 1


def test_depart_now_is_allowed_to_collaborators_who_can_program(company):
    from app.services.company_permissions import normalize_permissions
    client, *_, login_actor = company
    login_actor(normalize_permissions(['routes.plan']))
    assert client.post('/api/routes/999/depart-now').status_code == 403
    login_actor(normalize_permissions(['routes.program']))
    assert client.post('/api/routes/999/depart-now').status_code == 404  # superato il controllo dei permessi


def test_draft_cannot_get_an_operator_link_or_start(company):
    from app.services.route_start import ensure_new_route_can_start
    client, db, owner, *_, login_owner, _ = company
    login_owner()
    draft = _route(db, owner, status='bozza')
    response = client.post(f'/api/routes/{draft.id}/generate-token', json={})
    assert response.status_code == 409 and 'Programma' in response.json()['detail']
    with pytest.raises(HTTPException) as blocked:
        ensure_new_route_can_start(db, SimpleNamespace(status='bozza', data_giro=date.today()))
    assert blocked.value.status_code == 409


def test_create_only_import_cannot_overwrite_existing_customers(company):
    from app.models import Customer
    client, db, owner, _, _, first, _, _, login_actor = company
    login_actor(['customers.read', 'customers.create', 'agents.read'])
    changed = b'codice_cliente,nome,indirizzo\nA1,Sovrascritto,Via Cambiata\n'
    response = client.post('/api/customers/import', files={'file': ('c.csv', changed, 'text/csv')})
    assert response.status_code == 403, response.text
    db.refresh(first)
    assert (first.nome, first.indirizzo) == ('Owned', 'Via Uno')
    fresh = b'codice_cliente,nome,indirizzo\nN1,Nuovo,Via Nuova\n'
    assert client.post('/api/customers/import', files={'file': ('c.csv', fresh, 'text/csv')}).json() == {'created': 1, 'updated': 0}
    login_actor(['customers.read', 'customers.create', 'customers.update', 'agents.read'])
    assert client.post('/api/customers/import', files={'file': ('c.csv', changed, 'text/csv')}).json()['updated'] == 1
    assert db.query(Customer).filter_by(user_id=owner.id, codice_cliente='A1').one().nome == 'Sovrascritto'


def test_agent_import_reads_street_number_and_postcode(env):
    from app.routers import agent
    from app.models import Customer
    client, db, owner, other, seller, foreign, customer, account, *_ = env
    owner.agents_enabled = True
    db.commit()
    client.app.dependency_overrides[agent.get_current_agent] = lambda: account
    csv = b'codice_cliente,nome,via,civico,cap,comune,provincia\nV1,Via separata,Via Roma,12,80035,Nola,NA\n'
    response = client.post('/api/agent/customers/import', files={'file': ('c.csv', csv, 'text/csv')})
    assert response.status_code == 200, response.text
    assert response.json()['created'] == 1
    saved = db.query(Customer).filter_by(codice_cliente='V1').one()
    assert (saved.indirizzo, saved.cap, saved.comune) == ('Via Roma 12', '80035', 'Nola')


def test_depart_now_refuses_a_vehicle_already_busy(routing_env, monkeypatch):
    from app.models import RoutePlan
    from app.routers import routes
    from app.services import late_start
    client, db = routing_env[0], routing_env[1]
    draft = saved_route(routing_env, two=True)
    assert client.post(f"/api/routes/{draft['id']}/program", json={}).status_code == 200
    route = db.get(RoutePlan, draft['id'])
    today = date(2099, 1, 15)
    monkeypatch.setattr(routes, 'local_today', lambda: today)
    monkeypatch.setattr(late_start, 'local_now', lambda: datetime.combine(today, time(11, 57)))
    route.orario_partenza = time(8, 0)
    route.data_giro = today
    vehicle_id = route.vehicle_id
    assert vehicle_id, 'il giro di prova deve avere un mezzo'
    # Un altro giro dello stesso mezzo programmato alle 12:00.
    db.add(RoutePlan(user_id=route.user_id, nome='Pomeriggio', status='programmato', data_giro=today,
                     orario_partenza=time(12, 0), totale_minuti=60, vehicle_id=vehicle_id))
    db.commit()
    moved = client.post(f"/api/routes/{route.id}/depart-now")
    assert moved.status_code == 400 and 'Mezzo non disponibile' in moved.json()['detail'], moved.text
    db.expire_all()
    assert db.get(RoutePlan, route.id).orario_partenza == time(8, 0)  # nulla è cambiato
