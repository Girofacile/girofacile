# Collaboratori aziendali

Il titolare trova **Collaboratori** nella sidebar e nel menu mobile. Può creare
un accesso personale con nome, email e password iniziale, scegliere le funzioni
assegnate, modificarle e disattivare l'accesso. Non vengono spedite credenziali
automaticamente: la password iniziale va comunicata tramite un canale riservato.
Il collaboratore usa la normale pagina Login e può cambiare la propria password
dal profilo o utilizzare il recupero via email già configurato nel gestionale.

## Profili preimpostati e personalizzazione

Il form propone **Operatore** per un nuovo collaboratore:
tutte le funzioni aziendali attuali, inclusi dati aziendali e impostazioni.
**Piano/abbonamento, fatturazione e gestione dei collaboratori** restano
riservati al titolare; anche le API negano queste operazioni.

Sono disponibili anche **Pianificatore** (risorse in consultazione, gestione
giri, report, chat e assistenza) e **Sola lettura** (consultazione senza
modifiche operative). I profili rispettano sempre le funzioni previste dal
piano aziendale: un ruolo non sblocca servizi assenti dall'abbonamento.

Aprire **Personalizza le funzioni** per aggiungere o togliere singole
autorizzazioni. Una modifica manuale identifica la selezione come
**Personalizzato**. Selezionare un altro profilo sostituisce la selezione
corrente; scegliere Personalizzato la conserva. Le dipendenze necessarie
restano evidenti e vengono applicate dal server come prima.

I preset sono definiti centralmente e forniti dal catalogo API. Si salvano
sempre permessi espliciti, non un ruolo di autenticazione. Gli account
esistenti mantengono le autorizzazioni assegnate; aprire la scheda non
le sostituisce con quelle di un preset. Le nuove funzioni future richiedono
una revisione esplicita del catalogo dei profili.

Le schermate bloccate dal piano mostrano al collaboratore un messaggio
per contattare il titolare, senza prezzi o pulsanti upgrade. La guida di
configurazione iniziale dell'account rimane riservata al titolare; la normale
pagina Azienda e le impostazioni sono modificabili dall'Operatore.

I campi aziendali in sola lettura non attivano bozze non salvabili. La creazione
richieste di assistenza richiede il permesso corrispondente di scrittura.

Salva e Annulla del profilo aziendale sono raggiungibili anche su smartphone,
con una barra sopra la navigazione mobile quando ci sono modifiche non salvate.
I test usano i pulsanti reali, verificandone dimensioni e assenza di sovrapposizioni.

Non è necessaria una nuova migrazione per i preset.

## Funzioni e dipendenze

- Clienti, depositi, mezzi, autisti e agenti: visualizzazione, creazione,
  modifica ed eliminazione selezionabili separatamente.
- Giri: visualizzazione, pianificazione, programmazione, annullamento/completamento
  e gestione dei link operativi/tracking. Programmare include la normale
  assegnazione al conducente e la notifica prevista dal flusso esistente.
- Dashboard, report, chat, dati aziendali, impostazioni operative, assistenza
  e notifiche sono assegnabili. Le funzioni restano soggette al piano dell'azienda.
- Abbonamento, fatturazione, gestione dei collaboratori e accesso Super Admin
  restano riservati alle rispettive identità amministrative.

La selezione aggiunge le letture necessarie. Per esempio, **Pianifica** include
giri, clienti, depositi, mezzi, autisti e agenti; **Programma** include Pianifica.
Queste dipendenze non concedono la modifica delle anagrafiche. Per rimuovere una
lettura necessaria occorre prima togliere la funzione che la richiede.
La modifica di un giro già programmato richiede Programma anche nel ricalcolo.

Gli account senza permessi possono accedere solo al proprio profilo e vedono un
messaggio che invita a contattare il titolare. La disattivazione mantiene la
scheda e revoca le sessioni; la successiva riattivazione richiede un nuovo login.
Il titolare può gestire gli accessi esistenti anche con abbonamento scaduto.

## Confini di sicurezza

`CompanyCollaborator` è un'identità distinta da `User`: i dati operativi
continuano ad appartenere all'azienda. La sessione è firmata con ruolo distinto,
vincolata alla password e alla versione della sessione. Il server rilegge stato e
permessi ad ogni richiesta e nega gli endpoint non esplicitamente autorizzati.
Le API del profilo collaboratore modificano esclusivamente questa identità.
L'email di accesso è modificabile solo dal titolare; email, disattivazione e
password invalidano i relativi accessi/link di recupero preesistenti.

La UI nasconde menu e azioni non assegnati. Se il titolare cambia i permessi
durante una sessione, i nuovi vincoli sono immediati sul server; ricaricare la
pagina aggiorna anche i menu. Le email sono uniche rispetto alle altre identità
aziendali, incluse quelle archiviate.

## Aggiornamento

Migrazione **20261009_01**: crea `company_collaborators` senza modificare i dati
operativi esistenti. Gli avvii standard locali e Docker eseguono già le migrazioni.
Per un avvio personalizzato, con la configurazione del database corretta:

```sh
python -m app.migrations
```

Riavviare quindi i worker dell'applicazione. I test della modifica usano database
isolati; non è stata applicata manualmente una migrazione al database in uso.

## Verifica

`tests/test_company_collaborators.py` copre isolamento aziendale, diniego delle
operazioni non assegnate, login/logout, revoche, password, migrazione ripetibile,
coerenza dei percorsi API, ricalcolo dei giri programmati e piano scaduto.
`tests/check_collaborators_ui.py` usa Chromium di Playwright ed è integrato nella
CI a 390/768/1024/1440 px. Verifica preset, permessi manuali, dipendenze, modifica,
ricerca, retry, navigazione mobile, esclusioni del titolare e profilo personale
con API simulate. Screenshot e report sono conservati come artefatti CI.
I controlli backend mantengono i casi negativi, l'isolamento aziendale e le prove
PostgreSQL di migrazione e concorrenza. I test non inviano email né effettuano
pagamenti reali.
