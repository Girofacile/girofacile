# Fermate occasionali nella pianificazione

Il pulsante **+ Fermata occasionale**, nella selezione clienti, apre un modulo
responsive. Nome e indirizzo sono obbligatori; peso, colli, finestre, scarico,
ZTL, sponda e note seguono le normali consegne e le preferenze aziendali.
La verifica si avvia dal pulsante **Verifica indirizzo con Google**, come
nell'anagrafica. Cambiare l'indirizzo annulla la verifica. Nome e specifiche
possono essere modificati senza ripetere la richiesta Google.

## Verifica server

`POST /api/routes/verify-stop-address` riceve `indirizzo`, usa il servizio
`geocode_address` esistente e restituisce indirizzo normalizzato, coordinate,
stato e `geocoding_token`. Il token è una firma HMAC con `APP_SECRET`, dedicata
a questo uso e legata all'azienda, all'indirizzo esatto e alle coordinate.
Non è un token di autenticazione e non concede accesso a giri o clienti.

Ogni nuova consegna senza `customer_id` deve presentare dati verificati e
firma corrispondente. Il controllo viene eseguito prima dell'optimizer e
prima della persistenza. Uno stato `verificato` dichiarato dal browser,
coordinate modificate o una firma di un'altra azienda vengono rifiutati.
Le consegne con `customer_id` continuano a usare esclusivamente il controllo
sul cliente appartenente all'azienda e verificato in anagrafica.

La firma attesta un indirizzo e non scade: rimane nello snapshot e in
`Delivery.optimizer_details` per consentire riapertura e ricalcolo senza
nuove chiamate Google. Ruotare `APP_SECRET` richiede una nuova verifica per
successive modifiche/calcoli delle fermate già salvate; la lettura dello
storico resta possibile. Anche vecchie consegne senza cliente e senza firma
restano leggibili, ma vanno verificate prima di usarle in una nuova pianificazione.

## Persistenza e operatività

Non serve una migrazione: `Delivery.customer_id` è già nullable. Nessun
`Customer` viene creato. Nome, indirizzo e specifiche restano nella Delivery;
coordinate, prova della verifica e risultati di routing usano i metadati e
gli snapshot già esistenti.

Ottimizzazione e percorso manuale usano lo stesso motore, senza modifiche
all'algoritmo. La consegna partecipa a capacità, tempi, costi, quote, report,
OSRM, traffico finale e link Maps come le altre. Portale autista, firma, foto,
POD, note e mancata consegna usano i flussi esistenti.

Nel modulo di pianificazione sono disponibili modifica, rimozione, drag/drop
e frecce di riordino utilizzabili anche su touch. La modifica dei giri già
avviati rimane bloccata; non viene introdotta l'aggiunta urgente durante il giro.

## File

- `app/services/occasional_stops.py`: verifica Google e firma degli indirizzi.
- `app/services/customer_planning.py`: regola coordinate condivisa.
- `app/schemas/__init__.py`, `app/routers/routes.py`: API, controlli e metadati.
- `static/dashboard/index.html`, `static/dashboard/js/core.js`: integrazione.
- `static/dashboard/js/occasional-stops.js`, `static/dashboard/css/occasional-stops.css`: modulo responsive e riordino.
- `tests/test_occasional_stops.py`, `tests/test_occasional_stops_ui.cjs`: regressioni backend e frontend.
- `tests/stop_fixture.py`, `tests/test_routing_architecture.py`, `tests/test_optimizer_priorities.py`: fixture verificate per i test del routing esistente.
