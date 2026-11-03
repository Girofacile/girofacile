const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/dashboard/js/core.js','utf8');
function extract(name,next){return source.slice(source.indexOf('function '+name+'('),source.indexOf('function '+next+'('));}
test('payload preserves explicit manual, automatic and unspecified unloading provenance',()=>{
  const ctx={};vm.createContext(ctx);
  vm.runInContext(extract('cleanDeliveryForPayload','routePayloadFromResult'),ctx);
  for(const flag of [false,true,null,undefined]){
    const row=ctx.cleanDeliveryForPayload({tempo_scarico_min:10,tempo_scarico_auto:flag,colli:40});
    assert.equal(row.tempo_scarico_min,10);
    assert.equal(row.tempo_scarico_auto,flag??null);
  }
});
test('unloading entered in the stop form is explicitly manual even at ten minutes',()=>{
  const values={dCliente:'Cliente',dIndirizzo:'Via Prova',dScarico:'10',dColli:'40'};
  const ctx={selectedCustomer:null,val:key=>values[key]||'',boolVal:()=>false,alert:()=>assert.fail('unexpected alert')};
  vm.createContext(ctx);vm.runInContext(extract('deliveryPayloadFromForm','addDelivery'),ctx);
  const row=ctx.deliveryPayloadFromForm();
  assert.equal(row.tempo_scarico_min,10);assert.equal(row.tempo_scarico_auto,false);
});
