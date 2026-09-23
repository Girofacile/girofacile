import io
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_agents_feature import env


def seed_route(env):
    from app.models import Driver, DriverAccount, RoutePlan, Delivery, RouteToken
    client, db, owner, _, _, _, customer, *_ = env
    driver = Driver(user_id=owner.id, nome='Autista test')
    db.add(driver); db.flush()
    account = DriverAccount(driver_id=driver.id, email='driver@example.test', password_hash='test')
    route = RoutePlan(user_id=owner.id, driver_id=driver.id, nome='Test',
                      data_giro=date.today()+timedelta(days=1), orario_partenza=time(8), status='in_corso')
    db.add_all([account, route]); db.flush()
    delivery = Delivery(route_plan_id=route.id, customer_id=customer.id, cliente_nome='Test', indirizzo='Via Test')
    db.add(delivery)
    db.add(RouteToken(route_plan_id=route.id, token='test-route', expires_at=datetime.utcnow()+timedelta(days=1)))
    owner.delivery_signature_enabled = True
    db.commit()
    return route, delivery, account


@pytest.mark.parametrize('portal', ['operator', 'driver'])
def test_signature_required_for_every_completion_portal(env, portal):
    from app.routers import operator, driver
    from app.models import DeliveryStatus
    client, db, owner, *_ = env
    route, delivery, account = seed_route(env)
    client.app.include_router(operator.router)
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    path = f'/api/operator/test-route/delivery/{delivery.id}/complete' if portal == 'operator' else f'/api/driver/delivery/{delivery.id}/complete'
    assert client.post(path, json={}).status_code == 400
    state = db.query(DeliveryStatus).filter_by(delivery_id=delivery.id).one()
    assert state.status == 'in_attesa'
    assert client.post(path, json={'signature_data': 'data:image/png;base64,AA=='}).status_code == 400
    assert client.post(path, json={'signature_data': 'data:image/png;base64,AA==', 'signed_by_name': 'Mario'}).status_code == 200
    assert state.status == 'completata' and state.signed_by_name == 'Mario'
    assert route.status == 'completato'


def test_operator_signature_optional_when_company_disables_it(env):
    from app.routers import operator
    client, db, owner, *_ = env
    _, delivery, _ = seed_route(env)
    owner.delivery_signature_enabled = False
    db.commit()
    client.app.include_router(operator.router)
    assert client.post(f'/api/operator/test-route/delivery/{delivery.id}/complete', json={}).status_code == 200


@pytest.mark.parametrize('mode', ['agent', 'company_import', 'agent_import'])
def test_customer_quotas_cover_every_creation_path(env, monkeypatch, mode):
    from app.services.plans import PLAN_LIMITS
    from app.routers.agent import make_session_token
    from app.models import Customer
    client, db, owner, _, _, _, existing, account, *_ = env
    owner.agents_enabled = True
    db.commit()
    monkeypatch.setitem(PLAN_LIMITS['business'], 'max_customers', 1)
    client.cookies.set('agent_session', make_session_token(account))
    if mode == 'agent':
        response = client.post('/api/agent/customers', json={'nome':'Extra','indirizzo':'Via Extra'})
    else:
        path = '/api/agent/customers/import' if mode == 'agent_import' else '/api/customers/import'
        data = b'codice_cliente,nome,indirizzo\nC1,Changed,Via Updated\nC2,Extra,Via Extra\n'
        response = client.post(path, files={'file':('data.csv',data,'text/csv')})
    assert response.status_code == 403
    assert db.query(Customer).filter_by(user_id=owner.id).count() == 1
    assert existing.nome == 'Esistente'  # quota failure must not partly apply an import


def test_import_updates_at_quota_and_counts_repeated_codes_once(env, monkeypatch):
    from app.services.plans import PLAN_LIMITS
    client, db, owner, *_ = env
    monkeypatch.setitem(PLAN_LIMITS['business'], 'max_customers', 1)
    response = client.post('/api/customers/import', files={'file':('data.csv',b'codice_cliente,nome,indirizzo\nC1,Updated,Via Test\n','text/csv')})
    assert response.status_code == 200 and response.json()['updated'] == 1
    monkeypatch.setitem(PLAN_LIMITS['business'], 'max_customers', 2)
    response = client.post('/api/customers/import', files={'file':('data.csv',b'codice_cliente,nome,indirizzo\nC2,New,Via Test\nC2,New twice,Via Test\n','text/csv')})
    assert response.status_code == 200
    assert response.json() == {'created': 1, 'updated': 1}


def test_route_quota_also_guards_manual_creation_and_allows_existing_edit(env, monkeypatch):
    from app.services.plans import PLAN_LIMITS, check_daily_route_limit
    from app.routers import routes
    from app.schemas import ManualRoutePlanIn
    from app.models import Deposit
    client, db, owner, *_ = env
    route, _, _ = seed_route(env)
    monkeypatch.setitem(PLAN_LIMITS['business'], 'max_routes_per_day', 1)
    check_daily_route_limit(owner, db, route.data_giro, exclude_route_id=route.id)
    dep = Deposit(user_id=owner.id, nome='Depot', indirizzo='Via Test')
    db.add(dep); db.commit()
    data = ManualRoutePlanIn(data_giro=route.data_giro.isoformat(), deposit_id=dep.id, consegne=[])
    monkeypatch.setattr(routes, 'recalculate_manual_route', lambda *a,**k: pytest.fail('Google must not be called at quota'))
    with pytest.raises(HTTPException) as exc:
        routes.recalc_manual_route(data, None, db, owner)
    assert exc.value.status_code == 403


@pytest.mark.parametrize('cargo,capacity', [([{'peso_kg':101}],{'capacita_kg':100}),
    ([{'colli':3},{'colli':3}],{'capacita_colli':5}), ([{'peso_kg':-1}],{}), ([{'peso_kg':float('nan')}],{})])
def test_invalid_or_excess_vehicle_load_is_rejected(cargo, capacity):
    from app.optimizer import validate_vehicle_load
    with pytest.raises(ValueError): validate_vehicle_load(cargo, capacity)


def test_exact_capacity_and_unassigned_vehicle_are_supported():
    from app.optimizer import validate_vehicle_load
    validate_vehicle_load([{'peso_kg':50,'colli':2},{'peso_kg':50,'colli':3}],{'capacita_kg':100,'capacita_colli':5})
    validate_vehicle_load([{'peso_kg':100}], None)


@pytest.mark.parametrize('day,expected', [('2030-01-15','2030-01-15T07:00:00Z'),('2030-07-15','2030-07-15T06:00:00Z')])
def test_departure_uses_real_date_and_rome_timezone(day, expected, monkeypatch):
    from app import optimizer
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(optimizer, 'LOCAL_TZ', ZoneInfo('Europe/Rome'))
    monkeypatch.setattr(optimizer, 'local_now', lambda: datetime(2029,1,1,tzinfo=timezone.utc))
    assert optimizer._route_departure_time_iso('08:00', day) == expected


def test_past_departure_is_not_silently_moved_to_tomorrow(monkeypatch):
    from app import optimizer
    monkeypatch.setattr(optimizer, 'local_now', lambda: datetime(2030,1,15,12,tzinfo=timezone.utc))
    with pytest.raises(ValueError, match='già passato'):
        optimizer._route_departure_time_iso('08:00', '2030-01-15')


def test_traffic_cache_separates_departures_and_invalidates_all_versions(env, monkeypatch):
    from app import optimizer
    from app.services import distance_cache as cache
    from app.models import DistanceCache
    _, db, owner, *_ = env
    monkeypatch.setattr(optimizer, 'google_routes_enabled', lambda db: True)
    monkeypatch.setattr(optimizer, 'google_maps_api_key', lambda db: 'test')
    calls=[]
    def matrix(points, **kwargs):
        calls.append(kwargs)
        return {(0,1):{'km':1,'min':5},(1,0):{'km':1,'min':6}}
    monkeypatch.setattr(optimizer, 'google_route_matrix', matrix)
    monkeypatch.setattr(optimizer, 'local_now', lambda: datetime(2029,1,1,tzinfo=timezone.utc))
    keys=[cache.deposit_key(1,user_id=owner.id),cache.customer_key(1,user_id=owner.id)]
    for clock in ['08:00','08:00','09:00']:
        optimizer.build_distance_matrix(db,owner.id,[{},{}],keys,clock,route_date='2030-01-15')
    assert len(calls)==2
    assert calls[0]['route_date']=='2030-01-15'
    cache.invalidate_key(db,keys[1],user_id=owner.id)
    assert db.query(DistanceCache).count()==0


def test_manual_route_respects_same_optional_preferences(env):
    from app.routers.routes import _apply_route_preferences
    _, db, owner, *_ = env
    owner.has_time_windows=False;owner.has_ztl=False;owner.needs_tail_lift=False
    rows=[{'scarico_mattina_da':'08:00','ztl':True,'sponda':True}]
    _apply_route_preferences(owner,rows)
    assert rows[0]['scarico_mattina_da'] is None
    assert rows[0]['ztl'] is False and rows[0]['sponda'] is False


def test_backup_discovery_supports_dump_and_legacy_files(tmp_path,monkeypatch):
    from app.services import backups
    monkeypatch.setattr(backups,'PROJECT_ROOT',tmp_path)
    monkeypatch.setenv('BACKUP_DIR','backups')
    main=backups.backup_directory()
    (main/'valid.dump').write_bytes(b'test')
    (main/'unfinished.partial').write_bytes(b'test')
    legacy=tmp_path/'data'/'backups';legacy.mkdir(parents=True)
    (legacy/'old.zip').write_bytes(b'test')
    assert {p.name for p in backups.backup_files()} == {'valid.dump','old.zip'}
    assert backups.resolve_backup('valid.dump')==main/'valid.dump'
    with pytest.raises(ValueError):backups.resolve_backup('../valid.dump')


def test_failed_backup_never_leaves_a_downloadable_archive(tmp_path,monkeypatch):
    from scripts import backup_database as backup
    import subprocess
    monkeypatch.setattr(backup.shutil,'which',lambda command:command)
    def fail(command,**kwargs):
        Path(command[-1]).write_bytes(b'incomplete')
        raise subprocess.CalledProcessError(1,command)
    monkeypatch.setattr(backup.subprocess,'run',fail)
    with pytest.raises(RuntimeError):backup.backup_postgres('postgresql://u:secret@localhost/test',tmp_path)
    assert list(tmp_path.iterdir())==[]


def test_backup_credentials_are_not_in_command_arguments():
    from scripts.backup_database import postgres_connection
    url,env=postgres_connection('postgresql+psycopg2://u:s%40cret@localhost:5432/test?sslmode=require')
    assert 's%40cret' not in url and 'sslmode=require' in url
    assert env['PGPASSWORD']=='s@cret'
