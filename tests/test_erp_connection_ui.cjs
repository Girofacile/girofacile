const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('static/dashboard/js/order-sources.js','utf8');

function fixture({permissions,fetch}={}){
  const nodes=new Map();
  function node(id){
    if(!nodes.has(id))nodes.set(id,{id,innerHTML:'',textContent:'',value:'',checked:true,
      disabled:false,hidden:false,isConnected:true,attributes:{},
      setAttribute(key,value){this.attributes[key]=value;},
      focus(){this.focused=true;},scrollIntoView(){},querySelector(){return null;}});
    return nodes.get(id);
  }
  const requests=[],imports=[];
  const context=vm.createContext({document:{getElementById:node,querySelectorAll:()=>[]},
    GFCompanyAccess:{can:key=>!permissions||permissions.includes(key),isCollaborator:()=>false},
    GFOrderImport:{start:id=>imports.push(id)},
    fetch:async(url,options)=>{requests.push({url,...options});return fetch?fetch(url,options):{ok:true,json:async()=>({ticket:{id:17,email:'azienda@example.test'}})};},
    esc:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
    FormData,console});
  context.window=context;
  vm.runInContext(source,context);
  function fill(){
    node('erpSoftware').value=' Gestionale demo ';
    node('erpVersion').value=' 3.0 ';
    node('erpMessage').value=' Riceviamo ordini dal nostro gestionale. ';
    node('erpPhone').value=' 020000000 ';
  }
  return {api:context.GFOrderSources,node,requests,imports,fill,event:{preventDefault(){}}};
}

test('file is the default and legacy API/custom entry points open assistance without creating a source',()=>{
  const f=fixture();
  f.api.createForm();f.api.createForm('file');
  assert.equal(f.imports.length,2);
  f.api.createForm('api');
  assert.match(f.node('sourceWizard').innerHTML,/erpRequestForm/);
  f.api.createForm('custom');
  f.api.create(f.event);
  assert.equal(f.requests.length,0);
  assert.doesNotMatch(f.node('sourceWizard').innerHTML,/sourceKind|sourceName/);
});

test('assistance requires support permission even when the user can manage integrations',async()=>{
  const f=fixture({permissions:['orders.integrations']});
  f.api.requestErpConnection();
  assert.match(f.node('sourceWizard').innerHTML,/permesso/);
  assert.doesNotMatch(f.node('sourceWizard').innerHTML,/erpRequestForm/);
  f.fill();await f.api.submitErpRequest(f.event);
  assert.equal(f.requests.length,0);
  assert.match(f.node('erpRequestStatus').textContent,/Non hai il permesso/);
});

test('whitespace-only required fields are rejected before sending a ticket',async()=>{
  const f=fixture();f.fill();f.node('erpSoftware').value='   ';
  await f.api.submitErpRequest(f.event);
  assert.equal(f.requests.length,0);
  assert.match(f.node('erpRequestStatus').textContent,/Inserisci il nome/);
});

test('pending requests reject double submit and restore the form after a server error',async()=>{
  let release;
  const f=fixture({fetch:()=>new Promise(resolve=>{release=resolve;})});
  f.fill();
  const pending=f.api.submitErpRequest(f.event);
  assert.equal(f.node('erpRequestFields').disabled,true);
  assert.equal(f.node('erpRequestForm').attributes['aria-busy'],'true');
  await f.api.submitErpRequest(f.event);
  f.api.closeErpRequest();f.api.requestErpConnection();
  assert.equal(f.requests.length,1);
  assert.equal(f.node('sourceWizard').hidden,false);
  release({ok:false,json:async()=>({detail:'Completa l’email del profilo azienda.'})});
  await pending;
  assert.equal(f.node('erpRequestFields').disabled,false);
  assert.equal(f.node('erpRequestForm').attributes['aria-busy'],'false');
  assert.equal(f.node('erpSoftware').value,' Gestionale demo ');
  assert.match(f.node('erpRequestStatus').textContent,/Completa l’email/);
  const retry=f.api.submitErpRequest(f.event);
  assert.equal(f.requests.length,2);
  release({ok:true,json:async()=>({ticket:{id:19,email:'azienda@example.test'}})});
  await retry;
  assert.match(f.node('sourceWizard').innerHTML,/Richiesta #19 inviata/);
});

test('ticket payload is bounded to form data and confirmation escapes server values',async()=>{
  const f=fixture({fetch:async()=>({ok:true,json:async()=>({ticket:{id:17,email:'<img src=x onerror=alert(1)>'}})})});
  f.fill();f.node('erpRequestNotify').checked=false;
  await f.api.submitErpRequest(f.event);
  assert.equal(f.requests[0].url,'/api/support/erp-connection');
  assert.deepEqual(JSON.parse(f.requests[0].body),{software:'Gestionale demo',version:'3.0',message:'Riceviamo ordini dal nostro gestionale.',phone:'020000000',notify_on_resolution:false});
  assert.match(f.node('sourceWizard').innerHTML,/&lt;img/);
  assert.doesNotMatch(f.node('sourceWizard').innerHTML,/<img/);
  assert.match(f.node('sourceWizard').innerHTML,/Le mie richieste/);
});

test('admin can identify ERP requests and renders their content as text in list, recent tickets and details',async()=>{
  const html=fs.readFileSync('static/admin/index.html','utf8');
  assert.match(html,/<option value="collegamento_gestionale">Collegamento gestionale<\/option>/);
  const nodes=new Map();
  const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',value:''});return nodes.get(id);};
  const untrusted='<img src=x onerror=alert(1)>';
  const ticket={id:19,tipo:'collegamento_gestionale',email:untrusted,oggetto:untrusted,
    username:untrusted,messaggio:untrusted,admin_note:'</textarea>'+untrusted,status:'aperto'};
  const context=vm.createContext({document:{getElementById:node},api:async()=>[ticket],gfShow(){},
    badge:()=>'',fmtDate:()=>'',planName:v=>v,showToast:message=>{throw Error(message);}});
  vm.runInContext('let currentTicketId=null;'+
    html.slice(html.indexOf('function ticketTypeLabel('),html.indexOf('function fmtDate('))+
    html.slice(html.indexOf('function renderRecentTickets('),html.indexOf('// ---- USERS ----'))+
    html.slice(html.indexOf('async function loadTickets('),html.indexOf('async function saveTicket(')),context);
  context.renderRecentTickets([ticket]);
  await context.loadTickets();await context.openTicketModal(19);
  for(const id of ['table-recent-tickets','tickets-tbody','modal-ticket-body']){
    assert.match(node(id).innerHTML,/&lt;img/);
    assert.doesNotMatch(node(id).innerHTML,/<img/);
  }
  assert.match(node('tickets-tbody').innerHTML,/Collegamento gestionale/);
  assert.match(node('modal-ticket-body').innerHTML,/&lt;\/textarea&gt;/);
});
