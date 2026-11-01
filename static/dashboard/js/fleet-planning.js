/* Multi-vehicle planning, integrated into the existing three-step workspace. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id);
  let resources=[],plan=null,busy=false,changedAssignments=false,draftAssignments=null,manualAdjusted=false,acknowledgedWarning=false,reviseError='';
  const active=()=>window.GFPlanAccess?.has('has_fleet_planning')===true && el('planningMode')?.value==='fleet';
  const blank=()=>({vehicle_id:0,driver_id:0,energy_price_primary:1.75,energy_price_electric:0.30,energy_price_mode:'automatic'});
  const can=permission=>!window.GFCompanyAccess||GFCompanyAccess.can(permission);
  const field=(id,label,control)=>`<label class="gf-field" for="${id}"><span class="gf-field__label">${label}</span>${control}</label>`;
  const config=()=>({planning_mode:active()?'fleet':'single',fleet_strategy:el('fleetStrategy')?.value||'efficient',fleet_resources:active()?resources.filter(r=>r.vehicle_id&&r.driver_id):[]});
  // Una sola card per uno e più mezzi. Con un solo mezzo la card è una vista sui campi del giro
  // (routeVehicle, routeDriver, fuelPrice, electricityPrice, energyPriceMode, turno di #routeDriverSchedule):
  // il calcolo del giro singolo resta quello di sempre. Con più mezzi i dati stanno in resources.
  let lastMode='single',parked=[]; // parked: le card di «Più mezzi» mentre si è passati a un solo mezzo
  const ready=()=>typeof resourcesDateTimeReady!=='function'||resourcesDateTimeReady();
  const value=id=>el(id)?.value??'',put=(id,v)=>{const node=el(id);if(node)node.value=v;};
  function fromFields(){
    const mode=document.querySelector?.('input[name="energyPriceMode"]:checked')?.value==='automatic'?'automatic':'manual';
    return {...blank(),vehicle_id:Number(value('routeVehicle'))||0,driver_id:Number(value('routeDriver'))||0,
      energy_price_primary:Number(value('fuelPrice'))||1.75,energy_price_electric:Number(value('electricityPrice'))||0.30,
      energy_price_mode:mode,driver_schedule:globalThis.GFDriverSchedules?.routePayload().driver_schedule};
  }
  function toFields(r){
    put('routeVehicle',r.vehicle_id||'');put('routeDriver',r.driver_id||'');
    put('fuelPrice',r.energy_price_primary);put('electricityPrice',r.energy_price_electric);
    const radio=document.querySelector?.(`input[name="energyPriceMode"][value="${r.energy_price_mode==='automatic'?'automatic':'manual'}"]`);if(radio)radio.checked=true;
    globalThis.GFDriverSchedules?.route(r.driver_schedule??GFDriverSchedules.defaults(r.driver_id));
    globalThis.updateRouteEnergyPricingV895?.();
  }
  // Campo del giro singolo cambiato dalla card: stesso effetto di una modifica fatta a mano sul campo.
  function setField(id,value){const input=el(id);if(!input)return;input.value=value;input.dispatchEvent(new Event('change',{bubbles:true}));}
  // Disponibilità sotto mezzo e autista, come nel giro singolo di prima.
  function availability(type,id){
    const badge=(status,text)=>`<span class="gf-badge" data-status="${status}" data-availability="${type}">${esc(text)}</span>`;
    if(!ready())return badge('neutral','Seleziona prima data e orario di partenza');
    const rows=resourcesAvailabilityCache?.[type]||[],row=rows.find(r=>r.id===Number(id));
    if(row)return row.available===false?badge('danger','Non disponibile'+(row.status&&row.status!=='Disponibile'?' · '+row.status:'')):badge('success','Disponibile');
    const free=rows.filter(r=>r.available!==false).length,noun=type==='vehicles'?'mezzi':'autisti';
    return badge(free?'neutral':'warning',free===rows.length?`Tutti ${type==='vehicles'?'i mezzi':'gli autisti'} risultano disponibili`:`${free} ${noun} disponibili su ${rows.length}`);
  }
  // Un mezzo o un autista già scelto in un'altra card non si può scegliere di nuovo.
  function options(type,id,index){
    if(!ready())return '<option value="">Seleziona prima l’orario</option>';
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
  // Turno, pausa e costo carburante direttamente nella card (niente pannelli da aprire).
  const vehicleOf=id=>(typeof vehiclesCache!=='undefined'?vehiclesCache:[]).find(v=>v.id===Number(id));
  const scheduleOf=r=>r.driver_schedule??globalThis.GFDriverSchedules?.defaults(r.driver_id)??{start:null,end:null,breaks:[]};
  function autoPrice(r){
    const vehicle=vehicleOf(r.vehicle_id),type=vehicle?.alimentazione||'gasolio';
    return type==='elettrico'?null:(typeof gfFuelPricesV895!=='undefined'?gfFuelPricesV895?.[fuelBaseTypeV895(type)]?.price:null)||null;
  }
  function extras(r,i){
    const schedule=scheduleOf(r),pause=(schedule.breaks||[])[0]||{},type=vehicleOf(r.vehicle_id)?.alimentazione||'gasolio';
    const time=(id,key,value,label)=>`<input class="gf-input" id="${id}" type="time" data-index="${i}" data-schedule="${key}" value="${esc(value||'')}" aria-label="${label}">`;
    const error=globalThis.GFDriverSchedules?.error(schedule)||'';
    const electric=type==='elettrico',plugin=type.startsWith('ibrido_plugin'),automatic=r.energy_price_mode==='automatic'&&!electric;
    const fuel=electric?'':`<div class="gf-field"><span class="gf-field__label" id="fleetFuelLabel${i}">Costo carburante</span><div class="gf-cluster"><button type="button" class="gf-chip" data-fuel-auto="${i}" aria-pressed="${automatic}" title="Prezzo medio nazionale aggiornato">Automatico</button><input class="gf-input" id="fleetFuel${i}" type="number" min="0.01" step="0.01" data-index="${i}" data-field="energy_price_primary" value="${r.energy_price_primary}" aria-labelledby="fleetFuelLabel${i}" ${automatic?'readonly':''}></div></div>`;
    const energy=electric||plugin?field('fleetElectric'+i,'Energia elettrica (€/kWh)',`<input class="gf-input" id="fleetElectric${i}" type="number" min="0.01" step="0.01" data-index="${i}" data-field="energy_price_electric" value="${r.energy_price_electric}">`):'';
    return `<div class="gf-grid" data-cols="2"><div class="gf-field"><span class="gf-field__label">Turno</span><div class="gf-stack" data-gap="sm">${time('fleetShiftStart'+i,'start',schedule.start,'Inizio turno')}${time('fleetShiftEnd'+i,'end',schedule.end,'Fine turno')}</div></div>`
      +`<div class="gf-field"><span class="gf-field__label">Orario di pausa</span><div class="gf-stack" data-gap="sm">${time('fleetBreakStart'+i,'break-start',pause.start,'Inizio pausa')}${time('fleetBreakEnd'+i,'break-end',pause.end,'Fine pausa')}</div></div></div>`
      +`<div class="gf-field" ${error?'data-invalid':''} data-schedule-state="${i}"><p class="gf-field__error" role="alert">${esc(error)}</p></div>${fuel}${energy}`;
  }
  // In automatico il prezzo è la media del carburante del mezzo; senza dato resta l'ultimo prezzo.
  async function applyAutoPrices(){
    if(!active()||!resources.some(r=>r.energy_price_mode==='automatic'))return;
    if(typeof gfFuelPricesV895!=='undefined'&&!gfFuelPricesV895)await loadAutomaticFuelPricesV895();
    let changed=false;
    resources.forEach((r,i)=>{const price=r.energy_price_mode==='automatic'&&autoPrice(r);if(price&&price!==r.energy_price_primary){r.energy_price_primary=price;changed=true;const input=el('fleetFuel'+i);if(input)input.value=price;}});
    if(changed){updateRoutePlanningGateV68();updateDashboardStats();}
  }
  const vehicleName=id=>(resourcesAvailabilityCache?.vehicles||[]).find(v=>v.id===Number(id))?.nome||'Nuovo mezzo';
  function refresh(){
    if(!el('fleetResources'))return;
    if(!active())resources=[fromFields()];
    const focused=document.activeElement?.id;
    const pick=(id,label,control,after)=>`<div class="gf-field"><label class="gf-field__label" for="${id}">${label}</label>${control}${after}</div>`;
    // Stessa card per uno e più mezzi: mezzo e autista con la disponibilità, turno, pausa e costo carburante.
    // La X compare appena le card sono più di una; restando con una sola si torna a «Un solo mezzo».
    const remove=i=>`<button type="button" class="gf-icon-button" data-remove="${i}" aria-label="Rimuovi mezzo e autista ${i+1}" title="Rimuovi"><svg class="gf-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>`;
    const select=(id,i,key,type,value)=>`<select class="gf-select" id="${id}" data-index="${i}" data-field="${key}" ${ready()?'':'disabled'}>${options(type,value,i)}</select>`;
    const more=active()
      ?`<div class="gf-card gf-stack" data-variant="info" data-gap="sm"><strong>Un altro mezzo?</strong><span class="gf-muted">Aggiungi una card vuota e scegli tu mezzo e autista.</span><span><button type="button" class="gf-button" data-variant="secondary" id="fleetAdd" ${resources.length>=10?'disabled':''}>+ Aggiungi mezzo</button></span></div>`
      :`<div class="gf-card gf-stack" data-variant="info" data-gap="sm"><strong>Tante consegne oggi?</strong><span class="gf-muted">Con più mezzi dividiamo noi le consegne tra gli autisti, rispettando carichi, turni e orari.</span><span><button type="button" class="gf-button" data-variant="secondary" data-plan-feature="has_fleet_planning" onclick="selectPlanningModeCard('fleet')">Usa più mezzi</button></span></div>`;
    el('fleetResources').innerHTML=resources.map((r,i)=>`<article class="gf-card gf-stack" data-gap="sm" aria-label="Mezzo e autista ${i+1}"><header class="gf-cluster" data-justify="between"><span class="gf-cluster"><span class="gf-stop__number">${i+1}</span><strong data-fleet-name>${esc(vehicleName(r.vehicle_id))}</strong></span>${resources.length>1?remove(i):''}</header>${pick('fleetVehicle'+i,'Mezzo',select('fleetVehicle'+i,i,'vehicle_id','vehicles',r.vehicle_id),availability('vehicles',r.vehicle_id))}${pick('fleetDriver'+i,'Autista',select('fleetDriver'+i,i,'driver_id','drivers',r.driver_id),availability('drivers',r.driver_id))}${extras(r,i)}</article>`).join('')+more;
    if(focused&&el(focused)&&el('fleetResources').contains(el(focused)))el(focused).focus();
    applyAutoPrices();
  }
  function modeChanged(notify=true){
    if(!window.GFPlanAccess?.has('has_fleet_planning'))el('planningMode').value='single';
    const mode=active()?'fleet':'single';
    // Da un mezzo a più mezzi: la card 1 resta com'è e si aggiunge una card vuota.
    // Tornando a più mezzi riappaiono anche le altre card di prima.
    if(mode==='fleet'&&lastMode!=='fleet'){resources=[fromFields(),...(parked.length>1?parked.slice(1):[blank()])];parked=[];}
    // Da più mezzi a un mezzo: la card 1 diventa il mezzo del giro singolo, le altre restano da parte.
    if(mode==='single'&&lastMode==='fleet'&&resources[0]){parked=resources.slice();toFields(resources[0]);}
    if(mode==='fleet'&&resources.length<2)while(resources.length<2)resources.push(blank());
    lastMode=mode;
    el('fleetSetup').hidden=false;el('fleetStrategyRow').hidden=!active();
    refresh();globalThis.updateRouteEnergyPricingV895?.();updateRoutePlanningGateV68();updateDashboardStats();
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
  function restore(saved={}){el('planningMode').value=window.GFPlanAccess?.has('has_fleet_planning') ? (saved.planning_mode||'single') : 'single';el('fleetStrategy').value=saved.fleet_strategy||'efficient';resources=(saved.fleet_resources||[]).map(({max_minutes,...r})=>({...blank(),...r}));lastMode=active()?'fleet':'single';parked=[];modeChanged(false);}
  function reset(){plan=null;changedAssignments=false;draftAssignments=null;manualAdjusted=false;acknowledgedWarning=false;window.GFFleetReview?.stopMap();restore();}
  function notice(text){const box=el('fleetMessage');if(box){box.textContent=text;box.scrollIntoView({block:'nearest'});}}
  async function calculate(){
    if(!window.GFPlanAccess?.require('has_fleet_planning','La suddivisione automatica su più mezzi'))return;
    if(busy)return;
    const gaps=routePlanningMissingFieldsV68();if(gaps.length){alert('Completa: '+gaps.join(', '));return;}
    if(!deliveries.length){alert('Aggiungi almeno una consegna.');return;}
    if(deliveries.length>100){alert('Puoi suddividere fino a 100 consegne per volta. Riduci la selezione.');return;}
    busy=true;
    // Schermata di attesa a tutto schermo: il numero di mezzi è quello delle card compilate.
    const vans=resources.length===1?'1 mezzo':`${resources.length} mezzi`;
    const wait=globalThis.GFDesignSystem?.showWait({
      title:`Sto pianificando i giri di ${vans}`,hint:'Di solito servono 10–30 secondi.',
      messages:['Calcolo le distanze tra i clienti…',resources.length===1?'Assegno le consegne al mezzo…':`Divido le consegne tra i ${vans}…`,'Controllo orari, peso e colli…','Ottimizzo l’ordine delle fermate…','Preparo i giri da controllare…']
    });
    try{
      showTab('route-preview');el('routePreviewResult').innerHTML='<section class="gf-panel"><div class="gf-loading" role="status">Distribuzione delle consegne in corso…</div></section>';
      const data={nome:val('routeName')||'Piano consegne',data_giro:val('routeDate'),orario_partenza:val('routeStart'),deposit_id:Number(val('routeDeposit')),rientro_deposito:boolVal('returnDepot'),strategy:el('fleetStrategy').value,resources,consegne:deliveries};
      plan=await api('/api/fleet-planning/preview',{method:'POST',body:JSON.stringify(data)});await wait?.close();changedAssignments=false;draftAssignments=null;manualAdjusted=false;acknowledgedWarning=false;busy=false;render();
    }catch(e){await wait?.close();el('routePreviewResult').innerHTML=`<section class="gf-panel"><div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">Distribuzione non completata</h2><p class="gf-alert" data-status="danger" role="alert">${esc(e.message)}</p><div><button type="button" class="gf-button" data-variant="secondary" onclick="showTab('giro')">Torna alla pianificazione</button></div></div></section>`;}
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
      manualAdjusted=true;reviseError='';
      render();
      if(changedAssignments)notice('Fermate spostate: premi “Ripianifica giri” in basso per aggiornare l’ordine delle fermate, i tempi e i costi.');
    };
    if(!acknowledgedWarning){
      window.GFFleetReview.warning(()=>{acknowledgedWarning=true;apply();});
    }else apply();
  }
  function render(){
    if(!plan)return;
    window.GFFleetReview.render({
      plan,assignment:reviewAssignments(),dirty:changedAssignments,busy,manualAdjusted,error:reviseError,
      permission:can('routes.program'),
      onMove:moveStop,
      onUndo:()=>{draftAssignments=null;changedAssignments=false;manualAdjusted=false;acknowledgedWarning=false;reviseError='';render();},
      onRecalc:()=>action('revise'),
      onPlan:accept=>action('plan',accept),
      onBack:()=>showTab('giro')
    });
  }
  async function action(name,acceptUnassigned=false){
    if(busy||!plan)return;
    if(!window.GFPlanAccess?.require('has_fleet_planning','La suddivisione automatica su più mezzi'))return;
    if(name==='plan'&&plan.status==='preview'&&changedAssignments){
      notice('Premi “Ripianifica giri” in basso prima di pianificare i giri.');return;
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
    notice(name==='revise'?'Ripianificazione dei giri in corso…':'Verifica e programmazione dei giri in corso…');
    const routes=plan.routes?.length||0,giri=routes===1?'1 giro':`${routes} giri`;
    const wait=globalThis.GFDesignSystem?.showWait(name==='revise'
      ?{title:'Sto ricalcolando i giri',messages:['Aggiorno le fermate spostate…','Ricalcolo percorsi e orari…','Controllo orari, peso e colli…']}
      :{title:routes?`Sto programmando ${giri}`:'Sto programmando i giri',minMs:1000,messages:['Salvo i giri…','Preparo le consegne per il portale degli autisti…']});
    try{
      if(name==='revise'){
        const payload={version:plan.version,assignments:reviewAssignments()};
        plan=await api(`/api/fleet-planning/${plan.id}/revise`,{method:'POST',body:JSON.stringify(payload)});
        await wait?.close();
        changedAssignments=false;draftAssignments=null;reviseError='';
        render();notice('Nuove fermate e stime ricalcolate. Controlla il risultato e premi “Pianifica giri”.');
      }else{
        if(plan.status==='preview'||plan.status==='saved'){
          plan=await api(`/api/fleet-planning/${plan.id}/program`,{
            method:'POST',body:JSON.stringify({version:plan.version,accept_unassigned:!!acceptUnassigned})
          });
        }
        await wait?.close();
        render();
        if(plan.status==='programmed'){
          const issues=(plan.warnings||[]).filter(x=>/email non inviata|notifiche? non inviate?|fuori orario/i.test(x));
          const message=issues.length
            ?'Giri programmati. Attenzione: '+issues.join(' ')
            :'Giri programmati correttamente. Le consegne sono ora disponibili nel portale degli autisti.';
          notice(message);
          globalThis.GFOrderPlanning?.leave();
          customerDirectoryPlanning=false; // giri programmati: nulla da mettere in bozza
          await globalThis.GFOrderPlanning?.afterProgram?.().catch(()=>{});
          await loadRoutes();
          // Come per il giro singolo: si apre Giri programmati sul giorno dei giri appena creati.
          toast(message);
          dashboardScheduledDay=plan.configuration.data_giro;
          Promise.allSettled([loadDashboardHome(),refreshResourceAvailability()]);
          showTab('dashboard-scheduled');
        }
      }
    }catch(e){
      await wait?.close();
      if(name==='revise')reviseError=e.message||'Ripianificazione non riuscita.';
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
      wait?.dispose();
      const lastMessage=el('fleetMessage')?.textContent;
      busy=false;
      render();
      if(lastMessage)notice(lastMessage);
    }
  }
  document.addEventListener('change',e=>{
    if(e.target.id==='planningMode'){modeChanged();refreshResourceAvailability();}
    if(e.target.dataset.field&&el('fleetResources').contains(e.target)){
      const i=Number(e.target.dataset.index),key=e.target.dataset.field,value=Number(e.target.value);
      if(!active()){
        // Giro singolo: la card scrive sui campi del giro (che avvisano bozza, prezzi e turno da soli).
        const target={vehicle_id:'routeVehicle',driver_id:'routeDriver',energy_price_primary:'fuelPrice',energy_price_electric:'electricityPrice'}[key];
        if(key==='energy_price_primary'){const manual=document.querySelector('input[name="energyPriceMode"][value="manual"]');if(manual)manual.checked=true;}
        setField(target,e.target.value);
        if(key==='vehicle_id')Promise.resolve(globalThis.updateRouteEnergyPricingV895?.()).then(refresh);
        else if(key==='driver_id'||key==='energy_price_primary')refresh();
        return;
      }
      resources[i][key]=value;
      if(key==='driver_id')resources[i].driver_schedule=null;
      if(key==='energy_price_primary')resources[i].energy_price_mode='manual';
      if(['vehicle_id','driver_id','energy_price_primary'].includes(key))refresh();
      updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();
    }
    // Turno e pausa scritti nella card: diventano il turno di oggi dell'autista (la prima pausa).
    if(e.target.dataset.schedule&&el('fleetResources').contains(e.target)){
      const i=Number(e.target.dataset.index),r=resources[i],schedule=JSON.parse(JSON.stringify(scheduleOf(r)));
      const key=e.target.dataset.schedule,value=e.target.value||null;
      if(key==='start'||key==='end')schedule[key]=value;
      else{schedule.breaks=schedule.breaks||[];schedule.breaks[0]={...(schedule.breaks[0]||{start:'',end:''}),[key==='break-start'?'start':'end']:value||''};if(!schedule.breaks[0].start&&!schedule.breaks[0].end)schedule.breaks.shift();}
      r.driver_schedule=schedule;
      if(!active())GFDriverSchedules.route(schedule); // giro singolo: diventa il turno del giro
      const message=GFDriverSchedules.error(schedule),state=el('fleetResources').querySelector(`[data-schedule-state="${i}"]`);
      if(state){state.toggleAttribute('data-invalid',!!message);state.querySelector('.gf-field__error').textContent=message;}
      updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();
    }
    if(e.target.id==='fleetStrategy')globalThis.GFOrderPlanning?.changed();
    if(e.target.dataset.stop!==undefined&&el('routePreviewResult').contains(e.target)){changedAssignments=true;notice('Fermate spostate: premi “Ripianifica giri” per verificare i nuovi giri.');}
  });
  document.addEventListener('click',e=>{
    const remove=e.target.closest('[data-remove]'),button=e.target.closest('[data-action]'),open=e.target.closest('[data-open]');
    // «Automatico»: torna al prezzo medio del carburante del mezzo.
    const auto=e.target.closest('[data-fuel-auto]');
    if(auto&&el('fleetResources').contains(auto)){
      const r=resources[Number(auto.dataset.fuelAuto)],next=r.energy_price_mode==='automatic'?'manual':'automatic';
      if(!active()){
        const radio=document.querySelector(`input[name="energyPriceMode"][value="${next}"]`);if(radio)radio.checked=true;
        Promise.resolve(globalThis.updateRouteEnergyPricingV895?.()).then(()=>{refresh();globalThis.GFOrderPlanning?.changed();});
      }else{r.energy_price_mode=next;refresh();globalThis.GFOrderPlanning?.changed();}
    }
    if(e.target.closest?.('#fleetAdd')&&active()&&resources.length<10){resources.push(blank());refresh();updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();}
    if(remove&&el('fleetResources').contains(remove)){
      resources.splice(Number(remove.dataset.remove),1);
      // Rimasta una sola card: si torna a «Un solo mezzo» con mezzo e autista di quella card.
      if(resources.length<2){parked=[];selectPlanningModeCard('single');}
      else{refresh();updateRoutePlanningGateV68();globalThis.GFOrderPlanning?.changed();}
    }
    if(button&&el('routePreviewResult').contains(button))action(button.dataset.action);
    if(open&&el('routePreviewResult').contains(open))GFOrderPlanning.openRoute(Number(open.dataset.open));
  });
  // Giri in bozza: la suddivisione aperta e la sua riapertura. Un'anteprima scaduta (12 ore) o già usata si ricalcola.
  const current=()=>plan&&plan.status==='preview'?plan.id:null;
  async function open(id){
    try{
      const loaded=await api(`/api/fleet-planning/${Number(id)}`);
      const stamp=String(loaded.created_at||''),utc=/Z$|[+-]\d\d:\d\d$/.test(stamp)?stamp:stamp+'Z'; // orario del server in UTC
      const fresh=!!stamp&&Date.now()-new Date(utc).getTime()<11*3600*1000;
      if(loaded.status==='preview'&&fresh){
        plan=loaded;changedAssignments=false;draftAssignments=null;manualAdjusted=false;acknowledgedWarning=false;
        showTab('route-preview');render();return true;
      }
    }catch(error){console.warn('Suddivisione non riapribile, la ricalcolo',error);}
    await calculate();return false;
  }
  // La card del mezzo c'è da subito, anche prima di scegliere data e orario.
  refresh();
  window.GFFleetPlanning={active,config,restore,reset,refresh,missing,calculate,current,open};
})();
