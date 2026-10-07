const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 const nodes={};const node=id=>nodes[id]??={value:'',innerHTML:'',textContent:'',attributes:{},classList:{toggle(){}},setAttribute(k,v){this.attributes[k]=v}};
 const ctx=vm.createContext({document:{getElementById:node},vehiclesCache:[],esc:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')});
 const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
 vm.runInContext(core.slice(core.indexOf('const GF_FUEL_LABELS'),core.indexOf('function updateVehicleEnergyFieldsV895'))+'\n'+fs.readFileSync('static/dashboard/js/vehicles.js','utf8'),ctx);
 return {ctx,node,run:s=>vm.runInContext(s,ctx)};
}
test('fleet search normalizes plate spacing and combines with actual availability',()=>{
 const f=fixture();f.ctx.vehiclesCache=[{id:1,nome:'Furgone',targa:'GR 552 GG',stato:'Disponibile'},{id:2,nome:'Auto',modello:'Clio',stato:'In uso'},{id:3,nome:'Senza stato'}];
 f.node('fleetSearch').value='gr552gg';assert.equal(f.run('fleetFilteredVehicles()[0].id'),1);
 f.node('fleetStatusFilter').value='busy';assert.equal(f.run('fleetFilteredVehicles().length'),0);
 f.node('fleetSearch').value='';assert.equal(f.run('fleetFilteredVehicles()[0].id'),2);
 f.node('fleetStatusFilter').value='available';assert.equal(f.run('fleetFilteredVehicles().length'),1);
});
test('cards and table preserve energy units, escape names and do not fabricate vehicle type',()=>{
 const f=fixture();f.ctx.vehiclesCache=[{id:1,nome:'<Test>',alimentazione:'elettrico',consumo_kwh_100km:24.2,stato:'Disponibile'},{id:2,nome:'Metano',alimentazione:'metano',consumo_primario_100km:5}];
 f.run('renderFleetDirectory()');for(const id of ['fleetCards','vehiclesBody']){const html=f.node(id).innerHTML;assert.match(html,/&lt;Test>/);assert.match(html,/24.2 kWh\/100 km/);assert.match(html,/5 kg\/100 km/);assert.match(html,/Non specificato/);}
 f.run("setFleetView('table')");assert.equal(f.node('fleetTableButton').attributes['aria-pressed'],'true');
});
test('fleet photos reject unsafe URLs and plan warnings stay visible',()=>{
 const f=fixture();assert.doesNotMatch(f.run("fleetPhoto({photo_url:'javascript:alert(1)'})"),/<img/);
 assert.match(f.run("fleetPhoto({photo_url:'/static/photo.png',nome:'Mezzo'})"),/<img/);
 f.ctx.usage={over_limit:true,message:'Limite superato'};f.run('renderFleetPlanNotice(usage)');assert.equal(f.node('fleetPlanNotice').textContent,'Limite superato');
});
