# GiroFacile — roadmap di chiusura V1

Analisi del 6 ottobre 2026 sul commit `69c8d61`. Questo documento pianifica il
rilascio: non attesta che le attività elencate siano già completate.

## Obiettivo e giudizio sullo stato attuale

La V1 deve consentire a un'azienda di configurarsi, pianificare un giro,
assegnarlo, eseguirlo da telefono, consultare esiti e prove di consegna e
ricevere assistenza, con dati recuperabili e condizioni commerciali chiare.

Il progetto ha già una base funzionale consistente. Il lavoro prioritario è
chiudere e verificare il prodotto esistente, non aggiungere altre aree o
continuare un restyling senza una data di congelamento.

**Non considero ancora dimostrata la prontezza per un'apertura pubblica
self-service a clienti paganti.** Sono presenti blocchi verificabili nei
test e nel billing, oltre a verifiche operative non documentate per
l'ambiente reale. Questo non significa che tutte le funzionalità siano rotte.

### Evidenze verificate

| Area | Evidenza nel repository | Conseguenza per V1 |
|---|---|---|
| Funzioni centrali | Anagrafiche, importazione, pianificazione, programmazione, portali autista/operatore, esiti, chat, storico e report presenti | Collaudare un flusso intero, evitando nuove implementazioni parallele |
| Frontend | Nuova esecuzione: 66 test, 59 passati, 7 falliti | Nessun rilascio candidato finché la suite obbligatoria non è verde |
| Cause frontend | Sei fallimenti per `gfRouteEnergyMetric` non caricato nei contesti isolati dei test; uno sull'aspettativa `data-label="Avanzamento"` dell'area costi API | Distinguere fixture obsolete da errori UI; non eliminare le asserzioni per ottenere il verde |
| Backend mirato | 77 test: 76 passati, un 503 nel retry consegna con log storage non disponibile; il test isolato passa con `OBJECT_STORAGE_ENABLED=false` | Rendere i test indipendenti dalla configurazione locale e coprire esplicitamente storage attivo/disattivo/guasto |
| Sicurezza | Sessioni scadenti e revocabili, permessi e controlli tenant presenti; `config.py` conserva fallback di sviluppo per password e segreto | Aggiungere una validazione che impedisca l'avvio production con valori mancanti/deboli/default; non è una prova che il server reale usi questi valori |
| Billing | `stripe_client` accetta solo `test`; `live_enabled` è falso | L'acquisto autonomo reale non è ancora disponibile |
| Documenti POD | Bucket privato e URL temporanei previsti, test con storage simulato | Collaudo del bucket effettivo, recupero allegati e politica di conservazione obbligatori se attivati |
| GPS | Ultima posizione, polling e popup presenti; il browser sospende in background | Vendere monitoraggio con portale attivo, non localizzazione continua garantita |
| Routing | Benchmark sintetici e limiti di ricerca documentati; `optimizer-real-fixtures.md` dichiara zero giri reali | Raccogliere e validare campioni reali prima di promettere prestazioni o risparmi |
| Infrastruttura | Docker, PostgreSQL, OSRM, migrazioni e timer backup presenti | L'esistenza dei file non dimostra servizi attivi, allarmi o restore riuscito sul server reale |
| Struttura | `core.js` 5.284 righe; `routes.py` 928; `auth.py` 739; nuovi moduli UI decorano rendering preesistenti | Ridurre il rischio di regressione con confini chiari e test; evitare una riscrittura totale prima del lancio |

Non sono stati controllati credenziali, database produttivo, stato effettivo del
server, pannelli dei provider o l'esito corrente di GitHub Actions. In questa
analisi non è stata rieseguita l'intera suite Python né una prova di carico.
I risultati storici nei documenti non sostituiscono il collaudo del candidato V1.

## Perimetro da congelare

**Incluso:** aziende con consegne locali, gestione clienti/depositi/mezzi/autisti,
importazione dati, giro con fermate e finestre, anteprima, programmazione,
esecuzione, esiti, storico ed esportazione. Tracking cliente, GPS, firma/foto/PDF,
chat, agenti e report entrano con i limiti di piano e le configurazioni previste,
soltanto dopo i rispettivi collaudi.

**Rimandato:** GPS continuo in background tramite app nativa, funzionamento
offline completo, nuovi settori verticali, nuove integrazioni e-commerce,
nuove funzioni AI, riscrittura del frontend e ottimizzazione per flotte di
dimensioni non ancora misurate. Le API legacy vanno inventariate e protette;
non vanno cancellate senza una decisione sulla compatibilità.

La soglia massima di fermate, le aziende simultanee supportate e le funzioni
opzionali pubblicizzate saranno fissate dopo le misure della fase 4.

## Sequenza di lavoro

Priorità: **P0** impedisce il rilascio della funzione coinvolta; **P1** deve
essere chiusa prima della disponibilità generale; **P2** può passare a V1.1.
Ogni attività si chiude con commit, verifica ripetibile e risultato registrato.

### 0 — Contratto della V1 e inventario (P0)

Responsabili: prodotto e referente tecnico. Dipendenze: nessuna.

- [ ] V1-01: inventariare ogni pagina, API e ruolo; classificare attiva,
  opzionale, amministrativa o legacy e indicare chi la può usare.
- [ ] V1-02: congelare funzioni e flusso principale; allineare landing,
  piani e istruzioni ai limiti reali di GPS, ETA, pedaggi e prove di consegna.
- [ ] V1-03: scegliere il percorso commerciale. Raccomandazione: prima pilota
  assistito, poi V1 pubblica con billing reale collaudato. Un lancio con
  contratti/attivazioni manuali è possibile solo definendo gestione pagamenti,
  scadenze e assistenza e rimuovendo le promesse di acquisto automatico.

**Uscita:** elenco firmato delle funzioni V1, esclusioni, piani e clienti iniziali.

### 1 — Ripristinare una base di verifica affidabile (P0)

Responsabile: sviluppo. Dipendenze: fase 0.

- [ ] V1-04: correggere i sette test frontend; includere l'helper energetico
  reale nelle fixture e verificare il comportamento mobile della tabella costi.
- [ ] V1-05: isolare configurazione e dipendenze dei test. Nessun `.env`
  personale deve attivare un servizio reale; storage falso esplicito, SMTP
  intercettato e database temporanei. Una chiamata esterna inattesa deve fallire.
- [ ] V1-06: eseguire l'intera pipeline su Linux e PostgreSQL, inclusi
  migrazioni, concorrenza, backup/restore, build e browser. Classificare gli skip:
  i controlli critici PostgreSQL non possono essere saltati nel rilascio.
- [ ] V1-07: aggiungere test di browser completi contro il backend di staging,
  oltre a quelli con API simulate; conservare video/log dei fallimenti.

**Uscita:** zero fallimenti nei controlli obbligatori sullo stesso SHA; nessuno
skip critico e nessuna dipendenza non dichiarata dall'ambiente dello sviluppatore.

### 2 — Chiudere sicurezza e isolamento di produzione (P0)

Responsabili: sviluppo e infrastruttura. Dipendenze: fase 1.

- [ ] V1-08: bloccare lo startup production con segreti/credenziali di sviluppo,
  cookie non sicuri o configurazioni richieste incomplete. Definire bootstrap
  amministratore e rotazione dei segreti con gli effetti su sessioni e link.
- [ ] V1-09: verificare HTTPS, proxy fidati e accesso di rete. Il Compose espone
  app e OSRM: impedire l'accesso diretto non previsto. Non fidarsi di header
  inoltrati da client esterni. Configurare limiti condivisi al proxy dove servono;
  quelli applicativi di login/tracking sono attualmente per processo.
- [ ] V1-10: verificare richieste che modificano dati, protezione cross-site,
  XSS nei campi liberi/importati, upload, esportazioni e intestazioni browser.
  La CSP del tracking pubblico non equivale a protezione di tutta la dashboard.
- [ ] V1-11: matrice autorizzazioni azienda A/B, autista assegnato/non assegnato,
  agente, collaboratore admin, token operatore e link cliente. Coprire anche
  documenti, foto, revoca, scadenza, logout e reset password.
- [ ] V1-12: scansione dipendenze e segreti, revisione degli endpoint admin più
  sensibili; accesso amministrativo ristretto e secondo fattore tramite soluzione
  applicativa o protezione del perimetro, da scegliere prima dell'apertura.

**Uscita:** nessuna vulnerabilità critica/alta irrisolta nel perimetro di lancio;
test negativi di accesso ai dati di un'altra azienda tutti superati.

### 3 — Chiudere il ciclo operativo completo (P0)

Responsabili: sviluppo e collaudatore operativo. Dipendenze: fasi 1–2.

- [ ] V1-13: nuova azienda → profilo → deposito → mezzo/autista → importazione
  clienti → geocodifica → bozza → anteprima → programmazione → invito/accesso
  autista → avvio → consegna/mancata → chiusura → storico/report/export.
- [ ] V1-14: ripetere con doppio clic, retry, due dispositivi simultanei, giro
  annullato, quota terminata, mezzanotte/cambio ora, cliente occasionale,
  autista archiviato e documento già acquisito. Nessun doppio consumo o perdita dati.
- [ ] V1-15: firme/foto/PDF con storage reale dedicato al collaudo; timeout,
  bucket irraggiungibile e URL scaduti. Conservare quanto inserito durante un
  errore; rendere esplicita la mancata persistenza dopo refresh se non implementata.
- [ ] V1-16: su Android e iPhone reali verificare permessi GPS, passaggio a
  Google Maps, blocco schermo, rete persa e ritorno online. Non mostrare un dato
  vecchio come attuale; le consegne devono restare utilizzabili senza GPS.
- [ ] V1-17: tracking condiviso, revoca, scadenza e isolamento; chat/notifiche;
  reset e inviti con SMTP di staging, verificando ricezione e messaggi di errore.

**Uscita:** il flusso è completabile senza modifiche manuali al DB e senza
intervento dello sviluppatore. Tutte le anomalie bloccanti hanno regressioni.

### 4 — Validare pianificazione, report e capacità (P0/P1)

Responsabili: sviluppo e referente operativo. Dipendenze: fase 3 per il campo;
la raccolta dati può iniziare dopo la fase 0.

- [ ] V1-18: raccogliere 15–20 giri anonimizzati e separare sviluppo/validazione
  prima del tuning, come previsto dalla documentazione. Confrontare ordine
  operatore, fattibilità, km, tempi, attese e casi impossibili; registrare i limiti.
- [ ] V1-19: misurare latenza e consumi sul server previsto, con matrici fredde
  e in cache, timeout OSRM/provider e richieste simultanee. Provare dimensioni
  crescenti, ad esempio 10/30/50 fermate; pubblicare solo il limite validato.
- [ ] V1-20: carico misto di pianificazione, autisti, polling tracking/GPS,
  chat, report e upload. Stabilire budget API, allarmi di spesa, limiti e fallback.
  Proposta iniziale da validare: 10 pianificazioni concorrenti, 50 autisti e
  100 lettori tracking; non è una capacità già dimostrata.
- [ ] V1-21: riconciliare un campione di report con giri ed esiti: consegnate,
  mancate/non gestite, costi stimati, pedaggi parziali, energia elettrica e ore
  storiche. La ripartizione per fermata va spiegata, non presentata come costo reale.

**Uscita:** dossier ripetibile con dataset, hardware, latenza p95, errori,
limiti supportati e costi attesi; nessuna promessa commerciale non misurata.

### 5 — Rendere il servizio gestibile e recuperabile (P0)

Responsabile: infrastruttura, con sviluppo. Dipendenze: fase 2; avviabile insieme alla 3.

- [ ] V1-22: staging separato e produzione riproducibile; inventario segreti,
  domini, certificati, PostgreSQL, OSRM, storage e SMTP. Verificare autorizzazioni
  e capacità del servizio mappe utilizzato, senza assumere capacità illimitata.
- [ ] V1-23: endpoint di salute/readiness dell'app, controllo schema e dipendenze,
  monitor esterno, log con ID richiesta e allarmi su errori, code/timeout,
  spazio disco, mancati backup, storage e scadenze certificati.
- [ ] V1-24: eseguire e monitorare backup DB e copia recuperabile degli allegati
  fuori dal solo disco applicativo; adattare i path dei timer systemd al deploy
  reale. Pianificare cleanup GPS/cache e riconciliazione POD con precauzioni restore.
- [ ] V1-25: prova documentata di ripristino DB **e bucket** in ambiente vuoto;
  verificare riferimenti, foto, firme e PDF. Proporre RPO massimo 1 ora e RTO
  massimo 4 ore, da approvare e misurare; un dump giornaliero da solo non soddisfa
  quel RPO. Se si scelgono valori diversi, renderli espliciti prima dei contratti.
- [ ] V1-26: procedura deploy, migrazione unica prima dei worker, controlli dopo
  il deploy e rollback applicativo compatibile con lo schema. Non presumere
  che tornare al vecchio container annulli una migrazione o recuperi i dati.

**Uscita:** un secondo operatore sa ripristinare il servizio seguendo il manuale;
allarmi ricevuti tramite prova, non soltanto impostazioni compilate.

### 6 — Chiudere il percorso commerciale (P0 per V1 self-service)

Responsabili: sviluppo, titolare prodotto e consulente amministrativo.
Dipendenze: fasi 1–2 e ambiente della fase 5.

- [ ] V1-27: completare collaudo sandbox su acquisto, rinnovo, pagamento fallito,
  tolleranza, disdetta, upgrade/downgrade, quote e accesso ai dati dopo scadenza.
- [ ] V1-28: introdurre modalità live esplicita e separazione ambienti/eventi;
  firme webhook, replay, duplicati, ordine degli eventi e recupero dei webhook
  mancanti. Non basta impostare una chiave live nel codice attuale.
- [ ] V1-29: allineare prezzi, condizioni fiscali, documenti di pagamento e
  fatturazione alla gestione scelta; configurare e testare i promemoria schedulati.
- [ ] V1-30: verifica controllata del percorso reale autorizzata dal titolare,
  con riconciliazione contabile. Il ritorno dalla pagina checkout non deve
  concedere diritti prima della conferma autorevole del pagamento.

**Uscita:** acquisto e intero ciclo di abbonamento collaudati. In alternativa,
per il solo lancio assistito, procedura manuale completa e interfaccia coerente:
nessun pulsante di acquisto che porti a una funzione disabilitata.

### 7 — Rifinitura V1, documentazione e gestione dati (P1)

Responsabili: prodotto, sviluppo, assistenza; revisione privacy/contrattuale dedicata.
Dipendenze: fase 0; verifica finale dopo le fasi 3–6.

- [ ] V1-31: collaudo uniforme di tutte le pagine attive e dei popup: caricamento,
  errori, liste vuote, testi lunghi, filtri, tastiera, focus, contrasto e mobile.
  Evitare altri redesign estesi; correggere incoerenze che ostacolano l'operatività.
- [ ] V1-32: estrarre soltanto logiche condivise ad alto rischio, fissare contratti
  di rendering e stato; ridurre sovrapposizioni CSS e manipolazioni DOM fragili.
  Non rendere una migrazione completa a un framework prerequisito della V1.
- [ ] V1-33: guida rapida azienda/autista, limiti noti, diagnostica accessibile,
  contatto assistenza, gestione segnalazioni e tempi di risposta concordati.
- [ ] V1-34: verificare testi contrattuali e informativi rispetto a GPS, POD e
  fornitori effettivi; definire conservazione, accesso, export, cancellazione,
  gestione richieste sui dati e incidenti. La presenza delle pagine legali non
  equivale a una verifica del contenuto o della conformità del servizio reale.
- [ ] V1-35: allineare numero di release, changelog, manuali e messaggi di prodotto:
  la dicitura commerciale V1 deve essere distinta dalle versioni tecniche storiche.

**Uscita:** nessuna funzione pubblicizzata ma indisponibile senza spiegazione;
un'azienda nuova sa configurare ed eseguire il primo giro con la guida.

### 8 — Pilota assistito e candidato di rilascio (P0)

Responsabili: prodotto, 2–3 aziende pilota, sviluppo e assistenza.
Dipendenze: 1–5 e 7; billing live non necessario per un pilota senza acquisto automatico.

- [ ] V1-36: almeno due settimane operative con giri veri e dispositivi diversi,
  dati autorizzati e assistenza tracciata. Raccogliere blocchi, tempi, errori,
  differenze tra pianificazione ed esecuzione e qualità percepita dagli autisti.
- [ ] V1-37: triage giornaliero; correggere perdita dati, isolamento, blocchi di
  lavoro, accessi e problemi economici prima dei dettagli cosmetici.
- [ ] V1-38: congelare un candidato; ripetere regressioni, restore e verifica
  dei flussi dopo le ultime correzioni. Se cambia una funzione critica, riaprire
  il relativo collaudo e la finestra di osservazione.

**Uscita:** zero bug P0/P1 aperti nel perimetro promesso e cinque giorni operativi
consecutivi senza incidenti bloccanti sul candidato, con giri effettivamente eseguiti.

### 9 — Pubblicazione V1 e presidio iniziale (P0)

Responsabili: titolare prodotto e referente rilascio. Dipendenze: tutti i gate applicabili.

- [ ] V1-39: associare release/tag a SHA verificato, backup prima del deploy,
  checklist go/no-go e contatto reperibile durante il rilascio.
- [ ] V1-40: pubblicare gradualmente, eseguire smoke test produzione con utenza
  dedicata, controllare login, pianificazione, esito, documento, tracking e billing
  applicabile. Verificare allarmi e mantenere pronto il rollback.
- [ ] V1-41: presidio della prima settimana con errori, disponibilità, tempi,
  supporto e spesa provider; nessun ampliamento automatico senza controllo capacità.

**Uscita:** release tracciabile, servizio operativo, responsabili e procedure
attive. La V1 è chiusa quando il cliente lavora e il servizio è recuperabile.

## Calendario indicativo e ordine pratico

Stima di pianificazione, non promessa: **6–10 settimane** con uno sviluppatore
principale dedicato e disponibilità continuativa di collaudatore operativo,
referente infrastruttura e titolare per le decisioni. Il billing live e le
verifiche esterne possono estendere il calendario; ricalibrare dopo le fasi 0–1.

| Periodo indicativo | Obiettivo |
|---|---|
| Settimana 1 | Perimetro V1, suite verde, isolamento test, blocco configurazioni pericolose |
| Settimane 2–3 | Sicurezza e flusso completo; staging/backup in parallelo; raccolta giri reali |
| Settimane 3–5 | Validazione routing/carico, restore, billing, manuali e verifiche dati |
| Settimane 5–8 | Pilota di almeno due settimane, correzioni e candidato stabile |
| Settimane 8–10 se necessarie | Chiusura dipendenze commerciali/operative, rilascio e presidio |

Percorso critico: **suite affidabile → sicurezza → flusso completo e ambiente
recuperabile → pilota → rilascio**. Per la V1 self-service si aggiunge il gate
del billing reale. Il lavoro su UX e documentazione può procedere in parallelo,
ma non deve ritardare le verifiche che possono far emergere perdite dati.

## Checklist finale go/no-go

- [ ] SHA unico verificato; pipeline obbligatoria verde e build riproducibile.
- [ ] Zero problemi bloccanti di dati, accessi, operatività o addebiti.
- [ ] Flussi azienda/autista/cliente verificati su dispositivi reali.
- [ ] Routing e capacità dichiarata sostenuti da misure e giri reali.
- [ ] Storage, SMTP, mappe e provider collaudati nell'ambiente di rilascio.
- [ ] Backup DB/allegati ripristinati e rollback provato; obiettivi approvati.
- [ ] Acquisto/rinnovo funzionanti oppure lancio assistito dichiarato e gestibile.
- [ ] Limiti del prodotto, assistenza e gestione dati documentati.
- [ ] Pilota concluso e osservazione stabile del candidato completata.
- [ ] Responsabile del go/no-go, monitoraggio e presidio post-rilascio assegnati.

## Riferimenti interni

- [Audit precedente](audit-fixes-2026-10-04.md)
- [Billing sandbox](BILLING_SANDBOX.md)
- [POD e storage](pod-object-storage.md)
- [Tracking cliente](customer-tracking.md)
- [GPS e limiti browser](live-gps.md)
- [Validazione su giri reali](optimizer-real-fixtures.md)
- [Scalabilità ottimizzatore](optimizer-scaling.md)
- [Pipeline](../.github/workflows/tests.yml)
- [Configurazione](../app/core/config.py), [sicurezza HTTP](../app/core/http_security.py)
- [Migrazioni](../app/migrations.py), [backup](../scripts/backup_database.py)

Esiti locali dell'analisi (non versionati): `test-results/v1-roadmap-node.log`,
`test-results/v1-roadmap-python.log`, `test-results/v1-roadmap-isolated.log`.
