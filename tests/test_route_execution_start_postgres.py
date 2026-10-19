"""Start commands reserve resources on disposable PostgreSQL schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import time
from threading import Barrier
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from test_audit_postgres import pg


@pytest.mark.parametrize('resource', ['driver', 'vehicle'])
@pytest.mark.parametrize('commands', ['delivery_updates', 'explicit_and_delivery'])
def test_concurrent_starts_cannot_share_running_resource(pg, resource, commands):
    from app.core.utils import local_today
    from app.database import Base
    from app.models import Delivery, Driver, RoutePlan, RouteUsage, User, Vehicle
    from app.services.route_execution import apply_delivery_update
    from app.services.usage_limits import start_route_usage
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        owner = User(username='starts', password_hash='test', plan='business', plan_status='active')
        db.add(owner)
        db.flush()
        drivers = [Driver(user_id=owner.id, nome=f'Autista {i}') for i in range(2)]
        vehicle = Vehicle(user_id=owner.id, nome='Mezzo')
        db.add_all([*drivers, vehicle])
        db.flush()
        route_ids, delivery_ids = [], []
        for i in range(2):
            route = RoutePlan(user_id=owner.id, nome=f'Giro {i}', data_giro=local_today(),
                orario_partenza=time(8), status='programmato',
                driver_id=drivers[0 if resource == 'driver' else i].id,
                vehicle_id=vehicle.id if resource == 'vehicle' else None)
            db.add(route)
            db.flush()
            delivery = Delivery(route_plan_id=route.id, cliente_nome='Cliente', indirizzo='Privato')
            db.add(delivery)
            db.flush()
            route_ids.append(route.id)
            delivery_ids.append(delivery.id)
        db.commit()
    barrier = Barrier(2)
    def start(i):
        with Session(pg, autoflush=False) as db:
            route = db.get(RoutePlan, route_ids[i])
            delivery = db.get(Delivery, delivery_ids[i])
            barrier.wait(timeout=10)
            try:
                if commands == 'explicit_and_delivery' and i == 0:
                    start_route_usage(db, route)
                else:
                    apply_delivery_update(db, delivery, {'note': 'Pronti'}, 'note')
                db.commit()
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(start, range(2))) == [200, 409]
    with Session(pg) as db:
        assert db.query(RoutePlan).filter_by(status='in_corso').count() == 1
        assert db.query(RoutePlan).filter_by(status='programmato').count() == 1
        assert db.query(RouteUsage).count() == 1
