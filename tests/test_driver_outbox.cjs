const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {create,isRetryable,overlay}=require('../static/driver-outbox.js');

function memoryStorage(){
  const data=new Map();
  return {getItem:k=>data.has(k)?data.get(k):null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k),
    key:i=>[...data.keys()][i]??null,get length(){return data.size;},data};
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
  for(const status of [401,429,500,502,503,504])assert.ok(isRetryable(http(status)),status);
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

test('a newer outcome queued while the older one is being sent is kept and sent next',async()=>{
  const sent=[];let release;
  const box=create({storage:memoryStorage(),key:'k',send:item=>{sent.push(item.body.note);
    if(item.body.note==='A')return new Promise(r=>{release=r;});return Promise.resolve();}});
  box.add({kind:'note',url:'/n',body:{note:'A'},routeId:1,deliveryId:5});
  const running=box.flush();
  await new Promise(r=>setImmediate(r));
  box.add({kind:'note',url:'/n',body:{note:'B'},routeId:1,deliveryId:5});
  release();
  await running;
  // Prima B andava persa (sent=[A], coda vuota); ora parte subito dopo A.
  assert.deepEqual(sent,['A','B']);
  assert.equal(box.count(),0);
});

test('items saved by an older version get an operation id when loaded',()=>{
  const storage=memoryStorage();
  storage.setItem('k',JSON.stringify([{kind:'complete',url:'/c',body:{},routeId:1,deliveryId:1}]));
  const box=create({storage,key:'k',send:async()=>{}});
  assert.ok(box.pending()[0].opId);
});

test('two open tabs never overwrite each other outcomes',async()=>{
  const storage=memoryStorage();const sent=[];let online=false;
  const send=async item=>{if(!online)throw offline();sent.push(item.deliveryId);};
  const tabA=create({storage,key:'k',send,locks:null}), tabB=create({storage,key:'k',send,locks:null});
  tabA.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1});
  tabB.add({kind:'complete',url:'/2',body:{},routeId:1,deliveryId:2});
  tabA.add({kind:'missed',url:'/3',body:{},routeId:1,deliveryId:3});
  assert.equal([...storage.data.keys()].filter(k=>k.startsWith('k:')).length,3);
  assert.equal(tabA.count(),3);assert.equal(tabB.count(),3);
  online=true;
  await tabB.flush();
  assert.deepEqual(sent,[1,2,3]);
  assert.equal(tabA.count(),0);
});

test('a server error keeps the outcome in the queue',async()=>{
  let status=500;const sent=[];
  const box=create({storage:memoryStorage(),key:'k',send:async item=>{if(status)throw http(status);sent.push(item.deliveryId);}});
  box.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1});
  for(const code of [500,502,503,504,507]){status=code;assert.deepEqual(await box.flush(),[]);assert.equal(box.count(),1,String(code));}
  status=0;await box.flush();
  assert.deepEqual(sent,[1]);assert.equal(box.count(),0);
});

test('only one tab sends at a time when the browser offers locks',async()=>{
  let held=Promise.resolve();
  const locks={request:(name,fn)=>{const run=held.then(fn);held=run.catch(()=>{});return run;}};
  const storage=memoryStorage();let active=0,maxActive=0;const sent=[];
  const send=async item=>{active++;maxActive=Math.max(maxActive,active);await new Promise(r=>setTimeout(r,5));sent.push(item.deliveryId);active--;};
  const tabA=create({storage,key:'k',send,locks}),tabB=create({storage,key:'k',send,locks});
  tabA.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1});
  tabB.add({kind:'complete',url:'/2',body:{},routeId:1,deliveryId:2});
  await Promise.all([tabA.flush(),tabB.flush()]);
  assert.equal(maxActive,1);
  assert.deepEqual(sent,[1,2]);
});

test('an outcome from the older queue is sent exactly once',async()=>{
  const storage=memoryStorage();const sent=[];
  storage.setItem('k',JSON.stringify([{kind:'complete',url:'/c',body:{tempo_scarico:5},routeId:1,deliveryId:1,queuedAt:'2026-11-17T08:00:00Z'}]));
  const send=async item=>{sent.push(item.deliveryId);};
  const tabA=create({storage,key:'k',send,locks:null}),tabB=create({storage,key:'k',send,locks:null});
  assert.equal(tabA.pending()[0].opId,tabB.pending()[0].opId);
  await tabA.flush();await tabB.flush();await tabA.flush();
  assert.deepEqual(sent,[1]);
  assert.equal(tabB.count(),0);
});

test('an outcome is not sent twice when the phone cannot save its removal',async()=>{
  const storage=memoryStorage();const sent=[];
  const box=create({storage,key:'k',send:async item=>{sent.push(item.deliveryId);}});
  box.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1});
  storage.setItem=()=>{throw new Error('QuotaExceededError');};
  await box.flush();await box.flush();
  assert.deepEqual(sent,[1]);
  assert.equal(box.count(),0);
});

test('a confirmed outcome is not sent again after reopening the portal when the phone cannot write',async()=>{
  const storage=memoryStorage();const sent=[];let online=false;
  const send=async item=>{if(!online)throw offline();sent.push(item.deliveryId);};
  const first=create({storage,key:'k',send,locks:null});
  first.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1});
  first.add({kind:'complete',url:'/2',body:{},routeId:1,deliveryId:2});
  // Da qui il telefono legge ma non riesce più a scrivere.
  storage.setItem=()=>{throw new Error('QuotaExceededError');};
  online=true;
  await first.flush();
  assert.deepEqual(sent,[1,2]);
  const reopened=create({storage,key:'k',send,locks:null});
  assert.equal(reopened.count(),0);
  await reopened.flush();
  assert.deepEqual(sent,[1,2]);
});

test('older single-list queues move to separate entries and are sent once',async()=>{
  const storage=memoryStorage();const sent=[];
  storage.setItem('k',JSON.stringify([
    {kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1,queuedAt:'2026-11-17T08:00:00Z'},
    {kind:'missed',url:'/2',body:{motivo:'chiuso'},routeId:1,deliveryId:2,queuedAt:'2026-11-17T08:05:00Z'}]));
  const box=create({storage,key:'k',send:async item=>{sent.push(item.deliveryId);},locks:null});
  assert.equal(storage.getItem('k'),null);
  assert.equal(box.count(),2);
  await box.flush();
  const reopened=create({storage,key:'k',send:async item=>{sent.push(item.deliveryId);},locks:null});
  await reopened.flush();
  assert.deepEqual(sent,[1,2]);
});

test('an older queue that cannot be migrated is still sent once, even after reopening',async()=>{
  const storage=memoryStorage();const sent=[];
  storage.setItem('k',JSON.stringify([{kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1,queuedAt:'2026-11-17T08:00:00Z'}]));
  storage.setItem=()=>{throw new Error('QuotaExceededError');};
  const send=async item=>{sent.push(item.deliveryId);};
  await create({storage,key:'k',send,locks:null}).flush();
  await create({storage,key:'k',send,locks:null}).flush();
  assert.deepEqual(sent,[1]);
});

// Telefono con spazio limitato: rifiuta una scrittura che porterebbe il totale oltre «limit» caratteri.
function limitedStorage(limit){
  const s=memoryStorage();const set=s.setItem;
  s.setItem=(k,v)=>{let used=0;for(const [key,val] of s.data)if(key!==k)used+=key.length+val.length;
    if(used+k.length+String(v).length>limit)throw new Error('QuotaExceededError');set(k,v);};
  return s;
}
const legacyQueue=()=>JSON.stringify([
  {kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1,queuedAt:'2026-11-17T08:00:00Z'},
  {kind:'complete',url:'/2',body:{},routeId:1,deliveryId:2,queuedAt:'2026-11-17T08:05:00Z'}]);

test('an older queue only partly migrated is sent once, also after reopening',async()=>{
  const queue=legacyQueue();
  // Spazio per la vecchia lista e una sola voce separata: la migrazione riesce a metà.
  const entry=JSON.stringify({...JSON.parse(queue)[0],opId:'legacy-xxxxxxx'}).length+20;
  const storage=limitedStorage(1+queue.length+entry);storage.data.set('k',queue);
  const sent=[];const send=async item=>{sent.push(item.deliveryId);};
  const page=create({storage,key:'k',send,locks:null});
  assert.equal([...storage.data.keys()].filter(k=>k.startsWith('k:')).length,1,'migrazione parziale');
  await page.flush();
  await create({storage,key:'k',send,locks:null}).flush();
  assert.deepEqual(sent,[1,2]);
  assert.equal(storage.data.size,0);
});

test('an older queue that cannot be written at all is sent once, also after reopening',async()=>{
  const storage=memoryStorage();storage.data.set('k',legacyQueue());
  storage.setItem=()=>{throw new Error('QuotaExceededError');};
  const sent=[];const send=async item=>{sent.push(item.deliveryId);};
  await create({storage,key:'k',send,locks:null}).flush();
  await create({storage,key:'k',send,locks:null}).flush();
  assert.deepEqual(sent,[1,2]);
});

test('replacing an outcome on a full phone never loses both copies',async()=>{
  const offlineSend=async()=>{throw offline();};
  // Spazio per una sola voce: il nuovo esito non entra finché c'è il vecchio.
  const first=memoryStorage();
  create({storage:first,key:'k',send:offlineSend}).add({kind:'missed',url:'/m',body:{motivo:'chiuso'},routeId:1,deliveryId:1});
  const one=[...first.data].reduce((n,[k,v])=>n+k.length+v.length,0);
  const storage=limitedStorage(one+5);
  const sent=[];
  const page=create({storage,key:'k',send:async item=>{sent.push(item.body.motivo);}});
  page.add({kind:'missed',url:'/m',body:{motivo:'chiuso'},routeId:1,deliveryId:1});
  // Il nuovo non si riesce a salvare: resta il vecchio sul telefono, la pagina invia solo il nuovo.
  assert.equal(page.add({kind:'missed',url:'/m',body:{motivo:'assente'},routeId:1,deliveryId:1}),false);
  assert.equal(page.count(),1);
  let reopened=create({storage,key:'k',send:offlineSend});
  assert.equal(reopened.count(),1,'la copia precedente non deve sparire');
  assert.equal(reopened.pending()[0].body.motivo,'chiuso');
  await page.flush();
  assert.deepEqual(sent,['assente']);
  // Inviato il nuovo, la copia vecchia non riparte alla riapertura.
  assert.equal(create({storage,key:'k',send:offlineSend}).count(),0);
});

test('replacing an outcome when the phone can delete but never write keeps the older copy',async()=>{
  const storage=memoryStorage();const sent=[];
  const page=create({storage,key:'k',send:async item=>{sent.push(item.body.note);}});
  page.add({kind:'note',url:'/n',body:{note:'prima'},routeId:1,deliveryId:1});
  storage.setItem=()=>{throw new Error('QuotaExceededError');};
  assert.equal(page.add({kind:'note',url:'/n',body:{note:'seconda'},routeId:1,deliveryId:1}),false);
  const reopened=create({storage,key:'k',send:async()=>{throw offline();}});
  assert.equal(reopened.count(),1,'almeno la copia precedente resta');
  assert.equal(reopened.pending()[0].body.note,'prima');
  await page.flush();
  assert.deepEqual(sent,['seconda']);
  assert.equal(create({storage,key:'k',send:async()=>{}}).count(),0);
});

test('two replacements in a row on a full phone do not bring back the first note',async()=>{
  const offlineSend=async()=>{throw offline();};
  const first=memoryStorage();
  create({storage:first,key:'k',send:offlineSend}).add({kind:'note',url:'/n',body:{note:'uno'},routeId:1,deliveryId:1});
  const one=[...first.data].reduce((n,[k,v])=>n+k.length+v.length,0);
  const storage=limitedStorage(one+5);const sent=[];
  const page=create({storage,key:'k',send:async item=>{sent.push(item.body.note);}});
  page.add({kind:'note',url:'/n',body:{note:'uno'},routeId:1,deliveryId:1});
  assert.equal(page.add({kind:'note',url:'/n',body:{note:'due due'},routeId:1,deliveryId:1}),false);
  assert.equal(page.add({kind:'note',url:'/n',body:{note:'tre tre tre'},routeId:1,deliveryId:1}),false);
  assert.equal(page.count(),1);
  await page.flush();
  assert.deepEqual(sent,['tre tre tre']);
  assert.equal(create({storage,key:'k',send:offlineSend}).count(),0,'la prima nota non ricompare');
});

test('a rejected replacement brings back the valid note it was replacing',async()=>{
  const storage=memoryStorage();const sent=[];let online=false;
  const send=async item=>{
    if(!online)throw offline();
    if(item.body.note.length>500)throw http(422,'Nota troppo lunga');
    sent.push(item.body.note);
  };
  const box=create({storage,key:'k',send,locks:null});
  box.add({kind:'note',url:'/n',body:{note:'nota valida'},routeId:1,deliveryId:1});
  box.add({kind:'note',url:'/n',body:{note:'x'.repeat(501)},routeId:1,deliveryId:1});
  assert.equal(box.count(),1);
  // Riaprendo il portale prima dell'invio, la copia valida è ancora sul telefono.
  assert.equal(create({storage,key:'k',send,locks:null}).count(),1);
  online=true;
  const rejected=await box.flush();
  assert.equal(rejected.length,1);
  assert.deepEqual(sent,['nota valida']);
  assert.equal(create({storage,key:'k',send,locks:null}).count(),0);
});

test('outcomes from the older version are sent with the time they were queued',async()=>{
  const storage=memoryStorage();const bodies=[];
  storage.setItem('k',JSON.stringify([{kind:'note',url:'/n',body:{note:'vecchia'},routeId:1,deliveryId:1,queuedAt:'2026-11-17T08:00:00.000Z'}]));
  await create({storage,key:'k',send:async item=>{bodies.push(item.body);},locks:null}).flush();
  assert.deepEqual(bodies,[{note:'vecchia',scritta_il:'2026-11-17T08:00:00.000Z'}]);
});

test('outcomes kept only in the open page are counted apart',()=>{
  const storage=memoryStorage();
  const box=create({storage,key:'k',send:async()=>{throw offline();},locks:null});
  box.add({kind:'complete',url:'/1',body:{},routeId:1,deliveryId:1});
  storage.setItem=()=>{throw new Error('QuotaExceededError');};
  assert.equal(box.add({kind:'complete',url:'/2',body:{},routeId:1,deliveryId:2}),false);
  assert.equal(box.count(),2);
  assert.equal(box.memoryOnly(),1);
});
