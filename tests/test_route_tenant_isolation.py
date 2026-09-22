from types import SimpleNamespace
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ALLOW_SQLITE_LEGACY", "true")

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Customer, Deposit, Driver, User, Vehicle
from app.routers.routes import _owned_customer_map, _validate_route_tenant_scope


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_two_companies(db: Session):
    a = User(username="azienda-a", password_hash="x")
    b = User(username="azienda-b", password_hash="x")
    db.add_all([a, b])
    db.flush()

    dep_a = Deposit(user_id=a.id, nome="Deposito A", indirizzo="Via A")
    vehicle_a = Vehicle(user_id=a.id, nome="Furgone A")
    vehicle_b = Vehicle(user_id=b.id, nome="Furgone B")
    driver_a = Driver(user_id=a.id, nome="Mario")
    customer_a = Customer(user_id=a.id, nome="Cliente A", indirizzo="Via Cliente A")
    customer_b = Customer(user_id=b.id, nome="Cliente B", indirizzo="Via Cliente B")
    db.add_all([dep_a, vehicle_a, vehicle_b, driver_a, customer_a, customer_b])
    db.commit()
    for item in (a, b, dep_a, vehicle_a, vehicle_b, driver_a, customer_a, customer_b):
        db.refresh(item)
    return a, b, dep_a, vehicle_a, vehicle_b, driver_a, customer_a, customer_b


def test_foreign_customer_id_is_rejected():
    db = _db()
    try:
        a, _b, _dep_a, _vehicle_a, _vehicle_b, _driver_a, _customer_a, customer_b = _seed_two_companies(db)
        with pytest.raises(HTTPException) as exc:
            _owned_customer_map(db, a, [{"customer_id": customer_b.id}])
        assert exc.value.status_code == 400
        assert "questa azienda" in str(exc.value.detail)
    finally:
        db.close()


def test_route_resources_and_customers_must_belong_to_same_company():
    db = _db()
    try:
        a, _b, dep_a, vehicle_a, vehicle_b, driver_a, customer_a, _customer_b = _seed_two_companies(db)
        valid = SimpleNamespace(deposit_id=dep_a.id, vehicle_id=vehicle_a.id, driver_id=driver_a.id)
        deliveries = [{"customer_id": customer_a.id, "lat": None, "lon": None}]
        deposit, vehicle, driver = _validate_route_tenant_scope(db, a, valid, deliveries)
        assert deposit.id == dep_a.id
        assert vehicle.id == vehicle_a.id
        assert driver.id == driver_a.id

        invalid_vehicle = SimpleNamespace(deposit_id=dep_a.id, vehicle_id=vehicle_b.id, driver_id=driver_a.id)
        with pytest.raises(HTTPException) as exc:
            _validate_route_tenant_scope(db, a, invalid_vehicle, deliveries)
        assert exc.value.status_code == 400
        assert exc.value.detail == "Mezzo non trovato"
    finally:
        db.close()
