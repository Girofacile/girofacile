import csv
import io
import zipfile

import pytest

from test_billing import billing_env
from test_agents_feature import env


@pytest.mark.parametrize("name", ["=1+1", " \t=1+1", "+1+1", "-1+1", "@SUM(1)"])
def test_company_data_export_neutralizes_formulas(billing_env, name):
    from app.models import Customer
    client, db, user, *_ = billing_env
    db.add(Customer(user_id=user.id, nome=name, indirizzo="Via Roma"))
    db.commit()
    response = client.get('/api/billing/data-export')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read('customers.csv').decode('utf-8-sig'))))
    assert any(row['nome'] == "'" + name for row in rows)


def test_admin_csv_keeps_masking_and_neutralizes_formulas(env, monkeypatch):
    from app.routers import admin_database
    from app.models import Customer
    from app.core.dependencies import require_superadmin
    client, db, owner, *_ = env
    db.add(Customer(user_id=owner.id, nome=" \t=1+1", indirizzo="Via Roma"))
    db.commit()
    monkeypatch.setattr(admin_database, 'engine', db.get_bind())
    monkeypatch.setattr(admin_database, '_require_perm', lambda *_: None)
    monkeypatch.setattr(admin_database, '_activity', lambda *_: None)
    client.app.include_router(admin_database.router)
    client.app.dependency_overrides[require_superadmin] = lambda: {'username':'test'}
    response = client.get('/api/admin/database-viewer/table/customers/export')
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert any(row['nome'] == "' \t=1+1" for row in rows)
