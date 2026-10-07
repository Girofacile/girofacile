# Design System GiroFacile

## Architettura e perimetro

GiroFacile usa **FastAPI con HTML statico e JavaScript**, non Flask/Jinja.
Il sistema migliora gli stessi documenti, conservando endpoint, ID, handler,
permessi e flussi. Non introduce un secondo frontend o un framework e non
modifica database, prezzi, quote, Stripe, email o algoritmo di ottimizzazione.

| Asset condiviso | Responsabilità |
| --- | --- |
| `static/design-system/tokens.css` | Palette semantica, font, spaziature, raggi, ombre, controlli e breakpoint |
| `components.css` | Componenti riutilizzabili, varianti, focus, disabled e liste responsive |
| `layout.css` | Sidebar, topbar e shell aziendale/Super Admin |
| `workspace.css` | Collegamento dei moduli gestionali esistenti al sistema |
| `portals.css` | Mobile, autista, operatore, agente, login/setup, tracking, sito e documenti |
| `design-system.js` | Miglioramenti di presentazione e helper DOM sicuri |

I documenti dichiarano `data-gf-surface` sul body. Gli adattatori sono limitati
alla superficie interessata. I fogli precedenti conservano la geometria e i
selettori utilizzati; la presentazione condivisa viene caricata dopo di essi.
Una rimozione legacy richiede verifica degli utilizzi e delle regressioni.

## Analisi iniziale

Il riferimento analizzato è `cd12980fe06c377ee5af69f0eb543c67a4080784`.
`core.css` contiene 4.597 righe di revisioni sovrapposte, 203 colori hex,
52 gradienti e 211 dichiarazioni important. Il tema `management.css` escludeva
Dashboard, Clienti, Azienda e Depositi. Le pagine avevano titoli da 30 a 40 px,
controlli da 33 a 51 px e raggi/ombre propri. Mobile, portali, Super Admin,
tracking, sito e documenti legali adottavano altre palette.

Gli ID e gli eventi delle directory sono usati da JS e test: importarli in un
nuovo frontend avrebbe aumentato il rischio. Si è scelto un contratto comune,
con adattatori centrali per il markup esistente e miglioramento delle tabelle
generate dai moduli attuali.

## Token e regole

Blu principale `#0b63f6`, superfici bianche e neutre, testo `#17243b`.
Verde significa successo/attivo/completato; ambra avviso/programmato;
rosso problema/errore/eliminazione; blu informazione/in corso.
Raggi 6, 10 e 12 px, ombre leggere. Font Arial/Helvetica/sans-serif,
testo base 14 px, titolo gestionale 28 px. Controlli 40 px, target touch 44 px.
La preferenza `prefers-reduced-motion` è rispettata.

Breakpoint comuni: 640, 768, 1024, 1440 px. Le media query ripetono i valori
documentati perché le variabili CSS non possono sostituire le condizioni.
Il passaggio della navigazione gestionale/Super Admin a 820 px rimane una
compatibilità esplicita con i controlli esistenti, senza riscrivere la
navigazione applicativa.

Usare `var(--gf-...)` per nuove decisioni grafiche. Le vecchie variabili sono
alias dei token comuni. La geometria specifica può restare nel modulo di
pagina; l'aspetto di un componente deve cambiare nel foglio condiviso.

## Componenti

| Componente | Contratto |
| --- | --- |
| Button | `.gf-button`, `data-variant="primary\|secondary\|ghost\|danger"` |
| Input/select/textarea | `.gf-input`, `.gf-select`, `.gf-textarea`; label associata |
| Switch/checkbox | `.gf-switch` con checkbox nativa `role="switch"`; stati/focus nativi |
| Badge | `.gf-badge`, `data-status="success\|warning\|danger\|info\|neutral"` |
| Card | `.gf-card`, `data-variant="standard\|stat\|action\|info\|warning"` |
| Stat card | `.gf-stat` |
| Table/lista mobile | `.gf-table`, `data-gf-responsive="cards"`, celle `data-label` |
| Modal | `dialog.gf-dialog`; gli overlay legacy conservano il loro box a schermo intero |
| Dropdown | `details.gf-dropdown` con summary accessibile |
| Pagination/tabs | `.gf-pagination`, `.gf-tabs`; stato e ruoli espliciti |
| Toolbar/filters/search | `.gf-toolbar`, `.gf-search` |
| Empty/loading | `.gf-empty`, `.gf-loading[role="status"]` |
| Alert/toast | `.gf-alert[data-status]`, `.gf-toast[role="status"]` |
| Page header | `.gf-page-header`: titolo, descrizione e azione principale |

`GFDesignSystem` espone `enhance`, `breakpoints`, `announce`,
`createButton`, `createBadge`, `createEmptyState`, `createLoading` e
`pageHeader`. Gli helper restituiscono nodi e inseriscono testi con
`textContent`; non fanno richieste, navigazione, persistenza o operazioni
di business. Il runtime osserva il markup dinamico senza sostituire i renderer
delle funzionalità. Mantiene stato disabled, validazione e handler.

Le tabelle di consultazione compatibili diventano liste etichettate sotto
640 px, conservando dati e azioni. Tabelle di pianificazione interattive,
celle unite e componenti specializzati mantengono lo scorrimento locale.
Mappe, firma e canvas mantengono struttura e dimensioni necessarie.

## Migrazione e informazioni

Dashboard e Clienti sono le prime pagine pilota. Il sistema si applica anche
a Pianificazione/Anteprima, Giri programmati/in corso/completati, Mezzi, Autisti,
Depositi, Agenti, storico, report/POD, impostazioni, account, piani e fatturazione.
Gli stessi asset sono integrati nelle 18 pagine HTML esistenti dei vari portali.

Il KPI Clienti attivi replica esattamente Totale clienti nel renderer corrente:
la card duplicata è nascosta conservando ID e aggiornamento; sono visibili le
tre misure distinte. Le descrizioni utili restano disponibili anche su mobile.
Link, tab legacy e funzionalità operative non vengono rimossi o riattivati.

La precedente politica di pixel identici per quattro pagine era riferita al
restyling precedente: questa richiesta autorizza la loro migrazione. Si
conservano i controlli di comportamento e si verifica la coerenza del nuovo
sistema, senza imporre le vecchie proprietà CSS.

## UI kit solo per sviluppo

Il riferimento è `docs/design-system/ui-kit.html`, **fuori da static**.
Non esiste una route applicativa e Docker non copia docs: gli utenti della
produzione non possono aprirlo. Nascondere un link sarebbe insufficiente.

Dalla radice del checkout:
```text
python -m http.server 8765 --bind 127.0.0.1
```
Aprire localmente `http://127.0.0.1:8765/docs/design-system/ui-kit.html`.
Gli esempi mostrano tutti i componenti, tastiera, dialog e messaggi senza
chiamare API o modificare dati.

## Verifica

```text
python -m pytest tests -q -ra
node --test tests/*.cjs
python tests/check_design_system.py
python tests/check_management_design.py after
python tests/check_electric_responsive.py
node tests/check_tracking_responsive.js
node tests/check_gps_responsive.js
```

I browser usano Chromium/Playwright, server locale e API sintetiche.
Richieste esterne sono bloccate; nessun database di produzione, email,
pagamento o servizio a pagamento viene contattato. La suite backend resta
intatta. Le verifiche coprono 390/768/1024/1440 px e mantengono anche il
controllo elettrico a 320 px.

Si controllano stili calcolati dei veri pulsanti e campi contro lo UI kit,
etichette/azioni mobile, navigazione, tastiera/focus, retry clienti,
geometria e disegno locale della firma, filtri, modali, quote, mappe,
paginazione e CSV dei completati. I test Mezzi aprono il drawer e il riepilogo
quote attuali, invece di selezionare campi nascosti.

Screenshot e report: `test-results/design-system/`,
`test-results/management-design/` e directory esistenti.
La CI conserva gli artefatti anche in caso di fallimento.
I test non certificano da soli ogni dato, browser o dispositivo possibile.

## Manutenzione

I rischi principali sono cascata legacy, markup generato, overlay/drawer,
tabelle larghe, navigazione mobile, mappe e firma. Adottare i componenti comuni
prima di aggiungere regole; conservare ID/eventi e verificare il flusso quando
cambia la geometria. Eliminare progressivamente CSS superato solo dopo avere
verificato gli utilizzi: una cancellazione generale non fa parte del restyling.
