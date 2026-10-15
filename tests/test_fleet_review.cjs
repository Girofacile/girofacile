const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const read=path=>fs.readFileSync(path,'utf8');
function preview(){
 const page={
  innerHTML:'',classList:{add(){}},
  querySelector:()=>null,querySelectorAll:()=>[]
 };
 const body={appendChild(){}};
 const document={
  body,
  getElementById(id){return id==='routePreviewResult'?page:null;},
  createElement(){return {set innerHTML(v){this.value=v;},get innerHTML(){return this.value;},
   querySelector(){return {onclick:null}},addEventListener(){},showModal(){},remove(){}};}
 };
 const sandbox={window:{},document,console,requestAnimationFrame(){},setTimeout(){}};
 sandbox.GFDriverBreaks=vm.runInNewContext(read('static/driver-schedule.js')+';window.GFDriverBreaks',{window:{}});
 vm.runInNewContext(read('static/dashboard/js/fleet-review.js'),sandbox);
 const plan={
  id:15,version:1,status:'preview',
  configuration:{
   consegne:[
    {cliente_nome:'Alimentari Rossi',indirizzo:'Via Roma 1',lat:40.8,lon:14.4},
    {cliente_nome:'Bar Bianchi',indirizzo:'Via Napoli 5',lat:40.9,lon:14.5}
   ],
   resources:[
    {vehicle_id:1,driver_id:1,max_minutes:480},
    {vehicle_id:2,driver_id:2,max_minutes:480}
   ]
  },
  routes:[
   {resource:0,vehicle_name:'Furgone A',driver_name:'Mario Neri',stop_indexes:[0],
    fuel_cost:4.20,result:{total_km:21,total_min:55,return_time:'09:30',ordered:[{arrivo_stimato:'08:40'}]}},
   {resource:1,vehicle_name:'Furgone B',driver_name:'Sara Verdi',stop_indexes:[1],
    fuel_cost:5.30,result:{total_km:18,total_min:45,return_time:'09:15',ordered:[{arrivo_stimato:'08:50'}]}}
  ],unassigned:[],warnings:[]
 };
 const params={plan,assignment:[0,1],dirty:false,busy:false,manualAdjusted:false,permission:true,
  onMove(){},onUndo(){},onRecalc(){},onPlan(){},onBack(){}};
 return {control:sandbox.window.GFFleetReview,page,params};
}
test('fleet review replica il modello senza sidebar ne dati fittizi',()=>{
 const {control,page,params}=preview();
 control.render(params);
 assert.match(page.innerHTML,/Controlla la suddivisione/);
 assert.match(page.innerHTML,/Distribuzione sulla mappa/);
 assert.match(page.innerHTML,/Controlli sulla suddivisione/);
 assert.match(page.innerHTML,/Suddivisione per mezzo/);
 assert.match(page.innerHTML,/Alimentari Rossi/);
 assert.match(page.innerHTML,/Bar Bianchi/);
 assert.match(page.innerHTML,/Furgone A/);
 assert.match(page.innerHTML,/Furgone B/);
 assert.match(page.innerHTML,/>Pianifica giri<\/button>/);
 assert.doesNotMatch(page.innerHTML,/Salva giri in bozza/);
 assert.doesNotMatch(page.innerHTML,/class="sidebar"|Supermercati Iorio|Peugeot 2008/);
});
test('modifiche manuali invalidano stime e disabilitano pianificazione',()=>{
 const {control,page,params}=preview();
 control.render({...params,assignment:[1,1],dirty:true,manualAdjusted:true});
 assert.match(page.innerHTML,/Ricalcolo necessario/);
 assert.match(page.innerHTML,/Da ricalcolare/);
 assert.match(page.innerHTML,/data-fleet-plan disabled/);
 assert.match(page.innerHTML,/Ricalcola assegnazioni/);
 assert.match(page.innerHTML,/Annulla modifiche/);
});
test('un solo pulsante Pianifica giri usa conferma e programmazione backend sequenziale',()=>{
 const js=read('static/dashboard/js/fleet-planning.js');
 assert.match(js,/onPlan:accept=>action\('plan',accept\)/);
 assert.match(js,/\/confirm/);
 assert.match(js,/\/program/);
 assert.ok(js.indexOf("/confirm")<js.indexOf("/program"));
 assert.match(js,/if\(plan\.status==='saved'\)/);
 assert.match(js,/plan\.status==='programmed'/);
 assert.match(js,/changedAssignments/);
 assert.doesNotMatch(js,/data-action="confirm"|Salva giri in bozza/);
});
test('trasferimenti notificati e mappe solo sul contenuto, senza nuova sidebar',()=>{
 const review=read('static/dashboard/js/fleet-review.js');
 const css=read('static/dashboard/css/fleet-review.css');
 const html=read('static/dashboard/index.html');
 assert.match(review,/GiroFacile non può garantire la combinazione più efficiente/);
 assert.match(review,/data-fleet-move/);
 assert.match(review,/data-fleet-lane/);
 assert.match(review,/loadRoadMapLibrary\(\)/);
 assert.match(review,/Collegamenti indicativi, non stradali/);
 assert.match(css,/#routePreviewResult\.fleet-review-page/);
 assert.doesNotMatch(css,/\.sidebar\s*\{|\.brand\s*\{|\.topbar\s*\{/);
 assert.match(html,/fleet-review\.css\?v=[\w-]+/);
 assert.match(html,/fleet-review\.js\?v=[\w-]+/);
 assert.match(html,/\/static\/design-system\/design-system\.js\?v=[\w-]+/);
});
