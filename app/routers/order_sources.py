"""Source setup and controlled file import, separate from external bearer ingestion."""
import json
from uuid import uuid4
from fastapi import APIRouter,Depends,Request,UploadFile,File,HTTPException,Query,Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from sqlalchemy.orm import Session
from ..core.dependencies import current_user
from ..database import get_db
from ..models import User
from ..order_models import OrderSource,OrderImportRun,Order,CustomerSourceMapping
from ..schemas.order_sources import SourceCreate,SourceUpdate,SourceAction,RunConfirm,Acquisition,MAX_BYTES,MAX_ROWS
from ..services import order_ingestion as service
from ..services.order_files import read_file,suggestions,FIELDS,validate_rows
from ..services.order_source_security import issue,credential,authenticated,throttle_ip
from .orders import actor_key

router=APIRouter(tags=['order-sources'])


async def bounded_json(request):
    content=bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>MAX_BYTES: raise HTTPException(413,'Richiesta oltre 2 MB.')
    try: return json.loads(content)
    except (ValueError,UnicodeDecodeError): raise HTTPException(422,'JSON non valido.')


@router.get('/api/order-sources')
def list_sources(offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(current_user)):
    query=db.query(OrderSource).filter(OrderSource.user_id==user.id,OrderSource.kind.in_(('file','api')))
    return {'items':[service.public_source(db,s) for s in query.order_by(OrderSource.id.desc()).offset(offset).limit(50)],'total':query.count(),'offset':offset,'fields':FIELDS}


@router.post('/api/order-sources',status_code=201)
def create_source(data:SourceCreate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    db.query(User).filter_by(id=user.id).with_for_update().one()
    if db.query(OrderSource).filter(OrderSource.user_id==user.id,OrderSource.kind.in_(('file','api'))).count()>=100: raise HTTPException(422,'Limite tecnico: massimo 100 fonti per azienda.')
    src=OrderSource(user_id=user.id,key='source-'+str(uuid4()),name=data.name,kind=data.kind,status='draft',configuration={'software':data.software,'mapping':{}})
    db.add(src);db.commit();return service.public_source(db,src)


@router.put('/api/order-sources/{source_id}')
def configure(source_id:int,data:SourceUpdate,db:Session=Depends(get_db),user:User=Depends(current_user)):
    src=service.source(db,user.id,source_id,lock=True)
    if src.version!=data.version: raise HTTPException(409,'Fonte modificata: ricarica la pagina.')
    if src.status=='removed': raise HTTPException(409,'La fonte è stata rimossa.')
    if not {'external_id','number'}<=data.mapping.keys() or not set(data.mapping)<=set(FIELDS) or any(not v or len(v)>160 for v in data.mapping.values()):
        raise HTTPException(422,'Associa almeno identificativo esterno e numero ordine a colonne valide.')
    src.configuration={**src.configuration,'mapping':data.mapping,'validated':False}
    src.version+=1;src.status='draft';db.commit();return service.public_source(db,src)


@router.post('/api/order-sources/{source_id}/action')
def source_action(source_id:int,data:SourceAction,request:Request,response:Response,db:Session=Depends(get_db),user:User=Depends(current_user)):
    src=service.source(db,user.id,source_id,lock=True)
    if src.version!=data.version: raise HTTPException(409,'Fonte modificata: ricarica la pagina.')
    if src.status=='removed': raise HTTPException(409,'La fonte è rimossa; gli ordini restano disponibili.')
    secret=None
    if data.action in ('rotate','revoke') and getattr(request.state,'company_collaborator',None):
        raise HTTPException(403,'Le credenziali riservate sono gestite dal titolare dell’azienda.')
    if data.action=='activate':
        item=service.run(db,user.id,source_id,data.run_id)
        service.check_payload(item)
        if item.status!='preview_ready' or item.source_version!=src.version: raise HTTPException(409,'Verifica un campione valido con la configurazione corrente prima di attivare.')
        src.status='active';src.configuration={**src.configuration,'validated':True}
        item.source_version=src.version+1
    elif data.action=='resume':
        if not src.configuration.get('validated'): raise HTTPException(409,'La configurazione deve essere verificata prima di riattivare.')
        src.status='active'
    elif data.action=='pause': src.status='paused'
    elif data.action=='remove': src.status='removed';src.credential_hash=None
    elif data.action=='revoke': src.credential_hash=None;src.status='paused'
    elif data.action=='rotate':
        if src.kind!='api' or src.status!='active': raise HTTPException(409,'Attiva e verifica prima la fonte API.')
        secret=issue(src)
    src.version+=1
    db.add(OrderImportRun(user_id=user.id,source_id=src.id,status='source_'+data.action,report={'actor':actor_key(request,user),'action':data.action}))
    db.commit()
    response.headers['Cache-Control']='no-store'
    return service.public_source(db,src)|({'credential':secret} if secret else {})


@router.delete('/api/order-sources/{source_id}')
def delete_source(source_id:int,version:int=Query(...,ge=1),db:Session=Depends(get_db),user:User=Depends(current_user)):
    """Delete the connected source configuration while preserving already acquired orders."""
    src=service.source(db,user.id,source_id,lock=True)
    if src.version!=version: raise HTTPException(409,'Fonte modificata: ricarica la pagina.')
    orders=db.query(Order).filter_by(user_id=user.id,source_id=src.id)
    if orders.first() is not None:
        archive=OrderSource(user_id=user.id,key='archive-'+str(uuid4()),name=src.name,kind='archive',status='removed',
                            configuration={'archived':True},credential_hash=None)
        db.add(archive);db.flush()
        orders.update({'source_id':archive.id},synchronize_session=False)
    db.query(CustomerSourceMapping).filter_by(user_id=user.id,source_id=src.id).delete(synchronize_session=False)
    db.query(OrderImportRun).filter_by(user_id=user.id,source_id=src.id).delete(synchronize_session=False)
    db.delete(src)
    db.commit()
    return {'deleted':True,'id':source_id}


@router.post('/api/order-sources/{source_id}/upload')
async def upload(source_id:int,file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    content=await file.read(MAX_BYTES+1)
    headers,rows=read_file(content,file.filename or '')
    src=service.source(db,user.id,source_id,lock=True)
    if src.kind!='file': raise HTTPException(422,'Per una fonte API usa il campione JSON.')
    item=service.stage(db,src,headers,rows);db.commit()
    return {'run_id':item.id,'headers':headers,'sample':rows[:5],'total':len(rows),'suggested_mapping':suggestions(headers)}


@router.post('/api/order-sources/{source_id}/sample')
async def sample(source_id:int,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    data=await bounded_json(request)
    rows=data.get('orders') if isinstance(data,dict) else None
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_ROWS or any(not isinstance(r,dict) for r in rows): raise HTTPException(422,'Fornisci un oggetto JSON con orders: elenco di 1–1000 ordini.')
    headers=list(dict.fromkeys(k for row in rows for k in row))
    validate_rows(headers,rows)
    src=service.source(db,user.id,source_id,lock=True)
    if src.kind!='api': raise HTTPException(422,'Il campione JSON è previsto per le fonti API.')
    item=service.stage(db,src,headers,rows);db.commit()
    return {'run_id':item.id,'headers':headers,'sample':rows[:5],'total':len(rows),'suggested_mapping':suggestions(headers)}


@router.post('/api/order-sources/{source_id}/runs/{run_id}/preview')
def preview(source_id:int,run_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    src=service.source(db,user.id,source_id,lock=True);item=service.run(db,user.id,source_id,run_id)
    if item.status=='completed': raise HTTPException(409,'Questa importazione è già completata.')
    service.preview(db,src,item);db.commit();return service.public_run(item)


@router.post('/api/order-sources/{source_id}/runs/{run_id}/commit')
def commit_import(source_id:int,run_id:int,data:RunConfirm,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    try:
        src=service.source(db,user.id,source_id,lock=True);item=service.run(db,user.id,source_id,run_id)
        service.commit_file(db,src,item,actor_key(request,user));db.commit()
        return JSONResponse(jsonable_encoder(service.public_run(item)),status_code=422 if item.status=='failed' else 200)
    except Exception:
        db.rollback();raise


@router.get('/api/order-sources/{source_id}/runs')
def history(source_id:int,offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(current_user)):
    service.source(db,user.id,source_id)
    query=db.query(OrderImportRun).filter_by(user_id=user.id,source_id=source_id)
    return {'items':[service.public_run(item) for item in query.order_by(OrderImportRun.id.desc()).offset(offset).limit(20)],'total':query.count()}


@router.get('/api/order-sources/{source_id}/runs/{run_id}')
def report(source_id:int,run_id:int,offset:int=Query(0,ge=0),db:Session=Depends(get_db),user:User=Depends(current_user)):
    item=service.run(db,user.id,source_id,run_id);return service.public_run(item,offset)


@router.post('/api/order-ingestion')
async def ingest(request:Request,db:Session=Depends(get_db)):
    throttle_ip(request)
    sid,token=credential(request)
    try:
        authenticated(db,sid,token,rate=True)
        raw=await bounded_json(request)
        try: data=Acquisition.model_validate(raw)
        except ValidationError: raise HTTPException(422,'Invia batch_id univoco e orders con 1–1000 ordini, nel formato documentato.')
        src=authenticated(db,sid,token)
        item=service.acquire(db,src,data);db.commit()
        return JSONResponse(jsonable_encoder(service.public_run(item)),status_code=422 if item.status in ('failed','preview_invalid') else 200,headers={'Cache-Control':'no-store'})
    except Exception:
        db.rollback();raise
