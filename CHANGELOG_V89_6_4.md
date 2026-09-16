# GiroFacile V89.6.4

- Riparazione automatica completa dello schema `vehicles` per database locali provenienti da versioni precedenti.
- Inspector SQLAlchemy reso dinamico dopo gli `ALTER TABLE`, evitando cache dello schema obsoleto.
- Correzione del `500 Internal Server Error` su `GET /api/vehicles` dovuto a colonne mancanti.
- Diagnostica MyCarPlate: in caso di risposta HTTP 4xx/5xx viene mostrato nel terminale il messaggio reale del provider senza esporre la API key.
