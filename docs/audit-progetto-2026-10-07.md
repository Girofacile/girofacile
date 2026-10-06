# Audit del progetto — 7 ottobre 2026

## Esito e perimetro

Base analizzata: `e144d41`, coincidente con `origin/main` all'inizio del lavoro.
Sono stati trovati e corretti difetti applicativi e difetti della suite di test.
Il progetto **non può essere dichiarato privo di errori né pronto al rilascio
pubblico sulla sola base di questo audit**: le verifiche locali hanno un
perimetro preciso e restano i punti aperti elencati sotto.

Inventario automatico: **75 file Python applicativi, 206 dichiarazioni di
endpoint, 18 pagine HTML, 19 file JavaScript e 29 script complessivi includendo
quelli inline**. L'inventario [JSON](audit-inventory-2026-10-07.json) riporta
percorso, riga, metodo, funzione e dipendenze dichiarate di ogni endpoint.
Le dichiarazioni includono pagine e API; non equivalgono a 206 flussi collaudati
singolarmente. Le dipendenze estratte non costituiscono una prova automatica
dell'effettiva autorizzazione.

Il controllo combina analisi statica dell'intero inventario, revisione mirata
dei flussi critici, suite automatizzate e prove browser con dati simulati.
Non è una revisione manuale riga per riga di ogni file né un penetration test.
Database aziendale, allegati locali e file `.env` non sono stati modificati.

## Errori riprodotti e corretti

| Priorità | Problema e riproduzione | Correzione e copertura |
|---|---|---|
| P1 | Importare un cliente esistente con lo stesso codice e un indirizzo nuovo conservava latitudine/longitudine e stato verificato del vecchio indirizzo, sia da azienda sia da agente. Il cliente poteva essere pianificato verso il punto sbagliato. | Invalidazione di coordinate, metadati Google e cache distanze per l'indirizzo cambiato, senza commit intermedi durante l'importazione. Test per entrambi i portali, con indirizzo cambiato e invariato. |
| P1 | Cambiare insieme indirizzo e fasce orarie del cliente provocava un commit dalla cache prima della conversione delle stringhe in oggetti `time`; riprodotto con errore SQLAlchemy/SQLite. | Conversione delle fasce prima dell'invalidazione della cache. Test API di aggiornamento e rilettura dei valori salvati. |
| P1 | Marca, modello, anno, cilindrata, potenza, classe Euro, carrozzeria e provenienza lookup non sopravvivevano al salvataggio: mancavano nello schema API e nella mappatura ORM. | Campi collegati alle colonne già presenti nella migrazione legacy, con test creazione e rilettura. Non è stata inventata una nuova migrazione per colonne già previste. I valori scartati in passato non sono recuperati automaticamente. |
| P2 | Mezzo e autista impegnati in un giro iniziato ieri risultavano disponibili nelle anagrafiche. | La disponibilità considera tutti i giri `in_corso`, anche oltre la mezzanotte. Il controllo di conflitto all'avvio del giro resta distinto. |
| P2 | Nomi nulli causavano errori di integrità in alcune anagrafiche; stringhe vuote o di soli spazi venivano accettate. | Validazione API dei nomi di clienti, depositi, mezzi, agenti e autisti; limiti coerenti con le colonne. Richieste invalide restituiscono 422. |
| P1, CI | Sei test UI fallivano perché le fixture non caricavano `gfRouteEnergyMetric`; un settimo cercava l'etichetta mobile dei costi API nell'HTML invece che nel modulo che la genera. | Caricamento dell'helper reale e verifica dell'etichetta nel modulo corretto, mantenendo le asserzioni funzionali. |
| P1, CI | Il test browser gestionale cercava di premere “Nuovo deposito” dietro la modale di modifica aperta e terminava in timeout. | Il test chiude la modale tramite “Annulla”, apre quella nuova, verifica il reset e la richiude prima di navigare. |

Regressioni aggiunte in `tests/test_project_audit.py`: **19 casi superati**.
I difetti applicativi sono stati riprodotti prima delle rispettive correzioni.

## Copertura delle aree

| Area | Controlli svolti | Limite della conclusione |
|---|---|---|
| Landing, login, setup autista/agente, reset e pagine legali | Inventario HTML, sintassi script, asset e ID; test autenticazione, token, revoca e reset | Nessun collaudo email reale o verifica giuridica dei testi |
| Dashboard e profilo azienda | Browser desktop/tablet/mobile, navigazione, menu, annullamento modifiche e notifiche | API simulate nei test browser |
| Clienti e agenti | CRUD, isolamento, filtri, griglia/lista, dettaglio, modale, assegnazioni, import CSV/XLSX e regressioni indirizzo | Non tutte le combinazioni di file e input sono coperte |
| Depositi | CRUD, default, timestamp, isolamento, modale, lista/griglia e navigazione mobile | Concorrenza tra modifiche del deposito predefinito da approfondire |
| Mezzi e autisti | Piani/quote, bonus elettrico, moduli, reset, dati tecnici, inviti e disponibilità oltre mezzanotte | Lookup e ricezione inviti non collaudati con provider reali |
| Pianificazione e anteprima | Test ottimizzatore, capacità, finestre, priorità, fermate occasionali, selezioni, avvisi e azioni UI | Benchmark sintetici non dimostrano prestazioni su tutti i giri reali |
| Programmazione, esecuzione, completamento | Transizioni, retry, idempotenza, conflitti risorse, consegne mancate, annullamento e storico | Nessun turno operativo reale su dispositivi fisici |
| Portali autista/operatore e prove di consegna | Test autorizzazioni, firma/foto/PDF, errori storage, concorrenza e GPS browser | Storage simulato; bucket effettivo e recupero allegati non collaudati |
| Tracking cliente | Layout 320/390/768/1440 px, polling, completamento, link invalidi, indisponibilità, copia e revoca | Nessuna prova di carico sul servizio pubblico |
| GPS | Ciclo autista/operatore, permesso negato, background, riconnessione, posizione recente/obsoleta/offline e layout | Browser simulato; comportamento a schermo bloccato su iPhone/Android non certificato |
| Storico, report ed export | Paginazione, ricerca, filtri, CSV e test delle metriche | Distanze e costi sono stime/snapshot; non misure di odometro o fatture reali |
| Chat, assistenza, impostazioni e notifiche | Test esistenti, controlli tenant, permessi e interazioni gestionali | SMTP e assistenza AI non chiamati con account produttivi |
| Super Admin, costi API e database | Test permessi collaboratori, mascheramento segreti, export, configurazione e UI costi | Non è stato cliccato manualmente ogni controllo amministrativo |
| Billing | Suite con provider simulato, quote e stati abbonamento | Incassi reali disabilitati; nessun pagamento effettuato |
| Infrastruttura | PostgreSQL isolato, migrazioni/concorrenza/backup della suite, controllo Compose e build Docker | Non verifica lo stato del server produttivo o il ripristino del bucket |

## Risultati dei controlli

- Sintassi: 75 moduli Python analizzati e 29 script JavaScript compilati senza
  errori sintattici. Nessun ID HTML duplicato o asset locale mancante rilevato;
  la favicon è risolta tramite l'endpoint `/favicon.ico`.
- JavaScript: **72 test passati, zero falliti**.
- Regressioni applicative finali: **19 passate**. Suite mirata clienti/agenti/
  operatività dopo le correzioni import: **76 passate**; successivamente aggiunti
  i due casi di conservazione dell'indirizzo invariato, compresi nei 19 finali.
- Gestionale browser: 18 viste interne a 390/768/1440 px; **27 interazioni**,
  zero errori script, zero overflow, 12 confronti delle pagine protette passati.
- Mobilità elettrica: layout verificati a 320/768/1440 px.
- Tracking e GPS: controlli browser superati a 320/390/768/1440 px.
- `pip check`: nessuna incompatibilità dichiarata tra dipendenze installate.
  Questo non è uno scan delle vulnerabilità note.
- Suite completa con PostgreSQL 16 isolato: **635 passati, 5 saltati, zero
  fallimenti**, 970,81 secondi. Sono inclusi migrazioni, concorrenza e
  backup/ripristino effettivo PostgreSQL. I cinque skip riguardano esclusivamente
  OR-Tools, assente nell'ambiente principale: **tutti e cinque sono poi passati**
  nell'ambiente benchmark in 5,61 secondi. Le correzioni import successive all'avvio della suite sono state
  verificate con i 76 test mirati e le 19 regressioni finali sopra indicati.
- Build Docker finale riuscita; **19 regressioni passate anche nel container
  Linux**. Verificata presenza di script backup, `pg_dump` e `pg_restore` 16.
- Compose valido con credenziale fittizia di verifica. Il `.env` locale non
  fornisce `POSTGRES_PASSWORD` al comando Compose: l'avvio con quella
  configurazione resta bloccato finché il valore non viene configurato.
- OSRM locale: richiesta di percorso con risposta HTTP 200, codice `Ok`, un
  percorso restituito. Non equivale a validazione dell'intero dataset stradale.
- Backend: 19 richieste ai principali punti di ingresso HTML/favicon restituite
  con HTTP 200, senza utilizzare il database applicativo.

Le prime esecuzioni hanno evidenziato anche problemi dell'ambiente di collaudo:
ACL della directory temporanea Windows e Chromium Playwright non installato.
I test sono stati rieseguiti con directory temporanee dedicate e Chrome locale.
La prima suite Python interrotta per questi problemi non viene conteggiata
come verifica riuscita. I log e gli screenshot sono in `test-results/`, esclusa
dal versionamento.

## Punti ancora aperti

1. **P1 — Avvio production con configurazione debole.** `app/core/config.py`
   mantiene fallback `admin123` e `dev-secret-change-me`; non esiste un blocco
   centralizzato di avvio per segreti mancanti/default. Anche `COOKIE_SECURE`
   è sovrascrivibile a falso. Serve una validazione production con test di
   rifiuto all'avvio. Questo è un rischio del codice, non la prova che il server
   reale utilizzi tali valori; non sono state lette o pubblicate credenziali.
2. **P1 per vendita self-service — Billing live indisponibile.**
   `billing_state()` restituisce `live_enabled=False` e il checkout è riservato
   agli utenti di test. Occorre completare il percorso commerciale e verificare
   webhook, rinnovi e riconciliazione prima di promettere incassi autonomi.
3. **P2 — Validazione numerica e date incompleta.** È ancora possibile costruire
   `VehicleIn` con capacità negativa e `CustomerIn` con tempo di scarico
   negativo; le route di salvataggio non aggiungono una validazione generale.
   Date/orari malformati possono essere trasformati in `None` dagli helper.
   Estendere i vincoli API e import senza confondere lo zero valido con campo
   assente. La validazione peso/colli del motore è già presente e distinta.
4. **P1 condizionale — Fallback legacy mezzi permissivo.** Nel fallback di
   `list_vehicles`, il filtro aziendale viene applicato solo se la colonna
   `user_id` è presente. Uno schema legacy incoerente deve essere rifiutato,
   non letto senza filtro. Lo startup normale richiede migrazioni correnti;
   non è stata dimostrata un'esposizione sul database reale.
5. **P1 operativo — Configurazione rete da verificare.** Compose pubblica app
   e OSRM su tutte le interfacce e abilita per default la fiducia negli header
   proxy. La sicurezza effettiva dipende da firewall e reverse proxy. Il limite
   login è in memoria per processo; signup/reset non fanno parte della stessa
   lista di endpoint limitati. Verificare il perimetro e limiti condivisi.
6. **P1 operativo — Collaudo delle integrazioni reali incompleto.** Restano da
   verificare SMTP, storage privato e restore allegati, Stripe sandbox/live,
   Google/geocodifica/traffico/pedaggi, provider targa, servizi AI e backup
   schedulati nell'ambiente di rilascio. I test simulati non li certificano.
7. **P2 — Scalabilità e copertura.** Diverse liste/report caricano insiemi
   completi e lo stato delle anagrafiche comporta query aggiuntive per riga.
   Servono misure con volumi reali. Non sono state misurate capacità di flotta,
   latenza p95, carico misto o affidabilità GPS sui dispositivi fisici.
8. **P2 — Dipendenze e manutenzione.** Numerosi warning su `datetime.utcnow()`;
   dipendenze transitive non bloccate da lockfile. Serve una scansione dedicata
   delle vulnerabilità e una strategia di aggiornamento: `pip check` e la build
   non sostituiscono questi controlli.

Priorità successiva: validazione production e isolamento legacy, completamento
dei vincoli input, collaudo end-to-end contro backend di staging e servizi reali,
poi carico e prova di recupero DB + allegati. La roadmap V1 resta un riferimento
di lavoro; i suoi conteggi del 6 ottobre sono storici e non sostituiscono gli
esiti di questo audit.
