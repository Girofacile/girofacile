# GiroFacile

La [verifica del motore del 30 ottobre 2026](docs/routing-quality-2026-10-30.md)
riporta nuovi test indipendenti per giro singolo e flotta, risultati e limiti rilevati.

L'[audit del progetto del 7 ottobre 2026](docs/audit-progetto-2026-10-07.md)
documenta errori corretti, controlli eseguiti e rischi ancora aperti.

Per l'installazione locale vedere [README_LOCALE.md](README_LOCALE.md).
Per gli accessi delegati vedere [Collaboratori aziendali](docs/company-collaborators.md).
Quote e funzioni sono descritte in [Piani GiroFacile](docs/piani-abbonamento.md).
Le istruzioni sul routing sono in [README_ROUTING.md](README_ROUTING.md).

## Avvio e aggiornamenti database

Con le dipendenze installate nell'ambiente virtuale e la configurazione server
disponibile, prima dell'avvio eseguire:

```sh
python -m app.migrations
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In produzione (`APP_ENV=production` o `prod`) il server si rifiuta di partire se
`APP_SECRET` manca, usa un valore di sviluppo o ha meno di 32 caratteri, se
`SUPERADMIN_PASSWORD` (o in sua assenza `APP_PASSWORD`) manca, è comune o ha
meno di 12 caratteri, oppure se `COOKIE_SECURE` è disattivato.

Con Docker Compose l'app (porta 8000) e OSRM (porta 5000) ascoltano solo su
`127.0.0.1`: il traffico pubblico deve passare dal reverse proxy HTTPS. Per
esporre l'app direttamente impostare `APP_BIND_ADDRESS=0.0.0.0` (sconsigliato).
Gli header `X-Forwarded-For` sono considerati solo se la connessione arriva da
un indirizzo interno (loopback o rete privata).

Le dipendenze sono in `requirements.txt`; `requirements.lock` fissa anche
quelle indirette ed è usato dalla build Docker. Dopo ogni aggiornamento
rigenerarlo e verificare con `pip-audit -r requirements.lock`.

Gli script di avvio locale e l'immagine Docker eseguono già le migrazioni.
Per avvii personalizzati, includere il comando prima dell'avvio dei worker.
Non eseguire migrazioni tramite importazione di `app.main`: l'importazione
non modifica il database e il server rifiuta uno schema non aggiornato.

Le correzioni, i criteri dei report e le indicazioni di compatibilità sono in
[Correzioni audit del 4 ottobre 2026](docs/audit-fixes-2026-10-04.md).

La [roadmap di chiusura V1](docs/roadmap-v1.md) definisce priorità, attività,
criteri di collaudo e condizioni per il primo rilascio ai clienti.
