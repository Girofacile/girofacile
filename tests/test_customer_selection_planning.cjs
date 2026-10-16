const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const customers=fs.readFileSync('static/dashboard/js/customers.js','utf8');
const controller=customers.slice(customers.indexOf('let customerPlanningTransferBusy=false;'),customers.indexOf('function clearCustomerSelection(){'));
function fixture(options={}){
  const valid={id:1,nome:'A',stato_geocodifica:'verificato',lat:0,lon:0};
  const context={
    window:{GFCompanyAccess:{can:()=>!options.denied},GFOrderPlanning:{flush:async()=>{context.flushes++;if(options.flushError)throw Error('Salvataggio non riuscito');if(options.pause)await options.pause;}}},
    customerDirectory:{busy:!!options.busy,selected:new Set(options.ids||[1,2]),all:[valid,{...valid,id:2,nome:'B'},...(options.invalid?[{...valid,id:3,stato_geocodifica:'da_verificare'}]:[])]},
    deliveries:options.existing?[{customer_id:99}]:[],customerDirectoryPlanning:false,
    flushes:0,clears:0,renders:0,gates:0,alerts:[],navigations:[],
    alert:m=>context.alerts.push(m),confirm:()=>!options.cancel,
    renderCustomerSelection:()=>{},
    customerIsPlannable:c=>!!c&&c.stato_geocodifica==='verificato'&&Number.isFinite(c.lat)&&Number.isFinite(c.lon),
    deliveryFromCustomer:c=>({customer_id:c.id,note:'preserved'}),
    showTab:name=>context.navigations.push(name),
    cxEl:()=>({classList:{contains:()=>!!options.blocked}}),
    clearRouteWorkspace:()=>{context.clears++;context.deliveries=[];},
    renderDeliveries:()=>context.renders++,
    updateRoutePlanningGateV68:()=>context.gates++
  };
  context.GFCompanyAccess=context.window.GFCompanyAccess;
  const run=new Function('context','with(context){'+controller+';return goCustomerPlanning;}')(context);
  return {context,run};
}
test('selected customers transfer once in selection order through the existing mapper',async()=>{
  const f=fixture({ids:[2,1,2]});await f.run();
  assert.deepEqual(f.context.deliveries,[{customer_id:2,note:'preserved'},{customer_id:1,note:'preserved'}]);
  assert.equal(f.context.flushes,1);assert.equal(f.context.clears,1);
  assert.equal(f.context.customerDirectoryPlanning,true);assert.equal(f.context.renders,1);assert.equal(f.context.gates,1);
});
for(const [name,options] of Object.entries({
  empty:{ids:[]},denied:{denied:true},busy:{busy:true},missing:{ids:[9]},
  unverified:{ids:[1,3],invalid:true},cancelled:{existing:true,cancel:true},
  navigationBlocked:{existing:true,blocked:true},saveFailed:{existing:true,flushError:true}
})){
  test('preserves workspace and selection when '+name,async()=>{
    const f=fixture(options),before=JSON.stringify(f.context.deliveries),ids=[...f.context.customerDirectory.selected];
    await f.run();
    assert.equal(JSON.stringify(f.context.deliveries),before);assert.equal(f.context.clears,0);
    assert.deepEqual([...f.context.customerDirectory.selected],ids);
  });
}
test('double click while saving does not transfer twice',async()=>{
  let release;const pause=new Promise(resolve=>release=resolve);
  const f=fixture({pause});const first=f.run();await f.run();release();await first;
  assert.equal(f.context.flushes,1);assert.equal(f.context.clears,1);
});
test('a failed save can be retried',async()=>{
  const f=fixture({flushError:true});await f.run();
  f.context.window.GFOrderPlanning.flush=async()=>{};
  await f.run();assert.equal(f.context.clears,1);
});
test('selection and primary action remain available without time windows; no planner sidebar entry',()=>{
  const html=fs.readFileSync('static/dashboard/index.html','utf8');
  const shell=fs.readFileSync('static/design-system/shell.js','utf8');
  assert.doesNotMatch(html, /data-tab="giro"/);
  assert.doesNotMatch(shell, /id:'giro',label:'Pianificazione'/);
  assert.match(html, /id="customersGoPlanning"/);
  assert.doesNotMatch(html, /id="customerBulkBar"[^>]*data-gf-feature/);
  assert.doesNotMatch(customers, /data-label="Seleziona" data-gf-feature/);
  assert.doesNotMatch(customers, /class="gf-check" data-gf-feature="time_windows"><input type="checkbox" class="cx-cb"/);
});
