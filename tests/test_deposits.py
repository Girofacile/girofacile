from datetime import datetime
from test_agents_feature import env


def test_deposits_timestamp_default_crud_and_tenant_isolation(env):
    from app.models import Deposit
    from app.routers import deposits
    client, db, owner, other, *_ = env
    client.app.include_router(deposits.router)
    foreign = Deposit(user_id=other.id, nome='Altro', indirizzo='Via Test', predefinito=True)
    db.add(foreign)
    db.commit()
    created = client.post('/api/deposits', json={'nome':'Primo','indirizzo':'Via Roma','predefinito':True}).json()
    assert created['updated_at']
    item = db.get(Deposit, created['id'])
    item.updated_at = datetime(2020, 1, 1)
    db.commit()
    second = client.post('/api/deposits', json={'nome':'Secondo','indirizzo':'Via Test','predefinito':True}).json()
    assert foreign.predefinito is True
    rows = client.get('/api/deposits').json()
    assert len(rows) == 2 and sum(row['predefinito'] for row in rows) == 1
    updated = client.put(f"/api/deposits/{item.id}", json={'nome':'Aggiornato','indirizzo':'Via Nuova','predefinito':True}).json()
    assert datetime.fromisoformat(updated['updated_at']) > datetime(2020, 1, 1)
    assert client.put(f'/api/deposits/{foreign.id}', json={'nome':'No','indirizzo':'No'}).status_code == 404
    assert client.delete(f'/api/deposits/{foreign.id}').status_code == 404
    assert client.delete(f"/api/deposits/{second['id']}").status_code == 200
    assert len(client.get('/api/deposits').json()) == 1


def test_deposit_timestamp_migration_keeps_legacy_dates_unknown_and_is_repeatable(env):
    import ast
    from pathlib import Path
    import sqlalchemy
    from app.database import Base
    from app.models import Deposit
    client, db, owner, *_ = env
    item = Deposit(user_id=owner.id, nome='Storico', indirizzo='Via Roma')
    db.add(item)
    db.commit()
    item_id = item.id
    engine = db.get_bind()
    db.close()
    with engine.begin() as conn:
        conn.execute(sqlalchemy.text('ALTER TABLE deposits DROP COLUMN updated_at'))
    tree = ast.parse(Path('app/main.py').read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'migrate_database')
    namespace = {**vars(sqlalchemy), 'Base': Base, 'engine': engine}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<migration>', 'exec'), namespace)
    namespace['migrate_database']()
    namespace['migrate_database']()
    with engine.connect() as conn:
        row = conn.execute(sqlalchemy.text('SELECT nome, updated_at FROM deposits WHERE id=:id'), {'id':item_id}).one()
        assert row.nome == 'Storico' and row.updated_at is None
