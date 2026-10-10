# Ordini — analisi e primo intervento (10 ottobre 2026)

## Ambito consegnato

Questo intervento realizza analisi, architettura, schema incrementale e archivio
Ordini di base, come richiesto nella sequenza di sviluppo. Non completa i cinque
interventi in un unico rilascio. La pianificazione manuale rimane quella esistente.

Funzioni operative:

- Voce Ordini nella navigazione desktop e nel menu mobile.
- Creazione manuale, dettaglio, correzione dei dati operativi, annullamento.
- Elenco con ricerca, filtri per stato/fonte/data richiesta, ordinamento,
  paginazione server (25 righe nell'interfaccia; massimo 100 nell'API), tabella e schede.
- Quattro indicatori aziendali, indipendenti dai filtri dell'elenco.
- Destinatari occasionali: nessuna creazione automatica di clienti.
- Articoli facoltativi accettati dalla API di creazione e mostrati nel dettaglio.
- Dati ricevuti immutati, correzioni e autore registrati negli eventi; nel dettaglio
  sono mostrati gli ultimi 100 eventi, con limite esplicito. Gli eventi più vecchi
  restano nel database.
- Geocodifica tramite il servizio esistente, su comando esplicito. Stato Pronto
  solo con destinatario, indirizzo e verifica dell'indirizzo corrente.
- Distinzione tra assenza, No esplicito e Sì per sponda, transpallet e ZTL.
- Blocco di modifiche obsolete tramite versione e lock PostgreSQL; nuovo controllo
  dopo la geocodifica, che può effettuare commit per il registro dei consumi API.
- Autenticazione e permessi aziendali esistenti, senza nuove quote commerciali.

## Analisi iniziale e riuso

Base analizzata: `origin/main` a `878e7df`. Checkout iniziale quattro commit indietro;
aggiornamento fast-forward. Il ramo locale main era occupato da `.tracking-work`:
il lavoro è stato eseguito su HEAD staccato da origin/main, senza creare altri
rami, modificare quel worktree o includere `.tracking-work/` e `data/pod_storage/`.

| Area | Implementazione esistente e decisione |
| --- | --- |
| Azienda e accessi | `app/models.py`, `core/dependencies.py`, `services/sessions.py`: l'azienda è User; `current_user` risolve l'azienda anche per il collaboratore. Tutte le query API Ordini filtrano user_id. |
| Permessi | `services/company_permissions.py` applica regole su metodo e template esatto. Aggiunte chiavi esplicite; nessuna espansione dei permessi degli account già salvati. |
| Clienti | Customer conserva indirizzo, preferenze e geocodifica; soft delete. Ordini resta un archivio separato, senza modifiche a queste anagrafiche. |
| Mezzi, autisti, depositi | Router dedicati, proprietà aziendale e soft delete; capacità e disponibilità restano controlli del pianificatore esistente. |
| Importazione Clienti | `services/customer_import.py`: pandas, CSV/XLSX, limite 10 MB, preflight atomico e invalidazione geocodifica. Da riusare come convenzione nella fase import Ordini, senza cambiare il flusso Clienti. |
| Pianificazione | `routers/routes.py`: optimize/recalculate generano o aggiornano una bozza; program è il comando esplicito di programmazione. Il ricalcolo può eliminare e ricreare Delivery. Non modificato in questa fase. |
| Consegne | `services/route_execution.py`, route_schedule e i moduli POD/tracking gestiscono avanzamento ed evidenze. I nuovi ordini non interferiscono con questi flussi. |
| Indirizzi | Riutilizzato `services/occasional_stops.verify_stop_address`; il riconoscimento futuro di un cliente non varrà come verifica di un nuovo indirizzo. |
| Piani | `services/plan_catalog.py`, plans e usage_limits: Starter/Business/Pro e controllo scritture per abbonamento. Nessuna nuova limitazione commerciale per Ordini. |
| Frontend | Pannelli, pulsanti, campi, tabelle e normalizzazione del design system esistenti. Logica e CSS dedicati; core.js e routes.py non modificati. |
| Migrazioni | `app/migrations.py`: versioni esplicite e advisory lock PostgreSQL. Nuovo passo additivo nella stessa transazione del relativo marcatore. |
| Test | pytest con database isolati, fixture PostgreSQL a schema temporaneo, Node e Playwright; Actions scopre automaticamente i nuovi test pytest. |

Baseline prima delle modifiche: **719 passed, 23 skipped** per Python; **110 pass,
2 fail** per Node. Errori JavaScript preesistenti:

- `planning fuel KPI stays empty until a vehicle is selected`
- `account password change stays inline and separate from profile save`

I test saltati includono quelli che richiedono TEST_POSTGRES_URL e OR-Tools;
non sono stati disabilitati test o controlli per ottenere un risultato verde.

## Database e architettura

Migrazione **20261010_01**, sette nuove tabelle:

- `order_sources`: fonte per azienda, chiave univoca aziendale, tipo/stato e
  configurazione; campo hash credenziali predisposto, senza emissione credenziali.
- `orders`: identificativo esterno univoco per azienda e fonte; numero visibile,
  destinatario, data, payload originale, dati operativi, verifica indirizzo,
  versione, timestamp, stati distinti di acquisizione/verifica/consegna e stato operativo.
- `order_items`: righe articolo originali facoltative.
- `order_events`: storico append-only dal servizio, con attore e valori prima/dopo.
- `order_import_runs`: struttura per esiti di importazione, non ancora alimentata.
- `customer_source_mappings`: struttura per codici cliente esterni, non ancora alimentata.
- `route_order_assignments`: un'associazione corrente per ordine e chiave stabile
  della fermata, senza FK all'ID transitorio di Delivery.

FK composite impediscono una fonte di un'altra azienda e un'associazione con un
ordine di un'altra azienda. I futuri servizi di associazione dovranno validare e
bloccare anche cliente/giro per azienda; non esistono endpoint per impostare oggi
customer_id, source_id o assegnazioni. I campi sono rifiutati dal modello di input.
Non è stata aggiunta alcuna colonna a Clienti, Giri o Consegne.

Le tabelle di assegnazione sono una base strutturale: il test dimostra che la
cancellazione/ricreazione di Delivery non cancella l'associazione, ma la propagazione
della chiave fermata nel ricalcolo e le transazioni di programmazione, annullamento
e completamento saranno implementate nel secondo intervento. Non sono dichiarate
operative in questo rilascio. Gli eventi conserveranno le associazioni storiche
quando una futura cancellazione del giro libererà quella corrente.

Stati oggi modificabili: Nuovo, Da verificare, Pronto, Annullato. Gli stati
Assegnato/In consegna/Consegnato/Non consegnato sono predisposti e non impostabili
liberamente dalla API. Ordini annullati o assegnati sono protetti dalle correzioni.
L'annullamento è conservativo e non riapre l'ordine in questo primo intervento.

## API di base

Autenticazione: sessione aziendale già esistente; non è la futura API di ingestione.

| Metodo e percorso | Funzione | Permesso collaboratore |
| --- | --- | --- |
| GET /api/orders | Elenco e indicatori | orders.read |
| GET /api/orders/{order_id} | Dettaglio, originali e storico | orders.read |
| POST /api/orders | Creazione manuale | orders.create |
| PUT /api/orders/{order_id} | Correzione operativa completa con version | orders.update |
| POST /api/orders/{order_id}/verify-address | Verifica indirizzo con version | orders.update |
| POST /api/orders/{order_id}/status | Transizione con version | orders.update |

I conflitti restituiscono 409; record di altre aziende restituiscono 404; permessi
insufficienti 403; input non validi 422. Il dettaglio restituisce la versione da
inviare nelle modifiche. Le correzioni non modificano original_payload o OrderItems.
Il numero di ordine manuale può ripetersi; il suo external_id è un UUID generato.

Il profilo Operatore mantiene il contratto esistente di tutte le funzioni delegabili,
con elenco esplicito. Pianificatore e Sola lettura ricevono solo orders.read in
questa fase. I permessi futuri import/match/integrations/plan sono nel catalogo ma
non attivano servizi non implementati. Nessuna API restituisce hash o credenziali.

## Integrazioni predisposte, non attive

La pagina separata Collega i tuoi ordini spiega lo stato effettivo di gestionale,
CSV/XLSX, email ed e-commerce. Il pulsante Importa file è disabilitato e identificato
come funzione in sviluppo. Nessuna fonte esterna è attivabile o simulata.

Intervento 2: selezioni persistenti, configurazione del giro esistente, fermate,
associazioni, controlli di capacità e doppia assegnazione, ciclo di vita del giro.
Intervento 3: riconoscimento certo/probabile, conferme, priorità dei dati e
raggruppamento compatibile. Intervento 4: wizard, import reale, mapping, API,
credenziali e gestione fonti. Intervento 5: regressioni dell'intero percorso e
verifiche complete. Le nuove API non dichiarano questi percorsi già disponibili.

## Verifica del primo intervento

- Test dedicati: `test_orders.py`, `test_orders_permissions.py`,
  `test_orders_postgres.py`. Ultima esecuzione: **17 passed**, inclusa la corsa tra
  geocodifica e modifica concorrente su PostgreSQL 16 temporaneo.
- Gruppo Ordini + regressioni permessi/inviti/migrazioni PostgreSQL: **45 passed**
  prima dell'aggiunta dell'ultimo test di concorrenza.
- Suite Python completa dopo l'integrazione: **732 passed, 26 skipped**.
  L'ultimo test PostgreSQL aggiunto successivamente è incluso nel gruppo dedicato
  di 17 test superati, eseguito separatamente.
- Node dopo l'integrazione: **110 pass, 2 fail**, stessi errori della baseline.
- `check_orders_ui.py`: API Ordini reale su SQLite isolato, resto della shell con
  fixture; verifica creazione, correzione, errore recuperabile, escaping, filtri,
  stato vuoto e collegamenti a 390/768/1024/1440 px. Geocodifica esterna non chiamata.
- Gli screenshot sono artefatti in `test-results/orders-responsive/` e in Actions.
  In locale si può scegliere Chrome con `GF_TEST_BROWSER_CHANNEL=chrome`;
  in CI viene usato Chromium installato da Playwright.

## File interessati

Nuovi: `app/order_models.py`, `app/schemas/orders.py`, `app/services/orders.py`,
`app/routers/orders.py`, `static/dashboard/js/orders.js`,
`static/dashboard/css/orders.css`, i quattro file di test Ordini sopra indicati,
e questo documento.

Punti di collegamento: `app/models.py`, `app/main.py`, `app/migrations.py`,
`app/services/company_permissions.py`, `static/dashboard/index.html`,
`static/dashboard/js/navigation.js`, `static/dashboard/js/collaborators.js`,
`.github/workflows/tests.yml`. Adeguati i fixture/versioni attese in
`tests/test_audit_postgres.py` e `tests/test_collaborator_invitations_postgres.py`
per conservare il controllo preciso delle migrazioni storiche e della nuova versione.

## Rilascio controllato e recupero

Nessuna migrazione applicata a Neon o al database operativo durante lo sviluppo.
I test PostgreSQL usano un container temporaneo su loopback e schemi eliminabili.

1. Verificare i controlli CI e distinguere i due errori Node preesistenti.
2. Salvare un backup PostgreSQL e verificarne il ripristino su un database separato
   con gli strumenti già previsti dal progetto; conservare un punto di recupero
   Neon prima del rilascio. Non inserire URL o credenziali nei sorgenti.
3. Su staging ripristinato dal backup, verificare i marcatori correnti, applicare
   `python -m app.migrations` e ripeterlo: il secondo passaggio non deve cambiare
   dati o marcatori. Controllare le anagrafiche e un giro esistente.
4. Pianificare la finestra di rilascio. **scripts/start_app.sh esegue già le
   migrazioni all'avvio**: autorizzare l'avvio della nuova immagine soltanto dopo
   backup e verifica di staging. Per avvii personalizzati applicare lo stesso
   comando prima di riavviare i worker.
5. Controllare sessione titolare/collaboratore, elenco vuoto, creazione e correzione
   di un ordine di prova autorizzato, poi pianificazione manuale esistente.
6. In caso di rollback dell'applicazione mantenere le nuove tabelle e i marcatori:
   il vecchio codice non li usa e verifica la presenza della propria versione.
   Non eseguire DROP o ripristini distruttivi sui dati aggiunti nel frattempo.
   Un eventuale recupero dati deve passare da un ripristino separato e riconciliazione.

Rischi aperti: funzioni degli interventi successivi ancora assenti; geocodifica reale
subordinata alla configurazione Google esistente e non chiamata dai test;
ricerca testuale con contains da misurare su volumi reali, pur con elenco paginato
e indici azienda/stato/data; history API limitata agli ultimi 100 eventi; errori
Node preesistenti e test OR-Tools non disponibili nell'ambiente locale.
