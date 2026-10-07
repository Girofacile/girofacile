from datetime import datetime

import pytest

from test_agents_feature import env


def setup(env):
    from app.models import Vehicle
    from app.routers import vehicles_drivers as router
    client, db, owner, *_ = env
    client.app.include_router(router.vehicles_router)
    vehicle = Vehicle(user_id=owner.id, nome='Peugeot', targa='AB123CD',
                      lookup_provider='openapi', lookup_at=datetime(2025, 1, 2, 10))
    db.add(vehicle)
    db.commit()
    return client, db, vehicle, router


def test_capacity_edit_preserves_original_lookup_date_and_provider(env):
    client, db, vehicle, _ = setup(env)
    original = vehicle.lookup_at
    response = client.put(f'/api/vehicles/{vehicle.id}', json={
        'nome': vehicle.nome, 'targa': vehicle.targa, 'lookup_provider': 'openapi',
        'capacita_colli': 150, 'lookup_at': '2030-01-01T00:00:00',
    })
    assert response.status_code == 200
    db.refresh(vehicle)
    assert vehicle.lookup_at == original
    assert vehicle.capacita_colli == 150
    assert vehicle.lookup_provider == 'openapi'


def test_internal_registry_lookup_preserves_verification_date(env, monkeypatch):
    client, db, vehicle, router = setup(env)
    monkeypatch.setattr(router, 'lookup_vehicle_by_plate', lambda _: pytest.fail('Unexpected provider request'))
    result = client.get(f'/api/vehicles/lookup-plate/{vehicle.targa}').json()
    assert result['lookup_at'] == vehicle.lookup_at.isoformat()
    response = client.put(f'/api/vehicles/{vehicle.id}', json={
        'nome': vehicle.nome, 'targa': vehicle.targa, 'lookup_provider': result['provider'],
        'lookup_at': result['lookup_at'], 'lookup_token': result['lookup_token'],
    })
    assert response.status_code == 200
    assert response.json()['lookup_at'] == result['lookup_at']


@pytest.mark.parametrize('operation', ['create', 'update'])
def test_actual_lookup_timestamp_survives_save_retry_and_edit(env, monkeypatch, operation):
    client, db, vehicle, router = setup(env)
    monkeypatch.setattr(router, 'lookup_vehicle_by_plate', lambda plate: {
        'targa': plate, 'provider': 'test-provider', 'manual_required': False, 'marca': 'Peugeot'})
    result = client.get('/api/vehicles/lookup-plate/EF456GH').json()
    payload = dict(nome='Nuovo mezzo', targa='EF456GH', lookup_provider=result['provider'],
                   lookup_at=result['lookup_at'], lookup_token=result['lookup_token'])
    created = (client.post('/api/vehicles', json=payload) if operation == 'create' else
               client.put(f'/api/vehicles/{vehicle.id}', json=payload))
    assert created.status_code == 200
    assert created.json()['lookup_at'] == result['lookup_at']
    path = f"/api/vehicles/{created.json()['id']}"
    assert client.put(path, json=payload).json()['lookup_at'] == result['lookup_at']
    payload.pop('lookup_token')
    payload['capacita_colli'] = 180
    assert client.put(path, json=payload).json()['lookup_at'] == result['lookup_at']


@pytest.mark.parametrize('change', ['date', 'plate', 'provider', 'company'])
def test_lookup_receipt_cannot_be_reused_for_other_verifications(env, change):
    from app.services.vehicle_lookup_receipt import lookup_receipt
    client, db, vehicle, _ = setup(env)
    payload = dict(nome=vehicle.nome, targa=vehicle.targa, lookup_provider='openapi',
                   **lookup_receipt(vehicle.user_id + (1 if change == 'company' else 0),
                                    vehicle.targa, 'openapi'))
    payload.update({'lookup_at': '2030-01-01T00:00:00'} if change == 'date' else
                   {'targa': 'EF456GH'} if change == 'plate' else
                   {'lookup_provider': 'other'} if change == 'provider' else {})
    assert client.put(f'/api/vehicles/{vehicle.id}', json=payload).status_code == 400


def test_manual_plate_change_clears_old_verification(env):
    client, db, vehicle, _ = setup(env)
    response = client.put(f'/api/vehicles/{vehicle.id}', json={
        'nome': vehicle.nome, 'targa': 'EF456GH', 'lookup_provider': 'openapi'})
    assert response.status_code == 200
    assert response.json()['lookup_at'] is None
    assert response.json()['lookup_provider'] is None


def test_manual_lookup_does_not_issue_a_verification_date(env, monkeypatch):
    client, db, vehicle, router = setup(env)
    monkeypatch.setattr(router, 'lookup_vehicle_by_plate', lambda plate: {
        'targa': plate, 'provider': 'free', 'manual_required': True})
    result = client.get('/api/vehicles/lookup-plate/EF456GH').json()
    assert 'lookup_token' not in result and 'lookup_at' not in result
