# Ordini: secondo intervento

## Funzioni operative

- Selezione singola, degli ordini pronti nella pagina o di tutti quelli corrispondenti ai filtri. Selezione persistente per azienda e operatore, con controllo di versione contro aggiornamenti da schede concorrenti.
- Configurazione e fermate salvate sul server e riprendibili dalla pagina Ordini. Limite tecnico di 1000 ordini per selezione, senza nuove quote commerciali.
- «Vai alla pianificazione» apre il pianificatore esistente. «Prosegui» valida risorse e data e precompila le fermate senza calcolare o programmare il giro.
- Indirizzo verificato, destinatario, peso, colli, finestre orarie, sponda, ZTL e note passano al motore esistente. Pallet, volume, transpallet e requisiti restano visibili e sono conservati; il controllo automatico delle capacità resta su peso e colli.
- Le correzioni delle fermate sono snapshot operativi: non sovrascrivono i dati originali dell'ordine. Rimuovere una fermata libera l'ordine, senza cancellarlo.
- Il calcolo riserva gli ordini nella bozza. Associazioni stabili indipendenti dagli ID delle consegne, conservate durante il ricalcolo. Un ordine non può essere prenotato contemporaneamente in due giri.
- Programmazione, avvio, esito consegna e annullamento aggiornano gli ordini. Chiudere manualmente un giro lascia gli ordini senza esito come non consegnati, senza attribuire successi inesistenti. L'annullamento libera gli ordini ancora aperti e conserva i riferimenti degli esiti terminali.
- Il permesso orders.plan è necessario anche per rimuovere tutti i riferimenti ordine da un giro. Le selezioni di operatori diversi rimangono indipendenti.

## Database e file

Migrazione additiva `20261010_02`: tabella `order_planning_selections` con selezione, configurazione, snapshot fermate, versione e unicità azienda/operatore. Nessuna modifica distruttiva a clienti, consegne, documenti o dati originali.

Nuovi file: `app/schemas/order_planning.py`, `app/services/order_planning.py`, `app/services/route_orders.py`, `app/routers/order_planning.py`, `static/dashboard/js/order-planning.js`, `tests/test_order_planning.py`, `tests/test_order_planning_postgres.py` e questo documento.

Collegamenti modificati: `app/main.py`, `app/migrations.py`, `app/order_models.py`, `app/schemas/__init__.py`, `app/services/company_permissions.py`, `app/services/route_execution.py`, `app/services/usage_limits.py`, `app/routers/routes.py`, `app/routers/driver.py`, `app/routers/operator.py`, `static/dashboard/index.html`, `static/dashboard/js/core.js`, `static/dashboard/js/occasional-stops.js`, `static/dashboard/js/orders.js`. Aggiornati `tests/check_orders_ui.py` e i marcatori attesi nei test PostgreSQL audit/inviti.

## Verifiche

- Test integrazione ordini: selezione persistente, isolamento aziendale, conflitti di versione, configurazione non valida, capacità mezzo, metadati, permessi, ricalcolo, programmazione, rimozione, annullamento e consegna.
- PostgreSQL locale temporaneo: migrazioni ripetibili e concorrenti, dati preesistenti preservati, selezioni concorrenti e prenotazione esclusiva. Quattro richieste simultanee: una riesce, tre ricevono 409; nessun giro duplicato residuo.
- Chrome a 390, 768, 1024 e 1440 px: creazione/correzione, escaping, filtri, selezione persistente, accesso al pianificatore e assenza di overflow orizzontale. API ordini reali su database isolato; API del contorno simulate.
- I provider stradali sono simulati nei test: nessuna chiamata a servizi operativi.

### Esiti locali

- Suite Python completa: 737 passati, 28 saltati, una regressione individuata nella chiamata interna alla validazione aziendale (data assente nei giri manuali). Corretta mantenendo opzionale quel dato nel validatore; successiva esecuzione dei 77 test relativi a isolamento aziendale, pianificazione ordini, architettura routing e fermate occasionali: tutti passati. La suite completa non è stata ripetuta dopo questa correzione puntuale.
- PostgreSQL: 14 test passati, inclusi migrazioni, audit, inviti e concorrenza ordini.
- JavaScript: 110 passati; restano due errori preesistenti, `planning fuel KPI stays empty until a vehicle is selected` e `account password change stays inline and separate from profile save`.
- Browser: tutte le quattro larghezze passate, inclusa la precompilazione effettiva delle fermate tramite API.
- `git diff --check`: superato. Avvisi di deprecazione datetime e cache pytest non scrivibile nell'ambiente locale, senza impedire i test.

## Limiti e rilascio

Riconoscimento clienti, anomalie e raggruppamento appartengono al terzo intervento; import CSV/XLSX, acquisizione API e fonti al quarto. In questa fase ogni ordine genera una fermata autonoma, senza creare clienti automaticamente. Il collegamento esterno resta predisposto ma non attivo.

Peso o colli mancanti generano avvisi: verificare il carico prima del calcolo. Volume, pallet e transpallet richiedono verifica operativa manuale. Le selezioni già prenotate mostrano il collegamento al giro; per preparare altri ordini si può svuotare la selezione. La configurazione viene salvata al cambio dei campi, con pulsante di salvataggio esplicito e avviso se si chiude durante un salvataggio pendente.

Nessuna migrazione applicata a Neon o a dati di produzione. Seguire la procedura di backup, ripristino verificato, staging e rilascio controllato descritta in `docs/orders-phase-one.md`. `scripts/start_app.sh` applica le migrazioni all'avvio: predisporre il recupero prima del riavvio della nuova versione. Dopo il rilascio provare un ordine autorizzato fino alla programmazione e verificare anche un giro manuale. In rollback conservare nuove tabelle e marcatori, senza cancellare dati acquisiti.
