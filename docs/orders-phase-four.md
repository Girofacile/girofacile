# Ordini — quarto intervento

## Funzioni operative

Configurazione guidata nella dashboard: scelta fra gestionale, file, email ed e-commerce; solo file e API standard sono realmente disponibili. Nome software libero, senza elenco fittizio di compatibilità; indicazioni per un collegamento personalizzato. Campione reale, suggerimenti e associazioni modificabili, verifica per riga, attivazione esplicita e conferma separata dell'importazione.

CSV/XLSX vengono letti con limiti di dimensione, righe, colonne e archivi decompressi. Formule, link esterni e macro XLSX sono rifiutati. Le associazioni restano nella fonte. Gli import ripetuti non duplicano ordini; un lotto errato non applica modifiche parziali. Identificativi numerici interi di meno di 16 cifre vengono convertiti in testo; per conservare zeri iniziali o codici più lunghi usare celle testo.

API `POST /api/order-ingestion`: credenziale Bearer specifica per fonte/azienda, hash persistito, token mostrato solo alla generazione, rotazione e revoca riservate al titolare, validazione, prova senza importazione, batch idempotenti e report. Aggiornamenti del medesimo ordine conservano il primo originale e le correzioni manuali; l'ultimo dato ricevuto è consultabile nel dettaglio. Gli ordini assegnati o chiusi non sono sovrascritti. Nessuna geocodifica o ottimizzazione automatica durante l'acquisizione.

Gestione fonti: elenco paginato, stato reale, numero ordini, ultima acquisizione, problemi, caricamenti successivi, modifica associazioni con nuova validazione, pausa/riattivazione, rimozione logica, storico paginato e report per riga. Cambiare associazioni rende la fonte non attiva fino alla nuova verifica. Fonti API attive ma prive di credenziale sono esplicitamente indicate.

Permessi distinti: `orders.integrations` configura e gestisce le fonti; `orders.import` conferma gli import file. Entrambi permettono consultazione dei report e verifica file; le credenziali restano riservate al titolare. La difesa mantiene i controlli esistenti su azienda e piano attivo.

## Database

Migrazione additiva **20261011_02**:

- `order_sources.version` per modifiche concorrenti.
- `orders.ingested_payload` per l'ultima fotografia esterna, separata dall'originale e dai dati operativi.
- `order_import_runs`: chiave idempotenza, hash payload, campione temporaneo, scadenza e versione fonte.
- Vincolo/indice univoco `uq_order_import_request (source_id, idempotency_key)`.

La migrazione è ripetibile e conserva l'archivio precedente. Nessun dato di produzione o Neon è stato modificato.

## File

Nuovi:

- `app/routers/order_sources.py`
- `app/schemas/order_sources.py`
- `app/services/order_files.py`
- `app/services/order_ingestion.py`
- `app/services/order_source_security.py`
- `static/dashboard/js/order-sources.js`
- `tests/test_order_ingestion.py`
- `tests/test_order_ingestion_postgres.py`
- `docs/order-ingestion-api.md` e questo report.

Aggiornati: `app/main.py`, `app/migrations.py`, `app/order_models.py`, `app/services/company_permissions.py`, `app/services/orders.py`, dashboard HTML/CSS, `navigation.js`, `orders.js`, test browser `check_orders_ui.py`, aspettative migrazioni in `test_audit_postgres.py`, `test_collaborator_invitations_postgres.py`, `test_order_planning_postgres.py`.

## Test eseguiti

- Suite Python completa: **759 passati, 30 saltati, 1 errore**. L'errore è `test_complete_application_imports`: il sottoprocesso Windows è uscito con codice 3221227274, senza stderr/traceback Python. È passato nelle due successive esecuzioni mirate, senza modificare il test o la logica di avvio. Non viene dichiarata verde l'esecuzione completa originaria.
- Controlli mirati acquisizione, PostgreSQL, migrazioni, audit, inviti e pianificazione: **24 passati**, comprendenti **14 casi PostgreSQL**. Coperti stessa richiesta simultanea, chiavi diverse con stesso ordine, conflitti, unicità e aggiornamento da schema precedente senza perdita dati.
- Ultimo controllo dopo l'aggiunta di codici numerici e validazione dei campi API opzionali: **12 passati** (11 acquisizione + avvio completo applicazione).
- Controllo supplementare agenti/API costi/avvio/audit: **34 passati**.
- JavaScript: **110 passati, 2 errori preesistenti**, `planning fuel KPI stays empty until a vehicle is selected` e `account password change stays inline and separate from profile save`. Nessun test indebolito o disabilitato.
- Chrome con API reale e database isolato: creazione/correzione ordini, associazione cliente, selezione e raggruppamento, caricamento CSV, anteprima, attivazione, import effettivo, pausa, configurazione API, emissione e cancellazione della credenziale visibile. Passato a **390/768/1024/1440 px**, senza overflow orizzontale della pagina; schermate mobile/desktop ispezionate.
- La CI esistente scopre i test nuovi ed esegue lo script browser esteso. I due errori Node preesistenti possono interrompere il workflow prima dei test browser.

## Limiti e rischi residui

Email ed e-commerce sono predisposti nell'interfaccia ma **non attivi**. Nessuna sincronizzazione proprietaria simulata: il tecnico del gestionale deve usare il contratto API documentato. Le modifiche API sono fotografie complete, non patch; i campi omessi vanno considerati assenti.

Limiti tecnici: 2 MB, 1000 ordini/lotto, 50 colonne file, 100 fonti/azienda incluse quelle rimosse e manuali, 60 invii/minuto/fonte. L'ulteriore limite IP è per processo: usare anche il proxy per difesa globale. La ricerca conservativa dei clienti può essere costosa su archivi grandi; monitorare latenza prima di aumentare i limiti. I campioni scadono dopo 24 ore e vengono ripuliti al successivo caricamento aziendale; i completati sono eliminati subito. Storico e originali restano disponibili.

La conferma cliente dubbio e la verifica dell'indirizzo restano necessarie prima della pianificazione. Non sono stati alterati motore percorsi, importazione Clienti, giri o documenti di consegna.

## Configurazione e deployment

Contratto completo ed esempio: [API acquisizione ordini](order-ingestion-api.md).

Prima del rilascio: backup e ripristino verificato, prova su staging, migrazione `python -m app.migrations` ripetuta e controllo di ordini/giri preesistenti. `scripts/start_app.sh` applica migrazioni all'avvio: il riavvio operativo deve rientrare nel rilascio controllato. HTTPS e limiti al proxy, credenziali salvate nel gestore segreti del fornitore, prova `dry_run` e primo lotto controllato. In rollback conservare colonne, indici e marcatori: nessuna cancellazione distruttiva degli import acquisiti. Procedura di recupero generale in `orders-phase-one.md`.

Commit e push vengono effettuati direttamente su `origin/main`, includendo solo i file del quarto intervento. Le directory locali preesistenti `.tracking-work/` e `data/pod_storage/` non fanno parte della consegna.


## Correzione dell'avvio da database precedente al modulo Ordini

Il log segnalato dopo il rilascio mostrava `order_sources.user_id: Can't generate DDL for NullType()`. La causa era il caricamento condizionale dei modelli: se tutte le migrazioni anteriori agli ordini erano già registrate, un processo nuovo importava solo `order_models`, senza registrare la tabella `users` e le altre tabelle referenziate nel metadata SQLAlchemy. Il tipo della chiave esterna rimaneva quindi irrisolto. I precedenti test nello stesso processo avevano già importato tutti i modelli e mascheravano il problema.

`run_migrations` ora registra sempre i modelli prima delle operazioni sul database. Nessuna nuova versione di schema o cancellazione di marcatori: le migrazioni mantengono transazioni, lock e possibilità di ripetizione. Il test `tests/test_migrations_cold_start_postgres.py` ricrea un database precedente agli ordini in uno schema PostgreSQL temporaneo, avvia due volte la CLI in sottoprocessi nuovi e controlla conservazione degli utenti e vincolo verso `users`. Prima della correzione riproduce esattamente il `NullType` del log.

Dopo l'aggiornamento del codice, ripetere il consueto avvio che esegue `python -m app.migrations`. Non eliminare tabelle, dati o record di `schema_migrations` per risolvere questo errore. Nessuna migrazione è stata applicata al database operativo durante la diagnosi; per gli ambienti di produzione resta necessaria la procedura di rilascio controllata.

Verifica della correzione: **10 test passati** (avvio CLI a freddo, audit/migrazioni PostgreSQL, acquisizione concorrente, pianificazione e import completo applicazione). `git diff --check` superato.
