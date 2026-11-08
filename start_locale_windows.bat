@echo off
cd /d %~dp0
setlocal

echo ==========================================
echo   GiroFacile v87 - Avvio locale Windows
echo ==========================================
echo.

py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo ERRORE: Python 3.11 64-bit non trovato.
  echo Installa Python 3.11 e abilita "Add Python to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo Creo ambiente virtuale...
  py -3.11 -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERRORE durante l'installazione delle dipendenze.
  pause
  exit /b 1
)

REM Override SOLO per l'avvio locale. Il file .env rimane invariato per il server.
set APP_ENV=development
set COOKIE_SECURE=false
set TRUST_PROXY_HEADERS=false
set DATABASE_URL=postgresql+psycopg2://girofacile:girofacile_local@localhost:5432/girofacile

echo.
echo Avvio applicazione...
echo Apri nel browser: http://127.0.0.1:8000/login
echo Dal telefono (stessa rete Wi-Fi o Tailscale): usa l'indirizzo di questo PC con :8000
echo   - lo trovi in Super Admin, sezione Server, "Indirizzi per i test in locale"
echo   - la prima volta Windows puo' chiedere il permesso del firewall: consenti le reti private
echo Per fermare il server: CTRL+C
echo.
python -m app.migrations
if errorlevel 1 exit /b 1
REM 0.0.0.0: GiroFacile risponde anche agli altri dispositivi della rete (telefono degli autisti per i test).
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
