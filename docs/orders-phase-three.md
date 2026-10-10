# Ordini: terzo intervento

## Funzioni operative

- Riconoscimento automatico alla creazione/correzione: codice cliente già associato alla stessa fonte e azienda, oppure un solo cliente attivo con nome e indirizzo normalizzati identici. Nessuna associazione approssimativa automatica, nessun cliente creato implicitamente.
- Dettaglio ordine con confronto tra nomi e indirizzi, proposta da confermare, ricerca aziendale (massimo 20 risultati), scelta persistente «No, mantieni separati» e creazione esplicita dell'anagrafica. Il comando Riconosci cliente permette di rivalutare anche ordini già presenti.
- Conferme dei codici esterni conservate nella tabella di mapping già predisposta. Un codice associato a un altro cliente attivo non viene sovrascritto silenziosamente: viene restituito un conflitto. Un collegamento verso un cliente non più disponibile può essere corretto con una nuova conferma.
- La creazione esplicita rispetta permessi e limiti Clienti già esistenti, avviene nella stessa transazione del collegamento e non attribuisce all'anagrafica una verifica indirizzo inesistente.
- Anomalie leggibili: destinatario/indirizzo mancanti, verifica indirizzo necessaria, associazione dubbia/non valida, peso o colli mancanti. I problemi bloccanti impediscono lo stato Pronto; la mancanza di peso/colli resta un avviso.
- Nome/indirizzo e preferenze ereditati solo quando non specificati. Un No esplicito prevale sulle preferenze del cliente; gli orari dell'ordine prevalgono su entrambe le finestre abituali. Note, sponda, ZTL, transpallet e tempo di scarico sono riutilizzati senza alterare l'anagrafica o il payload originale. L'interfaccia segnala i dati «dal cliente».
- Ogni indirizzo effettivo richiede verifica con il servizio già esistente, anche dopo il riconoscimento cliente. Cambiare un indirizzo ereditato rende inutilizzabile la precedente prova.
- Raggruppamento su scelta esplicita nella configurazione del giro: stessa destinazione verificata, stesso destinatario e requisiti coerenti; finestre orarie intersecate, data richiesta verificata contro quella del giro. Destinazioni o requisiti diversi rimangono separati.
- Peso e colli sommati, note conservate con numero ordine, riferimenti di tutti gli ordini mantenuti. Pallet e volume sono sommati soltanto se tutti i membri hanno il dato. Tempo di scarico della fermata pari al massimo dei membri, modificabile prima del calcolo.
- Dettaglio espandibile degli ordini nella fermata, anche nei portali autista/operatore. Ricalcolo, separazione dei gruppi ed esiti conservano e aggiornano correttamente tutti i collegamenti.

## Database e file

Migrazione additiva `20261011_01`: colonna `orders.customer_resolution`, valore iniziale pending. Riutilizzate `customer_source_mappings`, `order_events`, `order_planning_selections` e `route_order_assignments`. Nessuna tabella o dato eliminato. La scelta di raggruppamento è conservata nella configurazione JSON esistente; le chiavi delle fermate sono derivate dall'insieme ordinato degli ID ordine, mantenendo compatibili quelle dei singoli ordini del secondo intervento.

Nuovi file: `app/services/order_customers.py`, `app/services/order_grouping.py`, `static/dashboard/js/order-customers.js`, `tests/test_order_customers_grouping.py`, questo report.

Modificati: modelli e migrazioni ordini; schemi ordini/fermate/configurazione; router ordini, autista e operatore; servizi ordini, pianificazione, associazioni ai giri e permessi; pagina dashboard e moduli JS ordini/pianificazione/core; pagine autista/operatore; test permessi, PostgreSQL e browser. La logica del motore di ottimizzazione e dell'importazione Clienti rimane quella esistente.

## Verifica e limiti

I test dedicati coprono corrispondenze certe e duplicate, conferma e separazione, mapping e isolamento aziendale, clienti inattivi, false esplicito, indirizzi ereditati/diversi, creazione esplicita, controlli di versione, permessi, intersezione orari, gruppi incompatibili, ricalcolo, separazione dei gruppi ed esito collettivo. PostgreSQL verifica migrazione ripetibile, prenotazioni e conferme concorrenti. Browser con API reale e risorse circostanti simulate a 390/768/1024/1440 px. Nessun provider operativo contattato.

La ricerca di somiglianze è una proposta conservativa, non una certificazione d'identità. Il confronto normalizzato scorre le anagrafiche attive lato server, a blocchi: monitorare tempi su archivi molto grandi. Le proposte sono limitate a 10 e la ricerca manuale a 20 risultati. Nessun elenco completo viene trasferito al browser.

Raggruppare/separare tramite il comando rigenera le fermate dai dati degli ordini: l'interfaccia richiede conferma prima di sostituire modifiche alle sole fermate. Il raggruppamento non divide automaticamente ordini o carichi in più veicoli. Requisiti differenti mantengono fermate distinte anche se una combinazione potrebbe risultare operativamente possibile. I valori mancanti di peso/colli richiedono verifica manuale; capacità pallet/volume/transpallet non sono validate automaticamente.

Importazione CSV/XLSX, configurazione fonti e API esterna restano al quarto intervento. I codici esterni sono già gestiti dal servizio ma non viene simulata alcuna acquisizione.

## Esiti finali

- Suite Python completa: **749 passati, 28 saltati**. Successivo controllo mirato dell'ultima correzione dei mapping inattivi e dei permessi: **11 passati**, incluso il caso aggiunto dopo l'avvio della suite completa.
- PostgreSQL locale temporaneo: **16 test distinti passati** (15 nel blocco migrazioni/audit/ordini/inviti, poi 3 di pianificazione/mapping, di cui 2 ripetuti). Conferme concorrenti dello stesso codice verso clienti diversi: una conferma, un conflitto 409, nessuna associazione parziale.
- JavaScript: **110 passati, 2 errori preesistenti**: `planning fuel KPI stays empty until a vehicle is selected` e `account password change stays inline and separate from profile save`.
- Chrome: flusso creazione/correzione, conferma cliente, escaping, filtri, selezione persistente e raggruppamento reale passato a **390, 768, 1024 e 1440 px**. Verificata assenza di overflow orizzontale della pagina e ispezionata la schermata mobile.
- `git diff --check` superato. La CI esistente scopre i nuovi test Python ed esegue lo script browser aggiornato; i due errori Node preesistenti possono ancora interrompere quel workflow.

## Rilascio

Nessuna modifica a Neon o ai dati di produzione. Prima di avviare la nuova versione: backup con ripristino verificato, prova su staging, applicazione ripetuta di `python -m app.migrations` e controllo di un ordine e di un giro manuale preesistenti. `scripts/start_app.sh` esegue già la migrazione all'avvio: autorizzare il riavvio operativo solo nel rilascio controllato. In rollback conservare colonna e marcatori; non cancellare mapping o associazioni già creati. Procedura di recupero completa in `docs/orders-phase-one.md`.
