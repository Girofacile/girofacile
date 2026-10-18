# Riordino completo dei giri fino a 8 fermate

Codice verificato: `fdb547f3d1bd906dad644723796a1073b7200b7b`.
[Campagna CI](https://github.com/Girofacile/girofacile/actions/runs/39119042056).

## Comportamento implementato

La suddivisione geografica flessibile e l'assegnazione tra mezzi continuano a usare il motore della flotta e una sola matrice stradale. Dopo questa fase:

- ogni giro da 1 a 8 fermate viene riordinato confrontando tutte le permutazioni, anche con più di 8 consegne totali nella flotta;
- 8 fermate richiedono 40.320 ordini; la fase non è troncata da `FLEET_MAX_CANDIDATES`;
- vengono rispettati capacità kg/colli, finestre, attese, scarico, pause, turno, durata massima e disponibilità;
- il confronto usa durata non arrotondata e poi km, coerentemente con entrambe le strategie della flotta a composizione fissa; in parità conserva l'ordine corrente;
- i giri oltre 8 fermate mantengono il metodo attuale, senza divisioni artificiali per rientrare nella soglia;
- sponda e ZTL rimangono preferenze con avviso, anche nelle revisioni manuali;
- le assegnazioni manuali mantengono le consegne sui mezzi scelti dall'operatore.

L'ottimo dimostrato è l'ordine del singolo giro con **consegne, mezzo, orario e vincoli fissati**. Non certifica la migliore ripartizione globale delle 50 consegne. La prova globale già esistente fino a 7 fermate e 3 risorse viene riutilizzata quando disponibile, evitando lavoro ridondante.

Il valutatore preparato condivide il selettore delle finestre e l'aritmetica delle pause con il valutatore canonico. Precalcola soltanto finestre, carico, scarichi e letture della matrice del gruppo, senza costruire copie dei dettagli ETA per ogni ordine. Il vincitore viene verificato dal valutatore canonico e i dettagli finali sono ricostruiti normalmente. Una discrepanza del vincitore attiva il passaggio canonico completo; questo controllo, da solo, non proverebbe l'equivalenza di tutti gli ordini, verificata anche dai test esaustivi.

## Prove specifiche

| Prova | Risultato |
|---|---|
| Tutti gli ordini di 8 fermate su matrice direzionale | 40.320 permutazioni distinte, una visita per ordine |
| Valutatore preparato contro canonico, 8 fermate con pause e finestre multiple | Tutti i 40.320 ordini confrontati, stessa fattibilità e stessi tempi/km |
| Giri da 9 fermate | Nessun affinamento aggiuntivo; ordine dell'euristica preservato |
| Budget euristico zero | Riordino dei piccoli giri comunque completo |
| Gruppi manuali | Appartenenza preservata; salvataggio e programmazione senza nuovo calcolo |
| Avvisi sponda/ZTL | Mantenuti; non trasformati in blocchi |
| Capacità, pause in viaggio/scarico/rientro, attese, finestre doppie, turno e arrotondamento del limite | Casi positivi e negativi superati |

Il riordino manuale sotto soglia ora usa la stessa priorità della flotta (durata, poi km) e la stessa gestione delle finestre dell'automatico; precedentemente usava il solutore del giro singolo, che privilegiava km prima della durata. Sopra 8 fermate il solutore manuale classico resta quello precedente. Il motore del giro singolo mantiene il proprio comportamento; riceve soltanto parametri opzionali interni per riutilizzare finestre già lette.

## Simulazione di 50 consegne

| Composizione dei gruppi | Permutazioni esatte | Tempo solo affinamento | CPU |
|---|---:|---:|---:|
| 6 giri da 8 + 1 da 2 | 241.922 | 3.916 s | 3.915 s |
| 5 giri da 8 + 1 da 9 + 1 da 1 | 201.601 | 3.298 s | 3.297 s |

Nel caso misto, il giro da 9 rimane invariato. Le prove fissano i gruppi per misurare precisamente la fase finale; non affermano che l'assegnazione di quelle consegne sia globalmente ottima.

Sono stati eseguiti anche due flussi completi del motore su 50 consegne:

- distribuzione automatica: tutte le 50 consegne assegnate, 1.503 s;
- gruppi fissati 6×8+2: tutte le 50 consegne assegnate, 4.705 s, prova dell'ordine per tutti i 7 giri attivi e 241.922 permutazioni;
- in ciascun flusso: una matrice, nessuna richiesta esterna e nessun errore nel controllo indipendente di percorrenza, pause, ETA, identità o copertura.

Tempi del runner CI con dati e matrici congelati, senza latenza di database/provider: non sono uno SLA di produzione.

## Confronto generale e regressioni

La campagna storica mantiene 196 scenari e 512 coppie prima/dopo (1.024 invocazioni), con la baseline di inserimento `1c4bb0969dc14b9da454d5a22019e1cd5e758ab4`. Questo confronto include anche gli interventi precedenti; non misura soltanto il contributo dell'ultima fase.

- Regressioni di copertura: 0.
- Regressioni dell'obiettivo scelto: 0.
- Errori invarianti dopo il calcolo: 0.
- Richieste esterne nella simulazione: 0.
- Nei 146 casi piccoli con riferimento globale indipendente, nessuna consegna fattibile esclusa e nessun risultato peggiore del riferimento della strategia.
- Le due prove di affinamento da 50 e i due flussi completi aggiuntivi rimangono separati dal conteggio storico delle 512 coppie.

## Suite e browser

- Test mirati: **149 superati**.
- Backend completo: **1.039 superati, 7 saltati, 23 avvisi**.
- Browser: configurazione, anteprima, avvisi, spostamento manuale, salvataggio e programmazione superati a **390, 768, 1024 e 1440 px**.
- Job GPS e navigazione/gestione superati.
- Frontend generale: **163 superati, 1 fallito**, lo stesso test preesistente `tests/test_occasional_stops_ui.cjs:77` sul markup di `moveDelivery`. Il job generale resta rosso e i suoi passi successivi sono saltati; nessun controllo è stato disattivato.

Evidenze: [test e simulazioni](https://github.com/Girofacile/girofacile/actions/runs/39119042056/job/117650675966), [browser](https://github.com/Girofacile/girofacile/actions/runs/39119042056/job/117650676215), [suite generale](https://github.com/Girofacile/girofacile/actions/runs/39119042056/job/117650676150).

L'[artifact](https://github.com/Girofacile/girofacile/actions/runs/39119042056/artifacts/12133572668) conserva i JSON prima/dopo, il confronto, i piani e `route-exact-benchmark.json` per 30 giorni. Nessun dato operativo, email o pagamento reale nei test.

## File, configurazione e riproduzione

Produzione:

- `app/services/fleet_search.py`: affinamento esaustivo dei gruppi.
- `app/services/fleet_route_evaluator.py`: valutazione preparata senza dettagli grafici.
- `app/services/fleet_planning.py`: integrazione automatica/manuale e diagnostica.
- `app/optimizer.py`: parametri interni opzionali per finestre e scarico già letti.

Test e CI:

- `tests/test_fleet_route_exact.py`
- `tests/test_fleet_route_exact_api.py`
- `tests/test_fleet_route_evaluator.py`
- `tests/run_fleet_route_exact_benchmark.py`
- `tests/run_fleet_simulations.py`
- `.github/workflows/tests.yml`

Documentazione: `docs/fleet-planning.md` e questo rapporto. Nessuna migrazione, nuova dipendenza o chiave API. Nessuna modifica grafica, di prezzi/quote o ai giri storici. I nuovi calcoli aggiungono `search.route_refinement` e `search.exact_route_evaluations`, distinguendo la prova locale dalla prova globale.

    python -m pytest tests -q -ra
    python tests/run_fleet_before_after.py
    python tests/run_fleet_route_exact_benchmark.py
    python tests/check_fleet_ui.py
