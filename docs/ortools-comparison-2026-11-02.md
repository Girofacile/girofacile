# Confronto preliminare GiroFacile / Google OR-Tools — 2 novembre 2026

## Esito

Sette scenari sintetici, ciascuno con tre mezzi. OR-Tools trova meno chilometri
in sei scenari e pareggia nel settimo, mantenendo la stessa copertura e senza
violazioni dei vincoli verificati. In tre scenari aumenta la durata cumulativa.
Il risultato giustifica una sperimentazione ulteriore, non una sostituzione
immediata del pianificatore né una promessa di risparmio economico.

Il software operativo non è stato modificato. OR-Tools è una dipendenza
facoltativa del solo benchmark, installata in un ambiente temporaneo.

## Versione effettivamente confrontata

Codice di produzione: `0ada113e478a3d10b59bc4e5ae4644763731156f`.
Prima della prova la copia Codex è stata aggiornata da `origin/main` tramite
fast-forward. La precedente analisi della chat si riferiva a una copia meno
recente: ora Efficiente minimizza prima i chilometri e dispone già di ricerche
adattive, riparazioni e supporto HiGHS. Il confronto usa questa versione aggiornata.

Python 3.12.10; OR-Tools 9.15.6755; SciPy 1.17.0; esecuzione locale Windows.

## Condizioni comuni

- Tre risorse, partenza 08:00, termine turno 17:00, rientro al deposito.
- Capacità in kg e colli differenti, durata dello scarico, singola finestra per cliente.
- Finestre rispettate alla fine dello scarico, non solo all'arrivo.
- Matrici sintetiche congelate, distanze a decimi di km e tempi a minuti interi.
- Gli stessi input sono forniti ai due motori, senza arrotondamenti aggiuntivi.
- Obiettivo Efficiente: più consegne, meno incompatibilità (assenti qui), meno km,
  meno minuti cumulativi, meno mezzi a parità delle misure precedenti.
- Nessuna pausa, finestra doppia, incompatibilità di dotazioni, traffico reale,
  autonomia elettrica o dato operativo. L'adattatore rifiuta input fuori ambito.
- I testimoni fattibili generano le finestre prima della ricerca. Nessun testimone
  e nessun percorso GiroFacile vengono forniti a OR-Tools come soluzione iniziale.
- Tutti i risultati vengono ricalcolati dal verificatore indipendente esistente.

GiroFacile esegue il vero servizio `distribute`, sostituendo soltanto i confini
per dati, disponibilità e provider. Nessun database operativo, email, richiesta
stradale o servizio Google a pagamento è stato utilizzato.

OR-Tools usa Parallel Cheapest Insertion e Guided Local Search, con limite di
ricerca di 10 secondi per scenario. GiroFacile mantiene i propri budget standard:
**non è un confronto a parità di tempo di calcolo**. L'obiettivo è codificato con
pesi derivati da limiti superiori, così una consegna aggiuntiva prevale su ogni
risparmio e un decimo di km prevale sull'intera differenza possibile di minuti.
L'obiettivo numerico restituito è verificato contro le metriche indipendenti.

## Risultati

Minuti = somma delle durate dei tre giri, incluse attese, scarichi e rientri.
Non sono il tempo trascorso fino al rientro dell'ultimo mezzo.

| Caso | Consegne servite, entrambi | Km GiroFacile | Km OR-Tools | Riduzione km | Minuti GiroFacile | Minuti OR-Tools |
|---|---:|---:|---:|---:|---:|---:|
| 6, finestre ampie | 6/6 | 58,0 | 58,0 | 0% | 208 | 208 |
| 12, finestre ampie | 12/12 | 75,7 | 68,3 | 9,78% | 303 | 289 |
| 24, finestre ampie | 24/24 | 101,6 | 101,0 | 0,59% | 486 | 485 |
| 24, finestre strette A | 24/24 | 137,4 | 132,2 | 3,78% | 568 | 572 |
| 24, finestre strette B | 24/24 | 155,4 | 144,8 | 6,82% | 634 | 620 |
| 36, finestre strette | 36/36 | 151,4 | 139,9 | 7,60% | 767 | 796 |
| 24, una impossibile | 23/24 | 102,9 | 101,0 | 1,85% | 511 | 532 |

Tutti i piani usano tre mezzi. Zero ritardi e zero violazioni rilevate in entrambi.
Nel caso impossibile lo scarico dura più dell'unico minuto disponibile: entrambi
lasciano esclusa quella consegna. Il caso a sei consegne coincide con il riferimento
esaustivo indipendente. Gli altri risultati non hanno una prova di ottimo globale.

Sul campione: 782,4 -> 745,2 km (-37,2 km, circa -4,75%); 3.477 -> 3.502 minuti
(+25 minuti, circa +0,72%). Il campione è piccolo, sintetico e non rappresentativo
dei consumi reali dei clienti: queste percentuali non sono stime commerciali.

| Caso | GiroFacile, secondi | OR-Tools, secondi |
|---|---:|---:|
| 6 ampie | 0,332 | 10,014 |
| 12 ampie | 0,312 | 10,002 |
| 24 ampie | 4,026 | 10,002 |
| 24 strette A | 2,379 | 10,004 |
| 24 strette B | 7,659 | 10,008 |
| 36 strette | 7,166 | 10,008 |
| 24 impossibile | 17,624 | 10,002 |

Una sola esecuzione per scenario: non sono misure statistiche né SLA. Le ricerche
con limite temporale possono produrre risultati diversi su macchine o carichi diversi.

## Valutazione

OR-Tools è un candidato concreto: su questi input migliora la distanza mantenendo
la fattibilità. Non è dimostrato che risparmi sempre ore o costo totale.
Nel caso da 36 consegne, 11,5 km risparmiati costano 29 minuti cumulativi in più.
Questo è coerente con l'obiettivo corrente, che privilegia i km.

Prima di una decisione servono:
1. Il piano reale con i 26 minuti di ritardo e un campione di giornate operative.
2. Pause, doppie finestre, compatibilità e strategia bilanciata con semantica equivalente.
3. Confronti a budget temporali confrontabili, più ripetizioni e casi riservati di verifica.
4. Una funzione di costo concordata, se si vuole minimizzare euro invece dei soli km.
5. Verifica dei percorsi dopo l'aggiornamento del traffico e gestione delle nuove incompatibilità.

## Riproduzione e controlli

In un ambiente isolato:

```text
python -m pip install -r tests/requirements-ortools-benchmark.txt
python tests/run_ortools_comparison.py --seconds 10
python -m pytest tests/test_ortools_comparison.py tests/test_routing_quality_oracle.py -q
```

23 test superati, tre avvisi di deprecazione SWIG. Il confronto controlla anche
copertura, metriche, assenza di mutazioni degli input e assenza di richieste esterne.
La prova non è un test dell'intero processo di programmazione in produzione.

`ortools-comparison-2026-11-02.json` contiene gli input, le matrici, i percorsi
mezzo per mezzo, gli orari ricalcolati, gli esclusi, i tempi di esecuzione,
la diagnostica GiroFacile, i pesi OR-Tools e le impronte dei sorgenti esaminati.
