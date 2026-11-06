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
e bilanciamento. Il primo tentativo usa il 65% del tempo della propria fase per riservare
il resto al retry con penalità diverse; il retry non riceve un nuovo budget intero.
La scadenza è assoluta, con verifiche durante la costruzione e prima di ogni ricerca.
Le operazioni native individuali non sono interrompibili: non è una garanzia di arresto
del processo esattamente al millisecondo. Una proposta già fattibile viene conservata
quando il bilanciamento esaurisce il tempo.

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
