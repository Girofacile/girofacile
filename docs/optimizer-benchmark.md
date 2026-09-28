# Punto 1 — test e benchmark del motore

Il codice applicativo non è stato modificato. La suite caratterizza il motore
presente su main (base d9236f0), senza cambiare algoritmo, pesi o finestre.
Non assegna consegne a più mezzi: misura l'ordine delle consegne già selezionate.

## Esecuzione e file

- `tests/test_optimizer.py`: 48 casi parametrizzati, 47 attesi verdi e un
  `xfail(strict=True)` per il difetto della partenza a mezzanotte.
- `tests/optimizer_benchmark.py`: matrici deterministiche, riferimento esatto
  Held–Karp e metriche di qualità, esclusivamente per i test.
- Questo documento: metodo, risultati, limiti e indicazioni per il Punto 2.

```sh
python -m pytest tests -q
python -m pytest tests/test_optimizer.py -q -s -k quality_against_exact_reference
python -m pytest tests/test_optimizer.py --junitxml=optimizer-results.xml -o junit_family=legacy
```

Il secondo comando stampa sei righe JSON `BENCHMARK`. Il terzo conserva le
metriche nella proprietà JUnit `quality`. Ogni riga contiene km/minuti del
motore e del riferimento, differenze assolute, gap percentuali, violazioni e
attesa totale. Un riferimento pari a zero produce un gap `null`, non una
divisione per zero. Nessuna dipendenza aggiuntiva o modifica alla CI è necessaria.

Le richieste HTTP e gli ingressi Google/OSRM/geocoding falliscono esplicitamente
se invocati dai nuovi test. Gli ingressi pubblici ricevono una matrice stub;
data e ora sono congelate. Non sono necessari database, chiavi o rete.

## Metodo del riferimento

Per le taglie 5, 8, 9, 10, 12 e 15 si usa la stessa famiglia di prefissi di una
griglia Manhattan fissata nel test. Un'unità vale 1 km e 2 minuti. Sono matrici
simmetriche che rispettano la disuguaglianza triangolare, senza scarichi o
finestre, con ritorno al deposito. Il caso è stato selezionato offline per
mostrare un minimo locale; nei test non si effettua alcuna ricerca casuale.

Held–Karp minimizza esattamente `10 * minuti + km` con programmazione dinamica
su sottoinsiemi: non chiama nessuna funzione dell'optimizer. Su questa griglia
tempo e distanza sono proporzionali, quindi l'ottimo è contemporaneamente
l'ottimo di entrambi. L'oracolo è verificato contro enumerazione indipendente
su quattro fermate con matrice asimmetrica, tempi e km distinti, sia con sia
senza rientro. Non applicarlo a finestre/attese: la sua funzione costo è additiva.

I test vincolano risultati esatti delle fixture, non soglie qualitative
arbitrarie. Una futura modifica del motore può richiedere l'aggiornamento
consapevole delle caratterizzazioni, confrontando sempre il nuovo gap.

## Risultati della famiglia di griglia

| Fermate | km motore / ottimo | min motore / ottimo | Delta km | Delta min | Gap km e min | Violazioni | Attesa min |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 70 / 70 | 140 / 140 | 0 | 0 | 0% | 0 | 0 |
| 8 | 96 / 96 | 192 / 192 | 0 | 0 | 0% | 0 | 0 |
| 9 | 108 / 96 | 216 / 192 | 12 | 24 | 12,50% | 0 | 0 |
| 10 | 110 / 98 | 220 / 196 | 12 | 24 | 12,24% | 0 | 0 |
| 12 | 110 / 102 | 220 / 204 | 8 | 16 | 7,84% | 0 | 0 |
| 15 | 110 / 106 | 220 / 212 | 4 | 8 | 3,77% | 0 | 0 |

I risultati sono stabili su esecuzioni ripetute con lo stesso ordine di input.
Non costituiscono una media rappresentativa della logistica reale né una
garanzia per altre matrici o diversi ordinamenti di input.

Il passaggio 8→9 è particolarmente informativo: aggiungere il cliente 9 non
aumenta il costo ottimo, ma il motore perde 12 km / 24 minuti. La sequenza
`1, 8, 3, 9, 6, 5, 4, 7, 2` testimonia il costo 96 km / 192 minuti.
Il test verifica greedy, miglioramento locale e dispatcher; inoltre enumera
tutti gli scambi e tutte le inversioni del risultato. Nessuna di queste mosse
lo migliora. Anche 20 round restano nello stesso minimo: aumentare soltanto il
limite attuale di quattro round non risolve questo caso.

Un secondo caso da 12 fermate include 10 minuti di scarico per cliente e
finestre 08:00–12:00: 26 km, 185 minuti, fine 11:05, zero violazioni e attese.
La matrice ha archi uguali: tutte le permutazioni raggiungono lo stesso limite
inferiore. Conferma gli orari con scarichi, ma non simula la varietà stradale.

## Copertura funzionale

- A–E: confronto con ordine iniziale a 5 fermate, ottimo unico piccolo,
  limite esaustivo a 8, confronto esatto a 9/10/12 e anche 15, ripetibilità.
- F: percorso più lungo ma fattibile preferito al percorso breve che viola
  una finestra stretta.
- G: uso della mattina o del pomeriggio; pomeriggio scelto anche se l'arrivo
  è mattutino ma lo scarico non terminerebbe in tempo.
- H: arrivo fisico 08:10, apertura 09:00, attesa 50 minuti, scarico fino alle
  09:20, seconda fermata 09:30–09:45, ritorno 09:55.
- I: due ordini con stessa percorrenza e scarichi da 30/20 minuti spostano
  correttamente gli arrivi successivi senza alterare la durata totale.
- L: fine scarico esattamente alla chiusura ammessa; oltre chiusura rifiutata;
  giro impossibile comunque restituito con warning, una violazione e penalità.
- M: stessa sequenza con/senza rientro, anche attraverso entrambi gli ingressi
  pubblici `optimize_route` e `recalculate_manual_route` con matrice stub.
- N: kg/colli al limite, capacità assente, superamento aggregato già coperto
  dai test esistenti, sovraccarico bloccato prima del routing, valori negativi,
  non finiti e colli frazionari respinti.
- ZTL/sponda restano avvisi, senza violazioni rigide; giro vuoto gestito.

## Riscontri e limiti attuali

1. **Difetto confermato a mezzanotte:** `parse_hhmm("00:00") or 8 * 60`
   sostituisce zero con 08:00. Il test attende 00:10 e fallisce come previsto
   (`xfail` rigoroso: un futuro successo richiede di rimuovere la marcatura).
   Il pattern compare anche nel greedy e nel ricalcolo manuale. Non corretto.
2. **Semantica degli orari:** `arrivo_stimato` contiene l'inizio servizio, non
   l'arrivo fisico prima dell'attesa. I test lo rendono esplicito.
3. **Score pesato:** tempo e km non sono ordinati lessicograficamente. Un
   test mostra 4 minuti / 3 km preferiti a 3 minuti / 22 km. Anche la priorità
   delle violazioni è una penalità finita; non è una garanzia matematica
   universale di fattibilità. Gli avvisi ZTL/sponda attivano il ramo dei
   vincoli e incidono sullo score, ma non rendono il giro impossibile.
4. **Segnalazione:** l'evaluatore interno espone violazioni, attesa totale e
   score; `optimize_route` li rimuove dalla risposta pubblica. Restano gli avvisi
   e le attese delle singole fermate. Un giro impossibile non genera da solo
   un'eccezione di ottimizzazione.
5. Nei casi diurni testati non sono emersi errori di finestre, attese o
   propagazione dello scarico. L'enumerazione fino a 8 minimizza lo score
   attuale; non dimostra l'ottimo globale con scelte alternative delle fasce
   dello stesso cliente, dato che queste sono scelte da `evaluate_candidate`.

## Verifica locale

Ambiente Python 3.12 della `.venv`. Il primo comando completo standard ha
prodotto 65 pass, 1 skip, 1 xfail e 46 errori di setup per permessi Windows
sulla directory temporanea di pytest (prima degli ultimi quattro casi).
È stato rieseguito con `-p no:cacheprovider --basetemp=<directory nuova>`:
nessun cambiamento ai test esistenti o alle ACL è stato necessario.

Risultato finale: **115 passed, 1 skipped, 1 xfailed, 381 warning di
deprecazione, 18,27 secondi**. Dei nuovi casi, 47 passano e uno è il difetto
noto marcato xfail. Tutti i **6 test JavaScript** previsti dalla CI passano.
Il test PostgreSQL reale richiede `TEST_POSTGRES_URL` e viene saltato localmente; la CI lo abilita
con il proprio servizio PostgreSQL. Docker non è disponibile localmente:
build e verifica degli strumenti di backup nel container restano alla CI.

## Proposte per il Punto 2 (non implementate)

- Risolvere il difetto di mezzanotte e precisare la semantica arrivo/inizio servizio.
- Valutare partenze multiple e mosse di rilocazione per uscire dal minimo
  locale dimostrato; confrontarle con questi riferimenti esatti.
- Concordare se tempo, distanza e fattibilità debbano avere priorità assolute
  o mantenere l'attuale compromesso pesato.
- Ampliare il corpus con matrici stradali anonimizzate, asimmetrie, finestre
  eterogenee e permutazioni dell'input prima di trarre conclusioni statistiche.
- Valutare una segnalazione esplicita delle violazioni aggregate verso
  l'operatore, senza irrigidire ZTL/sponda.
