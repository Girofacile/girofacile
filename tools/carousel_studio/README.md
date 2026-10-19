# GiroFacile Carousel Studio

Strumento editoriale locale separato dal gestionale. Richiede Python 3.9 o
successivo; non richiede pacchetti, database o accesso al pannello aziendale.

## Avvio

Su Mac fai doppio clic su **Apri Carousel Studio.command**, in questa cartella.
Si apre una finestra di Terminale che mantiene attivo il server e viene aperto
il browser. Lascia il Terminale aperto mentre lavori; premi Ctrl+C per fermare
il generatore. Un secondo doppio clic riapre il server già attivo.

Il collegamento web funziona soltanto mentre il server è in esecuzione:
`ERR_CONNECTION_REFUSED` indica normalmente che il server è spento. Riapri
il comando e poi ricarica la pagina. Questo avvio è indipendente dalla chat.

Dalla cartella del repository:

```sh
python3 tools/carousel_studio/server.py
```

Apri http://127.0.0.1:8765. Per aggiornare prima il repository da GitHub:

```sh
python3 tools/carousel_studio/server.py --sync
```

`--sync` usa il remote già configurato, richiede le normali credenziali Git e
interrompe l'avvio in presenza di modifiche locali o cronologie divergenti.
Non scarica altri repository e non esegue commit o push. Senza `--sync`, il brand
è aggiornato dai file locali a ogni generazione. Ricaricare la pagina dopo una
modifica ai file del brand. La revisione letta è visibile nello studio.

## Utilizzo

All'apertura tutti i campi sono già compilati: argomento dal titolo della
landing, sei funzioni con descrizioni e CTA con il collegamento presente nel
progetto. Il pubblico è dedotto dalle attività descritte e indicato come tale.
Lo studio propone tutti e tre i funnel, nove slide e formato 1080 × 1350.
Puoi premere subito **Genera i caroselli** senza inserire alcun dato.
Il pulsante **Ripristina brief GiroFacile** recupera i valori iniziali dopo
le modifiche manuali. La modalità predefinita resta locale anche se l'AI è
disponibile, per non attivare chiamate a pagamento senza una scelta esplicita.

1. Inserisci argomento, pubblico e informazioni confermate.
2. Scegli TOFU, MOFU, BOFU o tutti e tre; scegli da 5 a 9 slide.
3. Genera e modifica titoli, testi e caption nell'anteprima.
4. Esporta una PNG o lo ZIP del carosello selezionato, a 1080 × 1350 o 1080 × 1080.
5. Salva il progetto JSON per conservare tutte le varianti e riaprirle in futuro.

Le bozze restano in memoria nel browser finché non salvi il JSON. Ricaricare o
chiudere la pagina perde le modifiche non salvate. Nessuna pubblicazione social.
Il JSON riaperto usa la grafica corrente del repository.

### Modalità locale e AI

**Locale:** impagina i punti senza riscriverli. Un punto per riga, massimo 360
caratteri per punto e `numero slide - 3` punti. Se il testo non entra, viene
segnalato: non si omettono punti silenziosamente. Le aperture, i passaggi e le CTA
sono strutture editoriali predefinite differenziate per funnel.

**AI:** riscrive un brief anche discorsivo usando il brand e le regole del funnel.
Per abilitarla, impostare `OPENAI_API_KEY` nell'ambiente del processo prima
dell'avvio. `OPENAI_MODEL` è opzionale (default `gpt-4o-mini`, come l'integrazione
esistente del progetto; deve supportare Chat Completions e JSON object).
La chiave non viene richiesta al browser, salvata nei progetti o letta dal file
`.env` del gestionale. Brief e profilo editoriale vengono inviati a OpenAI solo
premendo Genera in modalità AI; le chiamate possono essere a pagamento.
La disponibilità mostrata indica la presenza della chiave, non la sua validità.
Errori API e risposte non valide sono mostrati senza sostituire la bozza precedente.
Non esiste fallback AI silenzioso alla modalità locale.

Il pulsante **Scarica prompt AI** prepara il prompt con brief, fonti e regole per
utilizzarlo anche in una conversazione esterna; non invia una richiesta AI.

## Brand e scelte editoriali

- `static/design-system/theme.css`: colori e font ufficiali, con precedenza sui
  vecchi stili incorporati nella landing.
- `static/girofacile-logo.png` (fallback JPEG): logo esistente, proporzioni conservate.
- `static/landing/index.html`: titoli e funzioni dichiarate del prodotto.
- `docs/design-system.md`: riferimento documentale per i token.

Non esiste qui una rilevazione automatica di tutta la strategia di brand: tono
di voce e struttura editoriale sono proposte esplicitamente indicate come tali.
TOFU educa sul problema, MOFU chiarisce metodo e criteri, BOFU aiuta la scelta.
La CTA personalizzata si applica soltanto a BOFU, per non forzare la vendita in
TOFU. Numeri, prezzi, offerte e testimonianze non devono essere inventati.
La validazione strutturale dell'AI non sostituisce la revisione dei fatti.

I font sono caricati da Google Fonts, come nel design system originale.
Se non disponibili viene segnalato il fallback di sistema, usato anche nei PNG.
Anteprima ed export condividono lo stesso renderer Canvas; i testi si adattano
entro un minimo leggibile e l'overflow blocca l'esportazione.

## Confini tecnici

Il server ascolta solo su loopback. File esposti in allowlist, controllo Host e
token di sessione per le richieste POST; niente lettura arbitraria del repository.
Non esporlo su internet: è uno strumento personale, senza autenticazione utenti.
Le immagini ZIP sono elaborate in memoria. I file del gestionale e il database
non vengono modificati dal generatore. Questa cartella non è servita dal sito
di produzione e non introduce endpoint nell'app FastAPI.

Test senza chiamate AI:

```sh
python3 -m unittest discover -s tests -p test_carousel_studio.py
```
