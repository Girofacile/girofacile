# Changelog

Le note delle versioni tecniche precedenti (V87–V89.7) sono in [docs/storico](docs/storico/).
Da qui in avanti le modifiche si annotano in questo file, la più recente in alto.

## Verso la V1

- Ordini: tolta dalle fonti la scheda "Email", non ancora disponibile. Shopify,
  WooCommerce, file e API standard restano attivi.
- Configurazione: aggiunto `.env.example` con tutte le impostazioni del server.
- Repository: changelog storici spostati in `docs/storico`.
- Produzione: l'avvio si blocca anche con SQLite, `APP_BASE_URL` non https o
  archivio prove di consegna locale/incompleto; email, avvisi errori e altre
  impostazioni mancanti compaiono come avvisi nel log.
- Produzione: nuovo `/health` (app + database), healthcheck Docker, proxy HTTPS
  Caddy in `deploy/caddy` e guida in `deploy/README.md`.
