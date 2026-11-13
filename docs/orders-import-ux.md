# Importazione ordini: percorso semplificato e passaggio alla pianificazione

Il percorso principale è ora **Carica file → Controlla dati → Fatto**. Dalla pagina Ordini, Importa file apre direttamente una pagina dedicata. Lo stesso percorso è disponibile dalla scheda File e dalle indicazioni per gli ordini esportati da e-commerce. Non occorrono chiavi API, JSON o configurazione tecnica per importare un file.

Le colonne riconosciute vengono associate e verificate automaticamente. L'anteprima mostra dati comprensibili (numero, destinatario, indirizzo, data, colli); le associazioni e gli avvisi dettagliati sono richiudibili. Un solo comando conferma l'attivazione delle impostazioni file e l'importazione. Gli elenchi esistenti vengono proposti per evitare di creare una nuova fonte a ogni caricamento; si possono scegliere tutti gli elenchi anche quando superano la prima pagina API. La conferma porta direttamente agli ordini della fonte, azzerando i precedenti filtri di ricerca/data/stato.

Il modulo `order-import.js` separa il percorso file dalla configurazione tecnica. Autorizzazioni, verifiche, idempotenza, gestione degli errori e conservazione degli originali continuano a usare i servizi esistenti.

## Collegamento gestionale tramite assistenza — 13 novembre 2026

In **Collega i tuoi ordini**, l'importazione CSV/Excel occupa il riquadro principale e il comando della barra superiore apre direttamente il caricamento file. Gestionale ed e-commerce sono presentati come alternative secondarie.

**Gestionale aziendale → Collega** apre un modulo di assistenza, con nome del gestionale e descrizione obbligatori, versione e telefono facoltativi. Il modulo non chiede chiavi o password. Il server ricava azienda ed email dal profilo autenticato; la richiesta viene salvata come ticket `collegamento_gestionale`, visibile all'azienda e nell'assistenza amministrativa. L'utente riceve il numero del ticket e può consultare lo storico. La richiesta non attiva automaticamente un'integrazione e non promette compatibilità o tempi di collegamento.

La richiesta di assistenza è disponibile anche prima di passare a un piano con integrazioni, nel rispetto del permesso `support.write`. Per l'uso delle API restano necessari Business o Pro e i permessi di integrazione. La creazione di una nuova fonte API richiede un precedente ticket gestionale della stessa azienda; il riferimento al ticket viene scelto dal server. Il requisito riguarda la richiesta di supporto e non introduce un'approvazione amministrativa separata.

Le fonti API esistenti conservano configurazione e gestione delle credenziali. I collegamenti Shopify e WooCommerce mantengono il proprio percorso; per i requisiti e i limiti effettivi vedere [collegamenti automatici](order-connectors.md). I dettagli del contratto tecnico e del modulo sono in [Invio ordini a GiroFacile](order-ingestion-api.md). Nel pannello amministratore il filtro **Collegamento gestionale** permette di trovare i ticket dedicati; il testo inserito dall'azienda viene visualizzato come testo anche quando contiene simboli HTML.

## Prosegui

Gli errori del caricamento delle fermate erano mostrati soltanto nel riquadro degli ordini, lontano dal pulsante. Adesso una risposta negativa compare accanto a Prosegui, con focus sul messaggio; il pulsante mostra l'attività in corso e impedisce invii ripetuti. Correggendo la configurazione si può riprovare senza perdere la selezione. I campi mancanti restano indicati dal controllo esistente invece di essere coperti dall'avviso generico degli ordini.

Quando si entra senza una configurazione già salvata e gli ordini hanno una sola data richiesta, quella data viene proposta per il giro. Le date degli ordini vengono lette lato server solo per l'azienda e la selezione correnti. Le configurazioni salvate non vengono sovrascritte. Restano attivi i controlli su data, indirizzo verificato, risorse e ordini già assegnati.

Il file originale usato dall'utente non era disponibile: il caso verificato è un ordine realmente importato con data richiesta diversa dal giro. Il test accerta errore visibile, selezione conservata e caricamento riuscito dopo la correzione. La verifica indirizzo nei test usa coordinate e firma sintetiche, senza provider esterni.

## Verifica del precedente percorso semplificato

- 24 test Python passati: pianificazione, acquisizione e permessi, inclusa la restituzione delle date richieste.
- Chrome con API reale e database isolato a 390/768/1024/1440 px: importazione guidata, seconda importazione senza duplicati, conservazione escaping, passaggio dell'ordine importato alle fermate, errore data e recupero, configurazione API recente e pulizia della chiave visibile.
- Node: 110 passati, 3 errori preesistenti sulla versione main corrente: carburante senza veicolo, estrazione del blocco salvataggio profilo, testo della guida API. L'ultimo è stato riprodotto anche sul contenuto del file preso direttamente da HEAD precedente alle modifiche. Nessun test disabilitato o indebolito.
- Nessuna migrazione di database. Nessun accesso ai dati operativi o alle credenziali di produzione.

File modificati: servizio di pianificazione, dashboard HTML/CSS, navigazione/permessi tab, moduli pianificazione e fonti, nuovo modulo importazione file, test browser e pianificazione, questo report. Gli asset modificati hanno una nuova versione cache. Il normale aggiornamento dell'app scarica il commit e carica i nuovi asset.
