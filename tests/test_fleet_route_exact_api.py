"""End-to-end fleet refinement preserves API flows and operator memberships."""
from copy import deepcopy
import pytest
from app.models import RoutePlan
from app.services import fleet_search
from test_fleet_planning import command, env, fleet, preview, routing_env


@pytest.mark.parametrize("mode",["automatic","manual"])
def test_small_fleet_routes_are_exact_with_zero_search_budget(fleet,monkeypatch,mode):
    ctx,original=fleet;data=deepcopy(original);data["consegne"]=data["consegne"][:10]
    for row in data["consegne"]:row["peso_kg"]=30
    monkeypatch.setattr(fleet_search,"candidate_limit",lambda count:0)
    calls=[];implementation=fleet_search.refine_routes
    def capture(routes,results,evaluate,**kwargs):
        refined=implementation(routes,results,evaluate,**kwargs)
        calls.append({"members":tuple(frozenset(o) for o in routes),"diagnostics":refined[2]})
        return refined
    monkeypatch.setattr(fleet_search,"refine_routes",capture)
    plan=preview(fleet,data)
    if mode=="manual":
        calls.clear()
        response=command(fleet,plan,"revise",assignments=[0]*5+[1]*5)
        assert response.status_code==200,response.text
        plan=response.json()
    assert len(calls)==1 and plan["unassigned"]==[]
    assert sorted(len(route["stop_indexes"]) for route in plan["routes"])==[5,5]
    diagnostics=calls[0]["diagnostics"]
    assert diagnostics["exact_route_evaluations"]==240
    assert [row["evaluations"] for row in diagnostics["route_refinement"]]==[120,120]
    assert all(row["order_optimum_proven"] for row in diagnostics["route_refinement"])
    if mode=="manual":
        assert calls[0]["members"]==(frozenset(range(5)),frozenset(range(5,10)))
    saved=command(fleet,plan,"confirm");assert saved.status_code==200,saved.text
    programmed=command(fleet,saved.json(),"program")
    assert programmed.status_code==200,programmed.text
    assert len(calls)==1
    rows=ctx[1].query(RoutePlan).all()
    assert len(rows)==2 and all(row.status=="programmato" for row in rows)
    assert sum(len(row.deliveries) for row in rows)==10


def test_manual_nine_stop_route_keeps_existing_classic_solver(fleet,monkeypatch):
    from app import optimizer
    data=deepcopy(fleet[1]);data["consegne"]=data["consegne"][:9]
    plan=preview(fleet,data);calls=[];implementation=optimizer._best_internal_sequence
    def capture(sequence,*args,**kwargs):
        calls.append(len(sequence));return implementation(sequence,*args,**kwargs)
    monkeypatch.setattr(optimizer,"_best_internal_sequence",capture)
    response=command(fleet,plan,"revise",assignments=[0]*9)
    assert response.status_code==200,response.text
    revised=response.json()
    assert calls==[9] and revised["unassigned"]==[] and len(revised["routes"])==1
    assert set(revised["routes"][0]["stop_indexes"])==set(range(9))
    info=revised["search"]["route_refinement"][0]
    assert info["method"]=="existing-heuristic" and info["evaluations"]==0
    assert not info["order_optimum_proven"]
