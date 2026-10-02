# Bonus mobilità elettrica

## Catalogo e regola unica

Il catalogo commerciale esistente, `app/services/plan_catalog.py`, ora espone
`electric_vehicle_bonus`. Valori iniziali: Starter 1, Business 2, Pro 5.
I limiti standard restano rispettivamente 3, 10 e 50 mezzi. API pubbliche,
catalogo JavaScript, autenticazione e interfacce leggono gli stessi valori.

Con S = limite standard, B = bonus, N = mezzi non elettrici ed E = elettrici,
le condizioni sono entrambe:

- N ≤ S;
- N + E ≤ S + B.

Il conteggio assegna prima gli elettrici al bonus:
`bonus_used = min(E, B)`, `standard_used = N + max(0, E - B)`.
Non esiste un'attribuzione permanente dello slot a uno specifico mezzo:
eliminazioni e cambi piano aggiornano automaticamente l'allocazione.

Esempio Business: 8 diesel + 4 elettrici = 10 slot standard + 2 bonus.
10 diesel + 2 elettrici sono ammessi; 11 diesel o 10 diesel + 3 elettrici no.
Solo l'alimentazione interamente elettrica, `elettrico`, è idonea: GPL,
metano, benzina, gasolio, ibridi e plug-in restano mezzi standard.
Gli input sono normalizzati per spazi e maiuscole. Dati legacy null o
sconosciuti non danno diritto al bonus. Il riconoscimento dati targa distingue
gli ibridi prima degli alias elettrico/benzina/diesel.

## API e autorizzazioni

`app/services/plans.py` centralizza `vehicle_usage` e `check_vehicle_limit`.
`GET /api/vehicles/usage` restituisce limiti, conteggi standard/bonus/totali,
disponibilità, possibilità di aggiunta e conflitti. Lo stesso report è incluso
in `usage.resources.vehicles` degli endpoint fatturazione: i precedenti
`used` e `limit` rappresentano ora il totale e il massimo comprensivo di bonus.

Creazione e modifica dell'alimentazione passano dallo stesso controllo.
Creazione, modifica e archiviazione serializzano le operazioni per azienda
sulla riga User PostgreSQL; il piano è riletto dopo il lock. Non sono contati
i mezzi archiviati (`deleted_at`); un mezzo inattivo ma non archiviato continua
a occupare uno slot, come prima.

Il passaggio elettrico → altra alimentazione viene bloccato se supera S.
Il messaggio indica perché il bonus è riservato agli elettrici e invita a
liberare uno slot standard o scegliere un piano superiore.

## Upgrade, downgrade e cancellazione

L'upgrade aggiorna immediatamente il bonus quando il nuovo piano diventa
effettivo secondo il sistema abbonamenti esistente; un pagamento pendente
non concede il bonus del futuro piano. La disdetta a fine periodo conserva
il piano corrente fino alla scadenza. A scadenza/cancellazione restano in
vigore gli attuali controlli di accesso: il bonus non riattiva l'abbonamento.

Il downgrade commerciale controlla N e N+E usando `vehicle_usage` per il
piano di destinazione; se ci sono eccedenze la richiesta è bloccata con
dettagli, senza cancellare mezzi. Un downgrade programmato cambia quote
al rinnovo effettivo. Le eventuali nuove risorse aggiunte durante l'attesa
sono valutate sul piano ancora attivo; se al rinnovo eccedono il nuovo
piano, il report segnala il conflitto e blocca nuove aggiunte.

Un cambio amministrativo o un aggiornamento esterno che lasci una flotta
oltre i limiti conserva tutti i dati e gli storici. Sono consentite
eliminazioni, modifiche che non cambiano classe elettrica e conversioni
non elettrico → elettrico. Un cambio elettrico → termico resta subordinato
al limite non elettrici. Non vengono disabilitati o cancellati mezzi
automaticamente e non viene modificato il motore di pianificazione.

## Interfacce e comunicazione

Mezzi e form di creazione/modifica mostrano slot standard, bonus e messaggi
dinamici. Anche i riepiloghi abbonamento, le card piani, il mobile e la landing
pubblica espongono il beneficio. I testi collegano ottimizzazione,
controllo di costi/consumi e incentivo alla mobilità elettrica senza
promettere sostenibilità assoluta o emissioni nulle.

## Database e verifica

Nessuna migrazione, nuova colonna o riscrittura dei mezzi è necessaria:
il bonus è una proprietà del catalogo e l'allocazione è derivata dalla
flotta corrente. Tutti i collegamenti ai giri storici sono mantenuti.

I test coprono limiti per tutti i piani, alimentazioni non idonee,
cambi di alimentazione, eliminazioni, upgrade e downgrade, cancellazioni,
tenant, valori legacy, configurazione centrale e creazione concorrente
sull'ultimo slot PostgreSQL. I test frontend verificano numeri dinamici,
messaggi e flussi. La CI esegue inoltre una verifica Chromium a 320, 768
e 1440 pixel sui nuovi componenti e sulla landing.

Comandi:
```sh
python -m pytest tests -q
node --test tests/*.cjs
# Solo per la verifica browser, senza dipendenze aggiunte al runtime:
pip install playwright==1.55.0
python -m playwright install --with-deps chromium
python tests/check_electric_responsive.py
```

## File modificati

- `.dockerignore`
- `.github/workflows/tests.yml`
- `.gitignore`
- `app/routers/admin_users.py`
- `app/routers/vehicles_drivers.py`
- `app/schemas/__init__.py`
- `app/services/billing.py`
- `app/services/plan_catalog.py`
- `app/services/plans.py`
- `app/services/usage_limits.py`
- `app/services/vehicle_lookup.py`
- `docs/electric-vehicle-bonus.md`
- `static/dashboard/css/electric-vehicles.css`
- `static/dashboard/index.html`
- `static/dashboard/js/billing.js`
- `static/dashboard/js/core.js`
- `static/dashboard/js/electric-vehicles.js`
- `static/landing/index.html`
- `static/mobile/index.html`
- `static/mobile/mobile.js`
- `tests/check_electric_responsive.py`
- `tests/test_electric_admin_plan.py`
- `tests/test_electric_landing_ui.cjs`
- `tests/test_electric_vehicle_bonus.py`
- `tests/test_electric_vehicle_ui.cjs`
