# Priorita di fattibilita e validazione offline — 29 settembre 2026

Commit di partenza: `e331503c36445ee526c2edfac50d9229d3cfa213` (`main`). Riferimenti remoti aggiornati prima del lavoro e prima della consegna. I due dump locali preesistenti sono esclusi dal commit e preservati.

## Modifiche e logica

Il confronto delle soluzioni complete usa la tupla `(presenza_violazioni, ritardo_totale, numero_violazioni, score_storico)`. Per soluzioni fattibili ritardo e numero sono zero. Una soluzione fattibile vince quindi anche con score arbitrariamente maggiore; non si usa una penalita finita come garanzia. Fra percorsi non fattibili si minimizzano prima i minuti di ritardo, poi il conteggio, poi lo score. La parita e esatta, senza tolleranze arbitrarie. Esempio coperto: due fermate violate per 3 minuti complessivi battono una fermata violata per 100 minuti.

La stessa chiave e usata in enumerazione fino a 8 fermate, scambi/inversioni/rilocazioni locali, confronto multistart e confronto con ordine operatore. I pesi dello score numerico restano identici, cosi come ZTL/sponda (avvisi), cache OSRM, mezzanotte e assegnazioni manuali. Il test storico della penalita finita e il solo test esistente aggiornato: conserva la dimostrazione dello score paradossale e ora richiede che vinca la soluzione fattibile.

Per 1-15 fermate, se la ricerca non trova una soluzione senza violazioni, un fallback dinamico per sottoinsiemi verifica la fattibilita con tempi di matrice fissi e finestre della stessa giornata: conserva il completamento piu anticipato per (insieme visitato, ultima fermata), ammette attesa e ricostruisce una sequenza testimone. Le alternative di finestra vengono selezionate per il primo completamento fattibile. Il rientro non ha una finestra aggiuntiva. Costo massimo O(N^2 2^N), memoria O(N 2^N), attivazione solo in caso di risultato inizialmente non fattibile. Nessuna chiamata routing aggiuntiva con matrici complete; il percorso di fallback stradale continua a usare la cache locale. Non si afferma un ottimo di km/tempo per il testimone. Oltre 15 fermate resta una ricerca euristica: la priorita e assoluta fra candidati, ma non viene provata l'esistenza di un percorso fattibile.

Se non esiste un percorso fattibile il giro rimane programmabile. Oltre 8 fermate il minor ritardo e quello dei candidati esplorati, non un ottimo globale dimostrato. Anche la scelta storica delle finestre nei percorsi impossibili mantiene la sua euristica; questo task non prova un ottimo su tutte le combinazioni di finestre.

## API, salvataggio e interfaccia

- Giro: `violations_count`, `total_lateness_min`, `total_wait_min`, `time_window_violations`.
- Fermata: `arrivo_fisico`, `inizio_servizio`, `lateness_min`, `time_window_violation` (null se assente).
- Dettaglio violazione: ID/nome/ordine, finestre richieste e scelta, arrivo fisico, inizio/fine servizio, minuti di ritardo e warning. Ritardo = max(0, fine scarico − chiusura).
- `arrivo_stimato` resta inizio servizio dopo l'attesa; `attesa_min` e `partenza_stimata` restano invariati. Orari HH:MM; ritardo numerico non arrotondato prima del confronto.
- Entrambi gli ingressi pubblici (ottimizzazione e ricalcolo manuale), risposta HTTP e lettura da storico espongono i campi. Una colonna nullable Text `deliveries.optimizer_details`, aggiunta dalla migrazione idempotente esistente, conserva i dettagli esatti per i nuovi salvataggi. Nessun dato storico viene riscritto; i giri precedenti vengono ricostruiti alla precisione dei tempi tappa/attese gia salvati. Le diagnosi rappresentano il piano, non i tempi effettivi di esecuzione.
- Anteprima: alert urgente “Finestre orarie non rispettate” solo per conteggio positivo, badge sulla fermata, arrivo fisico e inizio scarico separati nella stessa colonna. Restano attesa, ripartenza, avvisi operativi e possibilita di confermare. Riutilizzati stili e contenitore responsive esistenti.

## Benchmark prima/dopo

Prima delle modifiche al motore e stato eseguito il runner esistente, salvato in [optimizer-priorities-before.json](optimizer-priorities-before.json). Dopo e stato rieseguito lo stesso runner: [optimizer-benchmark-results.json](optimizer-benchmark-results.json). Il suo `before` interno resta il Punto 1 immutabile `81f5121`; il confronto di questo task e invece tra i campi `after` dei due file. Oracolo Held–Karp e fixture non modificati.

54 confronti diretti passati: nessun cambiamento in km, durata, score, numero violazioni o attese. Tutti i risultati finali sono fattibili (ritardo zero). Riferimenti con finestre sono testimoni verificati indipendentemente, non ottimi dichiarati. Matrici direzionali/tempi non proporzionali, finestre eterogenee, tre ordini iniziali, rientro si/no restano coperti.

| Fermate | Km prima/dopo | Minuti prima/dopo | Score prima/dopo | Violazioni | Attesa min | Runtime ms prima/dopo |
|---|---|---|---|---|---|---|
| 5 | 70.0 / 70.0 | 140.0 / 140.0 | 1470.0 / 1470.0 | 0 / 0 | 0 / 0 | 10.2 / 13.7 |
| 8 | 96.0 / 96.0 | 192.0 / 192.0 | 2016.0 / 2016.0 | 0 / 0 | 0 / 0 | 3679.8 / 4118.6 |
| 9 | 96.0 / 96.0 | 192.0 / 192.0 | 2016.0 / 2016.0 | 0 / 0 | 0 / 0 | 48.1 / 143.5 |
| 10 | 98.0 / 98.0 | 196.0 / 196.0 | 2058.0 / 2058.0 | 0 / 0 | 0 / 0 | 121.7 / 129.8 |
| 12 | 102.0 / 102.0 | 204.0 / 204.0 | 2142.0 / 2142.0 | 0 / 0 | 0 / 0 | 142.5 / 234.6 |
| 15 | 106.0 / 106.0 | 212.0 / 212.0 | 2226.0 / 2226.0 | 0 / 0 | 0 / 0 | 940.0 / 567.0 |

Caso noto a 9 fermate: 96 km conservati (gap 0% rispetto al riferimento esatto); tutti e sei i casi grid restano ottimali. Campioni di wall-clock singoli, con carico macchina variabile e verifiche concorrenti: non dimostrano accelerazione o regressione stabile. Nessuna soglia temporale nei test. La costruzione dei dettagli pubblici avviene soltanto per i risultati finali per evitare costo superfluo su ogni permutazione. Il fallback esatto puo aumentare il costo dei casi inizialmente impossibili, senza modificare quelli gia fattibili.

## Test e limiti

Nuovi test Python: priorita assoluta anche con score enorme; minor ritardo prima del conteggio; chiave su tutti i rami; doppia finestra e mezzanotte; arrivo/attesa/servizio/ripartenza; API optimize/manual e salvataggio/ricaricamento; migrazione idempotente; fallback 3/9/15 fermate e confronto con simulatore indipendente a enumerazione; runner offline, energia, dati invalidi, opt-in sintetico e separazione holdout. Nuovi test JavaScript: nessun falso allarme, alert e cliente evidenziati, campi orari, escape del nome e conferma ancora disponibile.

Il comando Python di sistema non ha pytest: le verifiche sono eseguite con `.venv/Scripts/python.exe`. Il comando standard `python -m pytest tests -q` nell'ambiente ha prodotto 170 passed, 1 skipped, 50 errori di setup (102.05 s): PermissionError Windows sulla cartella temporanea pytest preesistente. Non sono stati cambiati test/ACL per aggirarlo; verificato poi con `-p no:cacheprovider --basetemp=<nuova cartella temporanea>`. Esito completo con il metodo alternativo: **220 passed, 1 skipped, 407 warning di deprecazione, 0 failed/error, 86.69 s**. Lo skip riguarda il test PostgreSQL reale non configurato localmente.

JavaScript: `node --test tests/*.cjs`, 11 passed, 0 failed. Benchmark: 54 scenari, tutti i confronti score/fattibilita passati. Test mirati: 25 passed. `git diff --check` senza errori. Docker non disponibile localmente; test PostgreSQL reale richiede TEST_POSTGRES_URL ed e saltato localmente. La CI esegue PostgreSQL, suite Python/JS, build container e verifica pg_dump/pg_restore.

CI: il risultato sul commit finale deve essere letto dopo il push; viene riportato nella consegna insieme allo SHA, senza creare un secondo commit solo per autocitare il primo.

## Dati reali e file coinvolti

Formato e istruzioni: [optimizer-real-fixtures.md](optimizer-real-fixtures.md). Runner `tests/run_real_optimizer_benchmark.py`; directory separate `tests/fixtures/optimizer_real/development` e `validation`. Report vuoti versionati per entrambi: count=0, statistiche null. Mancano i 15-20 giri anonimizzati con matrici salvate, ordini operatore, finestre/scarichi e split congelato. Nessun risparmio reale dichiarato.

File applicativi: `app/optimizer.py`, `app/routers/routes.py`, `app/models.py`, `app/main.py`, `static/dashboard/js/core.js`. Test: `tests/test_optimizer_improvements.py` (solo bug storico), `tests/test_optimizer_priorities.py`, `tests/test_optimizer_preview.cjs`, `tests/test_real_optimizer_benchmark.py`, nuovo runner e due directory vuote. Documentazione: questo report, formato fixture, snapshot prima, risultati benchmark aggiornati e due report dataset vuoti.
