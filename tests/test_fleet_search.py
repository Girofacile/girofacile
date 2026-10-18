"""Fleet-wide regressions: real distribution, frozen matrices, independent replay."""
from copy import deepcopy
import importlib
import os
from unittest.mock import patch
import pytest
from fleet_simulation_cases import curated_cases, make_case, resource, stop, uniform_matrix


def _case(identifier):
    return deepcopy(next(case for case in curated_cases() if case["id"] == identifier))


def _audit():
    # The standalone runner configures its own process environment. Importing it
    # inside pytest must not leave those environment settings on unrelated tests.
    with patch.dict(os.environ, {}):
        return importlib.import_module("run_fleet_simulations")


def _execute(case, strategy):
    actual = _audit().execute(case, strategy)
    assert actual["invariant_errors"] == []
    assert actual["matrix_requests"] == 1
    assert actual["external_requests"] == 0
    return actual


@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
@pytest.mark.parametrize("identifier,served,km,minutes", [
    ("curated-opposite-clusters", 4, 44, 88),
    ("curated-opposite-clusters-breaks", 4, 44, 168),
    ("curated-break-window-reassignment", 2, None, None),
    ("curated-capacity-repacking", 6, None, None),
])
def test_fleet_reconsiders_membership_and_preserves_schedule(identifier, served, km, minutes, strategy):
    case = _case(identifier)
    actual = _execute(case, strategy)
    assert actual["metrics"]["served"] == served
    assert actual["unassigned"] == []
    if km is not None:
        assert actual["metrics"]["km"] == pytest.approx(km)
        assert actual["metrics"]["minutes"] == pytest.approx(minutes)
        assert actual["metrics"]["used"] == 2
    if identifier == "curated-break-window-reassignment":
        assert actual["metrics"]["orders"] == [[0], [1]]
    if identifier == "curated-capacity-repacking":
        loads = sorted(sum(case["stops"][i]["peso_kg"] for i in order)
                       for order in actual["metrics"]["orders"])
        assert loads == [10, 10]


@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
def test_combined_equipment_is_reserved_when_compatible_plan_exists(strategy):
    case = make_case(
        "scarce-combined-equipment", "equipment",
        [stop(0, sponda=True), stop(1, ztl=True), stop(2, sponda=True, ztl=True)],
        uniform_matrix(3),
        [resource(1, ha_sponda=True, accesso_ztl=True),
         resource(1, ha_sponda=True, accesso_ztl=False),
         resource(1, ha_sponda=False, accesso_ztl=True)])
    actual = _execute(case, strategy)
    assert actual["metrics"]["served"] == 3
    assert actual["metrics"]["mismatches"] == 0
    assert actual["metrics"]["orders"][0] == [2]


@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
def test_equipment_is_warning_when_no_compatible_vehicle_exists(strategy):
    case = make_case(
        "equipment-warning-fallback", "equipment",
        [stop(0, sponda=True, ztl=True)], uniform_matrix(1),
        [resource(10, ha_sponda=False, accesso_ztl=False) for _ in range(2)])
    actual = _execute(case, strategy)
    assert actual["metrics"]["served"] == 1
    assert actual["unassigned"] == []
    assert actual["metrics"]["mismatches"] == 2
    warnings = " ".join(actual["warnings"]).lower()
    assert "sponda" in warnings and "ztl" in warnings


@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
def test_small_optimum_metrics_survive_order_and_resource_reordering(strategy):
    case = _case("curated-opposite-clusters")
    expected = _execute(case, strategy)["metrics"]
    changed = _audit().permuted(case, [3, 1, 2, 0])
    changed["resources"].reverse()
    actual = _execute(changed, strategy)["metrics"]
    for field in ("served", "mismatches", "used", "km", "minutes", "makespan"):
        assert actual[field] == pytest.approx(expected[field])


def test_identical_preview_is_deterministic():
    case = _case("curated-break-window-reassignment")
    assert _execute(case, "efficient")["metrics"] == _execute(case, "efficient")["metrics"]


@pytest.mark.parametrize("strategy", ["efficient", "balanced"])
def test_coverage_has_priority_over_equipment_warnings(strategy):
    case = make_case(
        "equipment-coverage-first", "equipment",
        [stop(0, 2, sponda=True), stop(1, 1, sponda=True)], uniform_matrix(2),
        [resource(2, ha_sponda=True), resource(2, ha_sponda=False)])
    actual = _execute(case, strategy)
    assert actual["metrics"]["served"] == 2
    assert actual["metrics"]["mismatches"] == 1
    assert actual["unassigned"] == []
