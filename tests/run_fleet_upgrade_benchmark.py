"""Offline fleet upgrade comparison against the complete pre-upgrade service.

The frozen revision is loaded from Git, never from a mutable test expectation.
Both implementations use identical calendar inputs, input permutations and frozen
road matrices and the current input adapter. Each engine uses its own versioned
calendar and objective implementation. The independent replay applies the current
advisory policy for sponda/ZTL. The comparison includes policy changes rather
than attributing every difference solely to the search algorithm.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from fleet_upgrade_cases import independent_energy_cost, upgrade_cases
from routing_quality_fleet import run_fleet
from routing_quality_oracle import objective, plan_metrics
from run_routing_quality_audit import (compact, effective_case, first_difference,
    inspect_answer, reference_for, serializable_case)

BASELINE_COMMIT = '8df798d0810206fc88068729b5abf36d3770318b'
MODULES = ('fleet_route_evaluator', 'fleet_search', 'fleet_planning')
BASELINE_HASHES = {
    'fleet_route_evaluator': '9c8e73ce68223f51b3a788d070a1c8e77b0cefbc9fa227c77c4d836cdef44dd2',
    'fleet_search': 'a9efc7f6dc615eeb186d38d4e1e62244635d969e50130ef2ab15a28be46d3182',
    'fleet_planning': 'c3469c3c79d058da18c10f92941a6346a8168a8923670eb234a0306df24a6063',
}
SHARED_ENGINE_FILES = ('app/services/driver_schedule.py',
                       'app/services/optimizer_search.py', 'app/optimizer.py')
# These files were identical in both historical baseline revisions. Keep their
# immutable digests: a calendar update must never silently change the old engine.
BASELINE_SHARED_HASHES = {
    'app/optimizer.py': '6b452720b3541aa66610ecc7b71e229183a8c8835d86279d4c4225faa4cb5885',
    'app/services/driver_schedule.py': '5969479ea24bd88f6de22a5fab72be55c89d7815b6559ee7d24c1a7869698803',
    'app/services/optimizer_search.py': '9967ec8a98a5729c97795a7f060ec550533676c344a0c2daa54726e6b0ee1974',
}
COMPARISON_POLICY = ('current input adapter and independent replay; tail lift and ZTL advisory; '
                     'historical engine uses frozen optimizer/calendar/objective; current engine uses current implementation; '
                     'whole-upgrade comparison under current km-plus-work-time or balanced priorities')
SOURCE_FILES = ['app/services/fleet_planning.py', 'app/services/fleet_search.py',
    'app/services/fleet_route_pool.py', 'app/services/fleet_seed_search.py',
    'app/services/fleet_route_evaluator.py',
    'app/services/fleet_working_clock.py', 'app/services/fleet_milp_solver.py',
    'app/services/fleet_highs_start.py', 'requirements.txt', 'requirements.lock',
    'app/optimizer.py', 'app/services/driver_schedule.py', 'app/services/optimizer_search.py',
    'app/services/fleet_pyvrp.py', 'app/services/fleet_ortools.py', 'tests/fleet_upgrade_cases.py',
    'tests/routing_quality_fleet.py', 'tests/routing_quality_oracle.py',
    'tests/run_routing_quality_audit.py',
    'tests/run_fleet_upgrade_benchmark.py']


def source_hashes():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in SOURCE_FILES}


def frozen_sources():
    result = {}
    for name in MODULES:
        path = f'app/services/{name}.py'
        source = subprocess.check_output(['git', 'show', f'{BASELINE_COMMIT}:{path}'], cwd=ROOT)
        if hashlib.sha256(source).hexdigest() != BASELINE_HASHES[name]:
            raise ValueError(f'Unexpected frozen baseline: {path}')
        result[path] = source
    for path in SHARED_ENGINE_FILES:
        source = subprocess.check_output(['git', 'show', f'{BASELINE_COMMIT}:{path}'], cwd=ROOT)
        if hashlib.sha256(source).hexdigest() != BASELINE_SHARED_HASHES[path]:
            raise ValueError(f'Unexpected frozen baseline: {path}')
        result[path] = source
    return result


@contextmanager
def frozen_implementation(sources, commit, modules):
    """Swap the complete historical computation graph, restoring every alias.

    The input adapter and the independent verifier stay current. Shared engine
    modules are frozen too, so a legitimate current calendar/objective change
    cannot leak into the old planner or invalidate the comparison.
    """
    if sources is None:
        yield
        return
    paths = [*SHARED_ENGINE_FILES, *(f'app/services/{name}.py' for name in modules)]
    specs = []
    for path in paths:
        full_name = path.removesuffix('.py').replace('/', '.')
        import_module(full_name)
        package, name = full_name.rsplit('.', 1)
        specs.append((path, full_name, import_module(package), name))
    with ExitStack() as stack:
        replacements = []
        # Install every alias before executing sources: imports between the
        # historical modules must resolve to the same historical module objects.
        for path, full_name, package, name in specs:
            module = ModuleType(full_name)
            module.__package__ = full_name.rsplit('.', 1)[0]
            module.__file__ = f'git:{commit}:{path}'
            stack.enter_context(patch.dict(sys.modules, {full_name: module}))
            stack.enter_context(patch.object(package, name, module))
            replacements.append((path, module))
        for path, module in replacements:
            exec(compile(sources[path], module.__file__, 'exec'), module.__dict__)
        yield


def implementation(sources=None):
    return frozen_implementation(sources, BASELINE_COMMIT, MODULES)


def examine(case, strategy, answer, current):
    check = inspect_answer(case, strategy, answer, reference_for(case, strategy))
    metrics = plan_metrics(effective_case(case), answer['routes'], answer.get('departures'))
    energy = independent_energy_cost(case, answer['routes'])
    if abs(sum(energy) - answer['production_metrics']['fuel_cost']) > .011:
        check['errors'].append('energy_cost_disagrees_with_independent_accounting')
    if sorted(answer['unassigned']) != list(metrics['unassigned']):
        check['errors'].append('public_unassigned_disagrees_with_independent_replay')
    expected = case.get('expected_served', 50)
    if current and metrics['served'] < expected:
        check['errors'].append('known_feasible_coverage_missed')
    if current and case.get('expected_upper_bound') == expected and metrics['served'] > expected:
        check['errors'].append('coverage_exceeds_proven_physical_bound')
    return dict(metrics=compact(metrics), objective=objective(metrics, strategy),
                energy_per_route=energy, energy_cost=sum(energy),
                runtime_ms=answer['elapsed_ms'], external_calls=answer['external_calls'],
                matrix_calls=answer['routing_matrix_calls'],
                diagnostics=answer['diagnostics'], errors=check['errors'],
                observations=check['observations'])


def summarize(records):
    comparable = [r for r in records if r['before']['metrics']['feasible']
                  and r['after']['metrics']['feasible']]
    equal = [r for r in comparable if all(r['before']['metrics'][key] == r['after']['metrics'][key]
                                      for key in ('served', 'mismatches'))]
    summary = dict(paired_runs=len(records), engine_runs=len(records) * 2,
        errors=sum(len(row['after']['errors']) for row in records),
        baseline_infeasible=sum(not r['before']['metrics']['feasible'] for r in records),
        current_infeasible=sum(not r['after']['metrics']['feasible'] for r in records),
        expected_coverage_reached=sum(r['after']['metrics']['served'] == r['expected_served']
                                     for r in records),
        coverage_gap_runs=sum(r['after']['metrics']['served'] < r['expected_served'] for r in records),
        external_calls=sum(r[version]['external_calls'] for r in records
                           for version in ('before', 'after')),
        comparable_runs=len(comparable),
        objective_improvements=sum(bool(r['comparison'] and not r['comparison']['worse'])
                                   for r in comparable),
        objective_regressions=sum(bool(r['comparison'] and r['comparison']['worse'])
                                  for r in comparable), strategies={})
    for strategy in ('efficient', 'balanced'):
        rows = [r for r in records if r['strategy'] == strategy]
        same = [r for r in equal if r['strategy'] == strategy]
        summary['strategies'][strategy] = dict(runs=len(rows),
            coverage_gap_before=sum(r['before']['metrics']['served'] < r['expected_served'] for r in rows),
            coverage_gap_after=sum(r['after']['metrics']['served'] < r['expected_served'] for r in rows),
            equal_valid_service_runs=len(same),
            km_before=sum(r['before']['metrics']['km'] for r in same),
            km_after=sum(r['after']['metrics']['km'] for r in same),
            work_minutes_before=sum(r['before']['metrics']['minutes'] for r in same),
            work_minutes_after=sum(r['after']['metrics']['minutes'] for r in same),
            energy_before=sum(r['before']['energy_cost'] for r in same),
            energy_after=sum(r['after']['energy_cost'] for r in same))
    return summary


def markdown(report):
    s = report['summary']
    lines = ['# Verifica indipendente del nuovo motore multi mezzo', '',
        f"Baseline congelata: `{BASELINE_COMMIT}`; codice attuale identificato dagli hash in `results.json`.", '',
        f"Problemi nuovi da 50 consegne: **{report['metadata']['case_count']}**. "
        f"Suddivisioni incluse: {', '.join(report['metadata']['splits'])}; "
        f"numero di mezzi: {', '.join(map(str, report['metadata']['vehicle_counts']))}. "
        'La campagna completa combina capacità eterogenee, turni, due pause, finestre di scarico, '
        'sponde ed elettrico/diesel. '
        f"Problemi inclusi con una consegna fisicamente impossibile e copertura massima provata 49/50: "
        f"{report['metadata']['impossible_case_count']}; con un autista non ancora in turno alla partenza: "
        f"{report['metadata']['later_driver_case_count']}.", '',
        f"Coppie prima/dopo: **{s['paired_runs']}**; esecuzioni: **{s['engine_runs']}**; "
        f"piani nuovi con copertura testimone: **{s['expected_coverage_reached']}**; "
        f"errori nuovi: **{s['errors']}**; richieste esterne: **{s['external_calls']}**.", '',
        f"Piani precedenti incompatibili con i vincoli attuali: **{s['baseline_infeasible']}**. "
        'Sono registrati, ma esclusi dai confronti di risparmio. '
        'Il motore storico usa calendario e obiettivo congelati; quello attuale usa '
        'l’implementazione corrente. Il confronto misura '
        'l’intero aggiornamento, valutato con l’obiettivo Efficiente corrente '
        '(copertura, compatibilità, km più tempo di lavoro) e la politica corrente con sponda e ZTL '
        'come avvisi; non isola il solo algoritmo di ricerca.', '',
        '| Strategia | Casi con servizio e compatibilità uguali | km prima | km dopo | minuti cumulativi prima | minuti cumulativi dopo |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for strategy, values in s['strategies'].items():
        lines.append(f"| {strategy} | {values['equal_valid_service_runs']} | {values['km_before']:.2f} | "
            f"{values['km_after']:.2f} | {values['work_minutes_before']:.2f} | {values['work_minutes_after']:.2f} |")
    lines += ['',
        f"Fra {s['comparable_runs']} coppie operative valide: "
        f"{s['objective_improvements']} miglioramenti e {s['objective_regressions']} peggioramenti "
        'secondo la priorità della strategia. Il totale dei minuti può crescere quando '
        'la soluzione migliora il punteggio km più tempo o gli avvisi di sponda/ZTL.', '',
        '**Nessuna certificazione dell’ottimo globale su 50 consegne.** '
        'I testimoni costruttivi indipendenti provano fattibilità e copertura; le matrici sono sintetiche '
        'e congelate, senza traffico reale. I costi energia sono verificati separatamente; '
        'autonomia e ricariche non sono modellate perché non esistono quei dati nei mezzi. '
        'I tempi misurati riguardano il nucleo senza database o provider e non costituiscono uno SLA.', '',
        'Input, matrici, piani completi, errori e metadati sono salvati accanto a questo rapporto. '
        'Una regressione di copertura nota o un vincolo violato rendono `--strict` fallito.', '',
        '```sh', 'python tests/run_fleet_upgrade_benchmark.py --strict', '```', '']
    gaps = [r for r in report['records'] if r['after']['errors']]
    if gaps:
        lines += ['## Controesempi', '', '| Caso | Strategia | Variante | Servite | Errori |',
                  '| --- | --- | --- | ---: | --- |']
        for row in gaps:
            lines.append(f"| {row['case_id']} | {row['strategy']} | {row['variant']} | "
                         f"{row['after']['metrics']['served']} | {', '.join(row['after']['errors'])} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'test-results/fleet-upgrade/comparison')
    parser.add_argument('--no-variants', action='store_true')
    parser.add_argument('--split', choices=('all', 'development', 'holdout'), default='all')
    parser.add_argument('--case', help='Run only the case with this exact identifier')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    initial_hashes = source_hashes()
    from app.services import (fleet_planning, fleet_search, fleet_route_evaluator,
                              fleet_route_pool, fleet_seed_search, driver_schedule)
    if source_hashes() != initial_hashes:
        raise ValueError('Sources changed while importing the measured engine')
    sources = frozen_sources()
    cases = ((upgrade_cases() if args.split != 'holdout' else [])
             + (upgrade_cases(holdout=True) if args.split != 'development' else []))
    if args.case:
        cases = [case for case in cases if case['id'] == args.case]
        if not cases:
            raise ValueError(f'Unknown case: {args.case}')
    records, outputs = [], []
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'inputs.json').write_text(json.dumps([serializable_case(c) for c in cases], indent=2) + '\n')
    for case in cases:
        variants = [('original', list(range(50)))]
        if not args.no_variants:
            variants.append(('reverse', list(reversed(range(50)))))
        for strategy in ('efficient', 'balanced'):
            for variant, permutation in variants:
                pair = {}
                for version, implementation_sources in (('before', sources), ('after', None)):
                    with implementation(implementation_sources):
                        answer = run_fleet(case, strategy, input_order=permutation)
                    pair[version] = examine(case, strategy, answer, current=version == 'after')
                    outputs.append(dict(case_id=case['id'], strategy=strategy, variant=variant,
                                        version=version, input_order=permutation, answer=answer))
                valid_pair = all(pair[v]['metrics']['feasible'] for v in ('before', 'after'))
                comparison = first_difference(pair['after']['objective'], pair['before']['objective']) if valid_pair else None
                records.append(dict(case_id=case['id'], split=case['split'], family=case['family'],
                    vehicles=len(case['resources']), strategy=strategy, variant=variant,
                    expected_served=case['expected_served'], comparison=comparison, **pair))
                print(f"{case['id']} / {strategy} / {variant}: "
                    f"{pair['before']['metrics']['served']}→{pair['after']['metrics']['served']}, "
                    f"{len(pair['after']['errors'])} errors", flush=True)
                # Preserve evidence even if a subsequent long campaign is interrupted.
                (args.output / 'partial-records.json').write_text(json.dumps(records, indent=2) + '\n')
    report = dict(summary=summarize(records), records=records, metadata=dict(
        baseline_commit=BASELINE_COMMIT,
        baseline_hashes={path:hashlib.sha256(source).hexdigest() for path,source in sources.items()},
        current_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        measured_at=datetime.now(timezone.utc).isoformat(), synthetic=True,
        case_count=len(cases), splits=sorted({case['split'] for case in cases}),
        vehicle_counts=sorted({len(case['resources']) for case in cases}),
        impossible_case_count=sum(case['expected_served'] < 50 for case in cases),
        later_driver_case_count=sum(case['family'] == 'later_driver_start' for case in cases),
        comparison_policy=COMPARISON_POLICY,
        source_hashes=initial_hashes,
        source_changed_during_campaign=source_hashes() != initial_hashes))
    for name, value in (('results.json', report), ('outputs.json', outputs)):
        (args.output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    (args.output / 'report.md').write_text(markdown(report))
    print(json.dumps(report['summary'], indent=2), flush=True)
    return int(args.strict and (report['summary']['errors'] > 0
                               or report['summary']['objective_regressions'] > 0
                               or report['metadata']['source_changed_during_campaign']))


if __name__ == '__main__':
    raise SystemExit(main())
