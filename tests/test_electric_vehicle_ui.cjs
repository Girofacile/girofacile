const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function component(){
  const context=vm.createContext({window:{}});
  vm.runInContext(fs.readFileSync('static/dashboard/js/electric-vehicles.js','utf8'),context);
  return context.window.GiroFacileElectricVehicles;
}
function usage(overrides={}){
  return {standard_limit:10,electric_bonus:2,total_limit:12,standard_used:8,bonus_used:1,
    total_used:9,bonus_remaining:1,standard_remaining:2,can_add_electric:true,
    can_add_non_electric:true,plan_active:true,over_limit:false,...overrides};
}
test('shared vehicle summary uses server counts and distinguishes standard and bonus slots',()=>{
  const html=component().summaryHtml(usage({standard_used:4,non_electric_used:99}));
  assert.match(html,/Mezzi inclusi nel piano/);
  assert.match(html,/Bonus mobilità elettrica/);
  assert.match(html,/>4 <small>\/ 10 utilizzati/);
  assert.match(html,/>1 <small>\/ 2 utilizzati/);
  assert.match(html,/senza consumare gli slot mezzi standard/);
  assert.match(html,/utilizzano prima i bonus/);
  assert.match(html,/Totale mezzi: 9 \/ 12/);
  assert.match(component().summaryHtml(usage({electric_bonus:0,bonus_used:0})),/\/ 0 utilizzati/);
});
test('creation hint permits only canonical electric fuel to claim the available bonus',()=>{
  const ui=component();
  const limits=usage({standard_remaining:0,can_add_non_electric:false});
  assert.equal(ui.formHint(limits,'elettrico').tone,'positive');
  for(const fuel of ['gasolio','benzina','gpl','metano','ibrido_benzina','ibrido_diesel','ibrido_plugin_benzina','ibrido_plugin_diesel']){
    const hint=ui.formHint(limits,fuel);
    assert.equal(hint.tone,'warning',fuel);
    assert.match(hint.text,/1 slot bonus disponibile per un veicolo elettrico/);
  }
  assert.notEqual(ui.formHint(limits,'Elettrico').tone,'positive');
  assert.equal(ui.formHint(usage({bonus_remaining:0,can_add_electric:false}),'elettrico').tone,'warning');
});
test('downgrade and inactive subscription remain visible without promising unavailable bonus slots',()=>{
  const ui=component();
  const html=ui.summaryHtml(usage({over_limit:true,message:'Flotta oltre il limite <script>unsafe</script>'}));
  assert.match(html,/role="status"/);
  assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>/);
  assert.match(ui.formHint(usage(),'gasolio',{alimentazione:'elettrico'}).text,/controllo avviene al salvataggio/);
  assert.equal(ui.formHint(usage({plan_active:false}),'elettrico').tone,'warning');
  assert.equal(ui.formHint(null,'elettrico').tone,'neutral');
});
test('plan cards take configured bonus values from catalogue and expose a dedicated benefit',()=>{
  const context=vm.createContext({window:{GF_PLANS:{starter:{name:'Starter',price_eur:29,max_vehicles:3,max_drivers:3,
    max_customers:150,max_routes_per_month:100,max_deliveries_per_month:2000,max_deposits:1,electric_vehicle_bonus:7}}}});
  vm.runInContext(fs.readFileSync('static/dashboard/js/billing.js','utf8'),context);
  const plan=vm.runInContext("planFeatures('starter')",context);
  assert.equal(plan.electricBenefit,'⚡ +7 veicoli elettrici bonus');
  assert.ok(!plan.features.some(value=>value.includes('elettric')));
  assert.equal(component().planBenefit({electric_vehicle_bonus:1}),'⚡ +1 veicolo elettrico bonus');
  assert.equal(component().planBenefit({electric_vehicle_bonus:0}),'');
  const dashboard=fs.readFileSync('static/dashboard/js/core.js','utf8');
  assert.match(dashboard,/f.electricBenefit/);
  assert.match(dashboard,/"⚡ Veicoli elettrici bonus", "electric_vehicle_bonus"/);
  assert.match(fs.readFileSync('static/mobile/index.html','utf8'),/planBenefit\(p\)/);
});
function mobileFixture(fields){
  const source=fs.readFileSync('static/mobile/mobile.js','utf8');
  const block=source.slice(source.indexOf('const GF_MOBILE_FUEL_LABELS='),source.indexOf('// CRUD DEPOSITI'));
  const context=vm.createContext({mval:id=>fields[id]??'',mcheck:()=>false,
    esc:value=>String(value??'').replace(/"/g,'&quot;')});
  vm.runInContext(block,context);
  return code=>vm.runInContext(code,context);
}
test('mobile create and edit preserve electric, plug-in and methane fuel and energy units',()=>{
  const fields={fNome:'Test',fFuelType:'elettrico',fConsumo:'8.5',fConsumoKwh:'22.4',fTollClass:'3'};
  const run=mobileFixture(fields);
  let payload=run('mobileVehiclePayload()');
  assert.equal(payload.alimentazione,'elettrico');
  assert.equal(payload.consumo_primario_100km,0);
  assert.equal(payload.consumo_l_100km,0);
  assert.equal(payload.consumo_kwh_100km,22.4);
  assert.equal(payload.toll_class,'3');
  fields.fFuelType='ibrido_plugin_benzina';
  payload=run('mobileVehiclePayload()');
  assert.equal(payload.consumo_primario_100km,8.5);
  assert.equal(payload.consumo_kwh_100km,22.4);
  fields.fFuelType='metano';fields.fConsumo='0';
  payload=run('mobileVehiclePayload()');
  assert.equal(payload.consumo_primario_100km,0);
  assert.equal(payload.consumo_kwh_100km,0);
  const html=run("vehicleForm({alimentazione:'elettrico',consumo_kwh_100km:25,consumo_l_100km:0})");
  assert.match(html,/value="elettrico" selected/);
  assert.match(html,/kWh\/100 km/);
  assert.match(html,/id="fConsumoKwh"[^>]*value="25"/);
  assert.match(html,/id="mobileVehicleBonusHint"/);
  assert.match(run("vehicleForm({alimentazione:'metano'})"),/kg\/100 km/);
});
test('desktop and mobile load one presentation component and use authoritative usage endpoint',()=>{
  for(const path of ['static/dashboard/index.html','static/mobile/index.html']){
    const html=fs.readFileSync(path,'utf8');
    assert.match(html,/\/static\/dashboard\/js\/electric-vehicles.js/);
    assert.match(html,/\/static\/dashboard\/css\/electric-vehicles.css/);
    for(const [,script]of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(script);
  }
  for(const path of ['static/dashboard/js/core.js','static/mobile/mobile.js']){
    const source=fs.readFileSync(path,'utf8');
    new vm.Script(source,{filename:path});
    assert.match(source,/\/api\/vehicles\/usage/);
  }
  const css=fs.readFileSync('static/dashboard/css/electric-vehicles.css','utf8');
  assert.match(css,/@media\(max-width:600px\)/);
  assert.match(css,/grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css,/min-width:0/);
});
