const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const read=file=>fs.readFileSync(path.join(root,file),'utf8');

function harness(){
  const selectedRoute={
    id:19,nome:'Giro aziendale',status:'in_corso',
    driver_name:'Autista Verificato',vehicle_name:'Furgone Uno',
    totale_km:42,totale_minuti:90,costo_carburante:12.3,
    rientro_stimato_aggiornato:'17:45',toll_estimated_eur:null,
    consegne:[
      {id:4,cliente_nome:'Cliente reale',indirizzo:'Via delle Rose 1',delivery_status:'completata',ordine:1,arrivo_stimato:'09:00'},
      {id:5,cliente_nome:'Cliente successivo',indirizzo:'Via Roma 2',delivery_status:'in_attesa',ordine:2,arrivo_stimato:'10:00'},
      {id:6,cliente_nome:'Cliente assente',indirizzo:'Via Napoli 3',delivery_status:'mancata',ordine:3,arrivo_stimato:'11:00'}
    ]
  };
  const picker={innerHTML:''};
  const count={textContent:''};
  const page={
    innerHTML:'',children:[],
    querySelector(selector){
      if(selector==='.gf-ip-picker')return picker;
      if(selector==='.gf-ip-count')return count;
      if(selector==='.gf-ip-outcome')return {value:'all'};
      if(selector==='.gf-ip-map-badge')return {className:'',innerHTML:''};
      if(selector==='.gf-ip-map-gps')return {textContent:''};
      if(selector==='[data-ip-action="follow"]')return {disabled:true,setAttribute(){}};
      if(selector==='.gf-ip-map-canvas')return {isConnected:false,textContent:'',replaceChildren(){}};
      return null;
    },
    querySelectorAll(){return [];}
  };
  const context={
    window:{},
    document:{
      getElementById(id){return id==='dashboardInProgressPage'?page:
        id==='tab-dashboard-in-progress'?{classList:{contains:()=>false}}:null;},
      addEventListener(){},
    },
    api:async()=>({state:'unavailable'}),
    loadRoadMapLibrary:async()=>true,
    decodeGooglePolylineV75:()=>[],
    gfRouteEnergyMetric:()=>({electric:false}),
    gfPlannedArrivalDates:()=>[null,null,null],
    gfPlannedArrival:d=>d.arrivo_stimato,
    gfRealArrival:()=>'',gfRealArrivalDate:()=>null,gfDeltaBadge:()=>'<span>—</span>',
    deliverySignatureAction:()=>'<button>Firma</button>',
    trackingButton:()=>'<button>Tracking cliente</button>',
    setInterval:()=>1,clearInterval(){},
    setTimeout:()=>0,requestAnimationFrame(){},
    console:{warn(){}}
  };
  context.GFDriverBreaks=vm.runInNewContext(read('static/driver-schedule.js')+';window.GFDriverBreaks',{window:{}});
  vm.runInNewContext(read('static/dashboard/js/in-progress-reference.js'),context);
  return {page,picker,count,route:selectedRoute,controller:context.window.GFInProgressReference};
}

test('nuovo layout giri in corso mantiene i dati reali e le azioni operative',()=>{
  const {page,picker,count,route,controller}=harness();
  controller.render([route],route);
  assert.match(page.innerHTML,/Giri attivi/);
  assert.match(page.innerHTML,/Indicatori del giro/);
  assert.match(page.innerHTML,/Fermate del giro/);
  assert.match(page.innerHTML,/Cliente reale/);
  assert.match(page.innerHTML,/Cliente successivo/);
  assert.match(page.innerHTML,/Cliente assente/);
  assert.match(page.innerHTML,/Tracking cliente/);
  assert.match(page.innerHTML,/Firma/);
  assert.match(page.innerHTML,/Chat autista/);
  assert.match(picker.innerHTML,/Autista Verificato/);
  assert.match(picker.innerHTML,/Furgone Uno/);
  assert.equal(count.textContent,'1 giro attivo');
  assert.doesNotMatch(page.innerHTML,/Alessandro Paglietta|Supermercati Iorio|GIRI=/);
});

test('mappa usa soltanto gli endpoint reali e non interpola un GPS fittizio',()=>{
  const js=read('static/dashboard/js/in-progress-reference.js');
  assert.match(js,/\/map-data/);
  assert.match(js,/\/position/);
  assert.match(js,/road_polyline/);
  assert.match(js,/state\.gps/);
  assert.doesNotMatch(js,/Math\.random|setInterval\(function\(\)\s*\{\s*GIRI/);
  assert.match(js,/loadRoadMapLibrary\(\)/);
  assert.match(js,/setPrefix\(''\)/);
  assert.match(js,/OpenStreetMap contributors/);
});

test('sidebar e login esclusi dal redesign di Giri in corso',()=>{
  const css=read('static/dashboard/css/in-progress-reference.css');
  const html=read('static/dashboard/index.html');
  const navigation=read('static/dashboard/js/navigation.js');
  const core=read('static/dashboard/js/core.js');
  assert.match(css,/#app #tab-dashboard-in-progress/);
  assert.doesNotMatch(css,/\.sidebar\s*\{|\.brand\s*\{|\.login-side\s*\{/);
  assert.match(html,/\/static\/design-system\/design-system\.js\?v=[\w-]+/);
  assert.match(html,/in-progress-reference\.css\?v=[\w-]+/);
  assert.match(html,/in-progress-reference\.js\?v=[\w-]+/);
  assert.match(core,/GFInProgressReference\?\.render/);
  assert.match(navigation,/GFInProgressReference\?\.suspend/);
  assert.match(navigation,/"dashboard-in-progress":\s*\{\s*title: "Giri in corso"/);
});

test('nessun giro attivo mantiene lo stato vuoto e l’azione per pianificare',()=>{
  const {page,controller}=harness();
  controller.render([],null);
  assert.match(page.innerHTML,/Nessun giro in corso/);
  assert.match(page.innerHTML,/Pianifica un giro/);
});
