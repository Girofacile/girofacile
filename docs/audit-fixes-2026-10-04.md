# Correzioni dell'audit GiroFacile — 4 ottobre 2026

## Aggiornamento e compatibilità

Eseguire `python -m app.migrations` con l'ambiente virtuale e la configurazione
del server prima di avviare Uvicorn. Docker e gli script di avvio locale lo
eseguono automaticamente. Gli avvii personalizzati devono aggiungere questo
passaggio. L'importazione dell'applicazione non modifica più il database;
lo startup verifica la versione dello schema.

Le migrazioni PostgreSQL sono serializzate e registrate in `schema_migrations`.
Se esistono stati duplicati della stessa consegna, l'aggiornamento si ferma:
occorre riconciliare le evidenze prima di riprovare. Non vengono cancellati
stati, firme o dati storici per scegliere arbitrariamente un record.

Gli utenti aziendali, autisti e agenti devono effettuare un nuovo login:
i precedenti cookie non contenevano scadenza e legame con le credenziali.
Il cambio password invalida le sessioni precedenti, inclusa quella corrente.

## Riscontro dei 27 punti

1. **Account archiviati:** reset e attivazione verificano anche l'identità
   collegata. Il reset non riattiva autisti o agenti archiviati.
2. **Segreti nel visualizzatore DB:** mascheratura del valore in base alla
   chiave nelle impostazioni, anche nell'export; esclusione dei valori dalla
   ricerca delle tabelle chiave/valore per evitare inferenze sui segreti.
3. **Sessioni:** scadenza verificata dal server e revoca persistente al logout.
   Le credenziali e lo stato attivo vengono ricontrollati. Cookie eliminati
   con il dominio configurato; nonce anche per nuove sessioni amministrative.
4. **Cambio password aziendale:** i token sono legati all'hash corrente;
   le sessioni emesse prima del cambio non sono più valide.
5. **Permessi amministrativi:** la gestione della piattaforma non concede
   implicitamente lettura o modifica delle chiavi dei servizi.
6. **Giri annullati:** aggiornamenti operativi rifiutati anche quando esiste
   già un record di utilizzo. Blocco del giro durante le transizioni.
7. **Durate:** nuovi timestamp UTC per inizio e fine. Le vecchie date locali
   restano intatte; per lo storico ambiguo il report usa la durata pianificata.
8. **Ultima mancata consegna:** la chiusura considera tutte le fermate
   terminali, sia consegnate sia mancate, in entrambi i portali.
9. **Retry:** ripetere lo stesso esito non duplica osservazioni o utilizzo
   e non sovrascrive la prima evidenza. Un esito terminale diverso è rifiutato.
10. **Avvio futuro:** l'avvio esplicito di un giro è consentito nella sua
    giornata locale; un giro già in corso può essere ripreso.
11. **Input e firme:** schema condiviso, limiti su tempi/testi e motivazioni;
    verifica reale del contenuto PNG, dimensioni e decodifica prima delle scritture.
12. **Notifiche chat:** deduplica tramite ID messaggio, indipendente dal
    numero dei messaggi non letti.
13. **Isolamento notifiche:** filtro azienda prima dei limiti dei risultati;
    sincronizzazione serializzata per azienda.
14. **Omonimi nei report:** aggregazione per ID, con etichette solo per la
    presentazione. Clienti, agenti, autisti e veicoli omonimi restano distinti.
15. **Ripartizione report:** km, ore e costi sono ripartiti in proporzione
    alle fermate selezionate. I totali per agente sono additivi; questa è una
    convenzione di analisi, non una misura GPS del costo per singola consegna.
16. **Conteggi report:** fermate previste dei giri chiusi, con consegnate,
    mancate e non gestite distinte. Criterio esplicitato nella pagina e stampa.
17. **Utilizzo piano:** il contatore clienti usa l'utilizzo restituito dal
    server, non la lunghezza della lista caricata in interfaccia.
18. **Email delle identità:** controllo globale coerente con il login unico,
    serializzato su PostgreSQL. Include le identità archiviate; conflitti
    storici non vengono risolti fondendo o cancellando account automaticamente.
19. **Interruttori piattaforma:** blocco registrazioni e manutenzione applicati
    dal server. Amministrazione, recupero password, logout, assistenza e
    fatturazione restano accessibili nei rispettivi limiti di autenticazione.
20. **Trial e piano iniziale:** registrazione e catalogo leggono le impostazioni
    configurate. Il piano esplicitamente scelto mantiene la precedenza.
21. **Backup:** il pannello non promette frequenze o storage non implementati
    dal suo endpoint. Il timer reale `deploy/systemd/girofacile-backup.timer`
    resta configurabile sul server separatamente; il pannello non lo modifica.
22. **Stripe:** unica fonte della chiave operativa nell'ambiente server;
    input amministrativo disabilitato e aggiornamenti incoerenti rifiutati.
    Nessuna attivazione di pagamenti live effettuata da questa modifica.
23. **Migrazioni:** bootstrap estratto da `main.py`, comando esplicito,
    versioni e lock PostgreSQL. Rimossa la cancellazione automatica della
    tabella storica `activity_events` all'importazione.
24. **Transazioni consegne:** servizio comune, flush intermedi e commit finale;
    unicità dello stato per giro/consegna. La lettura dei portali non crea più
    stati vuoti. I GET che segnano messaggi letti mantengono la semantica esistente.
25. **Struttura:** estratti sessioni, identità, policy, esecuzione dei giri,
    migrazioni e navigazione. Un solo `showTab`, senza i tre wrapper precedenti.
    È un refactoring mirato: i moduli storici grandi non sono tutti riscritti.
26. **Funzioni legacy:** al momento di questo audit le verticalizzazioni storiche
    erano state mantenute per compatibilità. La successiva dismissione definitiva
    viene gestita con rimozione del codice e migrazione esplicita dei dati residui.
27. **Query, errori e verifiche:** query chat aggregate e caricamenti report
    raggruppati; catch prima vuoti della dashboard resi diagnosticabili;
    regressioni di sicurezza, operazioni e concorrenza PostgreSQL aggiunte.
    CI estesa ai controlli browser delle pagine gestionali. Le anagrafiche
    mantengono il caricamento limitato esistente: la paginazione completa lato
    server e la scomposizione integrale dei moduli restano evoluzioni ulteriori.

## Validazione

- Suite Python generale: 452 test passati e 8 saltati nella prima esecuzione
  completa, prima delle ultime regressioni aggiunte. I test PostgreSQL allora
  saltati sono stati successivamente eseguiti su un container PostgreSQL 16
  temporaneo con dati sintetici.
- Regressioni mirate: sessioni/revoche/reset, manutenzione, permessi, firme,
  giri annullati, retry, notifiche, report e registrazioni.
- PostgreSQL: migrazioni concorrenti e ripetute, conservazione dati, rifiuto
  dei duplicati preesistenti e conferme concorrenti della stessa consegna.
- JavaScript: 49 test passati.
- Browser: nessun errore o overflow rilevato a 390, 768 e 1440 pixel;
  Dashboard, Clienti, Azienda e Depositi conservano geometria e stili.

I controlli browser usano risposte sintetiche e non sostituiscono una verifica
dei provider esterni in produzione. Nessun database reale, pagamento o invio
email reale è stato usato. Non è stato eseguito un deployment del servizio.
