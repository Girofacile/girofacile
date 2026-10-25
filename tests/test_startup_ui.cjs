const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
const init=core.slice(core.indexOf('async function initApp(){'),core.indexOf('let resourcesAvailabilityCache'));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
 const calls=[],settings=deferred(),features=deferred(),customers=deferred();
 const noop=()=>{};
 const ctx=vm.createContext({window:{},document:{getElementById:()=>null},console:{warn:noop},
  initRoutePlanningGateV68:noop,loadProfilePanel:noop,initAddressAutocomplete:noop,initResourceAvailabilityControls:noop,
  loadSettingsV41:()=>settings.promise,loadUniversalFeaturesV89:()=>features.promise,
  api:async url=>{calls.push(url);return [{id:url}];},
  loadDashboardHome:async data=>{ctx.shared=data;await Promise.all(Object.values(data));calls.push('dashboard rendered');},
  loadDeposits:async()=>{calls.push('deposits');},
  loadVehicles:async data=>{assert.equal(data,ctx.shared.vehicles);await data;calls.push('vehicles ready');},
  loadDrivers:async data=>{assert.equal(data,ctx.shared.drivers);await data;calls.push('drivers ready');},
  refreshResourceAvailability:async()=>{assert.ok(calls.includes('vehicles ready')&&calls.includes('drivers ready'));calls.push('availability');},
  agentsFeatureEnabled:()=>true,loadAgents:async()=>{calls.push('agents');},
  loadCustomers:()=>{assert.ok(calls.includes('agents'));return customers.promise;},loadCustomerPicker:async()=>{assert.ok(calls.includes('agents'));},
  loadCompanyProfile:async()=>{calls.push('company');},loadOnboardingStatus:async()=>{assert.ok(calls.includes('company'));},
  loadNotificationsV30:async()=>{calls.push('notifications');},notificationsPollV30:null,
  setInterval:()=>1,clearInterval:noop,updateDashboardStats:noop,toast:msg=>calls.push(msg)});
 vm.runInContext(init,ctx);
 return {ctx,calls,settings,features,customers};
}
test('dashboard renders while slow customers remain pending; resources are requested once',async()=>{
 const f=fixture();const done=f.ctx.initApp();
 f.settings.resolve();await tick();assert.equal(f.calls.length,0);
 f.features.resolve();await tick();
 assert.ok(f.calls.includes('dashboard rendered'));
 assert.ok(f.calls.includes('notifications'));
 assert.equal(f.calls.filter(x=>x==='/api/vehicles').length,1);
 assert.equal(f.calls.filter(x=>x==='/api/drivers').length,1);
 f.customers.resolve();await done;
});
test('a failed secondary load does not prevent dashboard rendering or polling',async()=>{
 const f=fixture();const done=f.ctx.initApp();f.settings.resolve();f.features.resolve();
 await tick();f.customers.reject(new Error('Customers unavailable'));await done;
 assert.ok(f.calls.includes('dashboard rendered'));assert.equal(f.ctx.notificationsPollV30,1);
 assert.ok(f.calls.some(x=>x.startsWith('Alcuni dati')));
});
test('collaborator startup still uses its permission-aware initializer',async()=>{
 const f=fixture();let called=false;f.ctx.window.GFCompanyAccess={isCollaborator:()=>true,initialize:async()=>{called=true;}};
 f.ctx.GFCompanyAccess=f.ctx.window.GFCompanyAccess;await f.ctx.initApp();
 assert.ok(called);assert.equal(f.calls.length,0);
});
test('resource loaders reuse startup responses but fetch fresh data on subsequent calls',async()=>{
 const calls=[];const ctx=vm.createContext({api:async url=>{calls.push(url);return [];},document:{getElementById:()=>null},renderFleetDirectory(){},renderResourceSelects(){},loadVehicleUsage:async()=>{},renderDrivers(){}});
 vm.runInContext(core.slice(core.indexOf('async function loadVehicles('),core.indexOf('const VEHICLE_LOOKUP_FIELDS')),ctx);
 vm.runInContext(core.slice(core.indexOf('async function loadDrivers('),core.indexOf('function driverFullName(')),ctx);
 await ctx.loadVehicles(Promise.resolve([]));await ctx.loadDrivers(Promise.resolve([]));assert.equal(calls.length,0);
 await ctx.loadVehicles();await ctx.loadDrivers();assert.deepEqual(calls,['/api/vehicles','/api/drivers']);
});
