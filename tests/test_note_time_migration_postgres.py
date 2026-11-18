"""Le note salvate prima dell'ora di scrittura ricevono un'ora: una nota vecchia in coda non le sovrascrive."""
from datetime import date, time, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from test_audit_postgres import pg


def test_notes_saved_before_the_write_time_get_one_and_resist_old_queued_notes(pg):
    from app.database import Base
    from app.migrations import run_migrations, VERSIONS
    from app.models import User, RoutePlan, Delivery, DeliveryStatus
    from app.services.route_execution import written_at
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        owner = User(username='note', password_hash='test'); db.add(owner); db.flush()
        route = RoutePlan(user_id=owner.id, nome='Giro', data_giro=date.today(), orario_partenza=time(8), status='in_corso')
        db.add(route); db.flush()
        with_note, without = (Delivery(route_plan_id=route.id, cliente_nome=n, indirizzo='Via') for n in ('A', 'B'))
        db.add_all([with_note, without]); db.flush()
        db.add_all([DeliveryStatus(delivery_id=with_note.id, route_plan_id=route.id, status='in_attesa', note_operatore='Nota già accettata'),
                    DeliveryStatus(delivery_id=without.id, route_plan_id=route.id, status='in_attesa')])
        db.commit()
    with pg.begin() as conn:
        conn.execute(text('CREATE TABLE schema_migrations (version VARCHAR(40) PRIMARY KEY, applied_at TIMESTAMP)'))
        for version in VERSIONS:
            if version != '20261118_02':
                conn.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v': version})
    run_migrations(pg); run_migrations(pg)
    with Session(pg) as db:
        noted = db.query(DeliveryStatus).filter(DeliveryStatus.note_operatore.isnot(None)).one()
        empty = db.query(DeliveryStatus).filter(DeliveryStatus.note_operatore.is_(None)).one()
        assert noted.note_scritta_il is not None and empty.note_scritta_il is None
        # Una nota accodata ieri dalla vecchia coda è più vecchia: il server la ignora.
        queued = written_at({'scritta_il': datetime(2026, 11, 17, 8, 0)})
        assert queued <= noted.note_scritta_il
