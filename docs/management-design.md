# Stile del gestionale

## Riferimento e perimetro

La Dashboard è il riferimento principale; Clienti, Azienda e Depositi completano
il riferimento per tabelle e moduli. Le quattro pagine non adottano il nuovo
foglio e mantengono markup e stili propri. La sidebar, lo sfondo logistico e la
barra principale restano quelli esistenti.

`static/dashboard/css/management.css` è caricato dopo gli stili esistenti e
centralizza i componenti delle pagine che aderiscono con `.gf-page`. I dialoghi
aderiscono con `.gf-dialog`; supporto, notifiche e menu mobile hanno selettori
espliciti perché vengono creati dinamicamente o appartengono alla shell.
Anche i dialoghi aperti dalle pagine protette vengono uniformati, come richiesto.

| Elemento | Riferimento adottato |
| --- | --- |
| Font | Arial, Helvetica, sans-serif |
| Titolo pagina | 40 px, peso 700, interlinea 1.12; 32 px su mobile |
| Testo principale | `#101b3d`; titoli `#0b1435` |
| Testo secondario | `#657a9f`, sottotitoli `#52688f` |
| Blu principale | `#0b63f6` |
| Sfondo | `#f5f7fb`, illustrazione logistica già presente |
| Card | bianco, bordo `#e8eef8`, raggio 18 px |
| Ombra | `0 8px 25px #244f8710` |
| Gap principale | 16–20 px |
| Campi | bordo sottile, raggio 11 px, altezza minima 44 px |
| Pulsanti | primario blu, secondario bianco; focus visibile blu |
| Stati | accenti pastello, badge compatti |

## Schermate adattate

- Pianificazione: dati iniziali, risorse, rientro, scelta clienti e consegne.
- Anteprima giro, dettagli nello storico, giri programmati, in corso e completati.
- Report: quattro KPI principali, sei secondari, grafico principale e grafici
  secondari, filtri e tabelle.
- Mezzi: modulo con etichette persistenti e pannello separato per la flotta.
- Autisti, Agenti, Storico, Chat autisti e Impostazioni.
- Piani e abbonamento, fatturazione, profilo e configurazione iniziale.
- Modali cliente, importazione, dettagli cliente, autista e consegna; supporto,
  notifiche e menu mobile.

I quattro tab amministrativi legacy presenti nel template aderiscono alla base
comune, ma non vengono riattivati. Le verticalizzazioni dismesse non fanno più
parte della navigazione o dei flussi operativi.
Portali autista/agente/operatore, applicazione mobile separata, sito pubblico e
console Super Admin sono applicazioni distinte dalla shell aziendale interessata.

## Correzioni emerse dai controlli

- Le notifiche mobile erano contenute nella topbar desktop nascosta. Quando il
  menu è aperto viene reso visibile solo il relativo pannello.
- Il click sul pulsante mobile veniva interpretato anche come click esterno:
  i trigger sono ora riconosciuti dal gestore di chiusura. Lo stato aperto viene
  esposto con `aria-expanded`; Escape e click esterno chiudono il menu.
- Il rendering dei giri in corso usava variabili di anteprima non definite
  (`targetId`, `context`). Il riepilogo usa ora il giro corrente; per i giri
  avviati il componente già non prevede il pulsante di aggiornamento traffico.

Non cambiano endpoint, calcoli, permessi, persistenza o validazione dei moduli.

## Verifica ripetibile

Eseguire `node --test tests/*.cjs` dalla radice del repository.

`tests/check_management_design.py` usa Chrome con Playwright e Pillow e un
server HTTP locale. Tutte le API sono simulate e le richieste esterne sono
bloccate: non modifica dati reali e non verifica i fornitori di mappe o pagamenti.
Acquisisce 18 pagine e i dialoghi alle larghezze 390, 768 e 1440 px. Esegue click
su notifiche, navigazione mobile, filtri e viste clienti, dettagli e modifica,
annullamento azienda, modifica/reset deposito, campi energetici dei mezzi,
filtri report e dettagli impostazioni.

Per confrontare con il riferimento precedente a questa modifica:

```powershell
python tests/check_management_design.py before c189975
python tests/check_management_design.py after
```

Gli artefatti sono in `test-results/management-design` (ignorati da Git).
Il confronto delle pagine protette verifica esattamente geometria e proprietà
CSS calcolate rispetto al riferimento. Confronta anche i pixel con e senza il
nuovo foglio nella stessa sessione Chrome, ammettendo al massimo un livello per
canale per la rasterizzazione. Il confronto separato delle immagini originali
è registrato nel report; Chrome può ricampionare il WebP in modo leggermente
diverso fra processi. Non sono applicate maschere alle pagine protette.

Per estendere il tema, usare prima i componenti e i token esistenti del foglio
comune. Aggiungere regole specifiche solo per le necessità di layout della
pagina. Non estendere i selettori a `.tab`, `.panel`, `body` o `:root` senza
limitare esplicitamente il perimetro: coinvolgerebbe le quattro pagine protette.
