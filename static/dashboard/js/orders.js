/* Server-paginated order archive. All imported/customer text is escaped. */
(function(){
  'use strict';
  const labels={nuovo:'Da pianificare',da_verificare:'Da pianificare',pronto:'Da pianificare',assegnato:'Assegnato',in_consegna:'In consegna',consegnato:'Consegnato',non_consegnato:'Non consegnato',annullato:'Annullato'};
  // Stesse icone e stessi colori delle altre barre dei numeri (gf-stat-strip con icone).
  // Colori come nelle altre pagine: arrivati blu, da pianificare arancio (in attesa),
  // annullati rosso, già assegnati verde acqua (in un giro).
  const metricMeta={
    arrivati:{label:'Ordini arrivati',description:'Totale ordini ricevuti',tone:'1',icon:'<path d="M5 8h14l-1 12H6L5 8z M8.5 8a3.5 3.5 0 0 1 7 0"/>'},
    da_pianificare:{label:'Ordini da pianificare',description:'Ordini non ancora inseriti in un giro',tone:'5',icon:'<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2"/>'},
    annullato:{label:'Ordini annullati',description:'Ordini esclusi dalla pianificazione',tone:'4',icon:'<path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M9 9l6 6 M15 9l-6 6"/>'},
    assegnato:{label:'Già assegnati',description:'Ordini inseriti in un giro',tone:'2',icon:'<path d="M2 6h11v10H2z M13 9h5l3 3v4h-8z M6.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z M17.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z"/>'}
  };

  // Da pianificare in giallino, così non si confonde con «Assegnato» (azzurro).
  const statusTone={nuovo:'pending',da_verificare:'pending',pronto:'pending',assegnato:'info',in_consegna:'info',consegnato:'success',non_consegnato:'danger',annullato:'neutral'};
  const fields={number:'Numero ordine',recipient_name:'Destinatario',delivery_address:'Indirizzo di consegna',requested_date:'Data richiesta',time_from:'Fascia oraria: dalle',time_to:'Alle',weight_kg:'Peso (kg)',packages:'Colli',pallets:'Pallet',volume_m3:'Volume (m³)',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti operativi',notes:'Note'};
  const numeric=['weight_kg','packages','pallets','volume_m3'], bools=['tail_lift','pallet_truck','ztl'];
  let page=1, sequence=0, detailSequence=0, view='table', current=null, last=null, timer, modalScrollY=0, bulkVerifying=false, stopBulkVerification=false;
  const el=id=>document.getElementById(id);
  const can=key=>!window.GFCompanyAccess || GFCompanyAccess.can(key);
  const display=value=>value===null || value===undefined || value===''?'Non indicato':value===true?'Sì':value===false?'No':String(value);
  const date=value=>value?new Date(value+'Z').toLocaleString('it-IT'):'Non indicata';
  const receivedDate=value=>value?new Date(value+'Z').toLocaleString('it-IT',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):'Non indicata';
  const statusBadge=status=>`<span class="gf-badge" data-dot data-status="${statusTone[status]||'neutral'}">${esc(labels[status]||status)}</span>`;
  function syncActionPlacement(){
    const actions=el('ordersPageActions'), inline=el('ordersInlineActionsHost');
    if(!actions||!inline)return;
    if(actions.parentNode!==inline)inline.appendChild(actions);
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
      el('ordersMetrics').innerHTML=Object.entries(metricMeta).map(([key,meta])=>`<div class="gf-stat-strip__cell"><span class="gf-stat-strip__icon" data-tone="${meta.tone}" aria-hidden="true"><svg viewBox="0 0 24 24">${meta.icon}</svg></span><span class="gf-stat-strip__label">${meta.label}</span><strong class="gf-stat-strip__value">${Number(data.metrics[key]||0)}</strong><small class="gf-stat-strip__unit">${meta.description}</small></div>`).join('');
      const selected=el('ordersSource').value;
      el('ordersSource').innerHTML='<option value="">Tutte le fonti</option>'+data.sources.map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('');el('ordersSource').value=selected;
      render();
      if(data.total){
        const first=(page-1)*25+1,end=Math.min(page*25,data.total);
        el('ordersMessage').textContent=`Vista ${first}–${end} di ${data.total} ordini`;
      }else el('ordersMessage').textContent='Nessun ordine trovato. Crea un ordine oppure modifica i filtri.';
    }catch(err){if(request===sequence){el('ordersResults').replaceChildren();error('ordersMessage',err);}}
    finally{if(request===sequence)el('ordersResults').setAttribute('aria-busy','false');}
  }
  function accessBadges(o){
    const badges=[];
    if(o.ztl_notice)badges.push('<span class="gf-badge" data-kind="ztl" title="Attenzione: cliente in zona ZTL">ZTL</span>');
    if(o.pedestrian_area)badges.push('<span class="gf-badge" data-status="warning" title="Attenzione: cliente in area pedonale">Area pedonale</span>');
    return badges.length?'<div class="gf-cluster" data-gap="xs">'+badges.join(' ')+'</div>':'';
  }
  function render(){
    if(!last)return;
    const open=o=>`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFOrders.open(${o.id})" aria-label="Apri ordine ${esc(o.number)}">Apri</button>`;
    if(view==='cards'){
      el('ordersResults').innerHTML='<div class="gf-panel__body gf-grid" data-cols="3">'+last.items.map(o=>`<article class="gf-card gf-stack" aria-selected="${!!window.GFOrderPlanning?.isSelected(o.id)}"><div class="gf-cluster" data-justify="between"><span>${window.GFOrderPlanning?.checkbox(o)||""}</span>${statusBadge(o.status)}</div><h2 class="gf-subtitle">${esc(o.number)}</h2><p><strong>${esc(display(o.recipient_name))}</strong></p><p>${esc(display(o.delivery_address))}</p>${accessBadges(o)}<p class="gf-muted">${esc(o.source_name)} · ${esc(display(o.requested_date))}</p><p class="gf-muted">${o.packages==null?'— colli':gfCount(o.packages,'collo','colli')} · ${o.weight_kg==null?'—':gfDecimal(o.weight_kg)} kg</p><div>${open(o)}</div></article>`).join('')+'</div>';
    }else{
      const selectAll=window.GFOrderPlanning?.headerCheckbox(last.items)||'';
      el('ordersResults').innerHTML='<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards"><thead><tr><th scope="col" aria-label="Seleziona">'+selectAll+'</th><th scope="col">Numero ordine</th><th scope="col">Ricevuto</th><th scope="col">Cliente / destinatario</th><th scope="col">Indirizzo</th><th scope="col">Stato</th><th scope="col">Azioni</th></tr></thead><tbody>'+last.items.map(o=>`<tr aria-selected="${!!window.GFOrderPlanning?.isSelected(o.id)}"><td data-label="Seleziona">${window.GFOrderPlanning?.checkbox(o)||""}</td><td data-label="Numero ordine"><strong>${esc(o.number)}</strong></td><td data-label="Ricevuto">${esc(receivedDate(o.received_at))}</td><td data-label="Cliente / destinatario"><strong>${esc(display(o.recipient_name))}</strong></td><td data-label="Indirizzo">${esc(display(o.delivery_address))}${accessBadges(o)}</td><td data-label="Stato">${statusBadge(o.status)}</td><td data-label="Azioni">${open(o)}</td></tr>`).join('')+'</tbody></table></div>';
    }
    const totalPages=Math.max(1,Math.ceil(last.total/25));
    el('ordersPage').textContent=String(page);
    el('ordersPage').setAttribute('aria-label',`Pagina ${page} di ${totalPages}`);
    el('ordersPage').title=`Pagina ${page} di ${totalPages}`;
    el('ordersPrevious').disabled=page<=1;el('ordersNext').disabled=page*25>=last.total;
    for(const mode of ['table','cards'])el('ordersView-'+mode).setAttribute('aria-pressed',String(mode===view));
  }
  function form(data={}){
    el('orderFormFields').innerHTML=Object.entries(fields).map(([key,label])=>{
      const value=data[key], id='orderField-'+key;
      if(bools.includes(key))return `<label class="gf-field" for="${id}"><span class="gf-field__label">${label}</span><select class="gf-select" id="${id}" name="${key}"><option value="">Non indicato</option><option value="true" ${value===true?'selected':''}>Sì</option><option value="false" ${value===false?'selected':''}>No</option></select></label>`;
      if(['notes','requirements'].includes(key))return `<label class="gf-field" data-span="full" for="${id}"><span class="gf-field__label">${label}</span><textarea class="gf-textarea" id="${id}" name="${key}" maxlength="${key==='notes'?5000:2000}">${esc(value||'')}</textarea></label>`;
      const type=numeric.includes(key)?'number':key==='requested_date'?'date':key.startsWith('time_')?'time':'text';
      return `<label class="gf-field" for="${id}"><span class="gf-field__label">${label}</span><input class="gf-input" id="${id}" name="${key}" type="${type}" value="${esc(value??'')}" ${key==='number'?'required maxlength="160"':key==='recipient_name'?'maxlength="200"':key==='delivery_address'?'maxlength="500"':''} ${type==='number'?`min="0" max="${key==='packages'?1000000:100000000}" step="${key==='packages'?1:'any'}"`:''}></label>`;
    }).join('');
    // Keep the everyday workflow compact; optional logistics remain available on demand.
    const container=el('orderFormFields');
    const basic=document.createElement('div');
    basic.className='gf-form-grid';
    const optional=document.createElement('details');
    optional.className='gf-panel';
    optional.dataset.orderFormOptional='';
    const title=document.createElement('summary');
    title.className='gf-panel__header';
    title.textContent='Altre informazioni (facoltative)';
    const otherFields=document.createElement('div');
    otherFields.className='gf-panel__body gf-form-grid';
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
    el('orderModalContent').innerHTML=`<header class="gf-modal__header">
        <div><h2 class="gf-modal__title" id="orderModalTitle">${title}</h2><p class="gf-muted">${creating?'Inserisci i dati disponibili per creare un nuovo ordine.':'Aggiorna i dati operativi. I dati originali ricevuti restano conservati nello storico.'}</p></div>
        <button class="gf-icon-button" type="button" data-order-modal-close onclick="GFOrders.close()" aria-label="Chiudi"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
      </header>
      <form onsubmit="GFOrders.save(event)">
        <div class="gf-modal__body gf-stack"><div id="orderFormFields" class="gf-stack"></div>
        <div class="gf-field" data-invalid><p id="orderEditorError" class="gf-field__error" role="alert"></p></div></div>
        <footer class="gf-modal__footer">
          <button class="gf-button" data-variant="secondary" type="button" onclick="GFOrders.cancelEdit()">Annulla</button>
          <button id="orderSave" class="gf-button" data-variant="primary" type="submit">${creating?'Crea ordine':'Salva modifiche'}</button>
        </footer>
      </form>`;
    showOrderModal();form(data);el('orderEditorError').textContent='';
  }
  function newOrder(){++detailSequence;current=null;renderEditor({},true);}
  async function open(id){
    const request=++detailSequence;
    el('orderModalContent').innerHTML='<div class="gf-loading" role="status">Caricamento ordine…</div>';
    showOrderModal();
    try{const result=await orderApi('/api/orders/'+id);if(request!==detailSequence)return;current=result;detail();}
    catch(err){if(request===detailSequence)el('orderModalContent').innerHTML=`<div class="gf-modal__body gf-stack"><div class="gf-alert" data-status="danger">${esc(err.message||String(err))}</div><div><button type="button" class="gf-button" data-variant="secondary" onclick="GFOrders.close()">Chiudi</button></div></div>`;}
  }
  function changes(event){
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
    return ({received:'Acquisizione ordine',source_updated:'Aggiornamento dalla fonte',route_status:'Stato consegna',route_released:'Rimosso dal giro',route_snapshot:'Fermata salvata',created:'Creazione ordine',corrected:'Modifica dati',address_verified:'Indirizzo verificato',status_changed:'Cambio stato'})[kind]||kind;
  }
  function detail(){
    const o=current;if(!o)return;
    const data=o.operational_data||{};
    const allowed=can('orders.update') && ['nuovo','da_verificare','pronto'].includes(o.status) && !o.assignments.length;
    const verified=!!o.address_verification&&!o.anomalies?.some(a=>a.code==='verification');
    const requested=data.requested_date?esc(gfDateIt(data.requested_date)):'Non indicata';
    const hhmm=t=>String(t||'—').slice(0,5);
    const timeRange=data.time_from||data.time_to?`${esc(hhmm(data.time_from))} – ${esc(hhmm(data.time_to))}`:'Non indicata';
    const boolValue=value=>value===true?'Sì':value===false?'No':'N/D';
    const sourceChip=`<span class="gf-badge" data-status="neutral">${esc(o.source_name)}</span>`;
    const items=o.items?.length?o.items.map((item,index)=>`<div class="gf-details__item"><dt>${esc(item.description||item.name||`Articolo ${index+1}`)}</dt><dd><strong>${esc(display(item.quantity))}</strong></dd></div>`).join(''):'<p class="gf-muted">Nessun articolo indicato.</p>';
    const notes=data.notes?`<p>“${esc(data.notes)}”</p>`:'<p class="gf-muted">Nessuna nota ordine.</p>';
    const addressText=esc(display(data.delivery_address));
    const actionCard=!verified
      ?`<section class="gf-alert" data-status="warning"><div class="gf-alert__body">
            <p class="gf-kicker">Azione necessaria</p>
            <strong class="gf-alert__title">Indirizzo da confermare</strong>
            <p>Verifica l’indirizzo “${addressText}”. Se è valido, l’ordine diventa subito pianificabile.</p>
            ${allowed?'<div><button type="button" class="gf-button" data-variant="primary" data-size="sm" onclick="GFOrders.action(\'verify-address\')">Verifica indirizzo ora</button></div>':''}
        </div></section>`
      :`<section class="gf-alert" data-status="success"><div class="gf-alert__body">
            <strong class="gf-alert__title">${o.address_verification?.confirmed_manually?'Posizione confermata manualmente':'✓ Verifica completata'}</strong>
            <p>${o.address_verification?.confirmed_manually?'La posizione è stata scelta e confermata da un operatore.':'L’indirizzo di consegna è stato verificato ed è pronto per la pianificazione.'}</p>
        </div></section>`;
    const readyButton=''; // Verification makes the order ready without confirmation.
    const editButton=allowed?'<button type="button" class="gf-button" data-variant="primary" onclick="GFOrders.edit()">Modifica dati</button>':'';
    const cancelButton=allowed?'<button type="button" class="gf-button" data-variant="ghost" onclick="GFOrders.cancel()">Annulla ordine</button>':'';
    const item=(label,value)=>`<div class="gf-details__item"><dt>${label}</dt><dd><strong>${value}</strong></dd></div>`;

    el('orderModalContent').innerHTML=`
      <header class="gf-modal__header">
        <div>
          <div class="gf-cluster"><h2 class="gf-modal__title" id="orderModalTitle">${esc(o.number)}</h2>${statusBadge(o.status)}${sourceChip}</div>
          <p class="gf-muted">Acquisito il ${esc(date(o.received_at))}</p>
        </div>
        <button class="gf-icon-button" type="button" data-order-modal-close onclick="GFOrders.close()" aria-label="Chiudi"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
      </header>
      <div class="gf-modal__body gf-stack">
        <p id="orderActionMessage" class="gf-muted" role="status"></p>
        <div class="gf-grid" data-cols="main-side">
          <div class="gf-stack">
            <section class="gf-panel">
              <header class="gf-panel__header"><h3 class="gf-panel__title">Dati di consegna</h3></header>
              <div class="gf-panel__body"><dl class="gf-details">
                ${item('Destinatario',esc(display(data.recipient_name)))}${item('Indirizzo di consegna',addressText+accessBadges(o))}${item('Data richiesta',requested)}${item('Fascia oraria',timeRange)}
              </dl></div>
            </section>
            <section class="gf-panel">
              <header class="gf-panel__header"><h3 class="gf-panel__title">Specifiche merce e logistica</h3></header>
              <div class="gf-panel__body"><dl class="gf-details">
                ${item('Peso (kg)',esc(display(data.weight_kg)))}${item('Colli',esc(display(data.packages)))}${item('Pallet',esc(display(data.pallets)))}${item('Volume (m³)',esc(display(data.volume_m3)))}
                ${item('Sponda idraulica',boolValue(data.tail_lift))}${item('Transpallet',boolValue(data.pallet_truck))}${item('Permesso ZTL',boolValue(data.ztl))}${item('Req. operativi',esc(display(data.requirements)))}
              </dl></div>
            </section>
            <div class="gf-grid" data-cols="2">
              <section class="gf-panel">
                <header class="gf-panel__header"><h3 class="gf-panel__title">Distinta articoli</h3><span class="gf-panel__meta">${o.items?.length||0} ${(o.items?.length||0)===1?'riga':'righe'}</span></header>
                <div class="gf-panel__body"><dl class="gf-details">${items}</dl></div>
              </section>
              <section class="gf-panel">
                <header class="gf-panel__header"><h3 class="gf-panel__title">Note ordine</h3></header>
                <div class="gf-panel__body">${notes}</div>
              </section>
            </div>
          </div>
          <aside>${actionCard}</aside>
        </div>
      </div>
      <footer class="gf-modal__footer">
        <div class="gf-cluster">${cancelButton}</div>
        <div class="gf-cluster">
          <button type="button" class="gf-button" data-variant="secondary" onclick="GFOrders.close()">Chiudi</button>
          ${readyButton}
          ${editButton}
        </div>
      </footer>`;
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
  }
  const orderDialog=modal();
  if(orderDialog){
    orderDialog.addEventListener('click',event=>{if(event.target===orderDialog)closeModal();});
    orderDialog.addEventListener('cancel',event=>{event.preventDefault();closeModal();});
  }
  window.addEventListener('resize',syncActionPlacement);
  window.GFOrders={request:orderApi,bulkVerify,apply(value){current=value;detail();load();},currentItems:()=>last?.items||[],refreshSelection:render,load,open,newOrder,edit,cancelEdit,close:closeModal,save,action,cancel(){if(confirm('Annullare questo ordine? L’originale e lo storico saranno conservati.'))action('status','annullato');},search(){clearTimeout(timer);timer=setTimeout(()=>load(true),300);},page(delta){page+=delta;load();},view(mode){view=mode;render();},toggleFilters,syncActions:syncActionPlacement};
})();
