# GiroFacile V89.7 — Hardening isolamento aziende

- Bloccato il salvataggio di consegne che referenziano clienti appartenenti a un'altra azienda.
- Centralizzata la validazione tenant di deposito, mezzo, autista e clienti per creazione e ricalcolo giro.
- Aggiunta una seconda validazione immediatamente prima della persistenza del giro (defense in depth).
- Aggiunta bonifica automatica all'avvio per vecchi riferimenti cross-tenant già presenti nel database: le FK non valide vengono scollegate senza cancellare lo storico testuale del giro.
- Aggiunti test automatici specifici per impedire regressioni sull'isolamento multi-tenant.
