#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "GiroFacile v87 - Avvio locale"
if command -v python3.11 >/dev/null 2>&1; then PY=python3.11; else PY=python3; fi
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: -r requirements.txt
export APP_ENV=development
export COOKIE_SECURE=false
export TRUST_PROXY_HEADERS=false
export DATABASE_URL='postgresql+psycopg2://girofacile:girofacile_local@localhost:5432/girofacile'
echo "Apri: http://127.0.0.1:8000/login"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
