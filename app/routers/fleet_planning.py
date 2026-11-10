"""Company fleet previews, manual redistribution and explicit confirmation."""
from fastapi import APIRouter,Depends,Request,HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..core.dependencies import current_user
from ..schemas.fleet_planning import FleetInput,FleetRevision,FleetConfirm
from ..services import fleet_planning as service,route_orders
from ..services.plans import require_feature
from .orders import actor_key

router=APIRouter(prefix='/api/fleet-planning',tags=['fleet-planning'])

def permission(request,user,db,configuration):
    require_feature(user,'has_fleet_planning')
    route_orders.require_planning_permission(request,configuration['consegne'],db)

def with_duplicates(db,user,plan):
    """Revisione su più mezzi: segnala i clienti già serviti da un giro programmato lo stesso giorno."""
    from datetime import date
    from ..services.same_day import already_planned
    body=service.public(plan)
    if not isinstance(body,dict) or not hasattr(plan,'configuration'):
        return body
    try:
        day=date.fromisoformat(str(plan.configuration.get('data_giro')))
        ids=[s.get('customer_id') for s in plan.configuration.get('consegne',[])]
        body['clienti_gia_programmati']=already_planned(db,user.id,day,ids,plan.route_ids or ()) if plan.status=='preview' else []
    except (TypeError,ValueError):
        body['clienti_gia_programmati']=[]
    return body

@router.post('/preview')
def preview(data:FleetInput,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    permission(request,user,db,data.model_dump())
    try: return with_duplicates(db,user,service.create_preview(db,user,actor_key(request,user),data))
    except ValueError as exc: db.rollback();raise HTTPException(422,str(exc))
    except Exception: db.rollback();raise

@router.get('/{plan_id}')
def read(plan_id:int,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    plan=service.get_plan(db,user,actor_key(request,user),plan_id)
    permission(request,user,db,plan.configuration)
    return with_duplicates(db,user,plan)

@router.post('/{plan_id}/revise')
def revise(plan_id:int,data:FleetRevision,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    plan=service.get_plan(db,user,actor_key(request,user),plan_id)
    permission(request,user,db,plan.configuration)
    try: return with_duplicates(db,user,service.revise(db,user,actor_key(request,user),plan_id,data))
    except ValueError as exc: db.rollback();raise HTTPException(422,str(exc))
    except Exception: db.rollback();raise

@router.post('/{plan_id}/confirm')
def confirm(plan_id:int,data:FleetConfirm,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    plan=service.get_plan(db,user,actor_key(request,user),plan_id)
    permission(request,user,db,plan.configuration)
    try: return service.public(service.confirm(db,user,actor_key(request,user),plan_id,data))
    except ValueError as exc: db.rollback();raise HTTPException(422,str(exc))
    except Exception: db.rollback();raise

@router.post('/{plan_id}/program')
def program(plan_id:int,data:FleetConfirm,request:Request,db:Session=Depends(get_db),user:User=Depends(current_user)):
    plan=service.get_plan(db,user,actor_key(request,user),plan_id)
    permission(request,user,db,plan.configuration)
    try: return service.public(service.program(db,user,actor_key(request,user),plan_id,data))
    except ValueError as exc: db.rollback();raise HTTPException(422,str(exc))
    except Exception: db.rollback();raise
