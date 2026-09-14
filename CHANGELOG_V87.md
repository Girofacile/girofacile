# GiroFacile v87 — Sicurezza e stabilità

- Corretto il Dockerfile: eliminati SQLite e segreti hardcodati.
- Docker Compose ora usa `.env`, healthcheck PostgreSQL e dipendenza dall'avvio sano del database.
- Aggiunto rate limiting centralizzato ai login aziendale, Super Admin, autista e agente.
- Cookie di autenticazione uniformati con `HttpOnly`, `Secure` configurabile, `SameSite` e path esplicito.
- `/docs`, `/redoc` e `/openapi.json` vengono disabilitati automaticamente in produzione.
- Aggiunta una prima suite di smoke test di sicurezza/configurazione.
- Il file `.env` resta incluso su richiesta del proprietario del progetto.
