"""Commercial CRM API. Every query is scoped before reading or changing records."""
import csv
import io
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..core.clock import utc_now
from ..core.dependencies import require_superadmin
from ..core.utils import csv_safe_value
from ..database import get_db
from ..models import SuperAdminCollaborator
from ..crm_models import CRMCompany, CRMContact, CRMOpportunity, CRMFollowup, CRMActivity, CRMAudit
from ..schemas.crm import CompanyIn, ContactIn, OpportunityIn, FollowupIn, ActivityIn
from ..services.crm_permissions import allowed, require


def crm_actor(request: Request, response: Response, actor=Depends(require_superadmin)):
    require(actor)
    response.headers['Cache-Control'] = 'no-store'
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        require(actor, 'crm_write')
        origin = request.headers.get('origin')
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and urlsplit(origin).netloc != request.url.netloc):
            raise HTTPException(403, 'Origine della richiesta non consentita')
    return actor


router = APIRouter(prefix='/api/admin/crm', tags=['crm'], dependencies=[Depends(crm_actor)])
MODELS = {'contacts': CRMContact, 'opportunities': CRMOpportunity, 'followups': CRMFollowup, 'activities': CRMActivity}


def companies(db, actor):
    query = db.query(CRMCompany)
    if not allowed(actor, 'crm_view_all'):
        identity = actor.get('collaborator_id')
        if not identity:
            raise HTTPException(403, 'Identità commerciale non valida')
        query = query.filter(CRMCompany.owner_id == identity)
    return query


def company(db, actor, record_id, lock=False):
    query = companies(db, actor).filter(CRMCompany.id == record_id)
    if lock:
        query = query.with_for_update()
    row = query.populate_existing().first()
    if not row:
        raise HTTPException(404, 'Azienda non trovata')
    return row


def serialize(row):
    result = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if isinstance(value, datetime):
            value = value.isoformat() + 'Z'
        elif isinstance(value, Decimal):
            value = str(value)
        result[column.name] = value
    return result


def audit(db, actor, row, action):
    db.flush()
    db.add(CRMAudit(company_id=row.id if isinstance(row, CRMCompany) else row.company_id,
                    entity=row.__tablename__, entity_id=row.id, action=action,
                    actor=actor.get('username', 'superadmin')))


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Dati duplicati o collegamenti non validi. Verifica la partita IVA e ricarica.')


def check_version(row, version):
    if version is None or version != row.version:
        raise HTTPException(409, 'Il record è stato aggiornato. Ricarica prima di salvare.')
    row.version += 1
    row.updated_at = utc_now()


def check_owner(db, actor, owner_id, previous=None):
    if not allowed(actor, 'crm_view_all'):
        if owner_id not in (None, actor.get('collaborator_id')):
            raise HTTPException(403, 'Non puoi assegnare aziende ad altri commerciali')
        return actor['collaborator_id']
    if owner_id is not None and owner_id != previous:
        row = db.get(SuperAdminCollaborator, owner_id)
        import json
        try:
            perms = json.loads(row.permissions_json or '{}') if row else {}
        except (TypeError, ValueError):
            perms = {}
        if not row or not row.is_active or not isinstance(perms, dict) or perms.get('crm_access') is not True:
            raise HTTPException(422, 'Scegli un commerciale attivo autorizzato al CRM')
    return owner_id


@router.get('/me')
def me(actor=Depends(crm_actor), db: Session = Depends(get_db)):
    import json
    rows = db.query(SuperAdminCollaborator).filter(SuperAdminCollaborator.is_active.is_(True)).order_by(SuperAdminCollaborator.full_name).all() if allowed(actor, 'crm_view_all') else []
    assignees = []
    for row in rows:
        try:
            p = json.loads(row.permissions_json or '{}')
        except (TypeError, ValueError):
            continue
        if isinstance(p, dict) and p.get('crm_access') is True:
            assignees.append({'id': row.id, 'name': row.full_name})
    return {'write': allowed(actor, 'crm_write'), 'view_all': allowed(actor, 'crm_view_all'),
            'export': allowed(actor, 'crm_export'), 'assignees': assignees}


@router.get('/companies')
def list_companies(q: str = Query('', max_length=200), interest: str = '', archived: bool = False,
                   page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                   actor=Depends(crm_actor), db: Session = Depends(get_db)):
    query = companies(db, actor).filter(CRMCompany.archived == archived)
    if q:
        pattern = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.filter(or_(*[c.ilike(pattern, escape='\\') for c in (CRMCompany.name, CRMCompany.email, CRMCompany.phone, CRMCompany.vat)]))
    if interest:
        query = query.filter(CRMCompany.interest == interest)
    return {'items': [serialize(r) for r in query.order_by(CRMCompany.name, CRMCompany.id).offset((page-1)*page_size).limit(page_size)], 'total': query.count(), 'page': page, 'page_size': page_size}


@router.post('/companies', status_code=201)
def create_company(payload: CompanyIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    values = payload.model_dump(exclude={'version'})
    values['owner_id'] = check_owner(db, actor, values['owner_id'])
    if values['archived']:
        raise HTTPException(422, 'Una nuova azienda deve essere attiva')
    row = CRMCompany(**values)
    db.add(row)
    try:
        audit(db, actor, row, 'created')
        commit(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Esiste già un’azienda con questa partita IVA')
    return serialize(row)


@router.get('/companies/{record_id}')
def detail(record_id: int, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    row = company(db, actor, record_id)
    return serialize(row)


@router.put('/companies/{record_id}')
def update_company(record_id: int, payload: CompanyIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    row = company(db, actor, record_id, lock=True)
    check_version(row, payload.version)
    values = payload.model_dump(exclude={'version'})
    values['owner_id'] = check_owner(db, actor, values['owner_id'], row.owner_id)
    if values['archived'] != row.archived:
        if not allowed(actor, 'crm_view_all'):
            raise HTTPException(403, 'Archiviazione riservata al responsabile CRM')
        if values['archived'] and db.query(CRMFollowup).filter_by(company_id=row.id, status='open').count():
            raise HTTPException(409, 'Completa o annulla i follow-up aperti prima di archiviare')
    for key, value in values.items():
        setattr(row, key, value)
    try:
        audit(db, actor, row, 'updated')
        commit(db)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Esiste già un’azienda con questa partita IVA')
    return serialize(row)


def child_query(db, actor, model):
    return db.query(model).join(CRMCompany, model.company_id == CRMCompany.id).filter(
        CRMCompany.id.in_(companies(db, actor).with_entities(CRMCompany.id)), CRMCompany.archived.is_(False))


@router.get('/records/{kind}')
def list_records(kind: str, company_id: int | None = None, page: int = Query(1, ge=1),
                 page_size: int = Query(30, ge=1, le=100), status: str = '',
                 actor=Depends(crm_actor), db: Session = Depends(get_db)):
    model = MODELS.get(kind)
    if not model:
        raise HTTPException(404, 'Sezione non trovata')
    query = child_query(db, actor, model)
    if company_id is not None:
        company(db, actor, company_id)
        query = query.filter(model.company_id == company_id)
    if status and model is CRMFollowup:
        query = query.filter(model.status == ('open' if status == 'overdue' else status))
        if status == 'overdue':
            query = query.filter(model.due_at < utc_now())
    if status and model is CRMOpportunity:
        query = query.filter(model.stage == status)
    total = query.count()
    order = (model.due_at, model.id) if model is CRMFollowup else (model.created_at.desc(), model.id.desc())
    rows = query.order_by(*order).offset((page-1)*page_size).limit(page_size).all()
    names = dict(db.query(CRMCompany.id, CRMCompany.name).filter(CRMCompany.id.in_({r.company_id for r in rows})).all())
    return {'items': [dict(serialize(r), company_name=names[r.company_id]) for r in rows], 'total': total, 'page': page, 'page_size': page_size}


def save_child(db, actor, model, payload, record_id=None):
    values = payload.model_dump(exclude={'version'})
    parent = company(db, actor, payload.company_id, lock=True)
    if parent.archived:
        raise HTTPException(409, 'Ripristina prima l’azienda archiviata')
    row = None
    old_stage = None
    if record_id is not None:
        row = child_query(db, actor, model).filter(model.id == record_id).with_for_update().populate_existing().first()
        if not row or row.company_id != parent.id:
            raise HTTPException(404, 'Record non trovato nell’azienda')
        check_version(row, payload.version)
        old_stage = getattr(row, 'stage', None)
    else:
        row = model()
        db.add(row)
    if model is CRMOpportunity:
        if values['stage'] in ('won', 'lost'):
            if old_stage != values['stage']:
                row.closed_at = utc_now()
        else:
            row.closed_at = None
        if values['stage'] == 'won':
            values['probability'] = 100
        elif values['stage'] == 'lost':
            values['probability'] = 0
    if model is CRMFollowup:
        row.completed_at = (row.completed_at or utc_now()) if values['status'] == 'completed' else None
    if model is CRMActivity:
        row.actor = actor.get('username', 'superadmin')
    for key, value in values.items():
        setattr(row, key, value)
    action = 'updated' if record_id else 'created'
    if model is CRMOpportunity and old_stage != row.stage:
        action = f'stage:{old_stage or "start"}->{row.stage}'
    audit(db, actor, row, action)
    commit(db)
    return serialize(row)


@router.post('/contacts', status_code=201)
def create_contact(payload: ContactIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    return save_child(db, actor, CRMContact, payload)


@router.put('/contacts/{record_id}')
def update_contact(record_id: int, payload: ContactIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    return save_child(db, actor, CRMContact, payload, record_id)


@router.post('/opportunities', status_code=201)
def create_opportunity(payload: OpportunityIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    return save_child(db, actor, CRMOpportunity, payload)


@router.put('/opportunities/{record_id}')
def update_opportunity(record_id: int, payload: OpportunityIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    return save_child(db, actor, CRMOpportunity, payload, record_id)


@router.post('/followups', status_code=201)
def create_followup(payload: FollowupIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    return save_child(db, actor, CRMFollowup, payload)


@router.put('/followups/{record_id}')
def update_followup(record_id: int, payload: FollowupIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    return save_child(db, actor, CRMFollowup, payload, record_id)


@router.post('/activities', status_code=201)
def create_activity(payload: ActivityIn, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    return save_child(db, actor, CRMActivity, payload)


@router.get('/companies/{record_id}/history')
def history(record_id: int, actor=Depends(crm_actor), db: Session = Depends(get_db)):
    company(db, actor, record_id)
    return [serialize(r) for r in db.query(CRMAudit).filter_by(company_id=record_id).order_by(CRMAudit.id.desc()).limit(100)]


@router.get('/reports')
def reports(actor=Depends(crm_actor), db: Session = Depends(get_db)):
    active = companies(db, actor).filter(CRMCompany.archived.is_(False))
    pipeline = child_query(db, actor, CRMOpportunity)
    stages = [{'stage': stage, 'count': count, 'amount': str(amount or 0)} for stage, count, amount in
              pipeline.with_entities(CRMOpportunity.stage, func.count(CRMOpportunity.id), func.sum(CRMOpportunity.amount)).group_by(CRMOpportunity.stage).all()]
    won = next((s['count'] for s in stages if s['stage'] == 'won'), 0)
    lost = next((s['count'] for s in stages if s['stage'] == 'lost'), 0)
    followups = child_query(db, actor, CRMFollowup).filter(CRMFollowup.status == 'open')
    return {'companies': active.count(), 'contacts': child_query(db, actor, CRMContact).count(),
            'open_followups': followups.count(), 'overdue_followups': followups.filter(CRMFollowup.due_at < utc_now()).count(),
            'stages': stages, 'win_rate': round(won * 100 / (won + lost), 1) if won + lost else None,
            'currency': 'EUR', 'scope': 'all' if allowed(actor, 'crm_view_all') else 'assigned'}


@router.get('/export')
def export(actor=Depends(crm_actor), db: Session = Depends(get_db)):
    require(actor, 'crm_export')
    query = companies(db, actor).filter(CRMCompany.archived.is_(False)).order_by(CRMCompany.id)
    if query.count() > 10000:
        raise HTTPException(422, 'Esportazione oltre il limite di 10.000 aziende')
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['Azienda', 'Email', 'Telefono', 'Paese', 'Partita IVA', 'Città', 'Settore', 'Interesse'])
    for row in query.yield_per(200):
        writer.writerow([csv_safe_value(v) for v in (row.name, row.email, row.phone, row.country, row.vat or '', row.city, row.sector, row.interest)])
    from .admin_helpers import _activity
    _activity(db, actor.get('username'), 'crm_export', 'Esportazione portafoglio CRM')
    commit(db)
    return Response(out.getvalue().encode('utf-8-sig'), media_type='text/csv', headers={
        'Content-Disposition': 'attachment; filename="crm-aziende.csv"', 'Cache-Control': 'no-store'})
