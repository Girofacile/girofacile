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

  // Da pianificare come «In servizio» della Dashboard, così non si confonde con «Assegnato» (azzurro); annullato in rosso chiaro.
  const statusTone={nuovo:'warning',da_verificare:'warning',pronto:'warning',assegnato:'info',in_consegna:'info',consegnato:'success',non_consegnato:'danger',annullato:'danger'};
  const fields={number:'Numero ordine',recipient_name:'Destinatario',phone:'Telefono destinatario',street:'Via',street_number:'Civico',postal_code:'CAP',city:'Comune',requested_date:'Data richiesta',time_from:'Fascia oraria: dalle',time_to:'Alle',weight_kg:'Peso (kg)',packages:'Colli',pallets:'Pallet',volume_m3:'Volume (m³)',tail_lift:'Sponda idraulica',pallet_truck:'Transpallet',requirements:'Requisiti operativi',notes:'Note ordine'};
  // Etichette anche dei campi che non sono nel modulo (storico delle modifiche, errori).
  const labelOf=key=>fields[key]||({delivery_address:'Indirizzo di consegna',province:'Provincia',ztl:'ZTL'})[key];
  const numeric=['weight_kg','packages','pallets','volume_m3'], bools=['tail_lift','pallet_truck'];
  let page=1, sequence=0, detailSequence=0, view='table', current=null, last=null, timer, modalScrollY=0, bulkVerifying=false, stopBulkVerification=false, dirty=false, snapshot=null;
  const el=id=>document.getElementById(id);
  const can=key=>!window.GFCompanyAccess || GFCompanyAccess.can(key);
  const display=value=>value===null || value===undefined || value===''?'Non indicato':value===true?'Sì':value===false?'No':String(value);
  const date=value=>value?new Date(value+'Z').toLocaleString('it-IT'):'Non indicata';
  const receivedDate=value=>value?new Date(value+'Z').toLocaleString('it-IT',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):'Non indicata';
  const statusBadge=(status,problem)=>problem&&['nuovo','da_verificare','pronto'].includes(status)
    ?'<span class="gf-badge" data-dot data-status="danger" data-order-problem>Indirizzo da correggere</span>'
    :`<span class="gf-badge" data-dot data-status="${statusTone[status]||'neutral'}">${esc(labels[status]||status)}</span>`;
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
      if(Array.isArray(message))message=message.map(e=>`${labelOf(e.loc?.[1])||'Dati ordine'}: ${e.msg?.startsWith('Value error, ')?e.msg.slice(13):'verifica formato, limiti e campi obbligatori.'}`).join('\n');
      // Alcuni errori arrivano come oggetto con il motivo (es. indirizzo trovato solo come zona).
      if(message&&typeof message==='object'&&typeof message.message==='string')message=message.message;
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
      el('ordersResults').innerHTML='<div class="gf-panel__body gf-grid" data-cols="3">'+last.items.map(o=>`<article class="gf-card gf-stack" aria-selected="${!!window.GFOrderPlanning?.isSelected(o.id)}"><div class="gf-cluster" data-justify="between"><span>${window.GFOrderPlanning?.checkbox(o)||""}</span>${statusBadge(o.status,o.address_problem)}</div><h2 class="gf-subtitle">${esc(o.number)}</h2><p><strong>${esc(display(o.recipient_name))}</strong></p><p>${esc(display(o.delivery_address))}</p>${accessBadges(o)}<p class="gf-muted">${esc(o.source_name)} · ${esc(display(o.requested_date))}</p><p class="gf-muted">${o.packages==null?'— colli':gfCount(o.packages,'collo','colli')} · ${o.weight_kg==null?'—':gfDecimal(o.weight_kg)} kg</p><div>${open(o)}</div></article>`).join('')+'</div>';
    }else{
      const selectAll=window.GFOrderPlanning?.headerCheckbox(last.items)||'';
      el('ordersResults').innerHTML='<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards"><thead><tr><th scope="col" aria-label="Seleziona">'+selectAll+'</th><th scope="col">Numero ordine</th><th scope="col">Ricevuto</th><th scope="col">Cliente / destinatario</th><th scope="col">Indirizzo</th><th scope="col">Stato</th><th scope="col">Azioni</th></tr></thead><tbody>'+last.items.map(o=>`<tr aria-selected="${!!window.GFOrderPlanning?.isSelected(o.id)}"><td data-label="Seleziona">${window.GFOrderPlanning?.checkbox(o)||""}</td><td data-label="Numero ordine"><strong>${esc(o.number)}</strong></td><td data-label="Ricevuto">${esc(receivedDate(o.received_at))}</td><td data-label="Cliente / destinatario"><strong>${esc(display(o.recipient_name))}</strong></td><td data-label="Indirizzo">${esc(display(o.delivery_address))}${accessBadges(o)}</td><td data-label="Stato">${statusBadge(o.status,o.address_problem)}</td><td data-label="Azioni">${open(o)}</td></tr>`).join('')+'</tbody></table></div>';
    }
    const totalPages=Math.max(1,Math.ceil(last.total/25));
    el('ordersPage').textContent=String(page);
    el('ordersPage').setAttribute('aria-label',`Pagina ${page} di ${totalPages}`);
    el('ordersPage').title=`Pagina ${page} di ${totalPages}`;
    el('ordersPrevious').disabled=page<=1;el('ordersNext').disabled=page*25>=last.total;
    for(const mode of ['table','cards'])el('ordersView-'+mode).setAttribute('aria-pressed',String(mode===view));
  }
  function fieldHtml(key,value){
    const label=fields[key], id='orderField-'+key;
    if(bools.includes(key))return `<label class="gf-field" for="${id}"><span class="gf-field__label">${label}</span><select class="gf-select" id="${id}" name="${key}"><option value="">Non indicato</option><option value="true" ${value===true?'selected':''}>Sì</option><option value="false" ${value===false?'selected':''}>No</option></select></label>`;
    if(['notes','requirements'].includes(key))return `<label class="gf-field" for="${id}"><span class="gf-field__label">${label}</span><textarea class="gf-textarea" id="${id}" name="${key}" maxlength="${key==='notes'?5000:2000}">${esc(value||'')}</textarea></label>`;
    const type=numeric.includes(key)?'number':key==='requested_date'?'date':key.startsWith('time_')?'time':key==='phone'?'tel':'text';
    return `<label class="gf-field" for="${id}"><span class="gf-field__label">${label}</span><input class="gf-input" id="${id}" name="${key}" type="${type}" value="${esc(value??'')}" ${key==='number'?'required maxlength="160"':key==='recipient_name'?'maxlength="200"':key==='street'?'maxlength="300" autocomplete="off"':key==='street_number'?'maxlength="20" autocomplete="off"':key==='postal_code'?'maxlength="5" inputmode="numeric" pattern="\\d{5}" autocomplete="off"':key==='city'?'maxlength="150" autocomplete="off"':''} ${type==='number'?`min="0" max="${key==='packages'?1000000:100000000}" step="${key==='packages'?1:'any'}"`:''}></label>`;
  }
  const group=(keys,data)=>'<div class="gf-form-grid">'+keys.map(k=>fieldHtml(k,data[k])).join('')+'</div>';
  const card=(title,body,meta='')=>`<section class="gf-card gf-stack" data-gap="sm"><div class="gf-cluster" data-justify="between"><h3 class="gf-subtitle">${title}</h3>${meta}</div>${body}</section>`;
  // Stato dell'indirizzo nella scheda «Indirizzo»: la verifica è automatica, nessun tasto.
  function addressState(o){
    if(!o)return {badge:'',note:''};
    const access=accessBadges(o);
    if(o.address_problem)return {badge:'<span class="gf-badge" data-status="danger" data-dot data-order-problem>Indirizzo da correggere</span>',
      note:`<div class="gf-field" data-invalid><p class="gf-field__error" data-order-problem>${esc(o.address_problem.message||'Google non ha trovato questo indirizzo.')} Correggi i campi e salva: l’indirizzo si riverifica da solo.</p></div>`+access};
    const verified=!!o.address_verification&&!o.anomalies?.some(a=>a.code==='verification');
    if(verified){
      const manual=o.address_verification?.confirmed_manually;
      return {badge:`<span class="gf-badge" data-status="success" data-dot>${manual?'Posizione confermata':'Indirizzo verificato'}</span>`,
        note:`<p class="gf-field__hint">${manual?'Posizione scelta e confermata da un operatore.':'Verificato in automatico: '+esc(o.address_verification?.indirizzo||o.operational_data?.delivery_address||'')+'.'} Se cambi l’indirizzo si riverifica al salvataggio; anche la ZTL si rileva da sola.</p>`+access};
    }
    return {badge:'<span class="gf-badge" data-status="neutral" data-dot>Da verificare</span>',
      note:'<p class="gf-field__hint">Si verifica da solo quando salvi un indirizzo nuovo o metti l’ordine in un giro; anche la ZTL si rileva da sola.</p>'+access};
  }
  // Variante A (16/11/2026): un solo pop-up già modificabile, a due colonne; distinta apribile sotto.
  function form(data={},o=null){
    const state=addressState(o);
    const items=o?.items||[];
    const itemsHtml=items.length?`<details class="gf-card" data-order-items><summary><strong>Distinta articoli</strong> <span class="gf-muted">· ${gfCount(items.length,'riga','righe')}</span></summary><dl class="gf-details" data-layout="rows">${items.map((item,index)=>`<div class="gf-details__item"><dt>${esc(item.description||item.name||`Articolo ${index+1}`)}</dt><dd>${esc(display(item.quantity))}</dd></div>`).join('')}</dl></details>`:'';
    el('orderFormFields').innerHTML=`<div class="gf-grid" data-cols="2">
        <div class="gf-stack">
          ${card('Destinatario',group(['number','recipient_name','phone'],data))}
          ${card('Indirizzo',`<fieldset class="gf-fieldset gf-stack" data-gap="sm" data-order-address><legend class="gf-field__label" hidden>Indirizzo di consegna</legend>${group(['street','street_number','postal_code','city'],data)}<p class="gf-field__hint" data-order-address-exact></p><input type="hidden" name="province" value="${esc(data.province||'')}"></fieldset>${state.note}`,state.badge)}
          ${card('Consegna',group(['requested_date','time_from','time_to'],data))}
        </div>
        <div class="gf-stack">
          ${card('Merce',group(['packages','weight_kg','pallets','volume_m3'],data))}
          ${card('Mezzo',group(['tail_lift','pallet_truck'],data))}
          ${card('Note',group(['requirements','notes'],data))}
        </div>
      </div>${itemsHtml}`;
    // Sotto i campi dell'indirizzo, l'indirizzo esatto che arriverà a Google per la verifica.
    const box=el('orderFormFields').querySelector('[data-order-address]'),exact=box.querySelector('[data-order-address-exact]');
    const preview=()=>{
      const part=name=>(box.querySelector(`[name="${name}"]`)?.value||'').trim();
      const line=[[part('street'),part('street_number')].filter(Boolean).join(' '),[part('postal_code'),part('city'),part('province')].filter(Boolean).join(' ')].filter(Boolean).join(', ');
      exact.innerHTML=line?`Verifichiamo esattamente: <strong>${esc(line)}</strong>`:'Indica via, civico, CAP e comune: li verifichiamo così come li scrivi.';
    };
    box.addEventListener('input',preview);preview();
  }
  // «Salva modifiche» solo quando un campo cambia davvero (come la pagina Azienda).
  const formValues=()=>{const f=el('orderForm');return f?JSON.stringify([...new FormData(f)]):null;};
  function trackChanges(){
    const f=el('orderForm');snapshot=formValues();dirty=false;
    if(!f||f.dataset.creating)return;
    const update=()=>{
      dirty=formValues()!==snapshot;
      const clean=el('orderModalContent').querySelector('[data-order-clean]'),changed=el('orderModalContent').querySelector('[data-order-dirty]');
      if(clean)clean.hidden=dirty;if(changed)changed.hidden=!dirty;
      if(!dirty&&el('orderEditorError'))el('orderEditorError').textContent='';
    };
    f.addEventListener('input',update);f.addEventListener('change',update);
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
  function closeModal(force=false){
    // Con modifiche non salvate bisogna scegliere «Salva modifiche» o «Annulla modifiche».
    if(dirty&&force!==true){
      const message=el('orderEditorError');
      if(message)message.textContent='Hai modifiche non salvate: scegli «Salva modifiche» oppure «Annulla modifiche».';
      el('orderSave')?.focus();
      return;
    }
    dirty=false;
    const dialog=modal();
    ++detailSequence;
    if(dialog?.open)dialog.close();
    document.documentElement.classList.remove('order-modal-open');
    requestAnimationFrame(()=>window.scrollTo({top:modalScrollY,left:0,behavior:'auto'}));
    current=null;
  }
  function renderEditor(data={},creating=false){
    const o=creating?null:current;
    const editable=creating||(can('orders.update')&&['nuovo','da_verificare','pronto'].includes(o?.status)&&!o?.assignments?.length);
    const close='<button class="gf-icon-button" type="button" data-order-modal-close onclick="GFOrders.close()" aria-label="Chiudi"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>';
    const header=creating
      ?`<header class="gf-modal__header"><div><h2 class="gf-modal__title" id="orderModalTitle">Nuovo ordine</h2><p class="gf-muted">Inserisci i dati disponibili per creare un nuovo ordine.</p></div>${close}</header>`
      :`<header class="gf-modal__header"><div><div class="gf-cluster"><h2 class="gf-modal__title" id="orderModalTitle">${esc(o.number)}</h2>${statusBadge(o.status,o.address_problem)}<span class="gf-badge" data-status="neutral">${esc(o.source_name)}</span></div><p class="gf-muted">${esc(display(data.recipient_name))} · ricevuto il ${esc(receivedDate(o.received_at))}</p></div>${close}</header>`;
    const cancelOrder=!creating&&editable?'<button type="button" class="gf-button" data-variant="danger" onclick="GFOrders.cancel()">Annulla ordine</button>':'';
    const actions=creating
      ?'<div class="gf-cluster"><button class="gf-button" data-variant="secondary" type="button" onclick="GFOrders.close(true)">Annulla</button><button id="orderSave" class="gf-button" data-variant="primary" type="submit">Crea ordine</button></div>'
      :`<div class="gf-cluster" data-order-clean><button type="button" class="gf-button" data-variant="secondary" onclick="GFOrders.close()">Chiudi</button></div>
        <div class="gf-cluster" data-order-dirty hidden role="status" aria-live="polite"><span class="gf-muted">Modifiche non salvate</span><button type="button" class="gf-button" data-variant="secondary" onclick="GFOrders.cancelEdit()">Annulla modifiche</button><button id="orderSave" class="gf-button" data-variant="primary" type="submit">Salva modifiche</button></div>`;
    el('orderModalContent').innerHTML=`${header}
      <form id="orderForm" onsubmit="GFOrders.save(event)"${creating?' data-creating="1"':''}>
        <div class="gf-modal__body gf-stack" data-gap="lg">
          <p id="orderActionMessage" class="gf-muted" role="status" hidden></p>
          <fieldset class="gf-fieldset" ${editable?'':'disabled'}><legend class="gf-field__label" hidden>Dati dell’ordine</legend><div id="orderFormFields" class="gf-stack"></div></fieldset>
          <div class="gf-field" data-invalid><p id="orderEditorError" class="gf-field__error" role="alert"></p></div>
        </div>
        <footer class="gf-modal__footer gf-cluster" data-justify="between"><span>${cancelOrder}</span>${actions}</footer>
      </form>`;
    showOrderModal();form(data,o);trackChanges();
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
    if(event.kind==='corrected')return Object.entries(event.changes).map(([key,value])=>`<p>${labelOf(key)||esc(key)}: ${esc(display(value.before))} → ${esc(display(value.after))}</p>`).join('');
    if(event.kind==='status_changed')return `<p>${labels[event.changes.before]||event.changes.before} → ${labels[event.changes.after]||event.changes.after}</p>`;
    if(event.kind==='address_verified')return `<p>${esc(event.changes.address)}</p>`;
    if(event.kind==='route_status')return `<p>Giro #${esc(event.changes.route_id)}: ${esc(labels[event.changes.before]||event.changes.before)} → ${esc(labels[event.changes.after]||event.changes.after)}</p>`;
    if(event.kind==='route_released')return `<p>Ordine rimosso dal giro #${esc(event.changes.route_id)} e nuovamente disponibile.</p>`;
    if(event.kind==='route_snapshot')return `<p>Dati della fermata salvati nel giro #${esc(event.changes.route_id)}.</p>`;
    if(event.kind==='received')return '<p>Ordine ricevuto dalla fonte collegata.</p>';
    if(event.kind==='source_updated')return `<p>Aggiornamento dalla fonte. Correzioni manuali conservate: ${esc((event.changes.preserved_corrections||[]).map(k=>labelOf(k)||k).join(', ')||'nessuna')}.</p>`;
    return '<p>Inserimento manuale</p>';
  }
  function eventLabel(kind){
    return ({received:'Acquisizione ordine',source_updated:'Aggiornamento dalla fonte',route_status:'Stato consegna',route_released:'Rimosso dal giro',route_snapshot:'Fermata salvata',created:'Creazione ordine',corrected:'Modifica dati',address_verified:'Indirizzo verificato',status_changed:'Cambio stato'})[kind]||kind;
  }
  function detail(){
    if(!current)return;
    renderEditor(current.operational_data||{},false);
  }
  // Compatibilità: «Modifica» porta al primo campo; «Annulla modifiche» rimette i valori salvati.
  function edit(){if(!current)return;el('orderField-number')?.focus();}
  function cancelEdit(){dirty=false;current?detail():closeModal(true);}
  async function save(event){
    event.preventDefault();const data={};
    for(const [key,value] of new FormData(event.target))data[key]=value===''?null:numeric.includes(key)?Number(value):bools.includes(key)?value==='true':value;
    const editing=!!current;if(editing)data.version=current.version;
    const ADDRESS=['street','street_number','postal_code','city'];
    const before=current?.operational_data||{};
    const addressChanged=!editing||ADDRESS.some(k=>String(before[k]??'')!==String(data[k]??''))||!!current?.address_problem;
    el('orderSave').disabled=true;el('orderEditorError').textContent='';
    try{
      current=await orderApi('/api/orders'+(editing?'/'+current.id:''),{method:editing?'PUT':'POST',body:JSON.stringify(data)});
      dirty=false;
      if(addressChanged&&!current.address_verification&&can('orders.update')){
        // Verifica automatica: se Google non trova l'indirizzo, il problema compare nella scheda «Indirizzo».
        try{current=await orderApi(`/api/orders/${current.id}/verify-address`,{method:'POST',body:JSON.stringify({version:current.version})});}
        catch(e){try{current=await orderApi(`/api/orders/${current.id}`);}catch(_){}}
      }
      detail();
      const done=el('orderActionMessage');if(done){done.hidden=false;done.textContent=editing?'Modifiche salvate.':'Ordine creato.';}
      load();
    }catch(err){error('orderEditorError',err);}
    finally{if(el('orderSave'))el('orderSave').disabled=false;}
  }
  async function action(action,status){
    if(!current)return;
    const root=el('orderModalContent'),buttons=root.querySelectorAll('button');buttons.forEach(b=>b.disabled=true);
    const message=el('orderActionMessage');if(message){message.hidden=false;message.textContent='Operazione in corso…';}
    try{
      current=await orderApi(`/api/orders/${current.id}/${action}`,{method:'POST',body:JSON.stringify({version:current.version,...(status?{status}:{})})});
      detail();
      const updated=el('orderActionMessage');if(updated){updated.hidden=false;updated.textContent='Ordine aggiornato.';}
      load();
    }catch(err){
      // Verifica non riuscita: il server ha registrato il problema, si ricarica l'ordine per mostrarlo.
      if(action==='verify-address'){
        try{current=await orderApi(`/api/orders/${current.id}`);detail();load();}catch(e){}
      }
      const target=el('orderActionMessage');if(target){target.hidden=false;target.textContent=err.message||String(err);}
      el('orderModalContent')?.querySelectorAll('button').forEach(b=>b.disabled=false);
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
  // Clic sulla riga (o sulla card) di un ordine: lo seleziona per la pianificazione. «Apri» mostra i dettagli.
  document.addEventListener('click',event=>{
    const t=event.target,row=t?.closest?.('#ordersResults tr, #ordersResults article');
    if(!row||t.closest('button,a,input,select,label,textarea,summary')||String(window.getSelection?.()||''))return;
    row.querySelector('input.order-select:not(:disabled)')?.click();
  });
  const orderDialog=modal();
  if(orderDialog){
    orderDialog.addEventListener('click',event=>{if(event.target===orderDialog)closeModal();});
    orderDialog.addEventListener('cancel',event=>{event.preventDefault();closeModal();});
    // Esc gestito prima del browser: con modifiche non salvate il pop-up resta aperto
    // (Chrome può ignorare preventDefault sull'evento «cancel» senza un'azione recente dell'utente).
    orderDialog.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();closeModal();}});
  }
  window.addEventListener('resize',syncActionPlacement);
  window.GFOrders={request:orderApi,bulkVerify,apply(value){current=value;detail();load();},currentItems:()=>last?.items||[],refreshSelection:render,load,open,newOrder,edit,cancelEdit,close:closeModal,save,action,cancel(){if(confirm('Annullare questo ordine? L’originale e lo storico saranno conservati.'))action('status','annullato');},search(){clearTimeout(timer);timer=setTimeout(()=>load(true),300);},page(delta){page+=delta;load();},view(mode){view=mode;render();},toggleFilters,syncActions:syncActionPlacement};
})();
