"""GPS migration, concurrency and cascade checks on disposable PostgreSQL schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time, datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from fastapi import HTTPException

from test_audit_postgres import pg


def seed(pg):
    from app.database import Base
    from app.models import User, Driver, RoutePlan, Delivery
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        owner = User(username='gps',password_hash='test');db.add(owner);db.flush()
        driver = Driver(user_id=owner.id,nome='Driver');db.add(driver);db.flush()
        plan = RoutePlan(user_id=owner.id,driver_id=driver.id,nome='GPS',data_giro=date.today(),orario_partenza=time(8),status='in_corso')
        db.add(plan);db.flush()
        db.add(Delivery(route_plan_id=plan.id,cliente_nome='Preserved',indirizzo='Private'))
        db.commit()
        return plan.id


def test_gps_migration_preserves_existing_data_and_repeats(pg):
    from app.models import RoutePosition, Delivery
    from app.migrations import run_migrations, require_current_schema, LATEST
    seed(pg)
    RoutePosition.__table__.drop(pg)
    with pg.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in ('20261004_01','20261004_02','20261004_03','20261004_04'):
            conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'),{'v':version})
    run_migrations(pg);run_migrations(pg);require_current_schema(pg)
    assert inspect(pg).has_table('route_positions')
    with Session(pg) as db:
        assert db.query(Delivery).one().cliente_nome == 'Preserved'
        assert db.query(RoutePosition).count() == 0
        assert db.execute(text('SELECT count(*) FROM schema_migrations WHERE version=:v'),{'v':LATEST}).scalar() == 1


def test_concurrent_uploads_produce_one_snapshot_and_one_eta_attempt(pg):
    from app.models import RoutePlan, RoutePosition
    from app.services.live_position import record_position, PositionInput
    route_id=seed(pg)
    def upload(_):
        with Session(pg) as db:
            return record_position(db, db.get(RoutePlan,route_id), PositionInput(latitude=45,longitude=9,accuracy=10,captured_at=datetime.now(timezone.utc)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(upload,range(4)))
    assert sum(r['accepted'] for r in results) == 1
    with Session(pg) as db:
        assert db.query(RoutePosition).count() == 1
        # Real database cascade, including a route removed without loading relationships.
        db.execute(text('DELETE FROM route_plans WHERE id=:id'),{'id':route_id});db.commit()
        assert db.query(RoutePosition).count() == 0


def test_completion_racing_with_upload_cannot_leave_position(pg):
    from app.models import RoutePlan, RoutePosition
    from app.services.live_position import record_position, PositionInput
    from app.services.route_execution import mark_completed
    route_id=seed(pg)
    def upload():
        with Session(pg) as db:
            try:
                record_position(db,db.get(RoutePlan,route_id),PositionInput(latitude=45,longitude=9,accuracy=10,captured_at=datetime.now(timezone.utc)))
            except HTTPException as exc:
                assert exc.status_code == 409
    def close():
        with Session(pg) as db:
            plan=db.query(RoutePlan).filter_by(id=route_id).with_for_update().one()
            mark_completed(plan);db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(upload),pool.submit(close)]
        for future in futures:future.result()
    with Session(pg) as db:
        assert db.get(RoutePlan,route_id).status == 'completato'
        assert db.query(RoutePosition).count() == 0
