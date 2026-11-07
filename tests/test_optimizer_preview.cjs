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
  vm.runInContext(fs.readFileSync('static/format.js','utf8'),context);
  vm.runInContext(fs.readFileSync('static/driver-schedule.js','utf8'),context);
  vm.runInContext(core.slice(core.indexOf('function gfRouteEnergyMetric('),core.indexOf('function updateDashboardStats(')),context);
  vm.runInContext(fs.readFileSync('static/routing-summary.js','utf8'),context);
  vm.runInContext(fs.readFileSync('static/tracking/company.js','utf8'),context);
  vm.runInContext(core.slice(core.indexOf('function warnTypeCounts('),core.indexOf('function cleanDeliveryForPayload(')),context);
  // Helper condivisi con il dettaglio dei giri programmati (date, importi, numeri, costi e avvisi).
  vm.runInContext(core.slice(core.indexOf('const DASH_SCHEDULED_DAY_NAMES'),core.indexOf('async function loadDashboardScheduledPage(')),context);
  vm.runInContext(core.slice(core.indexOf('function dashScheduledDate('),core.indexOf('function dashScheduledRoutesOf(')),context);
  vm.runInContext(core.slice(core.indexOf('const GF_STAT_ICONS'),core.indexOf('function dashboardScheduledDetailHtml(')),context);
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

test('clean preview: five metrics, stops above the map panel, print and scheduling actions',()=>{
  const html=render(false,{consegne:[{ordine:1,cliente_nome:'Cliente',indirizzo:'Via Roma',warning:''}],totale_km:89.59,litri_stimati:7.62,google_maps_url:'https://www.google.com/maps'});
  // Cinque indicatori con icone, poi la tabella delle fermate e sotto la mappa a tutta larghezza e il riepilogo.
  const metrics=html.slice(html.indexOf('data-preview-metrics'),html.indexOf('data-preview-stops'));
  assert.equal((metrics.match(/class="gf-stat-strip__cell"/g)||[]).length,5);
  assert.ok(html.indexOf('data-preview-metrics') < html.indexOf('data-preview-stops'));
  assert.ok(html.indexOf('data-preview-stops') < html.indexOf('data-preview-layout'));
  assert.match(html,/<section class="gf-panel" data-preview-map/);
  // Nessun riquadro di riepilogo: costi nelle card, autista e mezzo nel sottotitolo,
  // «Torna» e «Aggiorna ETA» sopra la tabella, «Programma giro» nella barra flottante.
  assert.doesNotMatch(html,/data-preview-summary|data-route-costs|gf-crew|data-preview-alerts|gf-route-panel"|Prima della partenza/);
  const actions=html.slice(html.indexOf('data-preview-actions'),html.indexOf('<table'));
  // Si torna con la freccia in alto; la stampa è un pulsante con icona, senza «Altre azioni».
  assert.doesNotMatch(html,/Torna alla pianificazione|Altre azioni|data-preview-back/);
  assert.match(actions,/data-preview-print[^>]*aria-label="Stampa dettaglio fermate"[^>]*><svg class="gf-icon"/);
  // Barra in basso: «Annulla» a sinistra di «Programma giro».
  assert.match(html,/<div class="gf-savebar" data-floating[^>]*data-preview-program-bar>[^]*data-preview-cancel[^]*data-preview-program/);
  for(const text of ['89,59','Annulla','Programma giro','Visualizza su mappa','Apri in Google Maps','Ricarica mappa','Stampa dettaglio fermate','Copia indirizzo']) assert.ok(html.includes(text),text);
});

test('saved history cannot schedule or reorder stops and routes without IDs do not load a map',()=>{
  const history=render(false,{status:'completato'},true);
  assert.doesNotMatch(history,/programCurrentRoute|draggable="true"/);
  assert.match(history,/Risultato giro salvato/);
  const unsaved=render(false,{id:null});
  assert.doesNotMatch(unsaved,/programCurrentRoute|data-preview-map[ >]/);
});

test('warnings stay next to their stop in the table, without summary cards',()=>{
  const html=render(false,{consegne:[{ordine:1,cliente_nome:'Cliente',indirizzo:'Via Roma',warning:'Percorso non fattibile'}],
    consegne_escluse:[{cliente_nome:'Cliente isola',indirizzo:'Via del Porto'}]});
  assert.doesNotMatch(html,/Fermate da verificare|gf-alert/);
  assert.match(html,/Percorso non fattibile/);
  const excluded=html.slice(html.indexOf('data-preview-excluded'));
  assert.match(excluded,/Cliente isola/);
  assert.match(excluded,/raggiungibile solo in traghetto/);
});
test('violations show the affected customer in the table without blocking planning',()=>{
  const html=render(true);
  assert.doesNotMatch(html,/Finestre orarie non rispettate/);
  assert.match(html,/Finestra non rispettata · 5.0 min/);
  assert.match(html,/Cliente &lt;test>/);
  assert.match(html,/Programma giro/);
  assert.doesNotMatch(html,/disabled/);
});
test('anteprima: la card dei pedaggi sostituisce il rientro, che resta sotto la partenza',()=>{
  const html=render(false,{orario_partenza:'07:00',orario_rientro_stimato:'11:01',toll_status:'estimated',toll_estimated_eur:2.3,costo_carburante:10,costo_totale:12.3});
  const metrics=html.slice(html.indexOf('data-preview-metrics'),html.indexOf('data-preview-stops'));
  assert.match(metrics,/Pedaggi/);
  assert.match(metrics,/2,30/);
  assert.match(metrics,/rientro 11:01/);
  assert.doesNotMatch(metrics,/Rientro previsto/);
  // Pedaggi in fondo, accanto al costo del carburante senza pedaggi né diciture.
  assert.ok(metrics.indexOf('Costo carburante') < metrics.indexOf('Pedaggi'));
  assert.match(metrics,/Costo carburante<\/span><strong class="gf-stat-strip__value">€ 10,00<\/strong>/);
  assert.doesNotMatch(metrics,/Costo operativo|>carburante</);
  const unknown=render(false,{toll_estimated_eur:null,toll_status:'unavailable'});
  assert.match(unknown.slice(unknown.indexOf('data-preview-metrics'),unknown.indexOf('data-preview-stops')),/non disponibili/);
  const free=render(false,{toll_estimated_eur:0,toll_status:'estimated'});
  assert.match(free.slice(free.indexOf('data-preview-metrics'),free.indexOf('data-preview-stops')),/nessun pedaggio/);
});
