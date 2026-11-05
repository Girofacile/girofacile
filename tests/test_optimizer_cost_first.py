"""Confronto dei giri per costo (5 novembre 2026): carburante al km più ore dell'autista,
attese comprese, e partenza più tarda quando elimina le attese. Sostituisce la regola
«prima i km» (test_optimizer_distance_first.py)."""
from types import SimpleNamespace

import pytest

from app import optimizer as opt
from app.services import route_costs
from test_optimizer import offline, deliveries, constant_matrix, ids


def test_faster_route_wins_when_saved_minutes_cost_more_than_extra_km():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 1, "min": 40}
    matrix[0, 2] = {"km": 2, "min": 1}
    # 1 km in più (0,20 €) contro 39 minuti di autista (9,75 €).
    assert ids(opt._best_internal_sequence(rows, matrix, [])) == [2, 1]


def test_much_shorter_route_still_wins_against_a_little_faster_one():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 1, "min": 4}
    matrix[0, 2] = {"km": 20, "min": 1}
    # 19 km in più (3,80 €) contro 3 minuti (0,75 €).
    assert ids(opt._best_internal_sequence(rows, matrix, [])) == [1, 2]


def test_free_driver_minutes_bring_back_the_shortest_route():
    rows, matrix = deliveries(2), constant_matrix(2, 1, 1)
    matrix[0, 1] = {"km": 1, "min": 40}
    matrix[0, 2] = {"km": 2, "min": 1}
    vehicle = {"costo_orario_autista": 0}
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
    best = opt._best_internal_sequence(rows, matrix, [], {"costo_orario_autista": 0})
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
    assert opt.delivery_warnings(stop, {"costo_km": 0.2}) == ["Sponda richiesta"]
    assert opt.delivery_warnings(stop, {"ha_sponda": False}) == ["Serve sponda ma il mezzo selezionato non la possiede"]


def test_cost_rates_from_company_and_vehicle():
    user = SimpleNamespace(driver_hourly_cost=22)
    van = SimpleNamespace(alimentazione="gasolio", consumo_primario_100km=10, consumo_l_100km=None, consumo_kwh_100km=None)
    assert route_costs.rates(user, van, 1.8) == {"costo_km": 0.18, "costo_orario_autista": 22}
    assert route_costs.rates(SimpleNamespace(driver_hourly_cost=None), None) == {
        "costo_km": route_costs.DEFAULT_COST_PER_KM, "costo_orario_autista": route_costs.DEFAULT_DRIVER_HOURLY_COST}
    # Prezzo dell'energia mancante: si usa il valore predefinito, mai un carburante gratuito.
    assert route_costs.rates(user, van, 0)["costo_km"] == route_costs.DEFAULT_COST_PER_KM
    assert opt.cost_rates({"costo_km": 0.18, "costo_orario_autista": 22}) == (0.18, 22 / 60)
    assert opt.cost_rates({"costo_km": "x", "costo_orario_autista": -1}) == (
        route_costs.DEFAULT_COST_PER_KM, route_costs.DEFAULT_DRIVER_HOURLY_COST / 60)
