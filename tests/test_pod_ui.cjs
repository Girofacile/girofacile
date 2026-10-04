const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/pod.js','utf8');

test('desktop and mobile portals load evidence controls and parse',()=>{
  for(const path of ['static/dashboard/index.html','static/driver/index.html','static/operator/index.html']){
    const html=fs.readFileSync(path,'utf8');
    assert.match(html,/\/static\/pod.js/);
    for(const [,js] of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(js);
    if(!path.includes('dashboard')) {
      assert.match(html,/id="podDeliveryPhoto"[^>]*accept="image\/jpeg,image\/png,image\/webp"/);
      assert.match(html,/podPhotoPayload/);
      assert.match(html,/podEvidenceButtons/);
    }
  }
  const html=fs.readFileSync('static/dashboard/index.html','utf8');
  assert.doesNotMatch(html,/<input[^>]*id="featurePhotoProofV89"[^>]*disabled/);
});

test('evidence buttons show only available documents',()=>{
  const ctx=vm.createContext({});vm.runInContext(source,ctx);
  assert.equal(ctx.podEvidenceButtons({},'/evidence'),'');
  const result=ctx.podEvidenceButtons({has_signature:true,has_delivery_photo:true,has_pod:true},'/evidence');
  assert.match(result,/Visualizza firma/);assert.match(result,/Visualizza foto/);assert.match(result,/Scarica POD/);
  assert.equal((result.match(/<button/g)||[]).length,3);
});

test('photo validation, required policy and resize retain the selected file',async()=>{
  const input={files:[]};let closed=false,canvas;
  const ctx=vm.createContext({document:{getElementById:()=>input,createElement:()=>canvas={getContext:()=>({fillRect(){},drawImage(){}}),toDataURL:()=> 'data:image/jpeg;base64,photo'}},
    createImageBitmap:async()=>({width:4000,height:3000,close(){closed=true}})});
  vm.runInContext(source,ctx);
  await assert.rejects(ctx.podPhotoPayload(true),/obbligatoria/);
  input.files=[{type:'text/html',size:10}];await assert.rejects(ctx.podPhotoPayload(),/non valida/);
  input.files=[{type:'image/jpeg',size:12000001}];await assert.rejects(ctx.podPhotoPayload(),/non valida/);
  const file={type:'image/jpeg',size:1000};input.files=[file];
  assert.equal((await ctx.podPhotoPayload()).delivery_photo_data,'data:image/jpeg;base64,photo');
  assert.equal(canvas.width,1600);assert.equal(canvas.height,1200);assert.ok(closed);assert.equal(input.files[0],file);
});

test('file click fetches authorized URL and shows explicit errors',async()=>{
  const replaced=[];let closed=false,message;
  const target={location:{replace:url=>replaced.push(url)},close(){closed=true}};
  const ctx=vm.createContext({window:{open:()=>target},fetch:async(path,options)=>{
    assert.equal(path,'/api/deliveries/1/evidence/pod');assert.equal(options.credentials,'same-origin');
    return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({url:'https://example.test/signed'})};},alert:m=>message=m});
  vm.runInContext(source,ctx);await ctx.podOpenEvidence('/api/deliveries/1/evidence/pod');
  assert.deepEqual(replaced,['https://example.test/signed']);assert.equal(target.opener,null);
  ctx.fetch=async()=>({ok:false,json:async()=>({detail:'Archivio non disponibile'})});
  await ctx.podOpenEvidence('/api/deliveries/1/evidence/pod');assert.ok(closed);assert.equal(message,'Archivio non disponibile');
});
