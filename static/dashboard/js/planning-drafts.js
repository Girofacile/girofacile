/* Giri in bozza: lasciando la pianificazione (pre-pianificazione o suddivisione) il giro va in bozza,
   dopo una conferma. Le bozze compaiono in Dashboard e in Ordini solo quando ce ne sono. */
window.GFPlanningDrafts=(()=>{
  'use strict';
  const PLANNING=['giro','route-preview'];
  const el=id=>document.getElementById(id);
  let data={drafts:[],routes:[]},leaving=false,busy=false;
  const allowed=()=>!window.GFCompanyAccess||GFCompanyAccess.can('orders.plan')||GFCompanyAccess.can('routes.plan');
  const openTab=()=>PLANNING.find(name=>el('tab-'+name)&&!el('tab-'+name).classList.contains('hidden'));

  // Cosa andrebbe in bozza lasciando ora la pianificazione.
  function pending(){
    try{
      if(!deliveries.length)return null;
      if(lastRouteResult?.id)return lastRouteResult.status==='bozza'?'route':null; // giro calcolato: è già una bozza salvata
      if(globalThis.GFOrderPlanning?.active())return 'orders';
      if(customerDirectoryPlanning)return 'customers';
    }catch(error){} // core.js non ancora pronto (prima navigazione): nulla da mettere in bozza
    return null;
  }
  async function clearOrderSelection(){
    const current=GFOrderPlanning.selection();
    if(!current.order_ids?.length)return;
    GFOrderPlanning.acceptSelection(await api('/api/order-planning/selection',{method:'PUT',body:JSON.stringify({version:current.version,action:'clear',order_ids:[],filters:{}})}));
  }
  // Mette in bozza la pianificazione aperta e libera il pianificatore.
  async function park(kind){
    if(kind==='orders'){
      await GFOrderPlanning.flush();
      await api('/api/planning-drafts',{method:'POST',body:JSON.stringify({source:'orders',selection_version:GFOrderPlanning.selection().version})});
      await GFOrderPlanning.loadSelection();
    }else if(kind==='customers'){
      await api('/api/planning-drafts',{method:'POST',body:JSON.stringify({source:'customers',configuration:GFOrderPlanning.config(),stops:deliveries.map(cleanDeliveryForPayload)})});
    }else if(kind==='route'){
      await clearOrderSelection();
    }
    clearRouteWorkspace();
    await load();
  }
  // Chiamata da showTab: true blocca la navigazione (conferma o salvataggio in corso).
  function guard(name){
    if(leaving||busy||PLANNING.includes(name)||!openTab())return false;
    const kind=pending();if(!kind)return false;
    const text=kind==='route'
      ?'Attenzione: stai lasciando questo giro in bozza. Lo ritrovi in «Giri in bozza» per riprenderlo e programmarlo. Continuare?'
      :'Attenzione: stai per mandare questo giro in bozza. Lo ritrovi in «Giri in bozza» per riprenderlo più tardi. Sei sicuro?';
    if(!confirm(text))return true;
    busy=true;
    park(kind).then(()=>{leaving=true;try{showTab(name);}finally{leaving=false;}})
      .catch(error=>alert('Non è stato possibile mettere il giro in bozza: '+(error.message||error)))
      .finally(()=>{busy=false;});
    return true;
  }

  async function load(){
    if(!allowed()){data={drafts:[],routes:[]};render();return;}
    try{const result=await api('/api/planning-drafts');data={drafts:result?.drafts||[],routes:result?.routes||[]};}catch(error){data={drafts:[],routes:[]};}
    render();
  }
  const day=iso=>iso?gfDateIt(iso):'data da scegliere';
  function item(d){
    const mode=d.planning_mode==='fleet'?`Più mezzi (${d.vehicles})`:'Un mezzo';
    const from=d.source==='orders'?gfCount(d.orders,'ordine','ordini'):gfCount(d.stops,'cliente','clienti');
    return `<li class="gf-list-item"><div class="gf-list-item__main"><strong>${esc(d.name)}</strong><small>${esc(day(d.data_giro))} · ${esc(mode)} · ${esc(from)}</small></div>
      <span class="gf-cluster"><button type="button" class="gf-button" data-variant="primary" data-size="sm" onclick="GFPlanningDrafts.resume(${Number(d.id)})">Riprendi</button>
      <button type="button" class="gf-button" data-variant="ghost" data-size="sm" onclick="GFPlanningDrafts.remove(${Number(d.id)})">Elimina</button></span></li>`;
  }
  function route(r){
    return `<li class="gf-list-item"><div class="gf-list-item__main"><strong>${esc(r.name)}</strong><small>${esc(day(r.data_giro))}${r.orario_partenza?' · '+esc(r.orario_partenza):''} · Percorso calcolato, da programmare</small></div>
      <button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFPlanningDrafts.openRoute(${Number(r.id)})">Apri</button></li>`;
  }
  // Una sezione in Dashboard e una in Ordini: nascoste quando non ci sono bozze.
  function render(){
    const total=data.drafts.length+data.routes.length;
    document.querySelectorAll('[data-planning-drafts]').forEach(box=>{
      box.hidden=!total;
      if(!total){box.innerHTML='';return;}
      const id='planningDraftsTitle-'+box.dataset.planningDrafts;
      box.setAttribute('aria-labelledby',id);
      box.innerHTML=`<header class="gf-panel__header"><div><h2 class="gf-panel__title" id="${id}">Giri in bozza</h2><p class="gf-muted">Pianificazioni lasciate prima della programmazione: riprendile da dove eri rimasto.</p></div><span class="gf-badge" data-status="warning" data-dot>${total}</span></header>
        <ul class="gf-list">${data.drafts.map(item).join('')}${data.routes.map(route).join('')}</ul>`;
    });
  }

  // Prima di riprendere, l'eventuale pianificazione aperta va in bozza.
  async function parkOpen(){
    const kind=openTab()?pending():null;
    if(!kind)return true;
    if(!confirm('Hai una pianificazione aperta: verrà messa in bozza prima di riprendere questa. Continuare?'))return false;
    await park(kind);return true;
  }
  async function resume(id){
    const draft=data.drafts.find(d=>d.id===id);if(!draft||busy)return;
    busy=true;
    try{
      if(!await parkOpen())return;
      if(draft.source==='orders'){
        await GFOrderPlanning.loadSelection();
        let current=GFOrderPlanning.selection();
        if(current.order_ids.length){
          if(!confirm(`Hai già ${gfCount(current.order_ids.length,'ordine selezionato','ordini selezionati')}: li metto in bozza per riprendere questa?`))return;
          await api('/api/planning-drafts',{method:'POST',body:JSON.stringify({source:'orders',selection_version:current.version})});
          await GFOrderPlanning.loadSelection();current=GFOrderPlanning.selection();
        }
        const result=await api(`/api/planning-drafts/${id}/resume`,{method:'POST',body:JSON.stringify({selection_version:current.version})});
        GFOrderPlanning.acceptSelection(result.selection);
        await GFOrderPlanning.go(true);
        if(result.dropped)toast(`${gfCount(result.dropped,'ordine non era più da pianificare ed è stato escluso','ordini non erano più da pianificare e sono stati esclusi')}.`);
      }else{
        const result=await api(`/api/planning-drafts/${id}/resume`,{method:'POST',body:'{}'});
        showTab('giro');
        clearRouteWorkspace();
        await restore(result.configuration||{});
        deliveries=result.stops||[];customerDirectoryPlanning=true;
        renderDeliveries();updateRoutePlanningGateV68();
      }
    }catch(error){alert(error.message||'Non è stato possibile riprendere la bozza.');}
    finally{busy=false;load();}
  }
  // Configurazione salvata di una bozza da clienti: stessi campi della pianificazione dagli ordini.
  async function restore(saved){
    for(const [id,key] of [['routeName','nome'],['routeDate','data_giro'],['routeStart','orario_partenza'],['routeDeposit','deposit_id'],['returnDepot','rientro_deposito'],['fuelPrice','energy_price_primary'],['electricityPrice','energy_price_electric']])
      if(saved[key]!==undefined&&saved[key]!==null&&saved[key]!=='')set(id,saved[key]);
    await refreshResourceAvailability();
    const free=(list,id)=>id&&(list||[]).find(r=>String(r.id)===String(id))?.available!==false?id:'';
    set('routeVehicle',free(resourcesAvailabilityCache.vehicles,saved.vehicle_id));set('routeDriver',free(resourcesAvailabilityCache.drivers,saved.driver_id));
    const mode=document.querySelector(`input[name="energyPriceMode"][value="${saved.energy_price_mode||'manual'}"]`);if(mode)mode.checked=true;
    await updateRouteEnergyPricingV895();
    globalThis.GFFleetPlanning?.restore(saved);
    globalThis.GFDriverSchedules?.route(saved.driver_schedule??GFDriverSchedules.defaults(saved.driver_id));
  }
  async function remove(id){
    const draft=data.drafts.find(d=>d.id===id);if(!draft||busy)return;
    if(!confirm(`Eliminare la bozza «${draft.name}»? ${draft.source==='orders'?'Gli ordini restano da pianificare.':'I clienti restano in anagrafica.'}`))return;
    try{await api(`/api/planning-drafts/${id}`,{method:'DELETE'});}catch(error){alert(error.message);}
    load();
  }
  async function openRoute(id){
    if(busy)return;busy=true;
    try{if(!await parkOpen())return;GFOrderPlanning.openRoute(id);}
    catch(error){alert(error.message);}finally{busy=false;}
  }
  return {guard,load,resume,remove,openRoute,pending};
})();
