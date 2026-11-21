# GiroFacile · Video marketing (kit per Claude Code)

Questa cartella contiene tutto quello che serve per rifare, modificare o creare nuovi video promozionali di GiroFacile, e le regole imparate lavorandoci. Leggi tutto il file prima di toccare qualcosa.

Le regole di stile del CLAUDE.md principale (solo variabili di theme.css, layout condiviso, niente stili inline) valgono per le pagine dell'app, non per questi video: qui gli stili sono dentro le composizioni HyperFrames.

## Cosa c'è

| Percorso | Cosa contiene |
|---|---|
| `build_video.py` | Genera il video della campagna carburante (HyperFrames): scene, testi, tempi, effetti sonori. È la fonte: si modifica questo, non i file in `video/compositions/`. |
| `video/` | Progetto HyperFrames generato (index.html, compositions/spot.html, assets: font, logo, gsap, sfx, ui, music.wav). |
| `music.html` | Generatore della musica (Web Audio, 122 BPM, house leggera, drop sull'esplosione blu). Nessun sample esterno, nessun problema di diritti. |
| `capture/` | Script per catturare le schermate vere del gestionale (Puppeteer) + dati demo + OSRM finto. `capture/cap/` contiene le catture già fatte (2x) e `boxes.json` con le coordinate degli elementi. |
| `reference/` | Il video finale v4 e lo showreel motion design 15 s 9:16 (canvas puro, `reel.src.html` + `render_motion.py`, render Playwright con motion blur e colonna sonora generata). |

## Comandi

```bash
# prerequisiti: Node >= 22, ffmpeg, Chrome, Python 3 con Pillow e playwright
python3 build_video.py                      # rigenera video/ dalle scene
# musica (durata = durata finale del video, drop = secondo dell'impatto)
python3 -c "import base64;from playwright.sync_api import sync_playwright as P
with P() as p:
  b=p.chromium.launch();pg=b.new_page();pg.goto('file://'+__import__('os').path.abspath('music.html'))
  open('video/assets/music.wav','wb').write(base64.b64decode(pg.evaluate('renderAudio(25.0,1.18)')))"
cd video
npx hyperframes check --safe-zone reels     # controlli (zona sicura Instagram, leggibilità, errori)
npx hyperframes snapshot --at 0.6,3.4,7.4   # fotogrammi da guardare prima del render
npx hyperframes render --output ../out.mp4
cd .. && ffmpeg -i out.mp4 -c:v copy -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k finale.mp4
```

Le skill ufficiali di HyperFrames: `git clone --depth=1 https://github.com/heygen-com/hyperframes` e leggi `skills/hyperframes/SKILL.md` prima di scrivere scene nuove.

## Come è costruito `build_video.py`

- Si scrive in **tempo base**; il video esce accelerato di `SPEED` (oggi 1.12) tramite un timeline esterno che fa scorrere `tl.time`. Anche gli effetti sonori vengono divisi per `SPEED`. Durata finale = `TOTAL / SPEED`.
- Helper: `title()` (parole che salgono; `*parola` = parola in blu con evidenziatore), `window()` (finestra stile browser con la schermata), `pill()` (etichetta con icona `ok` / `no` / `warn`), `T_IN/T_OUT`, `W_IN/W_OUT`, `P_IN/P_OUT`.
- La mappa delle scene "a occhio" / "giro più corto" è **illustrata** (stesse fermate, ordine casuale vs ordine ottimizzato con 2-opt): da questo ambiente non si potevano scaricare mappe stradali. Se hai screenshot veri delle mappe, sostituiscila.
- Struttura attuale (tempo base): gancio 0-1.4 → perché ora (prezzo gasolio, sfondo blu) 1.4-4.9 → problema 4.9-8.7 → soluzione 8.8-11.8 → fasce/ZTL/sponda 11.8-15.4 → un clic giri pronti 15.4-18.9 → costo gasolio prima di partire 18.9-22.4 → outro 22.4-28 (il riquadro "Carburante" diventa l'icona).

## Stile (dalla bozza "bianco" approvata)

- Sfondo bianco, titoli Bricolage Grotesque 700 navy `#0f2250`, parole chiave blu `#1665ff` con evidenziatore `#e4edff`; testi secondari IBM Plex Sans. Logo: icona blu `#0060FD` con anello.
- Titoli brevi che salgono parola per parola con blur; schermate vere del gestionale in finestre con i tre pallini; pillole bianche con ombra e icona.
- Gancio leggibile dal frame 0, poi parole che "sbattono" a ritmo e transizione d'impatto (cerchio blu che esplode dalla "o" di gasolio). L'utente vuole ritmo veloce e transizioni anche nell'outro.
- Verticale 1080×1920. Testi tra y 270 e 1248 (sotto c'è l'interfaccia di Instagram). Font minimo 28 px.

## Regole sui messaggi (dal documento di posizionamento nel Project "software")

- Cliente: grossisti e distributori Ho.Re.Ca. con 2-8 furgoni che fanno i giri a mano (Excel, Google Maps). Prima campagna TOFU sul costo del gasolio.
- Parole da usare: giro, furgone, consegne, fasce di scarico, orari dei clienti, ZTL, sponda, km, gasolio, "provalo sui tuoi giri".
- Mai: percentuali di risparmio inventate, "rispetta la ZTL" (è un avviso: si dice "avviso ZTL"), "gestionale completo", "per tutte le aziende", TMS/last mile/fleet management, "rivoluzionario", "intelligenza artificiale" come argomento.
- Il dato "+32% in un anno" (gasolio 1,668 → 2,204 €/l, Mimit 18/11/2026) viene dal documento: riverificare la fonte prima di usarlo.
- "Per ogni furgone": solo se la suddivisione automatica su più mezzi è pronta e testata.
- I numeri nelle schermate (54,3 km, € 9,02, 3 giri) vengono da dati demo con un calcolo distanze simulato: sono esempi, non risultati di clienti.
- Non raccontare la storia personale del fondatore (origine cash and carry) nella comunicazione.

## Catturare di nuovo le schermate del gestionale

1. Avvia GiroFacile in locale (Postgres + `uvicorn app.main:app`), con `.env` di sviluppo.
2. `GIROFACILE_REPO=/percorso/repo python3 capture/seed.py` crea l'azienda demo "Distribuzioni Emilia" (Bologna, 3 furgoni, 18 clienti).
3. Senza OSRM vero avvia `python3 capture/osrm_mock.py` (porta 5000; distanze in linea d'aria ×1,35). Con OSRM vero e internet le mappe escono con le strade: meglio.
4. In `capture/`: `npm i puppeteer-core leaflet@1.9.4` poi `node capture.mjs` (viewport 1440×1500, scala 2). Prima svuota i giri: `TRUNCATE route_plans, planning_drafts, fleet_plans RESTART IDENTITY CASCADE;`.
5. Rilancia `build_video.py`: ritaglia da solo le schermate da `capture/cap/`.

## Errori già incontrati (da non ripetere)

- `urlparse` spezza i percorsi OSRM sul `;`: usare `urlsplit`.
- Nello showreel 3D il segno della profondità era invertito (cubo visto da sotto): `y2 = -y1*cos(p) - z*sin(p)`.
- Pillole centrate: usare solo `xPercent:-50` di GSAP, non anche `transform:translateX(-50%)` in CSS.
- Tratti SVG nascosti con dash: partire da `opacity:0`, altrimenti resta un puntino.
- Sotto le parole evidenziate serve `isolation:isolate` sullo span, altrimenti l'evidenziatore finisce dietro lo sfondo.
- Il volume finale va portato a -14 LUFS con `loudnorm`, altrimenti su Instagram è troppo basso.
- Prima del render guarda sempre gli snapshot: il controllo automatico non vede tutto (archi fuori posto, numeri di passaggio non reali).
