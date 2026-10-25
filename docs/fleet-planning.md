# Pianificazione su più mezzi

La schermata Pianificazione conserva i tre passaggi Dati del giro, Risorse e Rientro.
In Risorse si sceglie Un solo mezzo oppure Suddivisione automatica su più mezzi.
Nel secondo caso compaiono le coppie mezzo/autista disponibili e la strategia:

- Usa meno mezzi, se possibile: a parità di consegne e avvisi, minimizza i mezzi usati, poi la somma delle durate e infine i chilometri.
- Distribuisci il lavoro tra tutti i mezzi: a parità di consegne e avvisi, utilizza più risorse e minimizza la durata massima, poi lo squilibrio delle durate (somma dei quadrati), la durata totale e i chilometri.

Entrambe danno prima priorità al numero di consegne assegnate e poi alla riduzione degli avvisi per sponda/ZTL. Sponda e accesso ZTL restano preferenze: se non è possibile rispettarle il motore conserva la consegna e avvisa l'operatore; anche le assegnazioni manuali restano consentite.

La ricerca usa una sola matrice stradale condivisa. Fino a 7 fermate e 3 coppie confronta tutti i sottoinsiemi, gli ordini e le assegnazioni, compresa la possibilità di lasciare fermate non assegnate. Sceglie il migliore secondo la strategia selezionata, che non coincide necessariamente con i chilometri minimi. Oltre questi limiti usa una ricerca deterministica con budget: raggruppamenti geografici flessibili, riordino, trasferimenti e scambi tra mezzi. Mantiene il piano dell'inserimento precedente come soglia di qualità e non certifica un ottimo globale sui casi grandi.
Dopo la suddivisione, ogni giro fino a **8 fermate** riceve un riordino completo su tutti gli ordini possibili (`8! = 40.320`). La soglia riguarda il singolo giro: vale anche con 50 o 100 consegne totali. Consegne e mezzo assegnati rimangono fissi; si minimizza la durata, poi i km, coerentemente con la strategia della flotta a composizione fissa. Le pause e le finestre continuano a essere verificate per ogni ordine.

La matrice stradale globale è già completa e viene riutilizzata: non si richiede una nuova matrice o un provider per ogni permutazione. Un valutatore preparato riusa gli stessi selettori di finestre e l'aritmetica delle pause del valutatore canonico. Il vincitore viene verificato e poi ricostruito con tutti i dettagli ETA. La verifica canonica del vincitore non sostituisce i test di equivalenza esaustivi sul valutatore preparato.

Per i giri oltre 8 fermate resta l'ordine trovato dall'euristica attuale. Non si forza la creazione di più giri soltanto per rientrare nella soglia. L'ottimo dell'ordine di un gruppo assegnato non certifica l'ottimo della suddivisione dell'intera flotta; la prova globale fino a 7 fermate e 3 risorse rimane distinta e viene riutilizzata per evitare lavoro ridondante.

L'operatore può indicare i prezzi energetici nei dettagli della coppia; non esiste una durata massima del giro impostata a mano: il limite è dato da turno e pause dell'autista, impegni già programmati e fine della giornata. La disponibilità iniziale verifica la partenza; il calcolo considera anche gli impegni successivi già programmati e i giri in corso.

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

Vincoli bloccanti: kg, colli, fasce di consegna abilitate, turni, pause, impegni esistenti e fine della giornata. Preferenze con avviso: sponda e accesso ZTL. Le preferenze aziendali continuano a governare i vincoli dei clienti; i requisiti espliciti degli ordini vengono preservati. Peso/colli mancanti non consentono una verifica fisica completa. Turni e pause fisse dichiarate vengono considerati durante guida, scarico, attesa e rientro, come descritto in [driver-schedules.md](driver-schedules.md). Volume, pallet, transpallet e altri requisiti richiedono valutazione dell'operatore.

Il costo dell'anteprima è carburante/energia, non costo complessivo del servizio. Traffico e pedaggi si applicano alla programmazione secondo i provider già configurati. Se la matrice usa stime approssimative viene segnalato. Email di acquisizione ordini resta in sviluppo, senza modifiche.

Il budget aggiuntivo per i problemi grandi è configurabile con `FLEET_MAX_CANDIDATES`: predefinito tra 5.000 e 20.000 valutazioni, in funzione delle fermate, massimo configurabile 100.000. Il valore 0 mantiene l'inserimento iniziale per l'assegnazione euristica. Non tronca la ricerca globale esatta dei piccoli casi né il riordino completo dei singoli giri fino a 8 fermate: quest'ultimo viene sempre completato. Tutte le proposte usano la stessa matrice; nessuna richiesta Google/Mapbox/OSRM per combinazione. I dati diagnostici `search` della preview indicano metodo, valutazioni e limite raggiunto.

Le zone sono proposte di partenza, non confini obbligatori o nuovi dati da configurare. Le fermate possono passare a un altro giro quando migliora copertura, compatibilità o obiettivo. Le assegnazioni manuali mantengono i gruppi scelti dall'operatore e non applicano riallocazioni automatiche. Fino a 8 fermate il riordino manuale usa ora la stessa priorità della flotta (durata, poi km) e la stessa gestione delle finestre dell'automatico; oltre 8 fermate resta il solutore classico. Questa è una differenza rispetto al precedente riordino manuale, che sotto soglia usava distanza prima della durata.

## Persistenza e verifica

Migrazione additiva `20261013_01`: nuova tabella `fleet_plans`; nessuna cancellazione di dati. Il launcher esegue `python -m app.migrations` prima dell'avvio come di consueto.
Le anteprime sono private per azienda e operatore, versionate, valide per la conferma per 12 ore. Gli endpoint richiedono `routes.plan` oppure `routes.program`, oltre a `orders.plan` quando sono presenti ordini. Conferme/programmazioni ripetute non duplicano giri o notifiche. Al salvataggio vengono ricontrollati dati verificati, deposito, risorse e prenotazioni degli ordini.

Verifiche: `tests/test_fleet_planning.py` (motore reale, provider simulati, nessun database operativo); `tests/check_fleet_ui.py` (browser a 390, 768, 1024 e 1440 px); regressioni pianificazione ordini, routing e permessi. Le migrazioni sono provate in processi nuovi su SQLite e il DDL è compilato per PostgreSQL. I test PostgreSQL reali richiedono `TEST_POSTGRES_URL` verso un database di test e creano schemi temporanei isolati.

## Verifica della qualità della distribuzione

Il [rapporto iniziale delle simulazioni multi-mezzo](fleet-simulation-results.md) documenta la versione precedente e confronta entrambe le strategie con riferimenti esatti su piccoli scenari e controlli indipendenti su casi fino a 100 fermate e 10 risorse. Pause rispettate non implicano un'assegnazione globale ottima: sono documentati casi con km evitabili e consegne non assegnate pur esistendo una ripartizione completa. Il benchmark è riproducibile con `python tests/run_fleet_simulations.py`, senza provider o database operativo.


Il [rapporto del miglioramento](fleet-search-improvements.md) riporta il confronto eseguito sul nuovo motore e i limiti rimasti.

Il miglioramento è verificabile con `python tests/run_fleet_before_after.py`: esegue gli stessi 512 input prima sullo snapshot dell'inserimento precedente e poi sul motore corrente, senza dati operativi o provider. L'artifact conserva confronti, piani, input e tempi separati. I test di regressione aggiuntivi sono in `tests/test_fleet_search.py`.

Questa modifica non richiede migrazioni né nuove chiavi API e non ricalcola giri storici o anteprime già salvate. Per ottenere la nuova distribuzione si richiede un nuovo calcolo. Le funzioni di conferma, programmazione, traffico, pedaggi e invio notifiche restano quelle esistenti.

La diagnostica `search.route_refinement` indica metodo, permutazioni valutate, miglioramento ed eventuale prova dell'ordine per ogni giro, con ambito `fixed-membership-and-resource`. `search.global_optimum_proven` continua a riferirsi all'intera assegnazione: non diventa vero perché tutti i singoli giri sono stati riordinati esattamente.

Regressioni aggiuntive: `tests/test_fleet_route_exact.py`, `tests/test_fleet_route_exact_api.py`, `tests/test_fleet_route_evaluator.py`. Il benchmark separato `python tests/run_fleet_route_exact_benchmark.py` misura 50 consegne suddivise in `6×8+2`, il caso misto `5×8+9+1` e il flusso completo con una sola matrice; non modifica il conteggio storico delle 512 simulazioni.

Risultati misurati e differenze di comportamento: [riordino completo fino a 8 fermate](fleet-route-exact-results.md).
