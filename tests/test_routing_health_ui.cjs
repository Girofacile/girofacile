const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const html=readFileSync('static/admin/index.html','utf8');
const source=html.slice(html.indexOf('async function checkRoutingHealth()'), html.indexOf('async function testServerService('));

test('admin scripts parse and diagnostic runs only on explicit request',async()=>{
  for(const [,script] of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(script);
  const button={},output={};let calls=0;
  const context={document:{getElementById:id=>id==='routing-health-button'?button:output},api:async(path)=>{
    calls++;assert.equal(path,'/api/admin/routing-health');
    return {osrm:{status:'ok',response_ms:12,configuration_source:'database',warning:'docker_loopback_configuration'},traffic:{provider:'mapbox',configured:true}};
  }};
  vm.createContext(context);vm.runInContext(source,context);
  assert.equal(calls,0);
  await context.checkRoutingHealth();
  assert.equal(calls,1);assert.equal(button.disabled,false);
  assert.match(output.textContent,/operativo.*12 ms/);
  assert.match(output.textContent,/http:\/\/osrm:5000/);
});

test('diagnostic handles failure without rendering exception secrets',async()=>{
  const button={},output={};
  const context={document:{getElementById:id=>id==='routing-health-button'?button:output},api:async()=>{throw Error('private-token')}};
  vm.createContext(context);vm.runInContext(source,context);
  await context.checkRoutingHealth();
  assert.equal(button.disabled,false);assert.doesNotMatch(output.textContent,/private-token/);
});
