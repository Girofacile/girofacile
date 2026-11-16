# Messa in produzione (server Linux con Docker)

Percorso di riferimento: `/opt/girofacile` (copia del repository GitHub). Ogni comando va eseguito lì.

## 1. Configurazione

1. `cp .env.example .env` e compila i valori. **Obbligatori** in produzione:
   - `APP_ENV=production` (nel modello è `development`: va cambiato);
   - `APP_SECRET` lungo e casuale, `SUPERADMIN_USERNAME` e `SUPERADMIN_PASSWORD` forti;
   - `POSTGRES_PASSWORD` (può contenere caratteri speciali: l'app la codifica da sola);
   - `APP_BASE_URL=https://app.<dominio>`;
   - archivio prove di consegna su bucket S3 privato (`OBJECT_STORAGE_*`): l'archivio locale non è ammesso.
   Con `APP_ENV=production` l'app non parte se uno di questi è mancante o debole, e non crea
   l'account di sviluppo `APP_USER`/`APP_PASSWORD`.
2. Non impostare `DATABASE_URL` nel `.env` del server: dentro Docker l'indirizzo si costruisce
   da `POSTGRES_*` (vedi `docker-compose.yml`).

## 2. Dati stradali (OSRM)

Il servizio `osrm` parte solo con un dataset già preparato in `data/osrm/`
(nome in `OSRM_DATASET_BASENAME`). La preparazione richiede molta più memoria dell'uso:
conviene farla sul PC con `scripts/osrm_prepare_windows.ps1` (o `osrm_prepare_unix.sh`)
e copiare sul server i file `*.osrm*`. Dettagli in [README_ROUTING.md](../README_ROUTING.md).

## 3. Cartelle e avvio

```bash
mkdir -p backups data/ztl data/osrm
sudo chown -R 10001:10001 backups data/ztl   # l'app nel container non è root
docker compose up -d --build
docker compose ps                            # «healthy» quando /health raggiunge il database
```

L'app ascolta solo su `127.0.0.1:8000`. All'avvio esegue tutte le migrazioni e si rifiuta
di partire se ne manca anche una sola.

## 4. HTTPS

Installa Caddy, copia [caddy/Caddyfile](caddy/Caddyfile) in `/etc/caddy/Caddyfile`,
sostituisci i domini e `sudo systemctl reload caddy`.

## 5. Backup e pulizia cache

I servizi in [systemd](systemd/) eseguono gli script **dentro il container** con
`docker compose exec`; se il percorso non è `/opt/girofacile` va cambiato `WorkingDirectory`.

```bash
sudo cp deploy/systemd/girofacile-*.service deploy/systemd/girofacile-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now girofacile-backup.timer girofacile-cache-cleanup.timer
sudo systemctl start girofacile-backup.service && ls -l backups/   # prova subito un backup
```

I dump restano sul disco del server: copiali anche fuori (snapshot del fornitore o archivio
remoto) e prova un **ripristino** su un database vuoto prima di aprire alle aziende.

## 6. Aggiornamenti

```bash
git pull && docker compose up -d --build
```

Per tornare alla versione precedente: `git checkout <commit precedente> && docker compose up -d --build`
(il database resta; le migrazioni già applicate non vengono annullate).

## 7. Controllo esterno

Monitor (es. UptimeRobot) su `https://app.<dominio>/health` ogni minuto. `/health` controlla
solo il database: routing, email e archivio vanno provati a parte dopo ogni installazione.
