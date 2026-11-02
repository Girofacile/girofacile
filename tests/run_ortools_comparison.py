"""Offline comparison with optional OR-Tools, never imported by the application.

Run with the application requirements plus ortools==9.15.6755.
The first experiment deliberately covers single windows, kg/packages, fixed
08:00 departures and 17:00 shift ends, three vehicles and return to depot.
No breaks, equipment mismatches, traffic or live data: unsupported inputs fail.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:///:memory:'
os.environ['ALLOW_SQLITE_LEGACY'] = 'true'
os.environ['APP_ENV'] = 'test'
os.environ['BILLING_MODE'] = 'disabled'

from routing_quality_fleet import _case, _resource, _stop, run_fleet
from routing_quality_oracle import plan_metrics, replay, objective, solve_fleet


def hhmm(value):
    return f'{value // 60:02d}:{value % 60:02d}'


def make_case(n, seed, tight=False, impossible=False):
    rng = random.Random(seed)
    xy = [(0, 0)] + [(rng.uniform(-8, 8), rng.uniform(-8, 8)) for _ in range(n)]
    matrix = {}
    for i, (x, y) in enumerate(xy):
        for j, (xx, yy) in enumerate(xy):
            units = 0 if i == j else math.ceil((math.hypot(xx-x, yy-y)*1.15 + .2)*10)
            matrix[i, j] = {'km': units/10, 'min': 0 if i == j else math.ceil(units/10*2 + 1)}
    rows = [_stop(i, weight=rng.choice((10,20,30)), service=rng.choice((5,10,15)),
                  lat=45.47+xy[i+1][1]/111, lon=9.18+xy[i+1][0]/78) for i in range(n)]
    members = list(range(n))
    rng.shuffle(members)
    witness = []
    for v in range(3):
        pending, order, previous = set(members[v::3]), [], 0
        while pending:
            i = min(pending, key=lambda k: (matrix[previous,k+1]['min'],k))
            order.append(i);pending.remove(i);previous=i+1
        witness.append(order)
    resources = [_resource(math.ceil(sum(rows[i]['peso_kg'] for i in order)*1.15),
                    math.ceil(n/3)+1, available=540,
                    schedule={'start':'08:00','end':'17:00','breaks':[]}) for order in witness]
    case = _case(f'{n}-stops-seed-{seed}-' + ('tight' if tight else 'wide') + ('-impossible' if impossible else ''),
                 'ortools-pilot', rows, resources, matrix, seed=seed, witness=witness, reference='witness')
    for v, order in enumerate(witness):
        timing = replay(case, v, order)
        assert timing['feasible']
        for item in timing['stops']:
            row = rows[item['index']]
            start = max(480,int(item['service_start'])-30) if tight else 480
            end = min(1020,int(item['service_end'])+30) if tight else 1020
            row.update(scarico_mattina_da=hhmm(start),scarico_mattina_a=hhmm(end))
    assert plan_metrics(case,witness)['feasible']
    if impossible:
        rows[0].update(scarico_mattina_da='08:00',scarico_mattina_a='08:01')
        witness = [[i for i in order if i != 0] for order in witness]
        case['witness'] = witness
        assert plan_metrics(case,witness)['feasible']
    return case


def cases():
    return [make_case(6,1102),make_case(12,1103),make_case(24,1104),
            make_case(24,1105,True),make_case(24,1106,True),
            make_case(36,1107,True),make_case(24,1108,True,True)]


def solve_google(case, seconds=10):
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    n, count = len(case['stops']),len(case['resources'])
    assert count == 3 and case['return_depot'] and case['start_time'] == '08:00'
    assert case.get('traffic_margin',1) == 1
    for row in case['stops']:
        assert not row.get('sponda') and not row.get('ztl')
        assert not row.get('scarico_pomeriggio_da') and not row.get('scarico_pomeriggio_a')
    for r in case['resources']:
        assert r['driver_schedule'] == {'start':'08:00','end':'17:00','breaks':[]}
        assert r['max_minutes'] == 540
    for leg in case['matrix'].values():
        assert abs(leg['min']-round(leg['min'])) < 1e-8
        assert abs(leg['km']*10-round(leg['km']*10)) < 1e-8
    start_clock = perf_counter()
    manager = pywrapcp.RoutingIndexManager(n+1,count,0)
    routing = pywrapcp.RoutingModel(manager)
    # Exact lexicographic encoding on these integer fixtures:
    # missed visits > distance (0.1 km) > cumulative minutes > used vehicles.
    time_weight = count+1
    distance_weight = count*540*time_weight+count+1
    max_distance = (n+count)*max(round(x['km']*10) for x in case['matrix'].values())
    drop_penalty = max_distance*distance_weight + count*540*time_weight+count+1
    def distance(a,b):
        return round(case['matrix'][manager.IndexToNode(a),manager.IndexToNode(b)]['km']*10)*distance_weight
    def transit(a,b):
        origin,dest=manager.IndexToNode(a),manager.IndexToNode(b)
        service=case['stops'][origin-1]['tempo_scarico_min'] if origin else 0
        return round(case['matrix'][origin,dest]['min']+service)
    routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(distance))
    routing.SetFixedCostOfAllVehicles(1)
    routing.AddDimension(routing.RegisterTransitCallback(transit),540,540,True,'Time')
    time=routing.GetDimensionOrDie('Time')
    time.SetSpanCostCoefficientForAllVehicles(time_weight)
    for v in range(count):
        routing.AddVariableMinimizedByFinalizer(time.CumulVar(routing.End(v)))
    for field,cap in [('peso_kg','capacita_kg'),('colli','capacita_colli')]:
        def demand(a,field=field):
            node=manager.IndexToNode(a)
            return int(case['stops'][node-1][field]) if node else 0
        routing.AddDimensionWithVehicleCapacity(routing.RegisterUnaryTransitCallback(demand),0,
            [int(r[cap]) for r in case['resources']],True,field)
    for i,row in enumerate(case['stops']):
        index=manager.NodeToIndex(i+1)
        routing.AddDisjunction([index],drop_penalty)
        minute=lambda text:int(text[:2])*60+int(text[3:])
        lower=minute(row['scarico_mattina_da'])-480
        upper=minute(row['scarico_mattina_a'])-480-int(row['tempo_scarico_min'])
        if upper < lower or upper < 0:
            routing.ActiveVar(index).SetValue(0)
        else:
            time.CumulVar(index).SetRange(max(0,lower),min(540,upper))
    parameters=pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy=routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    parameters.local_search_metaheuristic=routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    parameters.time_limit.FromMilliseconds(round(seconds*1000))
    solution=routing.SolveWithParameters(parameters)
    if solution is None:
        raise RuntimeError(f'No OR-Tools assignment, status={routing.status()}')
    orders=[]
    for v in range(count):
        index=routing.Start(v);order=[]
        while not routing.IsEnd(index):
            node=manager.IndexToNode(index)
            if node:order.append(node-1)
            index=solution.Value(routing.NextVar(index))
        orders.append(order)
    metrics=plan_metrics(case,orders)
    assert metrics['feasible'], metrics
    encoded=((n-metrics['served'])*drop_penalty+round(metrics['km']*10)*distance_weight
             +round(metrics['minutes'])*time_weight+metrics['used'])
    assert encoded == solution.ObjectiveValue(), (encoded,solution.ObjectiveValue())
    return {'metrics':metrics,'elapsed_ms':(perf_counter()-start_clock)*1000,
            'status':routing.status(),'objective':solution.ObjectiveValue(),
            'weights':{'distance':distance_weight,'time':time_weight,'vehicle':1,'drop':drop_penalty}}


def export_case(case):
    return {**case,'matrix':[{'from':a,'to':b,**leg} for (a,b),leg in case['matrix'].items()]}


def rank(m):
    return (-m['served'],m['mismatches'],round(m['km'],6),round(m['minutes'],6),m['used'])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=float,default=10)
    parser.add_argument('--output',default='docs/ortools-comparison-2026-11-02.json')
    args=parser.parse_args()
    import ortools
    records=[]
    for case in cases():
        before=deepcopy(case)
        current=run_fleet(case,'efficient')
        metrics=plan_metrics(case,current['routes'])
        assert metrics['feasible'] and not current['mutation_detected']
        assert current['external_calls']==0 and current['routing_matrix_calls']==1
        assert current['production_metrics']['served']==metrics['served']
        assert abs(current['production_metrics']['km']-metrics['km'])<.02
        assert abs(current['production_metrics']['minutes']-metrics['minutes'])<.11
        google=solve_google(case,args.seconds)
        assert case==before
        winner='ortools' if rank(google['metrics'])<rank(metrics) else 'girofacile' if rank(metrics)<rank(google['metrics']) else 'tie'
        record={'id':case['id'],'input':export_case(case),'girofacile':{'metrics':metrics,
                'elapsed_ms':current['elapsed_ms'],'diagnostics':current['diagnostics']},
                'ortools':google,'winner':winner}
        if len(case['stops'])<=7:
            exact=solve_fleet(case,'efficient')
            record['exact']=exact
        records.append(record)
        print(json.dumps({'id':case['id'],'winner':winner,'current':{k:metrics[k] for k in ('served','km','minutes')},
            'google':{k:google['metrics'][k] for k in ('served','km','minutes')},
            'current_ms':round(current['elapsed_ms']),'google_ms':round(google['elapsed_ms'])}),flush=True)
    report={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'python':platform.python_version(),'ortools_version':ortools.__version__,
            'ortools_seconds_per_case':args.seconds,'strategy':'efficient',
            'scope':'Synthetic frozen matrices; 3 vehicles; single windows; no breaks, traffic, equipment restrictions or production data. OR-Tools starts independently, without current routes or witnesses.',
            'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                ['app/services/fleet_planning.py','app/services/fleet_search.py','app/optimizer.py','tests/run_ortools_comparison.py','tests/routing_quality_oracle.py']},
            'records':records}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':main()
