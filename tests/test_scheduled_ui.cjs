const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
function fixture(){
  const node={innerHTML:'',scrollIntoView(){},querySelector:()=>null,setAttribute(){}};
  const fields={},tabs=[],errors=[];
  const route={id:42,status:'programmato',nome:'Giro selezionato',data_giro:'2026-09-29',orario_partenza:'08:00',deposit_id:3,vehicle_id:4,driver_id:5,energy_price_primary:1.8,rientro_deposito:true,totale_km:0,totale_minuti:0,consegne:[{ordine:1,cliente_nome:'Cliente <test>',indirizzo:'Via Roma',delivery_status:'completata'},{ordine:2,cliente_nome:'Secondo',delivery_status:'mancata'},{ordine:3,cliente_nome:'Terzo',delivery_status:'in_attesa',note_operatore:'All\'ingresso "laterale"\nChiamare'}]};
  const ctx=vm.createContext({document:{getElementById:()=>node,querySelector:()=>({checked:false})},deliverySignatureAction:()=>'',api:async()=>route,showTab:t=>tabs.push(t),set:(id,v)=>fields[id]=v,val:id=>fields[id]||'',todayIso:()=> '2026-09-29',refreshResourceAvailability:async()=>{},updateRouteEnergyPricingV895:async()=>{},cleanDeliveryForPayload:d=>d,updateRoutePlanningGateV68:()=>{},renderDeliveries:()=>{},toast:()=>{},alert:m=>errors.push(m),renderRouteResult:()=>{}});
  ctx.window=ctx;
  vm.runInContext(fs.readFileSync('static/format.js','utf8'),ctx);
  vm.runInContext(fs.readFileSync("static/driver-schedule.js","utf8"),ctx);
  vm.runInContext(core.slice(core.indexOf('function gfRouteEnergyMetric('),core.indexOf('function updateDashboardStats(')),ctx);
  vm.runInContext(fs.readFileSync('static/routing-summary.js','utf8'),ctx);
  vm.runInContext(fs.readFileSync('static/tracking/company.js','utf8'),ctx);
  const parts=[core.slice(core.indexOf('function esc('),core.indexOf('\n',core.indexOf('function esc('))),core.slice(core.indexOf('function deliveryWindowLabel('),core.indexOf('function renderDeliveries(')),core.slice(core.indexOf('function deliveryStatusPill('),core.indexOf('function signatureDateLabel(')),core.slice(core.indexOf('function gfTimeFromIso('),core.indexOf('function renderDashboardInProgressSubpage(')),core.slice(core.indexOf('async function openDashboardScheduledPage('),core.indexOf('async function openDashboardCompletedPage(')),core.slice(core.indexOf('async function openProgrammedRouteForEdit('),core.indexOf('function renderRouteResult('))];
  vm.runInContext(parts.join('\n'),ctx);
  ctx.route=route;
  return {node,fields,tabs,errors,ctx,route,run:code=>vm.runInContext(code,ctx)};
}
test('scheduled week shows seven days and the day table; a route opens as a full page',()=>{
  const f=fixture();f.run('renderDashboardScheduledSubpage([route],null)');let html=f.node.innerHTML;
  // Sette card dei giorni affiancate, con giorno e data sempre sulla stessa riga.
  assert.match(html,/class="gf-grid" data-cols="7"/);
  assert.equal((html.match(/class="gf-day-head"/g)||[]).length,7);
  // Il colore segue il giorno scelto (aria-pressed); oggi ha solo aria-current (numero rosso), senza scritta.
  assert.doesNotMatch(html,/data-day="today"/);
  assert.match(html,/aria-pressed="true" aria-current="date" aria-label="Martedì 29 settembre · oggi · 1 giro"[^>]*><span class="gf-day-head__weekday">Mar<\/span><span class="gf-day-head__number">29<\/span><span class="gf-badge" data-status="info">1 giro<\/span>/);
  assert.equal((html.match(/data-day="weekend"/g)||[]).length,2);
  // Il giro mostra orario, autista, mezzo e fermate; in fondo «Mostra di più».
  assert.match(html,/class="gf-list-item"[^>]*onclick="openDashboardScheduledRoute\(42\)"><span class="gf-list-item__main"><strong>08:00 · Non assegnato<\/strong><small>Mezzo non indicato<\/small><small>0 fermate<\/small>/);
  assert.match(html,/onclick="showAllDashboardScheduledDay\('2026-09-29'\)">Mostra di più<\/button><\/footer>/);
  // Giorni vuoti: icona e «Nessun giro»; «Pianifica giro» solo da oggi in poi (mercoledì–domenica, non lunedì 28).
  assert.equal((html.match(/<p>Nessun giro<\/p>/g)||[]).length,6);
  assert.equal((html.match(/data-variant="secondary" data-size="sm" onclick="openPlanningSelection\(\)">Pianifica giro<\/button><\/div>/g)||[]).length,5);
  assert.doesNotMatch(html,/gf-route-card|data-status="warning"/);
  assert.match(html,/<p class="gf-muted">1 giro programmato<\/p>/);
  assert.match(html,/Settimana 28 settembre – 4 ottobre 2026/);
  for(const text of ['Non assegnato','0 km','0 min','openDashboardScheduledRoute(42)']) assert.ok(html.includes(text),text);
  // Il giro scelto si apre a pagina intera (variante B): barra con icone, mappa, fermate, tabella apribile.
  f.run('renderDashboardScheduledSubpage([route],route)');html=f.node.innerHTML;
  assert.doesNotMatch(html,/<dialog|data-cols="7"/);
  for(const text of ['<strong class="gf-stat-strip__value">3</strong>','data-scheduled-detail','class="gf-stat-strip" data-icons="side"','class="gf-stat-strip__icon"','data-route-map','class="gf-route-panel"','Giro selezionato','Cliente &lt;test&gt;','data-note="All&#39;ingresso &quot;laterale&quot;','alert(this.dataset.note)','openProgrammedRouteForEdit(42, true)',"refreshRouteTraffic(42, 'dashboardScheduledPage', 'scheduled')",'id="scheduledStopsTable"']) assert.ok(html.includes(text),text);
  // Accanto alla mappa solo gli avvisi (niente elenco fermate ripetuto): clienti in ZTL, area pedonale, sponda e colli.
  assert.doesNotMatch(html,/class="gf-stop-list"/);
  assert.match(html,/data-route-notices/);
  assert.match(html,/colli in totale per questo giro|collo in totale per questo giro/);
  // La freccia unica della barra in alto riporta alla settimana.
  assert.equal(f.node.onclick,f.ctx.closeDashboardScheduledRoute);
  f.run('closeDashboardScheduledRoute()');
  assert.match(f.node.innerHTML,/data-cols="7"/);
  f.run('selectDashboardScheduledDay("2026-09-30")');
  assert.match(f.node.innerHTML,/In questa giornata non ci sono giri/);
  assert.match(f.node.innerHTML,/class="gf-empty__icon"/);
  f.run('renderDashboardScheduledSubpage([],null)');assert.match(f.node.innerHTML,/Nessun giro programmato/);
});
test('direct edit hydrates the selected scheduled route and stays in planning',async()=>{
  const f=fixture();await f.run('openProgrammedRouteForEdit(42,true)');
  assert.deepEqual(f.errors,[]);assert.deepEqual(f.tabs,['giro']);
  assert.equal(f.fields.routeName,'Giro selezionato');assert.equal(f.fields.routeDeposit,3);assert.equal(f.fields.routeVehicle,4);assert.equal(f.fields.routeDriver,5);assert.equal(f.fields.fuelPrice,1.8);assert.equal(f.ctx.lastRouteResult.id,42);assert.equal(f.ctx.deliveries.length,3);
});
test('normal opening retains preview and completed routes retain read-only view',async()=>{
  const f=fixture();await f.run('openProgrammedRouteForEdit(42)');assert.equal(f.tabs.at(-1),'route-preview');
  f.route.status='completato';await f.run('openProgrammedRouteForEdit(42,true)');assert.equal(f.tabs.at(-1),'route-preview');assert.deepEqual(f.errors,[]);
});


test('completed delivery delay uses full date and keeps delays beyond 24 hours',()=>{
  const f=fixture();
  f.route.status='completato';
  f.route.data_giro='2026-10-04';
  f.route.orario_partenza='20:00';
  f.route.consegne=[{
    id:1,ordine:1,cliente_nome:'Cliente',indirizzo:'Via Roma',
    delivery_status:'completata',arrivo_stimato:'22:00',
    completata_il:'2026-10-05T23:00:00'
  }];
  const html=f.run('dashboardStopRowsUnified(route,"completed")');
  assert.match(html,/\+1500 min/);
});

test('completed delivery delay handles midnight rollover and same-day early arrivals',()=>{
  const overnight=fixture();
  overnight.route.status='completato';
  overnight.route.data_giro='2026-10-05';
  overnight.route.orario_partenza='23:00';
  overnight.route.consegne=[{
    id:1,ordine:1,cliente_nome:'Notturno',indirizzo:'Via Roma',
    delivery_status:'completata',arrivo_stimato:'00:30',
    completata_il:'2026-10-06T00:45:00'
  }];
  assert.match(overnight.run('dashboardStopRowsUnified(route,"completed")'),/\+15 min/);

  const early=fixture();
  early.route.status='completato';
  early.route.data_giro='2026-10-05';
  early.route.orario_partenza='08:00';
  early.route.consegne=[{
    id:2,ordine:1,cliente_nome:'Anticipato',indirizzo:'Via Milano',
    delivery_status:'completata',arrivo_stimato:'10:00',
    completata_il:'2026-10-05T09:45:00'
  }];
  assert.match(early.run('dashboardStopRowsUnified(route,"completed")'),/-15 min/);
});

test('route notices name the clients in ZTL, pedestrian areas and needing a tail lift, plus total parcels',()=>{
  const f=fixture();
  const html=f.run(`gfRouteNoticesHtml([
    {cliente_nome:'Bar Sole',ztl:true,colli:6},{cliente_nome:'Hotel Marina',ztl:true,sponda:true,colli:9},
    {cliente_nome:'Pizzeria <Nola>',pedestrian_area:true,colli:'5'},{cliente_nome:'Market',colli:10}
  ])`);
  assert.match(html,/<strong>2 clienti in zona ZTL<\/strong><small>Bar Sole · Hotel Marina<\/small>/);
  assert.match(html,/<strong>1 cliente in area pedonale<\/strong><small>Pizzeria &lt;Nola&gt;<\/small>/);
  assert.match(html,/<strong>1 cliente richiedono la sponda<\/strong>|<strong>1 cliente richiede la sponda<\/strong>/);
  assert.match(html,/<strong>30 colli in totale per questo giro<\/strong>/);
  assert.doesNotMatch(f.run(`gfRouteNoticesHtml([{cliente_nome:'Market',colli:3}])`),/ZTL|area pedonale|sponda/);
});

test('route numbers mirror the Dashboard strip; costs sit beside the map; stops table always open',()=>{
  const f=fixture();
  f.run('renderDashboardScheduledSubpage([route],route)');const html=f.node.innerHTML;
  assert.match(html,/class="gf-stat-strip" data-icons="side" data-fit/);
  assert.match(html,/<div class="gf-stat-strip__cell" data-size="sm">[^]*?<span class="gf-stat-strip__label">Fermate<\/span><strong class="gf-stat-strip__value">3<\/strong><small class="gf-stat-strip__unit"><\/small>/);
  assert.match(html,/data-route-costs/);
  assert.match(html,/id="scheduledStopsTable">/);
  assert.doesNotMatch(html,/Mostra tabella|scheduledStopsTable" hidden/);
  const costs=f.run(`gfRouteCostsHtml({costo_carburante:8.9,costo_totale:14.62,toll_estimated_eur:5.72,litri_stimati:10.4})`);
  assert.match(costs,/<dt>Carburante · 10.4 L<\/dt><dd>€ 8,90<\/dd>/);
  assert.match(costs,/<dt>Pedaggi<\/dt><dd>€ 5,72<\/dd>/);
  assert.match(costs,/<strong>€ 14,62<\/strong>/);
  assert.doesNotMatch(f.run(`gfRouteCostsHtml({costo_carburante:6.5,toll_estimated_eur:null})`),/Pedaggi/);
});

test('driver break is an unnumbered yellow row between stops in the scheduled table',()=>{
  const f=fixture();
  f.route.driver_breaks=[{after_order:2,start:'14:00',end:'14:30',duration_min:30}];
  f.run('renderDashboardScheduledSubpage([route],route)');
  const html=f.node.innerHTML;
  const table=html.slice(html.indexOf('id="scheduledStopsTable"'));
  assert.match(table,/<tr class="driver-break-row" data-break-after="2"><td aria-hidden="true"><\/td><td colspan="6"><strong>Pausa del turno dalle 14:00 alle 14:30<\/strong><small>30 minuti di riposo per l’autista<\/small><\/td><\/tr>/);
  // Tra la seconda e la terza fermata, senza numero.
  assert.ok(table.indexOf('Secondo')<table.indexOf('Pausa del turno') && table.indexOf('Pausa del turno')<table.indexOf('Terzo'));
  assert.doesNotMatch(html,/Ⅱ/);
});

test('giri programmati: «+ Pianifica giro» nella barra in alto, non nella riga della settimana',()=>{
  const index=fs.readFileSync('static/dashboard/index.html','utf8');
  assert.match(index,/data-show-on-tabs="dashboard-scheduled" data-scheduled-plan onclick="openPlanningSelection\(\)">\+ Pianifica giro<\/button>/);
  const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
  assert.doesNotMatch(core,/shiftDashboardScheduledWeek\(1\)">Successiva ›<\/button><button/);
});
test('giri non partiti in orario: badge, avviso con le scelte e avviso in Dashboard',()=>{
  const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
  const ctx=vm.createContext({esc:x=>String(x??'')});
  vm.runInContext(core.slice(core.indexOf('function gfLateStartBadge('),core.indexOf('// «Sposta la partenza ad adesso»')),ctx);
  assert.equal(ctx.gfLateStartBadge({}), '');
  assert.match(ctx.gfLateStartBadge({late_start:{state:'in_ritardo',label:'In ritardo',delay_min:20}}),/data-status="warning"[^>]*>In ritardo · \+20 min</);
  // Nei riquadri della settimana il badge è breve, senza minuti.
  assert.match(ctx.gfLateStartBadge({late_start:{state:'da_riprogrammare',label:'Da riprogrammare',delay_min:552}},{short:true}),/data-status="danger"[^>]*>Da riprogrammare</);
  const alert=ctx.gfLateStartAlert({id:7,late_start:{state:'da_riprogrammare',label:'Da riprogrammare',delay_min:47,problems:['1 consegna fuori fascia: Bar Roma']}});
  for(const text of ['Sposta la partenza ad adesso','Riprogramma','Annulla giro','Bar Roma','non può avviare da solo'])assert.ok(alert.includes(text),text);
  // Giorno passato: niente «Sposta la partenza», solo riprogrammare o annullare.
  assert.doesNotMatch(ctx.gfLateStartAlert({id:7,late_start:{state:'non_avviato',label:'Non avviato',delay_min:900,problems:[]}}),/Sposta la partenza/);
  assert.match(core,/data-late-start-dashboard/);
  assert.match(core,/\/depart-now`/);
});
test('«+ Pianifica giro» sparisce quando si apre il dettaglio di un giro programmato',()=>{
  const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
  assert.match(core,/querySelector\('\[data-scheduled-plan\]'\)\?\.classList\.toggle\('gf-hidden', !!selectedRoute\)/);
  assert.match(fs.readFileSync('static/dashboard/js/navigation.js','utf8'),/dashboardScheduledSelectedId\)document\.querySelector\("\[data-scheduled-plan\]"\)/);
});
