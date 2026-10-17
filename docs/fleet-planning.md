# Pianificazione su più mezzi

La schermata Pianificazione conserva i tre passaggi Dati del giro, Risorse e Rientro.
In Risorse si sceglie Un solo mezzo oppure Suddivisione automatica su più mezzi.
Nel secondo caso compaiono le coppie mezzo/autista disponibili e la strategia:

- Usa meno mezzi, se possibile: preferisce inserire consegne sui mezzi già utilizzati.
- Distribuisci il lavoro tra tutti i mezzi: preferisce utilizzare tutte le risorse compatibili e bilanciare la durata, comprese attese e scarico.

Le strategie sono euristiche deterministiche su una matrice stradale condivisa: non certificano un ottimo globale né l'impossibilità matematica di una diversa soluzione.
L'operatore può indicare la durata massima di ciascun giro e i prezzi energetici nei dettagli della coppia. La disponibilità iniziale verifica la partenza; il calcolo considera anche gli impegni successivi già programmati e i giri in corso.

## Percorso operativo

1. Scegli data, ora e deposito comuni, risorse e rientro.
2. Seleziona clienti oppure carica le fermate dalla selezione Ordini già esistente.
3. Calcola: l'anteprima mostra fermate, durata, termine del giro, chilometri, peso, colli e carburante/energia per mezzo. Le consegne non assegnate restano visibili.
4. Per spostare una consegna usa il relativo selettore e Ricalcola assegnazioni. Un movimento incompatibile non sostituisce l'anteprima valida.
5. Salva giri in bozza riserva gli ordini in una sola transazione. Lasciare consegne non assegnate richiede una scelta esplicita.
6. Programma tutti i giri aggiorna traffico/pedaggi e ricontrolla vincoli e disponibilità prima di programmare tutto il gruppo. Un conflitto lascia tutti i giri in bozza, con le stime aggiornate consultabili aprendo i singoli giri. Le notifiche agli autisti partono soltanto dopo il commit; eventuali mancati invii sono segnalati.

Le bozze si trovano nello storico. Aprire un singolo giro torna alla normale modifica su un mezzo. Dopo modifiche individuali il gruppo non può più essere programmato in blocco: si usano i comandi ordinari dei singoli giri.

## Vincoli della prima versione

Massimo 100 fermate e 10 coppie, minimo 2 coppie distinte. Un autista e un mezzo non possono essere selezionati due volte. Deposito, giorno e partenza sono comuni; i giri devono terminare nella stessa giornata. La durata massima iniziale è 480 minuti.

Controlli automatici: kg, colli, sponda, accesso ZTL, fasce di consegna abilitate, impegni esistenti e durata massima. Le preferenze aziendali continuano a governare i vincoli dei clienti; i requisiti espliciti degli ordini vengono preservati. Peso/colli mancanti non consentono una verifica fisica completa. Turni e pause fisse dichiarate vengono considerati durante guida, scarico, attesa e rientro, come descritto in [driver-schedules.md](driver-schedules.md). Volume, pallet, transpallet e altri requisiti richiedono valutazione dell'operatore.

Il costo dell'anteprima è carburante/energia, non costo complessivo del servizio. Traffico e pedaggi si applicano alla programmazione secondo i provider già configurati. Se la matrice usa stime approssimative viene segnalato. Email di acquisizione ordini resta in sviluppo, senza modifiche.

## Persistenza e verifica

Migrazione additiva `20261013_01`: nuova tabella `fleet_plans`; nessuna cancellazione di dati. Il launcher esegue `python -m app.migrations` prima dell'avvio come di consueto.
Le anteprime sono private per azienda e operatore, versionate, valide per la conferma per 12 ore. Gli endpoint richiedono `routes.plan` oppure `routes.program`, oltre a `orders.plan` quando sono presenti ordini. Conferme/programmazioni ripetute non duplicano giri o notifiche. Al salvataggio vengono ricontrollati dati verificati, deposito, risorse e prenotazioni degli ordini.

Verifiche: `tests/test_fleet_planning.py` (motore reale, provider simulati, nessun database operativo); `tests/check_fleet_ui.py` (browser a 390, 768, 1024 e 1440 px); regressioni pianificazione ordini, routing e permessi. Le migrazioni sono provate in processi nuovi su SQLite e il DDL è compilato per PostgreSQL. I test PostgreSQL reali richiedono `TEST_POSTGRES_URL` verso un database di test e creano schemi temporanei isolati.

## Verifica della qualità della distribuzione

Il [rapporto delle simulazioni multi-mezzo](fleet-simulation-results.md) confronta entrambe le strategie con riferimenti esatti su piccoli scenari e controlli indipendenti su casi fino a 100 fermate e 10 risorse. Pause rispettate non implicano un'assegnazione globale ottima: sono documentati casi con km evitabili e consegne non assegnate pur esistendo una ripartizione completa. Il benchmark è riproducibile con `python tests/run_fleet_simulations.py`, senza provider o database operativo.
