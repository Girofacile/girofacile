const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const podSource=fs.readFileSync('static/pod.js','utf8');
const trackingSource=fs.readFileSync('static/tracking/company.js','utf8');
const evidence={has_signature:true,has_delivery_photo:true,has_pod:true};

test('historical proof is hidden after downgrade, independently of saved preferences',async()=>{
  let readFile=false;
  const ctx=vm.createContext({document:{getElementById(){readFile=true;throw Error('Photo must not be read');}}});
  vm.runInContext(podSource,ctx);
  const stale={delivery_signature_enabled:true,delivery_photo_required:true,features:{has_delivery_signature:false,has_photo_proof:false,has_pod_pdf:false}};
  assert.equal(ctx.podEvidenceButtons(evidence,'/evidence',stale),'');
  assert.equal(ctx.podFeatureEnabled('has_delivery_signature',stale),false);
  assert.equal(JSON.stringify(await ctx.podPhotoPayload(true,stale)),'{}');
  assert.equal(readFile,false);
  const driver={settings:{...stale,features:{has_delivery_signature:true,has_photo_proof:true,has_pod_pdf:true}}};
  assert.equal((ctx.podEvidenceButtons(evidence,'/evidence',driver).match(/<button/g)||[]).length,3);
  driver.settings.features.has_pod_pdf=false;
  assert.doesNotMatch(ctx.podEvidenceButtons(evidence,'/evidence',driver),/Scarica POD/);
  assert.match(ctx.podEvidenceButtons(evidence,'/evidence',driver),/Visualizza firma/);
});

test('company and mobile customer tracking require the current plan before creating links',async()=>{
  let requests=0;const messages=[];
  const ctx=vm.createContext({currentSessionUser:{limits:{has_customer_tracking:false}},toast:message=>messages.push(message),fetch:()=>requests++});
  vm.runInContext(trackingSource,ctx);
  assert.equal(ctx.trackingButton({id:12},{status:'programmato'}),'');
  await ctx.openCustomerTracking(12);
  assert.equal(requests,0);
  assert.match(messages[0],/Business/);
  ctx.currentSessionUser.limits.has_customer_tracking=true;
  assert.match(ctx.trackingButton({id:12},{status:'programmato'}),/Tracking cliente/);
  assert.equal(ctx.trackingButton({id:12},{status:'bozza'}),'');
  const mobile=vm.createContext({me:{limits:{has_customer_tracking:true}}});
  vm.runInContext(trackingSource,mobile);
  assert.match(mobile.trackingButton({id:12},{status:'in_corso'}),/Tracking cliente/);
});

test('photo controls disable upload and clear a stale selection when no longer included',()=>{
  const toggles=[];const input={value:'old-photo',toggleAttribute:(name,value)=>toggles.push([name,value])};
  const field={classList:{toggle:(name,value)=>toggles.push([name,value])},querySelector:()=>input};
  const ctx=vm.createContext({document:{querySelectorAll:()=>[field],getElementById:id=>id==='podDeliveryPhoto'?input:null}});
  vm.runInContext(podSource,ctx);
  ctx.podConfigurePhoto({features:{has_photo_proof:false}});
  assert.equal(field.hidden,true);assert.equal(input.value,'');
  assert.deepEqual(toggles,[['hidden',true],['disabled',true]]);
  ctx.podConfigurePhoto({features:{has_photo_proof:true}});
  assert.equal(field.hidden,false);
});
