/* Multi-vehicle planning, integrated into the existing three-step workspace. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id);
  let resources=[],plan=null,busy=false,changedAssignments=false,draftAssignments=null,manualAdjusted=false,acknowledgedWarning=false;
  const active=()=>window.GFPlanAccess?.has('has_fleet_planning')===true && el('planningMode')?.value==='fleet';
  const blank=()=>({vehicle_id:0,driver_id:0,energy_price_primary:1.75,energy_price_electric:0.30});
  const can=permission=>!window.GFCompanyAccess||GFCompanyAccess.can(permission);
  const config=()=>({planning_mode:active()?'fleet':'single',fleet_strategy:el('fleetStrategy')?.value||'efficient',fleet_resources:active()?resources.filter(r=>r.vehicle_id&&r.driver_id):[]});
  // Un mezzo o un autista già scelto in un'altra card non si può scegliere di nuovo.
  function options(type,id,index){
    const rows=resourcesAvailabilityCache?.[type]||[];
    const key=type==='vehicles'?'vehicle_id':'driver_id';
    const takenBy=rid=>resources.findIndex((r,i)=>i!==index&&Number(r[key])===rid);
    return '<option value="">Seleziona '+(type==='vehicles'?'mezzo':'autista')+'</option>'+rows.map(r=>{
      const taken=r.id===Number(id)?-1:takenBy(r.id);
      const note=r.available===false?' · Non disponibile':taken>=0?` · Già scelto nel mezzo ${taken+1}`:'';
      return `<option value="${r.id}" ${r.id===Number(id)?'selected':''} ${r.available===false||taken>=0?'disabled':''}>${esc(type==='vehicles'?r.nome:(r.full_name||[r.nome,r.cognome].filter(Boolean).join(' ')))}${note}</option>`;
    }).join('');
  }
  // Aggiorna gli elenchi delle card senza ridisegnarle (turni e costi aperti restano aperti).
  function syncChoices(){
    el('fleetResources')?.querySelectorAll('select[data-field="vehicle_id"],select[data-field="driver_id"]').forEach(select=>{
      const i=Number(select.dataset.index),field=select.dataset.field;
      select.innerHTML=options(field==='vehicle_id'?'vehicles':'drivers',resources[i][field],i);
    });
  }
  const vehicleName=id=>(resourcesAvailabilityCache?.vehicles||[]).find(v=>v.id===Number(id))?.nome||'Nuovo mezzo';
  function refresh(){
    if(!el('fleetResources'))return;
    const field=(id,label,control)=>`<label class="gf-field" for="${id}"><span class="gf-field__label">${label}</span>${control}</label>`;
    // Una card per mezzo (variante B): turno, pause, durata e costi restano chiusi finché servono.
    const remove=i=>`<button type="button" class="gf-icon-button" data-remove="${i}" aria-label="Rimuovi mezzo e autista ${i+1}" title="Rimuovi"><svg class="gf-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>`;
    el('fleetResources').innerHTML=resources.map((r,i)=>`<article class="gf-card gf-stack" data-gap="sm" aria-label="Mezzo e autista ${i+1}"><header class="gf-cluster" data-justify="between"><span class="gf-cluster"><span class="gf-stop__number">${i+1}</span><strong data-fleet-name>${esc(vehicleName(r.vehicle_id))}</strong></span>${resources.length>2?remove(i):''}</header>${field('fleetVehicle'+i,'Mezzo',`<select class="gf-select" id="fleetVehicle${i}" data-index="${i}" data-field="vehicle_id">${options('vehicles',r.vehicle_id,i)}</select>`)}${field('fleetDriver'+i,'Autista',`<select class="gf-select" id="fleetDriver${i}" data-index="${i}" data-field="driver_id">${options('drivers',r.driver_id,i)}</select>`)}<details data-schedule-editor><summary class="gf-button" data-variant="ghost" data-size="sm">Modifica turno e pause di oggi</summary><div id="fleetDriverSchedule${i}"></div></details><details><summary class="gf-button" data-variant="ghost" data-size="sm">Costi carburante ed energia</summary><div class="gf-form-grid">${field('fleetFuel'+i,'Carburante (€/litro o €/kg)',`<input class="gf-input" id="fleetFuel${i}" type="number" min="0.01" step="0.01" data-index="${i}" data-field="energy_price_primary" value="${r.energy_price_primary}">`)}${field('fleetElectric'+i,'Energia elettrica (€/kWh)',`<input class="gf-input" id="fleetElectric${i}" type="number" min="0.01" step="0.01" data-index="${i}" data-field="energy_price_electric" value="${r.energy_price_electric}">`)}</div></details></article>`).join('')
      +`<div class="gf-card gf-stack" data-variant="info" data-gap="sm"><strong>Un altro mezzo?</strong><span class="gf-muted">Aggiungi una card vuota e scegli tu mezzo e autista.</span><span><button type="button" class="gf-button" data-variant="secondary" id="fleetAdd">+ Aggiungi mezzo</button></span></div>`;
    el('fleetAdd').disabled=resources.length>=10;
    globalThis.GFDriverSchedules?.fleet(resources);
  }
  function modeChanged(notify=true){
    if(!window.GFPlanAccess?.has('has_fleet_planning'))el('planningMode').value='single';
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
    if(resources.some(r=>globalThis.GFDriverSchedules?.error(r.driver_schedule??GFDriverSchedules.defaults(r.driver_id))))result.push("turni e pause autisti");
    return result;
  }
  function restore(saved={}){el('planningMode').value=window.GFPlanAccess?.has('has_fleet_planning') ? (saved.planning_mode||'single') : 'single';el('fleetStrategy').value=saved.fleet_strategy||'efficient';resources=(saved.fleet_resources||[]).map(({max_minutes,...r})=>({...blank(),...r}));modeChanged(false);}
  function reset(){plan=null;changedAssignments=false;draftAssignments=null;manualAdjusted=false;acknowledgedWarning=false;window.GFFleetReview?.stopMap();restore();}
  function notice(text){const box=el('fleetMessage');if(box){box.textContent=text;box.scrollIntoView({block:'nearest'});}}
  async function calculate(){
    if(!window.GFPlanAccess?.require('has_fleet_planning','La suddivisione automatica su più mezzi'))return;
    if(busy)return;
    const gaps=routePlanningMissingFieldsV68();if(gaps.length){alert('Completa: '+gaps.join(', '));return;}
    if(!deliveries.length){alert('Aggiungi almeno una consegna.');return;}
    if(deliveries.length>100){alert('Puoi suddividere fino a 100 consegne per volta. Riduci la selezione.');return;}
    busy=true;
    try{
      showTab('route-preview');el('routePreviewResult').innerHTML='<section class="gf-panel"><div class="gf-loading" role="status">Distribuzione delle consegne in corso…</div></section>';
      const data={nome:val('routeName')||'Piano consegne',data_giro:val('routeDate'),orario_partenza:val('routeStart'),deposit_id:Number(val('routeDeposit')),rientro_deposito:boolVal('returnDepot'),strategy:el('fleetStrategy').value,resources,consegne:deliveries};
      plan=await api('/api/fleet-planning/preview',{method:'POST',body:JSON.stringify(data)});changedAssignments=false;draftAssignments=null;manualAdjusted=false;acknowledgedWarning=false;busy=false;render();
    }catch(e){el('routePreviewResult').innerHTML=`<section class="gf-panel"><div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">Distribuzione non completata</h2><p class="gf-alert" data-status="danger" role="alert">${esc(e.message)}</p><div><button type="button" class="gf-button" data-variant="secondary" onclick="showTab('giro')">Torna alla pianificazione</button></div></div></section>`;}
    finally{busy=false;}
  }
  function assignments(){const a=Array(plan.configuration.consegne.length).fill(null);plan.routes.forEach(r=>r.stop_indexes.forEach(i=>a[i]=r.resource));return a;}
  function stop(index,resource){
    const row=plan.configuration.consegne[index];
    const route=plan.routes.find(r=>r.stop_indexes.includes(index));
    const timing=route?.result.ordered[route.stop_indexes.indexOf(index)];
    return `<li><div><strong>${esc(row.cliente_nome)}</strong><small>${esc(row.indirizzo)}</small>${timing?`<small>Arrivo ${esc(timing.arrivo_stimato||'—')} · ${gfDecimal(row.peso_kg||0)} kg · ${gfCount(row.colli,'collo','colli')}</small>`:''}</div>${plan.status==='preview'?`<select data-stop="${index}" aria-label="Assegna ${esc(row.cliente_nome)}"><option value="" ${resource===null?'selected':''}>Non assegnata</option>${plan.configuration.resources.map((r,i)=>`<option value="${i}" ${resource===i?'selected':''}>Mezzo e autista ${i+1}</option>`).join('')}</select>`:''}</li>`;
  }

  function reviewAssignments(){return draftAssignments?draftAssignments.slice():assignments();}
  function moveStop(index,to){
    if(busy||!plan||plan.status!=='preview')return;
    const current=reviewAssignments(),before=assignments();
    if(index<0||index>=current.length||to===current[index])return;
    const apply=()=>{
      draftAssignments=current.slice();draftAssignments[index]=to;
      changedAssignments=draftAssignments.some((v,i)=>v!==before[i]);
      manualAdjusted=true;
      render();
      if(changedAssignments)notice('Suddivisione modificata: ricalcola per aggiornare l’ordine delle fermate, i tempi e i costi.');
    };
    if(!acknowledgedWarning){
      window.GFFleetReview.warning(()=>{acknowledgedWarning=true;apply();});
    }else apply();
  }
  function render(){
    if(!plan)return;
    window.GFFleetReview.render({
      plan,assignment:reviewAssignments(),dirty:changedAssignments,busy,manualAdjusted,
      permission:can('routes.program'),
      onMove:moveStop,
      onUndo:()=>{draftAssignments=null;changedAssignments=false;manualAdjusted=false;acknowledgedWarning=false;render();},
      onRecalc:()=>action('revise'),
      onPlan:accept=>action('plan',accept),
      onBack:()=>showTab('giro')
    });
  }
  async function action(name,acceptUnassigned=false){
    if(busy||!plan)return;
    if(!window.GFPlanAccess?.require('has_fleet_planning','La suddivisione automatica su più mezzi'))return;
    if(name==='plan'&&plan.status==='preview'&&changedAssignments){
      notice('Ricalcola le assegnazioni prima di pianificare i giri.');return;
    }
    if(name==='plan'&&!can('routes.program')){
      notice('Il tuo account non ha il permesso di programmare i giri.');return;
    }
    if(name==='plan'&&plan.status==='preview'&&plan.unassigned.length&&!acceptUnassigned){
      notice('Conferma esplicitamente le consegne non assegnate prima di pianificare.');return;
    }
    if(name==='revise'&&!changedAssignments)return;
    if(name==='revise'&&plan.status!=='preview')return;
    if(name!=='plan'&&name!=='revise')return;
    busy=true;
    el('routePreviewResult')?.querySelectorAll('button,select').forEach(b=>b.disabled=true);
    notice(name==='revise'?'Ricalcolo delle assegnazioni in corso…':'Verifica e programmazione dei giri in corso…');
    try{
      if(name==='revise'){
        const payload={version:plan.version,assignments:reviewAssignments()};
        plan=await api(`/api/fleet-planning/${plan.id}/revise`,{method:'POST',body:JSON.stringify(payload)});
        changedAssignments=false;draftAssignments=null;
        render();notice('Nuove fermate e stime ricalcolate. Controlla il risultato e premi “Pianifica giri”.');
      }else{
        if(plan.status==='preview'||plan.status==='saved'){
          plan=await api(`/api/fleet-planning/${plan.id}/program`,{
            method:'POST',body:JSON.stringify({version:plan.version,accept_unassigned:!!acceptUnassigned})
          });
        }
        render();
        if(plan.status==='programmed'){
          const issues=(plan.warnings||[]).filter(x=>/email non inviata|notifiche? non inviate?|fuori orario/i.test(x));
          notice(issues.length
            ?'Giri programmati. Attenzione: '+issues.join(' ') 
            :'Giri programmati correttamente. Le consegne sono ora disponibili nel portale degli autisti.');
          globalThis.GFOrderPlanning?.leave();
          await globalThis.GFOrderPlanning?.afterProgram?.().catch(()=>{});
          await loadRoutes();
        }
      }
    }catch(e){
      if(name==='plan'){
        try{
          plan=await api(`/api/fleet-planning/${plan.id}`);
          if(plan.status==='preview'){
            deliveries=plan.configuration.consegne.map(stop=>({...stop}));
            if(globalThis.GFOrderPlanning?.active())await GFOrderPlanning.loadSelection();
            renderDeliveries();
          }
        }catch(refreshError){console.warn('Impossibile aggiornare il piano',refreshError);}
      }
      render();
      if(plan?.status==='programmed'){
        globalThis.GFOrderPlanning?.leave();
        notice('Giri programmati correttamente. La risposta precedente non era arrivata: non sono stati creati duplicati.');
      }else notice(plan?.status==='saved'
          ?'Programmazione non completata. Controlla le bozze nello storico prima di riprovare. '+e.message
          :e.message);
    }finally{
      const lastMessage=el('fleetMessage')?.textContent;
      busy=false;
      render();
      if(lastMessage)notice(lastMessage);
    }
  }
  document.addEventListener('change',e=>{
    if(e.target.id==='planningMode'){modeChanged();refreshResourceAvailability();}
    if(e.target.dataset.field&&el('fleetResources').contains(e.target)){resources[Number(e.target.dataset.index)][e.target.dataset.field]=Number(e.target.value);if(e.target.dataset.field==='vehicle_id'){const title=e.target.closest('article')?.querySelector('[data-fleet-name]');if(title)title.textContent=vehicleName(e.target.value);}if(e.target.dataset.field==='driver_id'){resources[Number(e.target.dataset.index)].driver_schedule=null;GFDriverSchedules.fleet(resources);}if(['vehicle_id','driver_id'].includes(e.target.dataset.field))syncChoices();updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();}
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
