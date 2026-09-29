const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function render(violation){
  const node={innerHTML:''};
  const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
  const context=vm.createContext({document:{getElementById:()=>node},esc:x=>String(x??'').replaceAll('<','&lt;'),
    mapsAddressUrl:()=>'',deliverySignatureAction:()=>'',currentSessionUser:null,setTimeout:()=>{}});
  vm.runInContext(core.slice(core.indexOf('function warnTypeCounts('),core.indexOf('function cleanDeliveryForPayload(')),context);
  vm.runInContext(core.slice(core.indexOf('function renderRouteResult('),core.indexOf('async function loadGoogleMapsScriptV74(')),context);
  context.route={id:1,status:'bozza',violations_count:violation?1:0,total_lateness_min:violation?5:0,
    consegne:[{ordine:1,cliente_nome:'Cliente <test>',indirizzo:'Test',arrivo_fisico:'08:40',inizio_servizio:'09:00',arrivo_stimato:'09:00',partenza_stimata:'09:15',attesa_min:20,lateness_min:violation?5:0,time_window_violation:violation?{}:null,warning:'Cliente in ZTL; Sponda richiesta'}]};
  vm.runInContext('renderRouteResult(route)',context);
  return node.innerHTML;
}
test('zero violations has no urgent window alarm, preserves operational warnings and timings',()=>{
  const html=render(false);
  assert.doesNotMatch(html,/Finestre orarie non rispettate|Finestra non rispettata/);
  for(const text of ['08:40','Inizio scarico: 09:00','09:15','20 min','ZTL','Sponda','Programma giro']) assert.ok(html.includes(text),text);
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
