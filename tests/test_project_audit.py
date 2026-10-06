"""Regression cases found during the 7 October project audit."""
from datetime import timedelta, time

import pytest

from test_agents_feature import env
from test_stability import seed_route


@pytest.mark.parametrize('endpoint,payload', [
    ('deposits', {'indirizzo': 'Via Roma'}),
    ('customers', {'indirizzo': 'Via Roma'}),
    ('vehicles', {}),
    ('agents', {}),
])
@pytest.mark.parametrize('name', [None, '', '   '])
def test_invalid_registry_names_return_validation_error(env, endpoint, payload, name):
    from app.routers import deposits, vehicles_drivers
    client, db, owner, *_ = env
    owner.agents_enabled = True
    db.commit()
    client.app.include_router(deposits.router)
    client.app.include_router(vehicles_drivers.vehicles_router)
    response = client.post('/api/' + endpoint, json={**payload, 'nome': name})
    assert response.status_code == 422


def test_customer_address_and_time_windows_can_be_updated_together(env):
    client, db, owner, other, seller, foreign, customer, *_ = env
    response = client.put(f'/api/customers/{customer.id}', json={
        'nome': customer.nome, 'indirizzo': 'Via Nuova 25',
        'scarico_mattina_da': '09:00', 'scarico_mattina_a': '12:00',
    })
    assert response.status_code == 200
    db.refresh(customer)
    assert customer.indirizzo == 'Via Nuova 25'
    assert customer.scarico_mattina_da == time(9)


def test_running_route_from_yesterday_keeps_resources_busy(env):
    from app.models import Vehicle
    from app.core.utils import local_today
    from app.routers.vehicles_drivers import driver_status, vehicle_status
    client, db, *_ = env
    route, delivery, account = seed_route(env)
    route.vehicle = Vehicle(user_id=route.user_id, nome='Mezzo audit')
    route.status = 'in_corso'
    route.data_giro = local_today() - timedelta(days=1)
    db.commit()
    assert driver_status(route.driver, db) == 'In servizio'
    assert vehicle_status(route.vehicle, db) == 'In uso'


def test_vehicle_technical_details_survive_save_and_reload(env):
    from app.routers.vehicles_drivers import vehicles_router
    client, db, *_ = env
    client.app.include_router(vehicles_router)
    details = dict(marca='Fiat', modello='Ducato', anno_immatricolazione=2020,
                   cilindrata_cc=2287, potenza_kw=103, classe_euro='Euro 6',
                   carrozzeria='Furgone', lookup_provider='manual')
    response = client.post('/api/vehicles', json={'nome': 'Furgone audit', **details})
    assert response.status_code == 200
    db.expire_all()
    saved = client.get('/api/vehicles').json()[0]
    for key, value in details.items():
        assert saved[key] == value
    assert saved['lookup_at']


@pytest.mark.parametrize('portal', ['company', 'agent'])
@pytest.mark.parametrize('changed', [True, False])
def test_import_changed_address_clears_old_verified_coordinates(env, portal, changed):
    from app.routers import agent
    client, db, owner, other, seller, foreign, customer, account, *_ = env
    owner.agents_enabled = True
    customer.lat, customer.lon = 45.0, 9.0
    customer.stato_geocodifica = 'verificato'
    customer.indirizzo_geocodificato = 'Vecchio indirizzo'
    db.commit()
    client.app.dependency_overrides[agent.get_current_agent] = lambda: account
    path = '/api/customers/import' if portal == 'company' else '/api/agent/customers/import'
    address = 'Via Nuova 99' if changed else customer.indirizzo
    csv = f'codice_cliente,nome,indirizzo\nC1,Esistente,{address}\n'
    response = client.post(path, files={'file': ('clienti.csv', csv, 'text/csv')})
    assert response.status_code == 200
    db.refresh(customer)
    assert customer.indirizzo == address
    if changed:
        assert customer.lat is None and customer.lon is None
        assert customer.stato_geocodifica == 'da_verificare'
    else:
        assert (customer.lat, customer.lon) == (45.0, 9.0)
        assert customer.stato_geocodifica == 'verificato'
