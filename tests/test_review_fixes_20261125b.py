"""Seconda revisione del 25/11/2026: traffico e sovrapposizioni, codici ripetuti, esiti offline, date, modelli."""
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from test_company_collaborators import company  # noqa: F401  (fixture)
from test_agents_feature import env  # noqa: F401  (fixture)
from test_routing_architecture import routing_env, saved_route  # noqa: F401


def test_traffic_refresh_cannot_push_a_route_into_another_one(routing_env, monkeypatch):
    from app.models import RoutePlan
    from app.routers import routes
    client, db = routing_env[0], routing_env[1]
    draft = saved_route(routing_env, two=True)
    assert client.post(f"/api/routes/{draft['id']}/program", json={}).status_code == 200
    route = db.get(RoutePlan, draft['id'])
    start = route.orario_partenza.hour * 60 + route.orario_partenza.minute
    before = int(route.totale_minuti or 0)
    assert route.vehicle_id, 'il giro di prova deve avere un mezzo'
    # Un altro giro dello stesso mezzo subito dopo la fine prevista.
    later = (datetime.combine(date.today(), time(0)) + timedelta(minutes=start + before + 30)).time()
    db.add(RoutePlan(user_id=route.user_id, nome='Secondo giro', status='programmato', data_giro=route.data_giro,
                     orario_partenza=later, totale_minuti=60, vehicle_id=route.vehicle_id))
    db.commit()

    def slower(db_, plan, **_):
        plan.totale_minuti = before + 120  # traffico: due ore in più
    monkeypatch.setattr(routes, 'enrich_final_route', slower)
    response = client.post(f"/api/routes/{route.id}/refresh-traffic")
    assert response.status_code == 400 and 'Mezzo non disponibile' in response.json()['detail'], response.text
    db.expire_all()
    assert int(db.get(RoutePlan, route.id).totale_minuti or 0) == before  # nulla è stato salvato


def test_repeated_codes_in_one_file_update_the_same_customer(company):
    from app.models import Customer
    client, db, owner, *_, login_owner, _ = company
    login_owner()
    csv = b'codice_cliente,nome,indirizzo\nR1,Prima riga,Via Uno\nR1,Seconda riga,Via Due\n'
    response = client.post('/api/customers/import', files={'file': ('c.csv', csv, 'text/csv')})
    assert response.status_code == 200, response.text
    assert response.json() == {'created': 1, 'updated': 0}
    saved = db.query(Customer).filter_by(user_id=owner.id, codice_cliente='R1').all()
    assert [(c.nome, c.indirizzo) for c in saved] == [('Seconda riga', 'Via Due')]


def test_offline_outcome_keeps_the_time_written_on_the_phone():
    from app.core.utils import LOCAL_TZ
    from app.services.route_execution import executed_at
    route = SimpleNamespace(started_at=datetime(2026, 11, 25, 7, 30))
    phone = datetime(2026, 11, 25, 9, 0, tzinfo=LOCAL_TZ)  # esito alle 9:00, sincronizzato più tardi
    assert executed_at({'scritta_il': phone}, route) == datetime(2026, 11, 25, 9, 0)
    # Orologio del telefono indietro: mai prima della partenza del giro.
    wrong = datetime(2026, 11, 25, 6, 0, tzinfo=LOCAL_TZ)
    assert executed_at({'scritta_il': wrong}, route) == datetime(2026, 11, 25, 7, 30)
    # Senza ora dal telefono vale l'ora di arrivo.
    before = datetime.now(timezone.utc).astimezone(LOCAL_TZ).replace(tzinfo=None) - timedelta(seconds=1)
    assert executed_at({'scritta_il': None}, SimpleNamespace(started_at=None)) >= before


def test_compact_dates_in_both_orders():
    from app.services.order_files import requested_date
    assert requested_date('25112026') == '2026-11-25'
    assert requested_date('18112026') == '2026-11-18'
    assert requested_date('20261125') == '2026-11-25'
    assert requested_date('01022027') == '2027-02-01'


def test_collaborators_can_download_the_import_templates(company):
    from app.services.company_permissions import normalize_permissions
    client, *_, login_actor = company
    login_actor(normalize_permissions(['customers.read']))
    assert client.get('/api/customers/import-template.xlsx').status_code == 403
    login_actor(normalize_permissions(['customers.read', 'customers.create']))
    assert client.get('/api/customers/import-template.xlsx').status_code == 200
    from app.routers import order_sources
    client.app.include_router(order_sources.router)  # non incluso nell'app di prova dei collaboratori
    login_actor(normalize_permissions(['orders.read']))
    assert client.get('/api/order-files/template.xlsx').status_code == 403
    login_actor(normalize_permissions(['orders.read', 'orders.import']))
    assert client.get('/api/order-files/template.xlsx').status_code == 200
