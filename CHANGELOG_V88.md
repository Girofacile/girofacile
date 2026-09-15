# GiroFacile V88 — Refactoring strutturale frontend

Nessuna funzione o grafica è stata intenzionalmente modificata.

## Struttura nuova
- `static/dashboard/css/core.css`: stili generali e moduli storici.
- `static/dashboard/css/transfer.css`: stili dedicati al settore Transfer.
- `static/dashboard/css/account.css`: Piani e Fatturazione.
- `static/dashboard/js/core.js`: logica principale Dashboard.
- `static/dashboard/js/transfer.js`: moduli Transfer V84–V86.

`style.css` e `app.js` restano come entrypoint di compatibilità, ma `index.html` carica i moduli direttamente e nello stesso ordine del codice precedente.

Obiettivo: ridurre il rischio di regressioni nelle modifiche successive e permettere patch più piccole e mirate.
