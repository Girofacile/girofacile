# Confronto completo GiroFacile / OR-Tools sui vincoli reali — 2 novembre 2026

Segue il [confronto preliminare](ortools-comparison-2026-11-02.md), che copriva
7 scenari senza pause, doppie fasce, sponda e ZTL. Qui si usano tutti i vincoli
del multi-mezzo e budget di tempo confrontabili. Il software operativo non è
stato modificato: OR-Tools è installato solo per l'esperimento.

## In breve

- **OR-Tools da solo** fa molti meno chilometri, ma nei casi con fasce strette
  lascia fuori consegne che si potevano servire (fino a 10 su 400 nei casi grandi).
- **OR-Tools che parte dal piano di GiroFacile** («combinato») mantiene le
  stesse consegne servite, riduce i chilometri del **14%** sui problemi da 50
  consegne e del **30%** su quelli da 100, riduce gli avvisi di sponda/ZTL ed è
  stato migliore o pari in 46 casi su 47. Nell'unico caso restante non ha
  prodotto un piano: in produzione resterebbe quello di GiroFacile.
- Il motore attuale peggiora con la dimensione: sui problemi da 100 consegne e
  8–10 mezzi fa il 40–45% di chilometri in più di OR-Tools.

**Raccomandazione:** integrare OR-Tools in modalità combinata (GiroFacile
costruisce il piano, OR-Tools lo migliora, il calendario canonico verifica e si
tiene il migliore). Non usarlo da solo.

## Casi

47 problemi con un **piano testimone** indipendente, costruito senza i motori in
esame, che dimostra quante consegne sono servibili:

- 43 problemi già usati per il motore multi-mezzo (`fleet_upgrade_cases`,
  `fleet_constraint_holdout`): 50 consegne, da 2 a 5 mezzi, partenze 7:30/8:00,
  due pause fisse per autista, una o due fasce di scarico, sponda e ZTL come
  preferenze, capacità in kg e colli, turni e disponibilità diversi;
- 4 problemi nuovi da 100 consegne con 8 e 10 mezzi (`large_case`, stesso metodo,
  famiglie «fasce e turni» e «vincoli combinati»).

Matrici stradali sintetiche congelate, nessun traffico, nessuna chiamata esterna.

## Motori

| Motore | Tempo |
|---|---|
| GiroFacile, servizio `distribute` reale, strategia «Riduci chilometri e tempi» | budget standard (media 17 s, massimo 106 s) |
| OR-Tools da solo | stesso tempo impiegato da GiroFacile (minimo 1 s) |
| OR-Tools da solo | 30 s |
| OR-Tools combinato: parte dal piano di GiroFacile | 10 s in più |

OR-Tools 9.15.6755, inserimento parallelo più economico e Guided Local Search.
Il modello riproduce le regole del calendario canonico: partenza comune alle
8:00, pause fisse in cui la guida si ferma ma lo scarico non si interrompe,
inizio scarico nell'unione delle fasce ridotte della durata dello scarico,
rientro entro fine turno e disponibilità, tempi in secondi arrotondati per
eccesso. Sponda e ZTL incompatibili costano l'equivalente di 20 km, una
consegna esclusa 1.000 km. Ogni piano è giudicato dallo stesso verificatore
indipendente (`routing_quality_oracle`), non dal punteggio dei motori.

## Risultati

Totali sui casi in cui tutti e quattro i motori hanno prodotto un piano.

**Problemi da 50 consegne (42 casi):**

| Motore | Consegne servibili non servite | Avvisi sponda/ZTL | Km | Minuti |
|---|---:|---:|---:|---:|
| GiroFacile | 1 | 27 | 6.130,9 | 25.359 |
| OR-Tools, stesso tempo | 12 | 21 | 5.073,2 (-17,3%) | 24.479 |
| OR-Tools, 30 s | 8 | 20 | 4.987,6 (-18,6%) | 23.947 |
| **Combinato** | **1** | **20** | **5.259,0 (-14,2%)** | **24.607 (-3,0%)** |

**Problemi da 100 consegne, 8 e 10 mezzi (4 casi):**

| Motore | Consegne servibili non servite | Avvisi sponda/ZTL | Km | Minuti |
|---|---:|---:|---:|---:|
| GiroFacile | 2 | 6 | 2.124,4 | 6.904 |
| OR-Tools, stesso tempo | 6 | 0 | 1.250,3 (-41,1%) | 6.181 |
| OR-Tools, 30 s | 10 | 0 | 1.223,2 (-42,4%) | 5.970 |
| **Combinato** | **2** | **4** | **1.481,1 (-30,3%)** | **5.983 (-13,3%)** |

**Confronto caso per caso contro GiroFacile (tutti i 47 casi):**

| Motore | Migliore | Pari | Peggiore |
|---|---:|---:|---:|
| OR-Tools, stesso tempo | 31 | 0 | 16 |
| OR-Tools, 30 s | 36 | 0 | 11 |
| Combinato | 45 | 1 | 1 |

«Migliore» segue l'obiettivo della strategia: prima più consegne, poi meno
avvisi, poi meno km, minuti e mezzi. Le sconfitte di OR-Tools da solo sono
quasi tutte consegne perse. L'unica «sconfitta» del combinato è il caso
`upgrade-holdout-3-windows_shifts-2037101312`, dove non ha restituito un piano
entro il tempo: il piano di partenza di GiroFacile non è stato accettato come
punto di partenza dal modello, probabilmente per l'arrotondamento in secondi
vicino al limite di una fascia. In produzione si terrebbe il piano di GiroFacile.

Nei due problemi grandi con «vincoli combinati» sia GiroFacile sia il combinato
lasciano fuori una consegna che il testimone serve: il combinato parte da
GiroFacile e non l'ha recuperata.

## Altre osservazioni

- Con pesi «lessicografici» enormi (ordine rigido delle priorità) OR-Tools da
  solo perdeva più consegne: la ricerca locale non riesce a reinserirle. I pesi
  pratici usati qui funzionano meglio.
- Dare a OR-Tools più tempo (30 s) riduce i km ma non risolve le consegne perse
  nei casi stretti: serve il piano iniziale di GiroFacile.
- I minuti totali scendono meno dei km: l'obiettivo privilegia i chilometri.

## Limiti

- Dati sintetici: nessuna giornata reale di un cliente, nessun traffico.
- Solo la strategia «Riduci chilometri e tempi»; «Distribuisci il lavoro» non è
  stata modellata in OR-Tools.
- Una sola esecuzione per caso su un PC Windows: le ricerche a tempo possono
  dare risultati leggermente diversi su altre macchine.
- Autonomia dei mezzi elettrici e prezzi non modellati, come nel motore attuale.

## Prossimi passi proposti

1. Integrare OR-Tools in modalità combinata dietro un'impostazione, con il
   motore attuale come riserva e il calendario canonico come giudice finale.
2. Verificare le prime giornate reali e il caso con «nessun piano».
3. Modellare la strategia «Distribuisci il lavoro».

## Riproduzione

```text
python -m pip install -r tests/requirements-ortools-benchmark.txt
python tests/run_ortools_full_comparison.py
python tests/summarize_ortools_full_comparison.py
python -m pytest tests/test_ortools_full_comparison.py -q
```

`ortools-full-comparison-2026-11-02.json` contiene, per ogni caso e motore,
metriche, consegne non servite, ordini mezzo per mezzo e tempi di calcolo.
Codice di partenza `4c7b6ef`, Python 3.12, OR-Tools 9.15.6755.
