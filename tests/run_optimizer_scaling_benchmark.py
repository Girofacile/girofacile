"""Offline current-vs-824816f benchmark, CPU time and evaluation counts.

python tests/run_optimizer_scaling_benchmark.py [--sizes 8 9 15 20 30 50]
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
from time import process_time, perf_counter
from unittest.mock import patch

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('ALLOW_SQLITE_LEGACY', 'true')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import optimizer as opt
import optimizer_legacy_reference as legacy
from optimizer_scaling_cases import scenario, exact_distance_reference, exact_window_reference
from optimizer_benchmark import deliveries
from app.services.optimizer_search import RouteEvaluator, CandidateBudget, bounded_descent


def forbidden(*args, **kwargs):
    raise AssertionError('Offline benchmark attempted an external provider call')


def measure(rows, matrix, back, previous=False):
    metrics = {}
    count = 0
    original = legacy._evaluate_fixed_sequence
    def counted(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)
    cpu, wall = process_time(), perf_counter()
    with contextlib.redirect_stdout(io.StringIO()), patch.object(legacy, '_evaluate_fixed_sequence', counted):
        if previous:
            result = legacy._best_internal_sequence(rows, matrix, [], return_depot=back)
        else:
            result = opt._best_internal_sequence(rows, matrix, [], return_depot=back, diagnostics=metrics)
    timing = dict(cpu_ms=round((process_time() - cpu) * 1000, 3), wall_ms=round((perf_counter() - wall) * 1000, 3))
    record = {k: result[k] for k in ('total_km', 'total_min', 'violations', 'total_lateness_min', 'total_wait')}
    record.update(timing, candidates_evaluated=count if previous else metrics['candidates_evaluated'],
                  feasible=result['violations'] == 0, **({'diagnostics': metrics} if not previous else {}))
    return result, record


def run(sizes):
    records = []
    with patch.object(opt.requests.sessions.Session, 'request', forbidden), patch.object(opt.road_routing, 'build_matrix', forbidden):
        for n in sizes:
            for kind in ('asymmetric', 'clusters', 'nearest_trap', 'windows'):
                for back in (False, True):
                    rows, matrix = scenario(n, kind)
                    old, before = measure(rows, matrix, back, True)
                    new, after = measure(rows, matrix, back)
                    assert opt.solution_key(new) <= opt.solution_key(old), (n, kind, back)
                    reference = (exact_window_reference(rows, matrix, back) if kind == 'windows' and n <= 8
                                 else exact_distance_reference(rows, matrix, back) if kind != 'windows' and n <= 12 else None)
                    if reference and n <= 8:
                        assert new['total_km'] == reference['total_km']
                    record = dict(n=n, kind=kind, return_depot=back, before=before, after=after, reference=reference,
                        delta_km=round(new['total_km'] - old['total_km'], 3),
                        improvement_km_pct=round(100 * (old['total_km'] - new['total_km']) / old['total_km'], 3),
                        improved=opt.solution_key(new) < opt.solution_key(old))
                    records.append(record)
                    print(n, kind, 'return' if back else 'open', before['total_km'], '->', after['total_km'],
                          f"{after['cpu_ms']:.1f}ms", flush=True)
    return {'baseline_commit': '824816f252e89274ebed6ef22f2d59e8483cb51a',
            'dataset': 'synthetic, deterministic, offline; not real-world savings',
            'timing': 'single process CPU/wall sample; no latency threshold assertions',
            'or_opt_ablation': ablation(), 'records': records}


def ablation():
    data = json.loads((Path(__file__).parent/'fixtures/optimizer_or_opt.json').read_text())
    rows = deliveries(data['n'])
    matrix = {(i, j): value for i, line in enumerate(data['matrix']) for j, value in enumerate(line) if i != j}
    order = [rows[i-1] for i in data['order']]
    out = {}
    for name, lengths in [('swap_2opt_relocate', (1,)), ('with_or_opt_2_3', (2, 3, 1))]:
        evaluator = RouteEvaluator(rows, matrix, [], None, True, '08:00')
        result = evaluator.evaluate(order, include_details=False)
        budget = CandidateBudget(evaluator, 5000)
        started = process_time()
        _, result = bounded_descent(order, result, budget, 5000, block_lengths=lengths)
        out[name] = dict(total_km=result['total_km'], total_min=result['total_min'],
                         candidates_evaluated=budget.used, cpu_ms=(process_time() - started) * 1000)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sizes', nargs='+', type=int, default=[5, 8, 9, 12, 15, 20, 30, 50])
    parser.add_argument('--output', default='docs/optimizer-scaling-results.json')
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(run(args.sizes), indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
