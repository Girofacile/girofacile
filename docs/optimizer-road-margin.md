# Margine dell'ottimizzatore su consegne simulate e strade reali

Studio del 1 ottobre 2026. Il motore di produzione esaminato è
`f1ad2d4d40db576006a1444d39dd37c0afd3345d`. Nessuna modifica al suo algoritmo,
alle sue dipendenze o alle sue impostazioni è inclusa in questo studio.

## Cosa misura

Confronto di **60 istanze**: tre famiglie geografiche × 8/15/20/30/50
consegne × con/senza finestre × con/senza rientro. Le consegne sono tutte
fittizie. Le strade provengono dal dataset OSRM locale del Sud Italia.
Non sono stati letti database, indirizzi o storici dei clienti.

- Urbano: tre nuclei nell'area di Napoli.
- Provinciale: Aversa, Caserta, Acerra e Nola.
- Misto: Napoli, Acerra, Pompei e Salerno.

Ogni famiglia contiene 51 punti (deposito + 50 consegne), estratti con seed
fisso e agganciati alla rete entro 200 metri. I sottoinsiemi sono annidati:
le dimensioni diverse **non sono campioni statisticamente indipendenti**.
Le coordinate non attestano la presenza di un cliente, un ingresso merci
o un parcheggio utilizzabile. Il profilo è `driving`, non un profilo camion
con limiti di sagoma, peso, ZTL e accessi privati.

La matrice salvata contiene distanze arrotondate al metro e tempi
arrotondati per eccesso al secondo, identici per tutti i motori. Non ci
sono riempimenti in linea d'aria. La precisione numerica del certificato
è relativa a **questa matrice**, non alla precisione fisica della mappa.
OSRM fornisce le distanze delle tratte più veloci, non necessariamente
quelle delle strade più corte: lo studio confronta gli ordini delle
consegne su quelle tratte. Non considera traffico in tempo reale.

## Protocollo e confronto equo

L'ordine manuale simulato raggruppa i punti in sei settori attorno al
deposito e procede per distanza geometrica nel settore. È un riferimento
semplice e trasparente, **non una simulazione validata di un operatore
esperto**. Girofacile riceve proprio quell'ordine, che resta un candidato
come avviene in produzione. Il confronto non può quindi dimostrare che
nessun essere umano sappia fare meglio.

La partenza è alle 08:00, con scarichi di 3–8 minuti. Nei casi vincolati
le finestre sono costruite intorno al giro geografico noto come fattibile,
con 30–60 minuti di margine per lato. Lo scarico deve essere completato
entro la chiusura, esattamente come nel gestionale. Questa costruzione
evita istanze impossibili ma favorisce la struttura dell'ordine iniziale;
non rappresenta la distribuzione osservata degli appuntamenti reali.
Una sola finestra per consegna; nessuna capacità, pausa o durata massima
aggiuntiva che non sia condivisa dai motori. Il limite interno dei tempi
del solver è un maggiorante calcolato dall'istanza, non un nuovo vincolo
di turno lavorativo.

OR-Tools **9.14.6206** è installato solo in `.venv-benchmark`:

1. Routing/Guided Local Search, 3 secondi, avviato dall'ordine manuale.
2. Lo stesso solver, altri 3 secondi, avviato dal risultato Girofacile.
3. Per 8 e 15 fermate: modello CP-SAT indipendente con circuito hamiltoniano
   diretto e finestre, fino a 5 secondi e un solo worker. Un arco di ritorno
   a costo zero rappresenta la fine libera dei giri senza rientro.

Il solver cerca la distanza minima tra giri fattibili: non usa pesi che
scambino chilometri con minuti o ammettano consegne saltate. Le soluzioni
emesse dal solver vengono rivalutate con un replay indipendente intero; fra gli
ordini raccolti i pareggi si risolvono per durata e attesa. Il vincitore
viene verificato anche dal valutatore canonico di Girofacile. La prova
CP-SAT riguarda **solo l'ottimo chilometrico**, non l'ottimo globale delle
priorità secondarie. I test confrontano modello e replay con enumerazione
esaustiva, anche su archi asimmetrici, finestre e ultimo scarico senza
rientro.

`best_known` conserva il migliore fra Girofacile e tutti questi candidati.
Per costruzione non può peggiorarlo: questa proprietà non è una prova
di superiorità del solver. Nel JSON sono riportati separatamente anche
`reference_independent` e `reference_warm`, senza nasconderne gli esiti.

**Margine trovato** = km Girofacile − km migliore soluzione trovata.
Se CP-SAT termina con `OPTIMAL`, il margine chilometrico è esatto per
l'istanza discretizzata. Altrimenti è soltanto un **limite inferiore al
risparmio ancora possibile**: zero significa «nessun miglioramento trovato
con questa prova», non «ottimo dimostrato». Per i casi piccoli il JSON
contiene anche il lower bound del certificatore; per quelli grandi non
si dichiara alcun certificato.

Budget e famiglie sono stati fissati prima di completare le misure. Tutti
i casi sono conservati, anche quando non migliorano. Il riferimento
dispone di più tempo; è un'indagine del margine, non una gara di latenza
a parità di CPU. Il limite wall-clock del solver può produrre risultati
diversi con carichi o hardware diversi, a differenza del budget per
candidati del motore di produzione. Gli ordini misurati sono salvati.

## Verifiche eseguite

- Benchmark completo: **60/60** casi, nessun errore di confronto o
  fattibilità. Sono conservati tutti gli ordini e gli esiti.
- Ambiente isolato con OR-Tools: **13 test specifici superati**, inclusi
  replay indipendente, prove esaustive dei certificati, assenza di chiamate
  di rete, identità delle matrici e ricalcolo di ogni risultato salvato.
- Suite generale sul commit dell'ottimizzatore misurato: **397 passed,
  7 skipped**, 370,54 s. Cinque skip riguardano il solver opzionale,
  verificato nell'ambiente dedicato; due richiedono `TEST_POSTGRES_URL`.
  Usati PATH della virtualenv e `PYTEST_ADDOPTS=-p no:cacheprovider
  --basetemp=.test-tmp-road-margin` per le directory temporanee Windows.
- Prima della pubblicazione è stato integrato con fast-forward
  `d6b862e` (pagina Depositi), che non modifica l'ottimizzatore.
  Sullo stato integrato: **15 test superati** (Depositi + tutti i 13
  test del benchmark), **31 test Node superati**, build Docker riuscita.
- `git diff --check`: superato. I solver restano fuori dalle dipendenze
  di produzione; gli appositi test opzionali possono essere saltati nella
  CI ordinaria e sono eseguiti integralmente nell'ambiente di ricerca.

## Provenienza e riproduzione

- Matrici: `tests/fixtures/road_margin_matrices.json`, con timestamp,
  coordinate richieste e agganciate, distanze di aggancio e attribuzione.
- OSM PBF locale: `sud-latest.osm.pbf`; SHA-256
  `a8791e61708f1e3e0d0afa1159c4c4b7931d8d06adf87d937aebcedd7a8011d1`.
  La data interna dell'estratto OSM non è stata verificata: la data di
  acquisizione delle matrici non è la data di aggiornamento della mappa.
- Immagine OSRM in esecuzione:
  `sha256:8a1b1bc938412f15f9b5b32d794c4ec6bf4a85dfbbabfa0a014b70b187edb53b`.
- Il report registra l'hash SHA-256 del file matrici UTF-8 con newline
  normalizzate a LF (portabile fra Windows e Linux), versione solver, ordini,
  chilometri, durata, attese, fattibilità, tempi CPU/wall e diagnostica
  della ricerca Girofacile.

```powershell
python -m venv .venv-benchmark
.venv-benchmark/Scripts/python.exe -m pip install -r tests/requirements-routing-benchmark.txt
.venv-benchmark/Scripts/python.exe -m pytest tests/test_road_margin_benchmark.py -q
# Offline: usa esclusivamente le matrici versionate.
.venv-benchmark/Scripts/python.exe tests/road_margin_benchmark.py
.venv-benchmark/Scripts/python.exe tests/summarize_road_margin.py
# Solo per acquisire un nuovo dataset da un proprio OSRM locale:
.venv-benchmark/Scripts/python.exe tests/road_margin_benchmark.py --collect
```

La raccolta e l'esecuzione sono separate. Il benchmark salva un checkpoint
dopo ogni caso: un file parziale non equivale a una prova completa;
il numero atteso per la configurazione predefinita è 60.

Riferimenti tecnici: [OSRM Table e significato delle distanze](https://project-osrm.org/docs/v5.24.0/api/),
[finestre in OR-Tools Routing](https://developers.google.com/optimization/routing/vrptw),
[limiti della ricerca](https://developers.google.com/optimization/routing/routing_options),
[stati e certificazione CP-SAT](https://developers.google.com/optimization/cp/cp_solver).
Dati stradali © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
distribuiti secondo ODbL. Non sono incluse informazioni sui clienti.

## Risultati misurati

| Fermate | Casi migliorabili / 12 | Km Girofacile → migliore (somma) | Margine trovato aggregato | Margine mediano per giro | Ottimi km certificati / 12 |
|---:|---:|---:|---:|---:|---:|
| 8 | 0 | 996.595 → 996.595 | 0.00% | 0.00% | 12 |
| 15 | 3 | 1104.705 → 1104.144 | 0.05% | 0.00% | 11 |
| 20 | 9 | 1244.119 → 1224.496 | 1.58% | 1.28% | 0 |
| 30 | 12 | 1383.370 → 1333.552 | 3.60% | 4.33% | 0 |
| 50 | 12 | 1600.282 → 1529.748 | 4.41% | 5.16% | 0 |

**36/60 casi migliorabili; 24 senza ulteriore riduzione trovata.** Il margine aggregato sul totale dei giri è 2.22%. Tutti i giri manuali, Girofacile e migliori di riferimento sono fattibili.

Di questi miglioramenti, **33 sono almeno 100 metri**. Il conteggio include anche differenze minime sulla matrice discretizzata, che non vanno interpretate come risparmi fisici affidabili: per esempio un metro su 30 fermate è inferiore all'incertezza introdotta dall'arrotondamento degli archi.

Le somme aggregano istanze sovrapposte e non costituiscono una stima statistica del risparmio su una flotta. Il margine zero senza certificato non dimostra ottimalità.

Rispetto all’ordine geografico manuale simulato, Girofacile riduce i km totali da 7916.378 a 6329.071 (20.05%). Nessun ordine iniziale simulato batte Girofacile: è coerente con il fatto che il motore lo conserva fra i candidati, non dimostra superiorità rispetto a un operatore esperto.

Il solver avviato dal solo ordine manuale trova meno km di Girofacile in **34/60** casi e più km in **2/60**. La ricerca avviata anche da Girofacile serve a misurare il margine senza perdere il suo lavoro; i risultati separati restano nel JSON.

| Famiglia | Casi migliorabili / 20 | Margine trovato aggregato |
|---|---:|---:|
| urban | 14 | 5.53% |
| provincial | 11 | 1.71% |
| mixed | 11 | 1.44% |

### Tempi e casi esemplificativi

| Fermate | CPU Girofacile mediana (s) | Wall Girofacile mediana (s) | CPU riferimento mediana (s) | Wall riferimento mediana (s) |
|---:|---:|---:|---:|---:|
| 8 | 5.570 | 5.696 | 5.836 | 6.057 |
| 15 | 0.930 | 0.964 | 6.055 | 6.474 |
| 20 | 0.883 | 0.960 | 5.742 | 6.014 |
| 30 | 1.844 | 1.902 | 5.422 | 6.014 |
| 50 | 4.156 | 4.947 | 5.828 | 6.016 |

Il riferimento include due ricerche fino a 3 secondi e, fino a 15 fermate, la certificazione fino a 5 secondi. Non è un confronto a parità di latenza.

- `urban-50-free-open`: 73.896 → 64.778 km, **−12.34%**; durata 417.7 → 404.4 min. Fattibilità preservata; ottimo km non certificato.
- `urban-30-windows-closed`: 71.078 → 63.605 km, **−10.51%**; durata 347.3 → 313.3 min. Fattibilità preservata; ottimo km non certificato.
- `provincial-50-free-open`: 112.239 → 101.602 km, **−9.48%**; durata 467.0 → 460.9 min. Fattibilità preservata; ottimo km non certificato.
- `urban-30-free-closed`: 61.921 → 56.260 km, **−9.14%**; durata 276.8 → 266.8 min. Fattibilità preservata; ottimo km non certificato.
- `urban-50-windows-closed`: 88.794 → 80.834 km, **−8.96%**; durata 515.9 → 520.8 min. Fattibilità preservata; ottimo km non certificato.

### Interpretazione operativa

I casi migliorati dimostrano che esistono ordini fattibili più corti di quelli trovati dal motore attuale. È ragionevole valutare una modalità di ottimizzazione più approfondita per giri grandi. Non dimostrano che un altro gestionale otterrebbe questi risultati, né che integrare un solver produrrebbe automaticamente gli stessi benefici su dati reali.

Prima di cambiare il motore servono un campione reale anonimizzato, vincoli operativi completi e un confronto a pari budget. Un pilota potrebbe mantenere il risultato attuale come candidato e spendere tempo aggiuntivo soltanto quando richiesto. Il software di produzione resta invariato in questo commit.
