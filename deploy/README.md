# Messa in produzione

1. Copia `.env.example` in `.env` e compila i valori. Con `APP_ENV=production`
   l'app non parte se segreti, HTTPS, database o archivio prove di consegna sono
   configurati in modo non sicuro; le funzioni opzionali mancanti compaiono come
   avvisi nel log all'avvio.
2. `docker compose up -d --build`: l'app ascolta solo su `127.0.0.1:8000`.
   `docker compose ps` mostra `healthy` quando `/health` raggiunge il database.
3. Proxy HTTPS: installa Caddy, copia [caddy/Caddyfile](caddy/Caddyfile) in
   `/etc/caddy/Caddyfile`, sostituisci i domini e `sudo systemctl reload caddy`.
4. Backup e pulizia cache: timer in [systemd](systemd/); adatta i percorsi
   all'installazione reale prima di abilitarli.
5. Monitor esterno (es. UptimeRobot): controlla `https://app.<dominio>/health`
   ogni minuto e avvisa se non risponde `{"status":"ok"}`.
