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
 const title={textContent:''};
 const host={innerHTML:'',classList:{add(){},remove(){}},querySelector:()=>null};
 const body={appendChild(){}};
 const document={
  body,
  // "Pianifica giri" sta nella barra in alto, come le azioni delle altre pagine.
  getElementById(id){return id==='routePreviewResult'?page:id==='fleetTopbarActionsHost'?host:id==='workspacePageTitle'?title:null;},
  createElement(){return {set innerHTML(v){this.value=v;},get innerHTML(){return this.value;},
   querySelector(){return {onclick:null}},addEventListener(){},showModal(){},remove(){}};}
 };
 const sandbox={window:{},document,console,requestAnimationFrame(){},setTimeout(){}};
 sandbox.GFDriverBreaks=vm.runInNewContext(read('static/driver-schedule.js')+';window.GFDriverBreaks',{window:{}});
 vm.runInNewContext(read('static/format.js'),sandbox);
 vm.runInNewContext(read('static/dashboard/js/fleet-review.js'),sandbox);
 const plan={
  id:15,version:1,status:'preview',
  configuration:{
   consegne:[
    {cliente_nome:'Alimentari Rossi',indirizzo:'Via Roma 1',lat:40.8,lon:14.4},
    {cliente_nome:'Bar Bianchi',indirizzo:'Via Napoli 5',lat:40.9,lon:14.5}
   ],
   resources:[
    {vehicle_id:1,driver_id:1},
    {vehicle_id:2,driver_id:2}
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
 return {control:sandbox.window.GFFleetReview,page,host,title,params};
}
test('fleet review replica il modello senza sidebar ne dati fittizi',()=>{
 const {control,page,host,title,params}=preview();
 control.render(params);
 assert.equal(title.textContent,'Controlla la suddivisione');
 assert.match(page.innerHTML,/data-fleet-map role="region"/);
 assert.doesNotMatch(page.innerHTML,/Note sul calcolo|data-fleet-map-details|Mostra la mappa/);
 assert.doesNotMatch(page.innerHTML,/Controlli sulla suddivisione/);
 // Variante C: tabella di confronto dei giri, il giro scelto con mappa e fermate, "Da sistemare" a lato.
 assert.match(page.innerHTML,/Confronto dei giri/);
 assert.match(page.innerHTML,/Da sistemare/);
 assert.match(page.innerHTML,/data-fleet-select="1"/);
 assert.match(page.innerHTML,/Alimentari Rossi/);
 assert.doesNotMatch(page.innerHTML,/Bar Bianchi/);
 assert.match(page.innerHTML,/Furgone A/);
 assert.match(page.innerHTML,/Furgone B/);
 assert.match(host.innerHTML,/>Pianifica giri<\/button>/);
 assert.doesNotMatch(page.innerHTML,/<h1|data-fleet-back|Torna alla pianificazione/);
 assert.doesNotMatch(page.innerHTML,/Salva giri in bozza/);
 assert.doesNotMatch(page.innerHTML,/class="sidebar"|Supermercati Iorio|Peugeot 2008/);
});
test('modifiche manuali invalidano stime e disabilitano pianificazione',()=>{
 const {control,page,host,params}=preview();
 control.render({...params,assignment:[1,1],dirty:true,manualAdjusted:true});
 // Nessun avviso in alto: compare solo la barra in basso con "Ripianifica giri".
 assert.doesNotMatch(page.innerHTML,/Ricalcolo necessario|Suddivisione manuale/);
 assert.match(page.innerHTML,/Da ricalcolare/);
 assert.match(host.innerHTML,/data-fleet-plan disabled/);
 assert.match(page.innerHTML,/>Ripianifica giri<\/button>/);
 assert.match(page.innerHTML,/Annulla modifiche/);
});
test('un solo pulsante Pianifica giri usa una richiesta backend di programmazione',()=>{
 const js=read('static/dashboard/js/fleet-planning.js');
 assert.match(js,/onPlan:accept=>action\('plan',accept\)/);
 assert.doesNotMatch(js,/\/confirm/);
 assert.match(js,/\/program/);

 assert.match(js,/plan\.status==='saved'/);
 assert.match(js,/plan\.status==='programmed'/);
 assert.match(js,/changedAssignments/);
 assert.doesNotMatch(js,/data-action="confirm"|Salva giri in bozza/);
});
test('trasferimenti notificati e mappe solo sul contenuto, senza nuova sidebar',()=>{
 const review=read('static/dashboard/js/fleet-review.js');
 const css=read('static/dashboard/css/fleet-review.css');
 const html=read('static/dashboard/index.html');
 assert.match(review,/GiroFacile non può garantire la combinazione più efficiente/);
 // Spostamento con "Sposta in…" (anche da telefono) oltre al trascinamento.
 assert.match(review,/data-fleet-move-to/);
 assert.match(review,/data-fleet-lane/);
 assert.match(review,/loadRoadMapLibrary\(\)/);
 assert.match(review,/drawMap\(plan,assignment\);/);
 // La revisione usa i componenti del sistema; nel foglio dedicato restano solo i segnaposto della mappa.
 assert.match(review,/data-fleet-review/);
 assert.match(css,/\.fleet-review-pin/);
 assert.doesNotMatch(css,/\.sidebar\s*\{|\.brand\s*\{|\.topbar\s*\{/);
 assert.match(html,/fleet-review\.css\?v=[\w-]+/);
 assert.match(html,/fleet-review\.js\?v=[\w-]+/);
 assert.match(html,/\/static\/design-system\/design-system\.js\?v=[\w-]+/);
});

test('unassigned deliveries stay visible with address, reason and reassignment',()=>{
 const {control,page,params}=preview();
 params.plan.routes=params.plan.routes.slice(0,1);
 params.plan.unassigned=[{index:1,reason:'Giro 1: accesso ZTL richiesto.'}];
 control.render({...params,assignment:[0,null]});
 assert.match(page.innerHTML,/data-fleet-assign="1"[^>]*>Assegna al giro 1</);
 assert.match(page.innerHTML,/Via Napoli 5/);
 assert.match(page.innerHTML,/accesso ZTL richiesto/);
 assert.match(page.innerHTML,/data-fleet-drag draggable="true"/);
 // La fermata del giro 1 si può spostare nel giro 2 dal menu "Sposta in…".
 assert.match(page.innerHTML,/<select class="gf-select" data-fleet-move-to="0" aria-label="Sposta Alimentari Rossi in un altro giro">/);
 assert.match(page.innerHTML,/<option value="1">Giro 2 · /);
 assert.match(page.innerHTML,/data-fleet-accept-unassigned/);
});

test('tail lift warning follows the selected vehicle immediately after a manual move',()=>{
 const {control,page,params}=preview();
 params.plan.configuration.consegne[0].sponda=true;
 params.plan.resource_capabilities=[{has_tail_lift:false},{has_tail_lift:true}];
 control.render(params);
 assert.match(page.innerHTML,/data-fleet-warning="tail-lift" title="Questa consegna richiede la sponda, ma questo mezzo non la possiede/);
 control.render({...params,assignment:[1,1],dirty:true});
 assert.doesNotMatch(page.innerHTML,/data-fleet-warning="tail-lift"/);
});

test('ZTL warning follows the selected vehicle and coexists with the tail lift warning',()=>{
 const {control,page,params}=preview();
 Object.assign(params.plan.configuration.consegne[0],{ztl:true,sponda:true});
 params.plan.resource_capabilities=[{has_tail_lift:false,has_ztl_access:false},{has_tail_lift:true,has_ztl_access:true}];
 control.render(params);
 assert.match(page.innerHTML,/data-fleet-warning="ztl" title="Questa consegna è in ZTL, ma questo mezzo non è abilitato/);
 assert.match(page.innerHTML,/data-fleet-warning="tail-lift"/);
 control.render({...params,assignment:[1,1],dirty:true});
 assert.doesNotMatch(page.innerHTML,/data-fleet-warning="(ztl|tail-lift)"/);
});

test('approximate road estimates remain clear without a bottom notes panel',()=>{
 const {control,page,params}=preview();
 params.plan.routes[0].result.base_routing_provider='mixed';
 params.plan.warnings=['Routing stradale non disponibile per alcune tratte'];
 control.render(params);
 assert.match(page.innerHTML,/Stima approssimativa/);
 assert.doesNotMatch(page.innerHTML,/Note sul calcolo/);
});

test('un ricalcolo rifiutato mostra il motivo nella barra in basso',()=>{
 const {control,page,params}=preview();
 control.render({...params,assignment:[1,1],dirty:true,error:'Giro 2: Fasce orarie di consegna o turni e pause non rispettati.'});
 assert.match(page.innerHTML,/class="gf-savebar"[^>]*>.*data-fleet-error><b>Ripianificazione non riuscita<\/b> · Giro 2: Fasce orarie/);
 control.render({...params,assignment:[1,1],dirty:true});
 assert.doesNotMatch(page.innerHTML,/data-fleet-error/);
 assert.match(page.innerHTML,/<b>Fermate spostate<\/b>/);
});

test('ogni fermata si può togliere dai giri e finisce in Da sistemare',()=>{
 const {control,page,params}=preview();
 control.render(params);
 assert.match(page.innerHTML,/data-fleet-remove="0" title="Togli dai giri" aria-label="Togli Alimentari Rossi dai giri"/);
 control.render({...params,assignment:[null,1],dirty:true});
 assert.match(page.innerHTML,/Tolta dai giri: non verrà programmata\./);
 assert.match(page.innerHTML,/data-fleet-assign="0"/);
 assert.match(page.innerHTML,/data-fleet-accept-unassigned/);
});
