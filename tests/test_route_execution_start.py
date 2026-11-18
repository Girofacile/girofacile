"""Every delivery command shares the explicit route start rules."""
from datetime import time, timedelta
import pytest
from test_agents_feature import env
from test_stability import seed_route

COMMANDS = [('driver', a) for a in ('start', 'note', 'complete', 'missed', 'signature')]
COMMANDS += [('operator', a) for a in ('start', 'note', 'complete', 'missed')]


def prepare(env, *, days=0, status='programmato', signature=False):
    from app.core.utils import local_today
    from app.routers import driver, operator
    client, db, owner, *_ = env
    route, delivery, account = seed_route(env)
    route.status, route.data_giro = status, local_today() + timedelta(days=days)
    owner.delivery_signature_enabled = signature
    db.commit()
    client.app.include_router(driver.router)
    client.app.include_router(operator.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    return client, db, owner, route, delivery


def path(portal, action, route, delivery):
    prefix = '/api/driver' if portal == 'driver' else '/api/operator/test-route'
    if action == 'start':
        return f'{prefix}/routes/{route.id}/start' if portal == 'driver' else f'{prefix}/start'
    return f'{prefix}/delivery/{delivery.id}/{action}'


@pytest.mark.parametrize('portal,action', COMMANDS)
@pytest.mark.parametrize('state', ['bozza', 'programmato'])
def test_future_route_cannot_start_through_any_command(env, portal, action, state):
    from app.models import DeliveryStatus, RouteUsage
    client, db, _, route, delivery = prepare(env, days=1, status=state, signature=action == 'signature')
    response = client.post(path(portal, action, route, delivery), json={'note': 'Prima della partenza'})
    assert response.status_code == 409, response.text
    assert 'futura' in response.json()['detail']
    assert route.status == state and route.started_at is None
    assert db.query(RouteUsage).count() == db.query(DeliveryStatus).count() == 0


@pytest.mark.parametrize('portal,action', [('driver', 'start'), ('operator', 'start'),
    ('driver', 'note'), ('operator', 'note'), ('driver', 'complete'), ('operator', 'missed')])
@pytest.mark.parametrize('resource', ['driver', 'vehicle'])
def test_running_resource_blocks_explicit_and_delivery_starts(env, portal, action, resource):
    from app.models import DeliveryStatus, RoutePlan, RouteUsage, Vehicle
    client, db, owner, route, delivery = prepare(env)
    running = RoutePlan(user_id=owner.id, nome='Già in corso', data_giro=route.data_giro,
                        orario_partenza=time(8), status='in_corso')
    if resource == 'driver':
        running.driver_id = route.driver_id
    else:
        vehicle = Vehicle(user_id=owner.id, nome='Mezzo condiviso')
        db.add(vehicle)
        db.flush()
        route.vehicle_id = running.vehicle_id = vehicle.id
    db.add(running)
    db.commit()
    response = client.post(path(portal, action, route, delivery), json={'note': 'Attendere'})
    assert response.status_code == 409, response.text
    assert route.status == 'programmato' and route.started_at is None
    assert running.status == 'in_corso'
    assert db.query(RouteUsage).count() == db.query(DeliveryStatus).count() == 0


@pytest.mark.parametrize('portal', ['driver', 'operator'])
def test_allowed_note_and_repeated_explicit_start_count_once(env, portal):
    from app.models import RouteUsage
    client, db, _, route, delivery = prepare(env)
    assert client.post(path(portal, 'note', route, delivery), json={'note': 'Pronti'}).status_code == 200
    started = route.started_at
    assert route.status == 'in_corso' and started is not None
    assert client.post(path(portal, 'start', route, delivery), json={}).status_code == 200
    assert client.post(path(portal, 'note', route, delivery), json={'note': 'In partenza'}).status_code == 200
    assert route.started_at == started
    assert db.query(RouteUsage).count() == 1


@pytest.mark.parametrize('portal', ['driver', 'operator'])
def test_legacy_running_route_can_close_after_expiry(env, portal):
    from app.models import RouteUsage
    client, db, owner, route, delivery = prepare(env, days=1, status='in_corso')
    owner.plan_status = 'expired'
    db.commit()
    response = client.post(path(portal, 'missed', route, delivery), json={})
    assert response.status_code == 200, response.text
    assert route.status == 'completato'
    assert db.query(RouteUsage).count() == 1


def test_an_older_queued_note_never_overwrites_a_newer_one(env):
    from app.models import DeliveryStatus
    client, db, _, route, delivery = prepare(env)
    note = path('driver', 'note', route, delivery)
    assert client.post(note, json={'note': 'Prima nota', 'scritta_il': '2026-01-10T08:00:00Z'}).status_code == 200
    assert client.post(note, json={'note': 'Nota corretta', 'scritta_il': '2026-01-10T08:05:00Z'}).status_code == 200
    # La coda del telefono rimanda la prima nota (reinvio dopo la riapertura): non cambia nulla.
    for repeated in ({'note': 'Prima nota', 'scritta_il': '2026-01-10T08:00:00Z'},
                     {'note': 'Nota corretta', 'scritta_il': '2026-01-10T08:05:00Z'}):
        assert client.post(note, json=repeated).status_code == 200
    status = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    db.refresh(status)
    assert status.note_operatore == 'Nota corretta'
    # Una nota senza ora (per esempio dall'ufficio) arriva adesso ed è la più recente.
    assert client.post(note, json={'note': 'Aggiornata ora'}).status_code == 200
    db.refresh(status)
    assert status.note_operatore == 'Aggiornata ora'


@pytest.mark.parametrize('action', ['missed', 'complete'])
def test_an_outcome_written_earlier_keeps_the_newer_note(env, action):
    from app.models import DeliveryStatus
    client, db, _, route, delivery = prepare(env)
    note = path('driver', 'note', route, delivery)
    assert client.post(note, json={'note': 'Citofono rotto, chiamare', 'scritta_il': '2026-01-10T09:00:00Z'}).status_code == 200
    # L'esito era stato scritto alle 8:50 senza rete ed è arrivato dopo dalla coda del telefono.
    body = {'note': 'Bozza', 'scritta_il': '2026-01-10T08:50:00Z', 'motivo': 'assente', 'tempo_scarico': 5}
    assert client.post(path('driver', action, route, delivery), json=body).status_code == 200
    # Lo stesso esito ripetuto dalla coda non ha altri effetti.
    assert client.post(path('driver', action, route, delivery), json=body).status_code == 200
    status = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    db.refresh(status)
    assert status.status == ('mancata' if action == 'missed' else 'completata')
    assert status.note_operatore == 'Citofono rotto, chiamare'


def test_an_accepted_note_sent_again_after_the_route_closed_is_confirmed(env):
    from app.models import DeliveryStatus
    client, db, _, route, delivery = prepare(env)
    note = {'note': 'Lasciato al bar accanto', 'scritta_il': '2026-01-10T08:00:00Z'}
    assert client.post(path('driver', 'note', route, delivery), json=note).status_code == 200
    assert client.post(path('driver', 'complete', route, delivery), json={'tempo_scarico': 5, 'note': note['note'],
                                                                            'scritta_il': '2026-01-10T08:01:00Z'}).status_code == 200
    db.refresh(route)
    assert route.status == 'completato'
    # La vecchia coda rimanda la nota già accettata: confermata senza errori e senza effetti.
    response = client.post(path('driver', 'note', route, delivery), json=note)
    assert response.status_code == 200, response.text
    # Una nota davvero nuova su un giro chiuso resta rifiutata.
    assert client.post(path('driver', 'note', route, delivery), json={'note': 'Altro', 'scritta_il': '2026-01-10T09:00:00Z'}).status_code == 409


def test_an_offline_note_beats_a_saved_note_whose_time_is_unknown(env):
    from app.models import DeliveryStatus
    client, db, _, route, delivery = prepare(env)
    assert client.post(path('driver', 'note', route, delivery), json={'note': 'Prima versione'}).status_code == 200
    status = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    status.note_scritta_il = None  # nota salvata prima che esistesse l'ora di scrittura
    db.commit()
    # Modifica scritta offline e rimasta nella coda del telefono: più recente di quella salvata.
    body = {'note': 'Versione corretta offline', 'scritta_il': '2026-01-10T08:00:00Z'}
    assert client.post(path('driver', 'note', route, delivery), json=body).status_code == 200
    db.refresh(status)
    assert status.note_operatore == 'Versione corretta offline'
    # Ripetuta, non cambia nulla; una mancata senza nota non la cancella.
    assert client.post(path('driver', 'note', route, delivery), json=body).status_code == 200
    assert client.post(path('driver', 'missed', route, delivery), json={'motivo': 'chiuso'}).status_code == 200
    db.refresh(status)
    assert status.note_operatore == 'Versione corretta offline' and status.status == 'mancata'
