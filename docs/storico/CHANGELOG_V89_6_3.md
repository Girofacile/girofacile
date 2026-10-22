# GiroFacile V89.6.3 — Fix diagnostica targa e lista mezzi

- MyCarPlate: gli errori HTTP ora riportano il messaggio reale restituito dal provider (chiave, quota, targa, parametri, ecc.).
- MyCarPlate: gestione esplicita 401/403, 404, 429 e altri errori HTTP.
- Lista mezzi: calcolo stato alleggerito; non carica più l'intero RoutePlan.
- Lista mezzi: fallback sicuro su "Disponibile" se un database locale precedente non ha ancora una colonna di stato giro necessaria.
- Nessuna modifica all'interfaccia o ai dati già salvati.
