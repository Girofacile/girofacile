"""Tail-lift warnings preserve deliveries through preview, save and programming.

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


def test_automatic_preview_can_be_saved_after_selected_vehicle_loses_lift(lift_lifecycle):
    fixture, payload = lift_lifecycle
    plan = preview(fixture, payload)
    assert plan['search'].get('tail_lift_required', False) is False
    assert plan['unassigned'] == []
    _lose_selected_lift(lift_lifecycle, plan)

    saved = command(fixture, plan, 'confirm')
    assert saved.status_code == 200, saved.text
    assert any('richiede la sponda' in warning.lower() for warning in saved.json()['warnings'])
    db = fixture[0][1]
    assert sum(len(route.deliveries) for route in db.query(RoutePlan)) == 2
    db.expire_all()
    persisted = db.get(FleetPlan, plan['id'])
    assert persisted.status == 'saved' and persisted.route_ids


def test_saved_automatic_plan_can_be_programmed_with_warning_after_lift_is_removed(lift_lifecycle):
    fixture, payload = lift_lifecycle
    plan = preview(fixture, payload)
    saved_response = command(fixture, plan, 'confirm')
    assert saved_response.status_code == 200, saved_response.text
    saved = saved_response.json()
    assert saved['route_ids']
    _lose_selected_lift(lift_lifecycle, plan)

    programmed = command(fixture, saved, 'program')
    assert programmed.status_code == 200, programmed.text
    assert any('richiede la sponda' in warning.lower() for warning in programmed.json()['warnings'])
    db = fixture[0][1]
    db.expire_all()
    assert all(db.get(RoutePlan, route_id).status == 'programmato' for route_id in saved['route_ids'])
    assert any(delivery.sponda and 'sponda' in (delivery.warning or '').lower()
               for route in db.query(RoutePlan) for delivery in route.deliveries)


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


@pytest.mark.parametrize('previously_strict', [False, True])
def test_saved_policy_marker_cannot_reintroduce_a_tail_lift_block(lift_lifecycle, previously_strict):
    fixture, payload = lift_lifecycle
    client, db = fixture[0][:2]
    plan = preview(fixture, payload)
    persisted = db.get(FleetPlan, plan['id'])
    old_result = deepcopy(persisted.result)
    old_result['search']['tail_lift_required'] = previously_strict
    old_result['search']['equipment_policy'] = (
        'tail-lift-required-ztl-warning-fallback' if previously_strict
        else 'prefer-compatible-with-warning-fallback')
    persisted.result = old_result
    db.commit()
    _lose_selected_lift(lift_lifecycle, plan)

    response = client.get(f"/api/fleet-planning/{plan['id']}")
    assert response.status_code == 200, response.text
    restored = response.json()
    assert restored['id'] == plan['id']
    assert restored['routes']

    saved = command(fixture, restored, 'confirm')
    assert saved.status_code == 200, saved.text
    programmed = command(fixture, saved.json(), 'program')
    assert programmed.status_code == 200, programmed.text
    assert any('sponda' in warning.lower() for warning in programmed.json()['warnings'])
    assert sum(len(route.deliveries) for route in db.query(RoutePlan)) == 2
    assert all(route.status == 'programmato' for route in db.query(RoutePlan))
    assert any(delivery.sponda and 'sponda' in (delivery.warning or '').lower()
               for route in db.query(RoutePlan) for delivery in route.deliveries)
