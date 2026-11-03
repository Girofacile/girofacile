"""Tempo di scarico: tempo a mano, tempo imparato, stima dai colli, 10 minuti."""
from types import SimpleNamespace

import pytest

from test_routing_architecture import routing_env, payload  # noqa: F401
from test_agents_feature import env  # noqa: F401
from test_order_planning import planning, ready, preview  # noqa: F401
from stop_fixture import verified_stop
from app.services import unload_time

COMPANY = SimpleNamespace()  # nessuna formula salvata: valori predefiniti


@pytest.mark.parametrize('packages,minutes', [(3, 5), (10, 7), (20, 9), (40, 14), (100, 29), (500, 30)])
def test_default_formula(packages, minutes):
    assert unload_time.estimate(packages, COMPANY) == minutes


def test_no_packages_means_no_estimate():
    assert unload_time.estimate(0, COMPANY) is None and unload_time.estimate(None, COMPANY) is None


def test_company_formula():
    company = SimpleNamespace(unload_base_min=2, unload_seconds_per_package=30, unload_max_min=20)
    assert unload_time.estimate(10, company) == 7 and unload_time.estimate(100, company) == 20


def test_priority_rules():
    unknown = SimpleNamespace(tempo_scarico_min=None, tempo_scarico_rilevazioni=0)
    stop = {'tempo_scarico_min': 10, 'colli': 40}
    unload_time.apply(stop, COMPANY, unknown)
    assert stop == {'tempo_scarico_min': 14, 'colli': 40, 'tempo_scarico_auto': True}
    # Colli cambiati: la stima si aggiorna; senza colli si torna a 10 minuti.
    stop['colli'] = 3
    unload_time.apply(stop, COMPANY, unknown)
    assert stop['tempo_scarico_min'] == 5
    stop['colli'] = 0
    unload_time.apply(stop, COMPANY, unknown)
    assert stop['tempo_scarico_min'] == 10 and stop['tempo_scarico_auto'] is False
    # Tempo scritto a mano sulla fermata: resta.
    manual = {'tempo_scarico_min': 12, 'colli': 40}
    unload_time.apply(manual, COMPANY, unknown)
    assert manual['tempo_scarico_min'] == 12
    # Cliente con misure reali o tempo scelto a mano: resta il suo tempo.
    for customer in (SimpleNamespace(tempo_scarico_min=10, tempo_scarico_rilevazioni=6),
                     SimpleNamespace(tempo_scarico_min=8, tempo_scarico_rilevazioni=0)):
        known = {'tempo_scarico_min': customer.tempo_scarico_min, 'colli': 40}
        unload_time.apply(known, COMPANY, customer)
        assert known['tempo_scarico_min'] == customer.tempo_scarico_min and 'tempo_scarico_auto' not in known


def test_company_profile_saves_formula(routing_env):  # noqa: F811
    from app.routers import auth
    client = routing_env[0]
    client.app.include_router(auth.router)
    profile = client.get('/api/company-profile').json()
    assert (profile['unload_base_min'], profile['unload_seconds_per_package'], profile['unload_max_min']) == (4, 15, 30)
    saved = client.put('/api/company-profile', json={'unload_base_min': 2, 'unload_seconds_per_package': 30, 'unload_max_min': 20})
    assert saved.status_code == 200, saved.text
    assert saved.json()['company']['unload_max_min'] == 20
    assert client.put('/api/company-profile', json={'unload_max_min': 0}).status_code == 422
    assert client.put('/api/company-profile', json={'unload_base_min': 'tanti'}).status_code == 422


def test_order_stop_uses_packages(planning):  # noqa: F811
    ctx, _ = planning
    state, _ = preview(planning, [ready(ctx, packages=40, weight_kg=200)])
    stop = state['stops'][0]
    assert stop['tempo_scarico_min'] == 14 and stop['tempo_scarico_auto'] is True


def test_route_estimates_unknown_stop_and_keeps_manual(routing_env):  # noqa: F811
    client, _, owner, *_ = routing_env
    data = payload(routing_env)
    data['consegne'][0]['colli'] = 40  # tempo 20 scelto a mano: resta
    data['consegne'].append(verified_stop(owner.id, cliente_nome='Nuovo', indirizzo='Via Nuova', lat=45.2, lon=9.2, colli=40))
    response = client.post('/api/routes/optimize', json=data)
    assert response.status_code == 200, response.text
    minutes = {stop['cliente_nome']: stop['tempo_scarico_min'] for stop in response.json()['consegne']}
    assert minutes['Nuovo'] == 14
    assert minutes[data['consegne'][0]['cliente_nome']] == 20

@pytest.mark.parametrize('packages', [3, 40])
def test_explicit_manual_ten_minutes_survives_estimation(packages):
    row = {'tempo_scarico_min': 10, 'tempo_scarico_auto': False, 'colli': packages}
    unload_time.apply(row, COMPANY)
    assert row['tempo_scarico_min'] == 10 and row['tempo_scarico_auto'] is False


def test_customer_ten_minutes_is_preserved_without_guessing_provenance():
    customer = SimpleNamespace(tempo_scarico_min=10, tempo_scarico_rilevazioni=0)
    row = {'tempo_scarico_min': 14, 'tempo_scarico_auto': True, 'colli': 40}
    unload_time.apply(row, COMPANY, customer)
    assert row['tempo_scarico_min'] == 10 and row['tempo_scarico_auto'] is False


def test_manual_ten_minutes_survives_api_save_and_manual_recalculation(routing_env):
    client, _, owner, *_ = routing_env
    data = payload(routing_env)
    data['consegne'] = [verified_stop(owner.id, colli=40, tempo_scarico_min=10, tempo_scarico_auto=False)]
    result = client.post('/api/routes/optimize', json=data)
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved['consegne'][0]['tempo_scarico_min'] == 10
    assert saved['consegne'][0]['tempo_scarico_auto'] is False
    fetched = client.get(f"/api/routes/{saved['id']}").json()
    data.update(route_id=saved['id'], consegne=fetched['consegne'])
    data['consegne'][0]['colli'] = 3
    again = client.post('/api/routes/recalculate-manual', json=data)
    assert again.status_code == 200, again.text
    assert again.json()['consegne'][0]['tempo_scarico_min'] == 10
    assert again.json()['consegne'][0]['tempo_scarico_auto'] is False
