const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function render(violation, overrides={}, fromHistory=false){
  const node={innerHTML:''};
  const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
  const context=vm.createContext({document:{getElementById:()=>node},esc:x=>String(x??'').replaceAll('<','&lt;'),
    mapsAddressUrl:()=>'',deliverySignatureAction:()=>'',currentSessionUser:null,setTimeout:()=>{}});
  context.window=context;
  vm.runInContext(core.slice(core.indexOf('function gfRouteEnergyMetric('),core.indexOf('function updateDashboardStats(')),context);
  vm.runInContext(fs.readFileSync('static/routing-summary.js','utf8'),context);
  vm.runInContext(fs.readFileSync('static/tracking/company.js','utf8'),context);
  vm.runInContext(core.slice(core.indexOf('function warnTypeCounts('),core.indexOf('function cleanDeliveryForPayload(')),context);
  vm.runInContext(core.slice(core.indexOf('function renderRouteResult('),core.indexOf('async function loadRoadMapLibrary(')),context);
  context.route={id:1,status:'bozza',violations_count:violation?1:0,total_lateness_min:violation?5:0,
    consegne:[{ordine:1,cliente_nome:'Cliente <test>',indirizzo:'Test',arrivo_fisico:'08:40',inizio_servizio:'09:00',arrivo_stimato:'09:00',partenza_stimata:'09:15',attesa_min:20,lateness_min:violation?5:0,time_window_violation:violation?{}:null,warning:'Cliente in ZTL; Sponda richiesta'}]};
  Object.assign(context.route, overrides);
  context.fromHistory=fromHistory;
  vm.runInContext('renderRouteResult(route, "routeResult", fromHistory)',context);
  return node.innerHTML;
}
test('zero violations has no urgent window alarm, preserves operational warnings and timings',()=>{
  const html=render(false);
  assert.doesNotMatch(html,/Finestre orarie non rispettate|Finestra non rispettata/);
  for(const text of ['08:40','Inizio scarico: 09:00','09:15','20 min','ZTL','Sponda','Programma giro']) assert.ok(html.includes(text),text);
});

test('clean preview uses six full-width metrics and keeps map, print and scheduling actions',()=>{
  const html=render(false,{consegne:[{ordine:1,cliente_nome:'Cliente',indirizzo:'Via Roma',warning:''}],totale_km:89.59,litri_stimati:7.62,google_maps_url:'https://www.google.com/maps'});
  assert.equal((html.match(/class="mini-card"/g)||[]).length,6);
  assert.ok(html.indexOf('class="result-cards"') < html.indexOf('class="result-layout"'));
  assert.doesNotMatch(html,/class="alerts-panel"/);
  for(const text of ['89.59 km','7.62 L','Programma giro','Visualizza su mappa','Apri in Google Maps','Ricarica mappa','Stampa dettaglio fermate','Copia indirizzo']) assert.ok(html.includes(text),text);
});

test('saved history cannot schedule or reorder stops and routes without IDs do not load a map',()=>{
  const history=render(false,{status:'completato'},true);
  assert.doesNotMatch(history,/programCurrentRoute|draggable="true"/);
  assert.match(history,/Risultato giro salvato/);
  const unsaved=render(false,{id:null});
  assert.doesNotMatch(unsaved,/programCurrentRoute|class="route-map-panel-v74"/);
});

test('unclassified warnings remain visible in the preview summary and stop table',()=>{
  const html=render(false,{consegne:[{ordine:1,cliente_nome:'Cliente',indirizzo:'Via Roma',warning:'Percorso non fattibile'}]});
  assert.match(html,/Fermate da verificare/);
  assert.match(html,/Percorso non fattibile/);
});
test('violations show urgent summary and affected customer without blocking planning',()=>{
  const html=render(true);
  assert.match(html,/role="alert"/);
  assert.match(html,/Finestre orarie non rispettate/);
  assert.match(html,/Finestra non rispettata · 5.0 min/);
  assert.match(html,/Cliente &lt;test>/);
  assert.match(html,/Programma giro/);
  assert.doesNotMatch(html,/disabled/);
});
