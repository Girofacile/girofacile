# Tracking cliente per consegna

## Utilizzo

Nei dettagli delle consegne in Dashboard, anche nella versione mobile, il
pulsante **Tracking cliente** apre il link, la scadenza e i comandi per copiarlo,
condividerlo, visualizzarlo o revocarlo. La generazione avviene su richiesta per
un giro programmato o in corso; riaprire il pannello mantiene lo stesso link.
Le bozze non sono condivisibili. Non vengono inviati messaggi automaticamente.
La condivisione usa il menu nativo del dispositivo, quando disponibile; altrimenti
il link può essere copiato in un messaggio. Non sono necessari servizi a pagamento.

Il destinatario vede esclusivamente stato, data prevista, ETA disponibile,
ultimo aggiornamento operativo, fermate previste prima della propria e data/ora
dell'esito finale. Nessun nome, indirizzo, identificativo interno, autista,
percorso, nota, documento, firma o fotografia viene restituito dall'API pubblica.
Il mittente può aggiungere il contesto desiderato al messaggio di condivisione.

La pagina aggiorna i dati ogni 30 secondi mentre è visibile. Sospende le richieste
quando passa in background e dopo un esito terminale. In caso di errore temporaneo
non continua a presentare i vecchi dati come aggiornati. Un token non valido,
revocato, scaduto o riferito a una consegna rimossa produce lo stesso messaggio.

## Sicurezza e ciclo di vita

- Ogni `DeliveryTrackingLink` riferisce una sola `Delivery`, con vincolo univoco
  e cancellazione a cascata. Il tenant deriva dalla relazione con `RoutePlan`;
  non vengono duplicati stati, ETA o dati aziendali.
- Il selettore contiene 32 byte casuali. La credenziale combina il selettore e
  una firma HMAC-SHA256 con `APP_SECRET` e dominio `delivery-tracking:v1`.
  La firma non viene memorizzata nel database. Non utilizzare una chiave di
  sviluppo in produzione; ruotare `APP_SECRET` invalida i link già condivisi.
- Il link è una credenziale al portatore: chi lo riceve può leggere questa
  singola consegna, anche inoltrandolo. Non autentica l'identità del destinatario.
- La generazione e la revoca richiedono una sessione aziendale, verificano
  l'ownership tramite il giro e bloccano la riga del giro per serializzare le
  richieste simultanee. L'API pubblica non accetta ID di consegna o di azienda
  e non permette modifiche.
- Il link scade alla mezzanotte locale dopo sette giorni completi successivi
  alla data programmata. La scadenza UTC viene mostrata nel pannello aziendale.
  La revoca è immediata; riaprendo il pannello si può generare un nuovo link
  per una consegna ancora aperta. I link esistenti restano consultabili anche
  dopo completamento o annullamento, fino alla scadenza.
- Il ricalcolo ricrea le `Delivery`: i link precedenti vengono invalidati nella
  stessa transazione. Il pannello aziendale avvisa di condividere quelli nuovi.
  Non si trasferisce un link in base al nome del cliente o alla posizione nel giro.
- La credenziale sta nel frammento `/tracking#...`, non trasmesso nei normali
  access log HTTP. Il browser la invia soltanto nell'header `X-Tracking-Token`.
  Anche proxy/APM personalizzati devono evitare di registrare questo header.
  Pagina e API usano `no-store`, `no-referrer` e `noindex`; la pagina ha una CSP
  restrittiva e nessuna risorsa esterna o analytics.
- Il limite è di 120 richieste/minuto/IP per processo con memoria limitata.
  Come per il login esistente, in installazioni distribuite serve anche un limite
  condiviso al reverse proxy su `/api/public/tracking`.

## ETA e integrazioni successive

`app/services/route_schedule.py` è la fonte comune per la Dashboard e il tracking.
Usa gli orari persistiti (inclusi gli aggiornamenti già effettuati dal flusso
traffico esistente), la partenza reale e gli esiti delle fermate precedenti.
Propaga lo scostamento tra chiusura effettiva e partenza pianificata della fermata.
Mantiene la data quando gli orari superano mezzanotte e non inventa un ETA quando
l'orario pianificato manca. Il tracking sopprime una previsione già trascorsa.
Le finestre di scarico non diventano una promessa di consegna.

La risposta indica il fuso orario aziendale configurato e contiene `eta.at`, `eta.source` (`planned`, `execution` o `gps`) e
`eta.updated_at` (ultimo evento operativo utilizzato, non l'ora del polling).
La sorgente GPS usa una posizione recente e un ETA OSRM condiviso, senza nuove
chiamate di routing a ogni lettura cliente. Quando non è più valido torna alla
proiezione operativa. Contratto, limiti e migrazione sono in [live-gps.md](live-gps.md).
Le fermate sono una previsione relativa all'ordine salvato, non una posizione GPS.

Per email/SMS/WhatsApp, riutilizzare il servizio di generazione dei link da un
adattatore di invio autenticato. Eventuali eventi e retry delle notifiche andranno
gestiti dopo il commit delle operazioni, con deduplicazione. Non è stata aggiunta
un'infrastruttura di messaggistica o una seconda copia dello stato di consegna.

## Rilascio e verifica

Eseguire `python -m app.migrations` prima di avviare la nuova versione: migrazione
`20261004_04`, sola aggiunta della tabella dei link. La procedura mantiene le
migrazioni precedenti, usa il lock PostgreSQL esistente ed è ripetibile.
La nuova tabella parte vuota: nessun link viene creato per le consegne pregresse.
`APP_BASE_URL` deve indicare l'origine HTTPS pubblica dell'applicazione.

Test specifici:

- `tests/test_delivery_tracking.py`: token, isolamento, allowlist, scadenza,
  revoca, esiti reali autista, ETA, mezzanotte, ricalcolo e limitazione richieste.
- `tests/test_tracking_postgres.py`: migrazione e preservazione dei dati,
  generazione concorrente e cascata alla cancellazione della consegna.
- `tests/check_tracking_responsive.js`: browser reale con API simulate, larghezze
  320/390/768/1440, polling, completamento, indisponibilità e pannelli aziendali.
  Richiede Playwright; `TRACKING_BROWSER_CHANNEL=msedge` usa Edge già installato.
  Le schermate sono salvate in `test-results/tracking-browser/` e archiviate in CI.
