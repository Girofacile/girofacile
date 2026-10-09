# Collaboratori aziendali

Il titolare trova **Collaboratori** nella sidebar e nel menu mobile. Può creare
un accesso personale con nome ed email, scegliere le funzioni assegnate,
modificarle e disattivare l'accesso. Il titolare non sceglie la password:
**Invia invito** spedisce automaticamente al destinatario un link personale.
Il collaboratore apre il link, sceglie e conferma la propria password, quindi
accede dalla normale pagina Login. Dopo l'attivazione può cambiare la password
dal profilo o utilizzare il recupero via email già configurato nel gestionale.

## Invito e attivazione

La scheda resta **Invito in attesa** finché il destinatario non imposta una
password conforme alle regole del gestionale. Prima dell'attivazione non sono
consentiti login, sessioni o recupero password ordinario. Nome, email, azienda e
autorizzazioni restano quelli assegnati dal titolare.

Il link scade dopo **7 giorni**, funziona una sola volta e serve esclusivamente
a inizializzare la password del collaboratore. Aprire la pagina non consuma
l'invito. Il token è conservato nel database solo come hash; nel link è nel
fragment, rimosso dalla pagina prima delle richieste API, senza query string,
storage del browser o cookie di autenticazione. La scelta della password non
crea automaticamente una sessione: il destinatario accede esplicitamente.

**Invia nuovo invito** sostituisce e revoca il link precedente. Se l'email non viene
inviata, il collaboratore già creato resta visibile, senza accesso: la pagina
mostra l'errore e permette il reinvio sulla stessa scheda. Non bisogna creare un
secondo account. Un invio già in corso viene protetto dai tentativi ravvicinati;
il completamento di un vecchio invio non ripristina link sostituiti.

Cambiare l'email revoca sessioni, inviti e recuperi precedenti e richiede una
nuova attivazione all'indirizzo aggiornato, anche per un account già attivo.
Disattivare revoca i link; riattivare un account ancora in attesa invia un nuovo
invito. Modificare nome o autorizzazioni non reinvia email e non cambia password.
Gli account esistenti già attivati conservano credenziali e autorizzazioni.
Le richieste di cambio/reset password del collaboratore rileggono identità e
token sotto lock: una richiesta avviata prima del cambio email non può
sovrascrivere la password impostata dal nuovo destinatario.

L'invio riutilizza il servizio email e le impostazioni SMTP amministrative
esistenti. Configurare **APP_BASE_URL** con il dominio pubblico corretto;
in produzione (`APP_ENV=production` o `prod`) è richiesto HTTPS. Non inserire
credenziali, query o fragment nell'URL configurato. Il titolare non riceve il
token né un link da copiare nelle risposte API.

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
operativi esistenti. La migrazione **20261009_02** aggiunge
`password_setup_required` con default falso e la tabella
`collaborator_invitations` (token hash univoco, scadenza, invio e consumo).
È additiva e ripetibile: non reinizializza le password già presenti.
Gli avvii standard locali e Docker eseguono già le migrazioni.
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

I test degli inviti sono in `tests/test_collaborator_invitations.py`,
`tests/test_collaborator_invitations_postgres.py` e
`tests/test_collaborator_invitation_security.py`. Verificano password scelte
solo dal destinatario, invii simulati, scadenza, revoca, isolamento, cambio email,
recupero ordinario e compatibilità degli account esistenti. Le prove di
concorrenza e migrazione usano PostgreSQL isolato, non SQLite.
`tests/check_collaborator_invitation_ui.py` verifica il form pubblico a
390/768/1024/1440 px, token privato, conferma password, errori e retry.
