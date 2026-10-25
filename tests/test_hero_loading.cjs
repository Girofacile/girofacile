const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
const source=core.slice(core.indexOf('async function loadDashboardHome('),core.indexOf('\nconst ROUTE_STATUS_TONE'));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise(r=>setImmediate(r));
function fixture(){
 const requests=[],heroes=[];
 const ctx=vm.createContext({document:{getElementById:id=>id==='tab-dashboard'?{}:null},window:{},console:{warn(){}},
 api:url=>{const task=deferred();requests.push({url,...task});return task.promise;},renderGFReferenceDashboardHero:route=>{heroes.push(route);return Promise.resolve();}});
 vm.runInContext(source,ctx);return {ctx,requests,heroes};
}
test('active hero starts before unrelated dashboard requests finish and survives their failure',async()=>{
 const f=fixture(),done=f.ctx.loadDashboardHome();
 f.requests.find(r=>r.url==='/api/routes/operativi').resolve([{id:42,status:'in_corso'}]);await tick();
 assert.equal(f.heroes.length,1);assert.equal(f.heroes[0].id,42);
 f.requests.find(r=>r.url==='/api/routes').reject(new Error('Slow history failed'));await done;
 assert.equal(f.heroes.length,1);
});
test('a superseded operational response cannot overwrite the latest hero',async()=>{
 const f=fixture(),first=f.ctx.loadDashboardHome(),second=f.ctx.loadDashboardHome();
 const operational=f.requests.filter(r=>r.url==='/api/routes/operativi');
 operational[1].resolve([{id:2,status:'in_corso'}]);await tick();
 operational[0].resolve([{id:1,status:'in_corso'}]);await tick();
 assert.deepEqual(f.heroes.map(r=>r.id),[2]);
 f.requests.filter(r=>r.url==='/api/routes').forEach(r=>r.reject(new Error('history')));
 await Promise.all([first,second]);
});
test('empty route state renders without waiting for secondary data',async()=>{
 const f=fixture(),done=f.ctx.loadDashboardHome();
 f.requests.find(r=>r.url==='/api/routes/operativi').resolve([]);await tick();
 assert.deepEqual(f.heroes,[null]);
 f.requests.find(r=>r.url==='/api/routes').reject(new Error('history'));await done;
});
