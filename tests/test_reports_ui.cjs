const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');

function fixture(){
  const ctx=vm.createContext({
    URLSearchParams, document:{getElementById:id=>id==='tab-report'?{}:null},
    customersCache:[], driversCache:[{}], vehiclesCache:[{}], agentsCache:[],
    agentsFeatureEnabled:()=>false, featureLockedForTab:()=>false,
    showLockedOrProceed:()=>false, val:()=>'', driverFullName:()=>'',
    reportData:null, toast:()=>{}, api:async()=>[],
  });
  vm.runInContext(readFileSync('static/dashboard/js/reports.js','utf8'),ctx);
  return {ctx,run:code=>vm.runInContext(code,ctx)};
}

test('report filters include clients beyond the first API page',async()=>{
  const f=fixture(),calls=[];
  f.ctx.api=async url=>{calls.push(url);return url.endsWith('offset=0')?Array.from({length:1000},(_,id)=>({id})): [{id:1001}];};
  await f.run('ensureReportFilters()');
  assert.equal(f.ctx.customersCache.length,1001);
  assert.equal(calls.length,2);
});

test('failed customer pagination does not cache an incomplete report filter',async()=>{
  const f=fixture();
  f.ctx.api=async url=>{if(url.endsWith('offset=0'))return Array(1000).fill({});throw Error('offline');};
  await f.run('ensureReportFilters()');
  assert.equal(f.ctx.customersCache.length,0);
});

test('slow report response cannot replace a newer filtered report',async()=>{
  const f=fixture(),pending=[],rendered=[];
  f.ctx.customersCache=[{}];
  f.ctx.api=()=>new Promise(resolve=>pending.push(resolve));
  f.ctx.renderReportMetrics=metrics=>rendered.push(metrics.count);
  f.ctx.renderReportCharts=f.ctx.renderReportTables=f.ctx.renderReportInsights=()=>{};
  const first=f.run('loadReport()');
  await new Promise(resolve=>setImmediate(resolve));
  const second=f.run('loadReport()');
  await new Promise(resolve=>setImmediate(resolve));
  pending[1]({metrics:{count:2}}); await second;
  pending[0]({metrics:{count:1}}); await first;
  assert.deepEqual(rendered,[2]);
  assert.equal(f.ctx.reportData.metrics.count,2);
});

test('printed report describes the filters used for its request',async()=>{
  const f=fixture();let resolve,html='';
  const popup={document:{body:{},open(){},write:value=>html=value,close(){},getElementById:()=>({})},focus(){},print(){}};
  f.ctx.window={open:()=>popup};f.ctx.esc=value=>String(value||'');
  f.ctx.val=id=>id==='reportDateFrom'?'2026-10-01':'';
  f.ctx.api=()=>new Promise(r=>resolve=r);
  const printing=f.run('printReport()');
  f.ctx.val=id=>id==='reportDateFrom'?'2026-10-16':'';
  resolve({metrics:{},tables:{giri:[]}});await printing;
  assert.ok(html.includes('date_from: 2026-10-01'));
  assert.ok(!html.includes('2026-10-16'));
});
