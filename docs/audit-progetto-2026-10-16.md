# Controllo del progetto — 16 ottobre 2026

## Correzioni

- Report: date inesistenti, formati non ISO e intervalli invertiti restituiscono
  un errore di validazione leggibile invece di provocare errori SQL o risultati
  vuoti fuorvianti. Identificativi di filtro non validi non vengono più ignorati.
- Report: il filtro clienti carica tutte le pagine dell'anagrafica, anche oltre
  1.000 clienti. Un caricamento interrotto non salva una lista parziale in cache.
- Report: una risposta precedente arrivata in ritardo non sovrascrive il report
  richiesto più recentemente e non mostra notifiche di errore ormai superate.
- Stampa: i filtri descritti nel documento sono quelli della richiesta iniziale,
  anche se l'utente modifica la selezione durante la preparazione.
- CSV dei report, esportazione aziendale e database amministrativo: i nomi che
  iniziano con operatori di formula, anche preceduti da spazi, restano testo.
  Le metriche numeriche e il mascheramento dei dati riservati sono preservati.
- Collaudo: su Windows il controllo del design usa Chrome installato, come il
  controllo delle pagine gestionali; su Linux continua a usare Chromium.
- Attivazione collaboratore: la pagina impedisce il caricamento di fogli stile
  e font esterni, incluso l'import Google Fonts del tema condiviso. Mantiene
  gli stili locali e i font di riserva senza contattare terzi durante l'invito.

## Verifiche

- Suite Python generale: 859 test superati, 34 saltati, nessun fallimento.
  La suite mirata riportata sotto verifica anche le correzioni introdotte durante
  l'esecuzione generale. Rimangono avvisi di deprecazione delle dipendenze e un
  avviso SQLAlchemy nel test di rigenerazione del tracking.
- Suite JavaScript completa: 139 test superati.
- Nuovi test API report: 29 test superati su database SQLite isolato.
- Suite mirata report, CSV, billing e separazione router amministrativi:
  66 test superati dopo le correzioni finali.
- Pagine gestionali: 18 sezioni a 390, 768, 1024 e 1440 pixel; nessun errore
  JavaScript, overflow orizzontale o scrittura imprevista nei percorsi verificati.
  Inclusi clienti, depositi, azienda, mezzi, autisti, impostazioni, report,
  pianificazione, anteprima, giri in corso e completati.
- Componenti e portali: 96 combinazioni pagina/stato/larghezza superate, inclusi
  amministrazione, mobile, autista, operatore, agente, tracking, landing e pagine
  legali. Verificati anche tastiera, ripetizione del caricamento e firme.
- Ordini: creazione, modifica, filtri, selezione persistita, raggruppamento,
  importazione, duplicati, errori di pianificazione e recupero; quattro larghezze,
  API applicative e database di test in memoria.
- Connettori ordini: configurazione email e Shopify e campi responsive a quattro
  larghezze con dati isolati.
- Collaboratori: preset, permessi manuali, dipendenze, esclusioni, sola lettura,
  navigazione mobile, fallimento/ripetizione inviti e profilo personale verificati.
- Attivazione collaboratori: 56 scenari superati (14 per larghezza), senza errori
  JavaScript o richieste esterne/impreviste dopo la correzione. La fixture della
  favicon rispecchia ora l'alias `/favicon.ico` già presente nel server.

## Limiti

I controlli browser utilizzano risposte sintetiche o database di test. Non
certificano ogni possibile combinazione di dati e azioni. Non sono state
eseguite operazioni su clienti, pagamenti o servizi esterni di produzione.
Le integrazioni PostgreSQL richiedono `TEST_POSTGRES_URL`; i controlli dedicati
che non dispongono del servizio vengono saltati, non considerati superati.
Restano distinti il push del codice e la verifica del deploy in produzione.
