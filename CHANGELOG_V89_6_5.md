# GiroFacile V89.6.5

Fix mirato alla lista Mezzi (`GET /api/vehicles`) senza modificare il lookup targa MyCarPlate.

- Isolata la query di stato mezzo dalla sessione ORM principale, così un eventuale schema legacy di `route_plans` non manda la sessione in stato aborted.
- Resa più robusta la serializzazione dei mezzi, inclusi valori null e date legacy.
- Aggiunto fallback di lettura diretta della tabella `vehicles` usando solo le colonne realmente presenti nel database.
- Aggiunto log locale `[VEHICLES]` per mostrare nel terminale l'errore reale se la query ORM dovesse ancora fallire.
- Nessuna modifica all'integrazione MyCarPlate, che resta invariata.
