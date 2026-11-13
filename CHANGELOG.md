# Changelog

Le note delle versioni tecniche precedenti (V87–V89.7) sono in [docs/storico](docs/storico/).
Da qui in avanti le modifiche si annotano in questo file, la più recente in alto.

## Verso la V1

- Clienti: un’unica scheda per vedere e modificare. «Dettagli» (o un clic sulla riga) apre la finestra
  con tutti i dati già nei campi, senza schede: Cliente e Indirizzo a sinistra, Consegna e Note a destra;
  si cambia quello che serve e si preme Salva. Tolti la matita, la vista di sola lettura e i messaggi
  «verificato con Google»: l’indirizzo si verifica da solo e compare un avviso solo se c’è da correggere.
- Clienti semplificati: «Dettagli» mostra tutte le informazioni del cliente in sola lettura (la fascia
  oraria è una riga con gli orari, oppure «Fascia oraria non presente»). La matita della riga e il pulsante
  «Modifica» nei dettagli aprono sempre la stessa finestra completa, dove si cambia tutto: indirizzo,
  contatti, fasce, tempo di scarico, accesso e note. Tolta la modifica rapida a metà.
- Clienti: la scheda del cliente non è più un pannello laterale ma una finestra al centro, nello
  stile di «Nuovo cliente» (variante B). A sinistra riquadri con righe etichetta → valore
  (indirizzo, contatti, consegna), a destra la fascia di scarico con lo stato attuale in evidenza.
- Importazione ordini da file: accettate anche le date tipiche dei gestionali AS400 (20261113,
  13/11/26, 13-11-2026, 13.11.2026) e riconosciute da sole colonne come NUMORD, RAGSOC, DTCONS,
  NRCOLLI e LOCALI. Le date a 6 cifre senza separatori restano un errore perché ambigue.
- Fonte API (variante B): la pagina è un elenco di righe come le Impostazioni (dati da importare,
  chiave API, verifica, istruzioni) con lo stato della ricezione a destra. I dati si scelgono in una
  finestra con gli interruttori; la nuova chiave compare in una finestra con «Copia chiave» e l’avviso
  che non sarà più visibile. Spariti il grande riquadro dei dati facoltativi e i riquadri verdi.
- Guida al primo giro: durante un caricamento (per esempio «Sto calcolando il giro») il riquadro
  e la barra della guida si nascondono, e ricompaiono al passo successivo quando il caricamento finisce.
- Pianificazione giro: un orario di partenza già passato o uguale a quello attuale (nella data
  di oggi) viene segnalato subito sotto il campo, appena l’orario è completo. Finché non è
  corretto, «Calcola percorso» non compare.
- Pianificazione giro: i clienti selezionati compaiono subito nell’elenco delle fermate. La barra
  in basso con «Elimina» e «Calcola percorso» compare solo con i dati del giro completi: data,
  orario, deposito, almeno un mezzo con autista e carburante. Nella guida al primo giro il passo
  «Calcolo del giro» indica prima data e orario, poi mezzo e autista, infine «Calcola percorso».
- Clienti: selezionando un cliente la tabella non scende più lasciando uno spazio vuoto sotto i
  filtri. La barra «clienti selezionati» è in fondo alla pagina e riserva il suo spazio sotto la tabella.
- Guida al primo giro, passo 6 «Seleziona il cliente»: il riquadro verde compare sotto la riga
  del cliente, con la freccia sulla casella, invece di coprire nome e indirizzo.
- Indirizzi verificati in automatico: nel nuovo cliente e nella consegna occasionale non c’è più
  il pulsante «Verifica indirizzo con Google». La verifica parte premendo «Salva». Se Google non
  trova l’indirizzo il pannello resta aperto con il motivo (indirizzo inesistente o solo simile);
  per il cliente, un secondo «Salva» lo registra comunque come da verificare.
- Registrazione: nome azienda, nome utente, email, password e sede operativa completa
  (via, città, CAP, paese) sono obbligatori e segnati con l’asterisco, anche nel controllo
  del server. Tolta la sezione «Funzioni utili» dall’ultimo passaggio: valgono le impostazioni
  predefinite, modificabili poi dalle Impostazioni.
- Pagina iniziale: scrivendo l’email e premendo «Prova gratis per 14 giorni» si apre subito
  il modulo di registrazione con l’email già inserita (prima si apriva l’accesso).
- Pagina di accesso: la parte blu occupa circa il 55% della pagina, il riquadro di accesso è
  più grande (campi e testi più grandi, più spazio tra le righe) e il testo di presentazione è ingrandito.
- Giri programmati: l’avviso dei giri dei giorni scorsi mai avviati non sta più in cima alla
  pagina. È una riga grigia in fondo, sotto la tabella del giorno, con il comando per annullarli.
- Pagina di accesso: la griglia dello sfondo blu ora si anima con onde di luce lente e continue che
  partono da dietro al riquadro e accendono le linee al loro passaggio. Il resto della
  pagina è invariato; chi ha attivato la riduzione del movimento vede la griglia ferma.
- Widget iPhone ridisegnato con fondo chiaro, blu GiroFacile e riquadri arrotondati:
  ticket e aziende in evidenza, due righe per gli altri indicatori e fascia MRR.
  Il formato grande conserva tutti i dieci dati e distribuisce gli spazi sull’intera
  altezza; medio e piccolo mantengono rispettivamente sei e due indicatori.
  [Istruzioni di aggiornamento](docs/widget-iphone.md).
- Pagina di accesso: la composizione occupa tutta la larghezza dello schermo; il titolo con i punti di forza è
  al centro della parte bianca e il riquadro di accesso al centro della parte blu (prima stavano in un blocco
  centrale largo 1200 px, con il testo attaccato alla parte blu).
- Nuova pagina di accesso (variante C, sfondo «Rete», scelta il 12 novembre): logo in alto a sinistra; a sinistra
  sul bianco il titolo e i tre punti di forza; a destra, su un'area blu notte con bordo curvo, griglia sottile e un
  percorso di consegna a puntini con le fermate luminose, il riquadro «Accedi a GiroFacile». Le garanzie
  (connessione cifrata, dati nell'UE, assistenza in italiano) sono nella riga in fondo. Recupero password,
  nuova password e registrazione restano uguali; con la registrazione aperta resta solo il modulo.
  Nuovo componente `.gf-auth[data-backdrop]` nel sistema di stile e nel catalogo.
- Manutenzione e avvisi (Super Admin › Server): un solo riquadro «Manutenzione e avvisi» al posto dei due
  interruttori doppi.
  - Manutenzione immediata oppure programmata (inizio, fine prevista, da quando mostrare l'avviso, nota):
    all'ora di inizio si attiva da sola, all'ora di fine si spegne; «Termina manutenzione» la chiude prima.
  - Avviso agli utenti: un messaggio libero, attivabile e disattivabile.
  - Landing, accesso, gestionale e portali (autisti, agenti, collaboratori, operatore, mobile) mostrano
    l'avviso in basso con icona e ✕; quello della manutenzione ricompare nell'ultima mezz'ora prima dell'inizio.
  - Durante la manutenzione, al posto degli errori, una pagina «Siamo in manutenzione» con l'ora di ritorno,
    che si ricarica da sola a lavori finiti. Il Super Admin continua a lavorare.
  - Il riquadro avvisa se ci sono giri in corso (gli autisti non potrebbero registrare le consegne).
- Meno chiamate a Google per verificare gli indirizzi:
  - un ordine diretto a un cliente già in anagrafica e verificato (stesso indirizzo) prende le sue coordinate
    senza chiamare Google, anche nella verifica di più ordini insieme;
  - un cliente eliminato occupa il suo posto nel piano fino a fine mese (prima si liberava subito: eliminando
    e reimportando si poteva far ripetere la verifica all'infinito). Il messaggio di limite lo spiega.
- Torna il limite di giri al mese: Starter 80, Business 250, Pro 1.200 (il 23 ottobre era stato sostituito
  dalla quota ordini, ma pianificando dall'anagrafica clienti si potevano creare giri senza limite).
  Un giro conta quando viene programmato, prima del calcolo col traffico (che ha un costo); riprogrammarlo
  non conta di nuovo, annullarlo non restituisce il giro. Visibile nelle card dei piani, nel confronto,
  nei consumi («Giri del mese»), nella landing, nella versione mobile e nel Super Admin.
- Prezzi senza IVA da aggiungere (regime fiscale del titolare): tolti «+ IVA» e «IVA esclusa» da piani,
  landing, versione mobile e Super Admin; la colonna delle fatture si chiama «Importo». Il pagamento su Stripe
  era già dell'importo esatto del piano.
- Avvisi azzurri e gialli senza riquadro, in tutte le pagine: diventano una riga di testo (grigia per le
  informazioni, con un pallino ambra per l'attenzione). Restano riquadri solo i messaggi di riuscita (verdi) e
  di errore (rossi). In Piani e abbonamento il piano programmato si legge nella riga sotto il nome del piano
  («… · poi passa a Business») e la nota «Ambiente di prova» è in fondo, sotto i pulsanti.
- Piani e abbonamento:
  - un piano scaduto, disdetto o da pagare ora si può rinnovare anche con lo stesso piano
    (pulsante «Rinnova in modalità di prova»); se su Stripe c'è un pagamento in sospeso si apre la sua pagina;
  - se un checkout è stato pagato senza tornare in GiroFacile (webhook non ricevuto), al primo cambio o
    acquisto il piano si riallinea con Stripe e lo dice («Il piano Pro è già attivo: stato aggiornato»)
    invece di rispondere solo «Piano già attivo».
- Report rifatto (variante B scelta il 10 novembre):
  - quattro card colorate: consegne riuscite con anello, fermate, km ed energia con il mini andamento;
  - chilometri ed energia al giorno in due grafici ad area separati (prima un grafico con due scale);
  - torta delle fermate per mezzo, ciambella della spesa per alimentazione, «Rendimento per autista»
    a colonne con un colore per autista e i pulsanti Fermate · Km · Ore · Costo;
  - in alto una sola riga come nell'anteprima: periodo a pillola (Tutto, Ultimi 7 giorni, Questo mese,
    Mese scorso, Quest'anno, Personalizzato con le date Dal/Al in un riquadro) e pulsanti Report AI, CSV,
    Stampa; tolto il riquadro «Mostra filtri» (cliente, autista, mezzo, agente); la nota sui calcoli è in fondo;
  - tabelle con barre nelle celle e nuova tabella Flotta; dati, filtri, CSV, stampa e report AI invariati.
  - Nuovo componente grafico nel sistema di stile (otto colori dei grafici, `charts.js`) e nel catalogo.
- Collaudo totale (10 novembre, ambiente isolato con due aziende, autisti, collaboratori, agente, Super Admin):
  - Import clienti: civico, telefono e provincia restano come scritti (prima «12.0», «811111111.0», «NA»
    perso); file con «;» accettati; in caso di errore si vede la riga da correggere, non «Errore import».
  - Più mezzi: durante «Pianifica giri» non si può uscire dalla pagina; il server rifiuta bozze di piani
    già programmati (prima si potevano programmare due volte gli stessi clienti).
  - Anteprima e revisione su più mezzi: avviso se un cliente ha già una consegna programmata quel giorno.
  - Chat autisti: orari nell'ora italiana (prima un'ora indietro).
  - Registrazione: errori sotto i campi invece degli avvisi del browser; partita IVA, codice fiscale, PEC
    e SDI controllati (anche in Azienda e Fatturazione); email inviate dopo la risposta (accesso immediato).
  - Ordini: numero già usato da un ordine attivo rifiutato; import con «Importa solo le righe valide»;
    data impossibile spiegata («Data consegna «31/02/2026» non valida»); anteprima con l'indirizzo composto.
  - Pianificazione da ordini: gli ordini dello stesso destinatario e indirizzo diventano una sola fermata.
  - Fatturazione: si carica anche ricaricando la pagina; Indietro/Avanti non aprono pagine vuote.
  - Assistenza: nella finestra compaiono le richieste inviate con il loro stato.
  - Errori di salvataggio già mostrati non risultano più «non gestiti»; «Elimina cliente» in Dati principali;
    pagina di primo accesso autista senza stili in linea.
- Collaudo completo del 10 novembre, correzioni:
  - «Sposta la partenza ad adesso» non falliva più solo quando il minuto era un multiplo di 5: la nuova
    partenza è sempre i prossimi 5 minuti tondi dopo adesso (alle 09:35 → 09:40); vicino a mezzanotte
    chiede di riprogrammare. Risposta senza tracciati del traffico (da ~150 KB a pochi KB).
  - Giri programmati: avviso per i giri dei giorni scorsi mai avviati, con «Annulla i N giri» (gli ordini
    tornano da pianificare).
  - Clienti: «Nuovo cliente» apre la finestra a schede con i campi obbligatori concordati.
  - Ordini: dopo una verifica non riuscita si vede subito il motivo (es. «Google ha trovato solo la zona»)
    invece di «Operazione non riuscita»; selezionando il primo ordine l'elenco non scende più (la barra di
    selezione è in fondo alla pagina); il banner dei cookie sale sopra le barre in basso invece di coprirle.
  - Nuovo mezzo / nuovo autista: il limite del piano si vede prima di compilare la finestra.
  - Collaboratori: il titolare può eliminarli (sessioni e inviti revocati subito).
  - Storico: un orario che cade in un altro giorno mostra la data («00:18 del 10/11»).
  - POD scaricata con un nome leggibile: «POD-2026-11-10-Bar-Roma-1085.pdf».
  - Test: non scrivono più falsi errori SMTP in «Errori sistema» del database locale.
- Widget iPhone del Super Admin (Server › Widget iPhone): ticket aperti e di oggi, aziende (registrate,
  in prova, abbonate, nuove nel mese), MRR stimato, giri in corso e di oggi, errori delle ultime 24 ore,
  in un widget dell'app Scriptable. «Genera chiave e copia script» crea una chiave dedicata (nel database
  solo la sua impronta), la inserisce nello script da incollare sull'iPhone; «Revoca chiave» la disattiva.
  Servizio GET /api/widget/stats in sola lettura, 60 letture al minuto per indirizzo.
- Punti aperti dalla prova del flusso: programmando un giro, se il ricalcolo con il traffico sposta il
  rientro di 10 minuti o più il messaggio lo dice («il rientro passa dalle 09:04 alle 08:04»); nei Giri in
  corso un giro partito in un giorno precedente mostra «Aperto dal …» e c'è «Chiudi giro» per chiuderlo e
  liberare autista e mezzo; l'anteprima avvisa se ci sono consegne previste tra le 22:00 e le 6:00; nelle
  tendine mezzo/autista niente emoji, «In servizio/In uso» solo se il giro è partito, altrimenti «Già
  assegnato/Già prenotato fino alle …»; annullamento, partenza e dettaglio del giro non inviano più i
  tracciati del traffico (risposta da ~500 KB a pochi KB); tempo di scarico anche da 5 minuti.
- App autista: un giro annullato dall'ufficio mentre l'autista lo ha aperto mostra «Giro annullato
  dall'ufficio» e nasconde Naviga/Consegnato/Mancata; con un giro in corso gli altri giri di oggi dicono
  «Si avvia dopo aver chiuso il giro in corso» invece di offrire un «Avvia giro» che dava errore.
- Prova del flusso autista (10 novembre): Invio nel login fa partire l'accesso; la nota scritta con
  «Nota» non si perde più confermando consegna o mancata (anche nel portale via link) e si vede nella
  scheda; l'avviso «Seleziona il tempo di scarico/il motivo» sparisce alla scelta; arrivo aggiornato e
  anticipo/ritardo solo per i giri di oggi; l'elenco non segna più avviabili i giri di altri giorni;
  «‹ Giri» su una riga.
- Finestre di creazione a schede (versione B): mezzo, autista, cliente, agente e collaboratore sono
  finestre centrali della stessa larghezza, con i dati divisi in schede. Campi obbligatori segnati con
  «*» (mezzo: nome, targa, alimentazione, consumo; autista: nome, cognome, email; deposito: nome e
  indirizzo; collaboratore: nome, email, profilo; agente: nome, cognome, email, stato; cliente: nome,
  via, civico, CAP, comune, provincia, tempo di scarico). Premendo «Salva» con dati mancanti si apre la
  prima scheda incompleta, con «!» su tutte quelle da completare (GFFormTabs in design-system.js).
- POD solo per l'azienda: l'app autista e il portale via link non mostrano più «Scarica POD» e il
  server risponde 403 se lo chiedono; firma e foto restano visibili. Chat autista: la casella di
  scrittura sta sopra il nuovo menu in basso.
- App autista ridisegnata (versione A): logo GiroFacile vero, «I miei giri» con il giro di oggi in
  grande e i prossimi giorni in elenco (i passati nello Storico); nel giro avanzamento a barra, la
  prossima consegna in una scheda con Naviga, Consegnato/Mancata, Chiama/Nota, e sotto tutte le fermate.
  Nuova pagina «Posizione» (menu in basso e pallino GPS in alto): stato del permesso, tasto «Attiva
  posizione» che fa comparire la richiesta del telefono e istruzioni per sbloccarla su iPhone e Android.
  Tolti il riquadro «ETA con traffico» e il blocco GPS sempre visibile. Corretta la migrazione
  20261108_01 sui database senza tabella utenti.
- Pianificazione: tolto il vecchio pannello «Seleziona clienti», che ricompariva tornando alla
  pianificazione dopo un calcolo. I clienti si aggiungono solo dalla finestra «Aggiungi clienti».
- Fonti ordini: «Telefono» tra i dati facoltativi da importare (si può escludere come gli altri).
  Shopify e WooCommerce ora leggono il telefono di spedizione (poi ordine o fatturazione).
- Ordini: nuovo campo facoltativo «Telefono destinatario» (`phone`) nel modulo, nel dettaglio, nelle
  importazioni da file (colonne telefono, tel, cellulare, recapito) e nell'API delle fonti. Salvato con i
  dati operativi, senza migrazione. Nell'app autista «Chiama» usa la scheda cliente e, se manca, il
  telefono del primo ordine della fermata che lo indica.
- App autista, consegna attiva: tasto «Chiama» (tel:) con il numero della scheda cliente, accanto
  ad «Aggiungi nota»; senza numero non compare. Al posto di arrivo, ripartenza e km tappa resta solo
  «Arrivo previsto», ricalcolato dal server come nel tracking (partenza reale, anticipi e ritardi
  delle consegne chiuse), con «+N min di ritardo» o «N min in anticipo» da 5 minuti in su.
- Tracking del cliente ridisegnato (versione A) con i componenti di GiroFacile: in alto logo e nome
  dell'azienda, una scheda con stato, numeri grandi (arrivo, fermate prima della tua, data),
  avanzamento in tre passi e avvisi; «Tracking fornito da GiroFacile» in fondo. Il colore del brand
  scelto in Azienda ora si salva (migrazione 20261108_01, colonna users.company_brand_color; i colori
  troppo chiari per il testo bianco sono rifiutati) e colora la pagina. Il logo arriva da
  /api/public/tracking/logo con lo stesso token. L'anteprima in Azienda segue la pagina vera.
- Super Admin → Server: sezione «Indirizzi per i test in locale» (solo fuori produzione).
  Mostra gli indirizzi del computer (Wi-Fi, Tailscale), sceglie quello usato nei link
  (inviti autisti e agenti, email, tracking, QR) ed elenca i collegamenti di ogni portale da
  copiare. start_locale_windows.bat ora ascolta anche sulla rete (0.0.0.0).
  Ogni app (gestionale, telefono, autista, agenti, tracking, Super Admin) può avere un
  indirizzo proprio; vuoto = indirizzo generale.
- Tendine nuove in tutto il software (variante A, senza icone colorate): con mouse o trackpad
  si apre l'elenco di GiroFacile (componente `.gf-listbox`) con nome, riga di dettaglio e stato
  a destra (Disponibile, In mezzo N, Non disponibile), spunta sulla voce scelta e ricerca da 9
  voci. La select resta la fonte del valore; sui telefoni resta il selettore nativo.
- «Aggiungi GiroFacile alla tua Home» (variante B): finestra dopo l'accesso nell'app autista e
  nel portale da telefono, una volta sola. iPhone: tre passaggi (Condividi, Aggiungi alla
  schermata Home, Aggiungi); Android: pulsante «Installa». Non compare se l'app è già
  installata; «Più tardi» la rimanda di 3 giorni.
- App installabili sulla schermata Home: manifest «GiroFacile Autista» (/driver) e
  «GiroFacile» (/mobile), service worker alla radice (/sw.js) che non tiene dati in cache
  e mostra «Sei offline» senza rete.
- Indirizzo a campi separati (variante B): via, civico, CAP e comune nel cliente e
  nell'ordine, con la riga «Verifichiamo esattamente: …» che mostra cosa arriva a Google.
  Clienti: nuova colonna CAP (migrazione 20261107_01), l'indirizzo resta «via civico».
  Ordini: campi nei dati dell'ordine, indirizzo su una riga composto dai campi; gli ordini
  già salvati si aprono con i campi ricavati dalla riga. Import: colonne via, civico, CAP,
  comune, provincia (resta valida la colonna unica); Shopify e WooCommerce senza paese e
  senza seconda riga dell'indirizzo, che va nelle note.
- Giri non partiti in orario (services/late_start.py): fino a 15 minuti dopo la partenza
  nessun avviso; oltre, «In ritardo» se partendo adesso fasce, turno e pause reggono ancora
  (stesse tratte salvate), altrimenti o dopo 30 minuti «Da riprogrammare» e l'autista non può
  avviare. L'ufficio sposta la partenza ad adesso (orari ricalcolati), riprogramma o annulla.
  Un giro di un giorno passato mai avviato è «Non avviato» e va riprogrammato. Badge in Giri
  programmati, avviso nel dettaglio e in Dashboard; la chiusura manuale resta sempre possibile.
- Verifica indirizzi severa: verificato in automatico solo se Google conferma comune (o CAP),
  via, civico e posizione sul civico; altrimenti «Indirizzo da correggere» con il motivo.
- Pedaggi in anteprima: nella suddivisione fra i mezzi e nell'anteprima del giro singolo
  la card in alto mostra la stima dei pedaggi al posto del rientro (nell'anteprima
  singola l'orario di rientro resta sotto la partenza). La stima usa il percorso
  stradale OSRM e le tariffe configurate, anche senza traffico; un giro senza dati
  rende la stima «parziale» e non vale zero. La programmazione riusa la stima del
  giro singolo e ricalcola quella della suddivisione.
- Ore dell'autista: il calcolo all'indietro della partenza più tarda ora tollera gli
  errori di arrotondamento (1e-9 minuti). Su un giro teso dopo un'attesa d'apertura
  ritrovava l'apertura come 899,9999999999999 invece di 900 e azzerava lo
  spostamento: nel piano reale 32 un giro valeva 655 minuti di lavoro invece di 206,
  quindi «Distribuisci il lavoro» e il punteggio km + ore scartavano proposte migliori.
  Piani reali, stessa data: stesse consegne servite, 108 km e 4,7 ore in meno; giro
  più lungo 233 → 208 minuti nel piano 32 e 439 → 413 nel piano 24.

- Motore dei giri V1, PyVRP: la prima ricerca usa sempre tutto il tempo previsto.
  Il secondo tentativo, con penalità più alte, parte solo se alla fine non c'è un
  piano valido e riceve al massimo il 35% di tempo in più. Con la riserva al 65%
  Solomon r104 e r112 lasciavano fuori 3 e 5 consegne su un computer più lento:
  ora tutti i 36 problemi servono tutte le consegne (scarto medio 0,72% dalla
  migliore soluzione nota). Nel bilanciamento un limite di durata troppo stretto
  si scarta senza secondo tentativo. Pagina anteprima del giro: titolo e stato
  nella barra in alto, avvisi solo nella tabella accanto alla fermata (anche le
  consegne escluse), mappa a tutta larghezza con riepilogo e pulsanti sotto.
- PyVRP: la ricerca con una soluzione già fattibile può usare l'intero tempo della
  propria fase, continuando a recuperare consegne escluse. La riserva per il secondo
  tentativo scatta al 65% soltanto se il primo è ancora non fattibile. Il limite
  complessivo resta condiviso e non viene raddoppiato dal retry.
- R104: aggiunti input ufficiale con checksum e confronto offline riproducibile dei
  due adattatori PyVRP, con controllo indipendente delle soluzioni. Gli audit distinguono
  la variazione fra ricerche effettivamente limitate a tempo dagli errori di fattibilità
  o di ottimo; una mancata ripetibilità senza solutori a tempo resta un errore.

- GF Engine Optimizer 1.0: il punteggio sottrae solo le attese eliminabili con una
  partenza realmente compatibile con pause e finestre, a passi di cinque minuti;
  con partenza fissa conta tutta la durata. PyVRP ha un limite alla dimensione del
  modello prima dell'allocazione e una scadenza condivisa fra costruzione e tentativi.
  Il verificatore indipendente usa il nuovo lavoro effettivo anche nel bilanciamento;
  i confronti storici conservano il proprio calendario congelato. Aggiornati il
  requisito dell'ultima migrazione e i test PostgreSQL di migrazione e tracking.
  Dettagli e controlli in docs/gf-engine-optimizer-1.0-fixes-2026-11-06.md.

- Calcolo dei giri, «Distribuisci il lavoro»: le ore di ogni autista non
  contano più l'attesa che una partenza più tarda elimina (come già in «Riduci
  chilometri e tempi»), quindi un autista con soli clienti del pomeriggio non
  sembra più lavorare dalle 8:00. Anche qui si affianca la proposta di PyVRP,
  che accorcia il giro più lungo. Sui 12 piani salvati: 35 ore di lavoro e 37
  ore di attesa in meno, giro più lungo fino a 4 ore più corto, stesse
  consegne servite. Dettagli in docs/motore-pyvrp-2026-11-05.md.
- Calcolo dei giri con più mezzi, «Riduci chilometri e tempi»: al piano
  trovato si affianca una seconda proposta calcolata con PyVRP (libreria
  gratuita, sul server). Vince sempre il piano migliore secondo le regole di
  GiroFacile: prima più consegne servite, poi meno km e ore. Su 36 problemi
  pubblici di riferimento serve sempre tutte le consegne (prima ne lasciava
  fuori in 14 problemi) e resta in media allo 0,7% dalla migliore soluzione
  nota. Sui piani salvati: fino a 3 consegne servite in più, fino a 24 km in
  meno. Il calcolo dura qualche decina di secondi in più. Dettagli in
  docs/motore-pyvrp-2026-11-05.md.
- Calcolo dei giri: vince il giro con meno km più ore di lavoro
  dell'autista, convertite in km con un peso fisso (1 ora = 60 km), e non
  più sempre quello con meno km. Il peso non dipende da prezzi del
  carburante o costi scritti dal cliente. Le ore contano anche quando
  l'autista aspetta che un cliente apra. Se le attese lo permettono, il
  giro parte più tardi (a multipli di 5 minuti) con lo stesso rientro:
  l'orario resta modificabile. Con più mezzi una ricerca di riserva sui
  soli km impedisce che il risultato sia peggiore di quello precedente; la
  proposta segnala la partenza spostata e le attese oltre 45 minuti.
  Dettagli e confronto in docs/punteggio-giri-2026-11-05.md. Il nome della fascia segue l'orario: 14:00–18:00 è «Pomeriggio»
  anche se salvata come prima fascia.
- Chat autisti: il riquadro della conversazione finisce sotto la casella
  d'invio e non si allunga più fino in fondo alla lista delle conversazioni.
- Giri programmati e Storico: tolta la scritta «Oggi» sotto il giorno, che
  allungava il riquadro; oggi ha il numero della data in rosso.
- Storico: nei giorni vuoti da oggi in poi, al posto di «Giorno futuro»,
  icona e pulsante «Pianifica giro», come in Giri programmati.
- Giri programmati: nuovo aspetto della settimana. Il colore segue il giorno
  che si sta guardando e non più oggi (che resta solo scritto, «Mer · Oggi»);
  ogni giro mostra orario, autista, mezzo e fermate; in fondo alla colonna
  «Mostra di più» apre la tabella del giorno; nei giorni vuoti icona e
  «Pianifica giro», solo da oggi in poi; gli annullati restano nella tabella
  (badge rosso solo se il giorno ha soltanto annullati). Niente più ambra:
  conteggi grigi, azzurri sul giorno scelto. Tabella del giorno con avatar
  dell'autista e targa del mezzo.
- Storico: la settimana ha lo stesso aspetto di Giri programmati (stessa
  funzione `dashWeekColumn`): colore sul giorno scelto, giri con orario,
  autista, mezzo e fermate, «Mostra di più» in fondo, giorni futuri vuoti senza
  «Pianifica». Tolti dal sistema di stile la colonna di oggi in blu, le card
  con la striscia colorata e il giorno tratteggiato, non più usati; catalogo e
  documentazione aggiornati.
- Giri in corso: la sezione «Giri attivi» è una tabella, una riga per giro con
  autista e mezzo, avanzamento, prossima fermata, rientro stimato (con il
  ritardo sul previsto) e segnali (mancate, ritardo, GPS, messaggi non letti
  dell'autista); «Apri» mostra il giro nel dettaglio sotto. Mappa, indicatori e
  fermate restano invariati.
- Finestre (gf-modal) su iPhone: Safari le schiacciava a una riga alta zero,
  lasciando la pagina scurita e apparentemente bloccata (per esempio «Controlla
  gli indirizzi» dopo «Vai alla pianificazione»). Contenuto e corpo della
  finestra ora prendono l'altezza del contenuto; sul computer non cambia nulla.
- Verifica degli indirizzi selezionati più veloce e con la schermata di attesa
  del calcolo del giro («Controllo 6 di 12 indirizzi…»): il server chiede a
  Google fino a 6 indirizzi diversi alla volta in parallelo, invece che uno dopo
  l'altro, e un indirizzo ripetuto una volta sola. Nella prova con 12 indirizzi
  (2–3 secondi per risposta di Google) circa 6 secondi invece di circa 30.
- La pagina aperta resta nell'indirizzo (es. `/dashboard#ordini`): con F5 si
  riapre la stessa pagina e Indietro/Avanti del browser si muovono tra le pagine
  del portale. Le pagine legate a un lavoro a metà (importazione, giro in
  pianificazione) riaprono Ordini; una pagina non consentita al collaboratore
  riapre la sua pagina iniziale.
- Nuova finestra «Controlla gli indirizzi» prima della pianificazione: tabella
  con indirizzo scritto, proposta di Google e motivo («Non trovato», «Altro
  comune», «Posizione approssimativa»); «Modifica» apre sotto la riga il campo da
  correggere e la mappa per mettere lo spillo. Ogni indirizzo si sistema riga per
  riga dal cliente: di proposito non c'è un «accetta tutto», e la proposta in un
  altro comune non sposta lo spillo.
- Correzioni dal collaudo con 250 ordini:
  - verifica indirizzi: un risultato di Google vale solo se corrisponde al CAP o
    al comune scritti (si sceglie il primo che corrisponde); altrimenti l'ordine
    resta da verificare con la posizione proposta da confermare sulla mappa.
    Prima «Via Nazionale 95, 80031 Brusciano» diventava Orosei (Sardegna);
  - più mezzi: un rientro oltre la fine del turno dovuto al traffico ora è un
    avviso nella revisione e fa rifare la divisione, invece di bloccare solo
    alla programmazione;
  - più mezzi: un autista con il turno che inizia dopo l'orario di partenza
    parte a inizio turno, invece di restare inutilizzato;
  - messaggio del turno con la causa (partenza prima del turno o rientro dopo la
    fine) e pulsante «Torna alla pianificazione» nella pagina d'errore del calcolo.

- Puntualità prima dei chilometri: se con il traffico una consegna resta fuori
  fascia anche dopo il riordino, il multi-mezzo rifà la divisione tra i mezzi
  con i tempi corretti e un margine di sicurezza sulle fasce (15–45 minuti) e
  tiene il nuovo piano se serve le stesse consegne con meno ritardi, anche con
  più km. Sul piano reale di prova: Agriturismo Luna da +28 minuti a in orario,
  con 6 km in più. Il giro singolo usa lo stesso margine nel secondo passaggio.

- OR-Tools anche nel giro singolo (oltre 8 fermate: parte dall'ordine trovato e
  resta solo se il giro migliora, servendo tutte le consegne) e nella strategia
  «Distribuisci il lavoro» (cerca giri equilibrati, con lo stesso controllo di
  accettazione). Stessa regolazione FLEET_ORTOOLS_SECONDS.

- Doppio passaggio Mapbox: calcolato il giro (singolo o più mezzi), si chiedono
  i tempi con il traffico; se qualche consegna finisce fuori fascia, le fermate
  vengono riordinate con i tempi allungati dal traffico misurato su quel giro e
  si richiede Mapbox. Il nuovo ordine resta solo se ha meno ritardi. Il giro
  singolo mostra già al calcolo orari con traffico e pedaggi. Una o due chiamate
  per giro; nessuno storico salvato.

- Più mezzi, strategia «Riduci chilometri e tempi»: dopo il calcolo attuale il
  piano passa a Google OR-Tools, che parte da quel piano e cerca giri più corti.
  Si tiene solo se migliore e senza perdere consegne (nel confronto su 47
  problemi: -14% di km con 50 consegne, -30% con 100). Da 1 a 10 secondi in più
  secondo il numero di consegne; regolabile con FLEET_ORTOOLS_SECONDS (0 lo
  spegne). Nuova dipendenza: ortools 9.15.6755.

- Tempo di scarico stimato dai colli: per clienti e ordini senza un tempo proprio
  il calcolo usa minuti fissi più un tempo per collo (predefiniti 4 minuti + 15
  secondi, massimo 30: 3 colli 5 minuti, 40 colli 14). Il tempo scritto a mano
  sul cliente o sulla fermata e quello imparato dalle consegne reali hanno la
  precedenza; senza colli restano 10 minuti. La formula si regola in
  Impostazioni. Lo scarico deve sempre finire entro la fascia del cliente.

- Aggiornando la pagina (F5) da utente collegato non compare più la schermata di
  login, disegnata due volte a grandezze diverse prima che si applicasse la
  scala dell'interfaccia. Finché si verifica la sessione si vede solo lo sfondo;
  poi il gestionale, oppure il login se l'utente non è collegato (comunque dopo
  6 secondi al massimo).

- Pianificazione dagli ordini: niente più blocco «Ordine … aggiornato: ricarica
  la selezione o il giro». Se un ordine cambia dopo la selezione (anche solo
  perché il giro è stato salvato in bozza), prima del calcolo la fermata ne
  ricarica i dati (indirizzo, colli, peso, orari, note) e compare un avviso; la
  durata dello scarico scelta sulla fermata resta. Il blocco rimane solo per gli
  ordini annullati o presi da un altro giro.

- Pianificazione, lista delle consegne: nuovo tasto «Aggiungi ordine» accanto ad
  «Aggiungi cliente». Si apre una finestra con gli ordini pronti e non ancora
  programmati per la data del giro (ricerca e provenienza), si spuntano e si
  aggiungono alle consegne senza ripartire da capo: mezzi, autisti, turni e
  modifiche alle fermate restano. Se la selezione unisce gli ordini per
  destinatario, il nuovo ordine entra nella fermata compatibile già presente.
- «Aggiungi cliente» ridisegnato con lo stesso schema: finestra grande con
  ricerca e filtri per comune, provincia e agente, tabella con caselle di spunta
  e «seleziona tutti», aggiunta di più clienti insieme. I clienti già nel giro e
  quelli raggiungibili solo in traghetto non si possono spuntare.

- Clienti raggiungibili solo in traghetto (isole e, dal deposito su un'isola,
  il continente): esclusi in automatico dal giro singolo e dalla pianificazione
  a più mezzi, con l'avviso «Consegna non programmabile: il cliente si trova su
  un'isola». Il calcolo stradale non conosce orari delle corse né imbarco e
  dava tempi senza senso. Dettagli in [docs/isole-traghetto.md](docs/isole-traghetto.md).

- Pianificazione, «Chi fa le consegne?»: una sola card del mezzo, uguale con uno
  e con più mezzi (mezzo, autista, turno, pausa e costo carburante). Sotto mezzo
  e autista si vede la disponibilità («Disponibile», «Non disponibile · In uso»,
  «3 mezzi disponibili su 4»). Passando a «Più mezzi» la card 1 resta com'è e si
  aggiunge una card vuota; tornando indietro e di nuovo a più mezzi riappaiono le
  altre card. La X compare su ogni card appena sono più di una; restandone una si
  torna a «Un solo mezzo». «Aggiungi mezzo» funziona anche cliccando sul testo.
  Con un solo mezzo il costo carburante sta nella card (niente riquadro separato)
  e, come con più mezzi, parte da «Automatico» (prezzo medio nazionale).

- Schermata di attesa a tutto schermo: durante il calcolo dei giri compare un
  velo chiaro sfocato su tutto il gestionale, con al centro il logo GiroFacile
  che si disegna, un titolo con il numero reale di mezzi ("Sto pianificando i
  giri di 4 mezzi"), frasi che cambiano e una barra senza percentuale. Vale per
  il calcolo multimezzo, il ricalcolo e la conferma della suddivisione e il
  calcolo del giro singolo; resta almeno 2 secondi anche se il calcolo è più
  rapido e, oltre i 45 secondi, avvisa che ci vuole più del solito.
- Piani e abbonamento: aperta dal riquadro "Passa a …" della sidebar mostrava
  "—" al posto del nome del piano attivo, perché il piano veniva letto solo
  aprendo il profilo. Ora è noto subito dopo l'accesso.
- Sidebar: il riquadro "Passa a …" ha ora una sola versione, compatta: tutta
  la card è il pulsante, con icona, «Passa a Pro ›» e la descrizione intera su
  due righe ("AI, 6.000 ordini al mese e 50 mezzi."). Entra anche con tutti i
  gruppi aperti e le voci Giri in bozza e Giri programmati su uno schermo con
  Windows al 150%; sparisce solo se nemmeno così c'è posto.
- Sidebar: con la finestra bassa il riquadro "Passa a …" non perde più subito
  la descrizione: mostra una riga breve ("AI, 6.000 ordini e 50 mezzi." per Pro,
  "Più mezzi, firma e foto." per Business) con titolo e pulsante. Solo se
  nemmeno così entra restano titolo e pulsante, e solo all'ultimo sparisce.
- Barre di scorrimento più moderne in tutte le pagine: sottili, grigie, con
  piccole frecce dello stesso grigio sopra e sotto; più scure al passaggio del
  mouse. Valgono per la pagina e per le aree che scorrono (elenchi, tabelle,
  sidebar, dove barra e frecce sono chiare e semitrasparenti). In Firefox la
  barra è grigia senza frecce.
- Gestionale e Super Admin: l'interfaccia si adatta da sola allo schermo e
  mostra sempre la stessa area di lavoro (circa 1707 × 960 px), cioè quello che
  si vedeva con Windows al 150% e Chrome al 75%. Non serve più cambiare lo zoom:
  su schermi piccoli o con Windows ingrandito tutto si rimpicciolisce (non
  sotto il 75%), su schermi grandi si ingrandisce (non oltre il 150%). Sotto i
  1024 px resta il layout a scomparsa. La settimana dei giri, la barra dei
  numeri, il Report e l'Azienda seguono lo spazio reale del contenuto.
- Sidebar della Dashboard: all'avvio tutti e quattro i gruppi sono aperti
  (anche "Azienda e sistema"), con voci sempre compatte, e restano chiudibili.
  Le voci non si ingrandiscono più in base allo spazio, così in fondo resta
  posto per il riquadro "Passa a …". Con la finestra bassa il riquadro perde il
  testo e resta con titolo e pulsante; sparisce solo se nemmeno così entra.
- Giri programmati e Storico: settimana più curata con la stessa disposizione.
  Intestazione del giorno stile calendario (nome breve e numero grande, «N
  giri» solo se ci sono giri attivi), colonna di oggi con bordo blu, sabato e
  domenica su fondo più chiaro, giri come piccole card con solo orario e
  autista e una striscia colorata (ambra programmato, verde completato, grigia
  e barrata se annullato, in fondo alla colonna), giorni vuoti tratteggiati con
  «+ Pianifica» nei Giri programmati. Accanto al titolo dei Giri programmati il
  riepilogo della settimana; nel dettaglio del giorno l'etichetta «Oggi» e lo
  stato vuoto con icona.
- Sidebar della Dashboard: fondo blu notte e voce attiva in un riquadro
  semitrasparente con barretta blu, come nel layout base; gruppi invariati.
- Sidebar: riquadro di upgrade ridisegnato (card scura con bordo, icona a
  razzo blu a sinistra, titolo, testo e pulsante «Scopri i piani» blu a
  destra). Non si nasconde più ogni volta che si apre "Azienda e sistema":
  sparisce solo se, con i gruppi aperti in quel momento, non c'è spazio (per
  esempio con tutti e quattro i gruppi aperti). Vale anche su tablet e telefono.
- Giri in bozza allineata alle altre pagine: numeri in alto (da riprendere,
  percorsi calcolati, consegne in bozza, ultimo salvataggio), nome del giro in
  grassetto con origine, mezzi o autista sotto, fase come etichetta, azioni
  secondarie (Riprendi / Apri giro, Elimina). Anche i giri calcolati mostrano
  origine, mezzo, autista e numero di fermate.
- Giri in bozza diventa una pagina: voce "Giri in bozza" nella sidebar
  (Attività), visibile solo quando ci sono bozze e con il loro numero; non più
  riquadri in Dashboard e Ordini. La pagina elenca in tabella bozze da ordini e
  da clienti e giri calcolati non programmati (fase, origine, data, mezzi,
  consegne, salvataggio), con Riprendi/Apri ed Elimina. Riprendendo si torna
  alla fase in cui il giro era stato lasciato: una bozza lasciata in "Controlla
  la suddivisione" riapre la stessa suddivisione (ricalcolata se scaduta). Gli
  ordini rimasti selezionati da un giro già portato in pianificazione vanno in
  bozza all'accesso, così non restano spuntati. Migrazione 20261027_02.
- Giri in bozza: lasciando la pianificazione (pre-pianificazione, anteprima o
  "Controlla la suddivisione") con un giro non ancora programmato compare
  l'avviso "stai per mandare questo giro in bozza". Confermando, il giro
  (ordini o clienti scelti, configurazione, mezzi e fermate) viene salvato come
  bozza e il pianificatore si svuota: aprendo Ordini o Clienti la selezione non
  resta più spuntata. Le bozze compaiono in Dashboard e in Ordini nella sezione
  "Giri in bozza" (nascosta quando non ce ne sono), con "Riprendi" ed
  "Elimina"; ci sono anche i giri già calcolati e non ancora programmati, con
  "Apri". Riprendendo una bozza da ordini, quelli non più da pianificare
  (annullati o già in un giro) vengono esclusi. Nuova tabella planning_drafts e
  API /api/planning-drafts. La tabella si crea con la migrazione 20261027_01
  (python -m app.migrations).
- Storico, vista settimana: ogni giorno mostra al massimo 3 giri; sotto,
  "Mostra altri N" seleziona quel giorno e porta alla tabella in basso con
  l'elenco completo (la colonna del giorno non si allunga).
- "Controlla la suddivisione": le fermate del giro scelto sono ora una tabella
  (#, cliente con indirizzo, avvisi, arrivo, "Sposta in", azioni con maniglia e
  ×); su telefono ogni fermata diventa una scheda. L'etichetta del fuori orario
  è più corta ("Fuori orario +22 min"), con l'orario di fine nel suggerimento.
- "Controlla la suddivisione": ogni fermata ha il pulsante "Togli dai giri"
  (×). La consegna diventa non assegnata, compare in "Da sistemare" (con
  "Assegna al giro N" per rimetterla) e, dopo "Ripianifica giri", non viene
  programmata confermando "programma soltanto le consegne assegnate".
- "Controlla la suddivisione", spostamenti più chiari: ogni fermata ha il menu
  "Sposta in…" con l'elenco degli altri giri (funziona anche da telefono, dove
  il trascinamento non c'è). Se "Ripianifica giri" viene rifiutato (per esempio
  fasce orarie, turni o capienza non rispettati in un giro, o anteprima
  scaduta), il motivo compare nella barra in basso al posto dell'invito a
  ripianificare, finché non si sposta di nuovo o si annulla.
- "Controlla la suddivisione" come le altre pagine: titolo e sottotitolo nella
  barra in alto, freccia per tornare alla pianificazione e "Pianifica giri"
  accanto alla campanella; a giri programmati il titolo mostra l'etichetta
  "Giri programmati".
- "Controlla la suddivisione": quando si sposta una consegna fra i giri non
  compare più l'avviso giallo in alto ("Ricalcolo necessario" / "Suddivisione
  manuale"). Compare solo la barra in basso, ora con il tasto "Ripianifica
  giri" (prima "Ricalcola assegnazioni") e "Annulla modifiche". Resta l'avviso
  dei giri in bozza se la programmazione non si completa.
- "Controlla la suddivisione": tolti i due avvisi grandi in alto (riepilogo
  della distribuzione e clienti fuori orario). Le consegne fuori orario e non
  assegnate restano in "Da sistemare"; restano gli avvisi di ricalcolo e di
  bozza non programmata.
- Pianificazione con più mezzi: sparisce il riquadro "Costo del giro" (il
  prezzo del carburante si imposta già in ogni card del mezzo, in "Costi
  carburante ed energia") e la mappa "Dove sono i clienti" prende tutta la
  larghezza. Anche la barra in basso non mostra più il carburante. Con un solo
  mezzo non cambia nulla.
- Più mezzi, "Controlla la suddivisione": nuovo layout. In alto la tabella di
  confronto dei giri (autista, mezzo, fermate, km, costo, rientro, avvisi);
  sotto il giro scelto con la mappa (gli altri giri attenuati, un colore per
  giro come l'avatar) e le fermate in ordine, con sponda, ZTL e fuori orario
  come etichette. A destra "Da sistemare" elenca solo le consegne non assegnate
  e quelle fuori orario; «Assegna al giro N» sposta una non assegnata nel giro
  che si sta guardando. Le fermate si trascinano sulla riga di un altro giro.
- Profilo account: finestra più compatta a due colonne. A sinistra avatar,
  ruolo, nome, email e password; a destra il piano con stato, barre di
  utilizzo e i pulsanti Gestisci piano e Fatturazione. Niente più "Salva
  profilo": come in Profilo azienda la barra "Salva modifiche" compare solo
  dopo una modifica; chiudere senza salvare annulla le modifiche.
- Sidebar: la pagina misura lo spazio libero e ingrandisce le voci (36, 40, 44
  o 48 px, testo più grande da 40 px) senza mai far comparire la barra di
  scorrimento; si ricalcola quando si apre o chiude un gruppo e quando cambia
  la finestra. Se non c'è posto nemmeno con voci da 32 px, il riquadro di
  upgrade si nasconde.
- Sidebar: in fondo un riquadro blu invita al piano successivo (Starter →
  Business, Business → Pro) e apre Piani e abbonamento. Non compare con Pro,
  per i collaboratori e quando è aperto "Azienda e sistema". Nuovo componente
  `.gf-sidebar-upgrade` nel catalogo.
- Anteprima giro (un mezzo): pagina ridisegnata come il dettaglio dei giri
  programmati. Testata con nome e stato, numeri con icone, tabella delle
  fermate in alto e, sotto, mappa con autista, mezzo, costi, avvisi "Prima
  della partenza" e "Programma giro". Stampa e spiegazione AI in "Altre azioni".
- Corretto: la barra di navigazione del telefono compariva anche su computer,
  per due chiusure in più lasciate nella pagina Fatturazione.
- Fatturazione: pagina ridisegnata. In alto il prossimo addebito con stato,
  carta, email per le fatture e ultimo pagamento (niente più fila di quattro
  riquadri); fatture e pagamenti in un pannello a schede; dati fiscali in
  lettura con "Modifica" e barra di salvataggio, e controllo dei dati per la
  fattura elettronica. Tolto il riquadro "Notifiche di pagamento", che
  indicava come attivi invii email non presenti.
- Piani e abbonamento: pagina ridisegnata. In alto il piano attuale con stato,
  prezzo, scadenza e consumi del mese; sotto tre card da scegliere con limiti e
  funzioni (✓ incluse, ✕ non incluse; firma, foto e prova di consegna in una
  sola voce), confronto completo apribile e barra flottante per il cambio piano.
- Portale autista: senza rete gli esiti (consegnata, mancata, nota) restano
  salvati sul telefono, compaiono subito nel giro e partono da soli quando la
  connessione torna. Un riquadro indica quanti esiti attendono l'invio.
- Ordini: tolta dalle fonti la scheda "Email", non ancora disponibile. Shopify,
  WooCommerce, file e API standard restano attivi.
- Configurazione: aggiunto `.env.example` con tutte le impostazioni del server.
- Repository: changelog storici spostati in `docs/storico`.
- Produzione: l'avvio si blocca anche con SQLite, `APP_BASE_URL` non https o
  archivio prove di consegna locale/incompleto; email, avvisi errori e altre
  impostazioni mancanti compaiono come avvisi nel log.
- Produzione: nuovo `/health` (app + database), healthcheck Docker, proxy HTTPS
  Caddy in `deploy/caddy` e guida in `deploy/README.md`.

## 2026-11-03 — Recupero ritardi e conservazione dello scarico manuale

- Recupero dopo il traffico: prima finestre reali, poi eventuale margine; conserva
  il migliore dei tentativi verificati senza ridurre le consegne assegnate.
- Il margine non estende le finestre già troppo corte per lo scarico.
- Conserva i 10 minuti manuali e i tempi registrati sul cliente; distingue
  provenienza automatica, manuale e non specificata nel payload delle fermate.
- Regressioni per il caso 3 consegne/2 mezzi, traffico non disponibile, impossibilità
  residua, salvataggio/ricaricamento dei tempi manuali e serializzazione frontend.
