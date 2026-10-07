const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function fixture(){
  const nodes={}, requests=[];
  const node=id=>nodes[id]??=( {value:'',dataset:{},classList:{add(){}},focus(){}} );
  const noop=()=>{};
  const ctx=vm.createContext({document:{getElementById:node},
    val:id=>node(id).value,set:(id,v)=>{node(id).value=String(v??'');},
    vehiclesCache:[{id:1,nome:'Peugeot',targa:'AB123CD',lookup_provider:'openapi',capacita_colli:100}],
    clearVehicleLookupHighlightsV8966:noop,markVehicleLookupResultV8966:noop,
    updateVehicleEnergyFieldsV895:noop,clearFileInput:noop,setImagePreview:noop,
    boolVal:()=>false,withButtonLoading:(_id,_label,fn)=>fn(),toast:noop,alert:noop,
    loadVehicles:async()=>{},loadDashboardHome:async()=>{},
    api:async(path,options)=>{requests.push({path,options});return ctx.result;}});
  const source=fs.readFileSync('static/dashboard/js/core.js','utf8');
  vm.runInContext(source.slice(source.indexOf('function normalizeVehiclePlateInputV896('),source.indexOf('async function deleteVehicle(')),ctx);
  return {ctx,node,requests};
}

test('editing capacity does not submit a new lookup receipt',async()=>{
  const f=fixture();f.ctx.editVehicle(1);f.node('vColli').value='150';
  await f.ctx.saveVehicle();
  const payload=JSON.parse(f.requests[0].options.body);
  assert.equal(payload.capacita_colli,150);
  assert.equal(payload.lookup_provider,'openapi');
  assert.equal(payload.lookup_at,null);assert.equal(payload.lookup_token,null);
});

test('successful lookup passes server timestamp and receipt only for that plate',async()=>{
  const f=fixture();f.ctx.editVehicle(1);
  f.ctx.result={targa:'AB123CD',provider:'openapi',lookup_at:'2026-10-07T09:00:00',lookup_token:'receipt'};
  await f.ctx.lookupVehiclePlateV896();await f.ctx.saveVehicle();
  const payload=JSON.parse(f.requests.at(-1).options.body);
  assert.equal(payload.lookup_at,f.ctx.result.lookup_at);assert.equal(payload.lookup_token,'receipt');
  assert.equal(f.node('vTarga').dataset.lookupToken,'');
  f.ctx.editVehicle(1);await f.ctx.lookupVehiclePlateV896();
  f.node('vTarga').value='EF456GH';await f.ctx.saveVehicle();
  const changed=JSON.parse(f.requests.at(-1).options.body);
  assert.equal(changed.lookup_token,null);assert.equal(changed.lookup_at,null);
});

test('late lookup response does not overwrite a changed plate',async()=>{
  const f=fixture();f.ctx.editVehicle(1);let resolve;
  f.ctx.api=()=>new Promise(r=>{resolve=r;});
  const lookup=f.ctx.lookupVehiclePlateV896();f.node('vTarga').value='EF456GH';
  resolve({targa:'AB123CD',provider:'openapi',lookup_token:'receipt'});await lookup;
  assert.equal(f.node('vTarga').value,'EF456GH');assert.equal(f.node('vTarga').dataset.lookupToken,'');
});
