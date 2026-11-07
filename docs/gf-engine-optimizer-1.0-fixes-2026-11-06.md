# GF Engine Optimizer 1.0 — correzioni del 6 novembre 2026

Correzioni successive alla revisione `87a846e`. Il motore continua a confrontare ricerca
interna, OR-Tools e PyVRP sul calendario operativo di GiroFacile.

## Punteggio e partenza

Il costo è `km + minuti di lavoro` (un'ora vale 60 km equivalenti). La quota di attesa
eliminabile non è più soltanto teorica: un calendario all'indietro verifica finestre,
scarichi non interrompibili e pause fisse, rispettando il rientro del giro. La partenza
si sposta a passi di cinque minuti rispetto all'orario richiesto e al massimo dell'attesa
per apertura clienti. Una pausa da sola non autorizza uno spostamento. Le pause che
restano nel giro continuano a essere conteggiate. Il punteggio e la proposta usano lo
stesso slittamento; un orario bloccato, anche nel secondo passaggio traffico, non ha sconti.

Sono inclusi due controesempi della revisione precedente, entrambi con 6 km:

- Con pausa 08:30–09:00, cliente A aperto dalle 09:00 e cliente B libero, veniva scelto
  A→B da 125 minuti invece di B→A da 105 minuti.
- Con partenza fissa 08:00 e cliente A aperto dalle 10:00, veniva scelto A→B da 175 minuti
  invece di B→A da 155 minuti.

Le regressioni verificano la scelta del percorso, il lavoro dichiarato, le partenze
effettive e la coerenza dei valutatori canonico, veloce e preparato della flotta.

## Protezioni PyVRP

Prima di creare il modello si contano copie, profili e archi. Con 100 consegne, 10
calendari diversi e due finestre per cliente si arrivava a 40.040.010 archi; il caso ora
viene escluso prima dell'allocazione, conservando il piano degli altri motori.

`FLEET_PYVRP_MAX_EDGES` ha valore predefinito 250.000, minimo 1.000 e limite massimo
1.000.000 anche se configurato erroneamente. La diagnostica espone dimensioni e motivo
del fallback (`model-size-limit` o `time-limit`).

`FLEET_PYVRP_SECONDS` è condiviso fra preparazione, ricerca, eventuale secondo tentativo
e bilanciamento. Il primo tentativo può usare l'intera fase quando ha già trovato un
piano fattibile, anche parziale: continua la stessa ricerca per recuperare le consegne
ancora escluse. Soltanto se è ancora non fattibile al 65% della fase cede il residuo al
retry con penalità diverse; il retry non riceve un nuovo budget intero. Il controllo usa
il criterio pubblico `FirstFeasible` di PyVRP, che riconosce il costo sentinella `INT_MAX`
dei piani non fattibili. Una quota fissa del 65% anche nei casi fattibili tagliava la ricerca
e lasciava inutilizzato il tempo residuo: questa ripartizione è stata corretta.
La scadenza è assoluta, con verifiche durante la costruzione e prima di ogni ricerca.
Le operazioni native individuali non sono interrompibili: non è una garanzia di arresto
del processo esattamente al millisecondo. Una proposta già fattibile viene conservata
quando il bilanciamento esaurisce il tempo.

### Ripartizione definitiva del tempo (V1)

Anche con lo stop adattivo, sull'intero prodotto e su un computer Windows più lento
r104 e r112 lasciavano fuori 3 e 5 consegne: al 65% della fase la prima ricerca non
aveva ancora un piano valido, quindi partiva il secondo tentativo con penalità alte,
che preferisce escludere consegne. Con tutto il tempo alla prima ricerca r104 le serve
tutte. Il risultato dipendeva quindi dalla velocità della macchina.

Regola definitiva: la prima ricerca usa tutta la propria fase. Solo se alla fine non è
fattibile, il secondo tentativo riceve al massimo il 35% di `FLEET_PYVRP_SECONDS` in più
(tetto assoluto: 1,35 volte il budget). Nei limiti di durata del bilanciamento non c'è
secondo tentativo: un limite troppo stretto si scarta e si prova il successivo.

Misura sui 36 problemi Solomon, prodotto completo, stesso computer della misura del
5 novembre: 36/36 serviti per intero, scarto medio 0,72% (mediana 0,16%, massimo 6,08%
su r112, che varia tra esecuzioni), 15 problemi alla migliore soluzione nota, tempo medio
110 s. Piani reali salvati, stessa data, contro `5e270a3`: stesse consegne servite,
108 km e 4 ore in meno in totale, nessun peggioramento oltre la variabilità della ricerca
a tempo (piano 32: giro più lungo 237 invece di 233 minuti, con 64 km in meno).

Limite degli archi: misurato su questo computer, 250.000 archi costano 0,5 s e 25 MB,
1.000.000 circa 2,4 s e 100 MB prima della ricerca. Il piano reale più grande ne usa
50.000: il predefinito resta 250.000, alzabile con `FLEET_PYVRP_MAX_EDGES`.

### Arrotondamento nella partenza più tarda e vicinanza all'ottimo (V1)

`realizable_departure_slack` ripercorre il giro all'indietro e confronta l'inizio scarico
più tardo con l'apertura della fascia. Su una catena tesa dopo un'attesa d'apertura il
valore ritrovato era 899,9999999999999 invece di 900: la fascia risultava mancata e lo
spostamento della partenza veniva azzerato. Nel piano reale 32 un giro di 206 minuti di
lavoro ne valeva 655, e le proposte di PyVRP migliori venivano scartate in entrambe le
strategie. Ora il confronto ammette uno scarto di 1e-9 minuti (gli errori misurati sono
circa 1e-13, sotto il margine 1e-7 usato per le pause). Test di regressione:
`test_tight_route_after_an_opening_wait_keeps_its_later_departure`.

Piani reali salvati, stessa data, contro `5e270a3`: stesse consegne servite (17 non
servite in entrambi, per mezzi o fasce), 7963 → 7855 km, 254,7 → 250,0 ore, nessun piano
peggiore oltre la variabilità della ricerca a tempo (piano 20: 16 km in più e 0,1 ore in
meno). «Distribuisci il lavoro», giro più lungo: piano 32 da 233 a 208 minuti, piano 24
da 439 a 413, piano 47 da 216 a 213, gli altri invariati.

Vicinanza all'ottimo di «Distribuisci il lavoro», 30 s contro 300 s di PyVRP:
- Solomon c102, r108, rc108, r205, r209: giro più lungo migliore dello 0–0,9% con 300 s;
- piani reali: 32 da 208 a 206 minuti, 24 da 413 a 395, 47 da 213 a 217 (variabilità).

Il guadagno di una ricerca dieci volte più lunga è piccolo: il budget predefinito resta
30 s. Nei piani con una pausa fissa il valore `longest_min` del bilanciamento PyVRP non
conta la pausa, che invece resta nelle ore dell'autista del calcolo canonico (piano 47:
184,6 contro 212,8 minuti sullo stesso giro, che attraversa la pausa 13:00–13:30).

### Verifica successiva della ripartizione del tempo: Solomon R104

È stata segnalata una perdita di tre consegne dopo la riserva fissa del 35%. La prova
locale con i dati ufficiali SINTEF, nove mezzi da 200 unità e 30 secondi non ha riprodotto
le tre esclusioni: entrambe le revisioni servono tutti i cento clienti. Conferma però il
taglio del tempo utile e il vantaggio della correzione adattiva:

| Versione del componente PyVRP | Tempo misurato | Servite | Distanza |
| --- | ---: | ---: | ---: |
| `34f6ef9`, quota fissa | 19,554 s su 30 | 100/100 | 1.022,52145 |
| Stop adattivo, stessa ricerca continua | 30,004 s su 30 | 100/100 | 1.007,31058 |

Nessun errore nel replay indipendente: capacità, inizio del servizio entro la finestra
originale Solomon, rientro in deposito entro 230 e unicità delle consegne. La seconda
distanza arrotondata coincide con 1.007,31, il valore riportato da
[SINTEF per R104 con nove mezzi](https://www.sintef.no/projectweb/top/vrptw/100-customers/).
È un confronto locale del componente, non una nuova campagna su tutte le istanze né una
garanzia dell'ottimo globale del prodotto. La ricerca a tempo può dare risultati diversi
su altre macchine.

La fixture R104 con provenienza e checksum è versionata in `tests/fixtures/solomon/`.
Il confronto si ripete senza rete con:

```sh
python tests/run_pyvrp_r104_benchmark.py --seconds 30 --baseline-ref 34f6ef9 --strict
```

Il controllo usa le nove risorse della soluzione di riferimento, non i 25 veicoli massimi
del file originale. Il report salva ordini completi, controlli indipendenti, versione della
libreria, tempi e hash dei sorgenti; si confrontano i due adattatori PyVRP sul medesimo
calendario corrente. Due esecuzioni locali successive della correzione hanno entrambe
servito 100/100 clienti a distanza 1.007,31058, in circa 30 secondi ciascuna.

Fonte dell'input: [archivio ufficiale Solomon 100](https://www.sintef.no/globalassets/project/top/vrptw/solomon/solomon-100.zip),
voce `In/r104.txt`, SHA-256 del file originale
`dd087124311d91facd81736debbfc7d0f351d27942917e2d76cbafd01e6183b7`.
Le finestre Solomon limitano l'inizio del servizio; nell'adattatore GiroFacile si aggiunge
la durata dello scarico alla chiusura della finestra, perché il calendario del prodotto
vincola la fine dello scarico. Distanze euclidee e tempi sono calcolati in doppia precisione.

### Ripetizioni con ricerca a tempo nell'audit

La pipeline del commit `34f6ef9` ha registrato un solo finding nell'audit: due ricerche
bilanciate sul medesimo input da 100 consegne hanno trovato piani diversi entro il limite
di tempo (`identical_input_not_deterministic`). Nell'artifact GitHub `13533105444` il
replay resta fattibile e non ci sono scarti dai riferimenti esatti o dai testimoni.
Una seed fissa non garantisce lo stesso numero di iterazioni prima di una scadenza reale.

L'audit continua a registrare la variazione, come `repeated_timed_search_changed_result`,
soltanto quando la diagnostica documenta che un solutore a tempo è stato effettivamente
eseguito. Senza tale evidenza la mancata ripetibilità resta un errore. La modifica non
declassa vincoli violati, assegnazioni duplicate, dati pubblici incoerenti o false promesse
di ottimo: questi controlli restano bloccanti. I rapporti riportano separatamente il numero
delle variazioni a tempo. L'adattatore del giro singolo conserva anche il resoconto della
ricerca OR-Tools per applicare la stessa classificazione.

Verifica dell'aggiornamento: 63 test mirati superati (solutore, audit, riferimento
indipendente e fixture R104). Il replay dell'output CI del caso segnalato conferma zero
errori operativi e registra la variazione come osservazione a tempo. Sono state aggiunte
regressioni che mantengono bloccanti sia le assegnazioni duplicate sia gli scarti in un
problema che promette l'ottimo esatto, anche in presenza di diagnostica a tempo.

## Verifiche e confronti

Il riferimento indipendente distingue durata complessiva e lavoro dopo lo slittamento
effettivamente possibile; il bilanciamento usa il secondo valore. Il riferimento non
importa il calendario di produzione per decidere la fattibilità o l'obiettivo.

I confronti storici caricano dal relativo commit congelato anche il calendario e le
funzioni di ricerca condivise, con controllo dei digest e ripristino dei moduli al
termine del confronto. Gli input e il verificatore restano quelli attuali: il confronto
misura l'intero aggiornamento e non attribuisce ogni differenza al solo solutore.

Sono stati inoltre riallineati il requisito di avvio dell'ultima migrazione già esistente
(`20261105_01`) e i test PostgreSQL: elenco completo dei marker, blocco di avvio con
migrazione pendente e tracking concorrente con un'azienda abilitata alla funzione.

I numeri Solomon nelle relazioni precedenti sono risultati storici: non sono stati
ricalcolati per questa revisione e non sono una prova dell'ottimo globale del nuovo
obiettivo.

### Collaudo della correzione

- Audit indipendente completo (`run_routing_quality_audit.py --profile full --strict`):
  70 problemi, 283 esecuzioni, zero errori, zero scarti nei 240 confronti con riferimento
  esatto, zero scarti dai testimoni della campagna, zero chiamate esterne. In questa
  campagna OR-Tools e PyVRP sono spenti: viene verificata la ricerca interna con i nuovi
  criteri e i calendari. Le prove con solutori attivi sono distinte.
- Entrambi i runner storici passano `--strict` sul caso di sviluppo verificato e sul primo
  holdout a finestre/turni da 50 consegne, efficient e balanced. Sugli holdout OR-Tools e
  PyVRP sono attivi con un secondo ciascuno. Zero errori, regressioni o chiamate esterne;
  hash dei sorgenti invariati durante i confronti. Non è una riesecuzione di tutte le
  combinazioni delle campagne storiche.
- Upgrade holdout: 49→50 consegne servite per entrambe le strategie. Constraint holdout:
  50→50, con miglioramento dell'obiettivo in entrambe. Nel balanced constraint vince
  OR-Tools, mentre il candidato PyVRP con 49 consegne viene scartato.
- Controllo differenziale aggiuntivo del nuovo calendario: 1.559 percorsi fattibili fra
  3.000 casi generati con pause, scarichi e finestre variabili; nessuna differenza fra lo
  slittamento calcolato all'indietro e il replay esaustivo delle partenze a passi di cinque
  minuti. Un confronto indipendente produzione/oracolo su altri 500 casi (289 fattibili)
  concorda su fattibilità e lavoro effettivo.
- Test JavaScript: 45 superati, nessun fallimento o salto.
- Suite Python completa con PostgreSQL 16 e prova reale di backup/ripristino:
  1.533 test superati, zero fallimenti inattesi. Gli 11 controlli PowerShell sono saltati
  perché l'ambiente Linux non dispone di PowerShell; rimane un fallimento atteso già
  documentato sul salvataggio del prezzo carburante manuale zero, esterno a queste
  correzioni del motore. La suite include i test dedicati con OR-Tools e PyVRP attivi.
- La verifica generale GitHub acquisisce la cronologia completa, necessaria per
  controllare l'isolamento dei calendari storici dai commit originali.
- Campagna da 50 consegne su 2, 3, 4 e 5 mezzi, con e senza finestre/turni/pause:
  8 scenari, 16 esecuzioni (ordine originale, entrambe le strategie), OR-Tools e PyVRP
  attivi con un secondo ciascuno. Copertura completa in 16/16 esecuzioni, zero errori,
  zero risultati peggiori del testimone e zero chiamate esterne. I confronti usano la
  partenza effettivamente proposta. Le varianti inversa/mescolata non sono incluse in
  questa campagna aggiuntiva (`run_routing_quality_fifty.py --strict --no-variants`).

Comandi degli holdout con solutori attivi (database SQLite isolato, nessun provider):

```sh
FLEET_ORTOOLS_SECONDS=1 FLEET_PYVRP_SECONDS=1 python tests/run_fleet_upgrade_benchmark.py \
  --case upgrade-holdout-2-windows_shifts-2037101211 --no-variants --strict
FLEET_ORTOOLS_SECONDS=1 FLEET_PYVRP_SECONDS=1 python tests/run_fleet_constraint_benchmark.py \
  --case constraint-holdout-2-windows_shifts-2045110206 --no-variants --no-cache --strict
```
