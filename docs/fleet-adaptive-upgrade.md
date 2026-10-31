# Motore multi mezzo: ricerca adattiva e verifica indipendente

L’aggiornamento riguarda la distribuzione delle consegne fra mezzi e autisti.
Il motore del giro singolo (`app/optimizer.py`) e il calendario comune non sono
modificati. Una ricerca euristica su cinquanta consegne non certifica l’ottimo
globale: la qualità va misurata insieme a copertura, vincoli e tempo di calcolo.

## Priorità operative

La strategia **Efficiente**, presentata come «Riduci chilometri e tempi», confronta
i piani nell’ordine seguente:

1. Più consegne servite.
2. Meno incompatibilità di accesso segnalate.
3. Meno chilometri complessivi.
4. Meno minuti cumulativi dei giri.
5. Meno mezzi impiegati a parità delle altre misure.

I confronti usano valori interni non arrotondati. I minuti cumulativi comprendono
viaggio, attese, pause e scarico; non coincidono con l’orario di completamento
dell’intera flotta. Ridurre prima i chilometri può aumentare i minuti: il rapporto
di verifica espone entrambe le quantità.

La strategia **Bilanciata** conserva la priorità alla distribuzione del lavoro:
copertura, compatibilità, impiego delle risorse, durata del giro più lungo,
dispersione delle durate, minuti complessivi e chilometri.

## Vincoli e compatibilità

Ogni itinerario accettato passa dal valutatore del calendario in produzione:
capacità in kg e colli, finestre di scarico, durata del servizio, turni, pause,
rientro e disponibilità prima di altri giri o della fine della giornata.
Non viene reintrodotto un limite configurabile della durata del giro.
Deposito, giorno e ora di partenza restano comuni: un autista il cui turno
inizia dopo tale ora è indisponibile. Non vengono cercate partenze differenziate
né pause flessibili; si rispettano le pause fisse dichiarate.

Nella distribuzione automatica una consegna che richiede la **sponda** viene
assegnata soltanto a un mezzo che la possiede. Se non esiste una combinazione
fattibile rimane non assegnata, con una motivazione; non diventa compatibile
grazie a un semplice avviso. Conferma e programmazione ricontrollano la sponda,
anche quando il mezzo è stato modificato dopo l’anteprima.

Le assegnazioni manuali conservano l’avviso e la scelta esplicita dell’operatore.
I piani salvati prima dell’aggiornamento mantengono la politica registrata allora.
L’accesso ZTL conserva la gestione con avviso prevista dall’applicazione.

I mezzi elettrici e diesel mantengono consumi e prezzi specifici nel calcolo dei
costi energia. Non esistono dati di batteria, autonomia e ricarica nel modello
attuale: l’aggiornamento non inventa quei vincoli e non presenta la stima energia
come una verifica dell’autonomia del mezzo.

## Ricerca e integrazioni

Il motore costruisce più proposte iniziali, con identità stabili delle consegne,
urgenza delle finestre, carichi e vicinanza stradale. Conserva proposte fattibili
alternative e cerca miglioramenti attraverso spostamenti, scambi, scambi di
porzioni di itinerario e ricostruzione di gruppi di consegne. Una raccolta limitata
di itinerari già verificati consente di ricombinare assegnazioni di più risorse.
Ogni accettazione mantiene l’identità reale del mezzo e dell’autista.

La ricerca ha un budget deterministico di valutazioni. La ricombinazione è
euristica sul proprio insieme di itinerari; non è una prova di ottimalità del
problema completo. La ricerca esatta resta limitata ai piccoli problemi e al
riordino dei giri brevi, con l’ambito indicato nella diagnostica.

Per cinquanta consegne il budget predefinito passa da 10.000 a **20.000**
valutazioni totali, comprendendo anche la costruzione complementare che conserva
l’esplorazione del precedente motore. Un limite esplicito
`FLEET_MAX_CANDIDATES` continua a valere per l’intera ricerca. Il confronto
prima/dopo include questo maggiore lavoro di calcolo; non isola il contributo
di ogni singola modifica.

La matrice stradale condivisa e la cache vengono riutilizzate per tutte le prove
interne. Non viene effettuata una richiesta API per ogni combinazione. Restano
le integrazioni esistenti per verifica indirizzi e traffico; il confronto offline
usa esclusivamente dati congelati, senza richieste a pagamento o traffico reale.

## Verifica riproducibile

La nuova campagna contiene **31 problemi da 50 consegne**: 19 di sviluppo e 12
con semi distinti riservati alla verifica finale, su flotte da 2, 3, 4 e 5 mezzi.
Combina carichi eterogenei, finestre, turni, due pause, sponde scarse, mezzi
elettrici/diesel e prezzi differenti. Include un autista che inizia dopo la
partenza comune e due consegne fisicamente impossibili, per le quali la massima
copertura dimostrata è 49/50.

I testimoni fattibili sono costruiti senza usare gli output del motore e
controllati da un simulatore indipendente. Provano la copertura raggiungibile,
senza provare il minimo globale dei chilometri. Il costo energia è ricontrollato
separatamente per ogni mezzo.

La baseline congela il servizio di distribuzione, il motore della flotta e il
valutatore degli itinerari al commit
`8df798d0810206fc88068729b5abf36d3770318b`. Il runner verifica gli hash dei tre
file e che giro singolo e calendario comuni non siano cambiati. Il confronto
misura l’intero aggiornamento, compreso il nuovo obiettivo Efficiente.
Gli itinerari precedenti senza sponda obbligatoria sono dichiarati incompatibili
ed esclusi dai confronti diretti di risparmio.

```sh
python tests/run_fleet_upgrade_benchmark.py --strict
python tests/run_fleet_upgrade_benchmark.py --split development --strict
python tests/run_fleet_upgrade_benchmark.py --split holdout --strict
python tests/run_routing_quality_fifty.py --strict --output test-results/fleet-upgrade/fifty-after
```

Serve la cronologia Git contenente il commit della baseline. Il runner salva
input completi, matrici, piani, confronti e hash in
`test-results/fleet-upgrade/comparison/`; modificare i sorgenti durante la
campagna invalida la verifica `--strict`. I rapporti storici restano separati.

I risultati misurati della verifica finale sono riportati nel rapporto generato
`test-results/fleet-upgrade/comparison/report.md`. Una consegna fattibile esclusa,
un vincolo violato, dati mutati o un tentativo di richiesta esterna fanno fallire
la verifica rigorosa. Gli eventuali peggioramenti dell’obiettivo vengono esposti
nel rapporto; il tempo del nucleo offline non è uno SLA di produzione.

La CI esegue il confronto completo e blocca violazioni operative, errori di
contabilità, richieste esterne, sorgenti cambiati durante la misura e regressioni
dell’obiettivo rispetto alla baseline valida. La copertura dei testimoni resta
un obiettivo di qualità pubblicato nel rapporto: il controllo aggiuntivo
`--strict` richiede di raggiungerla in ogni caso e, per i residui sotto, fallisce.

## Risultati del 31 ottobre 2026

La campagna completa esegue **248 calcoli**, cioè 124 coppie prima/dopo sui 31
problemi, con entrambe le strategie e input originale/inverso. Gli hash iniziali
e finali coincidono; il motore misurato ha SHA256
`169090229c6ee194ff36fad20af71a0f29da85a4dd101d0d5f0f05361c595f96`.

Nei 124 nuovi piani non risultano violazioni operative, assegnazioni duplicate,
errori del costo energia o richieste esterne. **111 piani raggiungono la massima
copertura dimostrata**: 103 servono cinquanta consegne e otto servono correttamente
49 consegne nei due problemi fisicamente impossibili. Nei restanti **13 piani
rimangono consegne fattibili escluse**. Per questo il comando `--strict`
termina con codice 1: la verifica di copertura non è dichiarata superata.

Dei piani precedenti, 43 violano i vincoli attuali e sono esclusi dal confronto
dell’obiettivo. Tutte le **81 coppie operative valide** migliorano l’obiettivo
della propria strategia; nessuna peggiora. I risultati dei semi riservati sono
42/48 piani alla copertura massima, rispetto a 69/76 nei problemi di sviluppo.
Non sono state apportate modifiche al motore dopo l’esame dei semi riservati.

Per confrontare direttamente chilometri e lavoro, la tabella seguente restringe
ulteriormente il campione: entrambi i piani devono essere validi, servire
**esattamente le stesse consegne** e avere lo stesso conteggio di incompatibilità.
I valori sono somme sui confronti, non consumi medi di un cliente reale.

| Strategia | Coppie comparabili | km prima | km dopo | Differenza km | Minuti cumulativi prima | Minuti cumulativi dopo | Differenza minuti |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Efficiente | 16 | 2.116,93 | 1.885,90 | −10,91% | 8.566,83 | 8.161,76 | −4,73% |
| Bilanciata | 25 | 3.501,41 | 3.330,16 | −4,89% | 13.779,52 | 13.462,11 | −2,30% |

Il lavoro aggiuntivo costa tempo di calcolo: in questo ambiente la mediana passa
da 0,80 a 3,29 secondi e il 95° percentile da 1,48 a 5,09 secondi. Sono misure
del nucleo con dati congelati, senza database e provider; non certificano tempi
o risparmi della produzione.

### Residui di copertura

Tutti i problemi nella tabella hanno un testimone indipendente da cinquanta
consegne. Le esclusioni sono quindi limiti della ricerca, non impossibilità
fisiche dimostrate. «Entrambi» indica ordine originale e inverso.

| Gruppo | Mezzi | Famiglia | Seme | Strategia | Input | Servite |
| --- | ---: | --- | ---: | --- | --- | ---: |
| Sviluppo | 2 | combined_tight | 2027113229 | Bilanciata | Entrambi | 48/50 |
| Sviluppo | 4 | scarce_tail_lift | 2027112422 | Bilanciata | Inverso | 49/50 |
| Sviluppo | 4 | combined_tight | 2027113431 | Efficiente | Entrambi | 49/50 |
| Sviluppo | 4 | combined_tight | 2027113431 | Bilanciata | Entrambi | 49/50 |
| Verifica finale | 2 | combined_tight | 2037103229 | Bilanciata | Originale | 49/50 |
| Verifica finale | 3 | combined_tight | 2037103330 | Efficiente | Originale | 47/50 |
| Verifica finale | 4 | combined_tight | 2037103431 | Bilanciata | Entrambi | 49/50 |
| Verifica finale | 5 | combined_tight | 2037103532 | Bilanciata | Entrambi | 49/50 |

L’ordine degli input può ancora influenzare il risultato. Il confronto più
ristretto fra le stesse consegne qui sopra esclude anche due coppie Bilanciate
che servono lo stesso numero di fermate ma lasciano escluse consegne differenti;
il rapporto JSON conserva anche questi confronti e tutti gli itinerari.

## Controlli di integrazione

- Suite flotta, turni e audit: **247 test superati**, un fallimento atteso già
  documentato sul prezzo energetico esplicitamente zero, dieci avvisi.
- Interfaccia JavaScript: **40 file di test superati**. La fixture di avvio
  include ora la funzione reale che avvia il controllo delle notifiche.
- Browser reale a **390, 768, 1024 e 1440 px**: configurazione, anteprima,
  spostamento manuale, ricalcolo, salvataggio e programmazione superati.
- Audit generale indipendente: **283 calcoli**, zero errori, zero scarti nei
  240 confronti esatti; include il motore del giro singolo invariato.
- Campagna precedente da cinquanta consegne su 2–5 mezzi: **64/64 esecuzioni
  con copertura completa**, zero violazioni e zero richieste esterne. Le
  precedenti esclusioni su input invertiti sono recuperate; rimangono 17
  variazioni dell’obiettivo cambiando l’ordine degli input.
- Benchmark del riordino breve: prova automatica e assegnazioni manuali da
  cinquanta consegne superate, una sola matrice condivisa per calcolo.

Questi controlli non annullano i tredici residui della campagna eterogenea:
la verifica rigorosa della copertura resta fallita nei casi elencati sopra.
