const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
const source=core.slice(core.indexOf('function validateRouteCalculation(){'),core.indexOf('async function optimizeRoute(){'));
function validate(missing, fleet=false, stops=[{}]){
  const node={dataset:{},scrollIntoView(){},focus(){this.focused=true;}};
  const context={document:{getElementById:()=>node},deliveries:stops,routePlanningMissingFieldsV68:()=>missing,GFFleetPlanning:{active:()=>fleet}};
  const valid=vm.runInNewContext(source+';validateRouteCalculation()',context);
  return {valid,node};
}
test('calculation names all missing fields and focuses the error',()=>{
  const {valid,node}=validate(['mezzo','autista']);
  assert.equal(valid,false);
  assert.match(node.textContent,/il mezzo, l’autista/);
  assert.equal(node.hidden,false);
  assert.equal(node.focused,true);
});
test('fleet validation explains that each route needs different resources',()=>{
  const {valid,node}=validate(['mezzo','autista'],true);
  assert.equal(valid,false);
  assert.match(node.textContent,/un mezzo diverso per ogni giro, un autista diverso per ogni giro/);
});
test('invalid date, energy, schedule and empty selection are actionable',()=>{
  for(const field of ['data','prezzo carburante','prezzo energia','turno e pause autista']){
    const {valid,node}=validate([field]);assert.equal(valid,false);assert.match(node.textContent,/inserisci o correggi/);
  }
  assert.match(validate([],false,[]).node.textContent,/seleziona almeno un ordine o un cliente/);
});
test('valid configuration clears the error and permits calculation',()=>{
  const {valid,node}=validate([]);assert.equal(valid,true);assert.equal(node.hidden,true);assert.equal(node.textContent,'');
});
