/* Giri in bozza: lasciando la pianificazione (selezione, configurazione o suddivisione) il giro va in bozza,
   dopo una conferma. Le bozze hanno una pagina propria, con una voce nella sidebar visibile solo quando ce ne sono. */
window.GFPlanningDrafts=(()=>{
  'use strict';
  const PLANNING=['giro','route-preview'];
  const STAGES={selezione:'Selezione',configurazione:'Configurazione del giro',suddivisione:'Controlla la suddivisione',route:'Anteprima del percorso'};
  const el=id=>document.getElementById(id);
  let data={drafts:[],routes:[]},leaving=false,busy=false,staleChecked=false;
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
  // La fase in cui si lascia il giro: dalla suddivisione si conserva anche la sua anteprima.
  function stage(){
    const fleet=openTab()==='route-preview'?globalThis.GFFleetPlanning?.current():null;
    return fleet?{stage:'suddivisione',fleet_plan_id:fleet}:{stage:'configurazione'};
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
      await api('/api/planning-drafts',{method:'POST',body:JSON.stringify({source:'orders',selection_version:GFOrderPlanning.selection().version,...stage()})});
      await GFOrderPlanning.loadSelection();
    }else if(kind==='customers'){
      await api('/api/planning-drafts',{method:'POST',body:JSON.stringify({source:'customers',configuration:GFOrderPlanning.config(),stops:deliveries.map(cleanDeliveryForPayload),...stage()})});
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

  // Ordini rimasti selezionati da un giro già portato in pianificazione (pagina chiusa o versione precedente):
  // vanno in bozza, così aprendo Ordini non restano spuntati.
  async function parkStaleSelection(){
    if(staleChecked||!window.GFOrderPlanning||GFOrderPlanning.active()||openTab())return;
    if(window.GFCompanyAccess&&!GFCompanyAccess.can('orders.plan'))return;
    staleChecked=true;
    try{
      await GFOrderPlanning.loadSelection();
      const current=GFOrderPlanning.selection();
      if(!current.order_ids?.length)return;
      if(current.routes?.length){await clearOrderSelection();return;} // ordini già in un giro calcolato: la bozza è quel giro
      if(current.stops==null&&!Object.keys(current.configuration||{}).length)return; // selezione mai portata in pianificazione
      await api('/api/planning-drafts',{method:'POST',body:JSON.stringify({source:'orders',selection_version:current.version,stage:'configurazione'})});
      await GFOrderPlanning.loadSelection();
      window.GFOrders?.refreshSelection?.();
      toast('Il giro lasciato in pianificazione è stato spostato in «Giri in bozza».');
    }catch(error){console.warn('Selezione precedente non spostata in bozza',error);}
  }
  async function load(){
    if(!allowed()){data={drafts:[],routes:[]};render();return;}
    await parkStaleSelection();
    try{const result=await api('/api/planning-drafts');data={drafts:result?.drafts||[],routes:result?.routes||[]};}catch(error){data={drafts:[],routes:[]};}
    render();
  }
  const day=iso=>iso?gfDateIt(iso):'—';
  const saved=value=>{
    if(!value)return '—';
    const stamp=String(value),date=new Date(/Z$|[+-]\d\d:\d\d$/.test(stamp)?stamp:stamp+'Z');
    return Number.isNaN(date.getTime())?'—':date.toLocaleString('it-IT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  };
  function rows(){
    const drafts=data.drafts.map(d=>({key:'d'+d.id,when:d.updated_at,html:`<tr>
      <td data-label="Giro"><button type="button" class="gf-button" data-variant="link" onclick="GFPlanningDrafts.resume(${Number(d.id)})">${esc(d.name)}</button></td>
      <td data-label="Fase"><span class="gf-badge" data-status="${d.stage==='suddivisione'?'info':'neutral'}">${esc(STAGES[d.stage]||STAGES.configurazione)}</span></td>
      <td data-label="Origine">${d.source==='orders'?'Ordini':'Clienti'}</td>
      <td data-label="Data giro">${esc(day(d.data_giro))}</td>
      <td data-label="Mezzi">${d.planning_mode==='fleet'?esc(gfCount(d.vehicles,'mezzo','mezzi')):'1 mezzo'}</td>
      <td data-label="Consegne">${esc(d.source==='orders'?gfCount(d.orders,'ordine','ordini'):gfCount(d.stops,'cliente','clienti'))}</td>
      <td data-label="Salvato">${esc(saved(d.updated_at))}</td>
      <td data-label="Azioni"><span class="gf-cluster"><button type="button" class="gf-button" data-variant="primary" data-size="sm" onclick="GFPlanningDrafts.resume(${Number(d.id)})">Riprendi</button><button type="button" class="gf-button" data-variant="ghost" data-size="sm" onclick="GFPlanningDrafts.remove(${Number(d.id)})">Elimina</button></span></td></tr>`}));
    const routes=data.routes.map(r=>({key:'r'+r.id,when:r.created_at,html:`<tr>
      <td data-label="Giro"><button type="button" class="gf-button" data-variant="link" onclick="GFPlanningDrafts.openRoute(${Number(r.id)})">${esc(r.name)}</button></td>
      <td data-label="Fase"><span class="gf-badge" data-status="success">${STAGES.route}</span></td>
      <td data-label="Origine">—</td>
      <td data-label="Data giro">${esc(day(r.data_giro))}${r.orario_partenza?' · '+esc(r.orario_partenza):''}</td>
      <td data-label="Mezzi">1 mezzo</td>
      <td data-label="Consegne">—</td>
      <td data-label="Salvato">${esc(saved(r.created_at))}</td>
      <td data-label="Azioni"><span class="gf-cluster"><button type="button" class="gf-button" data-variant="primary" data-size="sm" onclick="GFPlanningDrafts.openRoute(${Number(r.id)})">Apri</button><button type="button" class="gf-button" data-variant="ghost" data-size="sm" onclick="GFPlanningDrafts.cancelRoute(${Number(r.id)})">Elimina</button></span></td></tr>`}));
    return drafts.concat(routes).sort((a,b)=>String(b.when||'').localeCompare(String(a.when||''))).map(row=>row.html).join('');
  }
  // Voce nella sidebar (solo con bozze) e tabella della pagina.
  function render(){
    const total=data.drafts.length+data.routes.length;
    const item=el('sidebarDraftsItem'),badge=el('sidebarDraftsBadge'),count=el('planningDraftsCount'),table=el('planningDraftsTable');
    if(item){const hide=!total;if(item.classList.contains('gf-hidden')!==hide){item.classList.toggle('gf-hidden',hide);window.GFSidebarFit?.();}}
    if(badge)badge.textContent=String(total);
    if(count){count.hidden=!total;count.textContent=gfCount(total,'bozza','bozze');}
    if(!table)return;
    table.innerHTML=total
      ?`<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards"><thead><tr><th scope="col">Giro</th><th scope="col">Fase</th><th scope="col">Origine</th><th scope="col">Data giro</th><th scope="col">Mezzi</th><th scope="col">Consegne</th><th scope="col">Salvato</th><th scope="col">Azioni</th></tr></thead><tbody>${rows()}</tbody></table></div>`
      :'<div class="gf-empty"><p>Nessun giro in bozza</p><small>Quando lasci una pianificazione prima di programmarla, la ritrovi qui.</small></div>';
  }

  // Prima di riprendere, l'eventuale pianificazione aperta va in bozza.
  async function parkOpen(){
    const kind=openTab()?pending():null;
    if(!kind)return true;
    if(!confirm('Hai una pianificazione aperta: verrà messa in bozza prima di riprendere questa. Continuare?'))return false;
    await park(kind);return true;
  }
  // Riprende dalla fase in cui il giro era stato lasciato (configurazione o suddivisione).
  async function resume(id){
    const draft=data.drafts.find(d=>d.id===id);if(!draft||busy)return;
    busy=true;
    try{
      if(!await parkOpen())return;
      let result;
      if(draft.source==='orders'){
        await GFOrderPlanning.loadSelection();
        let current=GFOrderPlanning.selection();
        if(current.order_ids.length){
          if(!confirm(`Hai già ${gfCount(current.order_ids.length,'ordine selezionato','ordini selezionati')}: li metto in bozza per riprendere questa?`))return;
          await api('/api/planning-drafts',{method:'POST',body:JSON.stringify({source:'orders',selection_version:current.version,stage:'selezione'})});
          await GFOrderPlanning.loadSelection();current=GFOrderPlanning.selection();
        }
        result=await api(`/api/planning-drafts/${id}/resume`,{method:'POST',body:JSON.stringify({selection_version:current.version})});
        GFOrderPlanning.acceptSelection(result.selection);
        await GFOrderPlanning.go(true);
        if(result.dropped)toast(`${gfCount(result.dropped,'ordine non era più da pianificare ed è stato escluso','ordini non erano più da pianificare e sono stati esclusi')}.`);
      }else{
        result=await api(`/api/planning-drafts/${id}/resume`,{method:'POST',body:'{}'});
        showTab('giro');
        clearRouteWorkspace();
        await restore(result.configuration||{});
        deliveries=result.stops||[];customerDirectoryPlanning=true;
        renderDeliveries();updateRoutePlanningGateV68();
      }
      // Lasciato in "Controlla la suddivisione": si riapre lì (o si ricalcola se l'anteprima è scaduta).
      if(result.stage==='suddivisione'&&result.fleet_plan_id&&globalThis.GFFleetPlanning?.active())await GFFleetPlanning.open(result.fleet_plan_id);
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
  // Giro già calcolato: si apre la sua anteprima, da cui si programma o si torna a modificarlo.
  async function openRoute(id){
    if(busy)return;busy=true;
    try{if(!await parkOpen())return;globalThis.GFOrderPlanning?.leave();await openProgrammedRouteForEdit(id);}
    catch(error){alert(error.message);}finally{busy=false;}
  }
  async function cancelRoute(id){
    const route=data.routes.find(r=>r.id===id);if(!route||busy)return;
    if(!confirm(`Eliminare la bozza «${route.name}»? Il giro viene annullato e gli ordini collegati tornano da pianificare.`))return;
    try{await api(`/api/routes/${Number(id)}/cancel`,{method:'POST',body:'{}'});}catch(error){alert(error.message);}
    load();
  }
  return {guard,load,resume,remove,openRoute,cancelRoute,pending};
})();
