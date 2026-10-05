# GPS autista ed ETA senza API a consumo

## Utilizzo

Il portale autista attiva la Geolocation API solo su un giro in corso. Il portale
operatore `/giro/{token}` dispone ora del pulsante **Avvia giro**: prima dell'avvio
non viene chiesto il GPS. Le conferme di consegna esistenti continuano a funzionare.
Alla riapertura di un giro attivo il browser può riprendere il rilevamento.

Il pannello usa colori, tipografia e card del portale. Spiega la condivisione e il
limite del background; permesso negato, GPS impreciso, errore e assenza di rete
non bloccano le consegne. Dopo un diniego non vengono ripetute richieste di
permesso: l'autista può correggere le impostazioni e premere **Riprova GPS**.

In **Dashboard → Giri in corso**, la card **Posizione del mezzo** mostra mappa,
giro, mezzo, prossima fermata, percentuale e timestamp del rilevamento. Il marker
diventa attenuato quando il dato supera 90 secondi. Un errore di rete indica
esplicitamente che i dati non sono aggiornati. La mappa usa Leaflet e le tile
OpenStreetMap già utilizzate dal prodotto, senza ricrearsi a ogni aggiornamento.

## Limiti del browser

La PWA non garantisce GPS in background: mentre l'autista naviga in Google Maps,
soprattutto su iPhone, gli aggiornamenti possono interrompersi. Il codice
sospende acquisizioni e invii quando la pagina è nascosta; al ritorno verifica
prima che il giro sia ancora attivo. Nessuna posizione viene simulata lungo il
percorso. Non è stata realizzata un'app nativa in questo intervento.

Per continuità in background servirà un adattatore iOS/Android con i permessi e
le capacità native del sistema. Potrà riutilizzare le API sotto descritte, la
tabella corrente e la proiezione ETA; andrà integrata l'autenticazione del client.
Il solo caricamento del portale dentro una WebView non risolve il background.

## Costi e frequenze

- Rilevamento e invio indicativamente ogni 30 secondi, senza `watchPosition`
  continuo. Richiesta normalmente a bassa potenza; un tentativo ad alta precisione
  solo se necessario, al massimo ogni due minuti. I tempi reali dipendono dal
  dispositivo e dalla rete. Non è una garanzia temporale in background.
- Controllo ciclo di vita tramite una risposta minima `{"active":true}`. Anche il
  polling delle consegne dei portali è sospeso quando la pagina è nascosta.
- Il server accetta al massimo un aggiornamento ogni 20 secondi per la posizione
  corrente, rifiuta campioni fuori ordine, più vecchi di 90 secondi, oltre 10
  secondi nel futuro o con precisione peggiore di 150 metri.
- OSRM self-hosted: una richiesta Table con due punti e una sola coppia
  posizione/prossima fermata, al massimo ogni 120 secondi per snapshot attivo.
  Anche i tentativi falliti vengono limitati. Cambiare fermata invalida subito
  l'ETA precedente; il nuovo calcolo attende il limite. Non viene alimentata la
  cache delle distanze con infinite coordinate GPS.
- Nessuna chiamata Google, Mapbox, geocoding o AI nel percorso GPS. Nessun nuovo
  consumo delle quote giri/consegne. I link di navigazione Google Maps restano
  invariati. Restano costi di infrastruttura, mappe e connettività; OSRM non
  fornisce automaticamente traffico live.
- I lettori Dashboard e cliente riutilizzano l'ETA salvato: aggiungere lettori non
  moltiplica le richieste OSRM.

## Dati, API e isolamento

`RoutePosition` ha il giro come chiave primaria e un vincolo univoco sull'autista
quando assegnato: una sola ultima posizione per autista, nessuno storico GPS.
Per un giro senza autista assegnato resta una sola riga per quel giro. Include
precisione, timestamp UTC acquisizione/ricezione e una piccola cache dell'ETA.

- `GET /api/driver/routes/{id}/position`: stato minimo per il client autenticato.
- `POST /api/driver/routes/{id}/position`: upload autenticato e assegnazione
  verificata sia per autista sia per azienda.
- `GET/POST /api/operator/{token}/position`: stesso contratto, autorizzato solo
  dal token del giro esistente; il token cliente non è valido per questo accesso.
- `POST /api/operator/{token}/start`: avvio esplicito, limitato al giorno del giro
  e soggetto alle quote esistenti. Retry di un giro già avviato non lo riconta.
- `GET /api/routes/{id}/position`: lettura aziendale `no-store`, con controllo
  ownership tramite `RoutePlan.user_id`; include stato, posizione e avanzamento.

Payload POST: `latitude`, `longitude`, `accuracy` (metri), `captured_at`
(ISO 8601 con fuso). Il client non può scegliere azienda o autista nel payload.
Le risposte di upload includono `accepted` e `retry_after_seconds`; i campioni
non utili non sostituiscono l'ultima posizione buona. Il contratto non attesta
fisicamente il GPS: come ogni geolocalizzazione browser, dipende dal dispositivo.

I lock su autista/giro e il controllo dopo il lock impediscono che un upload in
ritardo ripristini una posizione dopo la chiusura o un cambio di assegnazione.
Completamento, ultima consegna e annullamento eliminano la riga nella stessa
transazione. Eliminare il giro produce una cascata sul database.

Non ci sono code persistenti sul telefono: alla riconnessione viene acquisito
un campione nuovo dopo la verifica del giro. Coordinate fuori ordine non vengono
rigiocate. Il job già esistente `scripts/cleanup_distance_cache.py` elimina anche
posizioni non ricevute da almeno 24 ore e residui di giri chiusi. Il relativo timer
deve essere abilitato: con esecuzione giornaliera la rimozione di un giro
abbandonato avviene al primo passaggio successivo alla scadenza, non esattamente
alla ventiquattresima ora.

## ETA

`route_schedule.py` rimane la fonte comune. Usa l'ETA GPS solo se posizione,
autista, prossima fermata e timestamp sono ancora validi. La previsione OSRM
scade dopo 150 secondi e non viene presentata come nuova semplicemente perché
arriva un campione GPS. Un ETA già trascorso viene scartato.

Le tappe successive riutilizzano i tempi stradali persistiti e i tempi di scarico,
rispettando le finestre complete di apertura e il passaggio della mezzanotte.
Se le finestre non sono più raggiungibili, le previsioni residue diventano non
disponibili. Senza GPS utile resta la proiezione pianificata/operativa precedente.
Il tracking pubblico continua a restituire solo la propria consegna, con
`eta.source = gps`, `planned` o `execution`: nessuna coordinata, identità autista
o informazione su altre consegne viene esposta.

## Rilascio

Eseguire **`python -m app.migrations` prima di avviare la nuova versione**.
La migrazione `20261005_01` aggiunge soltanto `route_positions`, relativi vincoli
e indici. Non modifica le coordinate dei clienti né ricostruisce giri precedenti;
parte vuota ed è ripetibile. Le precedenti versioni di migrazione sono preservate.

Servono HTTPS, permesso posizione e OSRM configurato nelle impostazioni già
esistenti. Se OSRM è indisponibile, la posizione continua a essere memorizzata e
l'ETA ricade sulla fonte operativa. Nessuna nuova chiave API o dipendenza runtime.
I test browser usano Leaflet come dipendenza esclusivamente di test.

## File principali

- `app/models.py`, `app/migrations.py`: snapshot GPS e migrazione.
- `app/services/live_position.py`: validazione, limiti, OSRM e retention.
- `app/services/route_schedule.py`, `delivery_tracking.py`: proiezione ETA comune.
- `app/services/route_execution.py`: pulizia al completamento.
- `app/routers/driver.py`, `operator.py`, `routes.py`: API e chiusura/annullamento.
- `static/live-gps.js`, `static/live-gps.css` e i due portali: adattatore browser.
- `static/dashboard/js/live-gps.js`, `css/live-gps.css`, `js/core.js`,
  `index.html`: card e mappa in Giri in corso.
- `static/tracking/app.js`: etichetta della previsione da GPS.
- `scripts/cleanup_distance_cache.py`: pulizia di sicurezza.
- `tests/test_live_position.py`, `test_live_position_postgres.py`,
  `check_gps_responsive.js`, `test_audit_postgres.py`, `.github/workflows/tests.yml`:
  regressioni, migrazione, concorrenza e verifiche visuali in CI.

Optimizer, algoritmo di routing e provider a pagamento non sono modificati.

## Verifiche

Test backend su database isolati per lifecycle, isolamento, autorizzazione,
campioni invalidi/vecchi, throttling, costi, finestre, mezzanotte e fallback.
Test PostgreSQL per migrazione ripetibile con dati preservati, upload simultanei,
cascata e completamento concorrente. Test browser reali con API/GPS simulati su
320, 390, 768 e 1440 px: avvio, permessi negati, background, riconnessione,
chiusura e stati della mappa. Screenshot in `test-results/gps-browser/`.
Il test visuale usa tile simulate; non verifica le condizioni GPS reali di un
iPhone né la precisione stradale dell'istanza OSRM di produzione.
