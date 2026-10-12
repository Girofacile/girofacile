/* Server-paginated order archive. All imported/customer text is escaped. */
(function(){
  'use strict';
  const labels={nuovo:'Nuovo',da_verificare:'Da verificare',pronto:'Pronto',assegnato:'Assegnato',in_consegna:'In consegna',consegnato:'Consegnato',non_consegnato:'Non consegnato',annullato:'Annullato'};
  const metricMeta={
    nuovo:{label:'Nuovi ordini',icon:'<path d="M5 8h14l-1 11H6L5 8Z"/><path d="M8 8a4 4 0 0 1 8 0"/>',cls:'nuovo'},
    da_verificare:{label:'Da verificare',icon:'<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',cls:'da_verificare'},
    pronto:{label:'Pronti per piano',icon:'<circle cx="12" cy="12" r="8"/><path d="m8.5 12 2.2 2.2 4.8-5"/>',cls:'pronto'},
    assegnato:{label:'Già assegnati',icon:'<path d="M3 7h11v9H3z"/><path d="M14 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',cls:'assegnato'}
  };
  const fields={number:'Numero ordine',recipient_name:'Destinatario',delivery_address:'Indirizzo di consegna',requested_date:'Data richiesta',time_from:'Fascia oraria: dalle',time_to:'Alle',weight_kg:'Peso (kg)',packages:'Colli',pallets:'Pallet',volume_m3:'Volume (m³)',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti operativi',notes:'Note'};
  const numeric=['weight_kg','packages','pallets','volume_m3'], bools=['tail_lift','pallet_truck','ztl'];
  let page=1, sequence=0, detailSequence=0, view='table', current=null, last=null, timer, modalScrollY=0, bulkVerifying=false, stopBulkVerification=false;
  const el=id=>document.getElementById(id);
  const can=key=>!window.GFCompanyAccess || GFCompanyAccess.can(key);
  const display=value=>value===null || value===undefined || value===''?'Non indicato':value===true?'Sì':value===false?'No':String(value);
  const date=value=>value?new Date(value+'Z').toLocaleString('it-IT'):'Non indicata';
  const receivedDate=value=>value?new Date(value+'Z').toLocaleString('it-IT',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):'Non indicata';
  const statusBadge=status=>`<span class="orders-status orders-status-${esc(status)}"><i aria-hidden="true"></i>${esc(labels[status]||status)}</span>`;
  function syncActionPlacement(){
    const actions=el('ordersPageActions'), inline=el('ordersInlineActionsHost'), topbar=el('ordersTopbarActionsHost');
    if(!actions||!inline||!topbar)return;
    const target=window.matchMedia('(min-width: 821px)').matches?topbar:inline;
    if(actions.parentNode!==target)target.appendChild(actions);
  }
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
    syncActionPlacement();
    if(reset)page=1;
    const request=++sequence, params=new URLSearchParams({page,page_size:25,sort:el('ordersSort').value,direction:el('ordersDirection').value});
    for(const [id,key] of [['ordersSearch','q'],['ordersStatus','status'],['ordersSource','source_id'],['ordersFrom','date_from'],['ordersTo','date_to']])if(el(id).value)params.set(key,el(id).value);
    el('ordersMessage').textContent='Caricamento ordini…';
    el('ordersResults').setAttribute('aria-busy','true');
    el('ordersNew').hidden=!can('orders.create');
    el('ordersImport').hidden=!(can('orders.import')||can('orders.integrations'));
    const verifyAll=el('ordersVerifyAll');if(verifyAll)verifyAll.hidden=!can('orders.update');
    try{
      const data=await orderApi('/api/orders?'+params);
      if(request!==sequence)return;
      if(window.GFOrderPlanning)await GFOrderPlanning.loadSelection();
      if(request!==sequence)return;
      last=data;
      el('ordersMetrics').innerHTML=Object.entries(metricMeta).map(([key,meta])=>`<article class="orders-metric-card"><div class="orders-metric-copy"><span class="orders-metric-label">${meta.label}</span><strong class="orders-metric-value">${Number(data.metrics[key]||0)}</strong></div><span class="orders-metric-icon is-${meta.cls}" aria-hidden="true"><svg viewBox="0 0 24 24">${meta.icon}</svg></span></article>`).join('');
      const selected=el('ordersSource').value;
      el('ordersSource').innerHTML='<option value="">Tutte le fonti</option>'+data.sources.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');el('ordersSource').value=selected;
      render();el('ordersMessage').textContent=data.total?`${data.total} ordini trovati`:'Nessun ordine trovato. Crea un ordine oppure modifica i filtri.';
    }catch(err){if(request===sequence){el('ordersResults').replaceChildren();error('ordersMessage',err);}}
    finally{if(request===sequence)el('ordersResults').setAttribute('aria-busy','false');}
  }
  function render(){
    if(!last)return;
    const open=o=>`<button class="btn-secondary orders-open-button" onclick="GFOrders.open(${o.id})" aria-label="Apri ordine ${esc(o.number)}">Apri</button>`;
    if(view==='cards'){
      el('ordersResults').innerHTML='<div class="orders-grid">'+last.items.map(o=>`<article class="panel orders-order-card ${window.GFOrderPlanning?.isSelected(o.id)?'is-selected':''}"><div class="orders-order-card-head"><span>${window.GFOrderPlanning?.checkbox(o)||""}</span>${statusBadge(o.status)}</div><h2>${esc(o.number)}</h2><p><strong>${esc(display(o.recipient_name))}</strong></p><p>${esc(display(o.delivery_address))}</p><p>${esc(o.source_name)} · ${esc(display(o.requested_date))}</p><p>${esc(display(o.packages))} colli · ${esc(display(o.weight_kg))} kg</p>${open(o)}</article>`).join('')+'</div>';
    }else{
      const selectAll=window.GFOrderPlanning?.headerCheckbox(last.items)||'';
      el('ordersResults').innerHTML='<div class="orders-table-shell tableWrap"><table class="orders-table" data-gf-responsive="cards"><thead><tr><th scope="col" class="orders-select-col" aria-label="Seleziona">'+selectAll+'</th><th scope="col">Numero ordine</th><th scope="col">Ricevuto</th><th scope="col">Cliente / destinatario</th><th scope="col">Indirizzo</th><th scope="col">Stato</th><th scope="col">Azioni</th></tr></thead><tbody>'+last.items.map(o=>`<tr class="${window.GFOrderPlanning?.isSelected(o.id)?'is-selected':''}"><td class="orders-select-cell">${window.GFOrderPlanning?.checkbox(o)||""}</td><td class="orders-number-cell">${esc(o.number)}</td><td>${esc(receivedDate(o.received_at))}</td><td class="orders-recipient-cell"><strong>${esc(display(o.recipient_name))}</strong></td><td class="orders-address-cell">${esc(display(o.delivery_address))}</td><td>${statusBadge(o.status)}</td><td>${open(o)}</td></tr>`).join('')+'</tbody></table></div>';
    }
    el('ordersPage').textContent=`Pagina ${page} di ${Math.max(1,Math.ceil(last.total/25))}`;
    el('ordersPrevious').disabled=page<=1;el('ordersNext').disabled=page*25>=last.total;
    for(const mode of ['table','cards'])el('ordersView-'+mode).setAttribute('aria-pressed',String(mode===view));
  }
  function form(data={}){
    el('orderFormFields').innerHTML=Object.entries(fields).map(([key,label])=>{
      const value=data[key], id='orderField-'+key;
      if(bools.includes(key))return `<label for="${id}">${label}<select id="${id}" name="${key}"><option value="">Non indicato</option><option value="true" ${value===true?'selected':''}>Sì</option><option value="false" ${value===false?'selected':''}>No</option></select></label>`;
      if(['notes','requirements'].includes(key))return `<label for="${id}" class="order-modal-form-wide">${label}<textarea id="${id}" name="${key}" maxlength="${key==='notes'?5000:2000}">${esc(value||'')}</textarea></label>`;
      const type=numeric.includes(key)?'number':key==='requested_date'?'date':key.startsWith('time_')?'time':'text';
      return `<label for="${id}">${label}<input id="${id}" name="${key}" type="${type}" value="${esc(value??'')}" ${key==='number'?'required maxlength="160"':key==='recipient_name'?'maxlength="200"':key==='delivery_address'?'maxlength="500"':''} ${type==='number'?`min="0" max="${key==='packages'?1000000:100000000}" step="${key==='packages'?1:'any'}"`:''}></label>`;
    }).join('');
    // Keep the everyday workflow compact; optional logistics remain available on demand.
    const container=el('orderFormFields');
    const basic=document.createElement('div');
    basic.className='order-form-primary';
    const optional=document.createElement('details');
    optional.className='order-form-optional';
    const title=document.createElement('summary');
    title.textContent='Altre informazioni (facoltative)';
    const otherFields=document.createElement('div');
    otherFields.className='orders-form-grid';
    const essential=new Set(['number','recipient_name','delivery_address']);
    for(const label of Array.from(container.children)){
      const input=label.querySelector('input,select,textarea');
      if(essential.has(input?.name))basic.appendChild(label);
      else otherFields.appendChild(label);
    }
    optional.append(title,otherFields);
    container.replaceChildren(basic,optional);
  }
  function modal(){return el('orderModal');}
  function showOrderModal(){
    const dialog=modal();if(!dialog)return;
    if(!dialog.open){
      modalScrollY=window.scrollY;
      dialog.showModal();
      document.documentElement.classList.add('order-modal-open');
    }
  }
  function closeModal(){
    const dialog=modal();
    ++detailSequence;
    if(dialog?.open)dialog.close();
    document.documentElement.classList.remove('order-modal-open');
    requestAnimationFrame(()=>window.scrollTo({top:modalScrollY,left:0,behavior:'auto'}));
    current=null;
  }
  function renderEditor(data={},creating=false){
    const title=creating?'Nuovo ordine':`Modifica ${esc(current?.number||'ordine')}`;
    el('orderModalContent').innerHTML=`<div class="order-modal-editor">
      <header class="order-modal-header">
        <div><h2 id="orderModalTitle">${title}</h2><p>${creating?'Inserisci i dati disponibili per creare un nuovo ordine.':'Aggiorna i dati operativi. I dati originali ricevuti restano conservati nello storico.'}</p></div>
        <button class="order-modal-close" type="button" onclick="GFOrders.close()" aria-label="Chiudi"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
      </header>
      <form class="order-modal-edit-form" onsubmit="GFOrders.save(event)">
        <div id="orderFormFields" class="orders-form-grid"></div>
        <p id="orderEditorError" class="orders-error" role="alert"></p>
        <div class="order-modal-editor-actions">
          <button class="btn-secondary" type="button" onclick="GFOrders.cancelEdit()">Annulla</button>
          <button id="orderSave" class="btn-primary" type="submit">${creating?'Crea ordine':'Salva modifiche'}</button>
        </div>
      </form>
    </div>`;
    showOrderModal();form(data);el('orderEditorError').textContent='';
  }
  function newOrder(){++detailSequence;current=null;renderEditor({},true);}
  async function open(id){
    const request=++detailSequence;
    el('orderModalContent').innerHTML='<div class="order-modal-loading"><span></span><p>Caricamento ordine…</p></div>';
    showOrderModal();
    try{const result=await orderApi('/api/orders/'+id);if(request!==detailSequence)return;current=result;detail();}
    catch(err){if(request===detailSequence)el('orderModalContent').innerHTML=`<div class="order-modal-error"><p>${esc(err.message||String(err))}</p><button class="btn-secondary" onclick="GFOrders.close()">Chiudi</button></div>`;}
  }
  function changes(event){
    if(['customer_linked','customer_resolution'].includes(event.kind))return `<p>Associazione cliente: ${esc(event.changes.after??event.changes.customer_id??'Destinatario separato')}</p>`;
    if(event.kind==='corrected')return Object.entries(event.changes).map(([key,value])=>`<p>${fields[key]||esc(key)}: ${esc(display(value.before))} → ${esc(display(value.after))}</p>`).join('');
    if(event.kind==='status_changed')return `<p>${labels[event.changes.before]||event.changes.before} → ${labels[event.changes.after]||event.changes.after}</p>`;
    if(event.kind==='address_verified')return `<p>${esc(event.changes.address)}</p>`;
    if(event.kind==='route_status')return `<p>Giro #${esc(event.changes.route_id)}: ${esc(labels[event.changes.before]||event.changes.before)} → ${esc(labels[event.changes.after]||event.changes.after)}</p>`;
    if(event.kind==='route_released')return `<p>Ordine rimosso dal giro #${esc(event.changes.route_id)} e nuovamente disponibile.</p>`;
    if(event.kind==='route_snapshot')return `<p>Dati della fermata salvati nel giro #${esc(event.changes.route_id)}.</p>`;
    if(event.kind==='received')return '<p>Ordine ricevuto dalla fonte collegata.</p>';
    if(event.kind==='source_updated')return `<p>Aggiornamento dalla fonte. Correzioni manuali conservate: ${esc((event.changes.preserved_corrections||[]).map(k=>fields[k]||k).join(', ')||'nessuna')}.</p>`;
    return '<p>Inserimento manuale</p>';
  }
  function eventLabel(kind){
    return ({received:'Acquisizione ordine',source_updated:'Aggiornamento dalla fonte',customer_linked:'Cliente riconosciuto',customer_resolution:'Associazione cliente',route_status:'Stato consegna',route_released:'Rimosso dal giro',route_snapshot:'Fermata salvata',created:'Creazione ordine',corrected:'Modifica dati',address_verified:'Indirizzo verificato',status_changed:'Cambio stato'})[kind]||kind;
  }
  function detail(){
    const o=current;if(!o)return;
    const data=o.effective_data||o.operational_data||{};
    const allowed=can('orders.update') && ['nuovo','da_verificare','pronto'].includes(o.status) && !o.assignments.length;
    const verified=!!o.address_verification&&!o.anomalies?.some(a=>a.code==='verification');
    const requested=data.requested_date?esc(data.requested_date):'Non indicata';
    const timeRange=data.time_from||data.time_to?`${esc(data.time_from||'—')} – ${esc(data.time_to||'—')}`:'Non indicata';
    const boolValue=value=>value===true?'Sì':value===false?'No':'N/D';
    const sourceChip=`<span class="order-modal-source-chip">${esc(o.source_name)}</span>`;
    const items=o.items?.length?o.items.map((item,index)=>`<div class="order-modal-item-row"><span>${esc(item.description||item.name||`Articolo ${index+1}`)}</span><strong>${esc(display(item.quantity))}</strong></div>`).join(''):'<p class="order-modal-empty">Nessun articolo indicato.</p>';
    const notes=data.notes?`<p class="order-modal-note-text">“${esc(data.notes)}”</p>`:'<p class="order-modal-empty">Nessuna nota ordine.</p>';
    const addressText=esc(display(data.delivery_address));
    const actionCard=!verified
      ?`<section class="order-modal-alert">
          <div class="order-modal-alert-band">Azione necessaria</div>
          <div class="order-modal-alert-body">
            <span class="order-modal-alert-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 21s6-5.3 6-11a6 6 0 1 0-12 0c0 5.7 6 11 6 11Z"/><circle cx="12" cy="10" r="2"/></svg></span>
            <strong>Indirizzo da confermare</strong>
            <p>Verifica l’indirizzo “${addressText}”. Se è valido, l’ordine diventa subito pianificabile.</p>
            ${allowed?'<button onclick="GFOrders.action(\'verify-address\')">Verifica indirizzo ora</button>':''}
          </div>
        </section>`
      :`<section class="order-modal-alert is-ok">
          <div class="order-modal-alert-band">Verifica completata</div>
          <div class="order-modal-alert-body">
            <span class="order-modal-alert-icon" aria-hidden="true">✓</span>
            <strong>Indirizzo verificato</strong>
            <p>La destinazione è pronta per essere utilizzata nella pianificazione.</p>
          </div>
        </section>`;
    const readyButton=''; // Verification makes the order ready without confirmation.
    const editButton=allowed?'<button class="btn-primary order-modal-footer-edit" onclick="GFOrders.edit()">Modifica dati</button>':'';
    const cancelButton=allowed?'<button class="order-modal-cancel-link" onclick="GFOrders.cancel()">Annulla ordine</button>':'';

    el('orderModalContent').innerHTML=`
      <header class="order-modal-header order-modal-detail-header">
        <div class="order-modal-heading">
          <div class="order-modal-title-row"><h2 id="orderModalTitle">${esc(o.number)}</h2>${statusBadge(o.status)}${sourceChip}</div>
          <p>Acquisito il ${esc(date(o.received_at))}</p>
        </div>
        <button class="order-modal-close" type="button" onclick="GFOrders.close()" aria-label="Chiudi"><svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
      </header>
      <p id="orderActionMessage" class="order-modal-action-message" role="status"></p>
      <div class="order-modal-body">
        <main class="order-modal-main">
          <section class="order-modal-card">
            <div class="order-modal-card-head"><span aria-hidden="true">●</span><h3>Dati di consegna</h3></div>
            <div class="order-modal-delivery-grid">
              <div><span>Destinatario</span><strong>${esc(display(data.recipient_name))}</strong></div>
              <div><span>Indirizzo di consegna</span><strong>${addressText}</strong></div>
              <div><span>Data richiesta</span><strong>${requested}</strong></div>
              <div><span>Fascia oraria</span><strong>${timeRange}</strong></div>
            </div>
          </section>

          <section class="order-modal-card">
            <div class="order-modal-card-head"><span aria-hidden="true">◆</span><h3>Specifiche merce e logistica</h3></div>
            <div class="order-modal-logistics-grid">
              <div><span>Peso (kg)</span><strong>${esc(display(data.weight_kg))}</strong></div>
              <div><span>Colli</span><strong>${esc(display(data.packages))}</strong></div>
              <div><span>Pallet</span><strong>${esc(display(data.pallets))}</strong></div>
              <div><span>Volume (m³)</span><strong>${esc(display(data.volume_m3))}</strong></div>
              <div><span>Sponda idraulica</span><strong>${boolValue(data.tail_lift)}</strong></div>
              <div><span>Transpallet</span><strong>${boolValue(data.pallet_truck)}</strong></div>
              <div><span>Permesso ZTL</span><strong>${boolValue(data.ztl)}</strong></div>
              <div><span>Req. operativi</span><strong>${esc(display(data.requirements))}</strong></div>
            </div>
          </section>

          <div class="order-modal-split">
            <section class="order-modal-card">
              <div class="order-modal-card-head"><span aria-hidden="true">≡</span><h3>Distinta articoli</h3><small>${o.items?.length||0} righe</small></div>
              <div class="order-modal-items">${items}</div>
            </section>
            <section class="order-modal-card order-modal-notes">
              <div class="order-modal-card-head"><span aria-hidden="true">□</span><h3>Note ordine</h3></div>
              <div class="order-modal-note-body">${notes}</div>
            </section>
          </div>
        </main>

        <aside class="order-modal-side">
          ${actionCard}
          <section id="orderCustomerPanel" class="order-modal-card order-modal-customer"></section>
        </aside>
      </div>
      <footer class="order-modal-footer">
        <div class="order-modal-footer-left">${cancelButton}</div>
        <div class="order-modal-footer-actions">
          <button class="btn-secondary" type="button" onclick="GFOrders.close()">Chiudi</button>
          ${readyButton}
          ${editButton}
        </div>
      </footer>`;
    window.GFOrderCustomers?.render(o);
  }
  function edit(){if(!current)return;renderEditor(current.operational_data||{},false);}
  function cancelEdit(){current?detail():closeModal();}
  async function save(event){
    event.preventDefault();const data={};
    for(const [key,value] of new FormData(event.target))data[key]=value===''?null:numeric.includes(key)?Number(value):bools.includes(key)?value==='true':value;
    const editing=!!current;if(editing)data.version=current.version;
    el('orderSave').disabled=true;el('orderEditorError').textContent='';
    try{
      current=await orderApi('/api/orders'+(editing?'/'+current.id:''),{method:editing?'PUT':'POST',body:JSON.stringify(data)});
      detail();
      load();
    }catch(err){error('orderEditorError',err);}
    finally{if(el('orderSave'))el('orderSave').disabled=false;}
  }
  async function action(action,status){
    if(!current)return;
    const root=el('orderModalContent'),buttons=root.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);
    const message=el('orderActionMessage');if(message)message.textContent='Operazione in corso…';
    try{
      current=await orderApi(`/api/orders/${current.id}/${action}`,{method:'POST',body:JSON.stringify({version:current.version,...(status?{status}:{})})});
      detail();
      const updated=el('orderActionMessage');if(updated)updated.textContent='Ordine aggiornato.';
      load();
    }catch(err){
      const target=el('orderActionMessage');if(target)target.textContent=err.message||String(err);
      buttons.forEach(b=>b.disabled=false);
    }
  }

  function verifyFilters(){
    const result={};
    for(const [input,key] of [['ordersSearch','q'],['ordersStatus','status'],
      ['ordersSource','source_id'],['ordersFrom','date_from'],['ordersTo','date_to']]){
      const value=el(input)?.value;
      if(value)result[key]=key==='source_id'?Number(value):value;
    }
    return result;
  }
  async function bulkVerify(){
    if(bulkVerifying){
      stopBulkVerification=true;
      const note=el('ordersMessage');if(note)note.textContent='Interruzione richiesta: attendo la verifica in corso…';
      return;
    }
    if(!can('orders.update'))return;
    if(!confirm('Verificare gli indirizzi degli ordini nei filtri attuali? Il sistema riutilizza le verifiche già valide, ma i nuovi indirizzi possono consumare crediti API di geocodifica. Gli ordini validi diventeranno subito pianificabili.'))return;
    const button=el('ordersVerifyAll'),label=el('ordersVerifyAllLabel'),note=el('ordersMessage'),filters=verifyFilters();
    let after=0,processed=0,verified=0,already=0,failed=0,skipped=0,issues=[];
    bulkVerifying=true;stopBulkVerification=false;
    if(button){if(label)label.textContent='Interrompi verifica';button.setAttribute('aria-busy','true');}
    try{
      for(let batch=0;batch<1000&&!stopBulkVerification;batch++){
        const result=await orderApi('/api/orders/verify-addresses',{
          method:'POST',body:JSON.stringify({...filters,after_id:after,limit:10})
        });
        processed+=result.processed;
        verified+=result.verified;
        already+=result.already_verified;
        failed+=result.failed;
        skipped+=result.skipped||0;
        issues.push(...(result.issues||[]));
        if(note)note.textContent='Verifica indirizzi: '+processed+' esaminati, '+verified+' pronti, '+failed+' da correggere.';
        if(!result.has_more||!result.processed)break;
        if(result.next_after<=after)throw new Error('Impossibile avanzare con la verifica: riprova.');
        after=result.next_after;
      }
      const interrupted=stopBulkVerification;
      await load();
      let status=(interrupted?'Verifica interrotta. ':'Verifica completata. ')+verified+' ordini pronti, '+already+' già verificati, '+failed+' da correggere.'+(skipped?' '+skipped+' ordini non più disponibili ignorati.':'');
      if(issues.length)status+=' Apri gli ordini problematici: '+issues.slice(0,3).map(i=>'#'+i.order_id+' ('+i.reason+')').join('; ')+'.';
      if(note)note.textContent=status;
    }catch(err){
      await load().catch(()=>{});
      if(note)note.textContent='Verifica interrotta dopo '+processed+' ordini: '+(err.message||String(err))+'. '+verified+' verificati.';
    }finally{
      bulkVerifying=false;stopBulkVerification=false;
      if(button){if(label)label.textContent='Verifica indirizzi';button.removeAttribute('aria-busy');}
    }
  }

  function toggleFilters(force){
    const drawer=el('ordersFilterDrawer'),button=el('ordersFilterToggle');
    if(!drawer||!button)return;
    const open=typeof force==='boolean'?force:drawer.classList.contains('hidden');
    drawer.classList.toggle('hidden',!open);
    button.setAttribute('aria-expanded',String(open));
    button.classList.toggle('is-active',open);
  }
  const orderDialog=modal();
  if(orderDialog){
    orderDialog.addEventListener('click',event=>{if(event.target===orderDialog)closeModal();});
    orderDialog.addEventListener('cancel',event=>{event.preventDefault();closeModal();});
  }
  window.addEventListener('resize',syncActionPlacement);
  window.GFOrders={request:orderApi,bulkVerify,apply(value){current=value;detail();load();},currentItems:()=>last?.items||[],refreshSelection:render,load,open,newOrder,edit,cancelEdit,close:closeModal,save,action,cancel(){if(confirm('Annullare questo ordine? L’originale e lo storico saranno conservati.'))action('status','annullato');},search(){clearTimeout(timer);timer=setTimeout(()=>load(true),300);},page(delta){page+=delta;load();},view(mode){view=mode;render();},toggleFilters,syncActions:syncActionPlacement};
})();
