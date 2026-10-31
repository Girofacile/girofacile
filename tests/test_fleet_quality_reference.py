"""Known-answer checks for the independent fleet oracle (no production imports)."""
import pytest
from fleet_quality_reference import plan_metrics, route_replay, solve_exact


def make_case(stops=None, resources=None, travel=20, returning=False):
    stops = stops if stops is not None else [{"tempo_scarico_min": 10}]
    resources = resources if resources is not None else [{
        "capacita_kg": 1000, "capacita_colli": 100,
        "ha_sponda": True, "accesso_ztl": True, "max_minutes": 480,
        "driver_schedule": {
            "start": "08:00", "end": "17:00",
            "breaks": [{"start": "08:15", "end": "08:45"}],
        },
    }]
    size = len(stops) + 1
    return {
        "id": "known", "family": "reference", "seed": 0,
        "stops": stops, "resources": resources, "return_depot": returning,
        "start_min": 480,
        "matrix": {(i, j): {"km": 0 if i == j else 10, "min": 0 if i == j else travel}
                   for i in range(size) for j in range(size)},
    }


def test_driving_is_interrupted_by_fixed_break():
    route = route_replay(make_case(), 0, [0])
    assert route["feasible"] and route["km"] == 10
    assert route["minutes"] == 60
    assert route["drive_min"] == 20
    assert route["break_drive_min"] == 30
    assert route["timings"] == [{
        "index": 0, "arrival": 530, "service_start": 530,
        "service_end": 540, "wait": 0,
    }]


def test_unloading_waits_as_one_contiguous_operation():
    case = make_case(travel=10)
    route = route_replay(case, 0, [0])
    assert route["timings"][0]["arrival"] == 490
    assert route["timings"][0]["service_start"] == 525
    assert route["wait_min"] == 35
    assert route["minutes"] == 55
    assert route["break_drive_min"] == 0
    case["stops"][0].update(scarico_mattina_da="08:00", scarico_mattina_a="08:50")
    assert route_replay(case, 0, [0])["errors"] == ["window:0"]


def test_wait_overlap_and_second_window_do_not_duplicate_the_pause():
    case = make_case(travel=10)
    case["stops"][0].update(scarico_mattina_da="09:00", scarico_mattina_a="10:00")
    route = route_replay(case, 0, [0])
    assert route["feasible"] and route["wait_min"] == 50
    assert route["minutes"] == 70 and route["break_drive_min"] == 0
    case["stops"][0].update(
        scarico_mattina_da="08:00", scarico_mattina_a="08:50",
        scarico_pomeriggio_da="09:00", scarico_pomeriggio_a="10:00",
    )
    assert route_replay(case, 0, [0])["timings"][0]["service_start"] == 540


def test_zero_service_is_postponed_inside_a_break_and_boundaries_are_inclusive():
    case = make_case(stops=[{"tempo_scarico_min": 0}], travel=10)
    case["resources"][0]["driver_schedule"]["breaks"] = [{"start": "08:10", "end": "08:45"}]
    route = route_replay(case, 0, [0])
    assert route["timings"][0]["arrival"] == 490
    assert route["timings"][0]["service_start"] == 525
    case["stops"][0]["tempo_scarico_min"] = 5
    case["resources"][0]["driver_schedule"]["breaks"] = [{"start": "08:15", "end": "08:45"}]
    assert route_replay(case, 0, [0])["end"] == 495


def test_return_shift_capacity_and_available_time_are_checked():
    case = make_case(stops=[{"tempo_scarico_min": 0, "peso_kg": 100, "colli": 4}],
                     travel=10, returning=True)
    route = route_replay(case, 0, [0])
    assert route["km"] == 20 and route["minutes"] == 50
    assert route["break_drive_min"] == 30
    case["resources"][0].update(capacita_kg=99, capacita_colli=3, available_minutes=49)
    case["resources"][0]["driver_schedule"]["end"] = "08:49"
    assert set(route_replay(case, 0, [0])["errors"]) == {
        "capacita_kg", "capacita_colli", "duration", "shift",
    }
    assert route_replay(case, 0, [])["feasible"]
    assert route_replay(case, 0, [])["minutes"] == 0


def test_breaks_at_multiple_points_and_before_departure():
    case = make_case(travel=100)
    case["resources"][0]["driver_schedule"]["breaks"] = [
        {"start": "07:00", "end": "07:15"},
        {"start": "08:10", "end": "08:20"},
        {"start": "08:40", "end": "09:00"},
    ]
    route = route_replay(case, 0, [0])
    assert route["timings"][0]["arrival"] == 610
    assert route["break_drive_min"] == 30 and route["minutes"] == 140


def test_plan_metrics_detects_duplicates_and_soft_equipment_requirements():
    resources = [{"max_minutes": 480, "ha_sponda": False, "accesso_ztl": False}] * 2
    case = make_case(stops=[{"tempo_scarico_min": 0, "sponda": True, "ztl": True}],
                     resources=resources, travel=10)
    # Explicit historical/manual advisory semantics remain testable; automatic
    # planning now treats a requested tail lift as physically required.
    case["hard_tail_lift"] = False
    valid = plan_metrics(case, [[0], []])
    assert valid["feasible"] and valid["mismatches"] == 2
    assert valid["served"] == 1 and valid["used"] == 1 and valid["makespan"] == 10
    assert not plan_metrics(case, [[0], [0]])["feasible"]
    assert not plan_metrics(case, [[1]])["feasible"]


def test_exact_reference_has_known_spatial_solution():
    coordinates = [0, 10, -10, 11, -11]
    case = make_case(
        stops=[{"peso_kg": 1, "colli": 1, "tempo_scarico_min": 0} for _ in range(4)],
        resources=[{"capacita_kg": 2, "max_minutes": 480}] * 2, returning=True,
    )
    case["matrix"] = {
        (i, j): {"km": abs(a - b), "min": abs(a - b) * 2}
        for i, a in enumerate(coordinates) for j, b in enumerate(coordinates)
    }
    exact = solve_exact(case)
    for objective, metrics in exact.items():
        assert metrics["served"] == 4 and metrics["feasible"], objective
        assert metrics["km"] == 44 and metrics["minutes"] == 88, objective
        assert plan_metrics(case, metrics["orders"]) == metrics


def test_exact_reference_finds_full_capacity_partition():
    case = make_case(
        stops=[{"peso_kg": weight, "tempo_scarico_min": 0}
               for weight in (6, 5, 3, 2, 2, 2)],
        resources=[{"capacita_kg": 10, "max_minutes": 480}] * 2, travel=1,
    )
    exact = solve_exact(case)
    for metrics in exact.values():
        assert metrics["served"] == 6 and metrics["used"] == 2
        weights = [sum(case["stops"][index]["peso_kg"] for index in order)
                   for order in metrics["orders"]]
        assert weights == [10, 10]


def test_exact_reference_keeps_distinct_km_and_time_witnesses():
    case = make_case(
        stops=[{"tempo_scarico_min": 0}] * 2,
        resources=[{"max_minutes": 480}], returning=True,
    )
    for edge in ((0, 1), (1, 2), (2, 0)):
        case["matrix"][edge] = {"km": 1, "min": 10}
    for edge in ((0, 2), (2, 1), (1, 0)):
        case["matrix"][edge] = {"km": 10, "min": 1}
    exact = solve_exact(case)
    assert exact["km"]["orders"] == [[0, 1]]
    assert exact["km"]["km"] == 3 and exact["km"]["minutes"] == 30
    assert exact["time"]["orders"] == [[1, 0]]
    assert exact["time"]["km"] == 30 and exact["time"]["minutes"] == 3
    assert exact["efficient"]["orders"] == exact["km"]["orders"]
    assert exact["balanced"]["orders"] == exact["time"]["orders"]


def test_automatic_reference_rejects_missing_tail_lift_but_ztl_stays_advisory():
    case = make_case(stops=[{"tempo_scarico_min": 0, "sponda": True, "ztl": True}],
                     resources=[{"max_minutes": 480, "ha_sponda": False, "accesso_ztl": False}],
                     travel=10)
    assert route_replay(case, 0, [0])["errors"] == ["tail_lift:0"]
    assert all(metrics["served"] == 0 for metrics in solve_exact(case).values())
    case["resources"][0]["ha_sponda"] = True
    allowed = route_replay(case, 0, [0])
    assert allowed["feasible"] and allowed["mismatches"] == 1
    assert solve_exact(case)["efficient"]["served"] == 1


def test_efficient_reference_can_use_an_extra_vehicle_to_save_distance():
    case = make_case(stops=[{"tempo_scarico_min": 0}] * 2,
                     resources=[{"max_minutes": 480}] * 2,
                     travel=10, returning=True)
    for edge in ((0, 1), (1, 0), (0, 2), (2, 0)):
        case["matrix"][edge]["km"] = 1
    case["matrix"][1, 2]["km"] = case["matrix"][2, 1]["km"] = 50
    exact = solve_exact(case)["efficient"]
    assert exact["served"] == 2 and exact["used"] == 2
    assert exact["km"] == 4 and exact["minutes"] == 40


def test_exact_reference_prefers_serving_deliveries_then_equipped_resources():
    case = make_case(
        stops=[{"tempo_scarico_min": 0, "sponda": True}],
        resources=[{"max_minutes": 480}, {"max_minutes": 480, "ha_sponda": True}],
    )
    for metrics in solve_exact(case).values():
        assert metrics["served"] == 1 and metrics["mismatches"] == 0
        assert metrics["orders"] == [[], [0]]
    case["stops"][0].update(scarico_mattina_da="07:00", scarico_mattina_a="07:30")
    assert all(metrics["served"] == 0 for metrics in solve_exact(case).values())


@pytest.mark.parametrize("n,resources", [(8, 2), (1, 4), (1, 0)])
def test_exact_reference_rejects_unbounded_experiments(n, resources):
    with pytest.raises(ValueError):
        solve_exact(make_case(stops=[{}] * n, resources=[{}] * resources))
