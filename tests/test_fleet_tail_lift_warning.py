"""A missing tail lift must never reduce otherwise feasible fleet coverage."""
from copy import deepcopy

import pytest

from routing_quality_fifty import fifty_cases
from routing_quality_fleet import run_fleet
from routing_quality_oracle import plan_metrics


@pytest.mark.parametrize('strategy', ['efficient', 'balanced'])
def test_fifty_deliveries_requiring_lift_are_served_when_no_vehicle_has_one(strategy):
    case=deepcopy(fifty_cases()[0])
    case['hard_tail_lift']=False
    for stop in case['stops']:
        stop['sponda']=True
    for resource in case['resources']:
        resource['ha_sponda']=False
    answer=run_fleet(case,strategy)
    replay=plan_metrics(case,answer['routes'])
    assert replay['feasible'] and replay['served']==50
    assert replay['mismatches']==50
    assert answer['unassigned']==[]
    assert sum('richiede la sponda' in warning.lower()
               for warning in answer['production']['warnings'])==50
    assert all('sponda' in stop['warning'].lower()
               for route in answer['production']['routes'] for stop in route['result']['ordered'])
    assert answer['routing_matrix_calls']==1 and answer['external_calls']==0
