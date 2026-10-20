const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const read=file=>fs.readFileSync(path.join(root,file),'utf8');

function harness(){
  const handlers={};
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
    contains:()=>true,
    querySelector(selector){
      if(selector==='[data-ip-picker]')return picker;
      if(selector==='[data-ip-count]')return count;
      if(selector==='[data-ip-outcome-filter]')return {value:'all'};
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
      addEventListener(type,handler){handlers[type]=handler;},
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
  vm.runInNewContext(read('static/format.js'),context);
  vm.runInNewContext(read('static/dashboard/js/in-progress-reference.js'),context);
  return {page,picker,count,route:selectedRoute,controller:context.window.GFInProgressReference,context,handlers};
}

test('annullamento usa il giro selezionato e aggiorna elenco solo dopo il successo',async()=>{
  const {page,route,controller,context,handlers}=harness();
  controller.render([route],route);
  assert.match(page.innerHTML,/data-ip-action="cancel">Annulla giro/);
  const calls=[];
  context.confirm=()=>false;
  context.api=async(...args)=>{calls.push(args);};
  context.toast=()=>{};
  context.loadDashboardInProgressPage=async()=>{calls.push(['reload']);};
  const button={dataset:{ipAction:'cancel'},disabled:false};
  const event={target:{closest:selector=>selector==='[data-ip-action]'?button:null}};
  await handlers.click(event);
  assert.equal(calls.length,0);
  context.confirm=()=>true;
  await handlers.click(event);
  assert.equal(calls[0][0],'/api/routes/19/cancel');
  assert.equal(calls[0][1].method,'POST');
  assert.equal(calls[1][0],'reload');
  assert.equal(button.disabled,false);
  calls.length=0;
  context.api=async()=>{throw new Error('Accesso negato');};
  let message;
  context.toast=value=>{message=value;};
  await handlers.click(event);
  assert.equal(message,'Accesso negato');
  assert.equal(calls.length,0);
  assert.equal(button.disabled,false);
});

test('autista vede il giro in corso vecchio anche con oltre tre giri recenti',()=>{
  const html=read('static/driver/index.html');
  const source=html.slice(html.indexOf('function renderRoutes()'),html.indexOf('function renderRouteCard('));
  const box={innerHTML:''};
  const context={document:{getElementById:()=>box},Date,
    allRoutes:[...Array.from({length:5},(_,i)=>({id:i,data_giro:'2020-01-02',status:'completato'})),
      {id:99,data_giro:'2020-01-01',status:'in_corso'}],
    renderRouteCard:r=>'[route:'+r.id+']'};
  vm.runInNewContext(source+';renderRoutes()',context);
  assert.match(box.innerHTML,/Giri in corso e programmati/);
  assert.equal(box.innerHTML.split('[route:99]').length-1,1);
  assert.ok(box.innerHTML.indexOf('[route:99]')<box.innerHTML.indexOf('Recenti'));
});

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

function gpsHarness(){
  const source=read('static/dashboard/js/in-progress-reference.js');
  const start=source.indexOf('  function drawGPS(){');
  const end=source.indexOf('  async function drawMap(',start);
  assert.ok(start>=0&&end>start,'GPS rendering function');
  const map={layers:new Set(),panTo(){}};
  const state={id:1,gps:new Map(),map,vehicle:null,circle:null,follow:false};
  const follow={disabled:true,attributes:{},setAttribute(name,value){this.attributes[name]=value;}};
  const layer=(kind,coord)=>{
    const item={kind,coord,removed:false,stale:false,
      addTo(target){target.layers.add(this);return this;},
      remove(){map.layers.delete(this);this.removed=true;return this;},
      getElement(){return {classList:{toggle:(_,on)=>{this.stale=on;}}};},
      setLatLng(next){this.coord=next;},
      setRadius(radius){this.radius=radius;}
    };
    return item;
  };
  const context={state,
    root:()=>({querySelector:selector=>selector==='[data-ip-action="follow"]'?follow:null}),
    n:value=>Number(value)||0,icon:()=>'<svg></svg>',
    L:{divIcon:options=>options,marker:coord=>layer('vehicle',coord),circle:coord=>layer('accuracy',coord)}
  };
  vm.runInNewContext(source.slice(start,end)+';this.drawGPS=drawGPS;',context);
  return {state,map,follow,update(value){state.gps.set(1,value);context.drawGPS();}};
}

test('GPS unavailability removes the old marker and accuracy circle and recovers without removing the map',()=>{
  const f=gpsHarness(),position={latitude:45.46,longitude:9.19,accuracy:20};
  f.update({state:'fresh',position});
  const oldMarker=f.state.vehicle,oldCircle=f.state.circle;
  assert.equal(f.map.layers.size,2);
  assert.equal(f.follow.disabled,false);
  f.state.follow=true;
  f.update({state:'unavailable',position:null});
  assert.equal(oldMarker.removed,true);assert.equal(oldCircle.removed,true);
  assert.equal(f.state.vehicle,null);assert.equal(f.state.circle,null);
  assert.equal(f.state.map,f.map);assert.equal(f.map.layers.size,0);
  assert.equal(f.follow.disabled,true);assert.equal(f.follow.attributes['aria-pressed'],'false');
  f.update({state:'fresh',position});
  assert.equal(f.map.layers.size,2);assert.equal(f.follow.disabled,false);
  assert.notEqual(f.state.vehicle,oldMarker);
});

test('stale GPS keeps the last known marker while invalid coordinates remove it',()=>{
  const f=gpsHarness(),position={latitude:45.46,longitude:9.19,accuracy:20};
  f.update({state:'fresh',position});
  const marker=f.state.vehicle;
  f.update({state:'stale',position});
  assert.equal(f.state.vehicle,marker);assert.equal(marker.stale,true);
  assert.equal(f.map.layers.size,2);assert.equal(f.follow.disabled,false);
  for(const invalid of [
    {latitude:null,longitude:9.19},{latitude:45.46,longitude:null},
    {latitude:91,longitude:9.19},{latitude:45.46,longitude:181},
    {latitude:NaN,longitude:9.19},{latitude:45.46,longitude:Infinity}
  ]){
    f.update({state:'fresh',position});
    f.update({state:'unavailable',position:invalid});
    assert.equal(f.map.layers.size,0);assert.equal(f.follow.disabled,true);
  }
});

test('zero-valued GPS coordinates remain valid',()=>{
  const f=gpsHarness();
  f.update({state:'fresh',position:{latitude:0,longitude:0,accuracy:0}});
  assert.equal(f.map.layers.size,2);assert.equal(f.follow.disabled,false);
  assert.equal(f.state.vehicle.coord[0],0);assert.equal(f.state.vehicle.coord[1],0);
});
