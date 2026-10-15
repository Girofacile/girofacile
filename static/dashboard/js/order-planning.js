/* Persistent selection and a narrow adapter to the existing planning workspace. */
(function(){
  'use strict';
  let state={version:0,order_ids:[],configuration:{},stops:null,routes:[]};
  let editingRouteId=null,proceeding=false;
  let enabled=false,loadedStops=false,busy=false,dirty=false,saving=null,timer;
  const ids=['routeName','routeDate','routeStart','routeDeposit','routeVehicle','routeDriver','returnDepot','fuelPrice','electricityPrice'];
  const el=id=>document.getElementById(id);
  const allowed=()=>!window.GFCompanyAccess || GFCompanyAccess.can('orders.plan');
  const message=text=>{if(el('orderPlanningMessage'))el('orderPlanningMessage').textContent=text;};
  function feedback(text,state='error'){
    const box=el('orderPlanningProceedMessage');if(!box)return;
    box.textContent=text;box.hidden=!text;box.dataset.state=state;
    if(text&&state==='error'){box.scrollIntoView({behavior:'smooth',block:'center'});box.focus({preventScroll:true});}
  }
  const metadata=row=>Object.fromEntries(['order_refs','order_stop_key','order_numbers','order_operational'].filter(k=>row?.[k]!==undefined).map(k=>[k,row[k]]));
  function controls(){
    const panel=el('ordersSelection');if(!panel)return;
    const count=state.order_ids.length;
    panel.hidden=!allowed() || (!count && !state.routes.length);
    const countLabel=count===1?'1 ordine selezionato':`${count} ordini selezionati`;
    el('ordersSelectionCount').textContent=countLabel;
    const dot=panel.querySelector('[data-orders-selection-count]');if(dot)dot.textContent=String(count);
    el('ordersGoPlanning').textContent=`Vai alla pianificazione (${count})`;
    el('ordersGoPlanning').disabled=busy || !count || !!state.routes.length;
    el('ordersSelectionRoutes').innerHTML=state.routes.map(r=>`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFOrderPlanning.openRoute(${r.id})">Apri ${r.status==='bozza'?'bozza':'giro'} #${r.id} · ${esc(r.name||'Giro consegne')}</button>`).join('');
    if(state.routes.length)el('ordersSelectionCount').textContent=countLabel+' · alcuni ordini sono già riservati';
    panel.querySelectorAll('[data-order-selection-action]').forEach(button=>button.disabled=busy);
  }
  async function loadSelection(){
    if(!allowed()){state={...state,order_ids:[],routes:[]};controls();return;}
    await flush();
    state=await api('/api/order-planning/selection');controls();
  }
  function isSelected(id){return state.order_ids.includes(id);}
  function checkbox(order){
    if(!allowed())return '';
    const checked=isSelected(order.id);
    return `<input class="order-select" type="checkbox" aria-label="Seleziona ordine ${esc(order.number)}" ${checked?'checked':''} ${busy || (order.status!=='pronto'&&!checked)?'disabled':''} onchange="GFOrderPlanning.select(${order.id},this.checked)">`;
  }
  function headerCheckbox(items=[]){
    if(!allowed())return '';
    const eligible=items.filter(order=>order.status==='pronto'||isSelected(order.id));
    const checked=eligible.length>0&&eligible.every(order=>isSelected(order.id));
    return `<input class="order-select order-select-all" type="checkbox" aria-label="Seleziona ordini pronti di questa pagina" ${checked?'checked':''} ${busy||!eligible.length?'disabled':''} onchange="GFOrderPlanning.selectPage(this.checked)">`;
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
  function config(){return {...(globalThis.GFDriverSchedules?.routePayload()||{}),...(globalThis.GFFleetPlanning?.config()||{}),group_orders:!!el('orderGroupOrders')?.checked,nome:val('routeName'),data_giro:val('routeDate'),orario_partenza:val('routeStart'),deposit_id:Number(val('routeDeposit'))||null,vehicle_id:Number(val('routeVehicle'))||null,driver_id:Number(val('routeDriver'))||null,rientro_deposito:boolVal('returnDepot'),energy_price_mode:document.querySelector('input[name="energyPriceMode"]:checked')?.value||'manual',energy_price_primary:Number(val('fuelPrice'))||0,energy_price_electric:Number(val('electricityPrice'))||0};}
  function gate(){
    const banner=el('orderPlanningBanner');if(banner)banner.hidden=!enabled;
    if(!enabled)return;
    const button=el('openCustomerStepBtn');if(button){button.textContent=proceeding?'Caricamento fermate…':'Prosegui';button.disabled=proceeding;}
    if(el('customerPlanningStep'))el('customerPlanningStep').classList.add('hidden');
    if(el('routePlanningGateHint')&&routePlanningDetailsCompleteV68())el('routePlanningGateHint').textContent=loadedStops?'Fermate degli ordini caricate. Verifica i dati e premi Calcola percorso.':'Completa la configurazione e premi Prosegui per caricare gli ordini selezionati.';
  }
  async function cancelSelected(){
    if(busy||!allowed()||!state.order_ids.length)return;
    const ids=[...state.order_ids];
    const label=ids.length===1?'l’ordine selezionato':`${ids.length} ordini selezionati`;
    if(!confirm(`Eliminare ${label}? Verranno annullati e resteranno disponibili nello storico per garantire la tracciabilità.`))return;
    busy=true;controls();
    let cancelled=0,skipped=0;
    try{
      for(const id of ids){
        try{
          const order=await GFOrders.request('/api/orders/'+id);
          if(!['nuovo','da_verificare','pronto'].includes(order.status)||order.assignments?.length){skipped++;continue;}
          await GFOrders.request(`/api/orders/${id}/status`,{method:'POST',body:JSON.stringify({version:order.version,status:'annullato'})});
          cancelled++;
        }catch(error){skipped++;}
      }
      await flush();
      state=await api('/api/order-planning/selection',{method:'PUT',body:JSON.stringify({version:state.version,action:'clear',order_ids:[],filters:{}})});
      enabled=false;loadedStops=false;dirty=false;gate();
      await GFOrders.load();
      el('ordersMessage').textContent=skipped?`${cancelled} ordini annullati. ${skipped} non erano eliminabili perché già assegnati o non modificabili.`:`${cancelled} ordini annullati.`;
    }catch(e){el('ordersMessage').textContent=e.message||'Non è stato possibile eliminare gli ordini selezionati.';}
    finally{busy=false;controls();GFOrders.refreshSelection?.();}
  }
  async function go(){
    try{
      await flush();await loadSelection();
      if(!state.order_ids.length || state.routes.length)return;
      if(deliveries.length && !enabled && !confirm('Sostituire le fermate aperte nel pianificatore con questa selezione? I giri già salvati restano disponibili nello storico.'))return;
      const saved=state.configuration;
      if(el('orderGroupOrders'))el('orderGroupOrders').checked=!!saved.group_orders;
      clearRouteWorkspace();enabled=true;loadedStops=false;dirty=false;
      showTab('giro');
      if(saved.data_giro){
        for(const [id,key] of [['routeName','nome'],['routeDate','data_giro'],['routeStart','orario_partenza'],['routeDeposit','deposit_id'],['returnDepot','rientro_deposito'],['fuelPrice','energy_price_primary'],['electricityPrice','energy_price_electric']])set(id,saved[key]??'');
        await refreshResourceAvailability();set('routeVehicle',saved.vehicle_id||'');set('routeDriver',saved.driver_id||'');
        const mode=document.querySelector(`input[name="energyPriceMode"][value="${saved.energy_price_mode||'manual'}"]`);if(mode)mode.checked=true;
        await updateRouteEnergyPricingV895();
      }
      globalThis.GFFleetPlanning?.restore(saved);
      globalThis.GFDriverSchedules?.route(saved.driver_schedule??GFDriverSchedules.defaults(saved.driver_id));
      if(!saved.data_giro&&state.requested_dates?.length===1)set('routeDate',state.requested_dates[0]);
      feedback('');updateRoutePlanningGateV68();gate();message(`${state.order_ids.length} ordini selezionati.${state.requested_dates?.length?' Date richieste: '+state.requested_dates.join(', ')+'.':''} Completa la configurazione del giro.`);
    }catch(e){alert(e.message);}
  }
  async function proceed(regenerate=false){
    if(proceeding)return;
    const missing=routePlanningMissingFieldsV68();
    if(missing.length){updateRoutePlanningGateV68();feedback('Per proseguire completa: '+missing.join(', ')+'.');return;}
    proceeding=true;gate();feedback('Sto preparando le fermate degli ordini…','loading');
    try{
      await flush();
      state=await api('/api/order-planning/preview',{method:'POST',body:JSON.stringify({version:state.version,configuration:config(),stops:regenerate?null:(loadedStops?deliveries:state.stops)})});
      deliveries=state.stops;loadedStops=true;dirty=false;customerPlanningStepOpenedV68=true;
      updateRoutePlanningGateV68();renderDeliveries();gate();feedback('');
      message(state.warnings?.length?state.warnings.join('\n'):'Fermate caricate. Controlla le consegne e calcola il percorso.');
      el('deliveryWorkbenchStep').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){feedback(e.message||'Non è stato possibile caricare le fermate. Riprova.');}
    finally{proceeding=false;gate();}
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
  function leave(){feedback('');editingRouteId=null;enabled=false;loadedStops=false;dirty=false;clearTimeout(timer);gate();}
  function describe(row){
    if(!row.order_refs?.length)return '';
    const values=row.order_operational||{},parts=[];
    if(values.pallet_truck!==null && values.pallet_truck!==undefined)parts.push('Transpallet: '+(values.pallet_truck?'Sì':'No'));
    if(values.pallets!=null)parts.push('Pallet: '+values.pallets);
    if(values.volume_m3!=null)parts.push('Volume: '+values.volume_m3+' m³');
    if(values.requirements)parts.push(values.requirements);
    return `<details><summary>${row.order_refs.length} ${row.order_refs.length===1?'ordine':'ordini'} · ${esc(row.colli??0)} colli</summary><p>${esc((row.order_numbers||row.order_refs.map(r=>'#'+r.id)).join(', '))}</p></details>${parts.length?'<small>'+esc(parts.join(' · '))+'</small>':''}`;
  }
  document.addEventListener('change',e=>{if(ids.includes(e.target.id)||e.target.name==='energyPriceMode')changed();});
  window.addEventListener('beforeunload',e=>{if(enabled&&(dirty||saving)){e.preventDefault();e.returnValue='';}});
  window.GFOrderPlanning={loadSelection,checkbox,headerCheckbox,isSelected,controls,metadata,describe,active:()=>enabled,gate,go,proceed,changed,flush,beforeCalculate,leave,cancelSelected,
    regroup(){if(loadedStops && !confirm('Rigenerare le fermate dai dati degli ordini? Le modifiche alle sole fermate verranno sostituite.')){el('orderGroupOrders').checked=!el('orderGroupOrders').checked;return;}changed();proceed(true);},
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
