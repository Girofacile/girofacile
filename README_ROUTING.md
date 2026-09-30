# Routing OSRM, cache persistente, traffico finale e pedaggi

Il motore di ricerca resta in `app/optimizer.py`: ricerca completa fino a 8
consegne, euristiche per giri più grandi, finestre, attese, scarico, capacità,
ZTL, sponda, rientro, diagnostica e ordine manuale sono conservati.

## Configurazione

Le impostazioni Super Admin → Impostazioni SaaS → Routing, traffico e pedaggi
prevalgono sull'env. Nessuna chiave è inclusa nel repository.

| Variabile env | Impostazione piattaforma | Default |
| --- | --- | --- |
| OSRM_URL | osrm_url | http://localhost:5000 |
| OSRM_CACHE_VERSION | osrm_cache_version | v1 |
| OSRM_TABLE_MAX_COORDINATES | osrm_table_max_coordinates | 100 |
| OSRM_ROUTE_MAX_COORDINATES | env | 100 |
| OSRM_ALLOW_PUBLIC_FALLBACK | osrm_allow_public_fallback | false |
| TRAFFIC_PROVIDER | traffic_provider | none |
| MAPBOX_ACCESS_TOKEN | mapbox_access_token | vuoto |
| MAPBOX_MAX_COORDINATES | env | 10, massimo 10 per driving-traffic |
| MAPBOX_TRAFFIC_COST_EUR | mapbox_traffic_cost_eur | 0, impostare costo contrattuale |
| ROUTING_TIMEOUT_SECONDS | env | 15 |
| DISTANCE_CACHE_TTL_DAYS | env | 0: nessuna scadenza |
| TOLL_RATES_JSON | toll_rates_json | {}: tariffe indicative interne |
| TOLL_DATASET_PATH | toll_dataset_path | vuoto |

Esempio di produzione (valori illustrativi, senza credenziali):

```dotenv
APP_ENV=production
OSRM_URL=http://osrm:5000
OSRM_CACHE_VERSION=italy-2026-09
TRAFFIC_PROVIDER=mapbox
MAPBOX_ACCESS_TOKEN=
MAPBOX_TRAFFIC_COST_EUR=0
DISTANCE_CACHE_TTL_DAYS=0
TOLL_DATASET_PATH=/app/data/osm-tolls.json
```

Occorre avviare un'istanza OSRM propria con dataset OSM aggiornato e profilo
stradale appropriato. Il profilo OSRM driving standard non garantisce vincoli
stradali per mezzi pesanti: i vincoli gestionali del mezzo restano quelli
esistenti in GiroFacile. Cambiare versione cache quando cambia il dataset o
il profilo. Il server pubblico OSRM è consentito solo con
`APP_ENV=development` e `OSRM_ALLOW_PUBLIC_FALLBACK=true`; in produzione viene
rifiutato. Il default localhost evita di utilizzare implicitamente un servizio
pubblico in produzione.

Per abilitare il traffico, impostare token e provider mapbox. Il valore none
mantiene gli ETA stradali. Il costo Mapbox nel monitoraggio è una stima
configurabile, da adeguare al piano effettivo; non è una tariffa certificata.

## Quando vengono chiamati i provider

- Ottimizzazione e anteprima manuale: cache PostgreSQL e OSRM Table. Zero
  richieste Google Matrix o Mapbox. Cache completa: zero richieste di routing.
- Cache incompleta: Table richiede le coppie mancanti; matrici grandi vengono
  suddivise in blocchi limitati dal numero di coordinate configurato.
- Programmazione: geometria/annotazioni OSRM del percorso ordinato, stima
  pedaggi e Mapbox driving-traffic. GiroFacile ricalcola gli ETA dai legs,
  sommando scarico e attese, senza cambiare ordine.
- Driving-traffic accetta 10 coordinate: deposito, 8 consegne e rientro
  rientrano in una richiesta. Percorsi più lunghi vengono suddivisi in
  segmenti consecutivi con un solo punto condiviso tra segmenti; ogni leg
  compare una volta. Le partenze dei segmenti includono scarico e attese.
- GET dettaglio, mappa e portali: leggono solo dati salvati. Nessuna richiesta
  di routing/traffico. La dashboard usa Leaflet/OpenStreetMap per la mappa;
  i link Google Maps/Waze per la navigazione restano disponibili.
- POST /api/routes/{id}/refresh-traffic: aggiornamento esplicito degli ETA di
  una bozza o di un giro programmato, prima dell'avvio. I giri in corso
  mantengono il precedente aggiornamento locale basato sull'avanzamento e sui
  tempi di scarico effettivi.
- Nuovo calcolo/manuale: aggiorna la revisione e invalida traffico/geometria/
  pedaggio precedenti. Su un giro già programmato il traffico diventa
  `stale` finché l'utente riprogramma o aggiorna gli ETA.

Finestre che diventano incompatibili con le durate traffico sono segnalate
con la diagnostica esistente; Mapbox non riordina le fermate. Il controllo di
sovrapposizione delle risorse resta attivo alla programmazione e usa la durata
aggiornata. Se la durata genera un conflitto, il calcolo viene salvato prima
di segnalare il conflitto, evitando un'altra richiesta al successivo tentativo.

## Persistenza e guasti

Le coppie sono direzionali e isolate per azienda. Le chiavi includono
coordinate e versione OSRM, senza data/ora. Le modifiche a cliente/deposito
invalidano entrambe le direzioni; le chiavi per coordinate proteggono anche
da modifiche/importazioni che non passano dagli endpoint ordinari.
L'upsert gestisce anche calcoli concorrenti. Le query della cache sono
suddivise in batch per non superare i limiti di parametri SQL.

Quando OSRM non risponde, solo le coppie mancanti usano la precedente stima
geometrica (distanza × 1,25; velocità 45 km/h), marcata come approssimativa.
Queste stime non entrano nella cache stradale e possono essere sostituite da
OSRM al calcolo successivo. Mapbox assente/non disponibile lascia il giro
programmabile con ETA base; anche l'esito negativo viene salvato, per evitare
tentativi impliciti aprendo la pagina. Un aggiornamento esplicito riprova.

Ogni giro salva snapshot del percorso, provider/stato/revisione del traffico,
istante del calcolo, partenza utilizzata, legs completi, ETA per fermata,
geometria e stato/importo della stima pedaggi. Gli ETA includono data e fuso
nei dettagli delle fermate, oltre ai campi orari legacy.

## Pedaggi stimati e dataset sostituibile

`app/services/toll_provider.py` espone un calcolatore sostituibile. La prima
versione usa classi toll dei passi OSRM, se presenti, e un dataset OSM locale
delle coppie di nodi percorse. Non effettua scraping o richieste a Google.
OSRM standard non restituisce tutti i tag OSM: il solo nome di un'autostrada
non viene trattato come prova di pedaggio.

Classi configurabili sul mezzo, disponibili anche da mobile: A, B, 3, 4, 5.
Le tariffe indicative €/km iniziali sono A=0,08, B=0,10, 3=0,14, 4=0,18,
5=0,22; sono ipotesi operative modificabili, non tariffe italiane ufficiali.
`TOLL_RATES_JSON` sostituisce i valori per classe. Dataset/provider futuri
possono fornire prezzi per tratto o tariffe fisse senza cambiare l'optimizer.

Esempio dataset (coppie direzionali; distanza presa dalle annotazioni OSRM):

```json
{
  "version": "example",
  "edges": {
    "10001,10002": {
      "tags": {"toll": "yes"},
      "eur_per_km_by_class": {"A": 0.08, "B": 0.10}
    },
    "10002,10003": {
      "tags": {"toll": "yes"},
      "charge_id": "example-fixed-section",
      "fixed_eur_by_class": {"A": 3.00, "B": 4.50}
    },
    "10003,10004": {
      "tags": {"toll": "no"}
    }
  }
}
```

Una tariffa fissa con lo stesso charge_id su più archi consecutivi viene
applicata una sola volta per attraversamento. La tratta inversa va indicata
separatamente nel dataset. Tag `toll:hgv` sono usati per le classi 3/4/5.
In assenza di dati sufficienti, il pedaggio è non disponibile o parziale:
non viene mostrato zero come importo noto. L'interfaccia usa sempre
“Pedaggio stimato”. Il costo operativo è energia/carburante più pedaggi
noti; se la copertura è incompleta il totale è dichiarato parziale.
La geometria/il pedaggio OSRM rappresentano il percorso base; Mapbox può
scegliere strade diverse tra le stesse fermate. L'importo non è certificato.

## Migrazioni e comportamento precedente

La migrazione automatica in `app/main.py:migrate_database` è idempotente e
aggiunge colonne nullable/default senza riscrivere i giri storici. Aggiunge
classe pedaggio al mezzo e associazione giro al registro API. Cancella solo
la cache disposable con `|departure=`; la cache base vecchia non viene
riusata perché le nuove chiavi hanno coordinate/versione OSRM.

Differenze intenzionali:

- Google Route Matrix e Google Routes per la geometria sono rimossi dal
  routing del giro; Google resta per geocodifica/verifica e navigazione.
- L'ordine viene valutato sui tempi stradali base, quindi può differire da
  quello precedentemente scelto sulla matrice Google con traffico.
- La cache non scade dopo 15 giorni salvo TTL esplicito.
- Il traffico non viene richiesto nell'anteprima né alla riapertura.
- `costo_totale` ora include i pedaggi noti; i calcoli di carburante, elettrico
  e ibrido plug-in e i relativi prezzi/quantità restano invariati.
- ApiUsageLog registra gli HTTP effettivi: geocodifica Google (anche deposito
  e autocomplete), Mapbox e altri servizi esistenti. Nessun finto log Matrix
  da €0,01. OSRM self-hosted non è conteggiato come API pagata per richiesta.
  Il riepilogo aggrega l'intero periodo; il dettaglio recente è limitato.
- Gli storici privi dei nuovi campi mostrano “ETA storico salvato”; non
  vengono ricalcolati aprendo la pagina.

## Verifica

```sh
python -m pytest tests -q
node --test tests/*.cjs
docker build -t girofacile-test .
```

La CI esegue tutta la suite Python/frontend, i controlli PostgreSQL su schema
temporaneo isolato e la costruzione del container. I nuovi test coprono
assenza di Google Matrix, riuso per date/orari diversi, invalidazione,
direzioni/tenant, OSRM Table e fallback, ETA Mapbox con attese/scarico,
segmentazione e partenze dei segmenti, pedaggi a km/fissi/copertura ignota,
riapertura senza richieste, conservazione energetica e migrazioni.

## File modificati

- `README_ROUTING.md`
- `app/main.py`
- `app/models.py`
- `app/optimizer.py`
- `app/routers/admin.py`
- `app/routers/customers.py`
- `app/routers/driver.py`
- `app/routers/operator.py`
- `app/routers/routes.py`
- `app/routers/vehicles_drivers.py`
- `app/schemas/__init__.py`
- `app/services/api_usage.py`
- `app/services/distance_cache.py`
- `app/services/geocoding.py`
- `app/services/platform_settings.py`
- `app/services/road_routing.py`
- `app/services/route_enrichment.py`
- `app/services/toll_provider.py`
- `app/services/traffic_provider.py`
- `static/admin/index.html`
- `static/dashboard/index.html`
- `static/dashboard/js/core.js`
- `static/driver/index.html`
- `static/mobile/index.html`
- `static/mobile/mobile.js`
- `static/operator/index.html`
- `static/routing-summary.css`
- `static/routing-summary.js`
- `tests/run_real_optimizer_benchmark.py`
- `tests/test_optimizer.py`
- `tests/test_optimizer_improvements.py`
- `tests/test_optimizer_preview.cjs`
- `tests/test_routing_architecture.py`
- `tests/test_routing_postgres.py`
- `tests/test_routing_ui.cjs`
- `tests/test_scheduled_ui.cjs`
- `tests/test_stability.py`
