"""Doppio passaggio Mapbox: con il traffico il giro viene riordinato per rientrare nelle fasce."""
from copy import deepcopy

import requests

from test_routing_architecture import routing_env, payload, Response  # noqa: F401
from test_agents_feature import env  # noqa: F401
from test_fleet_planning import fleet, preview  # noqa: F401
from stop_fixture import verified_stop
from app import optimizer as opt
from app.services import traffic_correction
from app.services.road_routing import RoadMatrix


def test_factor_and_lateness_order():
    assert traffic_correction.travel_factor([10, 10], [1200, 1200]) == 2
    assert traffic_correction.travel_factor([10, 10], [500, 500]) is None  # traffico più veloce: nessuna correzione
    assert traffic_correction.travel_factor([1], [100000]) == traffic_correction.MAX_FACTOR
    assert traffic_correction.lateness([{'lateness_min': 3}]) < traffic_correction.lateness([{'lateness_min': 1}, {'lateness_min': 1}])


def stops(owner_id):
    """A e B senza fascia, C chiude alle 8:55: il giro più corto mette C per ultimo."""
    return [verified_stop(owner_id, cliente_nome=name, indirizzo=f'Via {name}', lat=45.1 + i / 100, lon=9.1,
                          tempo_scarico_min=5, **window)
            for i, (name, window) in enumerate([('A', {}), ('B', {}),
                                                ('C', {'scarico_mattina_da': '08:00', 'scarico_mattina_a': '08:55'})])]


def setup_roads(monkeypatch):
    """10 minuti per tratta. Raggiungere C dal deposito e ripartire da C verso A o B costa
    10 km: il giro più corto finisce con C. Mapbox (traffico): 20 minuti per tratta.
    Restituisce le chiamate a Mapbox."""
    def matrix(db, user_id, points, keys, **kwargs):
        legs = {(i, j): {'km': 1.0, 'min': 10.0} for i in range(len(points)) for j in range(len(points)) if i != j}
        for key in ((0, 3), (3, 1), (3, 2)):
            legs[key] = {'km': 10.0, 'min': 10.0}
        return RoadMatrix(legs, source='osrm')
    monkeypatch.setattr(opt, 'build_distance_matrix', matrix)
    mapbox = []
    original = requests.get
    def get(url, params=None, **kwargs):
        if 'api.mapbox.com' in url:
            count = len(url.rsplit('/', 1)[-1].split(';')) - 1
            mapbox.append(url)
            return Response({'code': 'Ok', 'routes': [{'geometry': '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
                                                       'legs': [{'duration': 1200, 'distance': 1000} for _ in range(count)]}]})
        return original(url, params=params, **kwargs)
    monkeypatch.setattr(requests, 'get', get)
    return mapbox


def test_single_route_is_reordered_with_traffic(routing_env, monkeypatch):  # noqa: F811
    client, _, owner, *_ = routing_env
    mapbox = setup_roads(monkeypatch)
    data = payload(routing_env)
    data['consegne'] = stops(owner.id)
    response = client.post('/api/routes/optimize', json=data)
    assert response.status_code == 200, response.text
    route = response.json()
    # Senza traffico C sarebbe l'ultima (arrivo 9:10 con il traffico, chiusura 8:55).
    assert [stop['cliente_nome'] for stop in route['consegne']][-1] != 'C'
    assert route['eta_type'] == 'traffic' and len(mapbox) == 2
    assert not any(stop.get('time_window_violation') for stop in route['consegne'])


def test_single_route_without_lateness_calls_mapbox_once(routing_env, monkeypatch):  # noqa: F811
    client, _, owner, *_ = routing_env
    mapbox = setup_roads(monkeypatch)
    data = payload(routing_env)
    data['consegne'] = [stop for stop in stops(owner.id) if stop['cliente_nome'] != 'C']
    response = client.post('/api/routes/optimize', json=data)
    assert response.status_code == 200, response.text
    assert response.json()['eta_type'] == 'traffic' and len(mapbox) == 1


def test_fleet_route_is_reordered_with_traffic(fleet, monkeypatch):  # noqa: F811
    ctx, data = fleet
    mapbox = setup_roads(monkeypatch)
    data = deepcopy(data)
    data.update(strategy='efficient', consegne=stops(ctx[2].id))
    plan = preview(fleet, data)
    [route] = plan['routes']
    report = route['traffic']['second_pass']
    assert report['reordered'] and report['late_before'] == 1 and report['late_after'] == 0
    assert route['stop_indexes'][-1] != 2 and route['traffic']['late'] == []
    assert len(mapbox) == 2


def flat_roads(monkeypatch):
    """Tutte le tratte 1 km e 10 minuti; Mapbox (traffico) 20 minuti per tratta."""
    def matrix(db, user_id, points, keys, **kwargs):
        return RoadMatrix({(i, j): {'km': 1.0, 'min': 10.0} for i in range(len(points)) for j in range(len(points)) if i != j},
                          source='osrm')
    monkeypatch.setattr(opt, 'build_distance_matrix', matrix)
    return setup_traffic(monkeypatch)


def setup_traffic(monkeypatch):
    mapbox = []
    original = requests.get
    def get(url, params=None, **kwargs):
        if 'api.mapbox.com' in url:
            count = len(url.rsplit('/', 1)[-1].split(';')) - 1
            mapbox.append(url)
            return Response({'code': 'Ok', 'routes': [{'geometry': '_p~iF~ps|U_ulLnnqC_mqNvxq`@',
                                                       'legs': [{'duration': 1200, 'distance': 1000} for _ in range(count)]}]})
        return original(url, params=params, **kwargs)
    monkeypatch.setattr(requests, 'get', get)
    return mapbox


def same_window(owner_id, closing):
    return [verified_stop(owner_id, cliente_nome=name, indirizzo=f'Via {name}', lat=45.1 + i / 100, lon=9.1, tempo_scarico_min=5,
                          scarico_mattina_da='08:00', scarico_mattina_a=closing) for i, name in enumerate('ABC')]


def test_fleet_replans_across_vehicles_when_reordering_is_not_enough(fleet, monkeypatch):  # noqa: F811
    ctx, data = fleet
    flat_roads(monkeypatch)
    data = deepcopy(data)
    # Un solo mezzo fa meno km, ma con il traffico la terza consegna finisce alle 9:15 (chiusura 9:10).
    data.update(strategy='efficient', consegne=same_window(ctx[2].id, '09:10'))
    plan = preview(fleet, data)
    report = plan['search']['on_time_replan']
    assert report['accepted'] and report['late_before'] == 1 and report['late_after'] == 0
    assert len(plan['routes']) == 2 and plan['unassigned'] == []
    assert all(route['traffic']['late'] == [] for route in plan['routes'])


def test_fleet_keeps_every_delivery_when_replan_would_drop_one(fleet, monkeypatch):  # noqa: F811
    ctx, data = fleet
    flat_roads(monkeypatch)
    data = deepcopy(data)
    # Con il margine ogni mezzo può fare una sola consegna: il nuovo piano ne lascerebbe fuori una.
    data.update(strategy='efficient', consegne=same_window(ctx[2].id, '08:55'))
    plan = preview(fleet, data)
    assert plan['search']['on_time_replan']['accepted'] is False
    assert plan['unassigned'] == [] and sum(len(route['stop_indexes']) for route in plan['routes']) == 3
    assert any('fuori orario' in warning for warning in plan['warnings'])
