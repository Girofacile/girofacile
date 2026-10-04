const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
const code=fs.readFileSync('static/dashboard/js/occasional-stops.js','utf8');

function fixture(){
  const nodes=new Map();
  function node(id){
    if(!nodes.has(id)) nodes.set(id,{value:'',textContent:'',disabled:false,focus(){},showModal(){this.open=true;},close(){this.open=false;},reportValidity:()=>true,reset(){for(const n of nodes.values())n.value='';}});
    return nodes.get(id);
  }
  let calls=0,invalidations=0;
  const proof={indirizzo:'Via Roma 18, Napoli',lat:0,lon:0,stato_geocodifica:'verificato',geocoding_token:'signed'};
  const context=vm.createContext({document:{getElementById:node},deliveries:[],
    val:id=>node(id).value.trim(),set:(id,v)=>node(id).value=String(v),boolVal:id=>node(id).value==='true',
    api:async()=>{calls++;return {...proof};},addDeliveryObject:d=>context.deliveries.push(d),
    renderDeliveries(){},markRouteNeedsRecalculation(){invalidations++;},updateDashboardStats(){},
    gfUniversalFeaturesV891:{has_time_windows:true,has_ztl:true,needs_tail_lift:true}});
  vm.runInContext(core.slice(core.indexOf('function customerIsPlannable('),core.indexOf('function requirePlannableCustomer(')),context);
  vm.runInContext(core.slice(core.indexOf('function cleanDeliveryForPayload('),core.indexOf('function routePayloadFromResult(')),context);
  vm.runInContext(core.slice(core.indexOf('function updateDeliveryField('),core.indexOf('function moveDelivery(')),context);
  vm.runInContext(code,context);
  return {node,context,proof,run:s=>vm.runInContext(s,context),calls:()=>calls,invalidations:()=>invalidations};
}

test('creation requires verification, creates null customer and preserves all stop fields',async()=>{
  const f=fixture();f.run('openOccasionalStopModal()');
  f.node('osName').value='Cantiere';f.node('osAddress').value='Via Roma';
  f.run('saveOccasionalStop()');assert.equal(f.context.deliveries.length,0);
  await f.run('verifyOccasionalAddress()');
  assert.equal(f.node('osVerificationStatus').textContent,'✓ Indirizzo verificato');
  f.node('osWeight').value='25';f.node('osPackages').value='3';f.node('osNotes').value='Cancello B';
  f.node('osMorningFrom').value='09:00';f.node('osZtl').value='true';
  f.run('saveOccasionalStop()');
  const d=f.context.deliveries[0];
  assert.equal(d.customer_id,null);assert.equal(d.peso_kg,25);assert.equal(d.colli,3);assert.equal(d.ztl,true);
  assert.equal(d.scarico_mattina_da,'09:00');assert.equal(d.geocoding_token,'signed');
  assert.equal(f.calls(),1);
  const roundTrip=f.run('cleanDeliveryForPayload(deliveries[0])');
  assert.equal(roundTrip.geocoding_token,d.geocoding_token);assert.equal(roundTrip.lat,0);
  assert.equal(roundTrip.tempo_scarico_min,0);
});

test('editing description reuses proof, address edit invalidates it and stale response cannot verify it',async()=>{
  const f=fixture();f.context.deliveries.push({...f.proof,customer_id:null,cliente_nome:'Old'});
  f.run('openOccasionalStopModal(0)');f.node('osName').value='New';f.run('saveOccasionalStop()');
  assert.equal(f.context.deliveries[0].cliente_nome,'New');assert.equal(f.calls(),0);
  f.run('openOccasionalStopModal(0)');f.node('osAddress').value='Other address';f.run('invalidateOccasionalAddress();saveOccasionalStop()');
  assert.equal(f.node('osSave').disabled,true);assert.equal(f.context.deliveries[0].indirizzo,f.proof.indirizzo);
  let resolve;f.context.api=()=>new Promise(r=>{resolve=r;});
  const pending=f.run('verifyOccasionalAddress()');
  f.node('osAddress').value='Changed while verifying';f.run('invalidateOccasionalAddress()');
  resolve(f.proof);await pending;
  assert.equal(f.node('osSave').disabled,true);assert.equal(f.node('osAddress').value,'Changed while verifying');
  f.run("updateDeliveryField(0,'indirizzo','Inline changed')");
  assert.equal(f.context.deliveries[0].geocoding_token,null);assert.equal(f.context.deliveries[0].lat,null);
});

test('drag/drop preserves verification and company preferences clear disabled options',()=>{
  const f=fixture();f.context.deliveries.push({...f.proof,customer_id:null,cliente_nome:'Occasional'},{customer_id:123,cliente_nome:'Registry'});
  f.context.event={preventDefault(){},dataTransfer:{setData(){}}};
  f.run('planningStopDragStart(event,0);planningStopDrop(event,1)');
  assert.equal(f.context.deliveries[1].geocoding_token,'signed');assert.equal(f.invalidations(),1);
  f.run('planningStopDragStart(event,0);planningStopDragEnd();planningStopDrop(event,1)');
  assert.equal(f.context.deliveries[1].geocoding_token,'signed');assert.equal(f.invalidations(),1);
  f.context.gfUniversalFeaturesV891={has_time_windows:false,has_ztl:false,needs_tail_lift:false};
  f.run('openOccasionalStopModal(1)');
  f.node('osZtl').value=f.node('osTailLift').value='true';f.node('osMorningFrom').value='09:00';
  f.run('saveOccasionalStop()');
  assert.equal(f.context.deliveries[1].ztl,false);assert.equal(f.context.deliveries[1].sponda,false);
  assert.equal(f.context.deliveries[1].scarico_mattina_da,null);
  f.run('openOccasionalStopModal(0)');assert.equal(f.node('occasionalStopDialog').open,false);
});

test('planning markup exposes occasional edit badge, responsive dialog and touch reorder controls',()=>{
  const html=fs.readFileSync('static/dashboard/index.html','utf8');
  const css=fs.readFileSync('static/dashboard/css/occasional-stops.css','utf8');
  assert.match(html,/\+ Fermata occasionale/);assert.match(html,/<dialog id="occasionalStopDialog"/);
  assert.match(html,/oninput="invalidateOccasionalAddress\(\)"/);
  assert.match(css,/@media\(max-width:540px\)/);assert.match(css,/min-height:44px/);
  assert.match(core,/planningStopDrop\(event, \$\{i\}\)/);assert.match(core,/moveDelivery\(\$\{i\}, -1\)/);
  assert.match(core,/Occasionale<\/span>/);
});
