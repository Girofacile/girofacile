const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {create,isRetryable,overlay}=require('../static/driver-outbox.js');

function memoryStorage(){
  const data=new Map();
  return {getItem:k=>data.has(k)?data.get(k):null,setItem:(k,v)=>data.set(k,String(v)),data};
}
const offline=()=>Object.assign(new Error('Connessione assente.'),{offline:true});
const http=(status,message='errore')=>Object.assign(new Error(message),{status});

test('outcomes survive a reload of the page while offline',()=>{
  const storage=memoryStorage();
  const first=create({storage,key:'k',send:async()=>{throw offline();}});
  assert.equal(first.add({kind:'complete',url:'/c',body:{tempo_scarico:10},routeId:7,deliveryId:3}),true);
  const reloaded=create({storage,key:'k',send:async()=>{}});
  assert.equal(reloaded.count(),1);
  assert.equal(reloaded.pending(7)[0].deliveryId,3);
  assert.equal(reloaded.pending(8).length,0);
});

test('flush sends in order and stops at the first network failure',async()=>{
  const sent=[];let online=false;
  const box=create({storage:memoryStorage(),key:'k',send:async item=>{if(!online)throw offline();sent.push(item.deliveryId);}});
  box.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1});
  box.add({kind:'missed',url:'/2',body:{},routeId:1,deliveryId:2});
  assert.deepEqual(await box.flush(),[]);
  assert.equal(box.count(),2);
  online=true;
  assert.deepEqual(await box.flush(),[]);
  assert.deepEqual(sent,[1,2]);
  assert.equal(box.count(),0);
});

test('a rejected outcome is dropped and reported, temporary errors are kept',async()=>{
  const box=create({storage:memoryStorage(),key:'k',send:async item=>{
    if(item.deliveryId===1)throw http(409,'La consegna o il giro è già chiuso');
  }});
  box.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1,label:'Bar Roma'});
  box.add({kind:'complete',url:'/2',body:{},routeId:1,deliveryId:2});
  const rejected=await box.flush();
  assert.equal(rejected.length,1);
  assert.equal(rejected[0].item.label,'Bar Roma');
  assert.equal(box.count(),0);
  for(const status of [401,502,503,504])assert.ok(isRetryable(http(status)),status);
  for(const status of [400,403,404,409,422])assert.ok(!isRetryable(http(status)),status);
});

test('the same delivery keeps only the latest outcome of a kind',()=>{
  const box=create({storage:memoryStorage(),key:'k',send:async()=>{}});
  box.add({kind:'note',url:'/n',body:{note:'prima'},routeId:1,deliveryId:5});
  box.add({kind:'note',url:'/n',body:{note:'dopo'},routeId:1,deliveryId:5});
  box.add({kind:'complete',url:'/c',body:{},routeId:1,deliveryId:5});
  assert.equal(box.count(),2);
  assert.equal(box.pending(1)[0].body.note,'dopo');
});

test('a full phone storage keeps the outcome in memory and says so',()=>{
  const storage={getItem:()=>null,setItem:()=>{throw new Error('QuotaExceededError');}};
  const box=create({storage,key:'k',send:async()=>{}});
  assert.equal(box.add({kind:'complete',url:'/c',body:{},routeId:1,deliveryId:1}),false);
  assert.equal(box.count(),1);
});

test('pending outcomes are shown on the route with updated progress',()=>{
  const data={consegne:[{id:1,status:'completata'},{id:2,status:'in_attesa'},{id:3,status:'in_attesa'}],
    progress:{totale:3,completate:1,mancate:0,rimanenti:2,prossima_idx:1,percentuale:33}};
  overlay(data,[{kind:'missed',deliveryId:2,body:{motivo:'assente'}}]);
  assert.equal(data.consegne[1].status,'mancata');
  assert.equal(data.consegne[1].motivo_mancata,'assente');
  assert.equal(data.consegne[1].in_attesa_invio,true);
  assert.deepEqual(data.progress,{totale:3,completate:1,mancate:1,rimanenti:1,prossima_idx:2,percentuale:67});
  overlay(data,[{kind:'complete',deliveryId:3,body:{tempo_scarico:15}}]);
  assert.equal(data.progress.prossima_idx,null);
  assert.equal(data.progress.rimanenti,0);
});

test('driver portal queues outcomes instead of losing them',()=>{
  const html=fs.readFileSync('static/driver/index.html','utf8');
  assert.match(html,/driver-outbox\.js\?v=/);
  assert.match(html,/id="outboxBanner"/);
  for(const kind of ['complete','missed','note'])assert.match(html,new RegExp(`submitOutcome\\('${kind}'`));
  assert.match(html,/addEventListener\('online'/);
  assert.match(html,/GFDriverOutbox\.overlay\(/);
});
