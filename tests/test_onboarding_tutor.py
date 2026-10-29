from datetime import date, time
from test_agents_feature import env


def _steps(client):
    data = client.get('/api/onboarding/tutor').json()
    return data, {step['key']: step['done'] for step in data['steps']}


def test_tutor_advances_on_real_data_and_completes_with_first_programmed_route(env):
    from app.models import Deposit, Driver, RoutePlan, Vehicle
    from app.order_models import Order, OrderSource
    from app.routers import auth
    client, db, owner, other, *_ = env
    client.app.include_router(auth.router)
    owner.company_name, owner.company_address = 'Panificio Rossi', None
    db.commit()

    data, done = _steps(client)
    assert data['state'] == 'attivo' and data['current'] == 'company' and data['total'] == 7
    assert client.get('/api/onboarding/status').json()['tutor_pending'] is True

    owner.company_address = 'Via Emilia 112, Bologna'
    db.add_all([Deposit(user_id=owner.id, nome='Magazzino', indirizzo='Via Emilia 112'),
                Vehicle(user_id=owner.id, nome='Furgone'), Driver(user_id=owner.id, nome='Marco')])
    # I dati di un'altra azienda non fanno avanzare il tutor.
    db.add(RoutePlan(user_id=other.id, nome='Altro', data_giro=date.today(), orario_partenza=time(8), status='programmato'))
    db.commit()
    data, done = _steps(client)
    assert data['current'] == 'orders' and data['progress'] == 4 and not done['program']

    source = OrderSource(user_id=owner.id, key='manuale', name='Manuale', kind='manual')
    db.add(source)
    db.flush()
    db.add(Order(user_id=owner.id, source_id=source.id, external_id='1', number='1', status='nuovo', original_payload={}, operational_data={}))
    db.add(RoutePlan(user_id=owner.id, nome='Bozza', data_giro=date.today(), orario_partenza=time(8), status='bozza'))
    db.commit()
    data, _ = _steps(client)
    assert data['current'] == 'program' and data['state'] == 'attivo'

    db.add(RoutePlan(user_id=owner.id, nome='Primo giro', data_giro=date.today(), orario_partenza=time(8), status='programmato'))
    db.commit()
    data, done = _steps(client)
    assert data['state'] == 'completato' and data['current'] is None and all(done.values())
    assert owner.tutor_completed_at is not None
    # Completato resta completato: non si riapre né si chiude.
    assert client.post('/api/onboarding/tutor', json={'action': 'resume'}).json()['state'] == 'completato'
    assert client.get('/api/onboarding/status').json()['tutor_pending'] is False
    # Riavvio (provvisorio): riparte, ma con un giro già programmato risulta subito completata.
    assert client.post('/api/onboarding/tutor', json={'action': 'restart'}).json()['state'] == 'completato'


def test_tutor_close_and_resume_are_saved_on_server(env):
    from app.routers import auth
    client, db, owner, *_ = env
    client.app.include_router(auth.router)
    assert client.post('/api/onboarding/tutor', json={'action': 'close'}).json()['state'] == 'chiuso'
    db.refresh(owner)
    assert owner.tutor_state == 'chiuso'
    assert client.get('/api/onboarding/tutor').json()['state'] == 'chiuso'
    assert client.post('/api/onboarding/tutor', json={'action': 'resume'}).json()['state'] == 'attivo'
    owner.tutor_state = 'completato'
    db.commit()
    assert client.post('/api/onboarding/tutor', json={'action': 'restart'}).json()['state'] == 'attivo'
    assert owner.tutor_state is None and owner.tutor_completed_at is None
    assert client.post('/api/onboarding/tutor', json={'action': 'boh'}).status_code == 400


def test_tutor_migration_marks_companies_with_a_route_as_completed_and_is_repeatable():
    from sqlalchemy import create_engine, text, inspect
    from app.migrations import run_migrations, require_current_schema
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)'))
        conn.execute(text('CREATE TABLE route_plans (id INTEGER PRIMARY KEY, user_id INTEGER, status TEXT)'))
        conn.execute(text("INSERT INTO users VALUES (1,'con-giro'),(2,'solo-bozza'),(3,'nuovo')"))
        conn.execute(text("INSERT INTO route_plans VALUES (1,1,'completato'),(2,2,'bozza')"))
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in ('20261004_01', '20261004_02', '20261004_03', '20261004_04', '20261006_01', '20261009_01',
                        '20261009_02', '20261010_01', '20261010_02', '20261011_01', '20261011_02', '20261013_01',
                        '20261013_02', '20261020_01', '20261020_02', '20261023_01', '20261027_01', '20261027_02'):
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v': version})
    run_migrations(engine)
    run_migrations(engine)
    require_current_schema(engine)
    assert {'tutor_state', 'tutor_completed_at'} <= {c['name'] for c in inspect(engine).get_columns('users')}
    with engine.connect() as conn:
        states = dict(conn.execute(text('SELECT username, tutor_state FROM users')).all())
    assert states == {'con-giro': 'completato', 'solo-bozza': None, 'nuovo': None}
    engine.dispose()
