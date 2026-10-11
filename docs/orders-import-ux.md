# Importazione ordini: percorso semplificato e passaggio alla pianificazione

Il percorso principale è ora **Carica file → Controlla dati → Fatto**. Dalla pagina Ordini, Importa file apre direttamente una pagina dedicata. Lo stesso percorso è disponibile dalla scheda File e dalle indicazioni per gli ordini esportati da e-commerce. Non occorrono chiavi API, JSON o configurazione tecnica per importare un file.

Le colonne riconosciute vengono associate e verificate automaticamente. L'anteprima mostra dati comprensibili (numero, destinatario, indirizzo, data, colli); le associazioni e gli avvisi dettagliati sono richiudibili. Un solo comando conferma l'attivazione delle impostazioni file e l'importazione. Gli elenchi esistenti vengono proposti per evitare di creare una nuova fonte a ogni caricamento; si possono scegliere tutti gli elenchi anche quando superano la prima pagina API. La conferma porta direttamente agli ordini della fonte, azzerando i precedenti filtri di ricerca/data/stato.

La pagina API e la nuova grafica fonti arrivate nel frattempo su main sono conservate. Il nuovo modulo `order-import.js` separa il percorso file dalla configurazione tecnica. Non vengono simulate integrazioni native e-commerce o lettura email. Autorizzazioni, verifiche, idempotenza, gestione degli errori e conservazione degli originali continuano a usare i servizi esistenti.

## Prosegui

Gli errori del caricamento delle fermate erano mostrati soltanto nel riquadro degli ordini, lontano dal pulsante. Adesso una risposta negativa compare accanto a Prosegui, con focus sul messaggio; il pulsante mostra l'attività in corso e impedisce invii ripetuti. Correggendo la configurazione si può riprovare senza perdere la selezione. I campi mancanti restano indicati dal controllo esistente invece di essere coperti dall'avviso generico degli ordini.

Quando si entra senza una configurazione già salvata e gli ordini hanno una sola data richiesta, quella data viene proposta per il giro. Le date degli ordini vengono lette lato server solo per l'azienda e la selezione correnti. Le configurazioni salvate non vengono sovrascritte. Restano attivi i controlli su data, indirizzo verificato, risorse e ordini già assegnati.

Il file originale usato dall'utente non era disponibile: il caso verificato è un ordine realmente importato con data richiesta diversa dal giro. Il test accerta errore visibile, selezione conservata e caricamento riuscito dopo la correzione. La verifica indirizzo nei test usa coordinate e firma sintetiche, senza provider esterni.

## Verifica

- 24 test Python passati: pianificazione, acquisizione e permessi, inclusa la restituzione delle date richieste.
- Chrome con API reale e database isolato a 390/768/1024/1440 px: importazione guidata, seconda importazione senza duplicati, conservazione escaping, passaggio dell'ordine importato alle fermate, errore data e recupero, configurazione API recente e pulizia della chiave visibile.
- Node: 110 passati, 3 errori preesistenti sulla versione main corrente: carburante senza veicolo, estrazione del blocco salvataggio profilo, testo della guida API. L'ultimo è stato riprodotto anche sul contenuto del file preso direttamente da HEAD precedente alle modifiche. Nessun test disabilitato o indebolito.
- Nessuna migrazione di database. Nessun accesso ai dati operativi o alle credenziali di produzione.

File modificati: servizio di pianificazione, dashboard HTML/CSS, navigazione/permessi tab, moduli pianificazione e fonti, nuovo modulo importazione file, test browser e pianificazione, questo report. Gli asset modificati hanno una nuova versione cache. Il normale aggiornamento dell'app scarica il commit e carica i nuovi asset.
