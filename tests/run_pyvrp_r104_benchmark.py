"""Offline component benchmark on the official Solomon R104 instance.

The optional historical PyVRP adapter uses the SAME current calendar as the
current adapter: this isolates the search adapter, not the entire old product.
The solution checker below uses only the original Solomon data and arithmetic.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURE = ROOT / 'tests/fixtures/solomon/r104.txt'


def load_instance():
    import vrplib
    content = FIXTURE.read_bytes().replace(b'\r\n', b'\n')
    provenance = json.loads(FIXTURE.with_suffix('.json').read_text())
    if hashlib.sha256(content).hexdigest() != provenance['fixture_lf_sha256']:
        raise ValueError('R104 fixture differs from its recorded source')
    return vrplib.read_instance(FIXTURE, instance_format='solomon'), provenance


def prepare(raw, count):
    from app import optimizer as opt
    rows = [dict(customer_id=i, tempo_scarico_min=int(raw['service_time'][i]),
                 peso_kg=int(raw['demand'][i]), colli=0, sponda=False, ztl=False,
                 scarico_mattina_da=opt.fmt_hhmm(int(raw['time_window'][i, 0])),
                 scarico_mattina_a=opt.fmt_hhmm(int(raw['time_window'][i, 1]
                                                  + raw['service_time'][i])))
            for i in range(1, len(raw['demand']))]
    horizon = int(raw['time_window'][0, 1])
    vehicles = [dict(capacita_kg=int(raw['capacity']), capacita_colli=None,
                     ha_sponda=True, accesso_ztl=True,
                     driver_schedule=dict(start='00:00', end=opt.fmt_hhmm(horizon), breaks=[]))
                for _ in range(count)]
    matrix = {(i, j): dict(km=float(raw['edge_weight'][i, j]), min=float(raw['edge_weight'][i, j]))
              for i in range(len(raw['demand'])) for j in range(len(raw['demand']))}
    return rows, vehicles, matrix, [horizon] * count


def verify(raw, orders, count):
    seen, errors, distance = [], [], 0.0
    if orders is None:
        errors.append('no-feasible-solver-answer')
    if len(orders or []) > count:
        errors.append('too-many-vehicles')
    for order in orders or []:
        clock, previous, load = 0.0, 0, 0
        for index in order:
            node = index + 1
            if not 1 <= node < len(raw['demand']):
                errors.append('unknown-customer')
                continue
            leg = float(raw['edge_weight'][previous, node])
            distance += leg
            clock = max(clock + leg, float(raw['time_window'][node, 0]))
            if clock > raw['time_window'][node, 1] + 1e-7:
                errors.append(f'late:{node}')
            clock += float(raw['service_time'][node])
            load += int(raw['demand'][node])
            seen.append(node)
            previous = node
        if order:
            back = float(raw['edge_weight'][previous, 0])
            distance += back
            clock += back
        if load > raw['capacity']:
            errors.append('capacity')
        if clock > raw['time_window'][0, 1] + 1e-7:
            errors.append('depot-late')
    if len(set(seen)) != len(seen):
        errors.append('duplicate-customer')
    return dict(served=len(set(seen)), missing=sorted(set(range(1, len(raw['demand']))) - set(seen)),
                km=distance, independent_errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--baseline-ref', help='Compare that Git revision of the PyVRP adapter only')
    parser.add_argument('--output', type=Path, default=ROOT / 'test-results/pyvrp-r104')
    parser.add_argument('--strict', action='store_true', help='Require all 100 customers in the current valid answer')
    args = parser.parse_args()
    if not 0.1 <= args.seconds <= 120:
        parser.error('--seconds must be between 0.1 and 120')
    from app.services import fleet_pyvrp
    raw, provenance = load_instance()
    count = provenance['benchmark_vehicles']
    rows, vehicles, matrix, limits = prepare(raw, count)
    current_source = (ROOT / 'app/services/fleet_pyvrp.py').read_bytes()
    engines = []
    if args.baseline_ref:
        source = subprocess.check_output(['git', 'show', args.baseline_ref + ':app/services/fleet_pyvrp.py'], cwd=ROOT)
        old = ModuleType('app.services._pyvrp_r104_baseline')
        old.__package__ = 'app.services'
        exec(compile(source, args.baseline_ref + ':app/services/fleet_pyvrp.py', 'exec'), old.__dict__)
        engines.append(('baseline', old, source))
    engines.append(('current', fleet_pyvrp, current_source))
    records = []
    for name, engine, source in engines:
        started = perf_counter()
        orders, diagnostic = engine.improve(rows, vehicles, matrix, '00:00', True,
                                            limits, [()] * count, args.seconds, 'efficient')
        record = dict(engine=name, seconds=perf_counter() - started, orders=orders,
                      adapter_sha256=hashlib.sha256(source).hexdigest(),
                      diagnostic=diagnostic, **verify(raw, orders, count))
        records.append(record)
        print(json.dumps({k:v for k,v in record.items() if k != 'orders'}), flush=True)
    report = dict(provenance=provenance, allowed_seconds=args.seconds, vehicles=count,
                  baseline_ref=args.baseline_ref, pyvrp_version=version('pyvrp'),
                  python=platform.python_version(), comparison='PyVRP adapters with the same current calendar',
                  shared_source_sha256={p:hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                    for p in ('app/optimizer.py', 'app/services/fleet_working_clock.py', 'app/services/driver_schedule.py')},
                  records=records)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    current = records[-1]
    return int(args.strict and (bool(current['independent_errors']) or current['served'] != 100))


if __name__ == '__main__':
    raise SystemExit(main())
