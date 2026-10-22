# GiroFacile v87 — avvio locale

Questa cartella contiene la versione completa v87 Security & Stability.
Il file `.env` originale è mantenuto per il server; gli script locali sovrascrivono solamente le variabili necessarie durante l'esecuzione locale e non modificano `.env`.

## Requisiti Windows

- Python 3.11 64-bit
- PostgreSQL 16 (o compatibile), con `psql` disponibile

## Prima esecuzione

1. Esegui `setup_postgres_locale.bat`.
2. Inserisci la password dell'utente amministratore PostgreSQL locale quando richiesta.
3. Lo script crea, se mancanti:
   - utente DB: `girofacile`
   - database: `girofacile`
   - password DB locale: `girofacile_local`
4. Al termine esegui `start_locale_windows.bat`.
5. Apri `http://127.0.0.1:8000/login`.

## Avvio manuale Windows (PowerShell)

```powershell
cd "C:\percorso\GiroFacile_v87_COMPLETA_LOCALE"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: -r requirements.txt
$env:APP_ENV="development"
$env:COOKIE_SECURE="false"
$env:TRUST_PROXY_HEADERS="false"
$env:DATABASE_URL="postgresql+psycopg2://girofacile:girofacile_local@localhost:5432/girofacile"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Avvii successivi

```powershell
cd "C:\percorso\GiroFacile_v87_COMPLETA_LOCALE"
.\.venv\Scripts\Activate.ps1
$env:APP_ENV="development"
$env:COOKIE_SECURE="false"
$env:TRUST_PROXY_HEADERS="false"
$env:DATABASE_URL="postgresql+psycopg2://girofacile:girofacile_local@localhost:5432/girofacile"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In alternativa, basta fare doppio clic su `start_locale_windows.bat`.

## Test sicurezza v87

Con ambiente virtuale attivo:

```powershell
pytest -q
```

## Nota

Non pubblicare la cartella o il file `.env` su repository pubblici.
