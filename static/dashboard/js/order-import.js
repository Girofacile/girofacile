/* File import is independent of the technical API connection settings. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id),can=k=>!window.GFCompanyAccess||GFCompanyAccess.can(k);
  const labels={number:'Numero ordine',recipient_name:'Destinatario',delivery_address:'Indirizzo',requested_date:'Data consegna',packages:'Colli',weight_kg:'Peso',external_id:'Codice univoco',external_customer_id:'Codice cliente',time_from:'Dalle',time_to:'Alle',pallets:'Pallet',volume_m3:'Volume',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti',notes:'Note',items:'Articoli'};
  let sources=[],fields=[],source=null,stage=null,report=null,mapping={},excluded=[],busy=false,filename='';
  const post=value=>({method:'POST',body:JSON.stringify(value)});
  async function api(path,options={}){
    const res=await fetch('/api/order-sources'+path,{...options,headers:options.body instanceof FormData?{}:{'Content-Type':'application/json'}}),data=await res.json();
    if(!res.ok&&!data.report)throw new Error(typeof data.detail==='string'?data.detail:'Controlla i dati e riprova.');return data;
  }
  async function work(callback){
    if(busy)return;busy=true;el('orderImportMessage').textContent='';
    const buttons=[...el('orderImportWizard').querySelectorAll('button')].filter(b=>!b.disabled);buttons.forEach(b=>b.disabled=true);el('orderImportWizard').setAttribute('aria-busy','true');
    try{await callback();}catch(e){el('orderImportMessage').textContent=e.message;el('orderImportMessage').focus();}
    finally{busy=false;buttons.filter(b=>b.isConnected).forEach(b=>b.disabled=false);el('orderImportWizard').setAttribute('aria-busy','false');}
  }
  function steps(n){return `<ol class="order-import-steps">${['Carica file','Controlla dati','Fatto'].map((x,i)=>`<li ${n===i+1?'aria-current="step"':''}><span>${i+1}</span>${x}</li>`).join('')}</ol>`;}
  function render(html){el('orderImportWizard').innerHTML=html;el('orderImportWizard').scrollIntoView({block:'start'});}
  function start(id){if(busy)return;showTab('ordini-importa');return work(async()=>{
    const data=await api('');sources=data.items;fields=data.fields;
    // Load the remaining pages so existing sources never disappear from the reuse selector.
    for(let offset=50;offset<data.total;offset+=50)sources.push(...(await api('?offset='+offset)).items);
    sources=sources.filter(s=>s.kind==='file'&&['draft','active'].includes(s.status));
    source=sources.find(s=>s.id===id)||sources[0]||null;stage=report=null;form();
  });}
  function form(){
    if(!can('orders.import')&&!can('orders.integrations')){render('<h2>Importazione non abilitata</h2><p>Chiedi al responsabile di abilitare il tuo account.</p>');return;}
    render(`${steps(1)}<h2>Quale file vuoi importare?</h2><p>Carica il file Excel o CSV esportato dal tuo negozio o gestionale.</p><form onsubmit="GFOrderImport.upload(event)"><label class="order-import-file">Scegli il file<input id="orderImportFile" type="file" accept=".xlsx,.csv" required></label><p class="order-import-caption">Fino a 1000 ordini e 2 MB. Excel: un solo foglio, senza formule.</p><details ${!source?'open':''}><summary>${source?'Elenco: '+esc(source.name):'Nome dell’elenco (facoltativo)'}</summary>${sources.length?`<label>Riutilizza un elenco<select id="orderImportSource" onchange="GFOrderImport.choose()">${sources.map(s=>`<option value="${s.id}" ${source?.id===s.id?'selected':''}>${esc(s.name)}</option>`).join('')}${can('orders.integrations')?'<option value="">Nuovo elenco</option>':''}</select></label><p>Usa lo stesso elenco per aggiornare gli ordini senza duplicarli.</p>`:''}<label id="orderImportNameLabel" ${source?'hidden':''}>Nome elenco<input id="orderImportName" maxlength="160" placeholder="Es. Ordini del negozio"></label></details><button class="btn-primary" type="submit">Continua</button></form>`);
  }
  function choose(){source=sources.find(s=>s.id===Number(el('orderImportSource').value))||null;el('orderImportNameLabel').hidden=!!source;}
  function upload(event){event.preventDefault();return work(async()=>{
    const file=el('orderImportFile').files[0];if(!file)throw new Error('Scegli il file da importare.');
    if(file.size>2097152)throw new Error('Il file supera 2 MB. Dividilo in file più piccoli.');
    if(!/\.(csv|xlsx)$/i.test(file.name))throw new Error('Scegli un file Excel (.xlsx) o CSV.');
    if(!source){if(!can('orders.integrations'))throw new Error('Chiedi al responsabile di configurare un elenco.');source=await api('',post({name:(el('orderImportName').value.trim()||file.name.replace(/\.[^.]+$/,'')).slice(0,160),kind:'file',software:''}));}
    const body=new FormData();body.append('file',file);stage=await api('/'+source.id+'/upload',{method:'POST',body});filename=file.name;
    mapping=Object.keys(source.mapping).length?{...source.mapping}:{...stage.suggested_mapping};excluded=[...(source.excluded_fields||[])];report=null;review();
    if(mapping.number&&mapping.external_id&&Object.entries(mapping).every(([k,v])=>excluded.includes(k)||stage.headers.includes(v)))await validate();
  });}
  function review(){
    const basic=['number','recipient_name','delivery_address','requested_date','packages','weight_kg'];
    const select=k=>`<label>${labels[k]||esc(k)}<select data-import-field="${esc(k)}" onchange="GFOrderImport.changed()" ${can('orders.integrations')?'':'disabled'}><option value="">Non presente</option>${stage.headers.map(h=>`<option value="${esc(h)}" ${mapping[k]===h?'selected':''}>${esc(h)}</option>`).join('')}</select></label>`;
    render(`${steps(2)}<h2>Controlla l’anteprima</h2><p>${esc(filename)} · ${stage.total} ${stage.total===1?'ordine':'ordini'} · ${esc(source.name)}</p>${fieldChoices(excluded,'import',!can('orders.integrations'))}<button class="btn-secondary" onclick="GFOrderImport.validate()">Aggiorna anteprima</button><div id="orderImportPreview"></div><details id="orderImportMapping" ${!mapping.number||!mapping.external_id?'open':''}><summary>Le colonne non corrispondono? Modifica le associazioni</summary><div class="orders-form-grid">${basic.map(select).join('')}</div><details><summary>Altri dati e codice univoco</summary><p>Il codice univoco riconosce lo stesso ordine nei successivi import. Di solito coincide con il numero ordine.</p><div class="orders-form-grid">${fields.filter(k=>!basic.includes(k)).map(select).join('')}</div></details><button class="btn-secondary" onclick="GFOrderImport.validate()">Aggiorna anteprima</button></details><div id="orderImportReport"></div><div id="orderImportConfirm"></div><button class="btn-secondary" onclick="GFOrderImport.start()">← Cambia file</button>`);previewRows();confirmation();
  }
  function previewRows(){
    const keys=['number','recipient_name','delivery_address','requested_date','packages'].filter(k=>!excluded.includes(k));
    el('orderImportPreview').innerHTML='<div class="tableWrap"><table><thead><tr>'+keys.map(k=>`<th>${labels[k]}</th>`).join('')+'</tr></thead><tbody>'+stage.sample.map(row=>'<tr>'+keys.map(k=>`<td>${esc(String(row[mapping[k]]??'—'))}</td>`).join('')+'</tr>').join('')+'</tbody></table></div><p class="order-import-caption">Prime '+stage.sample.length+' righe. Potrai completare i dati mancanti negli ordini.</p>';
  }
  function changed(){report=null;excluded=readChoices('import');mapping={};document.querySelectorAll('[data-import-field]').forEach(n=>{if(n.value)mapping[n.dataset.importField]=n.value;});previewRows();el('orderImportReport').replaceChildren();confirmation();}
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
    el('orderImportReport').innerHTML=`<h3>${report.status==='completed'?'Importazione completata':invalid?'Ci sono dati da correggere':'Pronto per importare'}</h3><div class="order-import-counts"><span><strong>${r.new||0}</strong> nuovi</span><span><strong>${r.updated||0}</strong> aggiornamenti</span><span><strong>${r.unchanged||0}</strong> già presenti</span>${r.invalid?`<span>${r.invalid} errori</span>`:''}</div>${r.error?`<p class="orders-error">${esc(r.error)}</p>`:''}${invalid?'<p>Nessun ordine è stato importato. Correggi il file o le associazioni e riprova.</p>':''}${r.unmatched?'<p>I nuovi destinatari resteranno negli ordini: non devi creare prima l’anagrafica cliente.</p>':''}<details ${invalid?'open':''}><summary>Dettaglio righe e avvisi</summary><ul>${report.rows.map(row=>`<li>${esc(row.external_id||'Riga '+row.row)}: ${esc(row.error||({new:'Nuovo',updated:'Aggiornamento',unchanged:'Già presente'}[row.action]||''))}${row.warnings?.length?' · '+esc(row.warnings.join('; ')):''}</li>`).join('')}</ul>${report.offset?'<button class="btn-secondary" onclick="GFOrderImport.reportPage(-100)">Precedenti</button>':''}${report.has_more?'<button class="btn-secondary" onclick="GFOrderImport.reportPage(100)">Altre righe</button>':''}</details>`;
  }
  function confirmation(){
    const ready=report?.status==='preview_ready',allowed=can('orders.import')&&(source.status==='active'||can('orders.integrations'));
    el('orderImportConfirm').innerHTML=ready?(allowed?`<p>Confermi l’importazione in “${esc(source.name)}”. Le impostazioni saranno ricordate.</p><button id="orderImportCommit" class="btn-primary" onclick="GFOrderImport.commit()">Importa ${report.report.total} ${report.report.total===1?'ordine':'ordini'}</button>`:'<p>Chiedi al responsabile di attivare l’elenco o il permesso di importazione.</p>'):'<p>Controlla le associazioni e aggiorna l’anteprima per continuare.</p>';
  }
  function commit(){return work(async()=>{
    if(report?.status!=='preview_ready')throw new Error('Aggiorna l’anteprima prima di importare.');
    if(source.status!=='active')source=await api('/'+source.id+'/action',post({version:source.version,action:'activate',run_id:stage.run_id}));
    report=await api(`/${source.id}/runs/${stage.run_id}/commit`,post({confirm:true}));
    if(report.status==='completed')render(`${steps(3)}<h2>I tuoi ordini sono stati importati</h2><p>Controlla gli indirizzi e i dati mancanti. Quando sono pronti, selezionali per creare il giro.</p><div id="orderImportReport"></div><div class="page-actions"><button class="btn-primary" onclick="GFOrderImport.viewOrders()">Vai agli ordini importati</button><button class="btn-secondary" onclick="GFOrderImport.start()">Importa un altro file</button></div>`);
    renderReport();if(report.status!=='completed')confirmation();
  });}
  function viewOrders(){if(busy)return;for(const id of ['ordersSearch','ordersStatus','ordersFrom','ordersTo'])el(id).value='';const filter=el('ordersSource');if(![...filter.options].some(o=>o.value===String(source.id)))filter.add(new Option(source.name,source.id));filter.value=source.id;showTab('ordini');}
  function fieldChoices(ignored,prefix,disabled){
    const essential=['recipient_name','delivery_address'];
    const optional=Object.keys(labels).filter(k=>!['external_id','number',...essential,'time_to'].includes(k));
    const choice=(k,required=false)=>`<label class="order-field-choice"><input type="checkbox" data-choice="${prefix}" value="${k}" ${required||!ignored.includes(k)?'checked':''} ${required||disabled?'disabled':''} ${prefix==='import'?'onchange="GFOrderImport.changed()"':''}> ${k==='time_from'?'Fascia oraria':labels[k]}${required?' (obbligatorio)':''}</label>`;
    return `<section class="order-field-options"><h3>Quali dati vuoi importare?</h3><p>Nome destinatario e indirizzo sono sempre richiesti. Il numero ordine serve a evitare duplicati.</p><div class="orders-form-grid">${essential.map(k=>choice(k,true)).join('')}${choice('requested_date')}</div><p>Disattiva la data consegna per scegliere liberamente il giorno del giro.</p><details><summary>Altri dati facoltativi</summary><div class="orders-form-grid">${optional.filter(k=>k!=='requested_date').map(k=>choice(k)).join('')}</div></details><p class="order-import-caption">Le scelte valgono per i prossimi invii di questa fonte. Gli ordini già presenti restano invariati finché non vengono reimportati.${disabled?' Chiedi al responsabile di modificare queste impostazioni.':''}</p></section>`;
  }
  function readChoices(prefix){const ignored=[...document.querySelectorAll(`[data-choice="${prefix}"]:not(:checked)`)].map(n=>n.value);if(ignored.includes('time_from'))ignored.push('time_to');return ignored;}
  window.GFOrderImport={fieldChoices,readChoices,start,choose,upload,changed,commit,viewOrders,validate:()=>work(validate),reportPage(delta){return work(async()=>{report=await api(`/${source.id}/runs/${report.id}?offset=${report.offset+delta}`);renderReport();});}};
})();
