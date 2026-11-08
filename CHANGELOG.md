# Changelog

Le note delle versioni tecniche precedenti (V87–V89.7) sono in [docs/storico](docs/storico/).
Da qui in avanti le modifiche si annotano in questo file, la più recente in alto.

## Verso la V1

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
