"""Riassunto del confronto completo GiroFacile / OR-Tools (tabelle per il rapporto)."""
import json
import sys
from pathlib import Path

RUNS = (('girofacile', 'GiroFacile'), ('ortools_same_time', 'OR-Tools, stesso tempo'),
        ('ortools_long', 'OR-Tools, 30 s'), ('ortools_from_girofacile', 'OR-Tools da GiroFacile, +10 s'))


def main(path):
    records = json.loads(Path(path).read_text(encoding='utf-8'))['records']
    print(f'Casi: {len(records)}\n')
    print('| Motore | Piani validi | Consegne non servite (testimone le serve) | Avvisi sponda/ZTL | Km totali | Minuti totali | Secondi medi |')
    print('|---|---:|---:|---:|---:|---:|---:|')
    for key, label in RUNS:
        valid = [r for r in records if (r[key].get('metrics') or {}).get('feasible')]
        missed = sum(r['witness_served'] - r[key]['metrics']['served'] for r in valid)
        print(f"| {label} | {len(valid)}/{len(records)} | {missed} | {sum(r[key]['metrics']['mismatches'] for r in valid)} | "
              f"{sum(r[key]['metrics']['km'] for r in valid):,.1f} | {sum(r[key]['metrics']['minutes'] for r in valid):,.0f} | "
              f"{sum(r[key]['elapsed_ms'] for r in records) / len(records) / 1000:.1f} |")
    print('\nVittorie contro GiroFacile (obiettivo «Riduci chilometri e tempi»):\n')
    print('| Motore | Vince OR-Tools | Pari | Vince GiroFacile |')
    print('|---|---:|---:|---:|')
    for key, label in RUNS[1:]:
        outcomes = [r['winner_' + key] for r in records]
        print(f"| {label} | {outcomes.count('ortools')} | {outcomes.count('pari')} | {outcomes.count('girofacile')} |")
    print('\nPer gruppo (km a parità di consegne servite, solo casi dove entrambi servono lo stesso numero):\n')
    groups = {}
    for r in records:
        groups.setdefault((r['stops'], r['vehicles'] if r['stops'] > 50 else '2-5', r['family']), []).append(r)
    print('| Consegne | Mezzi | Famiglia | Casi | Non servite G / O-30 / O+G | Km G | Km O+G | Km O-30 |')
    print('|---:|---|---|---:|---|---:|---:|---:|')
    for (stops, vehicles, family), rows in sorted(groups.items(), key=lambda item: str(item[0])):
        miss = lambda key: sum(r['witness_served'] - (r[key].get('metrics') or {}).get('served', 0) for r in rows)
        km = lambda key: sum((r[key].get('metrics') or {}).get('km', 0) for r in rows)
        print(f"| {stops} | {vehicles} | {family} | {len(rows)} | {miss('girofacile')} / {miss('ortools_long')} / {miss('ortools_from_girofacile')} | "
              f"{km('girofacile'):,.1f} | {km('ortools_from_girofacile'):,.1f} | {km('ortools_long'):,.1f} |")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'docs/ortools-full-comparison-2026-11-02.json')
