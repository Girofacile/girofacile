const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const billing=fs.readFileSync('static/dashboard/js/billing.js','utf8');
function catalog(){
  return Object.fromEntries(['starter','business','pro'].map((key,index)=>[key,{
    name:['Starter','Business','Pro'][index],price_eur:[29,59,99][index],
    max_orders_per_month:[300,1200,6000][index],max_customers:[150,500,5000][index],
    max_deposits:[1,3,20][index],max_vehicles:[3,10,50][index],max_drivers:[3,10,50][index],
    electric_vehicle_bonus:[1,2,5][index],max_collaborators:[2,5,10][index],
    ...Object.fromEntries(['has_customer_tracking','has_fleet_planning','has_driver_chat','has_agents',
      'has_delivery_signature','has_photo_proof','has_pod_pdf','has_order_integrations','has_reports'].map(flag=>[flag,index>0])),
    has_ai:index===2
  }]));
}
function fixture(plan='starter'){
  const nodes={},messages=[];
  const node=id=>nodes[id]??={value:'',checked:false,disabled:false,hidden:false,innerHTML:'',textContent:'',dataset:{},
    classList:{toggle(){},add(){},remove(){}},closest(){return null;},setAttribute(){},toggleAttribute(){},
    reset(){},showModal(){},close(){},scrollIntoView(){},replaceChildren(){this.innerHTML='';},querySelectorAll(){return [];}};
  const ctx=vm.createContext({window:{GF_PLANS:catalog()},currentSessionUser:{plan},
    document:{getElementById:node,querySelectorAll(){return [];},addEventListener(){}},
    esc:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
    toast:message=>messages.push(message),console});
  vm.runInContext(billing,ctx);
  return {ctx,node,messages,run:code=>vm.runInContext(code,ctx)};
}
test('plan cards use monthly orders and retain all resource caps and portal GPS access',()=>{
  const f=fixture();
  for(const [key,orders,seats] of [['starter',300,2],['business',1200,5],['pro',6000,10]]){
    const plan=f.run(`planFeatures('${key}')`);
    assert.equal(plan.features[0],orders+' ordini/mese');
    assert.ok(plan.resourceFeatures.includes(seats+' collaboratori aziendali'));
    assert.ok(plan.features.includes('Portale autista e GPS autista'));
    assert.ok(!plan.features.some(label=>/giri\/mese|consegne\/mese/.test(label)));
  }
  for(const label of ['Tracking clienti','Firma alla consegna','Foto prova consegna','Prova di consegna PDF','Integrazione AI']){
    assert.ok(f.run("planFeatures('starter')").missing.includes(label));
  }
  assert.ok(f.run("planFeatures('business')").missing.includes('Integrazione AI'));
  assert.ok(f.run("planFeatures('pro')").features.includes('Integrazione AI'));
  const keys=f.run('planComparisonRows().map(row=>row[1])');
  assert.ok(keys.includes('max_orders_per_month') && keys.includes('max_collaborators'));
  assert.ok(!keys.includes('max_routes_per_month') && !keys.includes('max_deliveries_per_month'));
});
test('landing and account use the same compact capability groups derived from catalogue flags',()=>{
  const f=fixture('business');
  const starter=f.run("planFeatureGroups('starter')");
  assert.equal(starter.filter(([included])=>included).length,1);
  assert.equal(f.run("planFeatureGroups('business').filter(([included])=>included).length"),5);
  assert.equal(f.run("planFeatureGroups('pro').filter(([included])=>included).length"),6);
  f.ctx.window.GF_PLANS.pro.has_ai=false;
  assert.equal(f.run("planFeatureGroups('pro').at(-1)[0]"),false);
  assert.match(fs.readFileSync('static/landing/index.html','utf8'),/planFeatureGroups\(/);
  assert.match(fs.readFileSync('static/dashboard/js/core.js','utf8'),/planPageFeatures\(/);
});
test('monthly orders meter shows remaining quota, warns at 80 percent and never goes negative',()=>{
  const f=fixture();
  const html=used=>f.run(`monthlyOrderUsageMarkup({month:'2026-10',orders:{used:${used},limit:300}})`);
  assert.match(html(239),/61 ordini ancora disponibili/);
  assert.doesNotMatch(html(239),/80%/);
  assert.match(html(240),/80%/);
  assert.match(html(240),/role="progressbar"[^>]*aria-valuemax="300"[^>]*aria-valuenow="240"/);
  assert.match(html(305),/0 ordini ancora disponibili/);
  assert.match(html(305),/Quota mensile ordini esaurita/);
  assert.match(html(305),/aria-valuenow="300"/);
});
test('effective company flags override catalogue and clear stale premium settings after downgrade',()=>{
  const f=fixture('business');
  f.ctx.currentSessionUser.limits={has_delivery_signature:false,has_photo_proof:false,has_fleet_planning:false};
  f.node('settingDeliverySignature').checked=true;f.node('featurePhotoProofV89').checked=true;
  f.run('applyPlanFeatureControls()');
  for(const id of ['settingDeliverySignature','featurePhotoProofV89']){
    assert.equal(f.node(id).checked,false);assert.equal(f.node(id).disabled,true);
  }
  assert.equal(f.run("requirePlanFeature('has_fleet_planning','Suddivisione automatica')"),false);
  assert.match(f.messages[0],/Business/);
  f.ctx.currentSessionUser.limits={has_delivery_signature:true,has_photo_proof:true,has_fleet_planning:true};
  f.run('applyPlanFeatureControls()');
  assert.equal(f.node('settingDeliverySignature').disabled,false);
});
test('fleet configuration restored on Starter falls back to one vehicle and cannot call planning API',async()=>{
  const f=fixture();let calls=0;
  Object.assign(f.ctx,{resourcesAvailabilityCache:{vehicles:[],drivers:[]},updateRoutePlanningGateV68(){},updateDashboardStats(){},api(){calls++;},alert(){}});
  vm.runInContext(fs.readFileSync('static/dashboard/js/fleet-planning.js','utf8'),f.ctx);
  f.ctx.window.GFFleetPlanning.restore({planning_mode:'fleet',fleet_resources:[{vehicle_id:1,driver_id:2}]});
  assert.equal(f.node('planningMode').value,'single');
  assert.equal(f.ctx.window.GFFleetPlanning.config().planning_mode,'single');
  assert.equal(f.ctx.window.GFFleetPlanning.config().fleet_resources.length,0);
  await f.ctx.window.GFFleetPlanning.calculate();
  assert.equal(calls,0);
});
test('collaborator cap includes pending invitations and prevents reactivation without blocking existing edits',async()=>{
  const f=fixture();let writes=0;
  const records=[{id:1,full_name:'Active',email:'active@example.test',is_active:true,permissions:[]},
    {id:2,full_name:'Pending',email:'pending@example.test',is_active:true,password_setup_required:true,permissions:[]},
    {id:3,full_name:'Inactive',email:'inactive@example.test',is_active:false,permissions:[]}];
  f.ctx.api=async(path,options)=>{
    if(options){writes++;return records[0];}
    return path.endsWith('/permissions')?{permissions:[{key:'orders.read',label:'Leggi ordini',group:'Ordini'}],presets:[],dependencies:{}}:records;
  };
  vm.runInContext(fs.readFileSync('static/dashboard/js/collaborators.js','utf8'),f.ctx);
  await f.ctx.window.GFCollaborators.load();
  assert.equal(f.node('collaboratorInviteNew').disabled,true);
  assert.match(f.node('collaboratorQuota').textContent,/2 \/ 2/);
  f.ctx.window.GFCollaborators.edit();assert.match(f.messages.at(-1),/inviti in attesa/);
  f.ctx.window.GFCollaborators.edit(3);f.node('collaboratorActive').checked=true;
  await f.ctx.window.GFCollaborators.save({preventDefault(){}});
  assert.equal(writes,0);assert.match(f.node('collaboratorError').textContent,/Limite di 2/);
  f.ctx.window.GFCollaborators.edit(1);
  await f.ctx.window.GFCollaborators.save({preventDefault(){}});
  assert.equal(writes,1,'Editing an already occupied seat is permitted at the cap');
});

test('existing automatic sources show their locked availability after downgrade while file imports stay usable',async()=>{
  const f=fixture();
  f.ctx.FormData=class FormData {};
  f.ctx.fetch=async()=>({ok:true,json:async()=>({fields:[],total:2,items:[
    {id:1,name:'API esistente',kind:'api',status:'active',has_credential:true},
    {id:2,name:'File manuale',kind:'file',status:'active'}
  ]})});
  vm.runInContext(fs.readFileSync('static/dashboard/js/order-sources.js','utf8'),f.ctx);
  await f.ctx.window.GFOrderSources.load();
  assert.equal(f.node('sourceMessage').textContent,'');
  assert.match(f.node('sourceList').innerHTML,/Business richiesto/);
  assert.doesNotMatch(f.node('sourceList').innerHTML,/Pronta a ricevere richieste autenticate/);
  assert.match(f.node('sourceList').innerHTML,/GFOrderImport.start\(2\)/);
});

test('plans page lists every capability with signature, photo and PDF as one entry',()=>{
  const f=fixture();
  const labels=plan=>f.run(`planPageFeatures('${plan}')`);
  assert.equal(labels('starter').filter(([included])=>included).length,2);
  assert.equal(labels('business').filter(([included])=>!included).map(([,label])=>label).join(),'Integrazione AI');
  assert.ok(labels('pro').every(([included])=>included));
  assert.ok(labels('pro').some(([,label])=>label==='Firma, foto e prova di consegna'));
  assert.ok(!labels('pro').some(([,label])=>/Pianificazione giri|Foto prova consegna/.test(label)));
  f.ctx.window.GF_PLANS.business.has_photo_proof=false;
  assert.equal(labels('business').find(([,label])=>label==='Firma, foto e prova di consegna')[0],false);
});
