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
  assert.equal((html.match(/class="gf-chip"/g)||[]).length,7);
  assert.match(html,/Martedì&nbsp;29 <span class="gf-chip__count">1<\/span>/);
  assert.match(html,/Settimana 28 settembre – 4 ottobre 2026/);
  for(const text of ['Giro selezionato','0 km','0 min','openDashboardScheduledRoute(42)']) assert.ok(html.includes(text),text);
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
