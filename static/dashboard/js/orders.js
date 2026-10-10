/* Server-paginated order archive. All imported/customer text is escaped. */
(function(){
  'use strict';
  const labels={nuovo:'Nuovo',da_verificare:'Da verificare',pronto:'Pronto',assegnato:'Assegnato',in_consegna:'In consegna',consegnato:'Consegnato',non_consegnato:'Non consegnato',annullato:'Annullato'};
  const fields={number:'Numero ordine',recipient_name:'Destinatario',delivery_address:'Indirizzo di consegna',requested_date:'Data richiesta',time_from:'Fascia oraria: dalle',time_to:'Alle',weight_kg:'Peso (kg)',packages:'Colli',pallets:'Pallet',volume_m3:'Volume (m³)',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti operativi',notes:'Note'};
  const numeric=['weight_kg','packages','pallets','volume_m3'], bools=['tail_lift','pallet_truck','ztl'];
  let page=1, sequence=0, detailSequence=0, view='table', current=null, last=null, timer;
  const el=id=>document.getElementById(id);
  const can=key=>!window.GFCompanyAccess || GFCompanyAccess.can(key);
  const display=value=>value===null || value===undefined || value===''?'Non indicato':value===true?'Sì':value===false?'No':String(value);
  const date=value=>value?new Date(value+'Z').toLocaleString('it-IT'):'Non indicata';
  function error(id,err){el(id).textContent=err.message || String(err);}
  async function orderApi(path,options={}){
    const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
    const data=await response.json();
    if(!response.ok){
      let message=data.detail;
      if(Array.isArray(message))message=message.map(e=>`${fields[e.loc?.[1]]||'Dati ordine'}: ${e.msg?.startsWith('Value error, ')?e.msg.slice(13):'verifica formato, limiti e campi obbligatori.'}`).join('\n');
      throw new Error(typeof message==='string'?message:'Operazione non riuscita. Riprova.');
    }
    return data;
  }
  async function load(reset=false){
    if(reset)page=1;
    const request=++sequence, params=new URLSearchParams({page,page_size:25,sort:el('ordersSort').value,direction:el('ordersDirection').value});
    for(const [id,key] of [['ordersSearch','q'],['ordersStatus','status'],['ordersSource','source_id'],['ordersFrom','date_from'],['ordersTo','date_to']])if(el(id).value)params.set(key,el(id).value);
    el('ordersMessage').textContent='Caricamento ordini…';
    el('ordersResults').setAttribute('aria-busy','true');
    el('ordersNew').hidden=!can('orders.create');
    try{
      const data=await orderApi('/api/orders?'+params);
      if(request!==sequence)return;
      last=data;
      el('ordersMetrics').innerHTML=Object.entries({nuovo:'Nuovi ordini',da_verificare:'Da verificare',pronto:'Pronti per la pianificazione',assegnato:'Già assegnati a un giro'}).map(([key,label])=>`<div class="panel"><span>${label}</span><strong>${data.metrics[key]}</strong></div>`).join('');
      const selected=el('ordersSource').value;
      el('ordersSource').innerHTML='<option value="">Tutte le fonti</option>'+data.sources.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');el('ordersSource').value=selected;
      render();el('ordersMessage').textContent=data.total?`${data.total} ordini trovati`:'Nessun ordine trovato. Crea un ordine oppure modifica i filtri.';
    }catch(err){if(request===sequence){el('ordersResults').replaceChildren();error('ordersMessage',err);}}
    finally{if(request===sequence)el('ordersResults').setAttribute('aria-busy','false');}
  }
  function render(){
    if(!last)return;
    const open=o=>`<button class="btn-secondary" onclick="GFOrders.open(${o.id})" aria-label="Apri ordine ${esc(o.number)}">Apri</button>`;
    if(view==='cards')el('ordersResults').innerHTML='<div class="orders-grid">'+last.items.map(o=>`<article class="panel"><h2>${esc(o.number)}</h2><p>${esc(display(o.recipient_name))}</p><p>${esc(display(o.delivery_address))}</p><p>${labels[o.status]} · ${esc(o.source_name)}</p><p>Data richiesta: ${esc(display(o.requested_date))}</p><p>${esc(display(o.packages))} colli · ${esc(display(o.weight_kg))} kg</p>${open(o)}</article>`).join('')+'</div>';
    else el('ordersResults').innerHTML='<div class="tableWrap"><table data-gf-responsive="cards"><thead><tr>'+['Numero ordine','Ricevuto','Cliente / destinatario','Indirizzo','Data richiesta','Colli / kg','Provenienza','Stato','Azioni'].map(x=>`<th scope="col">${x}</th>`).join('')+'</tr></thead><tbody>'+last.items.map(o=>`<tr><td>${esc(o.number)}</td><td>${esc(date(o.received_at))}</td><td>${esc(display(o.recipient_name))}</td><td>${esc(display(o.delivery_address))}</td><td>${esc(display(o.requested_date))}</td><td>${esc(display(o.packages))} / ${esc(display(o.weight_kg))}</td><td>${esc(o.source_name)}</td><td>${labels[o.status]}</td><td>${open(o)}</td></tr>`).join('')+'</tbody></table></div>';
    el('ordersPage').textContent=`Pagina ${page} di ${Math.max(1,Math.ceil(last.total/25))}`;
    el('ordersPrevious').disabled=page<=1;el('ordersNext').disabled=page*25>=last.total;
    for(const mode of ['table','cards'])el('ordersView-'+mode).setAttribute('aria-pressed',String(mode===view));
  }
  function form(data={}){
    el('orderFormFields').innerHTML=Object.entries(fields).map(([key,label])=>{
      const value=data[key], id='orderField-'+key;
      if(bools.includes(key))return `<label for="${id}">${label}<select id="${id}" name="${key}"><option value="">Non indicato</option><option value="true" ${value===true?'selected':''}>Sì</option><option value="false" ${value===false?'selected':''}>No</option></select></label>`;
      if(['notes','requirements'].includes(key))return `<label for="${id}">${label}<textarea id="${id}" name="${key}" maxlength="${key==='notes'?5000:2000}">${esc(value||'')}</textarea></label>`;
      const type=numeric.includes(key)?'number':key==='requested_date'?'date':key.startsWith('time_')?'time':'text';
      return `<label for="${id}">${label}<input id="${id}" name="${key}" type="${type}" value="${esc(value??'')}" ${key==='number'?'required maxlength="160"':key==='recipient_name'?'maxlength="200"':key==='delivery_address'?'maxlength="500"':''} ${type==='number'?`min="0" max="${key==='packages'?1000000:100000000}" step="${key==='packages'?1:'any'}"`:''}></label>`;
    }).join('');
  }
  function newOrder(){++detailSequence;current=null;el('orderEditorTitle').textContent='Nuovo ordine';form();el('orderEditorError').textContent='';showTab('ordine-modifica');}
  async function open(id){
    const request=++detailSequence;
    showTab('ordine-dettaglio');el('orderDetail').textContent='Caricamento ordine…';
    try{const result=await orderApi('/api/orders/'+id);if(request!==detailSequence)return;current=result;detail();}catch(err){if(request===detailSequence)error('orderDetail',err);}
  }
  function changes(event){
    if(event.kind==='corrected')return Object.entries(event.changes).map(([key,value])=>`<p>${fields[key]||esc(key)}: ${esc(display(value.before))} → ${esc(display(value.after))}</p>`).join('');
    if(event.kind==='status_changed')return `<p>${labels[event.changes.before]} → ${labels[event.changes.after]}</p>`;
    if(event.kind==='address_verified')return `<p>${esc(event.changes.address)}</p>`;
    return '<p>Inserimento manuale</p>';
  }
  function detail(){
    const o=current, allowed=can('orders.update') && ['nuovo','da_verificare','pronto'].includes(o.status) && !o.assignments.length;
    el('orderDetail').innerHTML=`<div class="page-title-row"><div><h1>Ordine ${esc(o.number)}</h1><p>${labels[o.status]} · ${esc(o.source_name)}</p></div></div><div class="page-actions">${allowed?'<button class="btn-primary" onclick="GFOrders.edit()">Correggi dati operativi</button><button class="btn-secondary" onclick="GFOrders.action(\'verify-address\')">Verifica indirizzo</button><button class="btn-secondary" onclick="GFOrders.action(\'status\',\'pronto\')">Conferma pronto</button><button class="btn-secondary" onclick="GFOrders.action(\'status\',\'da_verificare\')">Da verificare</button><button class="btn-secondary" onclick="GFOrders.cancel()">Annulla ordine</button>':''}</div><p id="orderActionMessage" role="status"></p><dl class="orders-detail-grid">${Object.entries(fields).map(([key,label])=>`<div><dt>${label}</dt><dd>${esc(display(o.operational_data[key]))}</dd></div>`).join('')}<div><dt>Identificativo interno / esterno</dt><dd>${o.id} / ${esc(o.external_id)}</dd></div><div><dt>Cliente registrato</dt><dd>${o.customer_id??'Destinatario solo per questo ordine'}</dd></div><div><dt>Verifica indirizzo</dt><dd>${o.address_verification?'Verificato':'Da verificare'}</dd></div><div><dt>Acquisizione / verifica / consegna</dt><dd>${esc(({received:'Ricevuto'})[o.acquisition_status]||o.acquisition_status)} / ${esc(({pending:'Da verificare',verified:'Verificato'})[o.verification_status]||o.verification_status)} / ${esc(({not_assigned:'Non assegnato'})[o.delivery_status]||o.delivery_status)}</dd></div><div><dt>Giro</dt><dd>${o.assignments.length?o.assignments.map(a=>`Giro #${a.route_id}`).join(', '):'Non assegnato'}</dd></div></dl><h2>Articoli</h2>${o.items.length?o.items.map(i=>`<p>${esc(i.description)} — ${esc(i.quantity)}</p>`).join(''):'<p>Non indicati</p>'}<details><summary>Dati originali ricevuti</summary><pre>${Object.entries(fields).map(([key,label])=>`${label}: ${esc(display(o.original_payload[key]))}`).join("\n")}</pre></details><h2>Ultimi aggiornamenti (massimo 100)</h2>${o.events.map(e=>`<details><summary>${esc(date(e.created_at))} · ${esc(({created:'Creazione',corrected:'Correzione',address_verified:'Indirizzo verificato',status_changed:'Cambio stato'})[e.kind]||e.kind)} · ${esc(e.actor)}</summary>${changes(e)}</details>`).join('')}`;
  }
  function edit(){el('orderEditorTitle').textContent='Correggi ordine '+current.number;form(current.operational_data);el('orderEditorError').textContent='';showTab('ordine-modifica');}
  async function save(event){
    event.preventDefault();const data={};
    for(const [key,value] of new FormData(event.target))data[key]=value===''?null:numeric.includes(key)?Number(value):bools.includes(key)?value==='true':value;
    if(current)data.version=current.version;
    el('orderSave').disabled=true;el('orderEditorError').textContent='';
    try{current=await orderApi('/api/orders'+(current?'/'+current.id:''),{method:current?'PUT':'POST',body:JSON.stringify(data)});showTab('ordine-dettaglio');detail();}
    catch(err){error('orderEditorError',err);}finally{el('orderSave').disabled=false;}
  }
  async function action(action,status){
    const buttons=el('orderDetail').querySelectorAll('button');buttons.forEach(b=>b.disabled=true);
    el('orderActionMessage').textContent='Operazione in corso…';
    try{current=await orderApi(`/api/orders/${current.id}/${action}`,{method:'POST',body:JSON.stringify({version:current.version,...(status?{status}:{})})});detail();el('orderActionMessage').textContent='Ordine aggiornato.';}
    catch(err){error('orderActionMessage',err);}finally{buttons.forEach(b=>b.disabled=false);}
  }
  window.GFOrders={load,open,newOrder,edit,save,action,cancel(){if(confirm('Annullare questo ordine? L’originale e lo storico saranno conservati.'))action('status','annullato');},search(){clearTimeout(timer);timer=setTimeout(()=>load(true),300);},page(delta){page+=delta;load();},view(mode){view=mode;render();}};
})();
