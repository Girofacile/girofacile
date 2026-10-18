const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function fixture(){
  const fields={};
  const ctx=vm.createContext({document:{getElementById:id=>fields[id]||null,addEventListener(){}},agentsFeatureEnabled:()=>true,customersCache:[],api:async()=>[]});
  vm.runInContext(fs.readFileSync('static/dashboard/js/customers.js','utf8'),ctx);
  vm.runInContext('renderCustomerDirectory=()=>{}',ctx);
  return {ctx,fields,run:code=>vm.runInContext(code,ctx)};
}
test('directory searches, combines optional filters and sorts codes numerically',()=>{
  const f=fixture();
  f.run(`customerDirectory.all=[{id:1,nome:'Hotel Èlite',codice_cliente:'C10',comune:'Roma',ztl:true,agent_id:3},{id:2,nome:'Bar',codice_cliente:'C2',comune:'Roma',ztl:false},{id:3,nome:'Market',comune:'Napoli',ztl:true}];`);
  f.fields.customerListSearch={value:'ÈLITE'};assert.equal(f.run('customerFilteredRows()[0].id'),1);
  f.fields.customerListSearch.value='';f.fields.customerFilterComune={value:'Roma'};f.fields.customerFilterZtl={value:'false'};assert.equal(f.run('customerFilteredRows()[0].id'),2);
  f.fields.customerFilterZtl.value='';f.fields.customerFilterAgent={value:'interno'};assert.equal(f.run('customerFilteredRows().length'),1);
  f.fields.customerFilterAgent.value='';f.run("setCustomerSort('codice_cliente:asc')");assert.equal(f.run('customerFilteredRows()[0].id'),2);
  f.run("toggleCustomerSort('codice_cliente')");assert.equal(f.run('customerFilteredRows()[0].id'),1);
});

test('customer KPI cards refresh after loading the directory',async()=>{
  const f=fixture();
  f.fields.customerMetricTotal={textContent:'—'};
  f.fields.customerMetricVerified={textContent:'—'};
  f.fields.customerMetricPending={textContent:'—'};
  f.fields.customerMetricActive={textContent:'—'};
  f.ctx.api=async()=>[
    {id:1,stato_geocodifica:'verificato'},
    {id:2,stato_geocodifica:'verificato'},
    {id:3,stato_geocodifica:'da_verificare'}
  ];
  await f.run('refreshCustomerDirectory()');
  assert.equal(f.fields.customerMetricTotal.textContent,3);
  assert.equal(f.fields.customerMetricVerified.textContent,2);
  assert.equal(f.fields.customerMetricPending.textContent,1);
  assert.equal(f.fields.customerMetricActive.textContent,3);
});

test('directory loads beyond one API batch and discards stale responses',async()=>{
  const f=fixture(),calls=[];
  f.ctx.api=async url=>{calls.push(url);return url.endsWith('offset=0')?Array.from({length:1000},(_,id)=>({id})): [{id:1001}];};
  await f.run('refreshCustomerDirectory()');assert.equal(f.ctx.customersCache.length,1001);assert.equal(calls.length,2);
  let resolve;f.ctx.api=()=>new Promise(r=>resolve=r);
  const old=f.run('refreshCustomerDirectory()');f.ctx.api=async()=>[{id:2000}];await f.run('refreshCustomerDirectory()');resolve([{id:3}]);await old;assert.equal(f.ctx.customersCache[0].id,2000);
});
test('customer selection supports planning and keeps unloading windows feature-gated',()=>{
  const html=fs.readFileSync('static/dashboard/index.html','utf8');
  const js=fs.readFileSync('static/dashboard/js/customers.js','utf8');
  const bulkBar=html.match(/<div\b[^>]*id="customerBulkBar"[^>]*>/)?.[0];
  assert.ok(bulkBar,'Shared customer selection bar');
  assert.doesNotMatch(bulkBar,/data-gf-feature=/);
  assert.match(html,/id="customerBulkMenu"[^>]*data-gf-feature="time_windows"/);
  assert.match(html,/id="customersGoPlanning"[^>]*onclick="goCustomerPlanning\(\)"/);
  assert.match(html,/id="customerDrawer"/);
  assert.match(js,/function clearCustomerSelection/);
  assert.match(js,/function applyCustomerBulkSlot/);
  assert.match(js,/data-cx-bulk="clear"/);
});

test('drawer saves keep every stored field and reset geocoding when the address changes',async()=>{
  const f=fixture();const calls=[];
  const inputs={cxName:{value:'Bar Nuovo'},cxAddress:{value:'Via Roma 2'},cxCode:{value:'C9'},cxCity:{value:'Napoli'},cxProv:{value:'na'},
    cxSlot1From:{value:'06:00'},cxSlot1To:{value:'12:00'},cxSecondSlot:{hidden:true},cxSlotError:{},cxAddressError:{},customerDrawer:{querySelector:()=>null,classList:{remove(){},add(){}},setAttribute(){}}};
  for(const key of ['cxName','cxAddress','cxCity'])inputs[key].classList={toggle(){}};
  Object.assign(f.fields,inputs);
  f.ctx.document.documentElement={dataset:{gfTimeWindows:'on'}};
  f.ctx.api=async(url,opts)=>{calls.push([url,opts]);return url.includes('limit=')?[]:{stato_geocodifica:'da_verificare'};};
  f.run(`customerDirectory.all=[{id:7,nome:'Bar',indirizzo:'Via Roma 1',comune:'Napoli',provincia:'NA',telefono:'081',tempo_scarico_min:15,ztl:true,lat:40.8,lon:14.2,stato_geocodifica:'verificato',scarico_pomeriggio_da:'14:00',scarico_pomeriggio_a:'18:00'}];
    customerDrawer.current=customerDirectory.all[0];customerDrawer.mode='edit';`);
  await f.run('saveCustomerDrawer()');
  const [url,opts]=calls[0];const body=JSON.parse(opts.body);
  assert.equal(url,'/api/customers/7');assert.equal(opts.method,'PUT');
  assert.equal(body.telefono,'081');assert.equal(body.tempo_scarico_min,15);assert.equal(body.ztl,true);
  assert.equal(body.provincia,'NA');assert.equal(body.lat,null);assert.equal(body.stato_geocodifica,null);
  assert.equal(body.scarico_mattina_da,'06:00');assert.equal(body.scarico_pomeriggio_da,null);
});

test('drawer rejects incomplete or inverted unloading windows before calling the API',async()=>{
  const f=fixture();let called=false;
  Object.assign(f.fields,{cxSlot1From:{value:'12:00'},cxSlot1To:{value:'09:00'},cxSecondSlot:{hidden:true},cxSlotError:{textContent:''}});
  f.ctx.document.documentElement={dataset:{}};
  f.ctx.api=async()=>{called=true;return {};};
  f.run(`customerDrawer.current={id:1,nome:'Bar',indirizzo:'Via 1'};customerDrawer.mode='view';`);
  await f.run('saveCustomerDrawer()');
  assert.equal(called,false);assert.match(f.fields.cxSlotError.textContent,/fine deve essere successivo/);
});


test('customer deletion is available only inside edit modal',()=>{
 const html=fs.readFileSync('static/dashboard/index.html','utf8');
 const js=fs.readFileSync('static/dashboard/js/customers.js','utf8');
 const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
 assert.doesNotMatch(html,/deleteAllCustomers\s*\(/);
 assert.doesNotMatch(html,/Elimina tutti i clienti/);
 assert.doesNotMatch(js,/customer-delete[^\n]*deleteCustomer\s*\(/);
 assert.match(html,/id="customerDeleteSection"[^>]*hidden/);
 assert.match(html,/id="deleteCustomerBtn"/);
 assert.match(core,/deleteCustomerFromModal/);
 assert.match(core,/Questa operazione è irreversibile/);
 assert.doesNotMatch(core,/async function deleteAllCustomers/);
});

test('customer avatars get a stable colour from the name across the six avatar tones',()=>{
  const f=fixture();
  const names=['Alimentari Oplonti','Bar Pompei Scavi','Cash & Carry Nocera','Gastronomia Pagani','Hotel Cava Centro','Hotel Porto del Miglio','Market Sarno Sud','Minimarket La Vesuviana'];
  const tones=names.map(n=>f.run(`cxAvatarTone(${JSON.stringify(n)})`));
  tones.forEach(t=>assert.ok(t>=1&&t<=6));
  assert.ok(new Set(tones).size>=4,'clienti diversi devono avere colori diversi');
  assert.equal(f.run(`cxAvatarTone('  alimentari OPLONTI ')`),tones[0]);
  assert.match(f.run(`cxAvatar({nome:'Bar Pompei Scavi'})`),new RegExp(`class="gf-avatar" data-tone="${tones[1]}"`));
  assert.doesNotMatch(f.run(`cxAvatar({})`),/data-tone/);
});
