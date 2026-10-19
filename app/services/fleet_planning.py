"""Fleet-wide search on one shared road matrix, with private persisted previews."""
from copy import deepcopy
from datetime import datetime, timedelta
from ..core.clock import utc_now
import math
from fastapi import HTTPException
from .. import optimizer as opt
from ..models import Vehicle, Driver, RoutePlan
from ..fleet_models import FleetPlan
from ..schemas import RoutePlanIn
from ..schemas.fleet_planning import FleetInput
from . import route_orders
from ..core.utils import local_now


def ensure_future_departure(data_giro, orario):
    from datetime import date, time
    day=date.fromisoformat(data_giro) if isinstance(data_giro,str) else data_giro
    start=time.fromisoformat(orario) if isinstance(orario,str) else orario
    if datetime.combine(day,start)<local_now().replace(tzinfo=None):
        raise HTTPException(400,'L’orario di partenza è già passato. Inserisci una data e un orario futuri per pianificare i giri.')


def get_plan(db,user,actor,plan_id,lock=False):
    query=db.query(FleetPlan).filter_by(id=plan_id,user_id=user.id,actor=actor)
    row=(query.with_for_update().populate_existing() if lock else query).first()
    if not row: raise HTTPException(404,'Piano non trovato.')
    return row


def route_data(data,resource,rows,index,driver_name=None):
    # Nome automatico di ogni giro: base (la data) · autista; senza autista resta il numero del giro.
    values=data.model_dump(exclude={'resources','strategy','consegne'})
    values.update(nome=f'{data.nome or "Giro consegne"} · {driver_name or index+1}',vehicle_id=resource.vehicle_id,
                  driver_id=resource.driver_id,driver_schedule=resource.driver_schedule,consegne=rows,energy_price_mode='manual',
                  energy_price_primary=resource.energy_price_primary,energy_price_electric=resource.energy_price_electric)
    return RoutePlanIn.model_validate(values)


def input_state(db,user,data):
    from ..routers.routes import _validate_route_tenant_scope, _require_owned_entity, _apply_route_preferences, ensure_not_past_route_date, build_vehicle_dict
    from .plans import require_active_plan
    require_active_plan(user)
    ensure_not_past_route_date(data.data_giro)
    ensure_future_departure(data.data_giro,data.orario_partenza)
    rows=[d.model_dump(mode='json') for d in data.consegne]
    deposit,_,_= _validate_route_tenant_scope(db,user,route_data(data,data.resources[0],rows,0),rows)
    _apply_route_preferences(user,rows)
    vehicles=[_require_owned_entity(db,Vehicle,user,r.vehicle_id,'Mezzo') for r in data.resources]
    drivers=[_require_owned_entity(db,Driver,user,r.driver_id,'Autista') for r in data.resources]
    from .driver_schedule import resolved
    from ..schemas.driver_schedule import DriverSchedule
    for resource,driver in zip(data.resources,drivers):
        resource.driver_schedule=DriverSchedule.model_validate(resolved(resource.driver_schedule.model_dump() if resource.driver_schedule else None,driver))
    return deposit,rows,vehicles,drivers


def work_limits(db,user,data):
    from ..routers.routes import _check_resource_overlap
    start=opt.parse_hhmm(data.orario_partenza)
    limits=[]
    for index,r in enumerate(data.resources):
        route=route_data(data,r,[],index)
        low,high=0,r.max_minutes
        while low<high:
            middle=(low+high+1)//2
            try: _check_resource_overlap(db,user,route,start,start+middle)
            except HTTPException: high=middle-1
            else: low=middle
        limits.append(low)
    return limits


def fuel_cost(vehicle,resource,km):
    kind=vehicle.alimentazione or 'gasolio'
    primary=0 if kind=='elettrico' else km*float(vehicle.consumo_primario_100km or vehicle.consumo_l_100km or 0)/100*resource.energy_price_primary
    electric=km*float(vehicle.consumo_kwh_100km or 0)/100*resource.energy_price_electric if kind in ('elettrico','ibrido_plugin_benzina','ibrido_plugin_diesel') else 0
    return round(primary+electric,2)


def distribute(db,user,data,assignments=None):
    from ..routers.routes import build_vehicle_dict
    from .distance_cache import point_key
    deposit,rows,vehicles,drivers=input_state(db,user,data)
    frozen=deepcopy(rows)
    limits=work_limits(db,user,data)
    depot=opt.geocode_deposit(db,deposit)
    points=[depot]
    for index,row in enumerate(rows):
        coord=opt._coord_from_delivery(row)
        if not coord: raise HTTPException(422,'Verifica gli indirizzi prima della distribuzione.')
        row.update(coord=coord,_matrix_index=index+1,fleet_stop_index=index)
        points.append(coord)
    keys=[point_key(deposit_id=deposit.id,lat=depot['lat'],lon=depot['lon'],user_id=user.id)]+[
        point_key(customer_id=r.get('customer_id'),lat=r['coord']['lat'],lon=r['coord']['lon'],user_id=user.id) for r in rows]
    matrix=opt.build_distance_matrix(db,user.id,points,keys,start_time=data.orario_partenza,route_date=data.data_giro)
    vehicle_data=[build_vehicle_dict(v,r.driver_schedule.model_dump()) for v,r in zip(vehicles,data.resources)]
    routes=[[] for _ in vehicles];results=[None for _ in vehicles]
    unresolved={}

    def evaluate(sequence,resource,failures=None,include_details=False):
        def reject(reason):
            if failures is not None:
                failures.add(reason)
            return None
        if not sequence: return None
        try: opt.validate_vehicle_load(sequence,vehicle_data[resource])
        except ValueError as exc: return reject(str(exc))
        result=opt._evaluate_fixed_sequence(sequence,matrix,points,vehicle_data[resource],data.rientro_deposito,data.orario_partenza,include_details=include_details,earliest_windows=True)
        if result['violations']:
            return reject('Fasce orarie di consegna o turni e pause non rispettati.')
        if math.ceil(result['_objective'][1])>limits[resource]:
            return reject(f'Tempo disponibile insufficiente: {limits[resource]} minuti, considerando durata massima e altri giri già programmati.')
        if not include_details:
            # Search memoization retains scalar scores, never thousands of
            # complete copies of stops. Final routes are replayed with details.
            return {key:result[key] for key in ('total_km','total_min','_objective')}
        return result

    def insert(index):
        row=rows[index];best=None;reasons=[]
        for resource,sequence in enumerate(routes):
            failures=set()
            for position in range(len(sequence)+1):
                candidate=sequence[:position]+[row]+sequence[position:]
                evaluated=evaluate(candidate,resource,failures)
                if evaluated is None: continue
                durations=[r['total_min'] if r else 0 for r in results];durations[resource]=evaluated['total_min']
                delta=evaluated['total_min']-(results[resource]['total_min'] if results[resource] else 0)
                if data.strategy=='balanced':
                    key=(sum(not r for i,r in enumerate(routes) if i!=resource),max(durations),sum(x*x for x in durations),delta,evaluated['total_km'])
                else: key=(0 if sequence else 1,delta,evaluated['total_km'])
                # Prefer an equipped vehicle, but keep the delivery when none can take it.
                equipment_penalty=int(bool(row.get('sponda')) and not vehicles[resource].ha_sponda)+int(bool(row.get('ztl')) and not vehicles[resource].accesso_ztl)
                key=(equipment_penalty,*key)
                if best is None or key<best[0]: best=(key,resource,candidate,evaluated)
            if failures:
                reasons.append(f'Giro {resource+1}: '+ ' '.join(sorted(failures)))
        if best is None:
            unresolved[index]='Nessun inserimento compatibile nella suddivisione corrente. '+ ' '.join(reasons)
        else:
            _,resource,sequence,result=best
            routes[resource],results[resource]=sequence,result

    if assignments is None:
        # Constrained/heavy jobs first; deterministic ordering for repeatability.
        order=sorted(range(len(rows)),key=lambda i:(not(rows[i]['sponda'] or rows[i]['ztl']),not bool(opt.delivery_windows(rows[i])),-rows[i]['peso_kg'],-rows[i]['colli'],i))
        for index in order: insert(index)
        from .fleet_search import optimize_fleet
        import json
        def equipment(sequence, resource):
            return sum(
                int(bool(rows[i].get('sponda')) and not vehicles[resource].ha_sponda)
                + int(bool(rows[i].get('ztl')) and not vehicles[resource].accesso_ztl)
                for i in sequence)
        signature_fields=('driver_schedule','ha_sponda','accesso_ztl','capacita_kg','capacita_colli')
        signatures=[json.dumps({key:v.get(key) for key in signature_fields},sort_keys=True,default=str)+':'+str(limit)
                    for v,limit in zip(vehicle_data,limits)]
        proposed,optimized_results,search=optimize_fleet(
            rows,len(vehicles),
            lambda sequence,resource:evaluate([rows[i] for i in sequence],resource),
            data.strategy,initial_routes=[
                [row['fleet_stop_index'] for row in route] for route in routes],
            initial_results=results,matrix=matrix,points=points,
            equipment_penalty=equipment,resource_signatures=signatures,
            return_depot=data.rientro_deposito)
        routes=[[rows[i] for i in sequence] for sequence in proposed]
        results=list(optimized_results)
    else:
        search={'method':'manual-membership','equipment_policy':'prefer-compatible-with-warning-fallback'}
        if len(assignments)!=len(rows) or any(a is not None and (a<0 or a>=len(routes)) for a in assignments):
            raise HTTPException(422,'Assegna ogni consegna una sola volta a una risorsa valida.')
        for index,resource in enumerate(assignments):
            if resource is None: unresolved[index]='Lasciata non assegnata dall operatore.'
            else: routes[resource].append(rows[index])
        for resource,sequence in enumerate(routes):
            if not sequence: continue
            # Keep the existing classic search above eight stops. Smaller
            # memberships are ordered exhaustively in the common final pass.
            if len(sequence)>8:
                ordered=opt._best_internal_sequence(sequence,matrix,points,vehicle_data[resource],data.rientro_deposito,data.orario_partenza)['ordered']
                routes[resource]=[rows[s['fleet_stop_index']] for s in ordered]
            failures=set()
            results[resource]=evaluate(routes[resource],resource,failures)
            if len(sequence)>8 and results[resource] is None:
                raise HTTPException(422,f'Giro {resource+1}: '+ ' '.join(sorted(failures))+' Modifica l’assegnazione e ricalcola.')
    from .fleet_search import refine_routes
    from .fleet_route_evaluator import FixedRouteEvaluator
    sequences=tuple(tuple(row['fleet_stop_index'] for row in route) for route in routes)
    refined,results,refinement=refine_routes(
        sequences,results,
        lambda sequence,resource:evaluate([rows[i] for i in sequence],resource),
        global_exact=bool(search.get('global_optimum_proven')),
        prepare=lambda sequence,resource:FixedRouteEvaluator(
            rows,sequence,matrix,points,vehicle_data[resource],data.rientro_deposito,
            data.orario_partenza,limits[resource]))
    search.update(refinement)
    routes=[[rows[i] for i in sequence] for sequence in refined]
    for resource,sequence in enumerate(routes):
        if sequence and results[resource] is None:
            failures=set()
            evaluate(sequence,resource,failures)
            raise HTTPException(422,f'Giro {resource+1}: '+ ' '.join(sorted(failures))+
                                ' Nessun ordine compatibile per le consegne assegnate. Modifica l’assegnazione e ricalcola.')
    if assignments is None:
        assigned={i for sequence in refined for i in sequence}
        unresolved={}
        for index in range(len(rows)):
            if index in assigned: continue
            reasons=[]
            for resource,sequence in enumerate(routes):
                failures=set()
                for position in range(len(sequence)+1):
                    evaluate(sequence[:position]+[rows[index]]+sequence[position:],resource,failures)
                if failures:
                    reasons.append(f'Giro {resource+1}: '+ ' '.join(sorted(failures)))
            unresolved[index]='Consegna non assegnata nella suddivisione corrente. '+ ' '.join(reasons)
    # Generate complete ETA and diagnostic details only for selected final routes.
    results=[evaluate(sequence,index,include_details=True) if sequence else None
             for index,sequence in enumerate(routes)]
    output=[]
    for index,result in enumerate(results):
        if result is None: continue
        indexes=[s['fleet_stop_index'] for s in result['ordered']]
        for stop in result['ordered']: stop.pop('fleet_stop_index',None)
        for field in ('score','_objective','violations','total_wait'): result.pop(field,None)
        result.update(base_routing_provider=getattr(matrix,'source','osrm'),depot_coord=depot,
                      base_return_leg=dict(matrix.get((indexes[-1]+1,0)) or {}) if data.rientro_deposito else {},
                      google_maps_url=opt.build_google_maps_url(deposit.indirizzo,result['ordered'],data.rientro_deposito))
        output.append({'resource':index,'vehicle_name':vehicles[index].nome,'driver_name':(drivers[index].nome+' '+(drivers[index].cognome or '')).strip(),
                       'stop_indexes':indexes,'result':result,'fuel_cost':fuel_cost(vehicles[index],data.resources[index],result['total_km']),
                       'weight_kg':sum(rows[i]['peso_kg'] for i in indexes),'packages':sum(rows[i]['colli'] for i in indexes)})
    warnings=['Stima su tempi stradali; traffico e pedaggi saranno verificati alla programmazione. Costi mostrati: solo energia/carburante.',
              'Capacita automatiche: peso e colli. Verifica separatamente volume, pallet, transpallet e altri requisiti.']
    if getattr(matrix,'source','osrm') in ('estimated','mixed'):
        warnings.insert(0,'Routing stradale non disponibile per alcune tratte: tempi e distanze approssimativi, da verificare.')
    if data.strategy=='balanced' and len(output)<len(data.resources): warnings.append('Non tutte le risorse hanno ricevuto consegne: controlla le disponibilita e le consegne non assegnate.')
    for route in output:
        if not vehicles[route['resource']].ha_sponda:
            for index in route['stop_indexes']:
                if rows[index].get('sponda'):
                    warnings.append(f"Giro {route['resource']+1} · {rows[index]['cliente_nome']}: attenzione, questa consegna richiede la sponda, ma il mezzo non la possiede.")
        if not vehicles[route['resource']].accesso_ztl:
            for index in route['stop_indexes']:
                if rows[index].get('ztl'):
                    warnings.append(f"Giro {route['resource']+1} · {rows[index]['cliente_nome']}: attenzione, questa consegna è in ZTL, ma il mezzo non è abilitato all’accesso.")
    return {'routes':output,'unassigned':[{'index':i,'reason':reason} for i,reason in sorted(unresolved.items())],
            'search':search,'resource_capabilities':[{'has_tail_lift':bool(v.ha_sponda),'has_ztl_access':bool(v.accesso_ztl)} for v in vehicles],
            'warnings':warnings,'validated_stops':frozen,'validated_depot':{'id':deposit.id,'indirizzo':deposit.indirizzo,'lat':deposit.lat,'lon':deposit.lon},'source':getattr(matrix,'source','osrm')}


def public(plan):
    return {'id':plan.id,'version':plan.version,'status':plan.status,'configuration':plan.configuration,
            'routes':[{k:v for k,v in r.items()} for r in plan.result['routes']],
            'unassigned':plan.result['unassigned'],'warnings':plan.result['warnings'],'route_ids':plan.route_ids,
            'resource_capabilities':plan.result.get('resource_capabilities',[]),'search':plan.result.get('search',{})}


def check_version(plan,version):
    if plan.version!=version: raise HTTPException(409,'Anteprima modificata. Ricaricala prima di continuare.')
    if plan.created_at<utc_now()-timedelta(hours=12) and plan.status=='preview':
        raise HTTPException(409,'Anteprima scaduta: ricalcola la distribuzione.')


def create_preview(db,user,actor,data):
    result=distribute(db,user,data)
    plan=FleetPlan(user_id=user.id,actor=actor,configuration=data.model_dump(mode='json'),result=result,route_ids=[])
    db.add(plan);db.commit();return plan


def revise(db,user,actor,plan_id,data):
    plan=get_plan(db,user,actor,plan_id)
    check_version(plan,data.version)
    if plan.status!='preview': raise HTTPException(409,'I giri sono gia salvati: aprili dallo storico.')
    result=distribute(db,user,FleetInput.model_validate(plan.configuration),data.assignments)
    plan=get_plan(db,user,actor,plan_id,lock=True);check_version(plan,data.version)
    if plan.status!='preview': raise HTTPException(409,'Piano gia confermato.')
    plan.result=result;plan.version+=1;db.commit();return plan


def confirm(db,user,actor,plan_id,data):
    from ..routers.routes import save_route_result, _check_resource_overlap, build_vehicle_dict
    route_orders.lock_company(db,user.id)
    plan=get_plan(db,user,actor,plan_id,lock=True)
    if plan.status in ('saved','programmed'): return plan
    check_version(plan,data.version)
    if not plan.result['routes']: raise HTTPException(422,'Nessun giro da salvare.')
    if plan.result['unassigned'] and not data.accept_unassigned: raise HTTPException(422,'Conferma esplicitamente le consegne rimaste non assegnate.')
    settings=FleetInput.model_validate(plan.configuration)
    deposit,current,vehicles,_=input_state(db,user,settings)
    if {'id':deposit.id,'indirizzo':deposit.indirizzo,'lat':deposit.lat,'lon':deposit.lon}!=plan.result['validated_depot']:
        raise HTTPException(409,'Deposito cambiato: ricalcola la distribuzione.')
    if current!=plan.result['validated_stops']: raise HTTPException(409,'Indirizzi o dati cambiati: ricalcola la distribuzione.')
    route_ids=[]
    for route in plan.result['routes']:
        index=route['resource'];resource=settings.resources[index];result=deepcopy(route['result'])
        opt.validate_vehicle_load(result['ordered'],build_vehicle_dict(vehicles[index]))
        driver=db.get(Driver,resource.driver_id) if resource.driver_id else None
        driver_name=' '.join(x for x in (driver.nome,driver.cognome) if x).strip() if driver else None
        payload=route_data(settings,resource,result['ordered'],index,driver_name)
        start=opt.parse_hhmm(settings.orario_partenza)
        _check_resource_overlap(db,user,payload,start,start+math.ceil(result['total_min']))
        saved=save_route_result(db,user,payload,result,vehicles[index],commit=False)
        route_ids.append(saved.id)
    plan.route_ids=route_ids;plan.status='saved';plan.version+=1
    db.commit();return plan


def release_failed_drafts(db,user,actor,plan_id,version):
    """Release only untouched drafts belonging to this failed batch; retain its audit trail."""
    import json
    from ..order_models import Order,OrderPlanningSelection
    route_orders.lock_company(db,user.id)
    plan=get_plan(db,user,actor,plan_id,lock=True)
    if plan.status!='saved' or plan.version!=version:
        return False
    rows=db.query(RoutePlan).filter(RoutePlan.user_id==user.id,RoutePlan.id.in_(plan.route_ids)).order_by(RoutePlan.id).with_for_update().populate_existing().all()
    if len(rows)!=len(plan.route_ids):return False
    settings=FleetInput.model_validate(plan.configuration)
    for row,proposal in zip(rows,plan.result['routes']):
        expected=settings.resources[proposal['resource']]
        if (row.status!='bozza' or json.loads(row.routing_snapshot_json or '{}').get('revision')!=1
            or row.vehicle_id!=expected.vehicle_id or row.driver_id!=expected.driver_id
            or row.data_giro.isoformat()!=settings.data_giro or row.orario_partenza.strftime('%H:%M')!=settings.orario_partenza[:5]):
            return False
    for row in rows:
        route_orders.sync_route_orders(db,row,'cancelled')
        row.status='annullato';row.cancelled_at=local_now().replace(tzinfo=None)
    configuration=deepcopy(plan.configuration);result=deepcopy(plan.result)
    ids={ref['id'] for stop in configuration['consegne'] for ref in stop.get('order_refs',[])}
    versions={o.id:o.version for o in db.query(Order).filter(Order.user_id==user.id,Order.id.in_(ids))}
    stops=configuration['consegne']+result.get('validated_stops',[])
    for route in result['routes']:stops+=route['result']['ordered']
    for stop in stops:
        for ref in stop.get('order_refs',[]):
            if ref['id'] in versions:ref['version']=versions[ref['id']]
    selection=db.query(OrderPlanningSelection).filter_by(user_id=user.id,actor=actor).with_for_update().first()
    if selection and selection.stops is not None:
        selected=deepcopy(selection.stops)
        for stop in selected:
            for ref in stop.get('order_refs',[]):
                if ref['id'] in versions:ref['version']=versions[ref['id']]
        selection.stops=selected;selection.version+=1;selection.updated_at=utc_now()
    plan.configuration=configuration;plan.result=result;plan.route_ids=[];plan.status='preview';plan.version+=1
    db.commit()
    return True


def program(db,user,actor,plan_id,data):
    """A single programming request compensates any drafts saved before a failure."""
    from ..schemas.fleet_planning import FleetConfirm
    plan=get_plan(db,user,actor,plan_id)
    if plan.status=='programmed':return plan
    check_version(plan,data.version)
    version=plan.version
    try:
        ensure_future_departure(plan.configuration['data_giro'],plan.configuration['orario_partenza'])
        if plan.status=='preview':
            plan=confirm(db,user,actor,plan_id,data)
            version=plan.version
        return _program_saved(db,user,actor,plan_id,FleetConfirm(version=version,accept_unassigned=data.accept_unassigned))
    except Exception:
        db.rollback()
        release_failed_drafts(db,user,actor,plan_id,version)
        raise


def _program_saved(db,user,actor,plan_id,data):
    """Enrich saved drafts first, then atomically schedule the entire group."""
    import json
    from ..routers.routes import _check_resource_overlap, computed_route_status, ensure_not_past_route_date, build_vehicle_dict, _require_owned_entity
    from .route_execution import lock_route_resources
    from .route_enrichment import enrich_final_route
    from .plans import check_daily_route_limit
    plan=get_plan(db,user,actor,plan_id)
    if plan.status=='programmed': return plan
    check_version(plan,data.version)
    if plan.status!='saved': raise HTTPException(409,'Salva prima i giri in bozza.')
    settings=FleetInput.model_validate(plan.configuration)

    def drafts():
        # Refresh draft generations under row locks before provider enrichment.
        rows=db.query(RoutePlan).filter(RoutePlan.user_id==user.id,RoutePlan.id.in_(plan.route_ids)).order_by(RoutePlan.id).with_for_update().populate_existing().all()
        if len(rows)!=len(plan.route_ids): raise HTTPException(409,'Un giro e stato eliminato.')
        for row,proposal in zip(rows,plan.result['routes']):
            expected=settings.resources[proposal['resource']]
            if (computed_route_status(row)!='bozza' or json.loads(row.routing_snapshot_json or '{}').get('revision')!=1
                or row.data_giro.isoformat()!=settings.data_giro or row.orario_partenza.strftime('%H:%M')!=settings.orario_partenza[:5]
                or row.deposit_id!=settings.deposit_id or row.rientro_deposito!=settings.rientro_deposito
                or row.vehicle_id!=expected.vehicle_id or row.driver_id!=expected.driver_id):
                raise HTTPException(409,'Un giro e stato modificato o programmato separatamente: gestiscilo dallo storico.')
        return rows
    for row in drafts(): enrich_final_route(db,row)
    db.commit()  # Persist timing and provider accounting before releasing route locks.
    route_orders.lock_company(db,user.id)
    plan=get_plan(db,user,actor,plan_id,lock=True)
    if plan.status=='programmed': return plan
    check_version(plan,data.version)
    rows=drafts()
    for row in rows:
        from .driver_schedule import ensure_shift
        ensure_shift(row.driver_schedule,row.orario_partenza,row.totale_minuti)
        db.query(RoutePlan).filter_by(id=row.id,user_id=user.id).with_for_update().one()
        lock_route_resources(db,row)
        from ..models import Deposit
        _require_owned_entity(db,Vehicle,user,row.vehicle_id,'Mezzo')
        _require_owned_entity(db,Driver,user,row.driver_id,'Autista')
        _require_owned_entity(db,Deposit,user,row.deposit_id,'Deposito')
        ensure_not_past_route_date(row.data_giro)
        ensure_future_departure(row.data_giro,row.orario_partenza)
        check_daily_route_limit(user,db,row.data_giro,exclude_route_id=row.id)
        resource=next(r for r in settings.resources if r.vehicle_id==row.vehicle_id and r.driver_id==row.driver_id)
        opt.validate_vehicle_load([{'peso_kg':d.peso_kg,'colli':d.colli} for d in row.deliveries],build_vehicle_dict(row.vehicle))
        if math.ceil(row.totale_minuti)>resource.max_minutes or any(json.loads(d.optimizer_details or '{}').get('time_window_violation') for d in row.deliveries):
            raise HTTPException(409,'I tempi aggiornati non rispettano orari o durata massima. Rivedi i dati e ricalcola prima di programmare.')
        start=opt.parse_hhmm(settings.orario_partenza)
        _check_resource_overlap(db,user,row,start,start+math.ceil(row.totale_minuti),exclude_route_id=row.id)
    from ..models import RouteToken
    from secrets import token_urlsafe
    for row in rows:
        db.query(RouteToken).filter_by(route_plan_id=row.id).delete()
        db.add(RouteToken(route_plan_id=row.id,token=token_urlsafe(32),expires_at=utc_now()+timedelta(days=3)))
        row.status='programmato'
        route_orders.sync_route_orders(db,row,'scheduled')
    updated=deepcopy(plan.result)
    updated['resource_capabilities']=[{'has_tail_lift':bool(db.get(Vehicle,r.vehicle_id).ha_sponda),'has_ztl_access':bool(db.get(Vehicle,r.vehicle_id).accesso_ztl)} for r in settings.resources]
    for proposal,row in zip(updated['routes'],rows):
        proposal['result'].update(driver_breaks=row.driver_breaks or [],total_min=row.totale_minuti,return_time=row.orario_rientro_stimato.strftime('%H:%M'))
        for stop,delivery in zip(proposal['result']['ordered'],sorted(row.deliveries,key=lambda d:d.ordine)):
            stop.update(arrivo_stimato=delivery.arrivo_stimato.strftime('%H:%M'),partenza_stimata=delivery.partenza_stimata.strftime('%H:%M'))
    updated['warnings']=['Giri programmati. Apri ciascun giro per traffico, pedaggi e costi aggiornati.',
                         'Capacità verificate: peso e colli. Verifica separatamente gli altri requisiti.']
    for row in rows:
        if not row.vehicle.ha_sponda:
            for delivery in row.deliveries:
                if delivery.sponda:
                    updated['warnings'].append(f'{delivery.cliente_nome}: attenzione, questa consegna richiede la sponda, ma il mezzo {row.vehicle.nome} non la possiede.')
        if not row.vehicle.accesso_ztl:
            for delivery in row.deliveries:
                if delivery.ztl:
                    updated['warnings'].append(f'{delivery.cliente_nome}: attenzione, questa consegna è in ZTL, ma il mezzo {row.vehicle.nome} non è abilitato all’accesso.')
    plan.result=updated
    plan.status='programmed';plan.version+=1
    db.commit()
    # Standard assignment notification, only after the entire batch is committed.
    import os
    from .email import send_driver_route_assigned
    failed=[]
    for row in rows:
        if not row.driver.email: continue
        try:
            sent=send_driver_route_assigned(to_email=row.driver.email,
                driver_name=(row.driver.nome+' '+(row.driver.cognome or '')).strip(),
                company_name=user.company_name or user.username or 'GiroFacile',route_name=row.nome,
                data_giro=row.data_giro.isoformat(),orario_partenza=row.orario_partenza.strftime('%H:%M'),
                n_consegne=len(row.deliveries),km_totali=float(row.totale_km or 0),
                portal_url=os.getenv('APP_BASE_URL','https://app.girofacile.it').rstrip('/')+'/driver')
            if not sent: failed.append(row.id)
        except Exception:
            failed.append(row.id)
    if failed:
        updated=deepcopy(plan.result)
        updated['warnings'].append('Giri programmati, ma email non inviata per: '+', '.join(map(str,failed))+'. Avvisa gli autisti dal portale.')
        plan.result=updated;db.commit()
    return plan
