"""Doppio passaggio Mapbox: con il traffico il giro viene riordinato per rientrare nelle fasce."""
from copy import deepcopy

import requests

from test_routing_architecture import routing_env, payload, Response  # noqa: F401
from test_agents_feature import env  # noqa: F401
from test_fleet_planning import fleet, preview, command  # noqa: F401
from app.models import RoutePlan
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


def test_fleet_uses_real_windows_before_safety_margin(fleet, monkeypatch):  # noqa: F811
    ctx, data = fleet
    flat_roads(monkeypatch)
    data = deepcopy(data)
    # Con il margine ogni mezzo può fare una sola consegna: il nuovo piano ne lascerebbe fuori una.
    data.update(strategy='efficient', consegne=same_window(ctx[2].id, '08:55'))
    plan = preview(fleet, data)
    assert plan['search']['on_time_replan']['accepted'] is True
    assert plan['search']['on_time_replan']['attempts'] == [{'buffer_min': 0, 'late_after': 0, 'overtime_after': 0, 'accepted': True}]
    assert plan['unassigned'] == [] and sum(len(route['stop_indexes']) for route in plan['routes']) == 3
    assert len(plan['routes']) == 2
    assert all(route['traffic']['late'] == [] for route in plan['routes'])


def test_buffer_never_expands_or_mutates_customer_windows():
    for service, closing in ((20, '08:10'), (10, '08:10'), (5, '08:30')):
        row = {'scarico_mattina_da':'08:00','scarico_mattina_a':closing,'tempo_scarico_min':service,
               'scarico_pomeriggio_da':'13:00','scarico_pomeriggio_a':'14:00'}
        original = deepcopy(row)
        adjusted = traffic_correction.buffered(row, 15)
        assert row == original
        assert adjusted['scarico_mattina_a'] <= closing
        assert adjusted['scarico_pomeriggio_a'] == '13:45'
        if service >= 10:
            assert adjusted['scarico_mattina_a'] == closing


def test_fleet_retains_coverage_when_real_windows_are_still_impossible(fleet, monkeypatch):
    ctx, data = fleet
    flat_roads(monkeypatch)
    data = deepcopy(data)
    data.update(strategy='efficient', consegne=same_window(ctx[2].id, '08:40'))
    plan = preview(fleet, data)
    assert not plan['search']['on_time_replan']['accepted']
    assert len(plan['search']['on_time_replan']['attempts']) == 2
    assert plan['unassigned'] == []
    assert sum(len(r['stop_indexes']) for r in plan['routes']) == 3
    assert any(r['traffic']['late'] for r in plan['routes'])


def test_fleet_recovery_does_not_replace_plan_when_traffic_is_unavailable(monkeypatch):
    from app.services import fleet_planning
    original = {'routes':[{'stop_indexes':[0,1], 'traffic':{'status':'updated','late':[{'lateness_min':20}]}}], 'search':{}}
    retry = {'routes':[{'stop_indexes':[0,1], 'traffic':{'status':'unavailable'}}], 'search':{}}
    calls = []
    def distribute(*args):
        calls.append(args)
        return deepcopy(original if len(calls) == 1 else retry)
    monkeypatch.setattr(fleet_planning, '_distribute', distribute)
    result = fleet_planning._distribute_on_time(None,None,None)
    assert result['routes'] == original['routes']
    assert not result['search']['on_time_replan']['accepted']
    assert len(calls) == 3


def test_single_route_restores_best_verified_attempt(monkeypatch):
    from types import SimpleNamespace
    from app.routers import routes
    from app.services import platform_settings, route_enrichment
    plan = SimpleNamespace(id=1, delay=20, traffic_status='updated',
                           routing_snapshot_json={'base_legs':[{'min':10}]},
                           traffic_result_json={'legs':[{'duration':20}], 'delay':20})
    def result(name, delay):
        return {'ordered':[{'cliente_nome':name}], 'total_min':30, 'delay':delay}
    original, better, worse = result('A',20), result('B',10), result('C',30)
    candidates = iter([better,worse])
    buffers = []
    def optimize(*args, **kwargs):
        buffers.append(kwargs['window_buffer'])
        return next(candidates)
    def save(db,user,data,chosen,vehicle,plan_id):
        plan.delay = chosen['delay']
        return plan
    def enrich(db,current,force=False,cached_traffic=None):
        current.traffic_result_json = cached_traffic or {'legs':[{'duration':20}], 'delay':current.delay}
    def evaluate(snapshot,legs,current):
        return {'ordered':[{'time_window_violation':True,'lateness_min':current.delay}]}
    monkeypatch.setattr(platform_settings,'traffic_provider_name',lambda db:'mapbox')
    monkeypatch.setattr(route_enrichment,'evaluate_legs',evaluate)
    monkeypatch.setattr(routes,'json_data',lambda value:value)
    monkeypatch.setattr(routes,'enrich_final_route',enrich)
    monkeypatch.setattr(routes,'optimize_route',optimize)
    monkeypatch.setattr(routes,'save_route_result',save)
    monkeypatch.setattr(routes,'build_vehicle_dict',lambda *args:{})
    monkeypatch.setattr(routes,'_check_resource_overlap',lambda *args,**kwargs:None)
    data = SimpleNamespace(driver_schedule=SimpleNamespace(model_dump=lambda:{}),
                           rientro_deposito=False,orario_partenza='08:00',data_giro='2099-01-01')
    final, chosen, timed = routes._traffic_two_pass(SimpleNamespace(commit=lambda:None),None,data,None,[],None,plan,original)
    assert timed and chosen is better
    assert final.delay == 10 and final.traffic_result_json['delay'] == 10
    assert buffers[0] == 0 and buffers[1] > 0


def shifts(data, *schedules):
    for resource, (start, end) in zip(data['resources'], schedules):
        resource['driver_schedule'] = {'start': start, 'end': end, 'breaks': []}


def test_fleet_replans_when_traffic_pushes_return_past_the_shift(fleet, monkeypatch):  # noqa: F811
    ctx, data = fleet
    flat_roads(monkeypatch)
    data = deepcopy(data)
    # Un mezzo solo: 55 minuti senza traffico (rientro 8:55), 95 con il traffico (9:35, turno fino alle 9:30).
    data.update(strategy='efficient', consegne=[verified_stop(ctx[2].id, cliente_nome=n, indirizzo=f'Via {n}', lat=45.1 + i / 100,
                                                             lon=9.1, tempo_scarico_min=5) for i, n in enumerate('ABC')])
    shifts(data, ('08:00', '09:30'), ('08:00', '09:30'))
    plan = preview(fleet, data)
    report = plan['search']['on_time_replan']
    assert report['accepted'] and report['overtime_before'] == 5 and report['overtime_after'] == 0
    assert len(plan['routes']) == 2 and plan['unassigned'] == []
    assert all(not route['traffic']['overtime_min'] for route in plan['routes'])


def test_fleet_warns_when_overtime_cannot_be_removed(fleet, monkeypatch):  # noqa: F811
    ctx, data = fleet
    flat_roads(monkeypatch)
    data = deepcopy(data)
    # Un solo autista disponibile: la consegna resta sua, ma il rientro con il traffico è oltre il turno.
    data.update(strategy='efficient', consegne=[verified_stop(ctx[2].id, cliente_nome='A', indirizzo='Via A', lat=45.1, lon=9.1,
                                                             tempo_scarico_min=5)])
    shifts(data, ('08:00', '08:30'), ('12:00', '12:30'))
    plan = preview(fleet, data)
    [route] = plan['routes']
    assert route['traffic']['overtime_min'] == 15
    assert any('dopo la fine del turno (08:30)' in warning for warning in plan['warnings'])


def test_fleet_driver_with_later_shift_departs_at_shift_start(fleet, monkeypatch):  # noqa: F811
    ctx, data = fleet
    flat_roads(monkeypatch)
    data = deepcopy(data)
    # Fasce pomeridiane: solo il secondo autista (10:00-18:00) può servirle, partendo alle 10:00 e non alle 8:00.
    data.update(strategy='efficient', consegne=[verified_stop(ctx[2].id, cliente_nome=n, indirizzo=f'Via {n}', lat=45.1 + i / 100, lon=9.1,
                                                             tempo_scarico_min=5, scarico_mattina_da='14:00', scarico_mattina_a='16:00')
                                                for i, n in enumerate('ABC')])
    shifts(data, ('08:00', '12:00'), ('10:00', '18:00'))
    plan = preview(fleet, data)
    assert plan['unassigned'] == []
    [route] = plan['routes']
    assert route['resource'] == 1 and route['traffic']['departure_time'].endswith('T09:00:00Z')
    saved = command(fleet, plan, 'confirm')
    assert saved.status_code == 200, saved.text
    [row] = ctx[1].query(RoutePlan).all()
    assert row.orario_partenza.strftime('%H:%M') == '10:00'
