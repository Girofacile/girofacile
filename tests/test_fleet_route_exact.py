"""Exhaustive route orders preserve a larger fleet's assigned memberships."""
from collections import Counter
from math import ceil, factorial
import pytest
from app.services.fleet_search import refine_routes
from fleet_quality_reference import route_replay
from fleet_simulation_cases import make_case, resource, stop, uniform_matrix


def score(minutes, km):
    return {"total_min": ceil(minutes), "total_km": round(km, 1),
            "_objective": (float(km), float(minutes))}


def directed_matrix(routes):
    n = max(index for route in routes for index in route)+1
    matrix = {(a,b): {"km": float(a!=b)*100, "min": float(a!=b)*100}
              for a in range(n+1) for b in range(n+1)}
    for route in routes:
        path = (0,)+tuple(index+1 for index in reversed(route))+(0,)
        for a,b in zip(path,path[1:]):
            matrix[a,b] = {"km":1.0,"min":1.0}
    return matrix


def matrix_score(order, matrix):
    path = (0,)+tuple(index+1 for index in order)+(0,)
    return score(sum(matrix[a,b]["min"] for a,b in zip(path,path[1:])),
                 sum(matrix[a,b]["km"] for a,b in zip(path,path[1:])))


def test_all_40320_directed_eight_stop_orders_are_evaluated_once(monkeypatch):
    monkeypatch.setenv("FLEET_MAX_CANDIDATES","0")
    routes=(tuple(range(8)),);matrix=directed_matrix(routes);seen=Counter()
    def evaluate(order,selected):
        assert selected==0
        seen[tuple(order)]+=1
        return matrix_score(order,matrix)
    best,results,diagnostics=refine_routes(
        routes,(matrix_score(routes[0],matrix),),evaluate)
    assert len(seen)==factorial(8)==40320
    assert set(seen.values())=={1}
    assert all(set(order)==set(range(8)) for order in seen)
    assert best==(tuple(reversed(range(8))),)
    assert results[0]["_objective"]==(9.0,9.0)
    info=diagnostics["route_refinement"][0]
    assert info["evaluations"]==40320 and info["order_optimum_proven"]
    assert info["scope"]=="fixed-membership-and-resource"
    assert info["method"]=="exact-permutations" and info["improved"]
    assert diagnostics["exact_route_evaluations"]==40320


@pytest.mark.parametrize("first,second,expected",[
    ((20.02,1.0),(20.01,2.0),(1,0)),
    ((20.01,2.0),(20.01,1.0),(1,0)),
    ((20.01,1.0),(20.01,1.0),(0,1))])
def test_raw_duration_then_distance_and_stable_ties(first,second,expected):
    values={(0,1):score(*first),(1,0):score(*second)}
    best,results,diagnostics=refine_routes(((0,1),),(values[(0,1)],),
                                         lambda order,r:values[order])
    assert best==(expected,) and results[0]==values[expected]
    assert diagnostics["exact_route_evaluations"]==2


def test_nine_stop_route_is_preserved_without_any_evaluation():
    order=tuple(range(9));previous=score(25.5,12.3)
    def forbidden(*args):
        pytest.fail("More than eight stops must retain the existing heuristic")
    best,results,diagnostics=refine_routes((order,),(previous,),forbidden,prepare=forbidden)
    assert best==(order,) and results[0] is previous
    info=diagnostics["route_refinement"][0]
    assert info["method"]=="existing-heuristic" and not info["order_optimum_proven"]
    assert info["evaluations"]==diagnostics["exact_route_evaluations"]==0


def test_fifty_deliveries_are_exact_per_assigned_five_stop_group():
    routes=tuple(tuple(range(start,start+5)) for start in range(0,50,5))
    matrix=directed_matrix(routes);calls=Counter()
    def evaluate(order,r):
        assert set(order)==set(routes[r])
        calls[r]+=1
        return matrix_score(order,matrix)
    best,_,diagnostics=refine_routes(routes,tuple(matrix_score(o,matrix) for o in routes),evaluate)
    assert best==tuple(tuple(reversed(order)) for order in routes)
    assert calls==Counter({r:factorial(5) for r in range(10)})
    assert diagnostics["exact_route_evaluations"]==1200
    assert all(row["order_optimum_proven"] for row in diagnostics["route_refinement"])
    assert sorted(index for order in best for index in order)==list(range(50))


def test_mixed_fifty_stop_plan_refines_only_routes_with_at_most_eight():
    sizes=(8,7,6,9,10,10);routes=[];start=0
    for size in sizes:
        routes.append(tuple(range(start,start+size)));start+=size
    routes=tuple(routes);previous=tuple(score(len(o)+1,len(o)+1) for o in routes);calls=Counter()
    def evaluate(order,r):
        assert sizes[r]<=8 and set(order)==set(routes[r])
        calls[r]+=1
        return score(len(order)+1,len(order)+1)
    best,results,diagnostics=refine_routes(routes,previous,evaluate)
    assert best==routes
    assert calls==Counter({0:factorial(8),1:factorial(7),2:factorial(6)})
    assert diagnostics["exact_route_evaluations"]==sum(factorial(n) for n in sizes if n<=8)
    for r in (3,4,5):
        assert results[r] is previous[r]
        assert not diagnostics["route_refinement"][r]["order_optimum_proven"]


def test_empty_and_singleton_routes():
    previous=score(12,4);calls=[]
    def evaluate(order,r):
        calls.append((order,r));return previous
    best,results,diagnostics=refine_routes(((),(4,)),(None,previous),evaluate)
    assert best==((),(4,)) and results[0] is None
    assert calls==[((4,),1)]
    assert diagnostics["route_refinement"][0]["method"]=="empty"
    assert diagnostics["route_refinement"][1]["order_optimum_proven"]


def test_global_exact_reuses_only_existing_valid_proof():
    previous=score(15,5);calls=[]
    def evaluate(order,r):
        assert r==1
        calls.append(order);return score(15,5)
    best,results,diagnostics=refine_routes(((0,1),(2,3)),(previous,None),
                                         evaluate,global_exact=True)
    assert best==((0,1),(2,3)) and results[0] is previous
    assert set(calls)=={(2,3),(3,2)}
    assert diagnostics["route_refinement"][0]["method"]=="global-exact-reuse"
    assert diagnostics["route_refinement"][0]["evaluations"]==0
    assert diagnostics["exact_route_evaluations"]==2


def test_all_infeasible_orders_are_not_marked_optimal():
    calls=[]
    best,results,diagnostics=refine_routes(((0,1,2),),(None,),
        lambda order,r:calls.append(order))
    assert len(calls)==factorial(3) and best==((0,1,2),) and results==(None,)
    info=diagnostics["route_refinement"][0]
    assert info["all_orders_infeasible"] and not info["order_optimum_proven"]


def test_eight_stop_orders_respect_independent_breaks_and_windows():
    rows=[stop(i,service=5) for i in range(8)]
    rows[0].update(scarico_mattina_da="08:00",scarico_mattina_a="08:15")
    rows[7].update(scarico_mattina_da="08:50",scarico_mattina_a="11:00")
    schedule={"start":"08:00","end":"12:00","breaks":[{"start":"08:20","end":"08:40"}]}
    case=make_case("eight-fixed-schedule","breaks",rows,uniform_matrix(8,km=1,minutes=4),
                   [resource(schedule=schedule)],exact=False)
    original=tuple(range(8));previous=route_replay(case,0,original)
    assert previous["feasible"]
    feasible,infeasible,winner=[],[],[None]
    def evaluate(order,r):
        replay=route_replay(case,r,order)
        if not replay["feasible"]:
            infeasible.append(order);return None
        key=(replay["minutes"],replay["km"]);feasible.append(order)
        if winner[0] is None or key<winner[0]:winner[0]=key
        return score(*key)
    best,results,diagnostics=refine_routes((original,),
        (score(previous["minutes"],previous["km"]),),evaluate)
    assert len(feasible)+len(infeasible)==factorial(8) and feasible and infeasible
    verified=route_replay(case,0,best[0])
    assert verified["feasible"] and not verified["errors"]
    assert best[0][0]==0 and verified["break_drive_min"]>0
    assert (verified["minutes"],verified["km"])==winner[0]
    assert results[0]["_objective"]==(verified["km"],verified["minutes"])
    assert diagnostics["route_refinement"][0]["order_optimum_proven"]


def test_prepared_score_mismatch_triggers_complete_canonical_fallback():
    calls=[]
    def canonical(order,r):
        calls.append(order)
        return score(10 if order==(1,0) else 20,1)
    def prepare(order,r):
        return lambda candidate:score(0,1)
    best,results,diagnostics=refine_routes(((0,1),),(None,),canonical,prepare=prepare)
    assert best==((1,0),) and results[0]["_objective"]==(1.0,10.0)
    assert len(calls)==3  # winning-order check plus both canonical permutations
    assert diagnostics["route_refinement"][0]["method"]=="exact-permutations-canonical-fallback"
    assert diagnostics["route_refinement"][0]["order_optimum_proven"]
