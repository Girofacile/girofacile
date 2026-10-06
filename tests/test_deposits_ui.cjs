const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
const index=fs.readFileSync('static/dashboard/index.html','utf8');

function fixture(){
 const nodes=new Map(),calls=[];
 const node=id=>{
  if(!nodes.has(id)){
   const classes=new Set(['hidden']);
   nodes.set(id,{
    value:'',textContent:'',innerHTML:'',checked:false,disabled:false,
    classList:{
     toggle(name,force){if(force===undefined){if(classes.has(name)){classes.delete(name);return false;}classes.add(name);return true;}if(force)classes.add(name);else classes.delete(name);return !!force;},
     add(...names){names.forEach(name=>classes.add(name));},
     remove(...names){names.forEach(name=>classes.delete(name));},
     contains(name){return classes.has(name);}
    },
    focus(){},scrollIntoView(){},
    reportValidity(){return !!node('depNome').value&&!!node('depIndirizzo').value},
    querySelector(){return node('saveLabel')},
    querySelectorAll(){return [node('saveDepositBtn'),node('deleteDepositBtn'),node('depNome'),node('depIndirizzo'),node('newDepositBtn')]}
   });
  }
  return nodes.get(id);
 };
 const ctx=vm.createContext({
  document:{getElementById:node},
  api:async(url,opts)=>{calls.push({url,opts});return []},
  set:(id,value)=>node(id).value=String(value),
  val:id=>node(id).value,
  confirm:()=>true,
  esc:s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;')
 });
 vm.runInContext('let depositsCache=[];'+core.slice(core.indexOf('function depositActionIcon('),core.indexOf('const GF_FUEL_LABELS')),ctx);
 return {ctx,node,calls,run:s=>vm.runInContext(s,ctx)};
}

test('deposit page mirrors the customer directory layout and keeps delete inside edit modal',()=>{
 assert.match(index,/id="newDepositBtn"[^>]+onclick="openDepositModal\(\)"/);
 assert.match(index,/class="panel deposit-list-panel"/);
 assert.doesNotMatch(index,/class="panel deposit-form-panel"/);
 assert.match(index,/id="depositOverlay" class="modal-overlay hidden gf-dialog"/);
 assert.match(index,/id="depositDeleteSection" class="deposit-delete-section hidden"/);
});

test('deposit overview uses real timestamps, counts defaults, escapes values and preserves route selection',async()=>{
 const f=fixture();f.node('routeDeposit').value='2';
 f.ctx.api=async()=>[{id:1,nome:'<script>',indirizzo:'Via "Roma"',predefinito:true,updated_at:'2026-09-22T12:32:00'},{id:2,nome:'Secondo',indirizzo:'Via Test',updated_at:null}];
 await f.run('loadDeposits()');
 assert.equal(f.node('routeDeposit').value,'2');
 assert.equal(f.node('depositTotal').textContent,2);
 assert.equal(f.node('depositDefaultName').textContent,'<script>');
 assert.equal(f.node('depositDefaultAddress').textContent,'Via "Roma"');
 assert.match(f.node('depositLastUpdate').textContent,/22 set 2026/);
 assert.equal(f.node('depositLastUpdateTime').textContent,'ore 14:32');
 assert.match(f.node('depositsBody').innerHTML,/&lt;script>/);
 assert.doesNotMatch(f.node('depositsBody').innerHTML,/deposit-delete/);
 assert.match(f.node('depositsBody').innerHTML,/deposit-edit/);
 f.ctx.api=async()=>[];await f.run('loadDeposits()');
 assert.equal(f.node('depositDefaultName').textContent,'Nessun deposito selezionato');
 assert.match(f.node('depositDefaultAddress').textContent,/Imposta un deposito/);
 assert.equal(f.node('depositLastUpdate').textContent,'—');
 assert.match(f.node('depositsBody').innerHTML,/Nessun deposito configurato/);
});

test('new and edit deposit open the modal, while delete is exposed only in edit mode',()=>{
 const f=fixture();
 f.run('openDepositModal()');
 assert.equal(f.node('depositOverlay').classList.contains('hidden'),false);
 assert.equal(f.node('depositDeleteSection').classList.contains('hidden'),true);
 f.run("depositsCache=[{id:7,nome:'Test',indirizzo:'Via Test',note:'Nota esistente',predefinito:true}];editDeposit(7)");
 assert.equal(f.node('depositFormTitle').textContent,'Modifica deposito');
 assert.equal(f.node('depDefault').checked,true);
 assert.equal(f.node('depositDeleteSection').classList.contains('hidden'),false);
});

test('editing preserves notes, uses PUT and resets only after saving',async()=>{
 const f=fixture();
 f.run("depositsCache=[{id:7,nome:'Test',indirizzo:'Via Test',note:'Nota esistente',predefinito:true}];editDeposit(7)");
 f.node('depNome').value=' Aggiornato ';
 await f.run('saveDeposit()');
 assert.equal(f.calls[0].url,'/api/deposits/7');
 assert.equal(f.calls[0].opts.method,'PUT');
 assert.equal(JSON.parse(f.calls[0].opts.body).note,'Nota esistente');
 assert.equal(JSON.parse(f.calls[0].opts.body).nome,'Aggiornato');
 assert.equal(f.node('depId').value,'');
 assert.equal(f.node('saveDepositBtn').disabled,false);
 assert.equal(f.node('depositOverlay').classList.contains('hidden'),true);
});

test('invalid and duplicate submissions do not write; API errors preserve the form',async()=>{
 const f=fixture();
 f.node('depNome').value='  ';await f.run('saveDeposit()');assert.equal(f.calls.length,0);
 f.node('depNome').value='Test';f.node('depIndirizzo').value='Via Test';
 let reject;f.ctx.api=()=>new Promise((_,r)=>reject=r);
 const pending=f.run('saveDeposit()');
 assert.equal(f.node('saveDepositBtn').disabled,true);
 await f.run('saveDeposit()');
 reject(new Error('Errore di rete'));await pending;
 assert.equal(f.node('depNome').value,'Test');
 assert.equal(f.node('depositFormStatus').textContent,'Errore di rete');
 assert.equal(f.node('saveDepositBtn').disabled,false);
});

test('cancelled deletion does not call the API and confirmed deletion clears and closes the editor',async()=>{
 const f=fixture();
 f.run("depositsCache=[{id:7,nome:'Test',indirizzo:'Via Test'}];editDeposit(7)");
 f.ctx.confirm=()=>false;await f.run('deleteDeposit(7)');assert.equal(f.calls.length,0);
 f.ctx.confirm=()=>true;await f.run('deleteDeposit(7)');
 assert.equal(f.calls[0].opts.method,'DELETE');
 assert.equal(f.node('depId').value,'');
 assert.equal(f.node('depositOverlay').classList.contains('hidden'),true);
});
