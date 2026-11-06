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


def resource_start(data,resource):
    """Partenza di un giro: l'orario comune, oppure l'inizio turno se l'autista comincia più tardi."""
    schedule=getattr(resource,'driver_schedule',None)
    shift=opt.parse_hhmm(schedule.start) if schedule and schedule.start else None
    common=opt.parse_hhmm(data.orario_partenza)
    if shift is None or common is None or shift<=common: return data.orario_partenza
    return f'{shift//60:02d}:{shift%60:02d}'


def search_vehicle(vehicle,resource,data):
    from ..routers.routes import build_vehicle_dict
    result=build_vehicle_dict(vehicle,resource.driver_schedule.model_dump() if resource.driver_schedule else None)
    start=resource_start(data,resource)
    if result is not None and start!=data.orario_partenza: result['departure']=start
    return result


def overtime(schedule,start,total_min):
    """Minuti di rientro oltre la fine turno (0 se il giro sta nel turno)."""
    end=opt.parse_hhmm((schedule or {}).get('end'))
    begin=opt.parse_hhmm(start)
    if end is None or begin is None or total_min is None: return 0
    return max(0,math.ceil(begin+float(total_min)-end))


def delay(routes):
    """Ordine dei problemi con il traffico: consegne fuori fascia e rientri oltre il turno, poi i minuti."""
    traffic=[route.get('traffic') or {} for route in routes]
    late=[item for t in traffic for item in t.get('late',[])]
    extra=[t.get('overtime_min') or 0 for t in traffic]
    return (len(late)+sum(1 for m in extra if m),round(sum(float(i.get('lateness_min') or 0) for i in late)+sum(extra),1))


# Attesa oltre la quale la proposta lo segnala: tempo pagato all'autista senza consegnare.
WAIT_WARNING_MIN=45


def opt_duration(minutes):
    hours,rest=divmod(int(minutes),60)
    return f'{hours} h {rest} min' if hours and rest else f'{hours} h' if hours else f'{rest} min'


def proposal_start(settings,proposal):
    """Partenza salvata nella proposta (più tarda se elimina attese), altrimenti quella comune o di inizio turno."""
    return (proposal.get('departure') or resource_start(settings,settings.resources[proposal['resource']]))[:5]


def route_data(data,resource,rows,index,driver_name=None,departure=None):
    # Nome automatico di ogni giro: base (la data) · autista; senza autista resta il numero del giro.
    values=data.model_dump(exclude={'resources','strategy','consegne'})
    values.update(nome=f'{data.nome or "Giro consegne"} · {driver_name or index+1}',vehicle_id=resource.vehicle_id,orario_partenza=departure or resource_start(data,resource),
                  driver_id=resource.driver_id,driver_schedule=resource.driver_schedule,consegne=rows,energy_price_mode=resource.energy_price_mode,
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


# Traffico calcolato in anteprima: riusato alla programmazione se ha meno di 60 minuti.
TRAFFIC_REUSE_MINUTES=60


def traffic_margin(db):
    """Margine prudente sui tempi stradali usato dalla ricerca (1.15 = viaggi più lunghi del 15%)."""
    from .platform_settings import routing_number
    return routing_number(db,'fleet_traffic_margin',1.15,1)


def apply_traffic_margin(matrix,margin):
    """Copia della matrice con i tempi allungati del margine; distanze, fonte e cache restano invariate."""
    if margin<=1: return matrix
    from .road_routing import RoadMatrix
    return RoadMatrix({key:{**leg,'min':float(leg.get('min') or 0)*margin} for key,leg in matrix.items()},
                      source=getattr(matrix,'source','osrm'))


def _traffic_snapshot(result,return_depot):
    """Punti e tratte come in initialize_snapshot, così le tratte con traffico restano riutilizzabili."""
    ordered=[dict(d) for d in result['ordered']]
    depot=result.get('depot_coord')
    points=[depot]+[d.get('coord') or {'lat':d.get('lat'),'lon':d.get('lon')} for d in ordered]
    if any(not p or p.get('lat') is None or p.get('lon') is None for p in points): return None
    if return_depot and ordered: points.append(dict(depot))
    base_legs=[{'km':d.get('km_tappa') or 0,'min':d.get('minuti_tappa') or 0} for d in ordered]
    if return_depot and ordered:
        base_legs.append(result.get('base_return_leg') or {'km':0,'min':0})
    return {'points':points,'deliveries':ordered,'base_legs':base_legs}


def preview_traffic(db,user,data,route,vehicle,resource):
    """Traffico reale sul giro proposto: orari aggiornati e clienti fuori fascia, senza cambiare l'ordine."""
    from types import SimpleNamespace
    from .traffic_provider import get_traffic_provider, TrafficUnavailable
    from .route_enrichment import evaluate_legs
    snapshot=_traffic_snapshot(route['result'],data.rientro_deposito)
    if not snapshot: return {'status':'unavailable'}
    start=route.get('departure') or resource_start(data,resource)
    plan=SimpleNamespace(rientro_deposito=data.rientro_deposito,vehicle=vehicle,orario_partenza=start,
                         driver_schedule=resource.driver_schedule.model_dump() if resource.driver_schedule else {})
    departure=opt._route_departure_time_iso(start,data.data_giro)
    try:
        provider=get_traffic_provider(db)
        def advance(legs):
            partial=evaluate_legs(snapshot,legs,plan,return_depot=False)
            return (datetime.fromisoformat(departure.replace('Z','+00:00'))+timedelta(minutes=partial['total_min'])).isoformat()
        traffic=provider.calculate(snapshot['points'],departure,db=db,user_id=user.id,advance_departure=advance)
    except (TrafficUnavailable,ValueError,KeyError,TypeError):
        return {'status':'unavailable'}
    if not traffic: return {'status':'disabled'}
    # Si conservano solo le durate: geometrie e passi di Mapbox pesano centinaia di KB per giro.
    legs=[{'duration':leg['duration'],'distance':leg.get('distance')} for leg in traffic['legs']]
    timed=evaluate_legs(snapshot,legs,plan)
    late=[]
    for position,stop in enumerate(timed['ordered']):
        issue=stop.get('time_window_violation')
        if not issue: continue
        window=issue.get('window') or {}
        late.append({'stop_index':route['stop_indexes'][position],'cliente_nome':stop.get('cliente_nome'),
                     'fine_servizio':issue.get('fine_servizio'),'window':{'start':window.get('start'),'end':window.get('end')},
                     'lateness_min':round(float(issue.get('lateness_min') or 0))})
    return {'status':'updated','provider':traffic['provider'],'departure_time':departure,
            'calculated_at':traffic['calculated_at'],'legs':legs,'total_min':timed['total_min'],
            'return_time':timed.get('return_time'),'late':late,
            # Il traffico può spostare il rientro oltre il turno: la programmazione lo rifiuterebbe.
            'overtime_min':overtime(plan.driver_schedule,start,timed['total_min'])}


def reusable_traffic(proposal,row):
    """Tratte con traffico dell'anteprima, se recenti e calcolate per la stessa partenza e gli stessi punti."""
    from .route_enrichment import json_data
    traffic=(proposal or {}).get('traffic') or {}
    if traffic.get('status')!='updated' or not traffic.get('legs'): return None
    try: calculated=datetime.fromisoformat(traffic['calculated_at'].replace('Z','+00:00'))
    except (KeyError,ValueError,AttributeError): return None
    if (utc_now()-calculated.replace(tzinfo=None))>timedelta(minutes=TRAFFIC_REUSE_MINUTES): return None
    if traffic.get('departure_time')!=opt._route_departure_time_iso(row.orario_partenza,row.data_giro): return None
    points=json_data(row.routing_snapshot_json).get('points') or []
    if len(points)-1!=len(traffic['legs']): return None
    return {'provider':traffic.get('provider','mapbox'),'status':'updated','legs':traffic['legs'],'geometries':[],
            'departure_time':traffic['departure_time'],'calculated_at':traffic['calculated_at'],'version':1,'reused':True}


def day_minutes_left(orario_partenza):
    """Minuti dalla partenza alla fine della giornata: i giri si chiudono in giornata."""
    return max(0,24*60-opt.parse_hhmm(orario_partenza))


def traffic_window_problems(rows):
    """Clienti che, con i tempi aggiornati al traffico, finiscono fuori dalla loro fascia oraria."""
    import json
    problems=[]
    for row in rows:
        driver=row.driver
        who=' '.join(filter(None,[driver.nome,driver.cognome])) if driver else 'senza autista'
        for d in sorted(row.deliveries,key=lambda d:d.ordine or 0):
            issue=json.loads(d.optimizer_details or '{}').get('time_window_violation')
            if not issue: continue
            window=issue.get('window') or {}
            late=round(float(issue.get('lateness_min') or 0))
            problems.append(f"{d.cliente_nome} (giro di {who}): scarico fino alle {issue.get('fine_servizio','—')}, "
                            f"fascia {window.get('start','—')}–{window.get('end','—')}, {late} min oltre")
    return problems


def work_limits(db,user,data):
    """Tempo utilizzabile da ogni coppia prima di altri giri già programmati o della fine della giornata."""
    from ..routers.routes import _check_resource_overlap
    limits=[]
    for index,r in enumerate(data.resources):
        route=route_data(data,r,[],index)
        start=opt.parse_hhmm(route.orario_partenza)
        low,high=0,day_minutes_left(route.orario_partenza)
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


def _refresh_tail_lift_warnings(result,vehicles):
    """Refresh advisory equipment messages without changing route membership."""
    updated=deepcopy(result)
    updated['search']={**updated.get('search',{}),'tail_lift_required':False,
                       'equipment_policy':'prefer-compatible-with-warning-fallback'}
    updated['resource_capabilities']=[{'has_tail_lift':bool(v.ha_sponda),
        'has_ztl_access':bool(v.accesso_ztl)} for v in vehicles]
    updated['warnings']=[warning for warning in updated.get('warnings',[])
                         if 'richiede la sponda' not in warning.lower()]
    for route in updated['routes']:
        vehicle=vehicles[route['resource']]
        for stop in route['result']['ordered']:
            messages=[part.strip() for part in (stop.get('warning') or '').split(';')
                      if part.strip() and not part.strip().lower().startswith(('serve sponda','sponda richiesta'))]
            messages.extend(message for message in opt.delivery_warnings(stop,{'ha_sponda':vehicle.ha_sponda})
                            if 'sponda' in message.lower())
            stop['warning']='; '.join(messages)
            if stop.get('sponda') and not vehicle.ha_sponda:
                updated['warnings'].append(f"Giro {route['resource']+1} · {stop['cliente_nome']}: attenzione, questa consegna richiede la sponda, ma il mezzo non la possiede.")
    return updated


def _distribute_on_time(db,user,data,assignments=None):
    """Consegne ancora fuori orario dopo il riordino: si rifà la divisione tra i mezzi.

    Il nuovo calcolo usa i tempi corretti dal traffico e prima le finestre reali.
    Solo se restano ritardi prova le fasce ridotte da un margine, poi Mapbox. Resta se serve almeno le stesse
    consegne con meno ritardi, anche con più chilometri: la puntualità viene prima.
    Le assegnazioni scelte dall'operatore non vengono rifatte.
    """
    from . import traffic_correction as correction
    late_of=lambda plan:[item for route in plan['routes'] for item in (route.get('traffic') or {}).get('late',[])]
    overtime_of=lambda plan:[(route.get('traffic') or {}).get('overtime_min') or 0 for route in plan['routes']]
    served=lambda plan:sum(len(route['stop_indexes']) for route in plan['routes'])
    result=_distribute(db,user,data,assignments)
    late,extra=late_of(result),max(overtime_of(result) or [0])
    if not (late or extra) or assignments is not None:
        return result
    troubled=[route for route in result['routes'] if route['traffic'].get('late') or route['traffic'].get('overtime_min')]
    factors=[(route['traffic'].get('second_pass') or {}).get('factor') for route in troubled]
    factor=max([f for f in factors if f] or [1.0])
    # Rientro oltre il turno: per la ricerca il turno finisce qualche minuto prima.
    shift=correction.shift_buffer(extra) if extra else 0
    initial_late,initial_overtime=len(late),sum(overtime_of(result))
    attempts=[]
    accepted=False
    # Real customer windows first. A safety margin must not hide a punctual plan.
    for buffer in (0, correction.replan_buffer(late) if late else 0):
        if attempts and buffer==attempts[-1]['buffer_min']: break
        retry=_distribute(db,user,data,None,{'factor':factor,'buffer':buffer,'shift_buffer':shift})
        timed=bool(retry['routes']) and all((route.get('traffic') or {}).get('status')=='updated' for route in retry['routes'])
        improved=timed and served(retry)>=served(result) and delay(retry['routes'])<delay(result['routes'])
        attempts.append({'buffer_min':buffer,'late_after':len(late_of(retry)) if timed else None,
                         'overtime_after':sum(overtime_of(retry)) if timed else None,'accepted':bool(improved)})
        if improved:
            result=retry
            accepted=True
        if not late_of(result) and not any(overtime_of(result)):
            break
    result['search']['on_time_replan']={'factor':round(factor,2),'buffer_min':next((a['buffer_min'] for a in reversed(attempts) if a['accepted']),attempts[-1]['buffer_min']),
        'shift_buffer_min':shift,'late_before':initial_late,'late_after':len(late_of(result)),
        'overtime_before':initial_overtime,'overtime_after':sum(overtime_of(result)),'accepted':accepted,'attempts':attempts}
    return result


def distribute(db,user,data,assignments=None):
    """Clienti raggiungibili solo in traghetto: fuori dalla ricerca, poi tra i non assegnati."""
    from . import islands
    deposit,rows,vehicles,_=input_state(db,user,data)
    ferry=islands.ferry_exclusions(opt.geocode_deposit(db,deposit),rows)
    if not ferry: return _distribute_on_time(db,user,data,assignments)
    kept=[index for index in range(len(rows)) if index not in ferry]
    if kept:
        subset=data.model_copy(update={'consegne':[data.consegne[index] for index in kept]})
        result=_distribute_on_time(db,user,subset,None if assignments is None else [assignments[index] for index in kept])
        for route in result['routes']:
            route['stop_indexes']=[kept[index] for index in route['stop_indexes']]
            for item in (route.get('traffic') or {}).get('late',[]): item['stop_index']=kept[item['stop_index']]
        for item in result['unassigned']: item['index']=kept[item['index']]
    else:
        result={'routes':[],'unassigned':[],'search':{'method':'ferry-exclusion'},
                'resource_capabilities':[{'has_tail_lift':bool(v.ha_sponda),'has_ztl_access':bool(v.accesso_ztl)} for v in vehicles],
                'warnings':[],'validated_depot':{'id':deposit.id,'indirizzo':deposit.indirizzo,'lat':deposit.lat,'lon':deposit.lon},'source':'osrm'}
    result['unassigned']=sorted(result['unassigned']+[{'index':index,'reason':reason} for index,reason in ferry.items()],key=lambda item:item['index'])
    result['validated_stops']=deepcopy(rows)
    result['warnings'].insert(0,islands.warning([rows[index].get('cliente_nome') or 'Cliente senza nome' for index in sorted(ferry)]))
    return result


def _ortools_improvement(rows,vehicle_data,matrix,points,data,limits,refined,results,evaluate,search):
    """OR-Tools parte dal piano trovato e propone giri migliori: resta solo se lo sono davvero.

    «Riduci chilometri e tempi»: giri più corti. «Distribuisci il lavoro»: in più un costo
    sulla durata del giro più lungo; l'accettazione segue comunque la chiave della strategia.

    Confronto su 47 problemi: docs/ortools-full-comparison-2026-11-02.md. Il piano
    proposto passa dal calendario canonico e dal riordino esatto dei giri brevi come
    ogni altro candidato; un errore o un piano peggiore lasciano quello attuale.
    """
    from . import fleet_ortools, fleet_pyvrp
    from .fleet_search import refine_routes,_better
    from .fleet_route_evaluator import FixedRouteEvaluator
    from .fleet_working_clock import _plan_key
    seconds=fleet_ortools.seconds_budget(len(rows)) if fleet_ortools.available() else 0
    # PyVRP (dal 5 novembre 2026) per «Riduci chilometri e tempi» e «Distribuisci il lavoro»;
    # per quest'ultima con un limite di durata dei giri via via più stretto (fleet_pyvrp).
    pyvrp_seconds=(fleet_pyvrp.seconds_budget(len(rows))
                   if data.strategy in ('efficient','balanced') and fleet_pyvrp.available() else 0)
    if not rows or not (seconds or pyvrp_seconds):
        search['ortools']={'status':'disabled' if fleet_ortools.available() else 'unavailable'}
        return refined,results
    # «Riduci chilometri e tempi»: metà del tempo a una passata sul punteggio (km più ore
    # dell'autista) e metà a una sui soli km, che resta una buona strada verso piani corti.
    # Si tiene la proposta migliore secondo la chiave della strategia, cioè il punteggio.
    modes=([('efficient',seconds/2),('distance',seconds/2)] if data.strategy=='efficient' else [(data.strategy,seconds)]) if seconds else []
    if pyvrp_seconds:
        # Anche PyVRP, da zero (docs/motore-pyvrp-2026-11-05.md). Sui problemi di Solomon
        # vince quasi sempre PyVRP, su alcuni piani reali OR-Tools: si tiene il migliore.
        modes.append(('pyvrp',pyvrp_seconds))
    before=_plan_key(refined,results,rows,vehicle_data,data.strategy)
    best=None;reports=[]
    score=lambda sequence,resource:evaluate([rows[i] for i in sequence],resource)
    for mode,budget in modes:
        try:
            engine=fleet_pyvrp.improve if mode=='pyvrp' else fleet_ortools.improve
            orders,report=engine(rows,vehicle_data,matrix,data.orario_partenza,data.rientro_deposito,limits,refined,budget,
                                 data.strategy if mode=='pyvrp' else mode)
        except Exception as exc:  # Un problema del solutore esterno non deve fermare la pianificazione.
            reports.append({'mode':mode,'status':'error','error':type(exc).__name__})
            continue
        report['mode']=mode;reports.append(report)
        if orders is None: continue
        scores=tuple(score(order,v) if order else None for v,order in enumerate(orders))
        if not all(value is not None for order,value in zip(orders,scores) if order):
            report['rejected']='canonical-schedule';continue
        orders,scores,_=refine_routes(orders,scores,score,strategy=data.strategy,global_exact=False,
            prepare=lambda sequence,resource:FixedRouteEvaluator(
                rows,sequence,matrix,points,vehicle_data[resource],data.rientro_deposito,
                data.orario_partenza,limits[resource]))
        after=_plan_key(orders,scores,rows,vehicle_data,data.strategy)
        km=3 if data.strategy=='efficient' else -1  # posizione dei km nella chiave della strategia
        report.update(served_before=-before[0],served_after=-after[0],km_before=round(before[km],2),km_after=round(after[km],2))
        if data.strategy=='efficient': report.update(cost_before=round(before[2],2),cost_after=round(after[2],2))
        if best is None or _better(after,best[0]): best=(after,orders,scores,report)
    if all(report.get('status')=='error' for report in reports):
        search['ortools']={'status':'error','error':reports[0].get('error')};return refined,results
    summary=dict(reports[0]) if len(reports)==1 else {'status':reports[0].get('status'),'seeded':reports[0].get('seeded'),'passes':reports}
    summary['accepted']=False
    if best is not None and _better(best[0],before):
        best[3]['chosen']=True
        summary.update(accepted=True,**{k:best[3][k] for k in ('served_before','served_after','km_before','km_after','cost_before','cost_after') if k in best[3]})
        search['ortools']=summary
        return best[1],best[2]
    search['ortools']=summary
    return refined,results


def _distribute(db,user,data,assignments=None,tighten=None):
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
    margin=traffic_margin(db)
    matrix=apply_traffic_margin(matrix,margin)
    originals=rows
    if tighten:
        # Terzo passaggio: tempi corretti dal traffico e fasce chiuse prima, solo per la ricerca.
        from . import traffic_correction as correction
        matrix=correction.scaled_matrix(matrix,tighten['factor'])
        rows=[correction.buffered(row,tighten['buffer']) for row in rows]
    vehicle_data=[search_vehicle(v,r,data) for v,r in zip(vehicles,data.resources)]
    final_vehicle_data=vehicle_data
    if tighten and tighten.get('shift_buffer'):
        # Il traffico ha portato un rientro oltre il turno: per la ricerca il turno finisce prima.
        from . import traffic_correction as correction
        vehicle_data=[correction.shortened_shift(vehicle,tighten['shift_buffer']) for vehicle in vehicle_data]
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
            return reject(f'Tempo disponibile insufficiente: {limits[resource]} minuti, considerando altri giri già programmati e la fine della giornata.')
        if not include_details:
            # Search memoization retains scalar scores, never thousands of
            # complete copies of stops. Final routes are replayed with details.
            return {key:result[key] for key in ('total_km','total_min','_objective')}
        return result

    def insert(index,distance_first=False,balance=None):
        row=rows[index];best=None;reasons=[]
        balance=(data.strategy=='balanced') if balance is None else balance
        for resource,sequence in enumerate(routes):
            failures=set()
            for position in range(len(sequence)+1):
                candidate=sequence[:position]+[row]+sequence[position:]
                evaluated=evaluate(candidate,resource,failures)
                if evaluated is None: continue
                durations=[r['total_min'] if r else 0 for r in results];durations[resource]=evaluated['total_min']
                delta=evaluated['total_min']-(results[resource]['total_min'] if results[resource] else 0)
                if balance:
                    # Ore dell'autista senza le attese eliminabili partendo più tardi (optimizer.work_minutes).
                    durations=[opt.work_minutes(r) for r in results];durations[resource]=opt.work_minutes(evaluated)
                    delta=durations[resource]-opt.work_minutes(results[resource])
                    key=(sum(not r for i,r in enumerate(routes) if i!=resource),max(durations),sum(x*x for x in durations),delta,evaluated['total_km'])
                elif distance_first:
                    distances=[float(r['_objective'][0]) if r else 0 for r in results]
                    distances[resource]=evaluated['_objective'][0]
                    raw_minutes=[float(r['_objective'][1]) if r else 0 for r in results]
                    raw_minutes[resource]=evaluated['_objective'][1]
                    # Costruzione «per distanza»: un punto di partenza diverso per la ricerca, che poi sceglie per costo.
                    key=(sum(distances),sum(raw_minutes),sum(bool(route) for route in routes if route)+int(not sequence))
                else: key=(0 if sequence else 1,delta,evaluated['total_km'])
                # Equipment is advisory: prefer compatibility after coverage.
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
        from .fleet_search import optimize_fleet,stable_stop_key
        import json
        def equipment(sequence, resource):
            return sum(
                int(bool(rows[i].get('sponda')) and not vehicles[resource].ha_sponda)
                + int(bool(rows[i].get('ztl')) and not vehicles[resource].accesso_ztl)
                for i in sequence)
        def membership_compatible(sequence,resource):
            selected=[rows[i] for i in sequence]
            try:
                opt.validate_vehicle_load(selected,vehicle_data[resource])
            except ValueError:
                return False
            return True
        legacy_order=sorted(range(len(rows)),key=lambda i:(not(rows[i]['sponda'] or rows[i]['ztl']),not bool(opt.delivery_windows(rows[i])),-rows[i]['peso_kg'],-rows[i]['colli'],i))
        legacy_canonical=sorted(range(len(rows)),key=lambda i:(not(rows[i]['sponda'] or rows[i]['ztl']),not bool(opt.delivery_windows(rows[i])),-rows[i]['peso_kg'],-rows[i]['colli'],stable_stop_key(rows[i])))
        def urgency(index):
            windows=opt.delivery_windows(rows[index])
            closing=min((end for _,end in windows),default=float('inf'))
            width=min((end-start for start,end in windows),default=float('inf'))
            return (not rows[index]['sponda'],closing,width,-rows[index]['peso_kg'],-rows[index]['colli'],stable_stop_key(rows[index]))
        canonical_order=sorted(range(len(rows)),key=urgency)
        initial_candidates=[]
        # Keep the former construction as a quality floor under the CURRENT
        # physical constraints; add urgency-first time and distance proposals.
        constructions=[(legacy_order,False,None),(legacy_canonical,False,None),
                       (canonical_order,False,None),(canonical_order,True,False)]
        if data.strategy=='efficient':
            # A balanced construction can retain scarce capacity/time slots;
            # the final selection still follows coverage, then km and minutes.
            constructions.extend((order,False,True) for order in
                                 (canonical_order,legacy_canonical,legacy_order))
        else:
            constructions.extend((order,False,False) for order in
                                 (canonical_order,legacy_canonical,legacy_order))
        seen_constructions=set();constructed_candidates={}
        for order,distance_first,balance in constructions:
            balanced=(data.strategy=='balanced') if balance is None else balance
            construction=(tuple(order),'balanced' if balanced
                          else 'distance' if distance_first else 'legacy-time')
            if construction in seen_constructions:
                continue
            seen_constructions.add(construction)
            routes=[[] for _ in vehicles];results=[None for _ in vehicles];unresolved={}
            for index in order: insert(index,distance_first,balance)
            initial_candidates.append((tuple(tuple(row['fleet_stop_index'] for row in route) for route in routes),tuple(results)))
            constructed_candidates[construction]=initial_candidates[-1]
        def initial_key(candidate):
            sequences,scores=candidate
            common=(-sum(map(len,sequences)),sum(equipment(route,r) for r,route in enumerate(sequences)))
            minutes=[float(score['_objective'][1]) if score else 0 for score in scores]
            km=sum(float(score['_objective'][0]) for score in scores if score)
            used=sum(bool(route) for route in sequences)
            work=[opt.work_minutes(score) for score in scores]
            return common+((-used,max(work,default=0),sum(value*value for value in work),sum(work),km)
                           if data.strategy=='balanced' else (sum(opt.objective_cost(score) for score in scores if score),km,sum(minutes),used))
        initial_routes,initial_results=min(initial_candidates,key=initial_key)
        signature_fields=('driver_schedule','ha_sponda','accesso_ztl','capacita_kg','capacita_colli')
        signatures=[json.dumps({key:v.get(key) for key in signature_fields},sort_keys=True,default=str)+':'+str(limit)
                    for v,limit in zip(vehicle_data,limits)]
        proposed,optimized_results,search=optimize_fleet(
            rows,len(vehicles),
            lambda sequence,resource:evaluate([rows[i] for i in sequence],resource),
            data.strategy,initial_routes=initial_routes,
            initial_results=initial_results,initial_candidates=initial_candidates,matrix=matrix,points=points,
            equipment_penalty=equipment,resource_signatures=signatures,
            membership_compatible=membership_compatible,
            return_depot=data.rientro_deposito)
        if data.strategy=='efficient':
            # Rete di sicurezza: la stessa ricerca guidata dai soli km (la regola precedente al
            # 5 novembre 2026). Esplora piani che la ricerca sul punteggio può non visitare;
            # vince sempre la proposta migliore per copertura, attrezzatura e punteggio km + ore.
            from time import perf_counter
            from .fleet_working_clock import _plan_key
            from .fleet_search import _better
            distance_started=perf_counter()
            distance_initial=min(initial_candidates,key=lambda candidate:
                _plan_key(candidate[0],candidate[1],rows,vehicle_data,'distance'))
            km_routes,km_scores,km_search=optimize_fleet(
                rows,len(vehicles),
                lambda sequence,resource:evaluate([rows[i] for i in sequence],resource),
                'distance',initial_routes=distance_initial[0],initial_results=distance_initial[1],
                initial_candidates=initial_candidates,matrix=matrix,points=points,
                equipment_penalty=equipment,resource_signatures=signatures,
                membership_compatible=membership_compatible,return_depot=data.rientro_deposito)
            km_better=_better(_plan_key(km_routes,km_scores,rows,vehicle_data,'efficient'),
                              _plan_key(proposed,optimized_results,rows,vehicle_data,'efficient'))
            if km_better:
                proposed,optimized_results=km_routes,km_scores
            search['distance_portfolio']=dict(improved=km_better,
                evaluations=km_search.get('additional_evaluations'),wall_seconds=round(perf_counter()-distance_started,2))
        # A globally constrained feasibility model is a separate recovery
        # stage: do not declare a delivery impossible because local moves
        # exhausted their evaluation quota. It shares this matrix and replays
        # every proposed itinerary with the canonical scheduler above.
        potentially_serviceable=sum(any(membership_compatible((i,),resource)
            for resource in range(len(vehicles))) for i in range(len(rows)))
        from .fleet_search import candidate_limit
        if (sum(map(len,proposed))<potentially_serviceable
                and not search.get('global_optimum_proven')
                and candidate_limit(len(rows))>0):
            from time import perf_counter
            from .fleet_working_clock import _plan_key
            from .fleet_search import _better
            recovery_started=perf_counter()
            alternate='balanced' if data.strategy=='efficient' else 'efficient'
            preferred=constructed_candidates[(tuple(legacy_order),
                'balanced' if alternate=='balanced' else 'legacy-time')]
            alternate_candidates=[preferred]+[candidate for candidate in initial_candidates
                if candidate is not preferred]
            alternate_initial=min(alternate_candidates,key=lambda candidate:
                _plan_key(candidate[0],candidate[1],rows,vehicle_data,alternate))
            other_routes,other_scores,portfolio=optimize_fleet(
                rows,len(vehicles),
                lambda sequence,resource:evaluate([rows[i] for i in sequence],resource),
                alternate,initial_routes=alternate_initial[0],initial_results=alternate_initial[1],
                initial_candidates=alternate_candidates,matrix=matrix,points=points,
                equipment_penalty=equipment,resource_signatures=signatures,
                membership_compatible=membership_compatible,return_depot=data.rientro_deposito)
            recovery_candidates=[(proposed,optimized_results),(other_routes,other_scores)]
            improved=_better(_plan_key(other_routes,other_scores,rows,vehicle_data,data.strategy),
                             _plan_key(proposed,optimized_results,rows,vehicle_data,data.strategy))
            if improved:
                proposed,optimized_results=other_routes,other_scores
            search['coverage_portfolio']=dict(strategy=alternate,improved=improved,
                search=portfolio,wall_seconds=perf_counter()-recovery_started)
            if sum(map(len,proposed))<potentially_serviceable:
                from .fleet_milp_solver import solve_fleet_milp
                # Repair from the shorter-distance search basin; acceptance
                # still uses the operator's selected strategy and incumbent.
                seed=min(recovery_candidates,key=lambda candidate:
                    _plan_key(candidate[0],candidate[1],rows,vehicle_data,'efficient'))
                recovered,recovered_scores,recovery=solve_fleet_milp(
                    rows,vehicle_data,matrix,points,data.orario_partenza,
                    data.rientro_deposito,limits,seed[0],
                    lambda sequence,resource:evaluate([rows[i] for i in sequence],resource),
                    initial_results=seed[1],strategy=data.strategy,
                    max_seconds=max(0,30-(perf_counter()-recovery_started)))
                if _better(_plan_key(recovered,recovered_scores,rows,vehicle_data,data.strategy),
                           _plan_key(proposed,optimized_results,rows,vehicle_data,data.strategy)):
                    proposed,optimized_results=recovered,recovered_scores
                search['constraint_recovery']=recovery
        routes=[[rows[i] for i in sequence] for sequence in proposed]
        results=list(optimized_results)
        search['tail_lift_required']=False
        search['equipment_policy']='prefer-compatible-with-warning-fallback'
        search['primary_objective']='km-and-driver-hours' if data.strategy=='efficient' else 'balanced-workload'
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
        strategy=data.strategy,
        global_exact=bool(search.get('global_optimum_proven')),
        prepare=lambda sequence,resource:FixedRouteEvaluator(
            rows,sequence,matrix,points,vehicle_data[resource],data.rientro_deposito,
            data.orario_partenza,limits[resource]))
    search.update(refinement)
    if assignments is None and not search.get('global_optimum_proven'):
        refined,results=_ortools_improvement(rows,vehicle_data,matrix,points,data,limits,refined,results,evaluate,search)
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
    if tighten:
        # Orari finali con le fasce vere del cliente: il margine serviva solo alla ricerca.
        routes=[[originals[row['fleet_stop_index']] for row in route] for route in routes]
        rows=originals
        vehicle_data[:]=final_vehicle_data
    # Partenza più tarda se l'autista aspetterebbe i clienti: stesso rientro, meno ore di lavoro.
    for index,sequence in enumerate(routes):
        original=vehicle_data[index]
        if not sequence or original is None: continue
        base=evaluate(sequence,index,include_details=True)
        if base is None: continue
        def at(clock,index=index,sequence=sequence,original=original):
            vehicle_data[index]={**original,'departure':opt.fmt_hhmm(clock),'_flexible_departure':False}
            try: return evaluate(sequence,index,include_details=True)
            finally: vehicle_data[index]=original
        _,moved=opt.later_departure(base,opt.vehicle_start_clock(data.orario_partenza,original),at)
        # The chosen departure is now fixed: final working time includes all
        # waiting that remains, without discounting another future proposal.
        vehicle_data[index]={**original,'_flexible_departure':False}
        if moved is not None: vehicle_data[index]['departure']=opt.fmt_hhmm(moved)
    # Generate complete ETA and diagnostic details only for selected final routes.
    results=[evaluate(sequence,index,include_details=True) if sequence else None
             for index,sequence in enumerate(routes)]
    def build_route(index,result):
        indexes=[s['fleet_stop_index'] for s in result['ordered']]
        for stop in result['ordered']: stop.pop('fleet_stop_index',None)
        for field in ('score','_objective','violations','total_wait','_sequence','departure_slack_min'): result.pop(field,None)
        result.update(base_routing_provider=getattr(matrix,'source','osrm'),depot_coord=depot,
                      base_return_leg=dict(matrix.get((indexes[-1]+1,0)) or {}) if data.rientro_deposito else {},
                      google_maps_url=opt.build_google_maps_url(deposit.indirizzo,result['ordered'],data.rientro_deposito))
        return {'resource':index,'vehicle_name':vehicles[index].nome,'driver_name':(drivers[index].nome+' '+(drivers[index].cognome or '')).strip(),
                'stop_indexes':indexes,'result':result,
                'departure':opt.fmt_hhmm(opt.vehicle_start_clock(data.orario_partenza,vehicle_data[index])),'fuel_cost':fuel_cost(vehicles[index],data.resources[index],result['total_km']),
                'weight_kg':sum(rows[i]['peso_kg'] for i in indexes),'packages':sum(rows[i]['colli'] for i in indexes)}

    def traffic_second_pass(route):
        """Fuori orario con il traffico: riordino con i tempi corretti e nuova richiesta a Mapbox."""
        from . import traffic_correction as correction
        first=route['traffic']
        if first.get('status')!='updated' or not (first.get('late') or first.get('overtime_min')): return route
        snapshot=_traffic_snapshot(route['result'],data.rientro_deposito)
        factor=correction.travel_factor([leg['min'] for leg in snapshot['base_legs']],[leg['duration'] for leg in first['legs']])
        report={'factor':round(factor,2) if factor else None,'late_before':len(first['late']),
                'overtime_before':first.get('overtime_min') or 0,'reordered':False}
        first['second_pass']=report
        if not factor: return route
        resource=route['resource']
        ordered=opt._best_internal_sequence([rows[i] for i in route['stop_indexes']],correction.scaled_matrix(matrix,factor),
                                            points,vehicle_data[resource],data.rientro_deposito,resource_start(data,data.resources[resource]))['ordered']
        indexes=[stop['fleet_stop_index'] for stop in ordered]
        if indexes==route['stop_indexes']: return route
        result=evaluate([rows[i] for i in indexes],resource,include_details=True)
        if result is None: return route
        candidate=build_route(resource,result)
        candidate['traffic']=preview_traffic(db,user,data,candidate,vehicles[resource],data.resources[resource])
        if candidate['traffic'].get('status')!='updated': return route
        report.update(late_after=len(candidate['traffic']['late']),overtime_after=candidate['traffic'].get('overtime_min') or 0)
        if delay([candidate])<delay([route]):
            report['reordered']=True
            candidate['traffic']['second_pass']=report
            return candidate
        return route

    output=[build_route(index,result) for index,result in enumerate(results) if result is not None]
    for route in output:
        route['traffic']=preview_traffic(db,user,data,route,vehicles[route['resource']],data.resources[route['resource']])
    output=[traffic_second_pass(route) for route in output]
    statuses={route['traffic']['status'] for route in output}
    late=[item for route in output for item in route['traffic'].get('late',[])]
    if output and statuses=={'updated'}:
        timing='Tempi con traffico aggiornato: verranno riusati alla programmazione se non passa più di un’ora. Pedaggi calcolati alla programmazione. Costi mostrati: solo energia/carburante.'
    else:
        timing=(f'Traffico non disponibile per uno o più giri: tempi stradali con margine prudente del {round((margin-1)*100)}%; '
                'il traffico sarà verificato alla programmazione. Costi mostrati: solo energia/carburante.')
    warnings=[timing,'Capacita automatiche: peso e colli. Verifica separatamente volume, pallet, transpallet e altri requisiti.']
    if late:
        warnings.insert(0,f'Con il traffico {len(late)} {"cliente sarebbe servito" if len(late)==1 else "clienti sarebbero serviti"} fuori orario: '
                        'spostali in un altro giro o allarga la loro fascia, poi ricalcola.')
    for route in output:
        extra=route['traffic'].get('overtime_min') or 0
        if extra:
            schedule=data.resources[route['resource']].driver_schedule
            warnings.insert(0,f"Giro {route['resource']+1} · {route['driver_name']}: con il traffico rientra alle {route['traffic'].get('return_time')}, "
                            f"{extra} min dopo la fine del turno ({schedule.end}). Sposta una consegna in un altro giro o allunga il turno, poi ricalcola.")
    if getattr(matrix,'source','osrm') in ('estimated','mixed'):
        warnings.insert(0,'Routing stradale non disponibile per alcune tratte: tempi e distanze approssimativi, da verificare.')
    for route in output:
        # Partenza spostata per evitare attese, e attese che restano comunque lunghe.
        name=f"Giro {route['resource']+1} · {route['driver_name']}"
        usual=resource_start(data,data.resources[route['resource']])[:5]
        if route.get('departure') and route['departure']!=usual:
            warnings.append(f"{name}: parte alle {route['departure']} invece delle {usual}, così l'autista non aspetta l'apertura dei clienti. Puoi cambiare l'orario dal giro.")
        waited=round(float(route['result'].get('total_wait_min') or 0))
        if waited>=WAIT_WARNING_MIN:
            warnings.append(f"{name}: {opt_duration(waited)} di attesa ai clienti anche con la partenza alle {route.get('departure') or usual}. "
                            "Sposta in un altro giro le consegne con fasce lontane tra loro, oppure allarga le fasce, poi ricalcola.")
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
    return {'id':plan.id,'version':plan.version,'status':plan.status,'configuration':plan.configuration,'created_at':plan.created_at,
            'routes':[{k:({**v,'legs':None} if k=='traffic' and isinstance(v,dict) else v) for k,v in r.items()} for r in plan.result['routes']],
            'unassigned':plan.result['unassigned'],'warnings':plan.result['warnings'],'route_ids':plan.route_ids,
            'resource_capabilities':plan.result.get('resource_capabilities',[]),
            'search':{**plan.result.get('search',{}),'tail_lift_required':False,
                      'equipment_policy':'prefer-compatible-with-warning-fallback'}}


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
    plan.result=_refresh_tail_lift_warnings(plan.result,vehicles)
    route_ids=[]
    for route in plan.result['routes']:
        index=route['resource'];resource=settings.resources[index];result=deepcopy(route['result'])
        opt.validate_vehicle_load(result['ordered'],build_vehicle_dict(vehicles[index]))
        driver=db.get(Driver,resource.driver_id) if resource.driver_id else None
        driver_name=' '.join(x for x in (driver.nome,driver.cognome) if x).strip() if driver else None
        payload=route_data(settings,resource,result['ordered'],index,driver_name,proposal_start(settings,route))
        start=opt.parse_hhmm(payload.orario_partenza)
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
            or row.data_giro.isoformat()!=settings.data_giro or row.orario_partenza.strftime('%H:%M')!=proposal_start(settings,proposal)):
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
                or row.data_giro.isoformat()!=settings.data_giro or row.orario_partenza.strftime('%H:%M')!=proposal_start(settings,proposal)
                or row.deposit_id!=settings.deposit_id or row.rientro_deposito!=settings.rientro_deposito
                or row.vehicle_id!=expected.vehicle_id or row.driver_id!=expected.driver_id):
                raise HTTPException(409,'Un giro e stato modificato o programmato separatamente: gestiscilo dallo storico.')
        return rows
    for row,proposal in zip(drafts(),plan.result['routes']):
        enrich_final_route(db,row,cached_traffic=reusable_traffic(proposal,row))
    db.commit()  # Persist timing and provider accounting before releasing route locks.
    route_orders.lock_company(db,user.id)
    plan=get_plan(db,user,actor,plan_id,lock=True)
    if plan.status=='programmed': return plan
    check_version(plan,data.version)
    rows=drafts()
    # Come per il giro singolo, uno scarico fuori fascia non blocca: resta un avviso sui giri programmati.
    problems=traffic_window_problems(rows)
    for row in rows:
        from .driver_schedule import ensure_shift
        ensure_shift(row.driver_schedule,row.orario_partenza,row.totale_minuti)
        db.query(RoutePlan).filter_by(id=row.id,user_id=user.id).with_for_update().one()
        lock_route_resources(db,row)
        from ..models import Deposit
        vehicle=_require_owned_entity(db,Vehicle,user,row.vehicle_id,'Mezzo')
        db.refresh(vehicle)
        _require_owned_entity(db,Driver,user,row.driver_id,'Autista')
        _require_owned_entity(db,Deposit,user,row.deposit_id,'Deposito')
        ensure_not_past_route_date(row.data_giro)
        ensure_future_departure(row.data_giro,row.orario_partenza)
        check_daily_route_limit(user,db,row.data_giro,exclude_route_id=row.id)
        opt.validate_vehicle_load([{'peso_kg':d.peso_kg,'colli':d.colli} for d in row.deliveries],build_vehicle_dict(row.vehicle))
        departure=row.orario_partenza.strftime('%H:%M')
        if math.ceil(row.totale_minuti)>day_minutes_left(departure):
            raise HTTPException(409,'Con il traffico aggiornato un giro supera la fine della giornata. Anticipa la partenza o sposta alcune consegne, poi ricalcola.')
        start=opt.parse_hhmm(departure)
        _check_resource_overlap(db,user,row,start,start+math.ceil(row.totale_minuti),exclude_route_id=row.id)
    from ..models import RouteToken
    from secrets import token_urlsafe
    for row in rows:
        db.query(RouteToken).filter_by(route_plan_id=row.id).delete()
        db.add(RouteToken(route_plan_id=row.id,token=token_urlsafe(32),expires_at=utc_now()+timedelta(days=3)))
        row.status='programmato'
        route_orders.sync_route_orders(db,row,'scheduled')
    updated=deepcopy(plan.result)
    updated['search']={**updated.get('search',{}),'tail_lift_required':False,
                       'equipment_policy':'prefer-compatible-with-warning-fallback'}
    updated['resource_capabilities']=[{'has_tail_lift':bool(db.get(Vehicle,r.vehicle_id).ha_sponda),'has_ztl_access':bool(db.get(Vehicle,r.vehicle_id).accesso_ztl)} for r in settings.resources]
    for proposal,row in zip(updated['routes'],rows):
        proposal['result'].update(driver_breaks=row.driver_breaks or [],total_min=row.totale_minuti,return_time=row.orario_rientro_stimato.strftime('%H:%M'))
        for stop,delivery in zip(proposal['result']['ordered'],sorted(row.deliveries,key=lambda d:d.ordine)):
            stop.update(arrivo_stimato=delivery.arrivo_stimato.strftime('%H:%M'),partenza_stimata=delivery.partenza_stimata.strftime('%H:%M'))
    updated['warnings']=['Giri programmati. Apri ciascun giro per traffico, pedaggi e costi aggiornati.',
                         'Capacità verificate: peso e colli. Verifica separatamente gli altri requisiti.']
    if problems:
        updated['warnings'].insert(0,'Programmati con clienti fuori orario per il traffico: '+'; '.join(problems)+'.')
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
            if not sent: failed.append(row)
        except Exception:
            failed.append(row)
    if failed:
        updated=deepcopy(plan.result)
        names=[f"{r.nome} ({(r.driver.nome+' '+(r.driver.cognome or '')).strip()})" for r in failed]
        updated['warnings'].append('Giri programmati, ma email non inviata per: '+'; '.join(names)+'. Avvisa gli autisti dal portale.')
        plan.result=updated;db.commit()
    return plan
