"""Controllo rapido della versione locale GiroFacile v43."""
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.main import app
from app.database import engine

client = TestClient(app)

# Prova prima l'account demo generato in crea_demo.py, poi eventuali credenziali .env.
login_payloads = [
    {"username": "admin_demo", "password": "demo1234"},
]
try:
    from app.core.config import APP_USER, APP_PASSWORD
    login_payloads.append({"username": APP_USER, "password": APP_PASSWORD})
except Exception:
    pass

login_ok = False
for payload in login_payloads:
    r = client.post('/api/login', json=payload)
    print(f"Login gestionale con {payload['username']}:", r.status_code)
    if r.status_code == 200:
        login_ok = True
        break
    else:
        print(r.text[:200])

if login_ok:
    r = client.get('/api/settings')
    print('API impostazioni:', r.status_code, r.text[:200])

insp = inspect(engine)
print('Campo users.delivery_signature_enabled:', 'delivery_signature_enabled' in [c['name'] for c in insp.get_columns('users')])
print('Campo delivery_statuses.signature_data:', 'signature_data' in [c['name'] for c in insp.get_columns('delivery_statuses')])
print('Controllo completato.')
