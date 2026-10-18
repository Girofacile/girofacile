"""Offline final-order benchmark, separate from the historical 512-run campaign."""
from copy import deepcopy
from itertools import chain
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter,process_time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/"tests"))
os.environ["DATABASE_URL"]="sqlite+pysqlite:///:memory:"
os.environ["ALLOW_SQLITE_LEGACY"]="true"
os.environ["APP_ENV"]="test"
os.environ["BILLING_MODE"]="disabled"

from app import optimizer as opt
from app.services import fleet_planning as fleet
from app.services.fleet_route_evaluator import FixedRouteEvaluator
from app.services.fleet_search import refine_routes
from fleet_simulation_cases import make_case,resource,stop
from run_fleet_simulations import execute


def fixture():
    rows=[stop(i,service=2) for i in range(50)]
    points=[{"lat":45.46,"lon":9.19}]+[{"lat":r["lat"],"lon":r["lon"]} for r in rows]
    matrix={(a,b):{"km":0.0 if a==b else ((a*7+b*11)%23+1)/3,
        "min":0.0 if a==b else ((a*17+b*13)%19+1)/2}
        for a in range(51) for b in range(51)}
    schedule={"start":"08:00","end":"17:00","breaks":[
        {"start":"08:20","end":"08:35"},{"start":"12:00","end":"12:30"}]}
    vehicles=[resource(capacity=9,packages=9,schedule=schedule,
        ha_sponda=False,accesso_ztl=False) for _ in range(10)]
    rows[0]["sponda"]=True;rows[1]["ztl"]=True
    return rows,points,matrix,vehicles


def groups(sizes):
    routes=[];offset=0
    for count in sizes:
        routes.append(tuple(range(offset,offset+count)));offset+=count
    assert offset==50
    return tuple(routes)+((),)*(10-len(routes))


def fixed_workload(sizes):
    rows,points,matrix,vehicles=fixture()
    for index,row in enumerate(rows):row.update(_matrix_index=index+1,fleet_stop_index=index)
    routes=groups(sizes)
    prepared=[FixedRouteEvaluator(rows,order,matrix,points,vehicles[r],True,"08:00",540)
              if order else None for r,order in enumerate(routes)]
    def evaluate(order,r):return prepared[r](order) if order else None
    initial=tuple(evaluate(order,r) for r,order in enumerate(routes))
    before=deepcopy((rows,matrix,vehicles))
    wall,cpu=perf_counter(),process_time()
    best,results,diagnostics=refine_routes(routes,initial,evaluate)
    wall_ms=(perf_counter()-wall)*1000;cpu_ms=(process_time()-cpu)*1000
    expected=sum(math.factorial(n) for n in sizes if 0<n<=8)
    assert diagnostics["exact_route_evaluations"]==expected
    assert len(best)==10 and all(set(a)==set(b) for a,b in zip(routes,best))
    assert sorted(chain.from_iterable(best))==list(range(50))
    for r,order in enumerate(best):
        if not order:continue
        replay=opt._evaluate_fixed_sequence([rows[i] for i in order],matrix,points,
            vehicles[r],True,"08:00",earliest_windows=True)
        assert replay["violations"]==0
        assert math.isclose(results[r]["_objective"][0],replay["_objective"][0],abs_tol=1e-9)
        assert math.isclose(results[r]["_objective"][1],replay["_objective"][1],abs_tol=1e-9)
        if len(order)>8:assert order==routes[r]
    assert before==(rows,matrix,vehicles)
    return {"sizes":list(sizes),"resources":10,"exact_evaluations":expected,
        "wall_ms":wall_ms,"cpu_ms":cpu_ms,"diagnostics":diagnostics}


def main():
    def forbidden(*args,**kwargs):
        raise AssertionError("Offline benchmark attempted an external request")
    with patch("requests.sessions.Session.request",forbidden),patch("socket.socket.connect",forbidden),patch("smtplib.SMTP",forbidden):
        workloads=[fixed_workload((8,8,8,8,8,8,2)),fixed_workload((8,8,8,8,8,9,1))]
    rows,points,matrix,vehicles=fixture()
    case=make_case("route8-extra-50-stop-smoke","route8_extra",rows,matrix,
        vehicles,exact=False,coordinates=points)
    smoke=execute(case,"efficient")
    assert smoke["matrix_requests"]==1 and smoke["external_requests"]==0
    assert smoke["invariant_errors"]==[] and smoke["metrics"]["served"]==50
    assignments=[None]*50
    for r,order in enumerate(groups((8,8,8,8,8,8,2))):
        for index in order:assignments[index]=r
    implementation=fleet.distribute
    def fixed_groups(db,user,data):
        return implementation(db,user,data,assignments=assignments)
    with patch.object(fleet,"distribute",fixed_groups):
        fixed=execute(case,"efficient")
    assert fixed["metrics"]["served"]==50 and not fixed["invariant_errors"]
    assert fixed["matrix_requests"]==1 and fixed["external_requests"]==0
    assert fixed["search"]["exact_route_evaluations"]==241922
    assert all(info["order_optimum_proven"] for info in fixed["search"]["route_refinement"] if info["stops"])
    payload={"fixed_membership_workloads":workloads,"fleet_smoke":smoke,
        "fixed_membership_fleet_smoke":fixed,
        "scope":"Exact orders for fixed membership; no global fleet optimality claim"}
    target=ROOT/"test-results/fleet-simulations/route-exact-benchmark.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
    print("FLEET_ROUTE_EXACT_BENCHMARK "+json.dumps(payload,sort_keys=True),flush=True)

if __name__=="__main__":main()
