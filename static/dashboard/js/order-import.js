/* File import is independent of the technical API connection settings. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id),can=k=>!window.GFCompanyAccess||GFCompanyAccess.can(k);
  const labels={number:'Numero ordine',recipient_name:'Destinatario',phone:'Telefono',delivery_address:'Indirizzo',requested_date:'Data consegna',packages:'Colli',weight_kg:'Peso',external_id:'Codice univoco',external_customer_id:'Codice cliente',time_from:'Dalle',time_to:'Alle',pallets:'Pallet',volume_m3:'Volume',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti',notes:'Note',items:'Articoli'};
  let sources=[],fields=[],source=null,stage=null,report=null,mapping={},excluded=[],busy=false,filename='';
  const post=value=>({method:'POST',body:JSON.stringify(value)});
  async function api(path,options={}){
    const res=await fetch('/api/order-sources'+path,{...options,headers:options.body instanceof FormData?{}:{'Content-Type':'application/json'}}),data=await res.json();
    if(!res.ok&&!data.report)throw new Error(typeof data.detail==='string'?data.detail:'Controlla i dati e riprova.');return data;
  }
  async function work(callback){
    if(busy)return;busy=true;el('orderImportMessage').textContent='';
    const buttons=[...el('orderImportDialog').querySelectorAll('button')].filter(b=>!b.disabled);buttons.forEach(b=>b.disabled=true);el('orderImportWizard').setAttribute('aria-busy','true');
    try{await callback();}catch(e){el('orderImportMessage').textContent=e.message;el('orderImportMessage').focus();}
    finally{busy=false;buttons.filter(b=>b.isConnected).forEach(b=>b.disabled=false);el('orderImportWizard').setAttribute('aria-busy','false');}
  }
  function steps(n){return `<ol class="gf-steps">${['Carica file','Controlla dati','Fatto'].map((x,i)=>`<li class="gf-step${i+1<n?' is-done':''}" ${n===i+1?'aria-current="step"':''}><strong>${x}</strong></li>`).join('')}</ol>`;}
  // Pop-up: ogni passo riscrive il contenuto, il piè di pagina e la riga «Passo N di 3».
  const STEPS=['Carica il file','Scegli cosa importare','Importazione completata'];
  function render(html,footer='',step=1){
    el('orderImportWizard').innerHTML=html;el('orderImportFooter').innerHTML=footer;
    el('orderImportStep').textContent=`Passo ${step} di 3 · ${STEPS[step-1]}`;
    el('orderImportWizard').closest('.gf-modal__body').scrollTop=0;
  }
  function open(){const dialog=el('orderImportDialog');if(dialog&&!dialog.open)dialog.showModal();}
  function close(){
    const dialog=el('orderImportDialog');if(dialog?.open)dialog.close();
    // Gli ordini appena importati compaiono subito nell'elenco.
    if(report?.status==='completed'&&!el('tab-ordini')?.classList.contains('hidden'))window.GFOrders?.load?.();
  }
  function start(id){if(busy)return;el('orderImportMessage').textContent='';open();return work(async()=>{
    const data=await api('');sources=data.items;fields=data.fields;
    for(let offset=50;offset<data.total;offset+=50)sources.push(...(await api('?offset='+offset)).items);
    sources=sources.filter(s=>s.kind==='file'&&['draft','active'].includes(s.status));
    // L'elenco non si sceglie più: quello indicato, altrimenti il primo attivo; la prima volta se ne crea uno.
    source=sources.find(s=>s.id===id)||sources.find(s=>s.status==='active')||sources[0]||null;stage=report=null;form();
  });}
  function form(){
    const cancel='<button type="button" class="gf-button" data-variant="secondary" onclick="GFOrderImport.close()">Annulla</button>';
    if(!can('orders.import')&&!can('orders.integrations')){render('<div class="gf-empty"><p><strong>Importazione non abilitata</strong></p><p>Chiedi al responsabile di abilitare il tuo account.</p></div>',cancel);return;}
    render(`<div class="gf-empty"><span class="gf-empty__icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M12 16V4 M7 9l5-5 5 5 M4 20h16"/></svg></span>
      <p><strong>Scegli il file con gli ordini</strong></p><p>Excel (.xlsx) o CSV esportato dal tuo negozio o gestionale.</p>
      <label class="gf-button" data-variant="primary">Scegli file<input id="orderImportFile" type="file" accept=".xlsx,.csv" hidden onchange="GFOrderImport.upload()"></label>
      <p class="gf-field__hint">Servono almeno destinatario e indirizzo · fino a 1000 ordini e 2 MB · un solo foglio, senza formule.</p></div>`,cancel,1);
  }
  function choose(){source=sources.find(s=>s.id===Number(el('orderImportSource').value))||null;el('orderImportNameLabel').hidden=!!source;}
  function upload(event){event?.preventDefault?.();return work(async()=>{
    const file=el('orderImportFile')?.files?.[0];if(!file)throw new Error('Scegli il file da importare.');
    if(file.size>2097152)throw new Error('Il file supera 2 MB. Dividilo in file più piccoli.');
    if(!/\.(csv|xlsx)$/i.test(file.name))throw new Error('Scegli un file Excel (.xlsx) o CSV.');
    if(!source){if(!can('orders.integrations'))throw new Error('Chiedi al responsabile di fare la prima importazione da file.');source=await api('',post({name:'Importazione da file',kind:'file',software:''}));}
    const body=new FormData();body.append('file',file);stage=await api('/'+source.id+'/upload',{method:'POST',body});filename=file.name;
    // Colonne ricordate dall'ultimo file, se ci sono tutte; altrimenti quelle riconosciute in questo file.
    const saved=source.mapping||{},fits=Object.keys(saved).length&&Object.values(saved).every(v=>stage.headers.includes(v));
    mapping=fits?{...saved}:{...stage.suggested_mapping};excluded=[...(source.excluded_fields||[])];report=null;review();
    if(mapping.number&&mapping.external_id&&Object.entries(mapping).every(([k,v])=>excluded.includes(k)||stage.headers.includes(v)))await validate();
  });}
  // Passo 2: una sola tabella «Dato · Colonna del tuo file · Importa», poi l'anteprima e l'esito del controllo.
  const ALWAYS=['recipient_name','delivery_address','street','street_number','postal_code','city','province','number'];
  const ROW_ORDER=['recipient_name','delivery_address','street','street_number','postal_code','city','province','number','requested_date','packages','weight_kg','phone','time_from','time_to','notes'];
  const ROW_LABELS={...labels,street:'Via',street_number:'Civico',postal_code:'CAP',city:'Comune',province:'Provincia',time_from:'Fascia oraria dalle',time_to:'Fascia oraria alle'};
  function review(){
    const editable=can('orders.integrations');
    const keys=[...ROW_ORDER,...fields.filter(k=>!ROW_ORDER.includes(k)&&k!=='external_id')].filter(k=>fields.includes(k)||ALWAYS.includes(k));
    const select=k=>`<select class="gf-select" data-import-field="${esc(k)}" aria-label="Colonna per ${esc(ROW_LABELS[k]||k)}" onchange="GFOrderImport.changed()" ${editable?'':'disabled'}><option value="">Non presente</option>${stage.headers.map(h=>`<option value="${esc(h)}" ${mapping[k]===h?'selected':''}>${esc(h)}</option>`).join('')}</select>`;
    const toggle=k=>ALWAYS.includes(k)?'<span class="gf-muted">Sempre</span>':k==='time_to'?'<span class="gf-muted">Con «dalle»</span>'
      :`<label class="gf-switch"><input type="checkbox" role="switch" data-choice="import" value="${esc(k)}" aria-label="Importa ${esc(ROW_LABELS[k]||k)}" ${excluded.includes(k)?'':'checked'} ${editable?'':'disabled'} onchange="GFOrderImport.changed()"></label>`;
    const row=k=>`<tr><td data-label="Dato"><strong>${esc(ROW_LABELS[k]||k)}</strong></td><td data-label="Colonna del tuo file">${select(k)}</td><td data-label="Importa">${toggle(k)}</td></tr>`;
    const table=list=>`<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards"><thead><tr><th scope="col">Dato</th><th scope="col">Colonna del tuo file</th><th scope="col">Importa</th></tr></thead><tbody>${list.map(row).join('')}</tbody></table></div>`;
    // Indirizzo intero oppure a campi separati: si mostra solo la forma presente nel file.
    const split=['street','postal_code','city'].some(k=>mapping[k]);
    const shown=keys.filter(k=>split?k!=='delivery_address':!['street','street_number','postal_code','city','province'].includes(k));
    const found=shown.filter(k=>mapping[k]||ALWAYS.slice(0,2).includes(k)),missing=shown.filter(k=>!found.includes(k));
    render(`<p><strong>${esc(filename)}</strong> <span class="gf-muted">· ${esc(gfCount(stage.total,'riga','righe'))}</span> <button type="button" class="gf-button" data-variant="link" onclick="GFOrderImport.form()">Cambia file</button></p>
      <section class="gf-stack" data-gap="sm"><h3 class="gf-subtitle">Colonne riconosciute</h3><p class="gf-muted">Le abbiamo trovate da sole: correggi quelle sbagliate e spegni i dati che non vuoi importare.${editable?'':' Chiedi al responsabile per cambiarle.'}</p>${table(found)}
      ${missing.length?`<details class="gf-panel"><summary class="gf-panel__header">Altri dati non trovati nel file (${missing.length})</summary><div class="gf-panel__body">${table(missing)}</div></details>`:''}</section>
      <section class="gf-stack" data-gap="sm"><h3 class="gf-subtitle">Anteprima</h3><div id="orderImportPreview"></div></section><div id="orderImportReport"></div>`,
      '<button type="button" class="gf-button" data-variant="secondary" onclick="GFOrderImport.form()">Indietro</button><div id="orderImportConfirm" class="gf-cluster"></div>',2);
    previewRows();confirmation();
  }
  // Indirizzo a campi separati: in anteprima si mostra composto come verrà importato.
  function previewValue(row,key){
    const value=row[mapping[key]];
    if(key!=='delivery_address'||(value!==undefined&&value!==null&&String(value).trim()))return value;
    const part=k=>String(row[mapping[k]]??'').trim();
    const street=[part('street'),part('street_number')].filter(Boolean).join(' '),place=[part('postal_code'),part('city'),part('province')].filter(Boolean).join(' ');
    return [street,place].filter(Boolean).join(', ')||null;
  }
  function previewRows(){
    const keys=['number','recipient_name','delivery_address','requested_date','packages'].filter(k=>!excluded.includes(k));
    el('orderImportPreview').innerHTML='<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards"><thead><tr>'+keys.map(k=>`<th scope="col">${labels[k]}</th>`).join('')+'</tr></thead><tbody>'+stage.sample.map(row=>'<tr>'+keys.map(k=>`<td data-label="${labels[k]}">${esc(String(previewValue(row,k)??'—'))}</td>`).join('')+'</tr>').join('')+'</tbody></table></div><p class="gf-field__hint">Prime '+stage.sample.length+' righe. Potrai completare i dati mancanti negli ordini.</p>';
  }
  let changeTimer=null;
  function changed(){
    report=null;excluded=readChoices('import');mapping={};
    document.querySelectorAll('[data-import-field]').forEach(n=>{if(n.value)mapping[n.dataset.importField]=n.value;});
    // Il codice univoco segue il numero ordine (stessa regola dei suggerimenti del server).
    if(mapping.number)mapping.external_id=mapping.number;
    previewRows();el('orderImportReport').replaceChildren();confirmation();
    clearTimeout(changeTimer);changeTimer=setTimeout(()=>{if(mapping.number&&mapping.recipient_name)work(validate);},400);
  }
  async function validate(){
    const selection=JSON.stringify({mapping,excluded});
    if(JSON.stringify(Object.entries(mapping).sort())!==JSON.stringify(Object.entries(source.mapping).sort())){
      if(!can('orders.integrations'))throw new Error('Le colonne sono cambiate. Chiedi al responsabile di aggiornare le associazioni.');
      source=await api('/'+source.id,{method:'PUT',body:JSON.stringify({version:source.version,mapping})});
    }
    if(can('orders.integrations')&&(!source.fields_configured||JSON.stringify([...excluded].sort())!==JSON.stringify([...(source.excluded_fields||[])].sort())))source=await api('/'+source.id+'/fields',{method:'PUT',body:JSON.stringify({version:source.version,excluded_fields:excluded})});
    report=await api(`/${source.id}/runs/${stage.run_id}/preview`,post({}));if(selection!==JSON.stringify({mapping,excluded})){report=null;el('orderImportReport').replaceChildren();confirmation();return;}renderReport();confirmation();
  }
  function renderReport(){
    const r=report.report,invalid=r.invalid||report.status==='failed';
    const page=(delta,label)=>`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFOrderImport.reportPage(${delta})">${label}</button>`;
    el('orderImportReport').innerHTML=`<section class="gf-stack"><h3 class="gf-subtitle">${report.status==='completed'?'Importazione completata':invalid?'Ci sono dati da correggere':'Pronto per importare'}</h3><div class="gf-cluster"><span class="gf-badge" data-status="success">${r.new||0} nuovi</span><span class="gf-badge" data-status="info">${r.updated||0} aggiornamenti</span><span class="gf-badge" data-status="neutral">${r.unchanged||0} già presenti</span>${r.invalid?`<span class="gf-badge" data-status="danger">${r.invalid} errori</span>`:''}</div>${r.error?`<p class="gf-alert" data-status="danger">${esc(r.error)}</p>`:''}${invalid?'<p class="gf-alert" data-status="warning">Nessun ordine è stato importato. Correggi il file o le associazioni e riprova.</p>':''}${r.unmatched?'<p class="gf-muted">I nuovi destinatari resteranno negli ordini: non devi creare prima l’anagrafica cliente.</p>':''}<details class="gf-panel" ${invalid?'open':''}><summary class="gf-panel__header">Dettaglio righe e avvisi</summary><div class="gf-panel__body gf-stack"><ul>${report.rows.map(row=>`<li>${esc(row.external_id||'Riga '+row.row)}: ${esc(row.error||({new:'Nuovo',updated:'Aggiornamento',unchanged:'Già presente'}[row.action]||''))}${row.warnings?.length?' · '+esc(row.warnings.join('; ')):''}</li>`).join('')}</ul><div class="gf-cluster">${report.offset?page(-100,'Precedenti'):''}${report.has_more?page(100,'Altre righe'):''}</div></div></details></section>`;
  }
  function confirmation(){
    const box=el('orderImportConfirm');if(!box)return;
    const ready=report?.status==='preview_ready',allowed=can('orders.import')&&(source.status==='active'||can('orders.integrations'));
    // Righe sbagliate: si possono importare intanto quelle valide.
    const wrong=Number(report?.report?.invalid||0),valid=Math.max(0,Number(report?.report?.total||0)-wrong);
    if(report?.status==='preview_invalid'&&valid&&wrong&&allowed){
      box.innerHTML=`<button type="button" id="orderImportCommitValid" class="gf-button" data-variant="primary" onclick="GFOrderImport.commit(true)">Importa ${esc(gfCount(valid,'ordine valido','ordini validi'))}</button>`;
      return;
    }
    box.innerHTML=ready?(allowed?`<button type="button" id="orderImportCommit" class="gf-button" data-variant="primary" onclick="GFOrderImport.commit()">Importa ${esc(gfCount(report.report.total,'ordine','ordini'))}</button>`:'<span class="gf-muted">Chiedi al responsabile il permesso di importare.</span>')
      :`<span class="gf-muted">${mapping.number&&mapping.recipient_name?'Controllo dei dati in corso…':'Indica almeno destinatario e numero ordine.'}</span>`;
  }
  function commit(onlyValid=false){return work(async()=>{
    if(report?.status!=='preview_ready'&&!(onlyValid&&report?.status==='preview_invalid'))throw new Error('Attendi il controllo dei dati prima di importare.');
    if(source.status!=='active')source=await api('/'+source.id+'/action',post({version:source.version,action:'activate',run_id:stage.run_id}));
    report=await api(`/${source.id}/runs/${stage.run_id}/commit`,post({confirm:true,...(onlyValid?{skip_invalid:true}:{})}));
    if(report.status==='completed'){
      const r=report.report,imported=Number(r.new||0)+Number(r.updated||0);
      const line=(label,value)=>value?`<div class="gf-details__item"><dt>${label}</dt><dd>${value}</dd></div>`:'';
      render(`<div class="gf-empty"><span class="gf-empty__icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12l4 4 10-10"/></svg></span>
        <p><strong>${esc(gfCount(imported,'ordine importato','ordini importati'))}</strong></p><p>Li trovi nell’elenco degli ordini, pronti da controllare e pianificare.</p></div>
        <dl class="gf-details" data-layout="rows">${line('Nuovi',r.new)}${line('Aggiornati',r.updated)}${line('Già presenti, invariati',r.unchanged)}${line('Saltati per errori',r.invalid)}</dl>`,
        '<button type="button" class="gf-button" data-variant="secondary" onclick="GFOrderImport.close()">Chiudi</button><button type="button" class="gf-button" data-variant="primary" onclick="GFOrderImport.viewOrders()">Vai agli ordini</button>',3);
      return;
    }
    renderReport();confirmation();
  });}
  function viewOrders(){if(busy)return;close();for(const id of ['ordersSearch','ordersStatus','ordersFrom','ordersTo'])el(id).value='';const filter=el('ordersSource');if(![...filter.options].some(o=>o.value===String(source.id)))filter.add(new Option(source.name,source.id));filter.value=source.id;showTab('ordini');}
  function fieldChoices(ignored,prefix,disabled){
    const essential=['recipient_name','delivery_address'];
    const optional=Object.keys(labels).filter(k=>!['external_id','number',...essential,'time_to'].includes(k));
    const choice=(k,required=false)=>`<label class="gf-check"><input type="checkbox" data-choice="${prefix}" value="${k}" ${required||!ignored.includes(k)?'checked':''} ${required||disabled?'disabled':''} ${prefix==='import'?'onchange="GFOrderImport.changed()"':''}> <span>${k==='time_from'?'Fascia oraria':labels[k]}${required?' (obbligatorio)':''}</span></label>`;
    return `<section class="gf-stack"><h3 class="gf-subtitle">Quali dati vuoi importare?</h3><p class="gf-muted">Nome destinatario e indirizzo sono sempre richiesti. Il numero ordine serve a evitare duplicati.</p><div class="gf-form-grid">${essential.map(k=>choice(k,true)).join('')}${choice('requested_date')}</div><p class="gf-muted">Disattiva la data consegna per scegliere liberamente il giorno del giro.</p><details class="gf-panel"><summary class="gf-panel__header">Altri dati facoltativi</summary><div class="gf-panel__body gf-form-grid">${optional.filter(k=>k!=='requested_date').map(k=>choice(k)).join('')}</div></details><p class="gf-field__hint">Le scelte valgono per i prossimi invii di questa fonte. Gli ordini già presenti restano invariati finché non vengono reimportati.${disabled?' Chiedi al responsabile di modificare queste impostazioni.':''}</p></section>`;
  }
  // Dati facoltativi di una fonte, con l'etichetta mostrata (la fascia oraria vale per «Dalle» e «Alle»).
  function fieldOptions(){
    return Object.keys(labels).filter(k=>!['external_id','number','recipient_name','delivery_address','time_to'].includes(k))
      .map(k=>({key:k,label:k==='time_from'?'Fascia oraria':labels[k]}));
  }
  function readChoices(prefix){const ignored=[...document.querySelectorAll(`[data-choice="${prefix}"]:not(:checked)`)].map(n=>n.value);if(ignored.includes('time_from'))ignored.push('time_to');return ignored;}
  window.GFOrderImport={fieldChoices,fieldOptions,readChoices,start,form,close,choose,upload,changed,commit,viewOrders,validate:()=>work(validate),reportPage(delta){return work(async()=>{report=await api(`/${source.id}/runs/${report.id}?offset=${report.offset+delta}`);renderReport();});}};
})();
