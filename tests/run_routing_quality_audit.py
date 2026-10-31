"""Fresh, reproducible audit of the current single-route and fleet engines.

No historical scenario or reference helper is imported. The new independent
oracle replays every answer and exhausts small problems; larger cases use
explicit feasible witnesses or mathematical distance bounds. Offline matrices
isolate solver quality from provider latency and future traffic uncertainty.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')
os.environ.setdefault('ALLOW_SQLITE_LEGACY', 'true')
os.environ.setdefault('APP_ENV', 'test')

from routing_quality_oracle import objective, plan_metrics, solve_fleet, solve_single
from routing_quality_single import run_single, single_cases
from routing_quality_fleet import fleet_cases, run_fleet

METRICS = ('served', 'used', 'km', 'minutes', 'wait', 'lateness', 'violations',
           'mismatches', 'makespan', 'sumsq', 'feasible', 'unassigned', 'orders')


def compact(metrics):
    return {name: metrics[name] for name in METRICS if name in metrics}


def effective_case(case):
    result = deepcopy(case)
    margin = case.get('traffic_margin', 1.0) if case['kind'] == 'fleet' else 1.0
    if margin > 1:
        result['matrix'] = {edge: {**leg, 'min': leg['min'] * margin}
                            for edge, leg in case['matrix'].items()}
    if case['kind'] == 'fleet':
        hour, minute = map(int, case.get('start_time', '08:00').split(':'))
        remaining = 1440 - hour * 60 - minute
        for resource in result['resources']:
            resource['max_minutes'] = min(resource.get('max_minutes', remaining), remaining)
    return result


def serializable_case(case):
    return {**{key: value for key, value in case.items() if key != 'matrix'},
            'matrix': [[i, j, leg['km'], leg['min']]
                       for (i, j), leg in sorted(case['matrix'].items())]}


def first_difference(left, right):
    """Compare raw objective components, tolerating only floating point noise."""
    for index, (a, b) in enumerate(zip(left, right)):
        tolerance = max(1e-8, 1e-10 * max(abs(a), abs(b)))
        if abs(a - b) > tolerance:
            return {'index': index, 'actual': a, 'reference': b,
                    'delta': a - b, 'worse': a > b}
    return None


def reference_for(case, strategy):
    effective = effective_case(case)
    if case.get('reference') == 'validation':
        return None
    if case.get('reference') == 'exact':
        result = (solve_single(effective) if strategy == 'single'
                  else solve_fleet(effective, strategy))
        return {**result, 'type': 'independent-exhaustive'}
    if case.get('witness') is not None:
        metrics = plan_metrics(effective, case['witness'])
        return dict(type='feasible-witness', metrics=metrics,
                    objective=objective(metrics, strategy), orders=case['witness'],
                    optimality_proven=False, feasibility_proven=metrics['feasible'],
                    distance_lower_bound=case.get('distance_lower_bound'))
    return None


def inspect_answer(case, strategy, answer, reference=None):
    """Keep correctness, optimality evidence, and heuristic quality separate."""
    errors, observations = [], []
    if answer.get('provider_calls', answer.get('external_calls', 0)):
        errors.append('external_provider_attempt')
    if answer.get('mutation_detected'):
        errors.append('input_mutated')
    expected = case.get('expected_error')
    if expected:
        if not answer.get('rejected') or expected not in (answer.get('error') or ''):
            errors.append('expected_validation_rejection_missing')
        return dict(status='validation', errors=errors, observations=observations,
                    actual=None, reference=None, comparison=None)
    if answer.get('rejected'):
        return dict(status='error', errors=errors + [answer.get('error') or 'unexpected_rejection'],
                    observations=observations, actual=None, reference=None, comparison=None)
    effective = effective_case(case)
    try:
        metrics = plan_metrics(effective, answer['routes'])
    except (ValueError, IndexError, KeyError) as exc:
        return dict(status='error', errors=errors + [str(exc)], observations=observations,
                    actual=None, reference=None, comparison=None)
    if strategy == 'single' and metrics['served'] != len(case['stops']):
        errors.append('single_route_missing_deliveries')
    if strategy != 'single' and not metrics['feasible']:
        errors.append('fleet_contains_infeasible_or_duplicate_assignment')
    if strategy == 'single' and not metrics['feasible']:
        if reference and reference['metrics']['feasible']:
            errors.append('feasible_single_route_missed')
        else:
            observations.append('single_route_infeasible_no_feasible_reference')
    public = answer.get('result') if strategy == 'single' else answer.get('production_metrics')
    if public:
        for field, name, precision in (('total_km', 'km', .011), ('total_min', 'minutes', .051)):
            actual_field = field if strategy == 'single' else name
            # Aggregate public values are rounded once per active route.
            tolerance = precision * max(1, metrics['used'])
            if actual_field in public and abs(public[actual_field] - metrics[name]) > tolerance:
                errors.append(f'public_{name}_disagrees_with_independent_replay')
    comparison = None
    if reference:
        if reference['type'] == 'feasible-witness' and not reference['metrics']['feasible']:
            errors.append('invalid_audit_witness')
        if reference.get('optimality_proven') or reference['metrics']['feasible']:
            comparison = first_difference(objective(metrics, strategy), reference['objective'])
            if comparison and comparison['worse']:
                label = ('exact_objective_gap' if reference.get('optimality_proven')
                         else 'worse_than_feasible_witness')
                observations.append(label)
                # A proven gap outside the engine's exact-search scope is an
                # observed heuristic limitation, not a false optimality claim.
                engine_promises_exact = (len(case['stops']) <= 8 if strategy == 'single' else
                    len(case['stops']) <= 7 and len(case['resources']) <= 3)
                if reference.get('optimality_proven') and (
                        engine_promises_exact or answer.get('diagnostics', {}).get('global_optimum_proven')):
                    errors.append(label)
                elif metrics['served'] < reference['metrics']['served']:
                    observations.append('known_feasible_deliveries_left_unassigned')
        lower = reference.get('distance_lower_bound')
        if lower is not None:
            if metrics['km'] < lower - 1e-7:
                errors.append('distance_below_mathematical_bound')
            elif math.isclose(metrics['km'], lower, abs_tol=1e-7):
                observations.append('minimum_distance_certified_by_bound')
    return dict(status='ok' if not errors else 'finding', errors=errors,
                observations=observations, actual=compact(metrics),
                reference=({**{key: value for key, value in reference.items() if key != 'metrics'},
                            'metrics': compact(reference['metrics'])} if reference else None),
                comparison=comparison)


def _percentile(values, proportion):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * proportion) - 1)]


def run_campaign(quick=False, variants=True, progress=False):
    cases = single_cases(quick) + fleet_cases(quick)
    records, outputs = [], []
    wall = perf_counter()
    for case in cases:
        strategies = ('single',) if case['kind'] == 'single' else ('efficient', 'balanced')
        for strategy in strategies:
            reference = reference_for(case, strategy)
            n = len(case['stops'])
            permutations = [('original', list(range(n)))]
            if variants and n <= 12 and not case.get('expected_error'):
                shuffled = list(range(n))
                random.Random(301030 + n).shuffle(shuffled)
                permutations.extend([('reverse', list(reversed(range(n)))), ('shuffle', shuffled)])
            if variants and n in (9, 12, 25, 50, 100):
                permutations.append(('repeat', list(range(n))))
            base = None
            for variant, order in permutations:
                adapter = run_single if strategy == 'single' else run_fleet
                kwargs = dict(input_order=order)
                answer = adapter(case, **kwargs) if strategy == 'single' else adapter(case, strategy, **kwargs)
                inspection = inspect_answer(case, strategy, answer, reference)
                if inspection['actual']:
                    rank = objective(plan_metrics(effective_case(case), answer['routes']), strategy)
                    if base is None:
                        base = (answer['routes'], rank)
                    elif variant == 'repeat' and (answer['routes'] != base[0] or first_difference(rank, base[1])):
                        inspection['errors'].append('identical_input_not_deterministic')
                    elif variant in ('reverse', 'shuffle') and first_difference(rank, base[1]):
                        inspection['observations'].append('input_order_changes_objective')
                runtime = answer.get('runtime_ms', answer.get('elapsed_ms'))
                record = dict(case_id=case['id'], kind=case['kind'], family=case['family'],
                    stops=n, resources=len(case['resources']), strategy=strategy, variant=variant,
                    seed=case.get('seed'), runtime_ms=round(runtime, 3),
                    cpu_ms=round(answer.get('cpu_ms', 0), 3),
                    matrix_calls=answer.get('matrix_calls', answer.get('routing_matrix_calls')),
                    external_calls=answer.get('provider_calls', answer.get('external_calls', 0)),
                    diagnostics=answer.get('diagnostics', {}), **inspection)
                records.append(record)
                outputs.append(dict(case_id=case['id'], strategy=strategy, variant=variant,
                                    input_order=order, answer=answer))
                if progress:
                    print(f"{case['id']} / {strategy} / {variant}: {len(record['errors'])} errors, "
                          f"{runtime:.1f} ms", flush=True)
    summary = dict(cases=len(cases), single_cases=sum(c['kind'] == 'single' for c in cases),
        fleet_cases=sum(c['kind'] == 'fleet' for c in cases), runs=len(records),
        errors=sum(len(row['errors']) for row in records),
        error_runs=sum(bool(row['errors']) for row in records),
        exact_comparisons=sum(bool(row.get('reference', {}).get('optimality_proven'))
                              for row in records if row.get('reference')),
        exact_gaps=sum('exact_objective_gap' in row['observations'] for row in records),
        witness_gaps=sum('worse_than_feasible_witness' in row['observations'] for row in records),
        order_sensitive=sum('input_order_changes_objective' in row['observations'] for row in records),
        distance_certificates=sum('minimum_distance_certified_by_bound' in row['observations'] for row in records),
        external_calls=sum(row['external_calls'] for row in records),
        elapsed_seconds=round(perf_counter() - wall, 3))
    summary['runtime_ms'] = {kind: dict(
        median=round(statistics.median(values), 3), p95=round(_percentile(values, .95), 3),
        maximum=round(max(values), 3)) for kind in ('single', 'fleet')
        if (values := [r['runtime_ms'] for r in records if r['kind'] == kind])}
    return dict(summary=summary, records=records), cases, outputs


def markdown_report(report):
    summary, rows = report['summary'], report['records']
    lines = ['# Verifica del motore corrente — 30 ottobre 2026', '',
        f"Versione esaminata: `{report['metadata']['commit']}`. Nuovi casi sintetici, "
        'matrici stradali congelate e riferimento indipendente; nessun vecchio scenario riutilizzato.', '',
        f"{summary['cases']} problemi nuovi, {summary['runs']} esecuzioni; "
        f"{summary['exact_comparisons']} confronti con ottimo dimostrato, "
        f"{summary['exact_gaps']} scarti dall’ottimo (inclusi i casi oltre la soglia esatta del motore). "
        f"Errori di correttezza o delle garanzie dichiarate: {summary['errors']}. "
        f"Richieste esterne: {summary['external_calls']}.", '',
        '## Criteri', '',
        '- Giro singolo: fattibilità, poi chilometri, durata, attesa e avvisi.',
        '- Flotta efficiente: consegne compatibili servite, preferenza ZTL, chilometri, durata cumulativa e mezzi utilizzati.',
        '- Flotta bilanciata: consegne servite, compatibilità preferenziale, più mezzi utilizzati, durata massima, bilanciamento, durata cumulativa e km.',
        '- Il prezzo energetico modifica la stima, non l’obiettivo di assegnazione.', '',
        'Il riferimento esatto enumera ordini e assegnazioni sui casi piccoli. '
        'Sui casi grandi un testimone fattibile è un termine di confronto, non una prova di ottimalità; '
        'i casi in linea retta hanno un limite inferiore dimostrabile per i km. '
        'Un ottimo dell’ordine di un giro con mezzi e consegne fissati non prova l’ottimo globale della flotta.', '',
        '## Risultati per problema (prima esecuzione)', '',
        '| Caso | Strategia | Fermate | Servite | Mezzi | km | Minuti cumulativi | Riferimento | Esito | ms |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |']
    for row in rows:
        if row['variant'] != 'original':
            continue
        actual, reference = row['actual'], row['reference']
        label = ('ottimo esatto' if reference and reference.get('optimality_proven') else
                 'fattibilità esatta' if reference and reference.get('feasibility_proven') and reference.get('type') == 'independent-exhaustive' else
                 'limite km' if reference and reference.get('distance_lower_bound') is not None else
                 'testimone' if reference else 'validazione')
        values = ([actual[k] for k in ('served', 'used', 'km', 'minutes')]
                  if actual else ['—'] * 4)
        outcome = ', '.join(row['errors'] or row['observations']) or 'coerente'
        lines.append(f"| {row['case_id']} | {row['strategy']} | {row['stops']} | "
                     f"{values[0]} | {values[1]} | {values[2]} | {values[3]} | {label} | {outcome} | {row['runtime_ms']} |")
    lines.extend(['', '## Robustezza e prestazioni', '',
        f"Variazioni dell’obiettivo riordinando gli input: {summary['order_sensitive']}. "
        f"Risultati peggiori di un testimone fattibile: {summary['witness_gaps']}. "
        f"Certificati di distanza minima sui casi analitici: {summary['distance_certificates']}.", '',
        'I tempi misurano il motore su questa macchina, senza latenza database/provider; '
        'non sono tempi garantiti in produzione. Percentili sulle esecuzioni della campagna, non su un carico reale.', '',
        '```json', json.dumps(summary['runtime_ms'], indent=2), '```', '',
        '## Riproduzione', '', '```sh',
        'python tests/run_routing_quality_audit.py --profile full --strict',
        'python -m pytest tests/test_routing_quality_oracle.py tests/test_routing_quality_audit.py tests/test_routing_quality_integration.py -q -ra',
        '```', '', 'Il runner salva input completi, piani, risultati e hash dei sorgenti in '
        '`test-results/routing-quality/`. `--profile quick` riduce la campagna per la CI. '
        '`--strict` fallisce per violazioni o scarti nei casi in cui il motore dichiara ricerca esatta; '
        'i gap euristici, anche quando dimostrati con un riferimento esatto più ampio, '
        'restano esplicitamente visibili nel rapporto.', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('quick', 'full'), default='full')
    parser.add_argument('--output', type=Path, default=ROOT / 'test-results' / 'routing-quality')
    parser.add_argument('--no-variants', action='store_true')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    report, cases, outputs = run_campaign(args.profile == 'quick', not args.no_variants, progress=True)
    sources = ['app/optimizer.py', 'app/services/optimizer_search.py', 'app/services/fleet_planning.py',
               'app/services/fleet_search.py', 'app/services/fleet_route_evaluator.py',
               'app/services/driver_schedule.py', 'tests/routing_quality_oracle.py',
               'tests/routing_quality_single.py', 'tests/routing_quality_fleet.py',
               'tests/run_routing_quality_audit.py']
    report['metadata'] = dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        measured_at=datetime.now(timezone.utc).isoformat(), profile=args.profile,
        python=platform.python_version(), platform=platform.platform(),
        source_hashes={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
        provider_calls_blocked=True, synthetic=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('results.json', report), ('inputs.json', [serializable_case(c) for c in cases]),
                        ('outputs.json', outputs)]:
        (args.output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    (args.output / 'report.md').write_text(markdown_report(report), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2), flush=True)
    return int(args.strict and report['summary']['errors'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
