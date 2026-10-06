const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function fixture(){
  const fields={};
  const ctx=vm.createContext({document:{getElementById:id=>fields[id]||null},agentsFeatureEnabled:()=>true,customersCache:[],api:async()=>[]});
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
test('customer directory has no row-selection controls',()=>{
  const html=fs.readFileSync('static/dashboard/index.html','utf8');
  const js=fs.readFileSync('static/dashboard/js/customers.js','utf8');
  assert.doesNotMatch(html,/customerSelectAll|customerSelection|customer-checkbox/);
  assert.doesNotMatch(js,/selectCustomerPage|selectDirectoryCustomer|clearCustomerSelection|type="checkbox"/);
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
