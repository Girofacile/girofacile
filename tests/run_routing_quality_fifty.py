"""Compare the same fifty deliveries on two, three, four and five vehicles.

Both current fleet strategies run on identical frozen road data. Each returned
plan is independently replayed; a known feasible witness proves that all fifty
deliveries are serviceable, without claiming global optimality at this scale.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from run_routing_quality_audit import (effective_case, first_difference, inspect_answer,
    reference_for, serializable_case)
from routing_quality_oracle import objective, plan_metrics
from routing_quality_fleet import run_fleet
from routing_quality_fifty import fifty_cases


def campaign(variants=True):
    records, answers = [], []
    cases = fifty_cases()
    for case in cases:
        for strategy in ('efficient', 'balanced'):
            reference = reference_for(case, strategy)
            order = list(range(50))
            shuffled = order[:]
            random.Random(502345).shuffle(shuffled)
            inputs = [('original', order)]
            if variants:
                inputs += [('reverse', order[::-1]), ('shuffle', shuffled), ('repeat', order)]
            first = None
            for variant, permutation in inputs:
                answer = run_fleet(case, strategy, input_order=permutation)
                check = inspect_answer(case, strategy, answer, reference)
                actual = plan_metrics(effective_case(case), answer['routes'])
                rank = objective(actual, strategy)
                if first is None:
                    first = (answer['routes'], rank)
                elif variant == 'repeat' and (answer['routes'] != first[0] or first_difference(rank, first[1])):
                    check['errors'].append('identical_input_not_deterministic')
                elif variant in ('reverse', 'shuffle') and first_difference(rank, first[1]):
                    check['observations'].append('input_order_changes_objective')
                records.append(dict(case_id=case['id'], scenario=case['profile'],
                    vehicles=len(case['resources']), strategy=strategy, variant=variant,
                    distribution=[len(route) for route in answer['routes']],
                    available_per_vehicle=case['resources'][0]['capacita_colli'],
                    runtime_ms=round(answer['elapsed_ms'], 3),
                    external_calls=answer['external_calls'],
                    diagnostics=answer['diagnostics'], **check))
                answers.append(dict(case_id=case['id'], strategy=strategy, variant=variant,
                                    input_order=permutation, answer=answer))
                print(f"{case['id']} / {strategy} / {variant}: "
                    f"{actual['served']}/50, {len(check['errors'])} errors, "
                    f"{answer['elapsed_ms']:.1f} ms", flush=True)
    summary = dict(cases=len(cases), runs=len(records),
        errors=sum(len(row['errors']) for row in records),
        full_coverage=sum(row['actual']['served'] == 50 for row in records),
        coverage_gap_runs=sum(row['actual']['served'] < 50 for row in records),
        minimum_served=min(row['actual']['served'] for row in records),
        input_order_sensitive=sum('input_order_changes_objective' in row['observations'] for row in records),
        worse_than_witness=sum('worse_than_feasible_witness' in row['observations'] for row in records),
        external_calls=sum(row['external_calls'] for row in records))
    return dict(summary=summary, records=records), cases, answers


def markdown(report):
    summary = report['summary']
    lines = ['# Cinquanta consegne su 2, 3, 4 e 5 mezzi', '',
        f"Motore esaminato: `{report['metadata']['engine_commit']}`. "
        'Destinatari, coordinate, carichi e matrice stradale sono identici nei quattro confronti.', '',
        f"Esecuzioni: **{summary['runs']}**; copertura completa: **{summary['full_coverage']}**; "
        f"errori operativi inattesi: **{summary['errors']}**; richieste esterne: **{summary['external_calls']}**.", '',
        f"**In {summary['coverage_gap_runs']} esecuzioni rimangono consegne fattibili non assegnate**; "
        f"la copertura minima è {summary['minimum_served']}/50. Il conteggio degli errori sopra "
        'riguarda vincoli e consistenza dei piani restituiti: non certifica la massima copertura.', '',
        '## Condizioni della prova', '',
        'Ogni consegna pesa 1 kg, occupa un collo e richiede 2 minuti di scarico. '
        'Si parte alle 08:00 dallo stesso deposito e si rientra al deposito. '
        'La capacità per mezzo è rispettivamente 25, 17, 13 e 10 consegne: '
        'servire tutte le cinquanta consegne richiede quindi di utilizzare tutti i mezzi disponibili.', '',
        'La prova di base ha un turno ampio e nessuna finestra cliente. '
        'La seconda prova aggiunge turni, pause e finestre cliente costruite attorno a '
        'un itinerario testimone verificato dal simulatore indipendente. '
        'Le scadenze del testimone non sono generate dal risultato del motore in esame. '
        'Le finestre cliente del profilo vincolato cambiano con il numero di mezzi: '
        'le differenze di tempo tra questi quattro profili non dipendono soltanto dalla dimensione della flotta.', '',
        'Entrambe le strategie sono provate con ordine originale, inverso, mescolato con '
        'seme fisso e una ripetizione identica. I tempi sotto sono del solo motore con '
        'dati congelati, senza database o provider, e non sono uno SLA di produzione.', '',
        '## Risultati sull’ordine originale', '',
        '| Scenario | Mezzi | Strategia | Consegne per mezzo | Servite | km totali | Durata giro più lungo | ms |',
        '| --- | ---: | --- | --- | ---: | ---: | ---: | ---: |']
    for row in report['records']:
        if row['variant'] != 'original':
            continue
        metrics = row['actual']
        label = 'Efficiente' if row['strategy'] == 'efficient' else 'Bilanciata'
        distribution = ' / '.join(map(str, row['distribution']))
        lines.append(f"| {row['scenario']} | {row['vehicles']} | {label} | {distribution} | "
            f"{metrics['served']}/50 | {metrics['km']:.2f} | {metrics['makespan']:.2f} min | {row['runtime_ms']:.1f} |")
    lines += ['', '## Qualità e limiti', '',
        f"Cambiando l’ordine degli input, l’obiettivo varia in {summary['input_order_sensitive']} esecuzioni. "
        f"Piani peggiori del testimone fattibile secondo la strategia scelta: {summary['worse_than_witness']}.", '',
        '**Queste prove non certificano l’ottimo globale di cinquanta consegne.** '
        'Misurano copertura, vincoli, stabilità e confronto con un piano fattibile indipendente. '
        'Il carico resta 50 kg e 50 colli; cambia la capacità per mezzo: i quattro risultati non rappresentano '
        'la stessa flotta con mezzi lasciati inutilizzati.', '',
        '```sh', 'python tests/run_routing_quality_fifty.py --strict',
        'python -m pytest tests/test_routing_quality_fifty.py -q', '```', '',
        'Input completi e piani sono salvati in `test-results/routing-quality-fifty/`. '
        'Il rapporto precedente rimane separato e conserva i risultati della prima campagna.', '']
    gaps = [row for row in report['records'] if row['actual']['served'] < 50]
    if gaps:
        lines += ['## Controesempi di copertura', '',
            '| Caso | Strategia | Ordine input | Servite | Ripartizione | Consegne non assegnate (ID) |',
            '| --- | --- | --- | ---: | --- | --- |']
        for row in gaps:
            identifiers = ', '.join(str(index + 1) for index in row['actual']['unassigned'])
            lines.append(f"| {row['case_id']} | {row['strategy']} | {row['variant']} | "
                f"{row['actual']['served']}/50 | {' / '.join(map(str, row['distribution']))} | {identifiers} |")
        lines += ['', 'Per entrambi i problemi il testimone indipendente e l’esecuzione con ordine '
            'originale servono tutte le cinquanta consegne. Le esclusioni osservate non dimostrano '
            'quindi un’impossibilità operativa: mostrano un limite della ricerca euristica globale.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'test-results/routing-quality-fifty')
    parser.add_argument('--no-variants', action='store_true')
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    report, cases, answers = campaign(variants=not args.no_variants)
    files = ['app/services/fleet_planning.py', 'app/services/fleet_search.py', 'app/optimizer.py',
             'app/services/driver_schedule.py', 'tests/routing_quality_fifty.py',
             'tests/routing_quality_fleet.py', 'tests/routing_quality_oracle.py',
             'tests/run_routing_quality_audit.py', 'tests/run_routing_quality_fifty.py']
    report['metadata'] = dict(engine_commit=subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        measured_at=datetime.now(timezone.utc).isoformat(), synthetic=True,
        source_hashes={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files})
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('results.json', report), ('inputs.json', [serializable_case(c) for c in cases]),
                        ('outputs.json', answers)]:
        (args.output / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    (args.output / 'report.md').write_text(markdown(report))
    print(json.dumps(report['summary'], indent=2), flush=True)
    return int(args.strict and report['summary']['errors'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
