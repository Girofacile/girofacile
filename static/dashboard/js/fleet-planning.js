/* Multi-vehicle planning, integrated into the existing three-step workspace. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id);
  let resources=[],plan=null,busy=false,changedAssignments=false;
  const active=()=>el('planningMode')?.value==='fleet';
  const blank=()=>({vehicle_id:0,driver_id:0,max_minutes:480,energy_price_primary:1.75,energy_price_electric:0.30});
  const can=permission=>!window.GFCompanyAccess||GFCompanyAccess.can(permission);
  const config=()=>({planning_mode:active()?'fleet':'single',fleet_strategy:el('fleetStrategy')?.value||'efficient',fleet_resources:active()?resources.filter(r=>r.vehicle_id&&r.driver_id):[]});
  function options(type,id){
    const rows=resourcesAvailabilityCache?.[type]||[];
    return '<option value="">Seleziona '+(type==='vehicles'?'mezzo':'autista')+'</option>'+rows.map(r=>`<option value="${r.id}" ${r.id===Number(id)?'selected':''} ${r.available===false?'disabled':''}>${esc(type==='vehicles'?r.nome:(r.full_name||[r.nome,r.cognome].filter(Boolean).join(' ')))}${r.available===false?' · Non disponibile':''}</option>`).join('');
  }
  function refresh(){
    if(!el('fleetResources'))return;
    el('fleetResources').innerHTML=resources.map((r,i)=>`<section class="fleet-resource"><header><strong>Mezzo e autista ${i+1}</strong>${resources.length>2?`<button type="button" class="btn-secondary" data-remove="${i}">Rimuovi</button>`:''}</header><div class="fleet-fields"><div><label for="fleetVehicle${i}">Mezzo</label><select id="fleetVehicle${i}" data-index="${i}" data-field="vehicle_id">${options('vehicles',r.vehicle_id)}</select></div><div><label for="fleetDriver${i}">Autista</label><select id="fleetDriver${i}" data-index="${i}" data-field="driver_id">${options('drivers',r.driver_id)}</select></div></div><details><summary>Durata e costi · massimo ${r.max_minutes} minuti</summary><div class="fleet-fields"><div><label for="fleetDuration${i}">Durata massima del giro (minuti)</label><input id="fleetDuration${i}" type="number" min="1" max="1440" data-index="${i}" data-field="max_minutes" value="${r.max_minutes}"></div><div><label for="fleetFuel${i}">Carburante (€/litro o €/kg)</label><input id="fleetFuel${i}" type="number" min="0.01" step="0.01" data-index="${i}" data-field="energy_price_primary" value="${r.energy_price_primary}"></div><div><label for="fleetElectric${i}">Energia elettrica (€/kWh)</label><input id="fleetElectric${i}" type="number" min="0.01" step="0.01" data-index="${i}" data-field="energy_price_electric" value="${r.energy_price_electric}"></div></div></details></section>`).join('');
    el('fleetAdd').disabled=resources.length>=10;
  }
  function modeChanged(notify=true){
    if(active()&&!resources.length)resources=[blank(),blank()];
    el('fleetSetup').hidden=!active();el('singleVehicleField').hidden=active();el('singleDriverField').hidden=active();
    refresh();updateRoutePlanningGateV68();updateDashboardStats();
    if(notify)globalThis.GFOrderPlanning?.changed();
  }
  function missing(){
    const result=[];
    if(resources.length<2||resources.some(r=>!r.vehicle_id)||new Set(resources.map(r=>r.vehicle_id)).size!==resources.length)result.push('mezzo');
    if(resources.some(r=>!r.driver_id)||new Set(resources.map(r=>r.driver_id)).size!==resources.length)result.push('autista');
    if(resources.some(r=>!(r.energy_price_primary>0)))result.push('prezzo carburante');
    if(resources.some(r=>!(r.energy_price_electric>0)))result.push('prezzo energia');
    const start=val('routeStart').split(':').map(Number);
    if(resources.some(r=>!Number.isInteger(r.max_minutes)||r.max_minutes<1||r.max_minutes>1440||start[0]*60+start[1]+r.max_minutes>1440))result.push('durata massima dei giri (entro la giornata)');
    return result;
  }
  function restore(saved={}){el('planningMode').value=saved.planning_mode||'single';el('fleetStrategy').value=saved.fleet_strategy||'efficient';resources=(saved.fleet_resources||[]).map(r=>({...blank(),...r}));modeChanged(false);}
  function reset(){plan=null;changedAssignments=false;restore();}
  function notice(text){const box=el('fleetMessage');if(box){box.textContent=text;box.scrollIntoView({block:'nearest'});}}
  async function calculate(){
    if(busy)return;
    const gaps=routePlanningMissingFieldsV68();if(gaps.length){alert('Completa: '+gaps.join(', '));return;}
    if(!deliveries.length){alert('Aggiungi almeno una consegna.');return;}
    if(deliveries.length>100){alert('Puoi suddividere fino a 100 consegne per volta. Riduci la selezione.');return;}
    busy=true;
    try{
      showTab('route-preview');el('routePreviewResult').innerHTML='<section class="panel"><p role="status">Distribuzione delle consegne in corso…</p></section>';
      const data={nome:val('routeName')||'Piano consegne',data_giro:val('routeDate'),orario_partenza:val('routeStart'),deposit_id:Number(val('routeDeposit')),rientro_deposito:boolVal('returnDepot'),strategy:el('fleetStrategy').value,resources,consegne:deliveries};
      plan=await api('/api/fleet-planning/preview',{method:'POST',body:JSON.stringify(data)});changedAssignments=false;render();
    }catch(e){el('routePreviewResult').innerHTML=`<section class="panel"><h2>Distribuzione non completata</h2><p role="alert">${esc(e.message)}</p><button class="btn-secondary" onclick="showTab('giro')">Torna alla pianificazione</button></section>`;}
    finally{busy=false;}
  }
  function assignments(){const a=Array(plan.configuration.consegne.length).fill(null);plan.routes.forEach(r=>r.stop_indexes.forEach(i=>a[i]=r.resource));return a;}
  function stop(index,resource){
    const row=plan.configuration.consegne[index];
    const route=plan.routes.find(r=>r.stop_indexes.includes(index));
    const timing=route?.result.ordered[route.stop_indexes.indexOf(index)];
    return `<li><div><strong>${esc(row.cliente_nome)}</strong><small>${esc(row.indirizzo)}</small>${timing?`<small>Arrivo ${esc(timing.arrivo_stimato||'—')} · ${Number(row.peso_kg||0)} kg · ${Number(row.colli||0)} colli</small>`:''}</div>${plan.status==='preview'?`<select data-stop="${index}" aria-label="Assegna ${esc(row.cliente_nome)}"><option value="" ${resource===null?'selected':''}>Non assegnata</option>${plan.configuration.resources.map((r,i)=>`<option value="${i}" ${resource===i?'selected':''}>Mezzo e autista ${i+1}</option>`).join('')}</select>`:''}</li>`;
  }
  function render(){
    const preview=plan.status==='preview',saved=plan.status==='saved';
    const total=plan.routes.reduce((a,r)=>a+r.stop_indexes.length,0);
    el('routePreviewResult').innerHTML=`<section class="panel fleet-result"><h2>${preview?'Controlla la suddivisione':saved?'Giri salvati in bozza':'Giri programmati'}</h2><p>${total} consegne su ${plan.routes.length} mezzi · ${plan.unassigned.length} non assegnate</p><p>${preview?'Puoi spostare le consegne tra i mezzi e ricalcolare prima di salvare.':saved?'Le consegne sono riservate. Programma i giri per renderli operativi.':'I giri sono disponibili nello storico e nel portale degli autisti.'}</p><div id="fleetMessage" role="status" tabindex="-1"></div><div class="fleet-actions">${preview?'<button class="btn-secondary" data-action="revise">Ricalcola assegnazioni</button><button class="btn-primary" data-action="confirm">Salva giri in bozza</button>':saved&&can('routes.program')?'<button class="btn-primary" data-action="program">Programma tutti i giri</button>':''}<button class="btn-secondary" onclick="showTab('giro')">Torna alla pianificazione</button></div>${preview&&plan.unassigned.length?'<label><input id="fleetAccept" type="checkbox"> Salva i giri lasciando queste consegne non assegnate</label>':''}${plan.warnings.map(w=>`<p><small>${esc(w)}</small></p>`).join('')}</section>`+
    plan.routes.map((r,i)=>`<section class="panel fleet-result"><h2>Mezzo e autista ${r.resource+1} · ${esc(r.vehicle_name)}</h2><p>${esc(r.driver_name)}</p><div class="fleet-summary"><span>${r.stop_indexes.length} consegne</span><span>${Math.round(r.result.total_min)} min · ${plan.configuration.rientro_deposito?'rientro':'fine'} ${esc(r.result.return_time||'—')}</span><span>${Number(r.result.total_km).toFixed(1)} km</span><span>${Number(r.weight_kg).toFixed(1)} kg · ${r.packages} colli</span><span>Carburante/energia € ${Number(r.fuel_cost).toFixed(2)}</span></div>${plan.route_ids?.[i]?`<button class="btn-secondary" data-open="${plan.route_ids[i]}">Apri giro #${plan.route_ids[i]}</button>`:''}<ul class="fleet-stops">${r.stop_indexes.map(index=>stop(index,r.resource)).join('')}</ul></section>`).join('')+
    (plan.unassigned.length?`<section class="panel fleet-result"><h2>Consegne non assegnate</h2><p>Rimangono da pianificare. Puoi cambiare mezzi, disponibilità o assegnazione.</p><ul class="fleet-stops">${plan.unassigned.map(s=>stop(s.index,null)+`<li><small>${esc(s.reason)}</small></li>`).join('')}</ul></section>`:'');
  }
  async function action(name){
    if(busy||!plan)return;
    if(name==='confirm'&&changedAssignments){notice('Ricalcola le assegnazioni prima di salvare.');return;}
    const payload={version:plan.version};
    if(name==='revise'){payload.assignments=assignments();el('routePreviewResult').querySelectorAll('[data-stop]').forEach(s=>payload.assignments[Number(s.dataset.stop)]=s.value===''?null:Number(s.value));}
    if(name==='confirm')payload.accept_unassigned=!!el('fleetAccept')?.checked;
    busy=true;el('routePreviewResult').querySelectorAll('[data-action],[data-stop]').forEach(b=>b.disabled=true);notice('Operazione in corso…');
    try{
      plan=await api(`/api/fleet-planning/${plan.id}/${name}`,{method:'POST',body:JSON.stringify(payload)});changedAssignments=false;render();
      if(name!=='revise'){globalThis.GFOrderPlanning?.leave();await loadRoutes();await loadDashboardRoutes();}
    }catch(e){notice(e.message);}
    finally{busy=false;el('routePreviewResult').querySelectorAll('[data-action],[data-stop]').forEach(b=>b.disabled=false);}
  }
  document.addEventListener('change',e=>{
    if(e.target.id==='planningMode'){modeChanged();refreshResourceAvailability();}
    if(e.target.dataset.field&&el('fleetResources').contains(e.target)){resources[Number(e.target.dataset.index)][e.target.dataset.field]=Number(e.target.value);updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();}
    if(e.target.id==='fleetStrategy')globalThis.GFOrderPlanning?.changed();
    if(e.target.dataset.stop!==undefined&&el('routePreviewResult').contains(e.target)){changedAssignments=true;notice('Assegnazioni modificate: premi Ricalcola assegnazioni per verificare i nuovi giri.');}
  });
  document.addEventListener('click',e=>{
    const remove=e.target.closest('[data-remove]'),button=e.target.closest('[data-action]'),open=e.target.closest('[data-open]');
    if(e.target.id==='fleetAdd'&&resources.length<10){resources.push(blank());refresh();updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();}
    if(remove&&el('fleetResources').contains(remove)){resources.splice(Number(remove.dataset.remove),1);refresh();updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();}
    if(button&&el('routePreviewResult').contains(button))action(button.dataset.action);
    if(open&&el('routePreviewResult').contains(open))GFOrderPlanning.openRoute(Number(open.dataset.open));
  });
  window.GFFleetPlanning={active,config,restore,reset,refresh,missing,calculate};
})();
