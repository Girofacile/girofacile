"""Metro del motore nel verificatore indipendente: partenza più tarda utile e punteggio."""
from fleet_quality_reference import KM_PER_HOUR, route_replay, work_metrics, work_route
from fleet_simulation_cases import make_case, resource, stop, uniform_matrix


def test_score_weight_matches_the_engine():
    from app import optimizer
    assert KM_PER_HOUR == optimizer.KM_PER_HOUR


def late_window_case():
    # Primo cliente aperto dalle 10:00, partenza comune alle 8:00 a 10 minuti di strada.
    stops = [stop(0, service=10, scarico_mattina_da="10:00", scarico_mattina_a="11:00"), stop(1, service=10)]
    return make_case("late-window", "curated", stops, uniform_matrix(2, km=5.0, minutes=10.0),
                     [resource()])


def test_initial_wait_removed_by_departing_later_is_not_work():
    case = late_window_case()
    calendar = route_replay(case, 0, [0, 1])
    work = work_route(case, 0, [0, 1])
    assert calendar["feasible"] and work["feasible"]
    assert abs(work["end"] - calendar["end"]) < 1e-6
    assert work["minutes"] < calendar["minutes"]
    metrics = work_metrics(case, [[0, 1]])
    assert metrics["work_minutes"] == work["minutes"]
    assert metrics["cost"] == work["km"] + work["minutes"] * KM_PER_HOUR / 60


def test_route_without_waiting_keeps_its_minutes():
    case = make_case("no-wait", "curated", [stop(0, service=10), stop(1, service=10)],
                     uniform_matrix(2, km=5.0, minutes=10.0), [resource()])
    assert work_route(case, 0, [0, 1])["minutes"] == route_replay(case, 0, [0, 1])["minutes"]
