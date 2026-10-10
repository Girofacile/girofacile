/* Persistent selection and a narrow adapter to the existing planning workspace. */
(function(){
  'use strict';
  let state={version:0,order_ids:[],configuration:{},stops:null,routes:[]};
  let editingRouteId=null;
  let enabled=false,loadedStops=false,busy=false,dirty=false,saving=null,timer;
  const ids=['routeName','routeDate','routeStart','routeDeposit','routeVehicle','routeDriver','returnDepot','fuelPrice','electricityPrice'];
  const el=id=>document.getElementById(id);
  const allowed=()=>!window.GFCompanyAccess || GFCompanyAccess.can('orders.plan');
  const message=text=>{if(el('orderPlanningMessage'))el('orderPlanningMessage').textContent=text;};
  const metadata=row=>Object.fromEntries(['order_refs','order_stop_key','order_numbers','order_operational'].filter(k=>row?.[k]!==undefined).map(k=>[k,row[k]]));
  function controls(){
    const panel=el('ordersSelection');if(!panel)return;
    panel.hidden=!allowed();
    el('ordersSelectionCount').textContent=`${state.order_ids.length} ordini selezionati. La selezione è salvata per il tuo account, anche se cambi pagina o esci.`;
    el('ordersGoPlanning').textContent=`Vai alla pianificazione (${state.order_ids.length} ordini)`;
    el('ordersGoPlanning').disabled=busy || !state.order_ids.length || !!state.routes.length;
    el('ordersSelectionRoutes').innerHTML=state.routes.map(r=>`<button class="btn-secondary" onclick="GFOrderPlanning.openRoute(${r.id})">Apri ${r.status==='bozza'?'bozza':'giro'} #${r.id} · ${esc(r.name||'Giro consegne')}</button>`).join('');
    if(state.routes.length)el('ordersSelectionCount').textContent+=' Alcuni ordini sono già riservati: apri il giro oppure svuota la selezione per prepararne un’altra.';
    panel.querySelectorAll('.order-selection-action').forEach(button=>button.disabled=busy);
  }
  async function loadSelection(){
    if(!allowed()){state={...state,order_ids:[],routes:[]};controls();return;}
    await flush();
    state=await api('/api/order-planning/selection');controls();
  }
  function checkbox(order){
    if(!allowed())return '';
    const checked=state.order_ids.includes(order.id);
    return `<input class="order-select" type="checkbox" aria-label="Seleziona ordine ${esc(order.number)}" ${checked?'checked':''} ${busy || (order.status!=='pronto'&&!checked)?'disabled':''} onchange="GFOrderPlanning.select(${order.id},this.checked)">`;
  }
  function filters(){return Object.fromEntries([['ordersSearch','q'],['ordersStatus','status'],['ordersSource','source_id'],['ordersFrom','date_from'],['ordersTo','date_to']].map(([id,key])=>[key,el(id).value?(key==='source_id'?Number(el(id).value):el(id).value):null]).filter(([,value])=>value!==null));}
  async function change(action,order_ids=[]){
    if(busy)return;
    busy=true;controls();document.querySelectorAll('.order-select').forEach(e=>e.disabled=true);
    try{
      await flush();
      state=await api('/api/order-planning/selection',{method:'PUT',body:JSON.stringify({version:state.version,action,order_ids,filters:filters()})});
      enabled=false;loadedStops=false;dirty=false;gate();
      await GFOrders.load();
    }catch(e){el('ordersMessage').textContent=e.message;await loadSelection().catch(()=>{});}
    finally{busy=false;controls();GFOrders.refreshSelection?.();}
  }
  function config(){return {nome:val('routeName'),data_giro:val('routeDate'),orario_partenza:val('routeStart'),deposit_id:Number(val('routeDeposit'))||null,vehicle_id:Number(val('routeVehicle'))||null,driver_id:Number(val('routeDriver'))||null,rientro_deposito:boolVal('returnDepot'),energy_price_mode:document.querySelector('input[name="energyPriceMode"]:checked')?.value||'manual',energy_price_primary:Number(val('fuelPrice'))||0,energy_price_electric:Number(val('electricityPrice'))||0};}
  function gate(){
    const banner=el('orderPlanningBanner');if(banner)banner.hidden=!enabled;
    if(!enabled)return;
    const button=el('openCustomerStepBtn');if(button)button.textContent='Prosegui';
    if(el('customerPlanningStep'))el('customerPlanningStep').classList.add('hidden');
    if(el('routePlanningGateHint'))el('routePlanningGateHint').textContent=loadedStops?'Fermate degli ordini caricate. Verifica i dati e premi Calcola percorso.':'Completa la configurazione e premi Prosegui per caricare gli ordini selezionati.';
  }
  async function go(){
    try{
      await flush();await loadSelection();
      if(!state.order_ids.length || state.routes.length)return;
      if(deliveries.length && !enabled && !confirm('Sostituire le fermate aperte nel pianificatore con questa selezione? I giri già salvati restano disponibili nello storico.'))return;
      const saved=state.configuration;
      clearRouteWorkspace();enabled=true;loadedStops=false;dirty=false;
      showTab('giro');
      if(saved.data_giro){
        for(const [id,key] of [['routeName','nome'],['routeDate','data_giro'],['routeStart','orario_partenza'],['routeDeposit','deposit_id'],['returnDepot','rientro_deposito'],['fuelPrice','energy_price_primary'],['electricityPrice','energy_price_electric']])set(id,saved[key]??'');
        await refreshResourceAvailability();set('routeVehicle',saved.vehicle_id||'');set('routeDriver',saved.driver_id||'');
        const mode=document.querySelector(`input[name="energyPriceMode"][value="${saved.energy_price_mode||'manual'}"]`);if(mode)mode.checked=true;
        await updateRouteEnergyPricingV895();
      }
      updateRoutePlanningGateV68();gate();message(`${state.order_ids.length} ordini salvati. Completa la configurazione del giro.`);
    }catch(e){alert(e.message);}
  }
  async function proceed(){
    if(!routePlanningDetailsCompleteV68()){updateRoutePlanningGateV68();message('Completa data, orario, deposito, mezzo, autista e costi energetici.');return;}
    try{
      await flush();
      state=await api('/api/order-planning/preview',{method:'POST',body:JSON.stringify({version:state.version,configuration:config(),stops:loadedStops?deliveries:state.stops})});
      deliveries=state.stops;loadedStops=true;dirty=false;customerPlanningStepOpenedV68=true;
      updateRoutePlanningGateV68();renderDeliveries();gate();
      message(state.warnings.length?state.warnings.join('\n'):'Fermate caricate. Puoi modificarle o rimuoverle senza cambiare gli ordini originali. Il giro non è ancora calcolato né programmato.');
      el('deliveryWorkbenchStep').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){message(e.message);}
  }
  function changed(){
    if(!enabled || lastRouteResult?.id)return;
    dirty=true;clearTimeout(timer);message('Salvataggio della configurazione…');
    timer=setTimeout(()=>flush().catch(e=>message('Bozza non salvata: '+e.message)),400);
  }
  async function flush(){
    clearTimeout(timer);
    if(saving)await saving;
    if(!dirty || !enabled)return;
    dirty=false;
    const payload={version:state.version,configuration:config(),stops:loadedStops?deliveries:state.stops};
    saving=api('/api/order-planning/snapshot',{method:'PUT',body:JSON.stringify(payload)}).then(result=>{state=result;message('Configurazione salvata. Puoi riprenderla dalla pagina Ordini.');}).catch(e=>{dirty=true;throw e;});
    try{await saving;}finally{saving=null;}
    if(dirty)await flush();
  }
  async function beforeCalculate(){try{await flush();return true;}catch(e){message(e.message);alert('Salva la selezione prima del calcolo: '+e.message);return false;}}
  function leave(){editingRouteId=null;enabled=false;loadedStops=false;dirty=false;clearTimeout(timer);gate();}
  function describe(row){
    if(!row.order_refs?.length)return '';
    const values=row.order_operational||{},parts=[];
    if(values.pallet_truck!==null && values.pallet_truck!==undefined)parts.push('Transpallet: '+(values.pallet_truck?'Sì':'No'));
    if(values.pallets!=null)parts.push('Pallet: '+values.pallets);
    if(values.volume_m3!=null)parts.push('Volume: '+values.volume_m3+' m³');
    if(values.requirements)parts.push(values.requirements);
    return `<small>Ordine ${esc((row.order_numbers||row.order_refs.map(r=>'#'+r.id)).join(', '))}</small>${parts.length?'<small>'+esc(parts.join(' · '))+'</small>':''}`;
  }
  document.addEventListener('change',e=>{if(ids.includes(e.target.id)||e.target.name==='energyPriceMode')changed();});
  window.addEventListener('beforeunload',e=>{if(enabled&&(dirty||saving)){e.preventDefault();e.returnValue='';}});
  window.GFOrderPlanning={loadSelection,checkbox,controls,metadata,describe,active:()=>enabled,gate,go,proceed,changed,flush,beforeCalculate,leave,
    save:()=>flush().catch(e=>message(e.message)),
    select:(id,checked)=>change(checked?'add':'remove',[id]),
    selectPage:checked=>change(checked?'add':'remove',GFOrders.currentItems().filter(o=>checked?o.status==='pronto':state.order_ids.includes(o.id)).map(o=>o.id)),
    allFiltered:()=>change('all_filtered'),clear:()=>change('clear'),
    openRoute(id){leave();openProgrammedRouteForEdit(id,true);},
    routeId:()=>editingRouteId,
    opened(route){editingRouteId=route.consegne?.some(d=>d.order_refs?.length)?route.id:null;},
    calculated(route){leave();editingRouteId=route.consegne?.some(d=>d.order_refs?.length)?route.id:null;message('Bozza calcolata e salvata. Premi Programma giro per renderla operativa.');}
  };
})();
