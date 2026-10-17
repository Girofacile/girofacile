# Simulazioni della distribuzione multi-mezzo

Commit eseguito: e268327368733bba32b92b4ad2a110189b802c53.
Generato: 2026-10-17T23:50:36.960035+00:00. Matrici congelate e dati fittizi; nessun dato operativo.

Scenari distinti: **196**. Esecuzioni: **512**; casi con riferimento esatto: **146**, con entrambe le strategie.

## Metodo

- Invocazione reale di app.services.fleet_planning.distribute; ingressi aziendali, disponibilità e matrice sostituiti con fixture isolate.
- Valutatore indipendente per capacità, finestre doppie, scarico, pause, turno, durata massima e rientro.
- Nei casi piccoli: tutte le sequenze per sottoinsieme/risorsa e tutte le assegnazioni, comprese consegne lasciate fuori.
- Riferimenti distinti: copertura massima, dotazioni, poi minimo km / minimo minuti / consolidamento / bilanciamento. Questi ultimi sono riferimenti globali coerenti con le priorità, non la stessa decisione locale a ogni inserimento.
- Nei casi grandi: invarianti, tempi e stabilità; nessuna certificazione di ottimo.

## Risultati

Errori degli invarianti: **0**. Richieste esterne: **0**. Matrici al boundary: **512**, una per esecuzione, tutte da fixture.
Ripetizioni identiche: 24; divergenze: 0. Esecuzioni con selezione riordinata: 96.

| Strategia | Casi esatti | Casi con consegne fattibili lasciate fuori | Peggiore del riferimento globale coerente con la strategia | Testimoni di miglioramento km/tempo |
|---|---:|---:|---:|---:|
| efficient | 146 | 8 | 80 | 71 |
| balanced | 146 | 6 | 87 | 104 |

I gap usano solo casi con uguale copertura e dotazioni. I riferimenti km e tempo possono scegliere ripartizioni diverse. I testimoni simultanei sono miglioramenti concreti tra quattro ottimi; non rappresentano l'intera frontiera di Pareto.

## Casi mirati

| Caso | Strategia | Consegnate attuali / massimo | km attuali / minimi | minuti attuali / minimi |
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
| curated-waiting-absorbs-break | balanced | 2 / 2 | 4.00 / 3.00 | 160.0 / 100.0 |
| curated-return-crosses-break | efficient | 2 / 2 | 4.00 / 4.00 | 100.0 / 100.0 |
| curated-return-crosses-break | balanced | 2 / 2 | 4.00 / 4.00 | 100.0 / 100.0 |
| curated-km-time-tradeoff | efficient | 2 / 2 | 17.00 / 15.00 | 14.0 / 14.0 |
| curated-km-time-tradeoff | balanced | 2 / 2 | 25.00 / 15.00 | 20.0 / 14.0 |

Non confrontare km/minuti come miglioramento a parità di servizio quando le consegne servite differiscono.

## Prestazioni e limiti

Stress: mediana 57.5 ms, p95 1923.8 ms, massimo 2731.1 ms per distribuzione.
Tempi del solo motore, senza database/provider, su runner CI: non sono tempi garantiti in produzione.
La flotta automatica usa inserimento progressivo, senza riallocazione globale. Efficient preferisce mezzi già usati e incremento minuti; balanced impiega risorse e bilancia durata. Nessuna certifica i km minimi.
Partenza/deposito/giornata comuni; pause fisse dichiarate. Niente ricerca di partenze differenziate né verifica automatica normativa ore guida. Sponda/ZTL sono preferenze con avviso; volume/pallet non sono capacità rigide. Algoritmo, prezzi, database e pagine non sono stati modificati.
Il benchmark testa il nucleo della distribuzione. Persistenza, autorizzazioni e traffico sono coperti dai test applicativi separati. Il traffico reale futuro non è certificabile con matrici congelate.

## Riproduzione

    python -m pytest tests/test_fleet_quality_reference.py tests/test_fleet_planning.py tests/test_driver_schedule.py -q
    python tests/run_fleet_simulations.py

L'artifact fleet-simulation-results contiene JSON completo, ordini dei testimoni, semi, famiglie, matrici dei casi mirati e impronte SHA256 dei file del motore.

## Interpretazione pratica

**La risposta alla verifica “trova sempre il giro migliore?” è no.**
L'aritmetica delle pause è risultata coerente nei 512 replay indipendenti; la ricerca della ripartizione rimane euristica.
La soglia di ricerca completa fino a otto fermate del motore singolo non si applica alla distribuzione automatica dei mezzi.

### Ripartizione geografica

Nel caso fittizio con deposito a 0 e quattro consegne alle posizioni 10, -10, 11, -11, ciascun mezzo può portare due consegne.
Efficient riempie prima un mezzo con le prime due consegne, poi l'altro: 84 km e 168 minuti complessivi.
Accoppiare le consegne dello stesso lato usa sempre due mezzi, serve le stesse quattro destinazioni e richiede 44 km e 88 minuti.
Il risparmio possibile in quel caso è 40 km e 80 minuti complessivi. Balanced trova già questa soluzione.
Con pause fisse 08:45–09:15 e scarico di 5 minuti, lo stesso problema resta: 84 contro 44 km, 248 contro 168 minuti.

### Incastro di pausa, capacità e finestra

Due autisti partono alle 08:00, con due mezzi da 2 kg:
- autista A in pausa 08:20–08:40; autista B senza pausa;
- consegna X da 2 kg: scarico 15 minuti, finestra 08:00–10:00;
- consegna Y da 1 kg: scarico 10 minuti, finestra 08:15–08:35;
- ogni tratta della matrice fittizia dura 10 minuti.

Entrambe le strategie assegnano prima X all'autista B perché il giro è più rapido.
Y non entra più sul suo mezzo e l'altro autista non rispetta la sua finestra: resta fuori.
La soluzione completa esiste: X all'autista A, Y all'autista B, con rientri rispettivamente alle 09:05 e 08:35.
Il problema è la scelta dell'assegnazione precedente non riconsiderata, non il mancato rispetto della pausa.

### Copertura e confronto degli obiettivi

Nei 146 scenari piccoli con massimo numero di consegne servibili verificato esattamente:
- efficient lascia fuori una consegna servibile in **8 scenari**;
- balanced lo fa in **6 scenari**.

Sono frequenze di un insieme di prova costruito per esplorare anche casi avversi, non stime statistiche sui giri dei clienti.
Il confronto dei chilometri ammette risorse differenti, ma conserva copertura e dotazioni;
il riferimento della strategia mantiene invece le priorità esplicite di consolidamento o bilanciamento.
Usare tutti i mezzi per terminare prima può aumentare somma dei minuti e chilometri senza violare l'obiettivo balanced.
Per esempio, nel caso “waiting-absorbs-break” balanced termina in 80 minuti con due mezzi, contro 100 minuti con uno,
pur usando 160 minuti/autista complessivi invece di 100. Queste grandezze non sono intercambiabili.

La mediana del gap chilometrico rispetto al minimo, sui casi comparabili, è 16.36% per efficient (135 confronti)
e 15.88% per balanced (138 confronti).
Non è una promessa di risparmio percentuale in produzione: i due riferimenti possono usare un numero di mezzi differente.
Cambiare l'ordine di selezione ha modificato gli indicatori in 3 delle 96 varianti provate;
ripetere identicamente gli stessi input non ha prodotto divergenze nelle 24 ripetizioni.

## Priorità di miglioramento suggerite

1. Recuperare consegne non assegnate tramite riallocazioni e piccoli scambi tra mezzi, ricontrollando tutti i vincoli.
2. Rifinire automaticamente l'ordine interno di ciascun giro con il motore già disponibile.
3. Provare più soluzioni iniziali e confrontare spostamenti/scambi tra giri, con budget di calcolo misurato.
4. Rendere esplicita la priorità tra km, minuti complessivi, termine dell'ultimo giro e numero di mezzi.
5. Conservare una sola matrice condivisa, senza richieste a provider per ogni combinazione, e utilizzare queste prove come confronto prima/dopo.

Queste modifiche all'algoritmo non sono state applicate nel presente intervento di verifica.

## Controlli e file

Il job dedicato ha superato **61 test** su oracle indipendente, flotta, turni e pause, oltre alle **512 simulazioni**.
Le matrici stradali congelate provengono dal fixture OSRM già presente nel progetto: distanze dei percorsi più rapidi del profilo driving,
non un certificato di percorsi stradali a distanza assolutamente minima. I dati delle consegne sono fittizi.
Non sono state interrogate API, inviate email o usati database operativi.

File aggiunti: tests/fleet_quality_reference.py, tests/fleet_simulation_cases.py, tests/test_fleet_quality_reference.py,
tests/run_fleet_simulations.py e questo rapporto. La CI aggiunge un job dedicato; la documentazione flotta è allineata alle pause già implementate.
Nessuna migrazione e nessuna modifica al codice produttivo del motore.

La CI generale era già rossa prima dell'intervento:
[test Node della UI fermate occasionali](https://github.com/Girofacile/girofacile/actions/runs/39061424812/job/117480022256)
con asserzione testuale sul markup di moveDelivery.
Non è un fallimento del benchmark o del calcolo delle pause; non è stato disattivato né incluso in una modifica funzionale.

[Job delle simulazioni](https://github.com/Girofacile/girofacile/actions/runs/39080448741/job/117536138934)
· [Artifact completo](https://github.com/Girofacile/girofacile/actions/runs/39080448741/artifacts/12118369058).
