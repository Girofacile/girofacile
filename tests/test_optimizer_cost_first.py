"""Confronto dei giri per punteggio (5 novembre 2026): km più ore dell'autista convertite
in km (1 ora = 60 km), attese comprese, e partenza più tarda quando elimina le attese.
Sostituisce la regola «prima i km» (test_optimizer_distance_first.py)."""
from types import SimpleNamespace

import pytest

from app import optimizer as opt
from test_optimizer import offline, deliveries, constant_matrix, ids


def test_faster_route_wins_when_saved_minutes_cost_more_than_extra_km():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 1, "min": 40}
    matrix[0, 2] = {"km": 2, "min": 1}
    # 1 km in più contro 39 minuti di autista (39 km equivalenti).
    assert ids(opt._best_internal_sequence(rows, matrix, [])) == [2, 1]


def test_much_shorter_route_still_wins_against_a_little_faster_one():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 1, "min": 4}
    matrix[0, 2] = {"km": 20, "min": 1}
    # 19 km in più contro 3 minuti (3 km equivalenti).
    assert ids(opt._best_internal_sequence(rows, matrix, [])) == [1, 2]


def test_free_driver_minutes_bring_back_the_shortest_route():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 1, "min": 40}
    matrix[0, 2] = {"km": 2, "min": 1}
    vehicle = {"km_per_ora": 0}
    assert ids(opt._best_internal_sequence(rows, matrix, [], vehicle)) == [1, 2]


def unavoidable_wait_case():
    # 1 chiude alle 08:20 (prima fermata obbligata); 2 apre alle 10:00; 3 senza fascia.
    rows, matrix = deliveries(3), constant_matrix(3, 1, 10)
    rows[0].update(scarico_mattina_da="08:00", scarico_mattina_a="08:20")
    rows[1].update(scarico_mattina_da="10:00", scarico_mattina_a="12:00")
    matrix[1, 3] = {"km": 3, "min": 10}
    matrix[3, 2] = {"km": 3, "min": 10}
    return rows, matrix


def test_waiting_that_a_later_departure_cannot_absorb_costs_driver_time():
    rows, matrix = unavoidable_wait_case()
    best = opt._best_internal_sequence(rows, matrix, [])
    # 1, 3, 2 percorre 8 km invece di 4, ma l'autista lavora 10 minuti in meno:
    # con la vecchia regola dei km vinceva 1, 2, 3 con le stesse ore di attesa.
    assert ids(best) == [1, 3, 2]
    assert best["total_km"] == 8


def test_minutes_cost_nothing_then_kilometres_decide_again():
    rows, matrix = unavoidable_wait_case()
    best = opt._best_internal_sequence(rows, matrix, [], {"km_per_ora": 0})
    assert best["total_km"] == 4


def test_absorbable_wait_is_not_counted_as_driver_time():
    rows, matrix = deliveries(1), constant_matrix(1, 2, 40)
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="10:00", tempo_scarico_min=15)
    result = opt._evaluate_fixed_sequence(rows, matrix, [])
    assert result["total_wait"] == 20 and result["departure_slack_min"] == 20
    assert result["_objective"][4] == pytest.approx(opt.route_cost(4, result["total_min"] - 20))


@pytest.mark.parametrize("stops,total_wait,expected", [
    ([(0, None), (0, 10), (60, 90)], 60, 10),     # una fascia che chiude presto limita lo slittamento
    ([(30, None), (0, None)], 30, 30),            # tutta l'attesa si recupera
    ([(0, -5), (40, None)], 40, 0),               # già in ritardo: nessuno slittamento
    ([], 0, 0),
])
def test_departure_slack(stops, total_wait, expected):
    assert opt.departure_slack(stops, total_wait) == expected


def stub_route(monkeypatch, rows, matrix):
    monkeypatch.setattr(opt, "build_distance_matrix", lambda *a, **k: matrix)
    depot = SimpleNamespace(id=1, user_id=1, lat=45, lon=9, indirizzo="Depot")
    for row in rows:
        row.pop("_matrix_index", None)
    return depot


def test_optimize_route_departs_later_instead_of_waiting(monkeypatch):
    rows = deliveries(1)
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="10:00", tempo_scarico_min=15)
    depot = stub_route(monkeypatch, rows, constant_matrix(1, 2, 40))
    fixed = opt.optimize_route(None, depot, [dict(r) for r in rows], route_date="2099-01-01", flexible_departure=False)
    moved = opt.optimize_route(None, depot, [dict(r) for r in rows], route_date="2099-01-01")
    assert fixed["total_wait_min"] == 20 and "departure" not in fixed
    assert (moved["departure"], moved["requested_departure"]) == ("08:20", "08:00")
    row = moved["ordered"][0]
    assert (row["arrivo_fisico"], row["attesa_min"], row["inizio_servizio"]) == ("09:00", 0, "09:00")
    assert moved["total_wait_min"] == 0
    assert moved["return_time"] == fixed["return_time"]
    assert moved["total_min"] == fixed["total_min"] - 20


def test_departure_moves_in_steps_of_five_minutes(monkeypatch):
    rows = deliveries(1)
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="10:00", tempo_scarico_min=15)
    depot = stub_route(monkeypatch, rows, constant_matrix(1, 2, 37))
    moved = opt.optimize_route(None, depot, rows, route_date="2099-01-01")
    # 23 minuti di attesa: si parte alle 08:20 e restano 3 minuti.
    assert moved["departure"] == "08:20" and moved["total_wait_min"] == 3


def test_late_route_keeps_its_departure(monkeypatch):
    rows = deliveries(1)
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="09:10", tempo_scarico_min=15)
    depot = stub_route(monkeypatch, rows, constant_matrix(1, 2, 40))
    result = opt.optimize_route(None, depot, rows, route_date="2099-01-01")
    assert "departure" not in result and result["violations_count"] == 1


def test_short_wait_keeps_the_departure(monkeypatch):
    rows = deliveries(1)
    rows[0].update(scarico_mattina_da="09:00", scarico_mattina_a="10:00", tempo_scarico_min=15)
    depot = stub_route(monkeypatch, rows, constant_matrix(1, 2, 57))
    result = opt.optimize_route(None, depot, rows, route_date="2099-01-01")
    assert "departure" not in result and result["total_wait_min"] == 3


def test_later_departure_never_accepts_a_worse_route():
    base = {"violations": 0, "departure_slack_min": 30, "total_min": 100, "total_wait": 30}
    tried = []
    def evaluate_at(clock):
        tried.append(clock)
        return {"violations": 1, "total_min": 70, "total_wait": 0, "total_lateness_min": 5}
    result, moved = opt.later_departure(base, 480, evaluate_at)
    assert (result, moved) == (base, None)
    assert tried == [510, 495, 485]


def test_vehicle_without_tail_lift_field_is_not_a_missing_tail_lift():
    stop = {"sponda": True}
    assert opt.delivery_warnings(stop, {"km_per_ora": 60}) == ["Sponda richiesta"]
    assert opt.delivery_warnings(stop, {"ha_sponda": False}) == ["Serve sponda ma il mezzo selezionato non la possiede"]


def test_score_weights_are_fixed_and_ignore_company_prices():
    # Nessun prezzo o costo scritto dal cliente: 1 km vale 1, un minuto vale 1 km.
    assert opt.KM_PER_HOUR == 60
    assert opt.cost_rates() == (1.0, 1.0)
    assert opt.cost_rates({"costo_km": 5, "costo_orario_autista": 99, "ha_sponda": True}) == (1.0, 1.0)
    assert opt.route_cost(85, 300) == 385
    assert opt.cost_rates({"km_per_ora": 0}) == (1.0, 0.0)
    assert opt.cost_rates({"km_per_ora": "x"}) == (1.0, 1.0)
    assert opt.cost_rates({"km_per_ora": -1}) == (1.0, 1.0)


def test_fleet_backup_search_ranks_by_km_and_main_search_by_score():
    from app.services.fleet_search import _route_key
    from app.services.fleet_working_clock import _plan_key
    short_slow = {"total_km": 10, "total_min": 300, "_objective": (10, 300, 0, 0, 310)}
    long_fast = {"total_km": 40, "total_min": 100, "_objective": (40, 100, 0, 0, 140)}
    assert _route_key(short_slow, "distance") < _route_key(long_fast, "distance")
    assert _route_key(long_fast, "efficient") < _route_key(short_slow, "efficient")
    rows, vehicles = [{}], [{}]
    assert _plan_key([[0]], [short_slow], rows, vehicles, "distance") < _plan_key([[0]], [long_fast], rows, vehicles, "distance")
    assert _plan_key([[0]], [long_fast], rows, vehicles, "efficient") < _plan_key([[0]], [short_slow], rows, vehicles, "efficient")


def break_scoring_case():
    rows, matrix = deliveries(2), constant_matrix(2, 2, 20)
    rows[0].update(scarico_mattina_da='09:00', scarico_mattina_a='10:00', tempo_scarico_min=15)
    matrix[1, 2]['min'] = 40
    vehicle = {'driver_schedule': {
        'start': '08:00', 'end': '18:00',
        'breaks': [{'start': '08:30', 'end': '09:00'}],
    }}
    return rows, matrix, vehicle


def test_fixed_break_remains_in_cost_when_later_departure_cannot_remove_it(monkeypatch):
    rows, matrix, vehicle = break_scoring_case()
    first = opt._evaluate_fixed_sequence(rows, matrix, [], vehicle)
    assert first['departure_slack_min'] == 10  # 40 minutes of waiting include a fixed 30-minute break.
    assert opt.work_minutes(first) == 125
    moved, clock = opt.later_departure(first, 480, lambda start: opt._evaluate_fixed_sequence(
        rows, matrix, [], vehicle, True, opt.fmt_hhmm(start)))
    assert clock == 490 and moved['total_min'] == 125
    assert opt.work_minutes(moved) == moved['total_min']
    assert opt.objective_cost(moved) == 131
    # The alternative takes 105 minutes with the same 6 km, so it must win.
    depot = stub_route(monkeypatch, rows, matrix)
    best = opt.optimize_route(None, depot, rows, vehicle, route_date='2099-01-01')
    assert ids(best) == [2, 1] and best['total_min'] == 105
    assert 'departure' not in best


def fixed_departure_case():
    rows, matrix = deliveries(2), constant_matrix(2, 2, 20)
    rows[0].update(scarico_mattina_da='10:00', scarico_mattina_a='12:00', tempo_scarico_min=15)
    matrix[0, 2]['min'] = matrix[2, 1]['min'] = 40
    return rows, matrix


def test_fixed_departure_ranks_the_waiting_that_will_actually_remain(monkeypatch):
    rows, matrix = fixed_departure_case()
    depot = stub_route(monkeypatch, rows, matrix)
    fixed = opt.optimize_route(None, depot, [dict(row) for row in rows],
                               route_date='2099-01-01', flexible_departure=False)
    flexible = opt.optimize_route(None, depot, [dict(row) for row in rows], route_date='2099-01-01')
    assert ids(fixed) == [2, 1] and fixed['total_min'] == 155
    assert fixed['return_time'] == '10:35' and 'departure' not in fixed
    assert ids(flexible) == [1, 2] and flexible['total_min'] == 75
    assert flexible['departure'] == '09:40'


@pytest.mark.parametrize('fixed', [False, True])
def test_fast_evaluator_matches_realizable_slack_and_fixed_departure(fixed):
    from app.services.optimizer_search import RouteEvaluator
    rows, matrix = deliveries(2), constant_matrix(2, 2, 37)
    rows[0].update(scarico_mattina_da='09:00', scarico_mattina_a='12:00', tempo_scarico_min=15)
    vehicle = {'_flexible_departure': not fixed}
    canonical = opt._evaluate_fixed_sequence(rows, matrix, [], vehicle, include_details=False)
    fast = RouteEvaluator(rows, matrix, [], vehicle, True, '08:00').evaluate(rows, include_details=False)
    assert fast['_objective'] == canonical['_objective']
    assert canonical['departure_slack_min'] == (0 if fixed else 20)
    # The three minutes left after the five-minute grid remain paid time.
    assert opt.work_minutes(canonical) == canonical['total_min'] - (0 if fixed else 20)


@pytest.mark.parametrize('fixed', [False, True])
def test_fleet_fixed_order_evaluator_matches_pause_and_departure_score(fixed):
    from app.services.fleet_route_evaluator import FixedRouteEvaluator
    rows, matrix, vehicle = break_scoring_case()
    vehicle['_flexible_departure'] = not fixed
    canonical = opt._evaluate_fixed_sequence(rows, matrix, [], vehicle, earliest_windows=True)
    fast = FixedRouteEvaluator(rows, [0, 1], matrix, [], vehicle, True, '08:00', 600)([0, 1])
    assert opt.objective_cost(fast) == opt.objective_cost(canonical)
    assert opt.work_minutes(fast) == opt.work_minutes(canonical)
    assert canonical['departure_slack_min'] == (0 if fixed else 10)


def test_pause_alone_does_not_trigger_departure_change():
    rows, matrix = deliveries(1), constant_matrix(1, 2, 20)
    vehicle = {'driver_schedule': {'breaks': [{'start': '08:30', 'end': '09:00'}]}}
    base = opt._evaluate_fixed_sequence(rows, matrix, [], vehicle, start_time='08:40')
    assert base['departure_slack_min'] == 0
    assert opt.work_minutes(base) == base['total_min']


def test_departure_delay_grid_is_relative_to_requested_clock(monkeypatch):
    rows, matrix = deliveries(1), constant_matrix(1, 2, 37)
    rows[0].update(scarico_mattina_da='09:00', scarico_mattina_a='10:00', tempo_scarico_min=15)
    depot = stub_route(monkeypatch, rows, matrix)
    result = opt.optimize_route(None, depot, rows, start_time='08:03', route_date='2099-01-01')
    assert result['departure'] == '08:23' and result['total_wait_min'] == 0


def test_selected_departure_does_not_discount_a_second_future_shift(monkeypatch):
    rows, matrix = deliveries(1), constant_matrix(1, 2, 20)
    rows[0].update(scarico_mattina_da='09:30', scarico_mattina_a='11:00', tempo_scarico_min=15)
    vehicle = {'driver_schedule': {'breaks': [{'start': '08:30', 'end': '09:00'}]}}
    depot = stub_route(monkeypatch, rows, matrix)
    replay = opt._evaluate_fixed_sequence
    snapshots = []
    def record(*args, **kwargs):
        result = replay(*args, **kwargs)
        snapshots.append(dict(result))
        return result
    monkeypatch.setattr(opt, '_evaluate_fixed_sequence', record)
    result = opt.optimize_route(None, depot, rows, vehicle,
                                start_time='08:40', route_date='2099-01-01')
    # Only the original 10-minute opening wait may shift the departure. Even
    # though the selected clock remains inside the pause, do not discount a
    # second ten-minute shift from this final, already chosen departure.
    assert result['departure'] == '08:50' and result['total_min'] == 75
    assert opt.work_minutes(snapshots[-1]) == result['total_min']
    assert snapshots[-1]['departure_slack_min'] == 0
