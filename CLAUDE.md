# GiroFacile

Il flusso di lavoro Git (commit e push su `main`) è descritto in [AGENTS.md](AGENTS.md).

Riferimenti del sistema di stile:
- variabili: `static/design-system/theme.css` (unico foglio delle variabili, incluso direttamente da ogni pagina);
- layout base condiviso: `static/design-system/shell.js` + sezione "Layout base condiviso" di `static/design-system/layout.css`;
- componenti: `static/design-system/components.css`;
- catalogo: `docs/design-system/catalogo.html`, aperto da `/catalogo` (solo fuori produzione);
- documentazione: `docs/design-system.md`.

## Regole di stile
- Usa solo le variabili di theme.css. Mai colori, font o spaziature scritti a mano.
- Ogni pagina usa il layout base condiviso.
- Usa solo i componenti esistenti. Se ne serve uno nuovo, proponilo e chiedi prima di crearlo; se approvato, aggiungilo anche al catalogo.
- Niente stili inline né CSS specifico di una singola pagina.

## Procedura per ridisegnare una pagina
Quando ti chiedo di ridisegnare una pagina:
1. Crea 3 varianti di layout come file HTML separati nella cartella /anteprime (es. nomepagina-a.html, -b.html, -c.html), con dati di esempio realistici.
2. Le varianti devono usare solo theme.css e i componenti esistenti e differire solo nella disposizione degli elementi, non nello stile.
3. Per ogni variante scrivimi in 1-2 righe l'idea del layout.
4. Non modificare la pagina reale. Fermati e aspetta la mia scelta.
5. Quando scelgo, applica eventuali modifiche che ti chiedo alla variante, poi implementala nella pagina reale collegandola ai dati veri, senza cambiare la logica esistente.
6. Elimina le anteprime di quella pagina e dimmi quali file hai modificato.
