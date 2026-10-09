# Collaboratori aziendali

Il titolare trova **Collaboratori** nella sidebar e nel menu mobile. Può creare
un accesso personale con nome, email e password iniziale, scegliere le funzioni
assegnate, modificarle e disattivare l'accesso. Non vengono spedite credenziali
automaticamente: la password iniziale va comunicata tramite un canale riservato.
Il collaboratore usa la normale pagina Login e può cambiare la propria password
dal profilo o utilizzare il recupero via email già configurato nel gestionale.

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
`tests/check_collaborators_ui.py` verifica in Chrome/Playwright desktop e mobile
la creazione, le dipendenze, la ricerca e il profilo limitato con API simulate.
Non invia email né modifica dati reali.
