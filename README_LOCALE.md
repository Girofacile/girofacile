# Avvio locale GiroFacile v43

Questa versione parte dalla cartella reale scaricata dal server e contiene i fix ai pulsanti di salvataggio più la sezione Impostazioni/Firma consegna.

## Avvio rapido su Windows

1. Estrai lo ZIP.
2. Apri la cartella estratta.
3. Fai doppio click su:

```text
start_locale_windows.bat
```

Lo script usa Python 3.11 64-bit. Se non lo trova, installa Python 3.11 da python.org e durante l'installazione spunta **Add Python to PATH**.

Quando il server parte, apri:

```text
http://127.0.0.1:8000/login
```

## Avvio manuale su Windows

Apri PowerShell nella cartella del progetto e lancia:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Login demo

```text
Utente: admin_demo
Password: demo1234
```

## Controllo rapido

Con ambiente virtuale attivo:

```powershell
python check_locale.py
```

## Cosa testare

- Apri **Clienti** → `+ Nuovo cliente` → salva.
- Apri **Autisti** → `+ Nuovo autista` → salva.
- Apri **Mezzi** → modifica/crea mezzo → salva.
- Apri **Agenti** → salva agente.
- Apri **Impostazioni** → attiva/disattiva `Firma cliente alla consegna`.
- Dal portale autista verifica che la firma compaia solo quando il toggle è attivo.

## Nota importante

Questa cartella contiene anche il file `.env` preso dal server per mantenere la versione fedele all'attuale produzione. Non caricare questa cartella su GitHub pubblico e non condividere lo ZIP con terzi.

## Note v44 — firma cliente separata

Nella v44 la firma cliente non appare più dentro la schermata principale di conferma consegna.
Quando la firma è attiva da Dashboard > Impostazioni, nel portale autista appare il pulsante **Firma avvenuta consegna**. Cliccandolo si apre una schermata dedicata dove inserire nome firmatario e firma.

Dopo il salvataggio, nella conferma consegna compare lo stato **Firma acquisita**. La consegna non può essere confermata senza firma quando l'opzione è attiva.

Lato Dashboard, nelle sottopagine **Giri in corso**, **Giri completati** e nello **Storico**, le consegne firmate mostrano il pulsante **Firma** per aprire un popup con firmatario, orario, autista e immagine firma.

## Aggiornamento v45

Questa versione introduce la schermata giro unificata: giri programmati, in corso, completati e storico usano lo stesso stile e la stessa tabella fermate.

Nello storico il pulsante “Apri giro” mostra ora una scheda moderna con arrivo previsto, arrivo reale, differenza, firma e note.

---

## v46 — Registrazione azienda professionale

La registrazione azienda ora è divisa in 4 step:

1. Account
2. Dati aziendali
3. Fatturazione
4. Settore e necessità operative

Il settore scelto viene salvato nel profilo dell'azienda e servirà nelle prossime versioni per adattare testi, campi e funzioni di GiroFacile al tipo di attività.

## v47 - Motore Settori Aziendali

La v47 introduce la base multi-settore di GiroFacile. Il settore scelto in registrazione viene salvato sull'azienda e usato per adattare alcune etichette e funzioni consigliate del gestionale.

Settori principali inclusi: Grossista/distribuzione, Cash & Carry, Ho.Re.Ca., Surgelati/refrigerato, Corriere locale, E-commerce, Delivery food, Farmaceutico, Beverage, Lavanderia, Ricambi auto, Servizio transfer e Altro.

## Note v48 - Settori principali ottimizzati

Da questa versione GiroFacile usa 6 settori principali + Altro:

- Distribuzione / Cash & Carry
- Logistica / Corrieri locali
- E-commerce / Consegna ordini
- Food delivery / Ristorazione
- Servizio transfer
- Farmaceutico / Sanitario
- Altro

I vecchi settori della v47 vengono mantenuti compatibili tramite alias automatici.

## v50 - Settore Logistica / Corrieri locali

La versione v50 attiva la dashboard verticale per il settore Logistica / Corrieri locali. Per provarla, crea una nuova azienda e scegli quel settore in fase di registrazione.


## v53 - Food delivery / Ristorazione

Il settore Food delivery ora ha una Dashboard dedicata con KPI e sezioni orientate a ordini food, rider, turni, punti vendita, orari di ritiro/consegna e futuro Menu / Catalogo.

---

## v56 - Notifiche errori Super Admin

La v56 introduce la sezione **Errori sistema** nel pannello Super Admin.

Per ricevere email quando si verifica un errore tecnico importante, configura nel file `.env`:

```env
ERROR_NOTIFICATIONS_ENABLED=true
ERROR_NOTIFICATIONS_EMAIL=la_tua_email@dominio.it
ERROR_NOTIFICATION_MIN_SEVERITY=high
```

Il sistema usa lo stesso SMTP configurato per le email del gestionale.

## v64 - Super Admin SaaS avanzato

Nel pannello Super Admin sono disponibili nuove sezioni:

- Profilo Admin
- Impostazioni SaaS
- Registro attività

Da mobile sono accessibili dal menu **Altro** del pannello admin.


## v72 - PostgreSQL obbligatorio

Da v72 GiroFacile usa PostgreSQL come database ufficiale. Prima di avviare in locale eseguire `setup_postgres_locale.bat` e controllare `DATABASE_URL` nel file `.env`.
