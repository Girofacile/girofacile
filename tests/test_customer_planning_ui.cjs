const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');

function fixture(width){
  const box={innerHTML:''};
  const alerts=[], requests=[], added=[];
  const valid={id:1,nome:'Verified',indirizzo:'Address',stato_geocodifica:'verificato',lat:0,lon:0};
  const rows=[valid,...['da_verificare','non_trovato',null,'legacy'].map((state,i)=>({...valid,id:i+2,nome:'Invalid '+i,stato_geocodifica:state})),{...valid,id:6,lat:null},{...valid,id:7,lon:null},{...valid,id:8,lat:Infinity}];
  const context=vm.createContext({innerWidth:width,document:{getElementById:id=>id==='customerPickerList'?box:null},URLSearchParams,
    api:async url=>{requests.push(url);return rows;},deliveries:[],customersCache:rows,alert:m=>alerts.push(m),
    esc:s=>s||'',agentsFeatureEnabled:()=>false,fascia:()=>'',set:()=>{},markAddressVerified:()=>{}});
  vm.runInContext('let selectedCustomer=null;'+core.slice(core.indexOf('function customerIsPlannable('),core.indexOf('function markRouteNeedsRecalculation(')),context);
  // Capture successful additions without invoking unrelated rendering.
  context.addDeliveryObject=p=>added.push(p);
  return {box,alerts,requests,added,rows,context,run:code=>vm.runInContext(code,context)};
}

for(const width of [390,1440]){
  test(`picker and addition enforce verification at viewport ${width}`,async()=>{
    const f=fixture(width);
    await f.run('loadCustomerPicker()');
    assert.match(f.requests[0],/planning_only=true/);
    assert.match(f.box.innerHTML,/quickAddCustomerToDelivery\(1\)/);
    assert.doesNotMatch(f.box.innerHTML,/Invalid|quickAddCustomerToDelivery\([2-8]\)/);
    await f.run('quickAddCustomerToDelivery(2)');
    assert.equal(f.added.length,0);
    assert.match(f.alerts[0],/deve essere verificato/);
    f.run('selectCustomer(customersCache[1])');
    assert.equal(f.run('selectedCustomer'),null);
    await f.run('quickAddCustomerToDelivery(1)');
    assert.equal(f.added[0].customer_id,1);
    f.rows[1].stato_geocodifica='verificato';
    await f.run('loadCustomerPicker()');
    assert.match(f.box.innerHTML,/quickAddCustomerToDelivery\(2\)/);
  });
}

test('shared planning view explains availability without hiding registry',()=>{
  const html=fs.readFileSync('static/dashboard/index.html','utf8');
  assert.match(html,/Sono disponibili per la pianificazione solo i clienti con indirizzo verificato/);
  assert.equal((html.match(/id="customerPickerList"/g)||[]).length,1);
  assert.match(core,/async function loadCustomers\(/);
});
