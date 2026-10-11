"""Dedicated bearer credentials, bounded ingress and per-source shared throttling."""
import hashlib
import hmac
import secrets
import re
import time
import threading
from collections import OrderedDict
from datetime import datetime,timedelta
from fastapi import HTTPException
from starlette.responses import JSONResponse
from ..schemas.order_sources import MAX_BYTES
from ..models import User
from ..order_models import OrderSource
from .order_ingestion import source


class IngestionBodyLimit:
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method') not in ('POST','PUT') or not scope.get('path','').startswith(('/api/order-sources','/api/order-ingestion')):
            return await self.app(scope,receive,send)
        content=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect': return
            content.extend(message.get('body',b''))
            if len(content)>MAX_BYTES+65536:
                return await JSONResponse({'detail':'Richiesta troppo grande: massimo 2 MB più intestazioni del file.'},status_code=413)(scope,receive,send)
            if not message.get('more_body'): break
        delivered=False
        async def replay():
            nonlocal delivered
            if delivered: return await receive()
            delivered=True
            return {'type':'http.request','body':bytes(content),'more_body':False}
        return await self.app(scope,replay,send)


_attempts=OrderedDict()
_guard=threading.Lock()

def throttle_ip(request):
    from ..core.http_security import _client_ip
    key=_client_ip(request);now=time.monotonic()
    with _guard:
        start,count=_attempts.get(key,(now,0))
        if now-start>=60: start,count=now,0
        _attempts[key]=(start,count+1);_attempts.move_to_end(key)
        while len(_attempts)>4096: _attempts.popitem(last=False)
        if count>=120: raise HTTPException(429,'Troppi invii: riprova tra un minuto.',headers={'Retry-After':'60'})


def token_hash(value): return hashlib.sha256(value.encode()).hexdigest()

def issue(src):
    token=f'gf_orders_{src.id}.'+secrets.token_urlsafe(32)
    src.credential_hash=token_hash(token)
    return token


def credential(request):
    match=re.fullmatch(r'Bearer (gf_orders_([0-9]{1,10})\.[A-Za-z0-9_-]{43})',request.headers.get('authorization',''))
    if not match: raise HTTPException(401,'Credenziale della fonte non valida.')
    return int(match[2]),match[1]


def authenticated(db,sid,token,rate=False):
    hint=db.query(OrderSource.user_id).filter_by(id=sid).scalar()
    if hint is None: raise HTTPException(401,'Credenziale della fonte non valida.')
    src=source(db,hint,sid,lock=True)
    if src.kind!='api' or not src.credential_hash or not hmac.compare_digest(src.credential_hash,token_hash(token)):
        raise HTTPException(401,'Credenziale della fonte non valida.')
    if src.status!='active': raise HTTPException(403,'La fonte è in pausa o non è attiva.')
    from .plans import require_active_plan
    require_active_plan(db.get(User,src.user_id))
    if rate:
        now=datetime.utcnow();config=dict(src.configuration)
        start=datetime.fromisoformat(config.get('_rate_start',now.isoformat()));count=config.get('_rate_count',0)
        if now-start>=timedelta(minutes=1): start,count=now,0
        if count>=60: raise HTTPException(429,'Limite tecnico: massimo 60 richieste al minuto per fonte.',headers={'Retry-After':'60'})
        config.update(_rate_start=start.isoformat(),_rate_count=count+1);src.configuration=config
        db.commit()  # Shared across workers; acquisition reacquires the lock and rechecks revocation.
    return src
