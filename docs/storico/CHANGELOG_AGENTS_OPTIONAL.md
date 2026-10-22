# Gestione agenti opzionale

In **Impostazioni → Funzionalità opzionali → Gestione agenti**, attivare o
disattivare l'opzione e premere **Salva modifiche**.

- Disattivata: menu Agenti, assegnazione e filtro clienti, colonna Agente,
  filtro e riepiloghi dei report non vengono mostrati. I nuovi clienti, anche
  importati, vengono creati senza agente. I filtri agente ricevuti dal server
  vengono ignorati. Il portale agenti e gli inviti vengono bloccati.
- Attivata: le funzioni tornano disponibili nei piani che includono gli agenti.
- Gli agenti, gli account e le associazioni precedenti vengono conservati,
  anche modificando o importando clienti mentre l'opzione è disattivata.
- Le notifiche agenti sono nascoste durante la disattivazione; il registro
  delle attività precedenti rimane consultabile come storico.
- Le nuove aziende partono con l'opzione disattivata. Al primo aggiornamento
  del database, le aziende con agenti non archiviati mantengono la funzione
  attiva. I successivi riavvii rispettano la preferenza salvata.

La migrazione viene eseguita dal normale avvio del server. Aggiornare il
codice e riavviare il servizio; gli asset hanno una nuova versione cache.

Verifiche: `python -m pytest tests -q` e
`node --test tests/test_agents_ui.cjs`. I test database usano SQLite isolato;
non accedono al database di produzione.
