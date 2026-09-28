# Avviatore desktop Windows

Copia `Avvia GiroFacile.cmd` in Documenti o sul Desktop e fai doppio clic.
Il progetto deve trovarsi in `%USERPROFILE%\Documents\girofacile`.

L'avviatore apre un terminale, aggiorna `main` da `origin/main` solo tramite
fast-forward, installa le dipendenze, avvia il server e apre Chrome (oppure
il browser predefinito) su http://127.0.0.1:8000/login quando risponde.
Lascia aperto il terminale durante l'utilizzo. Premi Ctrl+C per fermare il server.
Chiudi il precedente server prima di rilanciare l'avviatore.

Le modifiche locali tracciate bloccano l'aggiornamento. I file non tracciati
non vengono eliminati; Git blocca il merge se rischia di sovrascriverli.
Errori Git, dipendenze, database o avvio rimangono visibili nel terminale.

Si usa l'ambiente `.venv` esistente; se assente serve Python 3.11.
Serve il database PostgreSQL locale descritto in `README_AVVIO_V87.md`.
Il file `.env` non viene modificato. Gli incassi sono disabilitati per questo avvio.

Controllo di Python e database senza aggiornamento o avvio:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\avvia_aggiornato_windows.ps1 -CheckOnly
```
