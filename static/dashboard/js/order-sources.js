/* Guided source configuration. Secrets live only in the visible credential control. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id), can=k=>!window.GFCompanyAccess||GFCompanyAccess.can(k);
  const manage=()=>can('orders.integrations'), owner=()=>!window.GFCompanyAccess?.isCollaborator();
  const names={external_id:'Identificativo esterno *',number:'Numero ordine *',external_customer_id:'Codice cliente',recipient_name:'Destinatario',delivery_address:'Indirizzo consegna',requested_date:'Data richiesta',time_from:'Dalle',time_to:'Alle',weight_kg:'Peso (kg)',packages:'Colli',pallets:'Pallet',volume_m3:'Volume (m³)',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti',notes:'Note',items:'Articoli (JSON)'};
  const statuses={draft:'Da configurare',active:'Attiva',paused:'In pausa',removed:'Rimossa',uploaded:'Campione caricato',preview_ready:'Anteprima valida',preview_invalid:'Anteprima con errori',completed:'Acquisizione completata',failed:'Acquisizione fallita',source_activate:'Fonte attivata',source_pause:'Fonte sospesa',source_resume:'Fonte riattivata',source_remove:'Fonte rimossa',source_rotate:'Credenziale generata',source_revoke:'Credenziale revocata'};
  const actions={new:'Nuovo',updated:'Da aggiornare',unchanged:'Invariato'};
  const sourceStatusClass=status=>status==='active'?'is-active':status==='paused'?'is-paused':status==='removed'?'is-removed':'';
  const sourceStatusBadge=status=>`<span class="orders-source-status ${sourceStatusClass(status)}">${esc(statuses[status]||status)}</span>`;
  let sources=[],fields=[],offset=0,current=null,staged=null,verified=null,busy=false;
  const example={orders:[{external_id:'ORD-001',number:'ORD-001',external_customer_id:'CLI-001',recipient_name:'Esempio cliente',delivery_address:'Via Roma 1, Milano',packages:3,weight_kg:12.5,tail_lift:false}]};
  const button=(label,call)=>`<button class="btn-secondary" onclick="GFOrderSources.${call}">${label}</button>`;
  const post=body=>({method:'POST',body:JSON.stringify(body)});
  async function request(path,options={}){
    const response=await fetch('/api/order-sources'+path,{...options,headers:options.body instanceof FormData?{}:{'Content-Type':'application/json'}});
    const data=await response.json();
    if(!response.ok && !data.report)throw new Error(typeof data.detail==='string'?data.detail:'Controlla i campi e riprova.');
    return data;
  }
  async function task(work){
    if(busy)return;busy=true;el('sourceMessage').textContent='Operazione in corso…';
    try{await work();el('sourceMessage').textContent='';}catch(err){el('sourceMessage').textContent=err.message;}
    finally{busy=false;}
  }
  function hideSecret(){const box=el('sourceCredential');if(box)box.replaceChildren();}
  async function refresh(){
    const data=await request('?offset='+offset);sources=data.items;fields=['external_id','number',...data.fields.filter(k=>!['external_id','number'].includes(k))];
    el('sourceCategories').hidden=!manage();
    el('sourceList').innerHTML=sources.length?'<div class="orders-source-list-grid">'+sources.map(s=>`<article class="orders-source-card"><h3>${esc(s.name)}</h3><div class="orders-source-meta"><span>${s.kind==='api'?'API standard':'File CSV / XLSX'}</span>${sourceStatusBadge(s.status)}</div><p><strong>${s.order_count} ordini</strong> · Ultima acquisizione: ${s.last_success?esc(new Date(s.last_success+'Z').toLocaleString('it-IT')):'nessuna'}</p>${s.kind==='api'&&s.status==='active'?`<p>${s.has_credential?'Pronta a ricevere richieste autenticate. Il gestionale deve essere configurato per inviarle.':'Credenziale da generare: nessun invio autorizzato.'}</p>`:''}${s.last_run?.status==='failed'||s.last_run?.status==='preview_invalid'?'<p class="orders-error">Ultima verifica o acquisizione con errori. Consulta lo storico.</p>':''}<div class="page-actions">${s.status!=='removed'?button('Apri',`open(${s.id})`):''}${button('Storico',`history(${s.id},0)`)}</div></article>`).join('')+'</div>':'<div class="orders-sources-empty">Nessuna fonte configurata.</div>';
    const pagination=el('sourcePagination');
    if(pagination)pagination.hidden=data.total<=50;
    el('sourcePage').textContent=`${data.total} fonti`;el('sourcePrevious').disabled=offset===0;el('sourceNext').disabled=offset+50>=data.total;
  }
  function load(){hideSecret();return task(refresh);}
  function unavailable(kind){
    if(busy)return;hideSecret();current=staged=verified=null;el('sourceWizard').hidden=false;
    el('sourceWizard').innerHTML=`<h2>${kind==='email'?'Ordini via email':'Ordini e-commerce'}</h2><p>Il connettore dedicato richiede una configurazione aggiuntiva e non è disponibile in questa versione. ${kind==='email'?'La futura integrazione userà un inoltro dedicato; non accediamo alla casella di posta.':'Puoi esportare gli ordini del negozio oppure chiedere al fornitore di inviarli tramite API standard.'}</p><div class="page-actions">${button('Configura una fonte file',"createForm('file')")}${button('Configura API standard',"createForm('api')")}</div>`;
    el('sourceWizard').scrollIntoView({block:'start'});
  }
  function invalidate(){verified=null;el('sourceConfirm')?.replaceChildren();}
  function createForm(kind){
    if(!manage()||busy)return;current=staged=verified=null;hideSecret();
    el('sourceWizard').hidden=false;
    el('sourceWizard').innerHTML=`<h2>1. Scegli la fonte</h2><form onsubmit="GFOrderSources.create(event)"><div class="orders-form-grid"><label>Nome della fonte<input id="sourceName" required maxlength="160" placeholder="Es. Gestionale magazzino"></label><label>Software utilizzato (facoltativo)<input id="sourceSoftware" maxlength="160" placeholder="Nome del gestionale"></label><label>Modalità disponibile<select id="sourceKind"><option value="file" ${kind==='file'?'selected':''}>File Excel o CSV</option><option value="api" ${kind==='api'?'selected':''}>API standard</option><option value="custom">Collegamento personalizzato: informazioni</option></select></label></div><p>Le API richiedono la configurazione dell'invio da parte di chi gestisce il tuo software. Nessun connettore proprietario viene attivato automaticamente.</p><button class="btn-primary" type="submit">Crea fonte e prosegui</button></form>`;
    el('sourceWizard').scrollIntoView({block:'start'});
  }
  function create(event){event.preventDefault();if(el('sourceKind').value==='custom'){el('sourceMessage').textContent='Collegamento personalizzato da predisporre con il fornitore: comunica nome e versione del software, esempio anonimo del tracciato, identificativi stabili e frequenza degli invii. Le modalità operative disponibili sono file o API standard: selezionane una per proseguire.';return;}return task(async()=>{current=await request('',post({name:el('sourceName').value,kind:el('sourceKind').value,software:el('sourceSoftware').value}));staged=verified=null;if(current.kind==='api'){await refresh();current=sources.find(s=>s.id===current.id)||current;showTab('ordine-fonte');detailPage();window.scrollTo({top:0,behavior:'auto'});}else{editor();await refresh();}});}
  function sourceSubtitle(s){return s.kind==='api'?'Gestione fonte API e validazione campioni JSON.':'Gestione fonte file e validazione degli ordini importati.';}
  function sourceTopActions(s,mobile=false){
    if(!manage())return '';
    const toggle=s.status==='active'
      ?'<button class="order-source-pause-btn" onclick="GFOrderSources.action(\'pause\')">Ⅱ&nbsp; Metti in pausa</button>'
      :s.status==='paused'
        ?'<button class="order-source-resume-btn" onclick="GFOrderSources.action(\'resume\')">Riattiva fonte</button>'
        :'';
    const remove='<button class="order-source-delete-btn" onclick="GFOrderSources.deleteSource()">⌫&nbsp; Elimina fonte</button>';
    return `<div class="${mobile?'order-source-mobile-actions':'order-source-topbar-actions'}">${toggle}${remove}</div>`;
  }
  function syncSourceTopbar(){
    if(!current)return;
    const title=el('workspacePageTitle'),subtitle=el('workspacePageSubtitle'),badge=el('workspacePageBadge'),actions=el('orderSourceTopbarActionsHost');
    if(title)title.textContent=current.name;
    if(subtitle)subtitle.textContent=sourceSubtitle(current);
    if(badge){badge.hidden=false;badge.textContent=statuses[current.status]||current.status;badge.className='order-source-topbar-badge '+sourceStatusClass(current.status);}
    if(actions)actions.innerHTML=sourceTopActions(current);
  }
  function detailPage(){
    hideSecret();const s=current;if(!s)return;
    syncSourceTopbar();
    const mobile=el('orderSourceMobileHead');
    if(mobile)mobile.innerHTML=`<div class="order-source-mobile-copy"><button class="btn-secondary" onclick="GFOrderSources.back()" aria-label="Torna alle fonti">←</button><h1>${esc(s.name)} ${sourceStatusBadge(s.status)}</h1><p>${esc(sourceSubtitle(s))}</p></div>${sourceTopActions(s,true)}`;
    const sample=s.kind==='api'
      ?`<div class="source-guide"><span class="source-guide-kicker">PASSO 1 · ORDINE DI PROVA</span><h3>Da dove arrivano i dati di prova?</h3><p>Il riquadro qui sotto contiene <strong>un esempio già preparato da GiroFacile</strong>: non devi cercarlo né copiarlo dal tuo gestionale.</p><ol><li>Premi <strong>Carica esempio per la verifica</strong>.</li><li>Controlla i campi riconosciuti e premi <strong>Verifica anteprima</strong>.</li><li>Per ricevere ordini veri, il tuo fornitore dovrà configurare l'invio alla nostra API con la chiave generata qui accanto.</li></ol><p>Se il tuo software non supporta le API, torna alle fonti e scegli <strong>File Excel o CSV</strong>.</p></div><details class="source-advanced" id="sourceTechnicalSample"><summary>Mostra o modifica il campione JSON <span>Configurazione avanzata</span></summary><p>Solo per chi conosce JSON: puoi sostituire l'esempio con i dati preparati dal tecnico del gestionale. Questa prova non importa ordini.</p><div class="source-code-editor"><div class="source-code-toolbar"><i></i><i></i><i></i><span>campione.json</span></div><textarea id="sourceSample" rows="14" spellcheck="false" aria-label="Campione JSON">${esc(JSON.stringify(example,null,2))}</textarea></div></details>`
      :`<div class="source-file-drop"><label>File CSV o XLSX<input id="sourceFile" type="file" accept=".csv,.xlsx"></label><p>Un solo foglio, senza formule. Mantieni i codici con zeri iniziali come testo.</p></div>`;
    const sampleFooter=s.status==='paused'
      ?'<div class="source-paused-notice">La fonte è in pausa. Riattivala per caricare e verificare nuovi campioni.</div>'
      :`<div class="source-sample-footer"><span class="source-sample-note"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>Il campione verifica la compatibilità: non importa ordini.</span><button class="btn-primary" onclick="GFOrderSources.upload()">${s.kind==='api'?'Carica esempio per la verifica':'Carica campione'}</button></div>`;
    const apiBody=s.kind==='api'
      ?`<div class="source-delivery-body"><div class="source-guide"><span class="source-guide-kicker">PASSO 2 · COLLEGAMENTO</span><h3>Come ricevere automaticamente gli ordini</h3><p>Non devi recuperare una chiave dal tuo gestionale: <strong>la chiave è generata da GiroFacile</strong> per autorizzare l'invio.</p><ol><li>Scarica le istruzioni da inviare al tecnico o fornitore software.</li><li>Genera una chiave e copiala subito: viene mostrata una sola volta.</li><li>Fai inviare un ordine di prova e controlla la prima ricezione riuscita.</li></ol></div><details class="source-advanced"><summary>Indirizzo API e dettagli tecnici <span>Per il tecnico</span></summary><span class="source-delivery-label">API Endpoint</span><div class="source-endpoint"><span class="source-endpoint-method">POST</span><code>/api/order-ingestion</code></div><p class="source-delivery-help">Aggiungi un <code>batch_id</code> univoco e invia ordini completi, non modifiche parziali.</p></details><div class="source-doc-actions"><button class="btn-secondary" onclick="GFOrderSources.downloadInstructions()">↓ Scarica istruzioni per il tuo gestionale</button></div><div class="source-delivery-divider"></div><span class="source-delivery-label">Stato ricezione ordini</span><div class="source-sync-state"><strong>${s.last_success?'Ultimo invio riuscito':'In attesa del primo ordine'}</strong><p>${s.last_success?esc(new Date(s.last_success+'Z').toLocaleString('it-IT')):'La fonte può essere attiva anche se il gestionale non ha ancora inviato ordini.'}</p><p>Stato fonte: ${esc(statuses[s.status]||s.status)} · Ordini acquisiti: ${s.order_count}</p></div><div class="source-delivery-divider"></div><span class="source-delivery-label">Chiave API generata da GiroFacile</span><div class="source-credential-state ${s.has_credential?'is-ready':'is-missing'}"><span class="source-credential-icon">${s.has_credential?'●':'!'}</span><div><strong>${s.has_credential?'Chiave già generata':'Chiave mancante'}</strong><span>${s.has_credential?'La chiave esistente non può essere riletta: puoi generarne una nuova.':'Genera una chiave per autorizzare il gestionale.'}</span></div></div>${manage()&&owner()&&s.status==='active'?`<div class="source-credential-actions"><button class="btn-secondary" onclick="GFOrderSources.action('rotate')">${s.has_credential?'Genera una nuova chiave':'Genera chiave API'}</button>${s.has_credential?'<button class="source-danger-outline" onclick="GFOrderSources.action(\'revoke\')">Disattiva chiave</button>':''}</div>`:'<p class="source-delivery-help">'+(!owner()?'Solo il titolare può gestire le chiavi.':'Attiva o riattiva la fonte prima di generare una chiave.')+'</p>'}<div id="sourceCredential"></div></div>`
      :`<div class="source-delivery-body"><span class="source-delivery-label">Importazione file</span><p>Carica un campione CSV o XLSX, associa le colonne e verifica l’anteprima. Gli ordini vengono inseriti solo dopo la conferma finale.</p><div class="source-delivery-divider"></div><span class="source-delivery-label">Stato fonte</span><div class="source-credential-state ${s.status==='active'?'is-ready':'is-missing'}"><span class="source-credential-icon">●</span><div><strong>${esc(statuses[s.status]||s.status)}</strong><span>${s.status==='active'?'Pronta per nuove importazioni.':'Riattiva la fonte per acquisire nuovi file.'}</span></div></div></div>`;
    el('orderSourceDetail').innerHTML=`<div class="order-source-detail-grid"><section class="order-source-panel"><div class="order-source-panel-head"><h2><svg viewBox="0 0 24 24"><path d="m8 9-3 3 3 3M16 9l3 3-3 3M14 5l-4 14"/></svg>${s.kind==='api'?'Verifica un ordine di prova':'Carica un campione'}</h2><p>Massimo 2 MB e 1000 ordini. L’anteprima è disponibile per 24 ore.</p></div>${sample}${sampleFooter}</section><aside class="order-source-panel"><div class="order-source-panel-head"><h2><svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="5" rx="1"/><rect x="4" y="14" width="16" height="5" rx="1"/></svg>${s.kind==='api'?'Invio dal gestionale':'Acquisizione file'}</h2><p>${s.kind==='api'?'Configura il tuo gestionale per inviare gli ordini a questo endpoint.':'Controlla lo stato e prepara una nuova importazione.'}</p></div>${apiBody}</aside><div class="source-detail-workflow"><div id="sourceMapping"></div><div id="sourceReport"></div><div id="sourceConfirm" class="page-actions"></div></div></div>`;
  }
  function open(id){
    if(busy)return;
    current=sources.find(s=>s.id===id);if(!current)return;
    staged=verified=null;showTab('ordine-fonte');detailPage();window.scrollTo({top:0,behavior:'auto'});
  }
  function back(){
    staged=verified=null;hideSecret();showTab('ordini-collegamenti');load();
  }
  async function deleteSource(){
    if(busy||!current||!manage())return;
    if(!confirm(`Eliminare definitivamente la fonte "${current.name}"? La connessione, le credenziali e lo storico tecnico della fonte saranno rimossi. Gli ordini già acquisiti resteranno disponibili.`))return;
    busy=true;const message=el('orderSourceMessage');if(message)message.textContent='Eliminazione fonte in corso…';
    try{
      await request('/'+current.id+'?version='+encodeURIComponent(current.version),{method:'DELETE'});
      current=staged=verified=null;if(message)message.textContent='';
      showTab('ordini-collegamenti');await refresh();
    }catch(err){if(message)message.textContent=err.message||String(err);}
    finally{busy=false;}
  }
  function editor(){
    hideSecret();const s=current;el('sourceWizard').hidden=false;
    el('sourceWizard').innerHTML=`<h2>${esc(s.name)} · ${statuses[s.status]}</h2><div class="page-actions">${manage()&&s.status==='active'?button('Metti in pausa',"action('pause')"):''}${manage()&&s.status==='paused'?button('Riattiva',"action('resume')"):''}${manage()&&s.status!=='removed'?button('Rimuovi fonte',"action('remove')"):''}</div>${s.status==='paused'||s.status==='removed'?'<p>La fonte non riceve ordini. Gli ordini acquisiti restano disponibili.</p>':`<h3>2. Carica un campione</h3><p>Massimo 2 MB e 1000 ordini. L'anteprima è disponibile per 24 ore.</p>${s.kind==='file'?'<label>File CSV o XLSX<input id="sourceFile" type="file" accept=".csv,.xlsx"></label><p>Un solo foglio, senza formule. Mantieni i codici con zeri iniziali come testo.</p>':`<label>Campione JSON<textarea id="sourceSample" rows="10" spellcheck="false">${esc(JSON.stringify(example,null,2))}</textarea></label><p>Il campione verifica i dati ma non importa ordini.</p>`}${button('Carica campione','upload()')}<div id="sourceMapping"></div><div id="sourceReport"></div><div id="sourceConfirm" class="page-actions"></div>`}${s.kind==='api'&&s.status==='active'?`<h3>Invio dal gestionale</h3><p>Endpoint: <code>POST /api/order-ingestion</code>. Autenticazione Bearer. Aggiungi un batch_id univoco e invia ordini completi, non modifiche parziali.</p><p>${s.has_credential?'Credenziale presente.':'Credenziale mancante: generala per autorizzare gli invii.'}</p>${manage()&&owner()?`<div class="page-actions">${button(s.has_credential?'Ruota credenziale':'Genera credenziale',"action('rotate')")}${s.has_credential?button('Revoca credenziale',"action('revoke')"):''}</div>`:'<p>Le credenziali sono gestite dal titolare.</p>'}<div id="sourceCredential"></div>`:''}`;
  }
  function upload(){return task(async()=>{
    if(current.kind==='file'){
      const file=el('sourceFile').files[0];if(!file)throw new Error('Scegli il file da caricare.');if(file.size>2097152)throw new Error('Il file supera 2 MB.');
      const body=new FormData();body.append('file',file);staged=await request('/'+current.id+'/upload',{method:'POST',body});
    }else{let data;try{data=JSON.parse(el('sourceSample').value);}catch{throw new Error('Controlla il formato JSON del campione.');}staged=await request('/'+current.id+'/sample',post(data));}
    verified=null;mapping();el('sourceReport').replaceChildren();el('sourceConfirm').replaceChildren();
  });}
  function mapping(){
    const selected=Object.keys(current.mapping).length?current.mapping:staged.suggested_mapping;
    el('sourceMapping').innerHTML=`<h3>3. Associa le colonne</h3><p>${staged.total} ordini. Prime ${staged.sample.length} righe del campione:</p><div class="tableWrap"><table><thead><tr>${staged.headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${staged.sample.map(r=>'<tr>'+staged.headers.map(h=>`<td>${esc(typeof r[h]==='object'?JSON.stringify(r[h]):String(r[h]??''))}</td>`).join('')+'</tr>').join('')}</tbody></table></div><p>* Identificativo esterno e numero ordine sono obbligatori. L'identificativo deve essere stabile e univoco per questa fonte: i successivi invii aggiornano lo stesso ordine.</p><div class="orders-form-grid">${fields.map(k=>`<label>${names[k]||esc(k)}<select onchange="GFOrderSources.invalidate()" data-source-field="${esc(k)}" ${manage()?'':'disabled'}><option value="">Non associato</option>${staged.headers.map(h=>`<option value="${esc(h)}" ${selected[k]===h?'selected':''}>${esc(h)}</option>`).join('')}</select></label>`).join('')}</div><p>${manage()?'Modificare le associazioni sospende gli invii fino alla nuova verifica e attivazione.':'Le associazioni sono gestite da chi configura le integrazioni.'}</p>${button('Verifica anteprima','preview()')}`;
  }
  function confirmation(){
    const ready=verified?.status==='preview_ready';
    el('sourceConfirm').innerHTML=ready?(current.status!=='active'?(manage()?button('Attiva fonte verificata',"action('activate')"):'<p>Il responsabile deve attivare la fonte verificata.</p>'):current.kind==='file'?(can('orders.import')?'<button class="btn-primary" onclick="GFOrderSources.commit()">Conferma importazione</button>':'<p>Serve il permesso di importazione per confermare.</p>'):'<p>Campione verificato. Gli ordini saranno acquisiti solo quando il gestionale li invierà alle API.</p>'):'';
  }
  function preview(){return task(async()=>{
    const selected={};el('sourceMapping').querySelectorAll('[data-source-field]').forEach(node=>{if(node.value)selected[node.dataset.sourceField]=node.value;});
    if(JSON.stringify(Object.entries(selected).sort())!==JSON.stringify(Object.entries(current.mapping).sort())){
      if(!manage())throw new Error('Le colonne non corrispondono. Richiedi la configurazione della fonte.');
      current=await request('/'+current.id,{method:'PUT',body:JSON.stringify({version:current.version,mapping:selected})});
    }
    verified=await request(`/${current.id}/runs/${staged.run_id}/preview`,post({}));renderReport(verified,'sourceReport',current.id);confirmation();await refresh();
  });}
  function renderReport(data,target,sid){
    const r=data.report;el(target).innerHTML=`<h3>${statuses[data.status]||esc(data.status)}</h3><p>Totale: ${r.total??0} · Nuovi: ${r.new??0} · Aggiornamenti: ${r.updated??0} · Invariati: ${r.unchanged??0} · Errori: ${r.invalid??0} · Clienti da verificare: ${r.unmatched??0}</p>${r.error?`<p class="orders-error">${esc(r.error)}</p>`:''}<p>${data.status==='completed'?'Acquisizione conclusa. Gli ordini nuovi o aggiornati sono da verificare prima della pianificazione.':'Questa verifica non inserisce ordini. Se sono presenti errori nessun ordine del lotto viene acquisito.'}</p><ol start="${(data.offset||0)+1}">${data.rows.map(row=>`<li>${esc(row.external_id||'Riga '+row.row)}: ${row.error?esc(row.error):actions[row.action]||''}${row.customer_match&&!['certain','linked'].includes(row.customer_match)?' · Cliente da verificare':''}${row.warnings?.length?' · '+esc(row.warnings.join('; ')):''}</li>`).join('')}</ol><div class="page-actions">${data.offset?button('Righe precedenti',`report(${sid},${data.id},${data.offset-100},'${target}')`):''}${data.has_more?button('Altre righe',`report(${sid},${data.id},${data.offset+100},'${target}')`):''}</div>`;
  }
  function commit(){return task(async()=>{verified=await request(`/${current.id}/runs/${staged.run_id}/commit`,post({confirm:true}));renderReport(verified,'sourceReport',current.id);confirmation();await refresh();});}
  function action(action){
    if(busy)return;
    const warnings={remove:'Rimuovere questa fonte? Gli ordini restano disponibili; la fonte non sarà riattivabile.',rotate:'Generare una NUOVA chiave API? La precedente cesserà immediatamente di funzionare. Il gestionale non potrà più inviare ordini finché non gli verrà comunicata la nuova chiave. Confermi?',revoke:'Disattivare la chiave e sospendere gli invii? Gli ordini già acquisiti resteranno disponibili. Per riprendere occorrerà riattivare la fonte e generare una nuova chiave.',pause:'Sospendere gli invii da questa fonte?'};
    if(warnings[action]&&!confirm(warnings[action]))return;
    const detailOpen=!el('tab-ordine-fonte').classList.contains('hidden');
    return task(async()=>{
      const result=await request('/'+current.id+'/action',post({version:current.version,action,...(action==='activate'?{run_id:staged.run_id}:{})}));
      const secret=result.credential;delete result.credential;current=result;
      if(detailOpen){staged=verified=null;detailPage();}
      else if(action==='activate'){editor();if(staged){mapping();renderReport(verified,'sourceReport',current.id);confirmation();}}
      else{staged=verified=null;editor();}
      if(secret){
        const credentialBox=el('sourceCredential');
        if(credentialBox){credentialBox.innerHTML='<div class="source-new-token" role="region" aria-label="Nuova chiave API"><strong>Nuova chiave generata</strong><p>Copia la chiave adesso e conservala in modo sicuro: non sarà più mostrata. La chiave precedente è disattivata.</p><label>Chiave riservata<textarea id="sourceToken" readonly rows="3" autocomplete="off" spellcheck="false"></textarea></label><button class="btn-primary" type="button" onclick="GFOrderSources.copyToken()">Copia la chiave</button><p id="sourceTokenMessage" role="status"></p></div>';el('sourceToken').value=secret;}
      }
      await refresh();
    });
  }

  function downloadInstructions(){
    if(!current||current.kind!=='api')return;
    const payload={batch_id:'lotto-univoco-001',orders:[{
      external_id:'ORD-001',number:'ORD-001',external_customer_id:'CLI-001',
      recipient_name:'Esempio cliente',delivery_address:'Via Roma 1, Milano',
      packages:3,weight_kg:12.5,tail_lift:false
    }]};
    const instructions=[
      'GIROFACILE — GUIDA PER IL TECNICO DEL GESTIONALE',
      'Fonte: '+current.name,
      'Questa guida NON contiene la chiave API segreta.',
      '',
      'ENDPOINT: POST '+window.location.origin+'/api/order-ingestion',
      'Content-Type: application/json',
      'Authorization: Bearer [INCOLLARE_QUI_LA_CHIAVE_RICEVUTA_DAL_TITOLARE]',
      '',
      'ESEMPIO JSON:',
      JSON.stringify(payload,null,2),
      '',
      'REGOLE:',
      '- Inviare batch_id unico per ogni lotto. Un retry identico riutilizza lo stesso batch_id.',
      '- Un batch_id già usato con contenuto diverso genera un errore.',
      '- external_id identifica stabilmente ogni ordine all’interno di questa fonte.',
      '- Inviare ordini completi: non sono supportate modifiche parziali.',
      '- Massimo 1000 ordini e 2 MB per richiesta.',
      '- Controllare il report della risposta prima di considerare importato il lotto.',
      '- Un nuovo token invalida immediatamente il vecchio: aggiornare il gestionale.',
      '',
      'VERIFICA:',
      'Inviare un ordine di prova con identificativo dedicato e controllare Ordini in GiroFacile.',
      'Il campione JSON della pagina serve solo a validare il formato: non invia ordini.',
      'Richiedere la chiave al titolare e trasmetterla tramite un canale sicuro.'
    ];
    const url=URL.createObjectURL(new Blob([instructions.join('\n')],{type:'text/plain;charset=utf-8'}));
    const link=document.createElement('a');
    link.href=url;link.download='girofacile-istruzioni-api.txt';
    document.body.appendChild(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),2000);
  }
  async function copyToken(){
    const input=el('sourceToken'),notice=el('sourceTokenMessage');
    if(!input?.value)return;
    try{
      await navigator.clipboard.writeText(input.value);
      if(notice)notice.textContent='Chiave copiata. Conservala e inseriscila nel gestionale.';
    }catch(error){
      input.focus();input.select();
      if(notice)notice.textContent='Copia automatica non consentita. La chiave è selezionata: usa Ctrl+C.';
    }
  }

  function history(id,next=0){return task(async()=>{
    const data=await request(`/${id}/runs?offset=${next}`);el('sourceHistory').hidden=false;
    el('sourceHistory').innerHTML='<h2>Storico della fonte</h2>'+data.items.map(r=>`<p>${esc(new Date(r.created_at+'Z').toLocaleString('it-IT'))} · ${statuses[r.status]||esc(r.status)} ${button('Report #'+r.id,`report(${id},${r.id},0,'sourceHistoryReport')`)}</p>`).join('')+`<div class="page-actions">${next?button('Precedenti',`history(${id},${next-20})`):''}${next+20<data.total?button('Successivi',`history(${id},${next+20})`):''}</div><div id="sourceHistoryReport"></div>`;el('sourceHistory').scrollIntoView({block:'start'});
  });}
  function report(sid,rid,next,target){return task(async()=>renderReport(await request(`/${sid}/runs/${rid}?offset=${next}`),target,sid));}
  window.GFOrderSources={load,hideSecret,downloadInstructions,copyToken,unavailable,invalidate,createForm,create,open,back,deleteSource,upload,preview,commit,action,history,report,page(delta){offset=Math.max(0,offset+delta*50);load();}};
})();
