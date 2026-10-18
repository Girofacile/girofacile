const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname,'..');
const read = name => fs.readFileSync(path.join(root,name),'utf8');

function harness(payload){
  const calls = {requests:[],maps:[],lines:[],markers:[],prefixes:[],tiles:[],viewport:null};
  const classList = () => {
    const values = new Set();
    return {add:x=>values.add(x),remove:x=>values.delete(x),
      contains:x=>values.has(x),toggle:(x,on)=>on?values.add(x):values.delete(x)};
  };
  const node = () => ({
    isConnected:true, children:[], classList:classList(),textContent:'',
    replaceChildren(...children){this.children=children;},
    appendChild(child){this.children.push(child);return child;},
    setAttribute(){},
  });
  const container = node();
  const subtitle = node();
  const hero = node();
  hero.querySelectorAll = () => [];
  const document = {
    getElementById(id){return id==='gfRefHeroWrap'?hero:
      id==='gfRefRouteSubtitle'?subtitle:null;},
    createElement(){return node();}
  };
  const fakeMap = () => ({
    removed:false,
    remove(){this.removed=true;},
    attributionControl:{setPrefix:prefix=>calls.prefixes.push(prefix)},
    fitBounds(bounds,options){calls.viewport=options;},invalidateSize(){},panTo(){},
  });
  const L = {
    divIcon:spec=>spec,
    map:() => {const map=fakeMap();calls.maps.push(map);return map;},
    tileLayer:(url,options) => {
      calls.tiles.push({url,options});
      return {addTo(){return this;}};
    },
    latLngBounds:() => ({extend(){},isValid(){return true;}}),
    polyline:(points) => {
      calls.lines.push(points);
      return {addTo(){return this;},getBounds(){return {};}};
    },
    marker:(point,options) => {
      const marker = {point,options,events:{},
        addTo(){return this;},bindPopup(){return this;},
        on(event,fn){this.events[event]=fn;return this;},
        getLatLng(){return point;},openPopup(){}
      };
      calls.markers.push(marker);
      return marker;
    }
  };
  const context = {
    window:{}, document, L,
    api:async url => {calls.requests.push(url);return payload;},
    decodeGooglePolylineV75:()=>[{lat:41.1,lng:12.4},{lat:41.2,lng:12.5}],
    loadRoadMapLibrary:async()=>true,
    requestAnimationFrame:()=>{},
    setTimeout:()=>1,clearTimeout:()=>{},
    console
  };
  vm.runInNewContext(read('static/dashboard/js/dashboard-real-map.js'),context);
  return {control:context.window.GiroFacileDashboardMap,calls,container,subtitle};
}

test('central map reuses saved OSRM road geometry, depot and real numbered stops',async()=>{
  const data = {
    depot:{lat:41.1,lon:12.4,name:'Deposito'},
    stops:[
      {id:91,lat:41.2,lon:12.5,name:'Cliente Uno',order:1},
      {id:92,lat:41.3,lon:12.6,name:'Cliente Due',order:2}
    ],
    road_polyline:{encoded_polylines:['encoded-osrm']}
  };
  const {control,calls,container,subtitle}=harness(data);
  await control.render(23,[{id:91,status:'completata'},{id:92,status:'mancata'}],container);
  assert.deepEqual(calls.requests,['/api/routes/23/map-data']);
  assert.equal(calls.maps.length,1);
  assert.equal(calls.lines.length,1);
  assert.equal(calls.markers.length,3);
  assert.deepEqual(calls.prefixes,['']);
  assert.match(calls.tiles[0].url,/tile\.openstreetmap\.org/);
  assert.match(calls.tiles[0].options.attribution,/OpenStreetMap contributors/);
  assert.equal(calls.viewport.padding[0],18);
  assert.equal(calls.viewport.maxZoom,13);
  assert.match(calls.markers[0].options.icon.html,/depot/);
  assert.match(calls.markers[1].options.icon.html,/is-done/);
  assert.match(calls.markers[2].options.icon.html,/is-miss/);
  assert.match(subtitle.textContent,/Percorso stradale pianificato/);
});

test('without road geometry the dashboard shows true geographic stops but never invents straight lines',async()=>{
  const data = {
    depot:{lat:41.1,lon:12.4,name:'Deposito'},
    stops:[{id:91,lat:41.2,lon:12.5,name:'Fermata'}],
    road_polyline:null
  };
  const {control,calls,container,subtitle}=harness(data);
  await control.render(5,[{id:91,status:'da_fare'}],container);
  assert.equal(calls.maps.length,1);
  assert.equal(calls.lines.length,0);
  assert.match(subtitle.textContent,/tracciato stradale non disponibile/);
  assert.ok(container.children.some(child=>/Tracciato stradale non disponibile/.test(child.textContent)));
});

test('missing coordinates show an honest empty state instead of a fabricated route',async()=>{
  const {control,calls,container}=harness({
    depot:{lat:null,lon:null},
    stops:[{id:91,lat:null,lon:null}],
    road_polyline:null
  });
  await control.render(4,[{id:91,status:'da_fare'}],container);
  assert.equal(calls.maps.length,0);
  assert.match(container.children[0].textContent,/Coordinate/);
});

test('switching routes disposes old map and does not change any sidebar styling',async()=>{
  const {control,calls,container}=harness({
    depot:{lat:41.1,lon:12.4},
    stops:[{id:91,lat:41.2,lon:12.5}],
    road_polyline:null
  });
  await control.render(1,[{id:91,status:'completata'}],container);
  const oldMap=calls.maps[0];
  await control.render(2,[{id:91,status:'completata'}],container);
  assert.ok(oldMap.removed);
  assert.equal(calls.maps.length,2);
  const core=read('static/dashboard/js/core.js');
  const html=read('static/dashboard/index.html');
  assert.match(core,/GiroFacileDashboardMap\?\.render\(routeId,rows,drawing\)/);
  assert.doesNotMatch(core,/Schema non geografico delle prime/);
  assert.match(html,/dashboard-real-map\.js\?v=[\w-]+/);
  assert.match(html,/\/static\/design-system\/design-system\.js\?v=[\w-]+/);
  const css=read('static/dashboard/css/dashboard-real-map.css');
  assert.match(css,/leaflet-control-attribution svg/);
  assert.match(css,/max-width:none!important/);
  assert.match(html,/dashboard-real-map\.css\?v=[\w-]+/);
});

test('dashboard map fills the available card height on desktop',()=>{
  const css=read('static/dashboard/css/dashboard-real-map.css');
  const html=read('static/dashboard/index.html');
  assert.match(css,/@media\s*\(min-width:\s*1025px\)[\s\S]*?\.gf-route-panel__map\s*\{[\s\S]*?display:\s*flex;[\s\S]*?flex-direction:\s*column;/);
  assert.match(css,/@media\s*\(min-width:\s*1025px\)[\s\S]*?\.gf-route-panel\s*\{\s*min-height:\s*28\.25rem;\s*\}/);
  assert.match(css,/\.gf-route-panel__canvas\s*\{\s*flex:\s*1 1 auto;\s*min-height:\s*var\(--gf-map-min-height\);\s*\}/);
  assert.match(html,/dashboard-real-map\.css\?v=gf_dashboard_start_20261018/);
});
