# GiroFacile · Reel carburante (Remotion)

Versione Remotion del Reel 9:16 della campagna carburante (1080×1920, 30 fps, 25 s).
Ricrea la v4 approvata (`marketing/video/reference/GiroFacile_campagna_carburante_9x16_v4.mp4`):
regole di stile e di messaggio in `marketing/video/CLAUDE.md`, valgono anche qui.

## Versioni

- `GiroFacileCarburante` (v1, 25 s): la v4 rifatta scena per scena (`src/scenes/`).
- `GiroFacileCarburanteV2` (v2 "La giornata di un furgone", 30 s, `src/v2/`): stessa logica, più facile da seguire.
  Lunedì 6:30 giro a occhio → lunedì sera un clic (orari, ZTL, sponda, 3 giri) → martedì 6:30 stesso furgone sul giro più corto
  → costo del gasolio prima di partire → outro. Una cosa alla volta per schermata. Musica: `public/audio/music-v2.wav` (30 s, drop a 2,7 s).
  Render: `COMP=GiroFacileCarburanteV2 OUT=GiroFacile_carburante_giornata_v2.mp4 ./scripts/finalize.sh`.

## Struttura

- `src/Root.tsx`: una composizione per scena (cartella "Scene") + `GiroFacileCarburante` (principale, 750 fotogrammi).
- `src/Main.tsx`: scene in sequenza (con pochi fotogrammi di sovrapposizione), musica ed effetti sonori.
- `src/scenes/`: Gancio, Perché ora, Problema, Soluzione, Scarico/ZTL/sponda, Un clic, Costo gasolio, Outro.
- `src/components/`: Title (parole che salgono), Window (finestra con i tre pallini), Pill (etichette), RouteMap.
- Tutti i tempi sono in secondi reali dall'inizio della scena (la v4 era scritta in tempo base ×1/1.12).
- Animazioni solo con `useCurrentFrame` + `interpolate` (curve Bézier ed `Easing.spring({damping: 200})`, senza rimbalzi).

## Comandi

```bash
npm i
npx remotion studio                              # anteprima
node scripts/stills.mjs 0 95 205 300 380 470 575 700   # fotogrammi di controllo in out/stills
./scripts/finalize.sh                            # render + loudnorm -14 LUFS -> output/GiroFacile_carburante_remotion.mp4
```

Nel container cloud: `REMOTION_BROWSER=/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell`.

## Dati e risorse

- **Prezzo gasolio** (`src/scenes/Stat.tsx`): media nazionale self Mimit, novembre 2025 = 1,683 €/l (open data Mimit, scheda Figisc),
  21/11/2026 = 2,198 €/l (Osservatorio Mimit). +30,6% → "+31% in un anno". Riverificare prima di ogni nuova uscita.
- **Schermate** (`public/ui/`): catturate dal gestionale con `marketing/video/capture/capture.mjs` (data giro 23/11/2026),
  dati demo "Distribuzioni Emilia", distanze stradali vere: `scripts/osrm_replay.py` risponde come OSRM usando la tabella
  reale scaricata da OSRM (`scripts/osrm_table.json`). Prezzo gasolio nel gestionale: media autostradale Mimit 2,254 €/l.
  I numeri (67,7 km, € 14,51, 3 giri) sono esempi da dati demo, non risultati di clienti.
- **Mappa** (`public/map/bologna.jpg`, `src/data/route.json`): tessere OpenStreetMap (le stesse del gestionale) e percorsi
  stradali OSRM per l'ordine "a occhio" (65,6 km) e il giro più corto (39,0 km) sulle stesse 12 fermate. Rigenerare con
  `scripts/build_map.py`. L'attribuzione "© OpenStreetMap" deve restare visibile.
- **Musica**: `node scripts/music.cjs ../video/music.html 25.0 1.18 public/audio/music.wav` (drop sull'esplosione blu a 1,18 s).
- **Effetti**: `public/sfx/` (dal kit HyperFrames), agli stessi momenti della v4.

I video renderizzati (`out/`, `output/`) non vanno nel repository.
