const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const historySource=fs.readFileSync('static/dashboard/js/history.js','utf8');
const mobileSource=fs.readFileSync('static/mobile/mobile.js','utf8');
const driverSource=fs.readFileSync('static/driver/index.html','utf8');
function sourceFunction(source,name){
  const start=source.indexOf('function '+name+'(');
  assert.ok(start>=0,name);
  const begin=source.slice(Math.max(0,start-6),start)==='async '?start-6:start;
  return source.slice(begin,source.indexOf('\n}',start)+2);
}
function classes(initial=[]){
  const values=new Set(initial);
  return {add:v=>values.add(v),remove:v=>values.delete(v),contains:v=>values.has(v),
    toggle(v,force){const show=force===undefined?!values.has(v):force;show?values.add(v):values.delete(v);}};
}
function historyFixture(api){
  const nodes=new Map(),downloads=[];
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{id,hidden:true,innerHTML:'',textContent:'',value:'',
      dataset:{},classList:classes(),events:{},
      addEventListener(name,fn){this.events[name]=fn;},close(){this.open=false;},
      showModal(){this.open=true;}});
    return nodes.get(id);
  };
  const context={window:{},document:{readyState:'complete',getElementById:node,createElement:()=>({click(){}})},
    api,esc:value=>String(value??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])),
    todayIso:()=> '2026-10-18',dashScheduledMonday:iso=>iso,
    dashScheduledAddDays:(iso,n)=>{const d=new Date(iso+'T12:00:00');d.setDate(d.getDate()+n);return d.toISOString().slice(0,10);},
    dashScheduledDate:iso=>new Date(iso+'T12:00:00'),dashScheduledDayLabel:iso=>iso,
    DASH_SCHEDULED_MONTHS:Array.from({length:12},(_,i)=>String(i+1)),
    DASH_SCHEDULED_DAY_NAMES:['Dom','Lun','Mar','Mer','Gio','Ven','Sab'],
    Blob:class {constructor(parts){this.parts=parts;}},
    URL:{createObjectURL:blob=>{downloads.push(blob.parts.join(''));return 'blob:test';},revokeObjectURL(){}},
    setTimeout(){},toast(){},
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/format.js','utf8'),context);
  vm.runInContext(historySource,context);
  return {history:context.window.GFHistory,node,nodes,downloads,context};
}
function closed(id,name='Giro '+id){
  return {id,nome:name,data_giro:'2026-10-18',orario_partenza:'08:00',status:'completato',
    driver_name:'Autista',vehicle_name:'Mezzo',consegne_count:1,totale_km:2};
}
test('history follows every bounded page and searches/exports beyond 200 records',async()=>{
  const rows=Array.from({length:230},(_,i)=>closed(i+1,i===229?'Archivio antico':'Giro '+i));
  const requests=[];
  const f=historyFixture(async path=>{
    const params=new URL(path,'https://example.test').searchParams;
    const page=Number(params.get('page'));requests.push(page);
    assert.equal(params.get('page_size'),'100');
    return {items:rows.slice((page-1)*100,page*100),total:230,next_page:page<3?page+1:null};
  });
  await f.history.load();
  assert.deepEqual(requests,[1,2,3]);
  assert.equal(f.node('historyLoading').hidden,true);
  assert.equal(f.node('historyError').hidden,true);
  assert.equal(f.node('historyPage').hidden,false);
  f.node('historySearch').value='Archivio antico';
  f.node('historySearch').events.input();
  assert.match(f.node('historyResultsList').innerHTML,/Archivio antico/);
  f.history.exportRoutes();
  assert.match(f.downloads.at(-1),/Archivio antico/);
});
test('failed history page shows retry and never presents a partial archive',async()=>{
  let fail=true;
  const f=historyFixture(async path=>{
    const page=Number(new URL(path,'https://example.test').searchParams.get('page'));
    if(page===2&&fail)throw new Error('Connessione interrotta');
    return {items:[closed(page)],total:2,next_page:page===1?2:null};
  });
  await f.history.load();
  assert.equal(f.node('historyError').hidden,false);
  assert.equal(f.node('historyErrorMessage').textContent,'Connessione interrotta');
  assert.equal(f.node('historyLoading').hidden,true);
  assert.equal(f.node('historyPage').hidden,true);
  fail=false;await f.history.load();
  assert.equal(f.node('historyError').hidden,true);
  assert.equal(f.node('historyPage').hidden,false);
  f.history.exportRoutes();
  assert.match(f.downloads.at(-1),/Giro 1/);assert.match(f.downloads.at(-1),/Giro 2/);
});
test('latest history load wins when an older request finishes later',async()=>{
  let release,calls=0;
  const f=historyFixture(()=>++calls===1?new Promise(resolve=>release=resolve):
    Promise.resolve({items:[closed(2,'Nuovo')],total:1,next_page:null}));
  const old=f.history.load();await f.history.load();
  release({items:[closed(1,'Vecchio')],total:1,next_page:null});await old;
  f.history.exportRoutes();
  assert.match(f.downloads.at(-1),/Nuovo/);assert.doesNotMatch(f.downloads.at(-1),/Vecchio/);
});
test('CSV neutralizes prefixed formulas and preserves actual numeric values',()=>{
  const start=historySource.indexOf('  const cell = value =>');
  const cell=vm.runInNewContext(historySource.slice(start,historySource.indexOf('  function download(',start))+';cell');
  for(const input of ['=1+1',' \t=1+1','\r\n@SUM(1)','\u0000+1','-1+1']){
    assert.equal(cell(input),'"\''+input+'"');
  }
  assert.equal(cell(-12.5),'"-12.5"');
  assert.equal(cell('Cliente "Roma"'),'"Cliente ""Roma"""');
});
test('driver start dispatch keeps apostrophes, quotes and backslashes as data',()=>{
  const calls=[],context={tryStartRoute:(...args)=>calls.push(args)};
  vm.runInNewContext(sourceFunction(driverSource,'handleRouteListClick'),context);
  const name='Giro d\'Italia "Nord" \\ deposito';
  context.handleRouteListClick({target:{closest:selector=>{
    assert.equal(selector,'[data-start-route]');
    return {dataset:{startRoute:'42',beforeTime:'true',startTime:'08:00',startName:name}};
  }}});
  assert.deepEqual(calls,[[42,true,'08:00',name]]);
  const renderContext={gfIcon:()=>'',fmt:()=>'',esc:value=>String(value??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))};
  vm.runInNewContext(fs.readFileSync('static/format.js','utf8'),renderContext);
  vm.runInNewContext(sourceFunction(driverSource,'renderRouteCard'),renderContext);
  const html=renderContext.renderRouteCard({id:42,nome:name,status:'programmato',can_start:true,
    before_time:true,orario_partenza:'08:00',data_giro:'2026-10-18'},'2026-10-18');
  assert.match(html,/data-start-route="42"/);
  assert.ok(html.includes('data-start-name="Giro d&#39;Italia &quot;Nord&quot;'));
  assert.doesNotMatch(html,/onclick="tryStartRoute/);
});
test('mobile detail switches to visible dashboard before rendering',async()=>{
  const views={dashboard:{classList:classes()},giri:{classList:classes(['active'])}};
  const calls=[],detail={scrollIntoView(){calls.push('scroll');}};
  const context={document:{
    querySelectorAll:selector=>selector==='.view'?Object.values(views):[],
    getElementById:id=>id==='dashRouteDetail'?detail:views[id.replace('view-','')],
    querySelector:()=>({classList:classes()}),
  },window:{scrollTo(){}},hideSubView(){},loadDashboard(){},
    api:async()=>({id:7}),renderMobileRouteDetails:(route,target)=>{
      assert.equal(views.dashboard.classList.contains('active'),true);
      assert.equal(views.giri.classList.contains('active'),false);calls.push([route.id,target]);
    },alert:message=>assert.fail(message)};
  vm.runInNewContext(sourceFunction(mobileSource,'showView')+'\n'+sourceFunction(mobileSource,'viewRouteDetail'),context);
  await context.viewRouteDetail(7);
  assert.deepEqual(calls,[[7,'dashRouteDetail'],'scroll']);
});
test('mobile archive follows every page and sends date filters',async()=>{
  const requests=[],context={URLSearchParams,api:async path=>{
    const params=new URL(path,'https://example.test').searchParams;
    const page=Number(params.get('page'));requests.push(page);
    assert.equal(params.get('date_from'),'2025-01-01');assert.equal(params.get('date_to'),'2026-10-18');
    return {items:[{id:page}],total:3,next_page:page<3?page+1:null};
  }};
  vm.runInNewContext(sourceFunction(mobileSource,'loadMobileHistory'),context);
  const rows=await context.loadMobileHistory('2025-01-01','2026-10-18');
  assert.equal(rows.length,3);assert.deepEqual(requests,[1,2,3]);
});
