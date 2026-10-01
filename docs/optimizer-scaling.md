# Ricerca deterministica oltre 8 fermate

Baseline: `824816f252e89274ebed6ef22f2d59e8483cb51a`, CI verificata verde prima
del lavoro. Le priorità rimangono quelle di `solution_key`: fattibilità,
chilometri, durata, attese e avvisi. Per soluzioni impossibili resta il
precedente confronto ritardo/conteggio/score storico. Nessun nuovo peso
decide fra soluzioni fattibili.

## Ricerca precedente e nuova

Fino a 8 fermate sono conservati enumerazione completa, confronto e fallback
precedenti. Oltre 8 viene eseguita **tutta** la vecchia euristica: greedy,
swap e inversioni per quattro round; ordine operatore; multi-start/relocate
9–15; fallback di fattibilità fino a 15 quando necessario. Il suo risultato
rimane sempre un candidato e vince anche in caso di parità finale.

La ricerca aggiuntiva usa seed deterministici: risultato baseline, greedy
distance-first, ordine operatore e inverso, inverso greedy, nearest-neighbour
sulla distanza, cheapest insertion direzionale, lookahead sulle finestre e
insertion delle finestre se rimane budget sufficiente. Seed identici vengono
deduplicati; il numero di nomi distinti nei log può quindi essere inferiore.
Ogni seed completo viene valutato prima della ricerca locale. Seed parziali
non possono mai diventare la soluzione restituita.

Il lookahead controlla se visitare una fermata comprometterebbe la prossima
finestra in chiusura; usa il tempo per verificare vincoli, poi confronta i km.
L'insertion con finestre considera prima le consegne urgenti, ma sceglie la
posizione attraverso `solution_key`, quindi fattibilità e distanza prima
della durata. Non modifica la priorità del confronto finale.

La ricerca locale aggiunta alterna Or-opt 2, Or-opt 3, relocate/Or-opt 1,
swap e 2-opt. Ogni round parte da un ordine fisso e conserva la migliore
variante visitata. L'alternanza evita che un budget ridotto esplori soltanto
il primo tipo di mossa. Ogni seed riceve una quota deterministica dei
candidati rimanenti, anche a 16, 20, 30, 50 e più fermate. Massimo tre round
aggiuntivi per seed. Non esiste casualità nella ricerca.

Ogni mossa viene rigiocata sulla **matrice direzionale completa**, con
propagazione di viaggio, attese, scarichi e ritardi. Non si usano delta
simmetrici per inversioni. L'insertion usa soltanto la sostituzione valida
anche per archi direzionali `a→x + x→b − a→b`, con trattamento separato della
coda libera senza rientro.

## Budget: garanzia e limite espliciti

`OPTIMIZER_MAX_CANDIDATES` è il massimo numero di **valutazioni aggiuntive**
di sequenze, comprese quelle parziali dell'insertion con finestre. Il default
è `min(10000, max(100, 500000 // numero_fermate))`: 10.000 fino a 50 fermate,
5.000 a 100. Valori negativi diventano zero, valori non interi usano il
default, valori sopra 200.000 vengono limitati a 200.000. Con zero si
restituisce esattamente la baseline. Esaurire il budget non è un errore.

Un limite rigido inferiore al costo della vecchia ricerca non sarebbe
compatibile con la garanzia richiesta di non peggiorarla: per questo la
baseline è obbligatoria e misurata separatamente. Sopra 15 fermate effettua
al massimo `4*(n-1)^2 + 3` valutazioni di sequenze; segue una sola valutazione
finale. Il totale è quindi limitato da quel costo più budget aggiuntivo più
uno. Sotto 16 resta anche il fallback DP preesistente, limitato a 15 fermate.
Non si promette un tetto assoluto di millisecondi o di CPU su ogni macchina.

Il budget conta simulazioni di sequenze, non ogni confronto di un singolo
arco: nearest-neighbour/lookahead hanno costruzione polinomiale; cheapest
insertion globale considera O(n³) posizioni/arco, senza simulare ogni volta
l'intero percorso. La baseline resta O(n³) in visite alle fermate, dato il
numero fisso di round. Giri molto più grandi di quelli misurati richiedono
nuove misure prima di promettere latenza interattiva.

Il limite basato sul conteggio, invece che su scadenze wall-clock, garantisce
che macchine/carichi diversi non tronchino la ricerca in punti diversi.
Un budget più grande può cambiare l'allocazione fra seed: la garanzia è
rispetto alla baseline, non la monotonia fra tutti i possibili budget.

## Valutazione veloce e compatibilità

La valutazione delle varianti non costruisce copie di consegne o testi
orario destinati alla UI. Le finestre e gli avvisi del mezzo sono preparati
una volta. I risultati temporali identici vengono riutilizzati in una cache
**locale alla richiesta**, con chiavi esatte `(origine, destinazione,
orologio)` e massimo 8192 voci. Nessuna tolleranza o arrotondamento modifica
i vincoli. Le metriche numeriche sono testate contro il valutatore completo,
anche con due finestre, decimali, sponda/ZTL e ritardi.

Le consegne finali vengono prodotte dal valutatore canonico. Gli indici
della matrice restano disponibili soltanto internamente, anche con nomi,
coordinate o clienti duplicati. Non si ricostruisce l'identità dal nome.
Capacità, carburante, pedaggi, isolamento aziende, ordine manuale, snapshot,
storici, UI e flusso provider non sono modificati.

La ricerca usa esclusivamente la matrice ricevuta. Se assente, il percorso
esistente la costruisce una volta; cache incompleta o limiti del provider
possono già richiedere più richieste Table nella fase di costruzione.
**Le varianti non aggiungono alcuna chiamata** Table, Route, Mapbox o Google.

## Metriche e riproduzione

Il parametro interno facoltativo `diagnostics` di `_best_internal_sequence`
riceve `optimizer_strategy`, `candidates_evaluated`, `baseline_candidates`,
`additional_candidates`, `candidate_budget`, `optimization_budget_exhausted`,
`baseline_cpu_ms`, `optimization_cpu_ms`, `optimization_ms` e `seeds_evaluated`.
I tempi sono separati dall'oggetto risultato, per non rompere ripetibilità,
risposte API o salvataggi. Le valutazioni terminali del fallback sono contate;
le transizioni DP non sono sequenze complete e non rientrano nel conteggio.

```bash
python tests/run_optimizer_benchmark.py
# Equivalente, con selezione opzionale:
python tests/run_optimizer_scaling_benchmark.py --sizes 8 9 15 20 30 50
```

Il report corrente è `optimizer-scaling-results.json`. I vecchi report
time-weighted rimangono snapshot storici e non vengono sovrascritti.
`tests/optimizer_legacy_reference.py` congela il controllo della ricerca
precedente; non usa il nuovo valutatore né la nuova ricerca locale. Si
condividono soltanto i primitivi di vincoli/confronto rimasti equivalenti.

La suite misura 5/8/9/12/15/20/30/50 fermate, quattro famiglie sintetiche
(asimmetrica, cluster, trappola nearest-neighbour, finestre), con e senza
rientro: 64 scenari. Tutte le chiamate esterne falliscono intenzionalmente.
Gli oracoli sono indipendenti: Held–Karp lessicografico fino a 12 fermate
senza finestre, enumerazione di schedulazioni fattibili fino a 8 con
finestre. Oltre queste dimensioni si verifica la non regressione, non si
dichiara un ottimo globale. I tempi CPU/wall sono singoli campioni locali,
senza soglie fragili nei test. Nessun risparmio reale di carburante è
dedotto da questi dati sintetici.

La fixture Or-opt contiene un minimo locale asimmetrico verificato
esaustivamente per swap, inversione e relocate: 152 km. Il trasferimento
di un blocco di due fermate trova un testimone da 127 km; l'ablazione nel
report confronta i due insiemi di mosse con lo stesso budget.

## Quando valutare un solver esterno

Questo intervento non introduce dipendenze da solver. Oltre otto fermate
non certifica l'ottimo: un risultato invariato può essere già buono oppure
un minimo locale non superato con il budget disponibile. Per decidere se
introdurre OR-Tools servono anche istanze reali anonimizzate e confronti
a parità di vincoli, obiettivo lessicografico e budget.

Una fase successiva avrebbe senso soprattutto per finestre strette su
30–50 o più fermate, per richieste di un limite totale di latenza che
includa la baseline, o per problemi con più veicoli. Il benchmark attuale
misura un singolo giro e non dimostra vantaggi di un solver esterno.

## Risultati misurati (1 ottobre 2026)

64 scenari: **23 migliorati, 41 invariati, nessun peggioramento** secondo `solution_key`. Tutti erano e restano fattibili. La tabella somma i km degli otto scenari di ogni dimensione; non rappresenta un singolo giro reale.

| Fermate | Migliorati / 8 | Km prima → dopo (somma) | Riduzione | CPU mediana prima → dopo (ms) | CPU massima nuova (ms) | Valutazioni nuove min–max |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 0 | 662.25 → 662.25 | 0.00% | 9882.8 → 9484.4 | 13421.9 | 40321–40321 |
| 9 | 1 | 663.51 → 660.51 | 0.45% | 250.0 → 140.6 | 343.8 | 3333–5218 |
| 15 | 1 | 862.22 → 861.22 | 0.12% | 1640.6 → 695.3 | 1453.1 | 10425–14056 |
| 20 | 8 | 1304.77 → 954.29 | 26.86% | 515.6 → 679.7 | 1640.6 | 9755–11448 |
| 30 | 6 | 1558.47 → 1243.99 | 20.18% | 1664.1 → 992.2 | 1437.5 | 10845–13368 |
| 50 | 6 | 2111.02 → 1761.92 | 16.54% | 4898.4 → 1320.3 | 6453.1 | 12405–19608 |

Campioni CPU locali Windows con altre verifiche contemporanee: confronto indicativo, non SLA né benchmark hardware isolato. I tempi wall-clock, i minuti di giro, le attese, la fattibilità, i singoli confronti e i contatori della baseline sono nel JSON. Il ramo esatto da otto fermate è invariato; le differenze temporali lì sono rumore della misurazione. Per giri euristici il valutatore più leggero può compensare le valutazioni aggiuntive, ma non in ogni scenario.

Esempi da 50 fermate con rientro: asimmetrico **133 → 129 km**, cluster **315,60 → 296,15 km**. Restano invariati il cluster da 50 senza rientro, le finestre da 50 con rientro e le finestre da 30 in entrambe le modalità. A 9 e 15 fermate migliora soltanto il caso asimmetrico con rientro; tutti i casi esatti da 5 e 8 restano invariati. A 12 migliora solo il caso con finestre e rientro.

I risparmi aggregati sono fortemente influenzati dalle trappole nearest-neighbour costruite appositamente: a 50 fermate **150,50 → 51 km** senza rientro e **259,50 → 52 km** con rientro. Non sono una previsione di risparmio su consegne reali.

Ablazione con lo stesso limite massimo di 5000 valutazioni: swap/inversione/relocate restano a **152 km** (136 valutazioni); aggiungendo Or-opt 2/3 si arriva a **93 km** (702 valutazioni). Entrambe terminano prima del limite; il test verifica anche che nessuna singola mossa delle tre famiglie precedenti migliori il punto iniziale.

## Verifica della modifica

- `python -m pytest tests -q`: **390 passed, 2 skipped**, 1207 warning di deprecazione, 509,27 s. Su Windows sono stati impostati `PYTEST_ADDOPTS=-p no:cacheprovider --basetemp=.test-tmp-multistart-final2` e il PATH della virtualenv; nessun test escluso. Le due integrazioni PostgreSQL richiedono `TEST_POSTGRES_URL`, configurata in CI ma non in questa esecuzione locale.
- `node --test tests/*.cjs`: **27 passed**, zero fallimenti.
- `docker build -t girofacile-test .`: completata dopo il riavvio di Docker Desktop; il primo tentativo aveva incontrato un timeout TLS di Docker Hub.
- `python tests/run_optimizer_benchmark.py`: **64 scenari completati**, confronti con baseline e oracoli superati; nessuna richiesta a provider.
- `git diff --check`: superato.
