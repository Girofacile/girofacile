"""Separate company management and anonymous read-only tracking endpoints."""
from pathlib import Path
from collections import OrderedDict
import threading
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from ..core.config import APP_BASE_URL
from ..core.dependencies import current_user
from ..core.http_security import _client_ip
from ..database import get_db
from ..models import DeliveryTrackingLink, User
from ..services.delivery_tracking import PUBLIC_HEADERS, credential, ensure_link, owned_delivery, public_projection, resolve_link

router = APIRouter(tags=['tracking'])
_requests = OrderedDict()
_lock = threading.Lock()


def tracking_limit(request: Request):
    # Bounded per-process protection, like existing login throttling. At scale
    # also apply a shared limit to /api/public/tracking at the reverse proxy.
    now = time.monotonic()
    key = _client_ip(request)
    with _lock:
        start, count = _requests.pop(key, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        _requests[key] = (start, count + 1)
        while len(_requests) > 10000:
            _requests.popitem(last=False)
        if count >= 120:
            raise HTTPException(429, 'Riprova tra un minuto', headers={**PUBLIC_HEADERS, 'Retry-After': '60'})


@router.get('/tracking', include_in_schema=False)
def tracking_page():
    return FileResponse(Path(__file__).resolve().parents[2] / 'static/tracking/index.html', headers={
        **PUBLIC_HEADERS,
        'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    })


@router.get('/api/public/tracking', dependencies=[Depends(tracking_limit)])
def read_tracking(x_tracking_token: str = Header(default=''), db: Session = Depends(get_db)):
    delivery, plan = resolve_link(db, x_tracking_token)
    return JSONResponse(public_projection(db, delivery, plan), headers=PUBLIC_HEADERS)


@router.post('/api/deliveries/{delivery_id}/tracking')
def get_tracking_link(delivery_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    delivery, plan = owned_delivery(db, user, delivery_id)
    link = ensure_link(db, delivery, plan)
    url = f'{APP_BASE_URL}/tracking#{credential(link)}'
    expires = link.expires_at.isoformat() + 'Z'
    db.commit()
    return JSONResponse({'url': url, 'expires_at': expires}, headers=PUBLIC_HEADERS)


@router.delete('/api/deliveries/{delivery_id}/tracking')
def revoke_tracking_link(delivery_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_delivery(db, user, delivery_id)
    db.query(DeliveryTrackingLink).filter_by(delivery_id=delivery_id).delete(synchronize_session=False)
    db.commit()
    return JSONResponse({'ok': True}, headers=PUBLIC_HEADERS)
