# Changelog

Le note delle versioni tecniche precedenti (V87–V89.7) sono in [docs/storico](docs/storico/).
Da qui in avanti le modifiche si annotano in questo file, la più recente in alto.

## Verso la V1

- Anteprima giro (un mezzo): pagina ridisegnata come il dettaglio dei giri
  programmati. Testata con nome e stato, numeri con icone, tabella delle
  fermate in alto e, sotto, mappa con autista, mezzo, costi, avvisi "Prima
  della partenza" e "Programma giro". Stampa e spiegazione AI in "Altre azioni".
- Corretto: la barra di navigazione del telefono compariva anche su computer,
  per due chiusure in più lasciate nella pagina Fatturazione.
- Fatturazione: pagina ridisegnata. In alto il prossimo addebito con stato,
  carta, email per le fatture e ultimo pagamento (niente più fila di quattro
  riquadri); fatture e pagamenti in un pannello a schede; dati fiscali in
  lettura con "Modifica" e barra di salvataggio, e controllo dei dati per la
  fattura elettronica. Tolto il riquadro "Notifiche di pagamento", che
  indicava come attivi invii email non presenti.
- Piani e abbonamento: pagina ridisegnata. In alto il piano attuale con stato,
  prezzo, scadenza e consumi del mese; sotto tre card da scegliere con limiti e
  funzioni (✓ incluse, ✕ non incluse; firma, foto e prova di consegna in una
  sola voce), confronto completo apribile e barra flottante per il cambio piano.
- Portale autista: senza rete gli esiti (consegnata, mancata, nota) restano
  salvati sul telefono, compaiono subito nel giro e partono da soli quando la
  connessione torna. Un riquadro indica quanti esiti attendono l'invio.
- Ordini: tolta dalle fonti la scheda "Email", non ancora disponibile. Shopify,
  WooCommerce, file e API standard restano attivi.
- Configurazione: aggiunto `.env.example` con tutte le impostazioni del server.
- Repository: changelog storici spostati in `docs/storico`.
- Produzione: l'avvio si blocca anche con SQLite, `APP_BASE_URL` non https o
  archivio prove di consegna locale/incompleto; email, avvisi errori e altre
  impostazioni mancanti compaiono come avvisi nel log.
- Produzione: nuovo `/health` (app + database), healthcheck Docker, proxy HTTPS
  Caddy in `deploy/caddy` e guida in `deploy/README.md`.
