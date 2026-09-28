const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function planningFixture() {
  const fields={routeName:'',routeDate:'2026-09-29',routeStart:'',routeDeposit:'1',routeVehicle:'',routeDriver:'',fuelPrice:'1.75',electricityPrice:'0.30',returnDepot:'true'};
  const nodes=new Map();
  const state={focused:null,opened:0};
  const document={getElementById(id){
    if(!nodes.has(id)) {
      const classes=new Set(['hidden']);
      nodes.set(id,{textContent:'',innerHTML:'',dataset:{},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c)},focus(){state.focused=id;},scrollIntoView(){},addEventListener(){}});
    }
    return nodes.get(id);
  }};
  const context=vm.createContext({document,val:id=>fields[id]||'',routeDateIsValid:()=>fields.routeDate>='2026-09-29',vehiclesCache:[{id:1,alimentazione:'gasolio'},{id:2,alimentazione:'elettrico'},{id:3,alimentazione:'ibrido_plugin_benzina'}],loadCustomerPicker:()=>state.opened++,alert:()=>{},updateRouteEnergyPricingV895:()=>{}});
  const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
  vm.runInContext('let customerPlanningStepOpenedV68=false;'+core.slice(core.indexOf('function routePlanningMissingFieldsV68(){'),core.indexOf('function fmtEuro(')),context);
  return {fields,state,node:id=>document.getElementById(id),run:code=>vm.runInContext(code,context)};
}

test('completion action focuses missing details and never opens customers prematurely',()=>{
  const f=planningFixture();
  f.run('updateRoutePlanningGateV68();advanceRoutePlanning()');
  assert.equal(f.state.focused,'routeStart');
  assert.equal(f.state.opened,0);
  assert.equal(f.node('planStepStatus1').textContent,'Quasi completato');
  Object.assign(f.fields,{routeStart:'08:00',routeVehicle:'1',routeDriver:'1'});
  f.run('advanceRoutePlanning()');
  assert.equal(f.state.opened,1);
  assert.equal(f.node('customerPlanningStep').classList.contains('hidden'),false);
  assert.match(f.node('planningChecklist').innerHTML,/Nome automatico/);
  f.fields.routeDriver='';
  f.run('updateRoutePlanningGateV68()');
  assert.equal(f.node('customerPlanningStep').classList.contains('hidden'),true);
  assert.equal(f.node('deliveryWorkbenchStep').classList.contains('hidden'),true);
});

test('energy requirements remain correct for diesel, electric and plug-in vehicles',()=>{
  const f=planningFixture();
  Object.assign(f.fields,{routeStart:'08:00',routeVehicle:'1',routeDriver:'1',fuelPrice:'0'});
  f.run('updateRoutePlanningGateV68();advanceRoutePlanning()');
  assert.equal(f.state.focused,'fuelPrice');
  assert.match(f.node('planningChecklist').innerHTML,/Carburante/);
  f.fields.routeVehicle='2';
  f.run('updateRoutePlanningGateV68()');
  assert.equal(f.node('planStepStatus2').textContent,'Completato');
  f.fields.electricityPrice='0';
  f.run('updateRoutePlanningGateV68();advanceRoutePlanning()');
  assert.equal(f.state.focused,'electricityPrice');
  assert.match(f.node('planningChecklist').innerHTML,/Energia/);
  Object.assign(f.fields,{routeVehicle:'3',fuelPrice:'1.75'});
  assert.equal(f.run('routePlanningDetailsCompleteV68()'),false);
  f.fields.electricityPrice='0.30';
  assert.equal(f.run('routePlanningDetailsCompleteV68()'),true);
});

test('invalid dates and missing depot are reflected in completion feedback',()=>{
  const f=planningFixture();
  Object.assign(f.fields,{routeDate:'2026-09-28',routeStart:'08:00',routeDeposit:'',routeVehicle:'1',routeDriver:'1'});
  f.run('updateRoutePlanningGateV68();advanceRoutePlanning()');
  assert.equal(f.state.focused,'routeDate');
  assert.match(f.node('planningChecklist').innerHTML,/Deposito/);
  assert.equal(f.node('planStepStatus2').textContent,'Da completare');
  assert.equal(f.state.opened,0);
});
