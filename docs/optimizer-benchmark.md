# Benchmark del motore — Punti 1 e 2

La sezione Punto 1 seguente conserva i risultati storici del commit `81f5121`.
Per lo stato attuale, le correzioni e le misure prima/dopo vedere **Punto 2** in fondo.

## Punto 1 — fotografia storica

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


# Punto 2 — mezzanotte e ricerca deterministica (29 settembre 2026)

## Modifiche e scelta sperimentale

La partenza usa un fallback alle 08:00 **solo quando il parser restituisce None**.
Lo zero valido di mezzanotte viene conservato in valutazione, greedy e ricalcolo
manuale. L'xfail diventa ordinario. Gli ingressi pubblici continuano a rifiutare
orari assenti/non validi prima del routing; il parser interno mantiene il proprio
fallback e la permissività preesistente per valori fuori intervallo. Non abbiamo
uniformato implicitamente i due contratti.

Fino a 8 fermate rimane l'enumerazione esaustiva sullo score attuale. Per 9–15:
si conserva il risultato della vecchia ricerca, si valuta l'ordine dell'operatore,
e si migliorano tre semi deterministici (greedy, operatore, greedy inverso) tramite
swap, inversioni e rilocazioni di una fermata. I semi duplicati vengono esclusi.
Quattro round per seme, accettazione solo di miglioramenti stretti e migliore
risultato conservato. Oltre 15 resta la vecchia ricerca con l'aggiunta del confronto
con l'ordine operatore. Nessun OR-Tools o componente casuale.

La matrice Google viene costruita una sola volta. Se manca, una cache locale alla
ricerca memorizza ogni arco OSRM alla prima richiesta: i nuovi tentativi non
ripetono richieste stradali. Un test confronta anche archi e numero di chiamate
con il vecchio greedy + ricerca locale. Nessuna modifica a cache persistente,
frontend, database, assegnazione ai mezzi, pesi, ZTL/sponda o finestre.

**arrivo_stimato significa inizio servizio dopo l'eventuale attesa**, come prima.
Non è l'arrivo fisico al cliente. Nessuna rinomina o variazione della risposta.

### Confronto delle varianti sulla stessa griglia (km)

| Fermate | Vecchia ricerca | Sole rilocazioni | Soli semi multipli | Combinazione |
|---|---:|---:|---:|---:|
| 9 | 108.0 | 108.0 | 96.0 | 96.0 |
| 10 | 110.0 | 110.0 | 110.0 | 98.0 |
| 12 | 110.0 | 110.0 | 108.0 | 102.0 |
| 15 | 110.0 | 106.0 | 106.0 | 106.0 |

La combinazione è scelta perché risolve anche 10 e 12 fermate, dove le singole
tecniche non bastano. Non si è aumentato il limite dei round. Il test storico del
minimo locale resta: dimostra ancora 108 km e l'assenza di miglioramenti tramite
swap/inversioni, mentre il dispatcher aggiornato deve raggiungere 96 km.

## Misure prima/dopo

Riproduzione: `python tests/run_optimizer_benchmark.py`. Legge il codice originale
con `git show 81f512189916f5e7e091c6956689fa5be38eb1b9:app/optimizer.py` e confronta
la copia in memoria con il codice corrente, senza checkout o modifiche Git.
Tutti gli accessi esterni falliscono esplicitamente. Dati completi e tempi delle
varianti sono in [optimizer-benchmark-results.json](optimizer-benchmark-results.json).
Fixture GRID e oracolo Held–Karp del Punto 1 sono invariati.

Tempi: una misura wall-clock per esecuzione, solo ricerca (oracolo/import esclusi),
Python 3.12 locale Windows. Sono misure descrittive, non soglie di test né benchmark
statistici. Le oscillazioni fra esecuzioni/varianti non sono regressioni dimostrate.

### Griglia originale, ritorno attivo

| N | km prima → dopo / esatto | min prima → dopo / esatto | score prima → dopo / esatto | gap score prima → dopo | violazioni / attese prima → dopo | ms prima → dopo |
|---|---|---|---|---|---|---|
| 5 | 70 → 70 / 70 | 140 → 140 / 140 | 1470 → 1470 / 1470 | 0.00% → 0.00% | 0 / 0 → 0 / 0 | 15.6 → 9.3 |
| 8 | 96 → 96 / 96 | 192 → 192 / 192 | 2016 → 2016 / 2016 | 0.00% → 0.00% | 0 / 0 → 0 / 0 | 4341.6 → 3881.0 |
| 9 | 108 → 96 / 96 | 216 → 192 / 192 | 2268 → 2016 / 2016 | 12.50% → 0.00% | 0 / 0 → 0 / 0 | 7.0 → 52.3 |
| 10 | 110 → 98 / 98 | 220 → 196 / 196 | 2310 → 2058 / 2058 | 12.24% → 0.00% | 0 / 0 → 0 / 0 | 6.9 → 77.2 |
| 12 | 110 → 102 / 102 | 220 → 204 / 204 | 2310 → 2142 / 2142 | 7.84% → 0.00% | 0 / 0 → 0 / 0 | 10.9 → 141.4 |
| 15 | 110 → 106 / 106 | 220 → 212 / 212 | 2310 → 2226 / 2226 | 3.77% → 0.00% | 0 / 0 → 0 / 0 | 105.7 → 456.5 |

Gap km, minuti e score coincidono nella griglia perché le grandezze sono
proporzionali. Nessuna regressione nei sei casi, nessuna violazione o attesa.

### Nuovi scenari diretti, tempi e km non proporzionali

Le matrici sono asimmetriche e deterministiche; non rappresentano un campione
stradale reale. Ogni taglia è provata con rientro sì/no e input naturale, inverso,
intercalato. Senza finestre il riferimento è l'ottimo esatto dello **score additivo**:
km e minuti del riferimento non sono necessariamente i rispettivi minimi separati.
Con finestre si usano aperture/chiusure eterogenee, scarichi di 3–7 minuti e attese.
Il riferimento è l'ordine naturale verificato da un simulatore indipendente a
finestra singola, **un testimone fattibile, non un ottimo**. Il simulatore verifica
anche l'ordine restituito e concordanza di km, minuti, attese, violazioni e score.
Un gap rispetto al testimone non certifica ottimalità.

Nelle 24 prove senza finestre lo score migliora sempre; il gap residuo massimo
rispetto all'ottimo è 14,20%. Nelle 24 prove con finestre migliora in 12 e resta
uguale in 12; le violazioni aggregate scendono da 12 a 0. Tutte raggiungono il
costo del testimone noto, senza provare che sia l'ottimo. Tre input differenti
non implicano che la ricerca sia invariante alle permutazioni: si garantisce la
ripetibilità per gli stessi dati e lo stesso ordine.

Nella tabella P/D significa prima/dopo; gap S è riferito allo score. Per ciascuna
riga il JSON include anche gap km e minuti, costi completi del riferimento e tipo.

| Tipo | N | Rientro | Input | km P/D | min P/D | score P/D | violazioni P/D | attese P/D | gap S % P/D | ms P/D |
|---|---:|---|---|---|---|---|---|---|---|---|
| directed | 9 | no | forward | 131/113 | 47/42 | 601/533 | 0/0 | 0/0 | 18.31/4.92 | 7.6/99.2 |
| directed | 9 | no | reverse | 131/128 | 47/38 | 601/508 | 0/0 | 0/0 | 18.31/0.00 | 11.2/86.2 |
| directed | 9 | no | interleaved | 131/128 | 47/38 | 601/508 | 0/0 | 0/0 | 18.31/0.00 | 9.7/137.0 |
| directed | 9 | sì | forward | 149/126 | 52/52 | 669/646 | 0/0 | 0/0 | 16.15/12.15 | 8.2/99.9 |
| directed | 9 | sì | reverse | 149/146 | 52/43 | 669/576 | 0/0 | 0/0 | 16.15/0.00 | 10.7/91.2 |
| directed | 9 | sì | interleaved | 149/126 | 52/52 | 669/646 | 0/0 | 0/0 | 16.15/12.15 | 9.7/108.5 |
| directed | 10 | no | forward | 145/130 | 45/35 | 595/480 | 0/0 | 0/0 | 23.96/0.00 | 17.6/184.1 |
| directed | 10 | no | reverse | 145/134 | 45/39 | 595/524 | 0/0 | 0/0 | 23.96/9.17 | 18.0/140.7 |
| directed | 10 | no | interleaved | 145/130 | 45/35 | 595/480 | 0/0 | 0/0 | 23.96/0.00 | 18.5/149.9 |
| directed | 10 | sì | forward | 163/152 | 50/48 | 663/632 | 0/0 | 0/0 | 11.80/6.58 | 19.3/142.9 |
| directed | 10 | sì | reverse | 163/143 | 50/45 | 663/593 | 0/0 | 0/0 | 11.80/0.00 | 19.2/170.3 |
| directed | 10 | sì | interleaved | 163/152 | 50/48 | 663/632 | 0/0 | 0/0 | 11.80/6.58 | 22.3/159.6 |
| directed | 12 | no | forward | 125/138 | 74/48 | 865/618 | 0/0 | 0/0 | 43.21/2.32 | 35.0/264.6 |
| directed | 12 | no | reverse | 125/138 | 74/48 | 865/618 | 0/0 | 0/0 | 43.21/2.32 | 34.9/396.8 |
| directed | 12 | no | interleaved | 125/151 | 74/46 | 865/611 | 0/0 | 0/0 | 43.21/1.16 | 38.0/318.3 |
| directed | 12 | sì | forward | 134/170 | 86/54 | 994/710 | 0/0 | 0/0 | 45.53/3.95 | 41.4/254.6 |
| directed | 12 | sì | reverse | 134/140 | 86/64 | 994/780 | 0/0 | 0/0 | 45.53/14.20 | 40.7/227.3 |
| directed | 12 | sì | interleaved | 134/140 | 86/64 | 994/780 | 0/0 | 0/0 | 45.53/14.20 | 40.4/295.7 |
| directed | 15 | no | forward | 141/142 | 73/56 | 871/702 | 0/0 | 0/0 | 39.81/12.68 | 42.1/348.8 |
| directed | 15 | no | reverse | 141/142 | 73/56 | 871/702 | 0/0 | 0/0 | 39.81/12.68 | 42.8/393.0 |
| directed | 15 | no | interleaved | 141/142 | 73/56 | 871/702 | 0/0 | 0/0 | 39.81/12.68 | 40.6/395.9 |
| directed | 15 | sì | forward | 161/163 | 77/63 | 931/793 | 0/0 | 0/0 | 28.77/9.68 | 46.6/443.2 |
| directed | 15 | sì | reverse | 161/162 | 77/63 | 931/792 | 0/0 | 0/0 | 28.77/9.54 | 59.8/455.2 |
| directed | 15 | sì | interleaved | 161/150 | 77/62 | 931/770 | 0/0 | 0/0 | 28.77/6.50 | 40.7/350.4 |
| windows | 9 | no | forward | 99/99 | 150/150 | 1705.5/1705.5 | 0/0 | 21/21 | 0.00/0.00 | 6.1/58.7 |
| windows | 9 | no | reverse | 99/99 | 150/150 | 1705.5/1705.5 | 0/0 | 21/21 | 0.00/0.00 | 8.6/57.9 |
| windows | 9 | no | interleaved | 99/99 | 150/150 | 1705.5/1705.5 | 0/0 | 21/21 | 0.00/0.00 | 6.6/102.9 |
| windows | 9 | sì | forward | 117/117 | 155/155 | 1773.5/1773.5 | 0/0 | 21/21 | 0.00/0.00 | 6.2/61.5 |
| windows | 9 | sì | reverse | 117/117 | 155/155 | 1773.5/1773.5 | 0/0 | 21/21 | 0.00/0.00 | 6.0/60.3 |
| windows | 9 | sì | interleaved | 117/117 | 155/155 | 1773.5/1773.5 | 0/0 | 21/21 | 0.00/0.00 | 6.5/150.6 |
| windows | 10 | no | forward | 110/110 | 162/162 | 1872/1872 | 0/0 | 28/28 | 0.00/0.00 | 17.2/130.7 |
| windows | 10 | no | reverse | 110/110 | 162/162 | 1872/1872 | 0/0 | 28/28 | 0.00/0.00 | 15.0/116.6 |
| windows | 10 | no | interleaved | 110/110 | 162/162 | 1872/1872 | 0/0 | 28/28 | 0.00/0.00 | 10.3/166.0 |
| windows | 10 | sì | forward | 112/112 | 180/180 | 2054/2054 | 0/0 | 28/28 | 0.00/0.00 | 9.6/101.7 |
| windows | 10 | sì | reverse | 112/112 | 180/180 | 2054/2054 | 0/0 | 28/28 | 0.00/0.00 | 9.4/85.3 |
| windows | 10 | sì | interleaved | 112/112 | 180/180 | 2054/2054 | 0/0 | 28/28 | 0.00/0.00 | 9.4/140.5 |
| windows | 12 | no | forward | 143/133 | 207/187 | 102371/2145 | 1/0 | 22/28 | 4672.54/0.00 | 15.9/210.7 |
| windows | 12 | no | reverse | 143/133 | 207/187 | 102371/2145 | 1/0 | 22/28 | 4672.54/0.00 | 15.6/269.7 |
| windows | 12 | no | interleaved | 143/133 | 207/187 | 102371/2145 | 1/0 | 22/28 | 4672.54/0.00 | 15.0/253.1 |
| windows | 12 | sì | forward | 152/149 | 213/193 | 102448/2221 | 1/0 | 27/28 | 4512.67/0.00 | 29.3/245.9 |
| windows | 12 | sì | reverse | 152/149 | 213/193 | 102448/2221 | 1/0 | 27/28 | 4512.67/0.00 | 29.4/351.7 |
| windows | 12 | sì | interleaved | 152/149 | 213/193 | 102448/2221 | 1/0 | 27/28 | 4512.67/0.00 | 35.8/262.5 |
| windows | 15 | no | forward | 156/177 | 250/240 | 102858/2754.5 | 1/0 | 35/35 | 3634.20/0.00 | 60.5/475.1 |
| windows | 15 | no | reverse | 156/177 | 250/240 | 102858/2754.5 | 1/0 | 35/35 | 3634.20/0.00 | 57.3/654.2 |
| windows | 15 | no | interleaved | 156/177 | 250/240 | 102858/2754.5 | 1/0 | 35/35 | 3634.20/0.00 | 54.9/663.9 |
| windows | 15 | sì | forward | 194/191 | 256/247 | 103018/2838.5 | 1/0 | 59/35 | 3529.29/0.00 | 84.4/1009.5 |
| windows | 15 | sì | reverse | 194/191 | 256/247 | 103018/2838.5 | 1/0 | 59/35 | 3529.29/0.00 | 117.8/708.8 |
| windows | 15 | sì | interleaved | 194/191 | 256/247 | 103018/2838.5 | 1/0 | 59/35 | 3529.29/0.00 | 99.3/653.6 |

## Prestazioni e limiti rimasti

La ricerca 9–15 costa più CPU: nella griglia circa 52–457 ms contro 7–106 ms
nel confronto principale. Nei nuovi scenari circa 58–1010 ms dopo la modifica.
I casi piccoli mantengono l'esaustivo (8 fermate circa 3,9 s in questa misura).
Non si promettono questi tempi su altre macchine o dataset. Complessità locale
per seme O(round * n³), perché ogni mossa rivaluta l'intero giro; semi e round
sono limitati e il ramo potenziato si ferma a 15 fermate.

- Nessuna garanzia di ottimo globale oltre 8; restano gap misurati sulle matrici
  asimmetriche. Nessuna garanzia universale di fattibilità: la scelta conserva
  lo score minimo, non un ordinamento lessicografico delle violazioni.
- La penalità finita può preferire un giro impossibile a un giro fattibile molto
  costoso. `test_finite_penalty_can_prefer_infeasible_route` riproduce il limite
  con due clienti e un arco costoso: **problema aperto**, pesi invariati.
- La selezione locale fra due fasce resta quella di `evaluate_candidate` e non
  esplora tutte le scelte possibili delle fasce. Le nuove fixture indipendenti
  usano una sola finestra per fermata; i test del Punto 1 sulle due fasce restano.
- La risposta pubblica continua a non esporre score e violazioni aggregate;
  ZTL e sponda restano avvisi. Nessuna assegnazione inter-veicolo.

## Verifica Punto 2

- Comando richiesto `python -m pytest tests -q`: **149 passed, 1 skipped,
  46 errori di setup, 9 warning, 73,99 s**. Gli errori sono PermissionError
  nelle directory temporanee pytest Windows, come nel Punto 1.
- Stessa suite con `-p no:cacheprovider --basetemp=<directory nuova>`:
  **195 passed, 1 skipped, 381 warning di deprecazione, 65,45 s; zero xfail**.
  Nessuna modifica ai test per aggirare errori e nessuna modifica alle ACL.
- Il test saltato richiede `TEST_POSTGRES_URL`: integrazione PostgreSQL reale
  non eseguita localmente; resta configurata nella CI.
- `node --test tests/*.cjs`: **6 passed**, zero fallimenti o skip.
- Runner offline prima/dopo: **54 scenari**, tutti i confronti di score e
  fattibilità superati; fixture e oracolo indipendente del Punto 1 preservati.
- `git diff --check`: superato.
- Docker non installato: build immagine e verifica pg_dump/pg_restore nel
  container non eseguibili localmente. Non si dichiara qui l'esito della CI.
- Difetti aperti e limiti dello score/finestre descritti nella sezione precedente;
  il test della penalità finita ne riproduce il comportamento, non lo corregge.
