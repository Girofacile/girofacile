const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function summary(route, action="refresh(1)"){
  const context=vm.createContext({window:{}});
  vm.runInContext(fs.readFileSync('static/routing-summary.js','utf8'),context);
  return context.window.GiroFacileRouting.summaryHtml(route,action);
}

test('shared desktop/mobile summary distinguishes traffic, toll estimate and operating cost',()=>{
  const html=summary({id:1,status:'programmato',eta_label:'ETA con traffico aggiornato',traffic_status:'updated',
    traffic_calculated_at:'2026-09-30T08:00:00Z',toll_status:'estimated',toll_estimated_eur:5.5,
    costo_carburante:20,costo_totale:25.5,operating_cost_status:'estimated'});
  for(const label of ['ETA con traffico aggiornato','Traffico calcolato','Pedaggio stimato','Costo operativo stimato','25,50','Aggiorna ETA con traffico']){
    assert.ok(html.includes(label),label);
  }
});
test('unknown tolls are not displayed as zero and completed routes cannot request traffic',()=>{
  const html=summary({id:1,status:'completato',eta_label:'Tempi stradali stimati senza traffico',
    toll_estimated_eur:null,toll_status:'unavailable',operating_cost_status:'partial',costo_totale:0});
  assert.match(html,/Non disponibile/);
  assert.match(html,/Totale parziale/);
  assert.doesNotMatch(html,/Aggiorna ETA con traffico/);
  assert.match(summary({eta_label:'<img onerror="test">'}),/&lt;img/);
});
test('electric energy stays in kWh and all route interfaces load the shared component',()=>{
  const html=summary({energy_unit:'kWh',energy_quantity_primary:0,energy_quantity_electric:12});
  assert.match(html,/12 kWh/);
  assert.doesNotMatch(html,/0 L/);
  for(const path of ['static/dashboard/index.html','static/mobile/index.html','static/driver/index.html','static/operator/index.html']){
    const source=fs.readFileSync(path,'utf8');
    assert.match(source,/\/static\/routing-summary.js/);
    assert.match(source,/\/static\/routing-summary.css/);
  }
});
test('mobile programming/refresh and vehicle toll classes are available alongside desktop controls',()=>{
  const mobile=fs.readFileSync('static/mobile/mobile.js','utf8');
  assert.match(mobile,/function programMobileRoute/);
  assert.match(mobile,/function refreshMobileRouteTraffic/);
  assert.match(mobile,/fTollClass/);
  assert.match(fs.readFileSync('static/dashboard/index.html','utf8'),/vTollClass/);
  assert.doesNotMatch(fs.readFileSync('static/dashboard/js/core.js','utf8'),/maps.googleapis.com\/maps\/api\/js/);
});
test('all changed browser scripts parse',()=>{
  for(const path of ['static/routing-summary.js','static/mobile/mobile.js','static/dashboard/js/core.js']){
    new vm.Script(fs.readFileSync(path,'utf8'),{filename:path});
  }
  for(const path of ['static/admin/index.html','static/driver/index.html','static/operator/index.html']){
    const html=fs.readFileSync(path,'utf8');
    for(const [,source] of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(source,{filename:path});
  }
});
