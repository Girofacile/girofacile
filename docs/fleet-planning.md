# Pianificazione su più mezzi

La schermata Pianificazione conserva i tre passaggi Dati del giro, Risorse e Rientro.
In Risorse si sceglie Un solo mezzo oppure Suddivisione automatica su più mezzi.
In entrambi i casi mezzo e autista si scelgono nella stessa card (fleet-planning.js), con la disponibilità sotto ciascuno, turno, pausa e costo carburante: con un solo mezzo c'è una card, che legge e scrive i campi del giro singolo (routeVehicle, routeDriver, fuelPrice, turno di #routeDriverSchedule); con più mezzi una card per mezzo, con la X per toglierla (restandone una si torna a un solo mezzo). Passando a più mezzi la card 1 resta e se ne aggiunge una vuota.
Con più mezzi compare anche la strategia:

- Riduci chilometri e tempi: a parità di consegne e compatibilità, minimizza il punteggio km più minuti di lavoro dell'autista (1 ora = 60 km equivalenti), poi i chilometri, la somma delle durate e i mezzi usati.
- Distribuisci il lavoro tra tutti i mezzi: a parità di consegne e avvisi, utilizza più risorse e minimizza la durata massima, poi lo squilibrio delle durate (somma dei quadrati), la durata totale e i chilometri. Dal 6 novembre 2026 la durata è quella del lavoro dell'autista (`optimizer.work_minutes`): come nel punteggio di «Riduci chilometri e tempi», non conta l'attesa che una partenza più tarda elimina senza spostare il rientro; le attese a metà giro restano.

Entrambe danno prima priorità al numero di consegne fattibili assegnate e poi alla riduzione degli avvisi per sponda e ZTL. La sponda è una preferenza con avviso: il motore cerca un mezzo attrezzato, ma una consegna rimane assegnabile anche quando il mezzo non la possiede. L'operatore vede l'avviso e decide se programmare lo stesso oppure modificare la suddivisione. Questo vale per assegnazioni automatiche, revisioni manuali e piani già salvati; l'assenza della sponda non blocca conferma o programmazione.

La ricerca usa una sola matrice stradale condivisa. Fino a 7 fermate e 3 coppie confronta tutti i sottoinsiemi, gli ordini e le assegnazioni, compresa la possibilità di lasciare fermate non assegnate. Sceglie il migliore secondo la strategia selezionata. Oltre questi limiti usa una ricerca interna con budget: costruzioni alternative per scadenze e geografia, riordino, trasferimenti, scambi di fermate e di tratti finali tra mezzi. Ricostruzioni parziali cercano di superare gli incastri che richiedono più spostamenti coordinati. Un archivio di giri già verificati permette anche di ricombinare più assegnazioni senza ripetere chiamate stradali. Mantiene l'inserimento precedente come candidato sotto i vincoli e l'obiettivo correnti; non certifica un ottimo globale sui casi grandi.
Dopo la suddivisione, ogni giro fino a **8 fermate** riceve un riordino completo su tutti gli ordini possibili (`8! = 40.320`). La soglia riguarda il singolo giro: vale anche con 50 o 100 consegne totali. Consegne e mezzo assegnati rimangono fissi; la strategia efficiente minimizza il punteggio km più lavoro effettivo, quella bilanciata il lavoro effettivo e poi i km. Le pause e le finestre continuano a essere verificate per ogni ordine. Le attese vengono sottratte soltanto se lo stesso calendario permette davvero di ritardare la partenza, a passi di cinque minuti, mantenendo il rientro. Con partenza bloccata non vengono sottratte.

Le ricerche limitate a tempo, come OR-Tools e PyVRP, possono trovare piani diversi in esecuzioni dello stesso input anche con seed fissa: varia il numero di iterazioni entro la scadenza. Gli audit registrano separatamente queste variazioni solo quando la diagnostica conferma un solutore effettivamente eseguito; senza tale evidenza la mancata ripetibilità resta un errore. I controlli di fattibilità e delle garanzie di ottimo restano invariati.

La matrice stradale globale è già completa e viene riutilizzata: non si richiede una nuova matrice o un provider per ogni permutazione. Un valutatore preparato riusa gli stessi selettori di finestre e l'aritmetica delle pause del valutatore canonico. Il vincitore viene verificato e poi ricostruito con tutti i dettagli ETA. La verifica canonica del vincitore non sostituisce i test di equivalenza esaustivi sul valutatore preparato.

Per i giri oltre 8 fermate resta l'ordine trovato dall'euristica attuale. Non si forza la creazione di più giri soltanto per rientrare nella soglia. L'ottimo dell'ordine di un gruppo assegnato non certifica l'ottimo della suddivisione dell'intera flotta; la prova globale fino a 7 fermate e 3 risorse rimane distinta e viene riutilizzata per evitare lavoro ridondante.

La ricerca usa i tempi stradali allungati di un margine prudente (`fleet_traffic_margin`, predefinito 1.15 = +15%). Finita la ricerca, i giri proposti vengono verificati con il traffico reale (una richiesta al fornitore per giro, anche a ogni ricalcolo): la revisione mostra minuti e rientro con traffico e segnala in rosso le consegne che finirebbero fuori fascia; come per il giro singolo, lo scarico fuori fascia non blocca la programmazione ma resta come avviso sui giri programmati. Alla programmazione il traffico dell'anteprima viene riusato se ha meno di 60 minuti ed è per la stessa partenza; altrimenti viene richiesto di nuovo.

L'operatore può indicare i prezzi energetici nei dettagli della coppia; non esiste una durata massima del giro impostata a mano: il limite è dato da turno e pause dell'autista, impegni già programmati e fine della giornata. La disponibilità iniziale verifica la partenza; il calcolo considera anche gli impegni successivi già programmati e i giri in corso.

## Doppio passaggio con il traffico

Calcolato il giro, Mapbox restituisce i tempi con il traffico tipico di quel giorno
e di quell'ora. Se una consegna finisce fuori fascia, dal giro stesso si ricava di
quanto il traffico allunga i tempi di guida (rapporto tra tempi Mapbox e tempi del
calcolo, al massimo ×3); le fermate dello stesso mezzo vengono riordinate con i
tempi allungati e Mapbox viene interrogato di nuovo. Il nuovo ordine resta solo se
ha meno consegne fuori fascia (poi meno minuti di ritardo); la diagnostica
`traffic.second_pass` riporta fattore e ritardi prima e dopo. Le consegne non
cambiano mezzo. Vale anche per il giro singolo: il calcolo restituisce già orari e
pedaggi con il traffico, come dopo «Aggiorna ETA con traffico». Una chiamata per
giro se tutto è in orario, due quando serve la correzione. Nessun dato di traffico
viene salvato oltre al giro; senza fornitore configurato nulla cambia
(`services/traffic_correction.py`).

**Puntualità prima dei chilometri.** Se dopo il riordino una consegna resta fuori
fascia, il multi-mezzo rifà l'intera divisione tra i mezzi con i tempi corretti dal
traffico e le fasce chiuse prima di un margine (almeno 15 minuti, o il ritardo
osservato, al massimo 45), poi richiede Mapbox. Il nuovo piano resta se serve almeno
le stesse consegne con meno ritardi, anche con più chilometri; altrimenti resta il
primo con l'avviso. Il margine vale solo per la ricerca: orari e fasce mostrati sono
quelli veri del cliente. Il giro singolo usa lo stesso margine nel secondo passaggio.
Diagnostica: `search.on_time_replan`. Le assegnazioni manuali non vengono rifatte.

**Rientro oltre il turno.** Il traffico può spostare anche il rientro oltre la fine del
turno (`traffic.overtime_min`), che la programmazione rifiuterebbe. Vale come un
ritardo: riordino, poi nuova divisione con il turno accorciato per la sola ricerca
(sforamento più 10 minuti, al massimo 60, mai oltre metà turno). Se il rientro resta
oltre il turno, la revisione lo mostra tra gli avvisi e in «Da sistemare».

**Partenza a inizio turno.** L'orario di partenza è comune a tutti i giri, ma un
autista il cui turno inizia più tardi parte all'inizio del suo turno
(`resource_start`, chiave `departure` nel mezzo usato dalla ricerca): la ricerca, OR-Tools,
il traffico, i giri salvati e la programmazione usano quella partenza. La revisione
la indica accanto al mezzo («parte alle 09:00»).

## Miglioramento con OR-Tools

Con entrambe le strategie, dopo la ricerca e il riordino dei giri, il piano
trovato passa a **Google OR-Tools** (libreria gratuita, eseguita sul
server, nessuna chiamata esterna). OR-Tools parte da quel piano e cerca giri più
corti con le stesse regole: pause, fasce, turni, disponibilità, capacità; sponda e
ZTL incompatibili sono penalizzate. Il risultato passa dal calendario canonico e
dal riordino esatto dei giri fino a 8 fermate, poi viene confrontato con il piano
di partenza secondo la strategia: si tiene solo se migliore (prima consegne
servite, poi avvisi, poi chilometri). Un errore, un piano peggiore o la libreria
assente lasciano il piano attuale; la diagnostica `search.ortools` indica stato,
tempo e accettazione.

Tempo: 0,15 s per consegna, tra 1 s e `FLEET_ORTOOLS_SECONDS` (predefinito 10 s;
0 disattiva). Con «Distribuisci il lavoro» OR-Tools aggiunge un costo sulla durata
del giro più lungo (un minuto pesa come circa 10 km) e l'accettazione segue la
chiave bilanciata. Nel **giro singolo** oltre 8 fermate OR-Tools parte dall'ordine
trovato e la proposta resta solo se migliore secondo `solution_key`, servendo tutte
le consegne; fino a 8 fermate l'ordine è già esatto. Nei test è
spento di default e si accende in `tests/test_fleet_ortools.py`. Il confronto su 47
problemi che ha motivato la scelta è in
[ortools-full-comparison-2026-11-02.md](ortools-full-comparison-2026-11-02.md).

### Seconda proposta con PyVRP

Con entrambe le strategie e più mezzi, oltre a OR-Tools gira anche **PyVRP**
(libreria gratuita, licenza MIT, sul server; `app/services/fleet_pyvrp.py`). Parte da zero,
non dal piano trovato, usa l'orologio di lavoro di ogni autista (pause tolte, fasce come
copie alternative della consegna) e lo stesso punteggio km + ore. La sua proposta passa
dallo stesso calendario canonico e dalla stessa accettazione di OR-Tools: vince il piano
migliore, prima per consegne servite. Tempo: 0,3 s per consegna, tra 1 s e
`FLEET_PYVRP_SECONDS` (predefinito 30 s; 0 disattiva), condiviso fra costruzione del modello, tentativi e bilanciamento. Prima della costruzione si stimano gli archi: `FLEET_PYVRP_MAX_EDGES` (predefinito 250.000, minimo 1.000, tetto massimo 1.000.000) evita l'espansione eccessiva delle copie cliente con calendari diversi. Se il modello supera il limite o il tempo disponibile, resta la proposta già trovata dagli altri motori. Le singole operazioni native non sono interrompibili a metà; la scadenza impedisce di avviare ulteriori fasi. Diagnostica in `search.ortools`
(modo `pyvrp`). Con «Distribuisci il lavoro» PyVRP calcola un piano libero e poi
impone a tutti i giri una durata massima via via più stretta (fino a 5 dimezzamenti), tenendo
il limite più basso che serve ancora le stesse consegne (`search.ortools`, voce `balance`).
Su 36 problemi pubblici di Solomon il piano serve sempre tutte le consegne
e resta in media allo 0,7% dalla migliore soluzione nota: misure in
[motore-pyvrp-2026-11-05.md](motore-pyvrp-2026-11-05.md).
Sono misure storiche precedenti alle correzioni del 6 novembre: non costituiscono un nuovo benchmark della versione corretta. I dettagli delle correzioni e del collaudo sono in [GF Engine Optimizer 1.0](gf-engine-optimizer-1.0-fixes-2026-11-06.md).

## Percorso operativo

1. Scegli data, ora e deposito comuni, risorse e rientro.
2. Seleziona clienti oppure carica le fermate dalla selezione Ordini già esistente.
3. Calcola: l'anteprima mostra fermate, durata, termine del giro, chilometri, peso, colli e carburante/energia per mezzo. Le consegne non assegnate restano visibili.
4. Per spostare una consegna usa il relativo selettore e Ricalcola assegnazioni. Un movimento incompatibile non sostituisce l'anteprima valida.
5. Salva giri in bozza riserva gli ordini in una sola transazione. Lasciare consegne non assegnate richiede una scelta esplicita.
6. Programma tutti i giri aggiorna traffico/pedaggi e ricontrolla vincoli e disponibilità prima di programmare tutto il gruppo. Un conflitto lascia tutti i giri in bozza, con le stime aggiornate consultabili aprendo i singoli giri. Le notifiche agli autisti partono soltanto dopo il commit; eventuali mancati invii sono segnalati.

Le bozze si trovano nello storico. Aprire un singolo giro torna alla normale modifica su un mezzo. Dopo modifiche individuali il gruppo non può più essere programmato in blocco: si usano i comandi ordinari dei singoli giri.

## Vincoli e configurazione

Massimo 100 fermate e 10 coppie, minimo 2 coppie distinte. Un autista e un mezzo non possono essere selezionati due volte. Deposito, giorno e partenza sono comuni; i giri devono terminare nella stessa giornata. I piani salvati con il vecchio campo `max_minutes` restano validi: il campo viene ignorato.

Vincoli bloccanti: kg, colli, fasce di consegna abilitate, turni, pause, impegni esistenti e fine della giornata. Sponda e accesso ZTL sono preferenze con avviso. Le preferenze aziendali continuano a governare i vincoli dei clienti; i requisiti espliciti degli ordini vengono preservati. Peso/colli mancanti non consentono una verifica fisica completa. Turni e pause fisse dichiarate vengono considerati durante guida, scarico, attesa e rientro, come descritto in [driver-schedules.md](driver-schedules.md). Volume, pallet, transpallet e altri requisiti richiedono valutazione dell'operatore. I mezzi elettrici usano consumi e prezzi per la stima energetica; autonomia, batteria residua e soste di ricarica non sono modellate perché mancano i relativi dati.

Il costo dell'anteprima è carburante/energia, non costo complessivo del servizio. Traffico e pedaggi si applicano alla programmazione secondo i provider già configurati. Se la matrice usa stime approssimative viene segnalato. Email di acquisizione ordini resta in sviluppo, senza modifiche.

Il budget euristico per i problemi grandi è configurabile con `FLEET_MAX_CANDIDATES`: predefinito tra 10.000 e 40.000 valutazioni, in funzione delle fermate (20.000 con 50 consegne), massimo configurabile 100.000. Ogni passata condivide il proprio tetto tra costruzione complementare precedente e ricerca adattiva. Se rimangono consegne assegnabili, una fase di recupero prova anche la strategia alternativa con una propria passata e, quando serve, un modello matematico globale HiGHS/SciPy. Il recupero ha un budget temporale separato di 30 secondi, comprensivo della passata alternativa. La proposta compete sempre secondo la strategia scelta dall'operatore: il recupero non sacrifica consegne per bilanciare il lavoro o risparmiare strada. La diagnostica espone separatamente `coverage_portfolio` e `constraint_recovery`.

Il valore 0 mantiene le costruzioni iniziali e disabilita il recupero approfondito. Non tronca la ricerca globale esatta dei piccoli casi né il riordino completo dei singoli giri fino a 8 fermate: quest'ultimo viene sempre completato. Tutte le proposte usano la stessa matrice; nessuna richiesta Google/Mapbox/OSRM per combinazione. I dati diagnostici `search` della preview indicano metodo, valutazioni e limite raggiunto. Un timeout del modello non dimostra che una consegna sia impossibile; il piano valido già trovato viene conservato.

Le zone sono proposte di partenza, non confini obbligatori o nuovi dati da configurare. Le fermate possono passare a un altro giro quando migliora copertura, compatibilità o obiettivo. Le assegnazioni manuali mantengono i gruppi scelti dall'operatore e non applicano riallocazioni automatiche. Fino a 8 fermate il riordino manuale usa la priorità della strategia selezionata e la stessa gestione delle finestre dell'automatico; oltre 8 fermate resta il solutore classico.

## Persistenza e verifica

Migrazione additiva `20261013_01`: nuova tabella `fleet_plans`; nessuna cancellazione di dati. Il launcher esegue `python -m app.migrations` prima dell'avvio come di consueto.
Le anteprime sono private per azienda e operatore, versionate, valide per la conferma per 12 ore. Gli endpoint richiedono `routes.plan` oppure `routes.program`, oltre a `orders.plan` quando sono presenti ordini. Conferme/programmazioni ripetute non duplicano giri o notifiche. Al salvataggio vengono ricontrollati dati verificati, deposito, risorse e prenotazioni degli ordini.

Verifiche: `tests/test_fleet_planning.py` (motore reale, provider simulati, nessun database operativo); `tests/check_fleet_ui.py` (browser a 390, 768, 1024 e 1440 px); regressioni pianificazione ordini, routing e permessi. Le migrazioni sono provate in processi nuovi su SQLite e il DDL è compilato per PostgreSQL. I test PostgreSQL reali richiedono `TEST_POSTGRES_URL` verso un database di test e creano schemi temporanei isolati.

## Verifica della qualità della distribuzione

Il [recupero con solutore matematico](fleet-constraint-upgrade.md) documenta l'evoluzione attuale, successiva all'[aggiornamento della ricerca adattiva](fleet-adaptive-upgrade.md). I rapporti sotto conservano le misure e le politiche delle rispettive versioni precedenti.

Il [rapporto iniziale delle simulazioni multi-mezzo](fleet-simulation-results.md) documenta la versione precedente e confronta entrambe le strategie con riferimenti esatti su piccoli scenari e controlli indipendenti su casi fino a 100 fermate e 10 risorse. Pause rispettate non implicano un'assegnazione globale ottima: sono documentati casi con km evitabili e consegne non assegnate pur esistendo una ripartizione completa. Il benchmark è riproducibile con `python tests/run_fleet_simulations.py`, senza provider o database operativo.


Il [rapporto del miglioramento](fleet-search-improvements.md) riporta il confronto eseguito sul nuovo motore e i limiti rimasti.

Il miglioramento è verificabile con `python tests/run_fleet_before_after.py`: esegue gli stessi 512 input prima sullo snapshot dell'inserimento precedente e poi sul motore corrente, senza dati operativi o provider. L'artifact conserva confronti, piani, input e tempi separati. I test di regressione aggiuntivi sono in `tests/test_fleet_search.py`.

Questa modifica non richiede migrazioni né nuove chiavi API e non ricalcola giri storici o anteprime già salvate. Per aggiornare una precedente esclusione dovuta alla sponda occorre ricalcolare la suddivisione. Conferma e programmazione non applicano più il vecchio blocco, anche se il piano salvato riporta la precedente politica; gli avvisi vengono aggiornati secondo la dotazione corrente del mezzo. Traffico, pedaggi e invio notifiche usano le integrazioni esistenti.

La diagnostica `search.route_refinement` indica metodo, permutazioni valutate, miglioramento ed eventuale prova dell'ordine per ogni giro, con ambito `fixed-membership-and-resource`. `search.global_optimum_proven` continua a riferirsi all'intera assegnazione: non diventa vero perché tutti i singoli giri sono stati riordinati esattamente.

Regressioni aggiuntive: `tests/test_fleet_route_exact.py`, `tests/test_fleet_route_exact_api.py`, `tests/test_fleet_route_evaluator.py`. Il benchmark separato `python tests/run_fleet_route_exact_benchmark.py` misura 50 consegne suddivise in `6×8+2`, il caso misto `5×8+9+1` e il flusso completo con una sola matrice; non modifica il conteggio storico delle 512 simulazioni.

Risultati misurati e differenze di comportamento: [riordino completo fino a 8 fermate](fleet-route-exact-results.md).

## Recupero delle finestre e tempi manuali — 3 novembre 2026

Il recupero dopo il traffico cerca prima con le finestre originali. Solo se restano
ritardi prova un margine sulle chiusure. Un piano sostituisce il precedente solo
se il traffico è verificato, non diminuisce la copertura e riduce i ritardi;
nel giro singolo si conserva il migliore dei tentativi verificati. Il recupero
si ferma appena trova un piano puntuale. Rimangono al massimo due tentativi di
recupero aggiuntivi: non si promette una soluzione quando i vincoli non lo consentono.

Regressione riprodotta: tre consegne, due mezzi, partenza 08:00, guida 20 minuti,
scarico 5 minuti, chiusura 08:55. Ora il recupero distribuisce 2+1 consegne,
terminando gli scarichi alle 08:50 e 08:25 invece di conservare 20 minuti di ritardo.
Il margine non può mai estendere la chiusura originale, neppure quando lo scarico
è già più lungo dell'intera fascia.

`tempo_scarico_auto=false` conserva sempre il tempo manuale, incluso 10 minuti;
`true` indica una stima ricalcolabile; `null` una provenienza non specificata.
Il frontend conserva questa distinzione durante salvataggio e ricalcolo.
I tempi presenti nell'anagrafica cliente sono conservati anche se uguali a 10:
la vecchia anagrafica non distingue un valore predefinito da uno scelto manualmente.
Le stime dai colli rimangono attive per fermate senza un tempo cliente e per stime
esplicitamente automatiche. Nessuna migrazione o modifica dei giri storici.
