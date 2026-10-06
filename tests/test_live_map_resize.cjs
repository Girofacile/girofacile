const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');

test('live map resize preserves the map and follows subsequent GPS updates',async()=>{
  const nodes=new Map();
  const host={isConnected:true,dataset:{},getClientRects:()=>[{}],querySelector:key=>{
    if(!nodes.has(key))nodes.set(key,{});return nodes.get(key);
  }};
  let created=0,invalidations=0,tick,point=[40.7,14.4],opacity;
  const marker={addTo(){return this;},setLatLng(value){point=value;},getLatLng(){return point;},setOpacity(value){opacity=value;}};
  const map={setView(){return this;},invalidateSize(){invalidations++;},panTo(value){assert.deepEqual(value,point);},getBounds:()=>({contains:()=>false}),remove(){},removeLayer(){}};
  let data={route_name:'Giro',vehicle_name:'Mezzo',next_stop:'Cliente',progress:10,route_status:'in_corso',state:'fresh',position:{latitude:40.7,longitude:14.4,accuracy:10,captured_at:'2026-10-06T12:00:00Z'}};
  const context=vm.createContext({window:{},document:{hidden:false,getElementById:()=>host,addEventListener(){}},
    setTimeout(fn){tick=fn;},clearTimeout(){},AbortSignal:{timeout(){}},
    fetch:async()=>({ok:true,json:async()=>data}),loadRoadMapLibrary:async()=>{},
    L:{map(){created++;return map;},tileLayer:()=>({addTo(){}}),divIcon:x=>x,marker:()=>marker}});
  vm.runInContext(fs.readFileSync('static/dashboard/js/live-gps.js','utf8'),context);
  const api=context.window.GiroFacileLiveMap;
  api.mount(1);await new Promise(resolve=>setImmediate(resolve));
  assert.equal(created,1);const before=invalidations;
  api.resize();assert.equal(created,1);assert.equal(invalidations,before+1);
  data={...data,state:'stale',position:{...data.position,latitude:40.8}};
  await tick();assert.equal(point[0],40.8);assert.equal(opacity,.45);assert.equal(created,1);
  data={...data,position:null,state:'unavailable'};await tick();api.resize();
  assert.equal(nodes.get('[data-gps-empty]').hidden,false);
});
