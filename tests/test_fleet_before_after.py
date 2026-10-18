"""Regression gates distinguish service, equipment, strategy and display precision."""
from copy import deepcopy
import os
from unittest.mock import patch
import pytest
with patch.dict(os.environ, {}):
    from run_fleet_before_after import compare_results, load_baseline


def fixture_result(strategy="efficient", **changes):
    metrics=dict(served=4,mismatches=0,used=2,km=44.0,minutes=88.0,
                 makespan=44.0,sumsq=3872.0,orders=[[0,2],[1,3]])
    metrics.update(changes)
    return {"summary":{},"runs":[{
        "case_id":"known","strategy":strategy,"stage":"base","family":"curated",
        "seed":1,"stops":4,"resources":2,"return_depot":True,"permutation":None,
        "actual":{"metrics":metrics,"runtime_ms":1.0}}]}


def test_identical_results_have_no_quality_change():
    data=fixture_result()
    summary=compare_results(data,deepcopy(data))["summary"]
    assert summary["paired_runs"]==1
    assert summary["total_engine_runs"]==2
    assert summary["objective_improvements"]==summary["objective_regressions"]==summary["coverage_regressions"]==0


def test_recovery_is_improvement_even_with_more_distance_and_warnings():
    result=compare_results(fixture_result(served=3,km=30,minutes=60),
                           fixture_result(served=4,km=50,minutes=100,mismatches=1))
    assert result["summary"]["objective_improvements"]==1
    assert result["summary"]["strategies"]["efficient"]["extra_served_stops"]==1
    assert result["summary"]["strategies"]["efficient"]["equal_service_cases"]==0


def test_equipment_is_soft_and_follows_coverage():
    result=compare_results(fixture_result(mismatches=1),
                           fixture_result(served=3,mismatches=0,km=10,minutes=20))
    assert result["summary"]["coverage_regressions"]==1
    assert result["summary"]["objective_regressions"]==1


@pytest.mark.parametrize("strategy,changes", [
    ("efficient",{"mismatches":1,"km":20,"minutes":40}),
    ("efficient",{"used":3,"km":20,"minutes":40}),
    ("balanced",{"used":1,"km":20,"minutes":40,"makespan":40}),
])
def test_strategy_priorities_are_preserved(strategy,changes):
    result=compare_results(fixture_result(strategy),fixture_result(strategy,**changes))
    assert result["summary"]["objective_regressions"]==1


def test_lower_time_and_distance_is_measured_at_equal_service():
    result=compare_results(fixture_result(minutes=168,km=84),fixture_result())
    assert result["summary"]["objective_improvements"]==1
    values=result["summary"]["strategies"]["efficient"]
    assert values["equal_service_cases"]==1
    assert values["equal_service_km_before"]==84
    assert values["equal_service_km_after"]==44


def test_real_subprecision_changes_are_still_quality_regressions():
    summary=compare_results(fixture_result(),fixture_result(km=44.001,minutes=88.001))["summary"]
    assert summary["objective_regressions"]==1
    assert summary["objective_improvements"]==0


def test_missing_variant_is_rejected():
    after=fixture_result();after["runs"]=[]
    with pytest.raises(ValueError,match="identities differ"):
        compare_results(fixture_result(),after)


def test_duplicate_variant_is_rejected():
    before=fixture_result();before["runs"].append(deepcopy(before["runs"][0]))
    with pytest.raises(ValueError,match="Duplicate run identity"):
        compare_results(before,fixture_result())


def test_changed_settings_are_rejected():
    after=fixture_result();after["runs"][0]["resources"]=3
    with pytest.raises(ValueError,match="Scenario changed"):
        compare_results(fixture_result(),after)


def test_modified_baseline_is_rejected_before_execution(tmp_path):
    source=tmp_path/"baseline.py";source.write_text("raise AssertionError('must never execute')\n",encoding="utf-8")
    with pytest.raises(ValueError,match="Baseline does not match"):
        load_baseline(source)


@pytest.mark.parametrize("gain",[0.02,0.001,0.000001])
def test_small_real_time_gain_precedes_distance_even_if_not_visible_in_ui(gain):
    summary=compare_results(fixture_result(),fixture_result(minutes=88.0-gain,km=47.0))["summary"]
    assert summary["objective_improvements"]==1
    assert summary["objective_regressions"]==0


def test_floating_time_noise_does_not_hide_distance_regression():
    summary=compare_results(fixture_result(),fixture_result(minutes=88.0-1e-14,km=47.0))["summary"]
    assert summary["objective_regressions"]==1
    assert summary["objective_improvements"]==0


@pytest.mark.parametrize("loss",[0.02,0.001,0.000001])
def test_true_time_loss_is_not_hidden_by_distance_savings(loss):
    summary=compare_results(fixture_result(),fixture_result(minutes=88.0+loss,km=41.0))["summary"]
    assert summary["objective_regressions"]==1
    assert summary["objective_improvements"]==0


@pytest.mark.parametrize("gain",[0.02,0.001,0.000001])
def test_balanced_makespan_precedes_total_time_and_distance(gain):
    summary=compare_results(fixture_result("balanced"),
        fixture_result("balanced",makespan=44.0-gain,sumsq=4000,minutes=90,km=47))["summary"]
    assert summary["objective_improvements"]==1
    assert summary["objective_regressions"]==0


def test_equal_permutations_from_distinct_variant_attempts_are_both_compared():
    before=fixture_result()
    row=before["runs"][0];row.update(stage="reordered",variant="reverse",permutation=[1,0])
    other=deepcopy(row);other["variant"]="shuffle"
    before["runs"].append(other)
    summary=compare_results(before,deepcopy(before))["summary"]
    assert summary["paired_runs"]==2
    assert summary["objective_regressions"]==0
