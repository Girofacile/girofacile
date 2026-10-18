# Distribuzione multi-mezzo: confronto prima/dopo

Baseline: 1c4bb0969dc14b9da454d5a22019e1cd5e758ab4; checkout: 9446025c7e4b3971a9b193d55f1b5412c99933b8.
Coppie confrontate: **512**; esecuzioni totali: **1024**.
Stesse matrici, input, strategie, permutazioni e ripetizioni; nessun dato operativo o provider.
Sponda e ZTL rimangono preferenze con avviso.

| Strategia | Casi con più consegne | Consegne recuperate | Miglioramenti obiettivo | Regressioni |
|---|---:|---:|---:|---:|
| efficient | 11 | 11 | 129 | 0 |
| balanced | 7 | 8 | 133 | 0 |

Regressioni di copertura: **0**. Regressioni dell'obiettivo: **0**.
Errori invarianti prima/dopo: **0 / 0**. Richieste esterne: **0 / 0**.

| Strategia | Casi con consegne fattibili escluse prima/dopo | Peggiore del riferimento esatto prima/dopo |
|---|---:|---:|
| efficient | 8 / 0 | 80 / 0 |
| balanced | 6 / 0 | 87 / 0 |

| Caso | Strategia | Consegnate prima/dopo | km prima/dopo | minuti cumulativi prima/dopo |
|---|---|---:|---:|---:|
| curated-capacity-repacking | efficient | 5 / 6 | 7.00 / 8.00 | 70.0 / 80.0 |
| curated-capacity-repacking | balanced | 5 / 6 | 7.00 / 8.00 | 70.0 / 80.0 |
| curated-opposite-clusters | efficient | 4 / 4 | 84.00 / 44.00 | 168.0 / 88.0 |
| curated-opposite-clusters | balanced | 4 / 4 | 44.00 / 44.00 | 88.0 / 88.0 |
| curated-opposite-clusters-breaks | efficient | 4 / 4 | 84.00 / 44.00 | 248.0 / 168.0 |
| curated-opposite-clusters-breaks | balanced | 4 / 4 | 44.00 / 44.00 | 168.0 / 168.0 |
| curated-break-window-reassignment | efficient | 1 / 2 | 2.00 / 4.00 | 35.0 / 100.0 |
| curated-break-window-reassignment | balanced | 1 / 2 | 2.00 / 4.00 | 35.0 / 100.0 |
| curated-late-driver-start | efficient | 2 / 2 | 3.00 / 3.00 | 50.0 / 50.0 |
| curated-late-driver-start | balanced | 2 / 2 | 3.00 / 3.00 | 50.0 / 50.0 |
| curated-waiting-absorbs-break | efficient | 2 / 2 | 3.00 / 3.00 | 100.0 / 100.0 |
| curated-waiting-absorbs-break | balanced | 2 / 2 | 4.00 / 4.00 | 160.0 / 160.0 |
| curated-return-crosses-break | efficient | 2 / 2 | 4.00 / 4.00 | 100.0 / 100.0 |
| curated-return-crosses-break | balanced | 2 / 2 | 4.00 / 4.00 | 100.0 / 100.0 |
| curated-km-time-tradeoff | efficient | 2 / 2 | 17.00 / 17.00 | 14.0 / 14.0 |
| curated-km-time-tradeoff | balanced | 2 / 2 | 25.00 / 25.00 | 20.0 / 20.0 |

Km e minuti indicano risparmi diretti solo a parità di servizio e compatibilità. I minuti sono la somma delle durate dei giri, non il completamento di calendario della flotta. Le strategie hanno priorità diverse; gli scenari non stimano risparmi medi commerciali.
Per i casi grandi la ricerca ha un budget: non certifica un ottimo globale. I tempi del nucleo con dati isolati non sono uno SLA di produzione.
La baseline congela il servizio; optimizer e calendario condivisi sono quelli del checkout, identificati nei metadati. Gli output before/ e after/ contengono tutti i piani e i riferimenti.

    python tests/run_fleet_before_after.py

## Implementazione e compatibilità

La modifica è stata verificata sul commit `9446025c7e4b3971a9b193d55f1b5412c99933b8` nella [campagna CI](https://github.com/Girofacile/girofacile/actions/runs/39082349764). I risultati sopra sono misurati, non previsioni di risparmio commerciale.

- Sponda e ZTL restano preferenze con avviso. Si cerca una distribuzione compatibile, mantenendo la consegna quando non si riesce a rispettare la preferenza.
- La copertura ha priorità sugli avvisi. Efficient privilegia meno mezzi, poi durata cumulativa e km. Balanced privilegia più risorse, poi durata massima, somma dei quadrati delle durate, durata cumulativa e km.
- Fino a 7 fermate e 3 risorse si confrontano tutti i sottoinsiemi, gli ordini e le assegnazioni. L'ottimo riguarda il modello di orari dichiarati e l'obiettivo scelto, che non equivale alla sola distanza minima.
- Per i casi grandi si conserva l'inserimento iniziale come candidato, si costruiscono proposte geografiche flessibili e si provano riordini, trasferimenti, scambi e riparazioni tra giri. Le zone non impongono confini.
- La ricerca ha un budget deterministico configurabile con `FLEET_MAX_CANDIDATES`, predefinito tra 5.000 e 20.000 valutazioni aggiuntive, massimo 100.000. Il valore 0 mantiene l'inserimento iniziale sui casi grandi; la ricerca completa dei piccoli casi non viene troncata.
- Ogni alternativa è valutata sulla stessa matrice con il motore esistente di capacità, finestre, scarico, attesa, pause, turno e disponibilità. La cache locale conserva soltanto metriche; i giri finali sono rivalutati con ETA e dettagli completi.
- La durata massima è verificata sui minuti non arrotondati. Il confronto ignora soltanto il rumore di rappresentazione numerica, senza nascondere differenze reali dietro l'arrotondamento della UI.
- Reverse e shuffle restano prove distinte anche quando producono la stessa permutazione.
- Le revisioni manuali mantengono l'appartenenza ai mezzi scelta dall'operatore e consentono gli avvisi per sponda/ZTL.
- Nessuna migrazione, dipendenza aggiuntiva o nuova chiave API obbligatoria. Nessun ricalcolo automatico di storico o anteprime salvate.
- Nessuna modifica a prezzi, quote, formule energetiche, pagine, permessi, traffico/pedaggi o notifiche. La risposta della preview aggiunge soltanto i dati diagnostici `search`.

Sui problemi grandi non viene certificato un ottimo globale; una consegna non assegnata non dimostra l'impossibilità matematica di servirla. Nei 146 scenari piccoli, dopo la modifica, nessuna consegna fattibile è rimasta esclusa e nessun risultato è peggiore del riferimento della rispettiva strategia.

Restano comuni deposito, giorno e partenza. Le pause sono quelle dichiarate: non si cercano pause flessibili o partenze differenziate e non si verifica automaticamente la normativa sulle ore di guida. Volume e pallet richiedono ancora valutazione manuale. Le matrici congelate non certificano il traffico futuro.

## Prestazioni misurate

Su 100 esecuzioni stress del solo nucleo: mediana **427.9 ms**, p95 **1484.3 ms**, massimo **2080.2 ms**. La mediana precedente era 29.6 ms. La ricerca più approfondita usa più CPU; questi tempi del runner CI non sono uno SLA di produzione.

Nelle 24 ripetizioni identiche non ci sono divergenze. Nei 96 riordinamenti degli input, le variazioni degli indicatori passano da 3 a 0. Questo risultato sui casi verificati non è una garanzia generale di indipendenza dall'ordine per la ricerca limitata.

## Test eseguiti e limite residuo della CI

- Test mirati: **116 superati**.
- Suite backend completa: **1.006 superati, 7 saltati, 23 avvisi**.
- Browser multi-mezzo: configurazione, anteprima, avvisi, spostamento manuale, salvataggio e programmazione superati a **390, 768, 1024 e 1440 px**.
- Job GPS e navigazione/gestione desktop-mobile superati.
- Frontend generale: **163 superati, 1 fallito**.

Il job generale resta rosso per il test preesistente `tests/test_occasional_stops_ui.cjs:77`, che cerca nel markup una chiamata a `moveDelivery` non trovata. Il fallimento era presente prima dell'intervento; nessun controllo è stato disattivato. I passi successivi di quel job sono saltati dopo il fallimento. Il job dedicato ai flussi interessati è superato.

Evidenze: [simulazioni](https://github.com/Girofacile/girofacile/actions/runs/39082349764/job/117541738694), [browser](https://github.com/Girofacile/girofacile/actions/runs/39082349764/job/117541738801), [suite generale](https://github.com/Girofacile/girofacile/actions/runs/39082349764/job/117541738881).

L'[artifact dei risultati](https://github.com/Girofacile/girofacile/actions/runs/39082349764/artifacts/12119337633) contiene `before/`, `after/`, `comparison.json` e `report.md`; conservazione 30 giorni. I JSON includono tutti i piani, gli input mirati, le impronte dei file e i riferimenti indipendenti. Lo snapshot baseline è verificato tramite hash e non viene scaricato durante i test.

Comandi:

    python -m pytest tests -q -ra
    python -m pytest tests/test_fleet_quality_reference.py tests/test_fleet_planning.py tests/test_driver_schedule.py tests/test_fleet_search.py tests/test_fleet_search_budget.py tests/test_fleet_before_after.py -q -ra
    python tests/run_fleet_before_after.py
    python tests/check_fleet_ui.py

## File e commit

- `app/services/fleet_search.py`: ricerca sulla flotta.
- `app/services/fleet_planning.py`: integrazione, riuso della matrice e dettagli finali.
- `tests/test_fleet_search.py`, `tests/test_fleet_search_budget.py`, `tests/test_fleet_before_after.py`, `tests/test_fleet_planning.py`: regressioni.
- `tests/run_fleet_simulations.py`, `tests/run_fleet_before_after.py`, `tests/fixtures/fleet_planning_before_20261018.py`: campagna ripetibile e snapshot.
- `.github/workflows/tests.yml`: confronto automatico e browser multi-mezzo.
- `docs/fleet-planning.md` e questo rapporto: metodo, configurazione e risultati.

Commit del codice: `8b9ea4ef`, `eb16d8a7`, `9446025c`. Il rapporto iniziale resta in [fleet-simulation-results.md](fleet-simulation-results.md).
