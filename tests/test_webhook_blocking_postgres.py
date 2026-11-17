"""Un webhook ordini fermo su una riga bloccata non deve rallentare le altre richieste."""
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from test_audit_postgres import pg


def test_waiting_webhook_does_not_slow_down_other_requests(pg):
    from app.database import Base, get_db
    from app.models import User
    from app.order_models import OrderSource
    from app.routers.order_connectors import router
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        owner = User(username='negozio', password_hash='test'); db.add(owner); db.flush()
        db.add(OrderSource(user_id=owner.id, key='hook-key', name='Shop', kind='api', status='active',
                           configuration={'connector': 'shopify', 'store': 'x.myshopify.com'}))
        db.commit(); owner_id = owner.id
    sessions = sessionmaker(bind=pg)
    app = FastAPI(); app.include_router(router)

    def session():
        db = sessions()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = session

    @app.get('/ping')
    async def ping():
        return {'ok': True}

    result = {}
    with TestClient(app) as client, Session(pg) as holder:
        # Un'altra operazione tiene bloccata l'azienda del negozio.
        holder.query(User).filter_by(id=owner_id).with_for_update().one()

        def hook():
            started = time.monotonic()
            result['hook'] = client.post('/api/order-connectors/hooks/hook-key', content=b'{}',
                                         headers={'content-type': 'application/json'})
            result['hook_seconds'] = time.monotonic() - started
        worker = threading.Thread(target=hook); worker.start()
        time.sleep(0.5)  # il webhook ora aspetta la riga bloccata
        started = time.monotonic()
        assert client.get('/ping').status_code == 200
        ping_seconds = time.monotonic() - started
        worker.join(15)
        holder.rollback()
    assert ping_seconds < 0.5, ping_seconds
    # L'attesa del blocco è limitata: il negozio riceve «riprova» invece di restare appeso.
    assert result['hook'].status_code == 503
    assert result['hook_seconds'] < 9
