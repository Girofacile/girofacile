"""Le note datate dalla migrazione 20261118_02 tornano «ora sconosciuta»; quelle con l'ora vera restano."""
from datetime import date, time, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from test_audit_postgres import pg


def test_migration_time_is_removed_and_real_times_are_kept(pg):
    from app.database import Base
    from app.migrations import run_migrations, VERSIONS
    from app.models import User, RoutePlan, Delivery, DeliveryStatus
    Base.metadata.create_all(pg)
    applied_02 = datetime(2026, 11, 18, 11, 0, 1, 928131)
    stamped = applied_02 - timedelta(microseconds=722)  # come sul server: pochi istanti prima
    real = datetime(2026, 11, 18, 10, 30)
    with Session(pg) as db:
        owner = User(username='note', password_hash='test'); db.add(owner); db.flush()
        route = RoutePlan(user_id=owner.id, nome='Giro', data_giro=date.today(), orario_partenza=time(8), status='in_corso')
        db.add(route); db.flush()
        stops = [Delivery(route_plan_id=route.id, cliente_nome=n, indirizzo='Via') for n in ('A', 'B', 'C', 'D')]
        db.add_all(stops); db.flush()
        db.add_all([DeliveryStatus(delivery_id=stops[0].id, route_plan_id=route.id, status='in_attesa',
                                   note_operatore='Nota storica', note_scritta_il=stamped),
                    DeliveryStatus(delivery_id=stops[1].id, route_plan_id=route.id, status='in_attesa',
                                   note_operatore='Nota con ora vera', note_scritta_il=real),
                    # Ore autentiche vicinissime a quella sintetica: non vanno toccate.
                    DeliveryStatus(delivery_id=stops[2].id, route_plan_id=route.id, status='in_attesa',
                                   note_operatore='Autentica a 3 s', note_scritta_il=applied_02 - timedelta(seconds=3)),
                    DeliveryStatus(delivery_id=stops[3].id, route_plan_id=route.id, status='in_attesa',
                                   note_operatore='Autentica a 0,5 s', note_scritta_il=applied_02 - timedelta(milliseconds=500))])
        db.commit()
    with pg.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in VERSIONS:
            if version != '20261118_03':
                conn.execute(text('INSERT INTO schema_migrations(version, applied_at) VALUES (:v, :t)'),
                             {'v': version, 't': applied_02 if version == '20261118_02' else None})
    run_migrations(pg); run_migrations(pg)
    with Session(pg) as db:
        by_note = {s.note_operatore: s.note_scritta_il for s in db.query(DeliveryStatus)}
    assert by_note == {'Nota storica': None, 'Nota con ora vera': real,
                       'Autentica a 3 s': applied_02 - timedelta(seconds=3),
                       'Autentica a 0,5 s': applied_02 - timedelta(milliseconds=500)}


def test_a_database_that_never_ran_the_old_update_keeps_every_time(pg):
    from app.database import Base
    from app.migrations import run_migrations, VERSIONS
    from app.models import User, RoutePlan, Delivery, DeliveryStatus
    from app.core.clock import utc_now
    Base.metadata.create_all(pg)
    just_now = utc_now() - timedelta(milliseconds=200)
    with Session(pg) as db:
        owner = User(username='nuovo', password_hash='test'); db.add(owner); db.flush()
        route = RoutePlan(user_id=owner.id, nome='Giro', data_giro=date.today(), orario_partenza=time(8), status='in_corso')
        db.add(route); db.flush()
        stop = Delivery(route_plan_id=route.id, cliente_nome='A', indirizzo='Via'); db.add(stop); db.flush()
        db.add(DeliveryStatus(delivery_id=stop.id, route_plan_id=route.id, status='in_attesa',
                              note_operatore='Scritta un attimo fa', note_scritta_il=just_now))
        db.commit()
    with pg.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in VERSIONS:
            if version not in ('20261118_02', '20261118_03'):
                conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v': version})
    run_migrations(pg)
    with Session(pg) as db:
        assert db.query(DeliveryStatus).one().note_scritta_il == just_now
