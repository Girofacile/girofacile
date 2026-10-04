# GiroFacile

Per l'installazione locale vedere [README_LOCALE.md](README_LOCALE.md).
Le istruzioni sul routing sono in [README_ROUTING.md](README_ROUTING.md).

## Avvio e aggiornamenti database

Con le dipendenze installate nell'ambiente virtuale e la configurazione server
disponibile, prima dell'avvio eseguire:

```sh
python -m app.migrations
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Gli script di avvio locale e l'immagine Docker eseguono già le migrazioni.
Per avvii personalizzati, includere il comando prima dell'avvio dei worker.
Non eseguire migrazioni tramite importazione di `app.main`: l'importazione
non modifica il database e il server rifiuta uno schema non aggiornato.

Le correzioni, i criteri dei report e le indicazioni di compatibilità sono in
[Correzioni audit del 4 ottobre 2026](docs/audit-fixes-2026-10-04.md).
