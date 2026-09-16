# GiroFacile V89.1 Hotfix
- Corretto errore 500 nel PUT /api/company-profile: i booleani false non vengono più convertiti in NULL.
- Fasce orarie ON di default per nuovi account; altre funzioni opzionali OFF.
- Disattivando le fasce orarie, i relativi controlli vengono nascosti da anagrafica cliente e modifica consegna.
- Il motore di ottimizzazione ignora le fasce orarie quando la funzione aziendale è OFF, senza cancellare i dati salvati.
- Riattivando la funzione, le fasce salvate tornano operative.
- Test automatici: 5/5 superati.
