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
test('directory loads beyond one API batch and discards stale responses',async()=>{
  const f=fixture(),calls=[];
  f.ctx.api=async url=>{calls.push(url);return url.endsWith('offset=0')?Array.from({length:1000},(_,id)=>({id})): [{id:1001}];};
  await f.run('refreshCustomerDirectory()');assert.equal(f.ctx.customersCache.length,1001);assert.equal(calls.length,2);
  let resolve;f.ctx.api=()=>new Promise(r=>resolve=r);
  const old=f.run('refreshCustomerDirectory()');f.ctx.api=async()=>[{id:2000}];await f.run('refreshCustomerDirectory()');resolve([{id:3}]);await old;assert.equal(f.ctx.customersCache[0].id,2000);
});
test('page selection affects only visible rows and refresh removes deleted selections',async()=>{
  const f=fixture();f.run('customerDirectory.rows=Array.from({length:12},(_,id)=>({id}));customerDirectory.page=2;selectCustomerPage(true)');
  assert.equal(f.run('customerDirectory.selected.size'),4);assert.equal(f.run('customerDirectory.selected.has(0)'),false);
  f.ctx.api=async()=>[{id:10}];await f.run('refreshCustomerDirectory()');assert.equal(f.run('customerDirectory.selected.size'),1);
});
