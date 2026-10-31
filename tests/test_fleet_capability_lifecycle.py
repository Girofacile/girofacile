"""Required tail lifts remain valid through preview, save and programming.

Only isolated account/routing fixture plumbing is reused. The stops and
capability changes are new; all road and traffic providers remain frozen.
"""
from copy import deepcopy

import pytest

from app.fleet_models import FleetPlan
from app.models import RoutePlan, Vehicle
from stop_fixture import verified_stop
from test_agents_feature import env
from test_routing_architecture import routing_env
from test_fleet_planning import fleet, preview, command


@pytest.fixture
def lift_lifecycle(fleet):
    ctx, original = fleet
    client, db, owner = ctx[:3]
    owner.needs_tail_lift = True
    payload = deepcopy(original)
    payload.update(nome='Compatibilità sponda nel ciclo operativo', strategy='balanced')
    payload['consegne'] = [
        verified_stop(owner.id, cliente_nome='Magazzino Faro audit',
            indirizzo='Via Faro audit 31', lat=45.131, lon=9.131,
            peso_kg=4, colli=1, tempo_scarico_min=3, sponda=True),
        verified_stop(owner.id, cliente_nome='Deposito Cedro audit',
            indirizzo='Via Cedro audit 47', lat=45.147, lon=9.147,
            peso_kg=6, colli=2, tempo_scarico_min=4, sponda=True),
    ]
    for resource in payload['resources']:
        db.get(Vehicle, resource['vehicle_id']).ha_sponda = True
    db.commit()
    return fleet, payload


def _lose_selected_lift(fixture, plan):
    fleet_fixture, payload = fixture
    db = fleet_fixture[0][1]
    selected = plan['routes'][0]['resource']
    vehicle = db.get(Vehicle, payload['resources'][selected]['vehicle_id'])
    vehicle.ha_sponda = False
    db.commit()
    return vehicle


def test_automatic_preview_cannot_be_saved_after_selected_vehicle_loses_lift(lift_lifecycle):
    fixture, payload = lift_lifecycle
    plan = preview(fixture, payload)
    assert plan['search']['tail_lift_required'] is True
    assert plan['unassigned'] == []
    _lose_selected_lift(lift_lifecycle, plan)

    rejected = command(fixture, plan, 'confirm')
    assert rejected.status_code == 422, rejected.text
    assert 'sponda' in rejected.json()['detail'].lower()
    db = fixture[0][1]
    assert db.query(RoutePlan).count() == 0
    db.expire_all()
    persisted = db.get(FleetPlan, plan['id'])
    assert persisted.status == 'preview' and persisted.route_ids == []


def test_saved_automatic_plan_cannot_be_programmed_after_lift_is_removed(lift_lifecycle):
    fixture, payload = lift_lifecycle
    plan = preview(fixture, payload)
    saved_response = command(fixture, plan, 'confirm')
    assert saved_response.status_code == 200, saved_response.text
    saved = saved_response.json()
    assert saved['route_ids']
    _lose_selected_lift(lift_lifecycle, plan)

    rejected = command(fixture, saved, 'program')
    assert rejected.status_code == 422, rejected.text
    assert 'sponda' in rejected.json()['detail'].lower()
    db = fixture[0][1]
    db.expire_all()
    assert db.query(RoutePlan).filter(RoutePlan.status == 'programmato').count() == 0
    assert all(db.get(RoutePlan, route_id).status != 'programmato' for route_id in saved['route_ids'])


def test_manual_revision_keeps_explicit_incompatible_choice_with_warning(lift_lifecycle):
    fixture, payload = lift_lifecycle
    client, db = fixture[0][:2]
    plan = preview(fixture, payload)
    target = 1
    db.get(Vehicle, payload['resources'][target]['vehicle_id']).ha_sponda = False
    db.commit()

    response = command(fixture, plan, 'revise', assignments=[target, target])
    assert response.status_code == 200, response.text
    revised = response.json()
    assert revised['search'].get('tail_lift_required', False) is False
    assert revised['search']['method'] == 'manual-membership'
    assert revised['unassigned'] == []
    assert {route['resource'] for route in revised['routes']} == {target}
    assert any('sponda' in warning.lower() for warning in revised['warnings'])

    saved = command(fixture, revised, 'confirm')
    assert saved.status_code == 200, saved.text
    programmed = command(fixture, saved.json(), 'program')
    assert programmed.status_code == 200, programmed.text
    assert any('sponda' in warning.lower() for warning in programmed.json()['warnings'])
    assert all(route.status == 'programmato' for route in db.query(RoutePlan))


def test_historical_soft_policy_remains_readable_and_programmable(lift_lifecycle):
    fixture, payload = lift_lifecycle
    client, db = fixture[0][:2]
    plan = preview(fixture, payload)
    persisted = db.get(FleetPlan, plan['id'])
    old_result = deepcopy(persisted.result)
    old_result['search'].pop('tail_lift_required', None)
    old_result['search']['equipment_policy'] = 'prefer-compatible-with-warning-fallback'
    persisted.result = old_result
    db.commit()
    _lose_selected_lift(lift_lifecycle, plan)

    response = client.get(f"/api/fleet-planning/{plan['id']}")
    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored['id'] == plan['id']
    assert not restored['search'].get('tail_lift_required', False)
    assert restored['routes']

    saved = command(fixture, restored, 'confirm')
    assert saved.status_code == 200, saved.text
    programmed = command(fixture, saved.json(), 'program')
    assert programmed.status_code == 200, programmed.text
    assert any('sponda' in warning.lower() for warning in programmed.json()['warnings'])
