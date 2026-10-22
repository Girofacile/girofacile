# GiroFacile V89.6.1 — Registro targa gratuito

- Provider targa predefinito impostato su `free`: nessun token richiesto.
- Aggiunto registro targa interno gratuito: se una targa è già stata salvata nell’azienda, GiroFacile recupera automaticamente i dati già presenti.
- Per targhe nuove senza provider esterno, la targa viene validata e l’utente può completare manualmente la scheda.
- L’integrazione OpenAPI resta disponibile in futuro impostando `VEHICLE_LOOKUP_PROVIDER=openapi` e il relativo token.
- Nessuna chiamata a servizi a pagamento viene effettuata con la configurazione predefinita.
