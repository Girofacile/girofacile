@echo off
cd /d %~dp0
echo Setup PostgreSQL locale GiroFacile v87
echo.
where psql >nul 2>&1
if errorlevel 1 (
  echo ERRORE: psql non trovato nel PATH.
  echo Installa PostgreSQL per Windows e seleziona l'opzione per aggiungere gli strumenti al PATH.
  echo Download: https://www.postgresql.org/download/windows/
  pause
  exit /b 1
)
set PGDATABASE=postgres
set PGUSER=postgres
set /p PGPASSWORD=Inserisci password utente postgres locale: 
echo.
echo Creo utente/database se non esistono...
psql -h localhost -U postgres -d postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='girofacile'" | findstr 1 >nul
if errorlevel 1 psql -h localhost -U postgres -d postgres -c "CREATE USER girofacile WITH PASSWORD 'girofacile_local';"
psql -h localhost -U postgres -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='girofacile'" | findstr 1 >nul
if errorlevel 1 psql -h localhost -U postgres -d postgres -c "CREATE DATABASE girofacile OWNER girofacile;"
echo.
echo DATABASE_URL locale consigliato:
echo DATABASE_URL=postgresql+psycopg2://girofacile:girofacile_local@localhost:5432/girofacile
echo.
py -3.11 -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: -r requirements.txt
python scripts\init_postgres_demo.py
pause
