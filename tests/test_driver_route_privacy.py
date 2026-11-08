"""Il portale autista mostra percorso e orari, mai costi e pedaggi dell'azienda."""
from test_agents_feature import env
from test_stability import seed_route


def test_driver_route_detail_hides_company_costs(env):
    from app.routers import driver

    client, db, *_ = env
    route, _, account = seed_route(env)
    route.costo_carburante, route.costo_totale, route.toll_estimated_eur = 12.5, 30.0, 4.2
    db.commit()
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account

    response = client.get(f'/api/driver/routes/{route.id}')
    assert response.status_code == 200, response.text
    data = response.json()['route']
    assert 'eta_label' in data and 'traffic_status' in data
    assert not driver.DRIVER_HIDDEN_COSTS & data.keys()


def test_driver_sees_customer_phone_and_arrival_updated_by_previous_delays(env):
    """«Chiama» usa il telefono del cliente; l'arrivo previsto segue anticipi e ritardi già registrati."""
    from datetime import datetime, time
    from app.routers import driver
    from app.models import Delivery, DeliveryStatus

    client, db, owner, _, _, _, customer, *_ = env
    route, first, account = seed_route(env)
    customer.telefono = '+39 081 555 1234'
    first.ordine, first.arrivo_stimato, first.partenza_stimata = 1, time(9), time(9, 10)
    second = Delivery(route_plan_id=route.id, cliente_nome='Senza scheda', indirizzo='Via Due', ordine=2,
                      arrivo_stimato=time(10), partenza_stimata=time(10, 10))
    db.add(second); db.flush()
    # La prima consegna si chiude alle 9:40 invece delle 9:10: 30 minuti di ritardo.
    db.add(DeliveryStatus(route_plan_id=route.id, delivery_id=first.id, status='completata',
                          completata_il=datetime.combine(route.data_giro, time(9, 40))))
    db.commit()
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account

    stops = {c['id']: c for c in client.get(f'/api/driver/routes/{route.id}').json()['consegne']}
    assert stops[first.id]['telefono_cliente'] == '+39 081 555 1234'
    assert stops[second.id]['telefono_cliente'] is None
    assert stops[first.id]['arrivo_aggiornato'] is None
    assert stops[second.id]['arrivo_stimato'] == '10:00'
    assert stops[second.id]['arrivo_aggiornato'] == '10:30' and stops[second.id]['arrivo_scarto_min'] == 30


def test_driver_calls_order_recipient_when_stop_has_no_customer_card(env):
    """Consegne da ordini (es. simulatore) senza scheda cliente: «Chiama» usa il telefono dell'ordine."""
    import json
    from app.routers import driver
    from app.models import Delivery
    from app.order_models import Order, OrderSource, RouteOrderAssignment
    from app.schemas.orders import OrderData

    client, db, owner, *_ = env
    route, _, account = seed_route(env)
    source = OrderSource(user_id=owner.id, key='sim', name='Simulatore', kind='api')
    db.add(source); db.flush()
    stop = Delivery(route_plan_id=route.id, cliente_nome='DEMO Agriturismo', indirizzo='Via Luca Giordano 7', ordine=2,
                    optimizer_details=json.dumps({'order_stop_key': 'stop-1'}))
    db.add(stop)
    for i, phone in enumerate(['', '081 123 4567']):
        order = Order(user_id=owner.id, source_id=source.id, external_id=f'E{i}', number=f'N{i}', original_payload={},
                      operational_data={'phone': phone} if phone else {})
        db.add(order); db.flush()
        db.add(RouteOrderAssignment(user_id=owner.id, order_id=order.id, route_plan_id=route.id, stop_key='stop-1'))
    db.commit()
    client.app.include_router(driver.router)
    client.app.dependency_overrides[driver.get_current_driver] = lambda: account
    stops = {c['id']: c for c in client.get(f'/api/driver/routes/{route.id}').json()['consegne']}
    assert stops[stop.id]['telefono_cliente'] == '081 123 4567'
    # Il campo dell'ordine accetta solo cifre e simboli di un numero di telefono.
    assert OrderData(number='1', phone='+39 (081) 123-4567').phone == '+39 (081) 123-4567'
    import pytest
    with pytest.raises(Exception):
        OrderData(number='1', phone='javascript:alert(1)')
