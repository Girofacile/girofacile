"""Prepared route scoring agrees with the canonical pause/window scheduler."""
from copy import deepcopy
from itertools import permutations
import math
import pytest
from app import optimizer as opt
from app.services.fleet_route_evaluator import FixedRouteEvaluator


def fixture(n=8):
    rows=[dict(cliente_nome=f"Stop {i}",indirizzo=f"Via fittizia {i}",
        _matrix_index=i+1,fleet_stop_index=i,peso_kg=1,colli=1,
        tempo_scarico_min=(i%4)*2.5,sponda=i==1,ztl=i==4) for i in range(n)]
    matrix={(i,j):{"km":0.0 if i==j else ((i*7+j*11)%23+1)/3,
        "min":0.0 if i==j else ((i*17+j*13)%19+1)/2}
        for i in range(n+1) for j in range(n+1)}
    points=[{"lat":45+i*.001,"lon":9} for i in range(n+1)]
    vehicle={"capacita_kg":n,"capacita_colli":n,"ha_sponda":False,"accesso_ztl":False,
        "driver_schedule":{"start":"08:00","end":"13:00","breaks":[
            {"start":"08:25","end":"08:40"},{"start":"09:10","end":"09:25"}]}}
    return rows,matrix,points,vehicle


def assert_same(fast,order,rows,matrix,points,vehicle,returning=True,start="08:00",limit=240):
    try:opt.validate_vehicle_load([rows[i] for i in order],vehicle)
    except ValueError:
        assert fast(order) is None
        return False
    expected=opt._evaluate_fixed_sequence([rows[i] for i in order],matrix,points,vehicle,
        returning,start,include_details=False,earliest_windows=True)
    actual=fast(order)
    if expected["violations"] or math.ceil(expected["_objective"][1])>limit:
        assert actual is None,(order,expected,actual)
        return False
    assert actual is not None,(order,expected)
    assert actual["_objective"][0]==pytest.approx(expected["_objective"][0],abs=1e-10)
    assert actual["_objective"][1]==pytest.approx(expected["_objective"][1],abs=1e-10)
    assert actual["total_km"]==expected["total_km"]
    assert actual["total_min"]==expected["total_min"]
    return True


def test_prepared_replay_matches_canonical_for_all_eight_stop_orders(monkeypatch):
    rows,matrix,points,vehicle=fixture()
    rows[0].update(scarico_mattina_da="08:00",scarico_mattina_a="08:25",
        scarico_pomeriggio_da="09:00",scarico_pomeriggio_a="11:00")
    rows[2].update(scarico_mattina_da="08:10",scarico_mattina_a="09:00")
    rows[4].update(scarico_mattina_da="08:50",scarico_mattina_a="09:05",
        scarico_pomeriggio_da="10:00",scarico_pomeriggio_a="12:00")
    def external(*args,**kwargs):
        raise AssertionError("Prepared route replay must not request routing")
    monkeypatch.setattr(opt,"build_distance_matrix",external)
    monkeypatch.setattr(opt,"geocode_deposit",external)
    original=deepcopy((rows,matrix,vehicle))
    fast=FixedRouteEvaluator(rows,tuple(range(8)),matrix,points,vehicle,True,"08:00",240)
    accepted=0
    for order in permutations(range(8)):
        accepted+=assert_same(fast,order,rows,matrix,points,vehicle)
    assert 0<accepted<math.factorial(8)
    assert (rows,matrix,vehicle)==original


@pytest.mark.parametrize("mode",["travel","service","return","waiting","double","ceil","start","end"])
@pytest.mark.parametrize("returning",[False,True])
def test_prepared_replay_boundary_cases(mode,returning):
    rows,matrix,points,vehicle=fixture(2)
    rows[0]["tempo_scarico_min"]=rows[1]["tempo_scarico_min"]=0
    for (i,j),leg in matrix.items():leg["min"]=0 if i==j else 5
    schedule=vehicle["driver_schedule"];schedule["breaks"]=[]
    limit=240
    if mode=="travel":schedule["breaks"]=[{"start":"08:02","end":"08:12"}]
    elif mode=="service":
        rows[0]["tempo_scarico_min"]=10
        schedule["breaks"]=[{"start":"08:10","end":"08:25"}]
    elif mode=="return":schedule["breaks"]=[{"start":"08:12","end":"08:22"}]
    elif mode=="waiting":
        rows[0].update(scarico_mattina_da="09:00",scarico_mattina_a="10:00",tempo_scarico_min=10)
        schedule["breaks"]=[{"start":"08:15","end":"08:45"}]
    elif mode=="double":
        rows[0].update(scarico_mattina_da="08:00",scarico_mattina_a="08:20",
            scarico_pomeriggio_da="09:00",scarico_pomeriggio_a="10:00",tempo_scarico_min=10)
        schedule["breaks"]=[{"start":"08:10","end":"08:40"}]
    elif mode=="ceil":
        matrix[0,1]["min"]=5.000000001
        limit=15 if returning else 10
    elif mode=="start":schedule["start"]="08:01"
    else:schedule["end"]="08:09"
    fast=FixedRouteEvaluator(rows,(0,1),matrix,points,vehicle,returning,"08:00",limit)
    for order in permutations(range(2)):
        assert_same(fast,order,rows,matrix,points,vehicle,returning,limit=limit)


def test_prepared_replay_rejects_load_even_without_time_constraints():
    rows,matrix,points,vehicle=fixture(2);vehicle["capacita_kg"]=1
    fast=FixedRouteEvaluator(rows,(0,1),matrix,points,vehicle,True,"08:00",240)
    for order in permutations(range(2)):
        assert_same(fast,order,rows,matrix,points,vehicle)
