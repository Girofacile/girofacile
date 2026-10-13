"""PostgreSQL regression: route summaries must not DISTINCT JSON columns."""
from datetime import date,time
from types import SimpleNamespace
from sqlalchemy.orm import Session
from test_audit_postgres import pg


def test_selection_json_routes_deduplicated_and_scoped(pg):
    from app.database import Base
    from app.models import User,RoutePlan
    from app.order_models import OrderSource,Order,RouteOrderAssignment
    from app.services.order_planning import selection_response
    Base.metadata.create_all(pg)
    with Session(pg) as db:
        owners=[User(username=name,password_hash='test') for name in ('company-a','company-b')]
        db.add_all(owners);db.flush()
        ids=[];routes=[]
        for owner in owners:
            source=OrderSource(user_id=owner.id,key='test',name='Test',kind='manual')
            route=RoutePlan(user_id=owner.id,nome=owner.username,data_giro=date(2099,1,15),orario_partenza=time(8),status='bozza',
                driver_schedule={'start':'08:00','end':'17:00','breaks':[{'start':'12:00','end':'13:00'}]},
                driver_breaks=[{'start':'12:00','end':'13:00','after_order':1,'duration_min':60}])
            db.add_all([source,route]);db.flush();routes.append(route)
            for number in ('1','2'):
                order=Order(user_id=owner.id,source_id=source.id,external_id=number,number=number,original_payload={},operational_data={},requested_date=date(2099,1,15))
                db.add(order);db.flush();ids.append(order.id)
                db.add(RouteOrderAssignment(user_id=owner.id,order_id=order.id,route_plan_id=route.id,stop_key=number))
        db.commit()
        row=SimpleNamespace(user_id=owners[0].id,order_ids=ids,version=1,configuration={},stops=None,updated_at=None)
        result=selection_response(db,row)
        assert result['routes']==[{'id':routes[0].id,'name':'company-a','status':'bozza'}]
        assert result['requested_dates']==['2099-01-15']
        row.order_ids=[]
        assert selection_response(db,row)['routes']==[]
        assert selection_response(db,None)['routes']==[]
