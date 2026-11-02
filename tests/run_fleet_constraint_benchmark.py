"""Compare the specialized fleet solver with the published adaptive engine.

Every candidate is replayed by an independent calendar. All witnesses stay in
the test harness; only delivery, road, vehicle and driver input enters the real
planning service. Cached answers are accepted only when their engine/source
hashes and complete case inputs match the frozen published baseline. Both
implementations use the current input adapter and advisory-equipment replay;
the comparison includes intentional policy changes as well as search changes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import subprocess
import sys
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from fleet_constraint_holdout import constraint_holdout_cases
from fleet_upgrade_cases import upgrade_cases
from routing_quality_fleet import run_fleet
from run_fleet_upgrade_benchmark import examine, shared_fleet_source_matches
from run_routing_quality_audit import first_difference, serializable_case

BASELINE_COMMIT = 'dbe4641271fd95a8a8b78c93ab169306d86e131e'
MODULES = ('fleet_route_evaluator', 'fleet_route_pool', 'fleet_seed_search',
           'fleet_search', 'fleet_planning')
SHARED_FILES = ('app/optimizer.py', 'app/services/driver_schedule.py')
INPUT_FILES = ('tests/fleet_upgrade_cases.py', 'tests/routing_quality_fleet.py',
               'tests/routing_quality_oracle.py', 'tests/run_routing_quality_audit.py')
SOURCE_FILES = [*(f'app/services/{name}.py' for name in MODULES),
    'requirements.txt', 'requirements.lock',
    'app/services/fleet_milp_solver.py', 'app/services/fleet_working_clock.py',
    'app/services/fleet_highs_start.py',
    *SHARED_FILES, *INPUT_FILES,
    'tests/run_fleet_upgrade_benchmark.py',
    'tests/fleet_constraint_holdout.py', 'tests/run_fleet_constraint_benchmark.py']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    return {path: digest((ROOT / path).read_bytes()) for path in SOURCE_FILES}


def write_json(path, value):
    """Keep the last complete diagnostic snapshot if a campaign is stopped."""
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
    temporary.replace(path)


def frozen_sources():
    files = [*(f'app/services/{name}.py' for name in MODULES), *SHARED_FILES, *INPUT_FILES]
    sources = {path: subprocess.check_output(
        ['git', 'show', f'{BASELINE_COMMIT}:{path}'], cwd=ROOT) for path in files}
    for path in SHARED_FILES:
        if not shared_fleet_source_matches(path,sources[path],(ROOT / path).read_bytes()):
            raise ValueError(f'Shared optimizer/calendar changed since baseline: {path}')
    return sources


@contextmanager
def implementation(sources=None):
    if sources is None:
        yield
        return
    import app.services as services
    for name in MODULES:
        __import__(f'app.services.{name}')
    with ExitStack() as stack:
        for name in MODULES:
            full_name = f'app.services.{name}'
            module = ModuleType(full_name)
            module.__package__ = 'app.services'
            module.__file__ = f'git:{BASELINE_COMMIT}:app/services/{name}.py'
            stack.enter_context(patch.dict(sys.modules, {full_name: module}))
            stack.enter_context(patch.object(services, name, module))
            path = f'app/services/{name}.py'
            exec(compile(sources[path], module.__file__, 'exec'), module.__dict__)
        yield


def cached_baseline(cases, sources, directory):
    """Reuse only independently identifiable answers from the previous report."""
    if directory is None:
        return {}, None
    results_path, outputs_path = directory / 'results.json', directory / 'outputs.json'
    inputs_path = directory / 'inputs.json'
    if not all(path.is_file() for path in (results_path, outputs_path, inputs_path)):
        return {}, None
    provenance = dict(directory=str(directory), results_sha256=digest(results_path.read_bytes()),
                      inputs_sha256=digest(inputs_path.read_bytes()),
                      outputs_sha256=digest(outputs_path.read_bytes()), validated_answers=0)
    previous = json.loads(results_path.read_text())
    if previous['metadata'].get('source_changed_during_campaign'):
        return {}, dict(provenance, ignored_reason='cached_sources_changed_during_campaign')
    measured = previous['metadata']['source_hashes']
    for path, source in sources.items():
        if measured.get(path) != digest(source):
            return {}, dict(provenance, ignored_reason=f'cached_source_differs_from_baseline: {path}')
    prior_inputs = {case['id']: case for case in json.loads(inputs_path.read_text())}
    permitted, changed_inputs = set(), []
    for case in cases:
        if case['id'] in prior_inputs:
            if prior_inputs[case['id']] != serializable_case(case):
                changed_inputs.append(case['id'])
                continue
            permitted.add(case['id'])
    answers = {}
    for row in json.loads(outputs_path.read_text()):
        if row['version'] == 'after' and row['case_id'] in permitted:
            key = row['case_id'], row['strategy'], row['variant']
            if key in answers:
                raise ValueError(f'Duplicate cached baseline answer: {key}')
            answers[key] = (row['input_order'], row['answer'])
    provenance.update(validated_answers=len(answers), ignored_input_cases=changed_inputs)
    return answers, provenance


def inspect(case, strategy, answer, *, current):
    """Validate shared-matrix work and each vehicle's energy, not only totals."""
    result = examine(case, strategy, answer, current=current)
    if answer['routing_matrix_calls'] != 1:
        result['errors'].append('shared_matrix_must_be_built_once')
    seen = set()
    for route in answer['production']['routes']:
        resource = route['resource']
        if type(resource) is not int or not 0 <= resource < len(case['resources']):
            result['errors'].append('invalid_production_resource_index')
            continue
        if resource in seen:
            result['errors'].append('duplicate_production_resource')
        seen.add(resource)
        actual = float(route['fuel_cost'])
        if not math.isfinite(actual) or abs(actual-result['energy_per_route'][resource]) > .011:
            result['errors'].append(f'energy_cost_disagrees_for_resource_{resource}')
    return result


def summarize(records):
    comparable = [row for row in records if row['before']['metrics']['feasible']
                  and row['after']['metrics']['feasible']]
    same = [row for row in comparable if (
        row['before']['metrics']['unassigned'] == row['after']['metrics']['unassigned']
        and row['before']['metrics']['mismatches'] == row['after']['metrics']['mismatches'])]
    summary = dict(paired_runs=len(records),
        new_engine_runs=len(records), baseline_engine_runs=sum(not r['baseline_cached'] for r in records),
        baseline_cached_runs=sum(r['baseline_cached'] for r in records),
        errors=sum(len(r['after']['errors']) for r in records),
        current_infeasible=sum(not r['after']['metrics']['feasible'] for r in records),
        expected_coverage_reached=sum(r['after']['metrics']['served'] == r['expected_served'] for r in records),
        coverage_gap_runs=sum(r['after']['metrics']['served'] < r['expected_served'] for r in records),
        recovered_deliveries=sum(max(0, r['after']['metrics']['served']-r['before']['metrics']['served']) for r in records),
        served_before=sum(r['before']['metrics']['served'] for r in records),
        served_after=sum(r['after']['metrics']['served'] for r in records),
        expected_served=sum(r['expected_served'] for r in records),
        external_calls=sum(r[v]['external_calls'] for r in records for v in ('before', 'after')),
        objective_improvements=sum(bool(r['comparison'] and not r['comparison']['worse']) for r in comparable),
        objective_regressions=sum(bool(r['comparison'] and r['comparison']['worse']) for r in comparable),
        strategies={}, splits={})
    for strategy in ('efficient', 'balanced'):
        rows = [row for row in records if row['strategy'] == strategy]
        equal = [row for row in same if row['strategy'] == strategy]
        summary['strategies'][strategy] = dict(runs=len(rows), same_deliveries_runs=len(equal),
            gaps_before=sum(r['before']['metrics']['served'] < r['expected_served'] for r in rows),
            gaps_after=sum(r['after']['metrics']['served'] < r['expected_served'] for r in rows),
            km_before=sum(r['before']['metrics']['km'] for r in equal),
            km_after=sum(r['after']['metrics']['km'] for r in equal),
            minutes_before=sum(r['before']['metrics']['minutes'] for r in equal),
            minutes_after=sum(r['after']['metrics']['minutes'] for r in equal))
    for split in sorted({row['split'] for row in records}):
        rows = [row for row in records if row['split'] == split]
        summary['splits'][split] = dict(runs=len(rows),
            reached=sum(r['after']['metrics']['served'] == r['expected_served'] for r in rows),
            coverage_gaps=sum(r['after']['metrics']['served'] < r['expected_served'] for r in rows))
    return summary


def markdown(report):
    summary = report['summary']
    lines = ['# Solutore specializzato: confronto indipendente della flotta', '',
        f'Baseline pubblicata: `{BASELINE_COMMIT}`; solutore HiGHS tramite SciPy '
        f"`{report['metadata']['scipy_version']}`.", '',
        f"Coppie confrontate: **{summary['paired_runs']}**. "
        f"Copertura dimostrata raggiunta: **{summary['expected_coverage_reached']}**; "
        f"residui: **{summary['coverage_gap_runs']}**; "
        f"piani operativamente invalidi: **{summary['current_infeasible']}**; "
        f"richieste esterne: **{summary['external_calls']}**.", '',
        'I testimoni indipendenti sono usati soltanto per verificare la copertura; '
        'le loro assegnazioni e sequenze non sono fornite al motore. '
        'Gli input precedenti e i nuovi semi di verifica rimangono distinti. '
        'Una maggiore copertura non viene presentata come un risparmio di km a parità di servizio.', '',
        'Entrambi i motori ricevono gli input correnti e vengono rivalutati secondo '
        'la politica corrente: sponda e ZTL sono preferenze con avviso. Il confronto '
        'include quindi la correzione della politica, oltre alle modifiche della ricerca. '
        'Le cache con input differenti sono ignorate e il motore storico viene rieseguito.', '',
        '| Strategia | Confronti sulle stesse consegne | km prima | km dopo | minuti prima | minuti dopo |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for strategy, values in summary['strategies'].items():
        lines.append(f"| {strategy} | {values['same_deliveries_runs']} | {values['km_before']:.2f} | "
            f"{values['km_after']:.2f} | {values['minutes_before']:.2f} | {values['minutes_after']:.2f} |")
    lines += ['', f"Regressioni dell’obiettivo su coppie valide: **{summary['objective_regressions']}**. "
        'La verifica rigorosa fallisce per consegne fattibili escluse, vincoli violati, '
        'richieste esterne, contabilità discordante, regressioni o sorgenti modificati durante la misura.', '',
        'Ogni risposta è rivalutata con il calendario indipendente, comprese capacità, sponda, '
        'finestre, pause, turni, rientro ed energia. Le matrici sono sintetiche e congelate: '
        'la copertura verificata non certifica il minimo globale dei chilometri né il traffico futuro.', '']
    failed = [row for row in report['records'] if row['after']['errors']]
    if failed:
        lines += ['## Risultati da correggere', '', '| Caso | Strategia | Ordine | Servite | Errori |',
            '| --- | --- | --- | ---: | --- |']
        for row in failed:
            lines.append(f"| {row['case_id']} | {row['strategy']} | {row['variant']} | "
                f"{row['after']['metrics']['served']} | {', '.join(row['after']['errors'])} |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'test-results/fleet-constraint/comparison')
    parser.add_argument('--split', choices=('all', 'prior', 'fresh'), default='all')
    parser.add_argument('--case')
    parser.add_argument('--strategy', choices=('efficient', 'balanced'))
    parser.add_argument('--no-variants', action='store_true')
    parser.add_argument('--only-gaps', action='store_true', help='Rerun only the thirteen previously missed combinations')
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    sources = frozen_sources()
    cases = ((upgrade_cases()+upgrade_cases(holdout=True) if args.split != 'fresh' else [])
             + (constraint_holdout_cases() if args.split != 'prior' else []))
    if args.case:
        cases = [case for case in cases if case['id'] == args.case]
    if not cases:
        raise ValueError('No cases selected')
    cache_dir = None if args.no_cache else ROOT/'test-results/fleet-upgrade/comparison'
    cached, cache_provenance = cached_baseline(cases, sources, cache_dir)
    known_gaps = set()
    if args.only_gaps:
        if args.split == 'fresh':
            raise ValueError('Fresh inputs have no previously known gaps')
        old_report = json.loads((ROOT/'test-results/fleet-upgrade/comparison/results.json').read_text())
        known_gaps = {(row['case_id'], row['strategy'], row['variant']) for row in old_report['records']
                      if row['after']['metrics']['served'] < row['expected_served']}
        gap_ids = {key[0] for key in known_gaps}
        cases = [case for case in cases if case['id'] in gap_ids]
        if not cases:
            raise ValueError('The selected cases contain no previously missed combinations')
    initial_hashes = source_hashes()
    from app.services import fleet_planning, fleet_search, fleet_milp_solver, fleet_working_clock
    if source_hashes() != initial_hashes:
        raise ValueError('Sources changed while importing the measured engine')
    args.output.mkdir(parents=True, exist_ok=True)
    # Preserve the exact measured code even for an interrupted, uncommitted
    # qualification. Hashes alone cannot reconstruct a superseded prototype.
    for path, expected_hash in initial_hashes.items():
        source = (ROOT/path).read_bytes()
        if digest(source) != expected_hash:
            raise ValueError(f'Sources changed before preserving the measured snapshot: {path}')
        target = args.output/'sources'/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)
    write_json(args.output/'campaign-start.json', dict(
        baseline_commit=BASELINE_COMMIT, baseline_hashes={p:digest(s) for p,s in sources.items()},
        current_input_hashes={p:initial_hashes[p] for p in INPUT_FILES},
        comparison_policy='current input adapter and replay; tail lift and ZTL advisory; shared optimizer/calendar unchanged',
        source_hashes=initial_hashes, cache_provenance=cache_provenance,
        measured_at=datetime.now(timezone.utc).isoformat(),
        selected_cases=[case['id'] for case in cases]))
    records, outputs = [], []
    (args.output/'inputs.json').write_text(json.dumps([serializable_case(c) for c in cases], indent=2)+'\n')
    for case in cases:
        variants = [('original', list(range(50)))]
        if not args.no_variants:
            variants.append(('reverse', list(reversed(range(50)))))
        for strategy in ('efficient', 'balanced'):
            if args.strategy and args.strategy != strategy:
                continue
            for variant, order in variants:
                key = case['id'], strategy, variant
                if args.only_gaps and key not in known_gaps:
                    continue
                baseline_cached = key in cached
                if baseline_cached:
                    prior_order, before = cached[key]
                    if order != prior_order:
                        raise ValueError(f'Cached input permutation changed: {key}')
                else:
                    with implementation(sources):
                        before = run_fleet(case, strategy, input_order=order)
                after = run_fleet(case, strategy, input_order=order)
                pair = dict(before=inspect(case, strategy, before, current=False),
                            after=inspect(case, strategy, after, current=True))
                comparable = all(pair[v]['metrics']['feasible'] for v in ('before', 'after'))
                comparison = first_difference(pair['after']['objective'], pair['before']['objective']) if comparable else None
                record = dict(case_id=case['id'], family=case['family'], split=case['split'],
                    vehicles=len(case['resources']), strategy=strategy, variant=variant,
                    expected_served=case['expected_served'], baseline_cached=baseline_cached,
                    comparison=comparison, **pair)
                records.append(record)
                outputs += [dict(case_id=case['id'], strategy=strategy, variant=variant,
                    version=version, input_order=order, answer=answer) for version, answer
                    in (('before', before), ('after', after))]
                print(f"{case['id']} / {strategy} / {variant}: "
                    f"{pair['before']['metrics']['served']}→{pair['after']['metrics']['served']}, "
                    f"{len(pair['after']['errors'])} errors, {after['elapsed_ms']:.1f} ms", flush=True)
                write_json(args.output/'partial-records.json', records)
                write_json(args.output/'partial-outputs.json', outputs)
    if not records:
        raise ValueError('The selected filters contain no benchmark runs')
    try:
        scipy_version = metadata.version('scipy')
    except metadata.PackageNotFoundError:
        scipy_version = None
    report = dict(summary=summarize(records), records=records, metadata=dict(
        baseline_commit=BASELINE_COMMIT, baseline_hashes={p:digest(s) for p,s in sources.items()},
        current_input_hashes={p:initial_hashes[p] for p in INPUT_FILES},
        comparison_policy='current input adapter and replay; tail lift and ZTL advisory; shared optimizer/calendar unchanged',
        cache_provenance=cache_provenance, current_commit=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        measured_at=datetime.now(timezone.utc).isoformat(), scipy_version=scipy_version,
        case_count=len({r['case_id'] for r in records}), source_hashes=initial_hashes,
        source_changed_during_campaign=source_hashes()!=initial_hashes))
    for name,value in (('results.json', report), ('outputs.json', outputs)):
        (args.output/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    (args.output/'report.md').write_text(markdown(report))
    print(json.dumps(report['summary'],indent=2),flush=True)
    return int(args.strict and (report['summary']['errors']
        or report['summary']['objective_regressions']
        or report['metadata']['source_changed_during_campaign']))


if __name__ == '__main__':
    raise SystemExit(main())
