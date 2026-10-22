# GiroFacile V89.6.7 — Fix favicon globale

- Creata una favicon reale in formato `.ico` a partire dal logo GiroFacile.
- L'endpoint `/favicon.ico` ora serve `static/favicon.ico` con MIME `image/x-icon`.
- Disabilitata la cache della favicon lato endpoint per facilitare l'aggiornamento nei browser.
- Aggiunti i riferimenti favicon e Apple Touch Icon a tutte le pagine HTML statiche del progetto.
- Nessuna modifica alle funzioni operative, database o integrazione MyCarPlate.
