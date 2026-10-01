"""Derive the report tables from the complete, retained benchmark evidence."""
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
MARKER = '\n## Risultati misurati\n'


def summary(records):
    expected = {(f,n,w,b) for f in ('urban','provincial','mixed')
                for n in (8,15,20,30,50) for w in (False,True) for b in (False,True)}
    if len(records) != 60 or {(r['family'],r['n'],r['windows'],r['return_depot']) for r in records} != expected:
        raise ValueError('Expected all 60 distinct cases; incomplete run')
    if any(r[k]['violations'] for r in records for k in ('operator','girofacile','best_known')):
        raise ValueError('Cannot aggregate infeasible routes as feasible savings')
    lines = [MARKER, '| Fermate | Casi migliorabili / 12 | Km Girofacile → migliore (somma) | Margine trovato aggregato | Margine mediano per giro | Ottimi km certificati / 12 |',
             '|---:|---:|---:|---:|---:|---:|']
    for n in (8,15,20,30,50):
        subset = [r for r in records if r['n']==n]
        before = sum(r['girofacile']['distance_m'] for r in subset)/1000
        after = sum(r['best_known']['distance_m'] for r in subset)/1000
        lines.append(f"| {n} | {sum(r['found_margin_km']>0 for r in subset)} | {before:.3f} → {after:.3f} | {100*(before-after)/before:.2f}% | {median(r['found_margin_pct'] for r in subset):.2f}% | {sum(r['margin_is_exact'] for r in subset)} |")
    improved = sum(r['found_margin_km']>0 for r in records)
    manual = sum(r['operator']['distance_m'] for r in records)
    current = sum(r['girofacile']['distance_m'] for r in records)
    best = sum(r['best_known']['distance_m'] for r in records)
    independent = sum(r['reference_independent']['distance_m']<r['girofacile']['distance_m'] for r in records)
    worse = sum(r['reference_independent']['distance_m']>r['girofacile']['distance_m'] for r in records)
    lines += ['', f'**{improved}/60 casi migliorabili; {60-improved} senza ulteriore riduzione trovata.** Il margine aggregato sul totale dei giri è {100*(current-best)/current:.2f}%. Tutti i giri manuali, Girofacile e migliori di riferimento sono fattibili.',
        '', f"Di questi miglioramenti, **{sum(r['found_margin_km']>=.1 for r in records)} sono almeno 100 metri**. Il conteggio include anche differenze minime sulla matrice discretizzata, che non vanno interpretate come risparmi fisici affidabili: per esempio un metro su 30 fermate è inferiore all'incertezza introdotta dall'arrotondamento degli archi.",
        '', 'Le somme aggregano istanze sovrapposte e non costituiscono una stima statistica del risparmio su una flotta. Il margine zero senza certificato non dimostra ottimalità.',
        '', f'Rispetto all’ordine geografico manuale simulato, Girofacile riduce i km totali da {manual/1000:.3f} a {current/1000:.3f} ({100*(manual-current)/manual:.2f}%). Nessun ordine iniziale simulato batte Girofacile: è coerente con il fatto che il motore lo conserva fra i candidati, non dimostra superiorità rispetto a un operatore esperto.',
        '', f'Il solver avviato dal solo ordine manuale trova meno km di Girofacile in **{independent}/60** casi e più km in **{worse}/60**. La ricerca avviata anche da Girofacile serve a misurare il margine senza perdere il suo lavoro; i risultati separati restano nel JSON.',
        '', '| Famiglia | Casi migliorabili / 20 | Margine trovato aggregato |', '|---|---:|---:|']
    for family in ('urban','provincial','mixed'):
        subset = [r for r in records if r['family']==family]
        old = sum(r['girofacile']['distance_m'] for r in subset)
        new = sum(r['best_known']['distance_m'] for r in subset)
        lines.append(f"| {family} | {sum(r['found_margin_km']>0 for r in subset)} | {100*(old-new)/old:.2f}% |")
    lines += ['', '### Tempi e casi esemplificativi', '', '| Fermate | CPU Girofacile mediana (s) | Wall Girofacile mediana (s) | CPU riferimento mediana (s) | Wall riferimento mediana (s) |', '|---:|---:|---:|---:|---:|']
    for n in (8,15,20,30,50):
        subset = [r for r in records if r['n']==n]
        values = [median(r[k][t] for r in subset) for k in ('production_timing','reference_timing') for t in ('cpu_s','wall_s')]
        lines.append('| '+str(n)+' | '+' | '.join(f'{x:.3f}' for x in values)+' |')
    lines += ['', 'Il riferimento include due ricerche fino a 3 secondi e, fino a 15 fermate, la certificazione fino a 5 secondi. Non è un confronto a parità di latenza.', '']
    for r in sorted(records,key=lambda r:r['found_margin_pct'],reverse=True)[:5]:
        lines.append(f"- `{r['id']}`: {r['girofacile']['distance_m']/1000:.3f} → {r['best_known']['distance_m']/1000:.3f} km, **−{r['found_margin_pct']:.2f}%**; durata {r['girofacile']['duration_s']/60:.1f} → {r['best_known']['duration_s']/60:.1f} min. Fattibilità preservata; ottimo km {'certificato' if r['margin_is_exact'] else 'non certificato'}.")
    lines += ['', '### Interpretazione operativa', '', 'I casi migliorati dimostrano che esistono ordini fattibili più corti di quelli trovati dal motore attuale. È ragionevole valutare una modalità di ottimizzazione più approfondita per giri grandi. Non dimostrano che un altro gestionale otterrebbe questi risultati, né che integrare un solver produrrebbe automaticamente gli stessi benefici su dati reali.', '', 'Prima di cambiare il motore servono un campione reale anonimizzato, vincoli operativi completi e un confronto a pari budget. Un pilota potrebbe mantenere il risultato attuale come candidato e spendere tempo aggiuntivo soltanto quando richiesto. Il software di produzione resta invariato in questo commit.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    report = json.loads((ROOT/'docs/optimizer-road-margin-results.json').read_text(encoding='utf-8'))
    target = ROOT/'docs/optimizer-road-margin.md'
    target.write_text(target.read_text(encoding='utf-8').split(MARKER)[0] + summary(report['records']),encoding='utf-8')
