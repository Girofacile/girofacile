# Design System GiroFacile

## Architettura e perimetro

GiroFacile usa **FastAPI con HTML statico e JavaScript**, non Flask/Jinja.
Il sistema migliora gli stessi documenti, conservando endpoint, ID, handler,
permessi e flussi. Non introduce un secondo frontend o un framework e non
modifica database, prezzi, quote, Stripe, email o algoritmo di ottimizzazione.

| Asset condiviso | Responsabilità |
| --- | --- |
| `static/design-system/theme.css` | **Unica fonte** di colori, font, dimensioni del testo, spaziature, bordi, ombre, controlli, misure del layout e breakpoint |
| `components.css` | Componenti riutilizzabili, varianti, focus, disabled e liste responsive |
| `layout.css` | Layout base condiviso (`.gf-shell`), più gli adattatori di sidebar e topbar esistenti |
| `shell.js` | Costruisce sidebar e intestazione del layout base con il menu standard |
| `workspace.css` | Solo adattatori dei moduli condivisi con i portali (riepilogo percorso, uso mezzi elettrici, tracking cliente) |
| `portals.css` | Mobile, autista, operatore, agente, login/setup, tracking, sito e documenti |
| `design-system.js` | Miglioramenti di presentazione e helper DOM sicuri |

I documenti dichiarano `data-gf-surface` sul body. Gli adattatori sono limitati
alla superficie interessata.

### Gestionale (Dashboard e Super Admin) dopo la pulizia di ottobre 2026

La vecchia interfaccia è stata eliminata: niente più `reference-*.css`,
`unified.css`, `sidebar-unified.css`, `tokens.css` né fogli per singola sezione.
Nella Dashboard restano, oltre ai fogli del sistema, solo:

- `dashboard/css/core.css`: stati di visibilità comandati dal JS (`.hidden`,
  funzionalità disattivate, permessi del collaboratore), pulsanti `btn-secondary` /
  `btn-mini` generati dai moduli condivisi, grafici SVG del Report;
- `dashboard-real-map.css`, `in-progress-reference.css`, `live-gps.css`,
  `fleet-review.css`: segnaposto e controlli delle mappe Leaflet;
- `company.css`: anteprima del colore del brand nella pagina Azienda;
- `electric-vehicles.css`: condiviso con il portale mobile.

Mappe, grafici e anteprima del brand sono in attesa dei componenti proposti per il
catalogo; tutti i fogli usano solo variabili di `theme.css`.

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

Riferimento: la Dashboard. Blu principale `--gf-color-primary` (`#1665ff`),
sidebar blu notte `--gf-color-nav` (`#0f2250`), sfondo `#edf0f6`, superfici
bianche, testo `#16213a`. Verde significa successo/attivo/completato; ambra
avviso/programmato; rosso problema/errore/eliminazione; blu informazione/in
corso; grigio bozza. ZTL usa i toni di avviso, la sponda quelli informativi.
Titoli in Bricolage Grotesque, testo in IBM Plex Sans; testo base 14 px,
titolo di pagina 28 px. Raggi 9, 10, 12 e 16 px, ombre leggere. Controlli
40 px, target touch 44 px. La preferenza `prefers-reduced-motion` è rispettata.
I valori sono in `theme.css`: altrove si usano solo le variabili.

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
| Disposizione | `.gf-stack[data-gap]`, `.gf-cluster[data-justify]`, `.gf-grid[data-cols="2\|3\|4\|7\|main-side"]` (7: una colonna per giorno della settimana) |
| Testo | `.gf-title`, `.gf-subtitle`, `.gf-text`, `.gf-muted`, `.gf-kicker` |
| Pulsanti extra | `data-variant="link"`, `data-size="sm"`, `.gf-icon-button`, `.gf-avatar` |
| Pannello | `.gf-panel` con `__header`, `__title`, `__meta`, `__body`, `__footer`; righe `.gf-list-item` |
| Numeri del giorno | `.gf-stat-strip` con celle `__cell`, `__label`, `__value`, `__unit` |
| Campi | `.gf-form-grid`, `.gf-field` (`__label`, `__hint`, `__error`, `[data-invalid]`), `.gf-fieldset`, `.gf-check`, `.gf-form-actions` |
| Mappa + fermate | `.gf-route-panel` (`__map`, `__canvas`, `__detail`, `__footer`), `.gf-route-map__*`, `.gf-crew`, `.gf-progress`, `.gf-stop-list` / `.gf-stop.is-done\|is-miss\|is-next` |
| Avvisi operativi | `.gf-alert[data-kind="ztl\|tail-lift"]` con `__icon`, `__title`, `__text`; badge `.gf-badge[data-kind]` |
| Filtri | `.gf-filters` con campi `.gf-field` e `.gf-chip[aria-pressed]` |
| Layout base esteso | `.gf-sidebar__count`, `.gf-notifications` (+ `__panel`, `.gf-notification[data-unread]`), `.gf-bottom-nav` (`__item`, `[data-primary]`), `.gf-header__back`, `.gf-savebar` |
| Finestre | `.gf-overlay` (`[data-position="side"]` per il pannello laterale) con `.gf-modal` (`__header`, `__title`, `__body`, `__footer`, `[data-size="lg"]`) |
| Dati | `.gf-details` (`[data-layout="rows"]`), `.gf-setting` (`__copy`, `__control`), `.gf-stat-card` (`__icon[data-tone]`, `__label`, `__value`, `__change[data-trend]`), `.gf-bar-chart` |
| Flussi | `.gf-steps` / `.gf-step.is-done\|[aria-current="step"]`, `.gf-chat` + `.gf-message[data-from="me"]`, `.gf-upload` |
| Accesso e avvisi | `.gf-auth` (`__aside`, `__main`, `__card`), `.gf-banner`, `.gf-hidden` |

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

## Layout base condiviso

Ogni nuova pagina usa il layout base: sidebar blu notte con il menu della
Dashboard, intestazione con titolo, sottotitolo, azioni e utente, contenuto
con margini di 32 px. Sotto 1024 px la sidebar si apre dal pulsante menu.

```html
<body data-gf-surface="workspace" data-gf-layout="base"
      data-gf-nav-active="clienti" data-gf-title="Clienti"
      data-gf-subtitle="Anagrafica e indirizzi di consegna">
  <button class="gf-button" data-variant="primary" data-gf-slot="header-actions">Nuovo cliente</button>
  <main data-gf-shell-content>…</main>
  <script src="/static/design-system/shell.js" defer></script>
</body>
```

Il menu standard è `GFShell.NAV` in `shell.js`; uno
`<script type="application/json" id="gf-shell-nav">` lo sostituisce solo
dove serve un menu diverso (per esempio il catalogo). shell.js crea i nodi con
`textContent` e non interpreta testi come HTML.

## Catalogo dei componenti (/catalogo)

Il catalogo sostituisce il vecchio UI kit: `docs/design-system/catalogo.html`,
servito da `/catalogo` **solo fuori produzione** (`APP_ENV` diverso da
`production`/`prod`). Il file sta in docs, che Docker non copia, quindi in
produzione la route risponde 404. Mostra le variabili di `theme.css` lette in
automatico, il layout base e tutti i componenti con dati di esempio, senza
chiamare API o modificare dati. Ogni nuovo componente approvato va aggiunto qui.

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
paginazione e CSV dei completati. I controlli delle tabelle verificano anche che
le etichette delle azioni restino su una riga; la sidebar mantiene icone
senza cornici residue e contrasto del marchio sulla superficie scura. I test Mezzi aprono il drawer e il riepilogo
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
