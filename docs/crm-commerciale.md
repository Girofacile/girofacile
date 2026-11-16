# CRM commerciale

Il modulo si apre nel pannello Super Admin, **Commerciale → CRM commerciale**,
oppure in `/admin#crm`. I dati sono persistenti nel database PostgreSQL del server.
Le anagrafiche commerciali sono separate dai clienti destinatari delle consegne.

## Primo utilizzo

1. Aprire **Aziende → Nuova azienda**. Inserire ragione sociale e i recapiti;
   partita IVA, settore, provenienza e interesse sono facoltativi.
2. Con **Apri**, consultare la scheda azienda e lo storico. Da qui selezionare
   Contatti, Pipeline, Follow-up o Attività; i nuovi record saranno collegati
   a questa azienda. **Tutte le aziende** rimuove il filtro.
3. In **Contatti**, inserire i referenti e, quando necessario, segnare
   “Non contattare”. Il modulo registra i recapiti, non invia messaggi.
4. In **Pipeline**, creare una trattativa e modificarne fase e valore EUR.
   Per la fase Persa è richiesto il motivo. Vinta imposta la probabilità al 100%.
5. In **Follow-up**, impostare la scadenza nell'ora locale. Modificare lo stato
   in Completato o Annullato quando l'attività è conclusa.
6. In **Attività**, registrare telefonate, riunioni, email già inviate o note.
   Il registro è append-only: per una rettifica aggiungere una nuova nota.

Dashboard e Report considerano l'intero periodo e le aziende attive nel portafoglio
accessibile. La conversione è vinte / (vinte + perse); senza trattative chiuse è
mostrato un trattino. I valori commerciali non rappresentano fatture o incassi.
La pipeline è presentata come elenco filtrabile per fase.

## Commerciali e permessi

Il proprietario crea o aggiorna gli account in **Collaboratori**:

- **Accesso CRM** (`crm_access`): lettura delle aziende assegnate.
- **Gestione CRM** (`crm_write`): creazione e modifica, richiede Accesso CRM.
- **Tutto il portafoglio CRM** (`crm_view_all`): visibilità globale, assegnazione
  e archiviazione; concedere soltanto a un responsabile.
- **Export CRM** (`crm_export`): CSV delle aziende attive visibili.

Per un commerciale standard abilitare Accesso CRM e Gestione CRM, poi assegnargli
le aziende dalla relativa scheda. Le aziende create dal commerciale sono assegnate
a lui automaticamente. Le aziende non assegnate sono visibili solo al proprietario
ed ai responsabili con visibilità globale. Il login è quello amministrativo
(`/admin/login`); gli account con solo CRM entrano direttamente nel modulo.
Non concedere permessi amministrativi generali per usare il CRM.

Le autorizzazioni sono rilette a ogni richiesta. L'accesso generico `all` dei
collaboratori non abilita il CRM. Solo il proprietario può concedere i permessi CRM
o modificare/reinvitare un account commerciale. Disattivare un account ne revoca
l'accesso. Prima di eliminarlo occorre riassegnare tutte le sue aziende.

## Conservazione e protezioni

L'archiviazione aziendale è reversibile (filtro **Mostra archiviate** e modifica).
Prima di archiviare bisogna completare o annullare i follow-up aperti.
Le tabelle CRM sono escluse dal Database Viewer generico, inclusi gli export.
I backup completi contengono anche il CRM: il download è riservato al proprietario.
Il registro globale annota l'export senza includere i dati commerciali.

Le schede usano un numero di versione: se un altro operatore ha salvato modifiche,
il secondo salvataggio viene rifiutato. Chiudere il modulo, aggiornare i dati e
riapplicare la modifica. Nessuna sovrascrittura silenziosa.
Non sono previsti hard delete né invio automatico di email in questa versione.

## Aggiornamento del server

Aggiornare la copia che avvia il server alla versione corrente di `main`.
Eseguire, nell'ambiente Python del gestionale:

```sh
python -m app.migrations
```

Poi riavviare il server e ricaricare `/admin#crm`.
`scripts/start_app.sh` esegue già le migrazioni prima dell'avvio.
La migrazione `20261116_01` aggiunge le tabelle CRM, senza importare clienti né
concedere accessi ai collaboratori esistenti. È ripetibile; l'app verifica lo schema
prima di partire. Il rollback del codice deve conservare le tabelle e i dati CRM.

## Collaudo

```sh
python -m pytest tests/test_crm.py tests/test_crm_postgres.py tests/test_admin_router_split.py
python tests/check_crm_ui.py
```

Il test PostgreSQL richiede `TEST_POSTGRES_URL` verso un database di test e usa uno
schema isolato. Il test browser usa un database in memoria, dati sintetici e blocca
richieste esterne. Verifica creazione, aggiornamento, persistenza dopo reload,
report, desktop/mobile e ingresso del commerciale senza privilegi amministrativi.
