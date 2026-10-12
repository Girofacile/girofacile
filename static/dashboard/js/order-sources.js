/* Guided source configuration. Secrets live only in the visible credential control. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id), can=k=>!window.GFCompanyAccess||GFCompanyAccess.can(k);
  const manage=()=>can('orders.integrations'), owner=()=>!window.GFCompanyAccess?.isCollaborator();
  const names={external_id:'Identificativo esterno *',number:'Numero ordine *',external_customer_id:'Codice cliente',recipient_name:'Destinatario',delivery_address:'Indirizzo consegna',requested_date:'Data richiesta',time_from:'Dalle',time_to:'Alle',weight_kg:'Peso (kg)',packages:'Colli',pallets:'Pallet',volume_m3:'Volume (m³)',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti',notes:'Note',items:'Articoli (JSON)'};
  const statuses={draft:'Da configurare',active:'Attiva',paused:'In pausa',removed:'Rimossa',uploaded:'Campione caricato',preview_ready:'Anteprima valida',preview_invalid:'Anteprima con errori',completed:'Acquisizione completata',failed:'Acquisizione fallita',source_activate:'Fonte attivata',source_pause:'Fonte sospesa',source_resume:'Fonte riattivata',source_remove:'Fonte rimossa',source_rotate:'Credenziale generata',source_revoke:'Credenziale revocata',source_fields_updated:'Dati da importare aggiornati'};
  const actions={new:'Nuovo',updated:'Da aggiornare',unchanged:'Invariato'};
  const sourceStatusClass=status=>status==='active'?'is-active':status==='paused'?'is-paused':status==='draft'?'is-draft':status==='removed'?'is-removed':'';
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
  function hideSecret(){const box=el('sourceCredential');if(box)box.replaceChildren();const secret=el('connectorSecret');if(secret)secret.value='';}
  function sourceCard(s){
    const isRemoved=s.status==='removed';
    const isApi=s.kind==='api';
    const count=Number(s.order_count)||0;
    const last=s.last_success?esc(new Date(s.last_success+'Z').toLocaleString('it-IT')):'nessuna';
    const type=s.connector?({email:'EMAIL',shopify:'SHOPIFY',woocommerce:'WOOCOMMERCE'}[s.connector.provider]):isApi?'API STANDARD':'FILE CSV / XLSX';
    const description=isRemoved
      ?'Questa fonte è stata rimossa. Puoi consultare lo storico degli ordini importati.'
      :s.connector?(s.status==='paused'?'Ricezione in pausa.':s.connector.received?'Invii ricevuti. Controlla lo storico per gli esiti.':'In attesa del primo invio dal collegamento configurato.')
      :isApi&&s.status==='active'
        ?(s.has_credential?'Pronta a ricevere richieste autenticate. Il gestionale deve essere configurato per inviarle.':'Credenziale da generare: nessun invio autorizzato.')
        :s.status==='paused'?'Fonte in pausa. Puoi riattivarla dalle impostazioni.':'';
    const hasIssue=s.last_run?.status==='failed'||s.last_run?.status==='preview_invalid';
    const importBtn=!isRemoved&&s.kind==='file'&&['active','draft'].includes(s.status)
      ?`<button type='button' class='btn-primary orders-source-import-btn' onclick='GFOrderImport.start(${s.id})'>Importa file</button>`:'';
    const openBtn=!isRemoved?`<button type='button' class='btn-secondary orders-source-open-btn' onclick='GFOrderSources.open(${s.id})'>Apri</button>`:'';
    const historyBtn=`<button type='button' class='btn-secondary orders-source-history-btn' onclick='GFOrderSources.history(${s.id},0)'>Storico <span aria-hidden='true'>›</span></button>`;
    const removeBtn=isRemoved&&manage()?`<button type='button' class='orders-source-remove-btn' onclick='GFOrderSources.deleteFromList(${s.id})'><span aria-hidden='true'>⌫</span> Rimuovi</button>`:'';
    return `<article class='orders-source-card ${isRemoved?'is-removed':''}'>
      <div class='orders-source-card-copy'>
        <h3>${esc(s.name)}</h3>
        <div class='orders-source-meta'><span>${type}</span>${sourceStatusBadge(s.status)}</div>
        <p class='orders-source-stat'><strong>${count} ${count===1?'ordine':'ordini'}</strong><span aria-hidden='true'> · </span>Ultima acquisizione: ${last}</p>
        ${description&&!isRemoved?`<p class='orders-source-info'>${description}</p>`:''}
        ${hasIssue?`<p class='orders-source-issue'>Ultima verifica o acquisizione con errori. Consulta lo storico.</p>`:''}
      </div>
      <div class='page-actions orders-source-card-actions'>${importBtn}${openBtn}${historyBtn}${removeBtn}</div>
      ${isRemoved?`<p class='orders-source-removed-note'>${description}</p>`:''}
    </article>`;
  }
  async function refresh(){
    const data=await request('?offset='+offset);
    sources=data.items;
    fields=['external_id','number',...data.fields.filter(k=>!['external_id','number'].includes(k))];
    el('sourceCategories').hidden=!manage();
    const createTopButton=el('ordersConnectionsNewSource');
    if(createTopButton)createTopButton.hidden=!manage();
    const count=el('sourceCount');
    if(count)count.textContent=`${data.total} ${data.total===1?'fonte':'fonti'}`;
    el('sourceList').innerHTML=sources.length
      ?'<div class="orders-source-list-grid">'+sources.map(sourceCard).join('')+'</div>'
      :'<div class="orders-sources-empty">Nessuna fonte configurata.</div>';
    const pagination=el('sourcePagination');
    if(pagination)pagination.hidden=data.total<=50;
    el('sourcePage').textContent=`${data.total} fonti`;
    el('sourcePrevious').disabled=offset===0;
    el('sourceNext').disabled=offset+50>=data.total;
  }
  function deleteFromList(id){
    const source=sources.find(s=>s.id===id);
    if(!source||source.status!=='removed'||!manage()||busy)return;
    if(!confirm(`Eliminare definitivamente la fonte "${source.name}"? La configurazione e lo storico tecnico saranno eliminati, ma gli ordini già acquisiti saranno conservati.`))return;
    return task(async()=>{
      await request('/'+source.id+'?version='+encodeURIComponent(source.version),{method:'DELETE'});
      await refresh();
    });
  }
  function load(){hideSecret();return task(refresh);}
  function unavailable(kind){
    if(!manage()||busy)return;hideSecret();current=staged=verified=null;el('sourceWizard').hidden=false;
    const email=kind==='email';
    el('sourceWizard').innerHTML=`<h2>${email?'Ricevi ordini via email':'Collega il negozio online'}</h2><p>${email?'Ogni azienda riceve un indirizzo dedicato: imposta una regola di inoltro nella casella dove arrivano gli ordini.':'Scegli la piattaforma. Dopo il collegamento, i nuovi ordini arrivano automaticamente in GiroFacile, da verificare prima del giro.'}</p>${!owner()?'<p>Il titolare deve configurare questo collegamento.</p>':`<form onsubmit="GFOrderSources.createConnector(event)"><div class="orders-form-grid"><label>Nome collegamento<input id="connectorName" maxlength="160" required placeholder="${email?'Ordini via email':'Negozio online'}"></label><label ${email?'hidden':''}>Piattaforma<select id="connectorProvider"><option value="${email?'email':'shopify'}">${email?'Email':'Shopify'}</option>${email?'':'<option value="woocommerce">WooCommerce</option>'}</select></label>${email?'':`<label>Dominio del negozio<input id="connectorStore" required placeholder="negozio.myshopify.com"></label><label>Chiave di firma<input id="connectorSecret" type="password" autocomplete="new-password" minlength="16" maxlength="500" required></label>`}</div>${email?'<p>Importazione automatica da allegati CSV/Excel e messaggi con righe Numero ordine:, Destinatario:, Indirizzo:. PDF, immagini e testo libero vanno controllati manualmente e sono segnalati nello storico.</p>':'<details open><summary>Dove trovare la chiave</summary><p>Shopify: Impostazioni → Notifiche → Webhook, chiave di firma. WooCommerce: scegli una chiave di almeno 16 caratteri e usa la stessa nella configurazione del webhook.</p><p>Dopo il salvataggio ti mostreremo l’indirizzo da inserire nel negozio. Non viene letto lo storico degli ordini.</p></details>'}<button class="btn-primary" type="submit">${email?'Crea indirizzo di ricezione':'Prepara collegamento'}</button><p id="connectorMessage" role="status"></p></form>`}${email?'':'<details><summary>Uso un’altra piattaforma</summary><p>Il fornitore del negozio può collegarsi tramite le API standard di GiroFacile. Ogni piattaforma richiede una configurazione compatibile.</p><button class="btn-secondary" onclick="GFOrderSources.createForm(\'api\')">Configura API standard</button></details>'}`;
    el('sourceWizard').scrollIntoView({block:'start'});
  }
  function createConnector(event){event.preventDefault();return task(async()=>{
    const message=el('connectorMessage'),secret=el('connectorSecret');
    try{
      const created=await request('/connectors',post({name:el('connectorName').value,provider:el('connectorProvider').value,store:el('connectorStore')?.value||'',secret:secret?.value||''}));
      if(secret)secret.value='';await refresh();current=created;el('sourceWizard').hidden=true;showTab('ordine-fonte');detailPage();window.scrollTo({top:0,behavior:'auto'});
    }catch(error){message.textContent=error.message;}
  });}
  function connectorDetail(s){
    const c=s.connector,email=c.provider==='email';
    el('orderSourceDetail').innerHTML=`<section class="source-api-card source-api-card-body"><h2>${email?'Inoltra qui gli ordini': 'Completa il collegamento nel negozio'}</h2><label>${email?'Indirizzo dedicato all’azienda':'Indirizzo di ricezione'}<input readonly value="${esc(email?c.address:c.webhook_url)}" onclick="this.select()"></label>${email?'<ol><li>Nella casella aziendale crea una regola che inoltri solo le email degli ordini a questo indirizzo.</li><li>Invia un ordine con allegato CSV/Excel oppure con righe Numero ordine:, Destinatario:, Indirizzo:.</li><li>Apri Ordini per controllare la consegna.</li></ol><p>PDF e messaggi non strutturati sono segnalati nello storico: consulta l’email originale e inserisci l’ordine manualmente. L’indirizzo dedicato va condiviso solo con chi deve inviare ordini.</p>':`<ol><li>${c.provider==='shopify'?'Shopify: Impostazioni → Notifiche → Webhook. Crea un webhook Ordine creato, formato JSON.':'WooCommerce: Impostazioni → Avanzate → Webhook. Crea un webhook Ordine creato, stato Attivo.'}</li><li>Incolla l’indirizzo di ricezione qui sopra. Usa la stessa chiave di firma inserita in GiroFacile.</li><li>Crea un ordine di prova con nome e indirizzo di spedizione completi.</li></ol><p>Si ricevono i nuovi ordini. Modifiche, annullamenti e ordini precedenti devono essere gestiti separatamente.</p>`}<p role="status">${c.received?'Ricezione verificata: almeno un messaggio autenticato è arrivato. Controlla gli esiti nello storico.':'In attesa del primo invio reale. La creazione del collegamento non verifica l’inoltro.'}</p>${s.last_run?.summary?.error?`<p class="orders-error">${esc(s.last_run.summary.error)}</p>`:''}</section><section class="source-api-card source-api-card-body">${GFOrderImport.fieldChoices(s.excluded_fields||[],'api',!manage())}${manage()?'<button class="btn-primary" onclick="GFOrderSources.saveFields()">Salva dati da importare</button>':''}<p id="sourceFieldsMessage" role="status"></p></section>`;
  }
  function invalidate(){verified=null;el('sourceConfirm')?.replaceChildren();}
  function createForm(kind){
    if(kind==='file'){GFOrderImport.start();return;}
    if(!manage()||busy)return;current=staged=verified=null;hideSecret();
    el('sourceWizard').hidden=false;
    el('sourceWizard').innerHTML=`<h2>1. Scegli la fonte</h2><form onsubmit="GFOrderSources.create(event)"><div class="orders-form-grid"><label>Nome della fonte<input id="sourceName" required maxlength="160" placeholder="Es. Gestionale magazzino"></label><label>Software utilizzato (facoltativo)<input id="sourceSoftware" maxlength="160" placeholder="Nome del gestionale"></label><label>Modalità disponibile<select id="sourceKind"><option value="file" ${kind==='file'?'selected':''}>File Excel o CSV</option><option value="api" ${kind==='api'?'selected':''}>API standard</option><option value="custom">Collegamento personalizzato: informazioni</option></select></label></div><p>Le API richiedono la configurazione dell'invio da parte di chi gestisce il tuo software. Nessun connettore proprietario viene attivato automaticamente.</p><button class="btn-primary" type="submit">Crea fonte e prosegui</button></form>`;
    el('sourceWizard').scrollIntoView({block:'start'});
  }
  function create(event){event.preventDefault();if(el('sourceKind').value==='custom'){el('sourceMessage').textContent='Collegamento personalizzato da predisporre con il fornitore: comunica nome e versione del software, esempio anonimo del tracciato, identificativi stabili e frequenza degli invii. Le modalità operative disponibili sono file o API standard: selezionane una per proseguire.';return;}return task(async()=>{current=await request('',post({name:el('sourceName').value,kind:el('sourceKind').value,software:el('sourceSoftware').value}));staged=verified=null;if(current.kind==='api'){current=await request('/'+current.id+'/fields',{method:'PUT',body:JSON.stringify({version:current.version,excluded_fields:[]})});await refresh();current=sources.find(s=>s.id===current.id)||current;showTab('ordine-fonte');detailPage();window.scrollTo({top:0,behavior:'auto'});}else{editor();await refresh();}});}
  function sourceSubtitle(s){if(s.connector)return 'Ricezione automatica degli ordini aziendali';return s.kind==='api'?'Genera la chiave API e verifica il collegamento per attivare la fonte.':'Gestione fonte file e validazione degli ordini importati.';}
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

  // Key-first source setup: the credential is visible before optional technical checks.
  function prioritizeApiKey(s){
    if(s.kind!=='api')return;
    const root=el('orderSourceDetail'), grid=root.querySelector('.order-source-detail-grid');
    if(!grid)return;
    const left=grid.querySelector('section.order-source-panel');
    const right=grid.querySelector('aside.order-source-panel');
    const body=right?.querySelector('.source-delivery-body');
    if(!body)return;

    const hero=document.createElement('section');
    hero.className='gf-key-first-hero';
    hero.innerHTML='<div class="gf-key-first-heading"><span class="gf-key-first-mark" aria-hidden="true">🔑</span><div><span class="gf-key-first-kicker">PASSO 1 · COLLEGAMENTO API</span><h2>Genera la tua chiave API</h2><p>Questa chiave permette al tuo gestionale di inviare ordini a GiroFacile. Generala, copiala e comunicala al tecnico che gestisce il software.</p></div></div><div class="gf-key-first-body"></div><p class="gf-key-first-footnote">La chiave viene mostrata solo quando la generi. Se l’hai persa, puoi generarne una nuova: la precedente smetterà subito di funzionare.</p>';
    const target=hero.querySelector('.gf-key-first-body');
    const state=body.querySelector('.source-credential-state');
    const actions=body.querySelector('.source-credential-actions');
    const credential=body.querySelector('#sourceCredential');
    if(state)target.appendChild(state);
    const owner=!window.GFCompanyAccess?.isCollaborator();
    const canManage=!window.GFCompanyAccess||GFCompanyAccess.can('orders.integrations');
    if(actions){
      const primary=actions.querySelector('.btn-secondary');
      if(primary){primary.classList.remove('btn-secondary');primary.classList.add('btn-primary','gf-key-first-generate');}
      const revoke=actions.querySelector('.source-danger-outline');
      if(revoke)revoke.classList.add('gf-key-first-revoke');
      target.appendChild(actions);
    }else if(s.status==='draft'&&owner&&canManage){
      const button=document.createElement('button');
      button.type='button';
      button.className='btn-primary gf-key-first-generate';
      button.textContent=s.has_credential?'Genera una nuova chiave':'Genera chiave API';
      button.addEventListener('click',()=>window.GFOrderSources.action('rotate'));
      target.appendChild(button);
    }else{
      const tip=document.createElement('p');
      tip.className='gf-key-first-tip';
      tip.textContent=s.status==='paused'?'La fonte è in pausa: riattivala dal comando in alto per gestire la chiave.':owner?'La fonte non consente nuove chiavi in questo stato.':'Solo il titolare può creare o sostituire una chiave.';
      target.appendChild(tip);
    }
    if(credential)target.appendChild(credential);
    if(s.has_credential&&!el('sourceToken')){
      const info=document.createElement('p');
      info.className='gf-key-first-tip';
      info.textContent='Chiave già creata: non è recuperabile per motivi di sicurezza. Per copiarne una nuova usa il pulsante qui sopra.';
      target.appendChild(info);
    }
    root.prepend(hero);
    const guideLeft=left.querySelector('.source-guide');
    if(guideLeft)guideLeft.innerHTML='<span class="source-guide-kicker">PASSO 3 · PROVA FACOLTATIVA</span><h3>Verifica un ordine di esempio</h3><p>GiroFacile ha già preparato un ordine di prova. Premi il pulsante qui sotto per controllarne il formato, poi verifica e attiva la fonte. Non devi scrivere codice.</p>';
    const guideRight=right.querySelector('.source-guide');
    if(guideRight)guideRight.innerHTML='<span class="source-guide-kicker">PASSO 2 · ISTRUZIONI</span><h3>Invia le istruzioni al tuo fornitore</h3><p>Scarica la guida e inviala al tecnico. Comunica la chiave separatamente, in modo sicuro. La ricezione degli ordini partirà soltanto dopo l’attivazione.</p>';
    const duplicate=Array.from(body.querySelectorAll('.source-delivery-label')).find(x=>x.textContent.includes('Chiave API generata'));
    if(duplicate)duplicate.remove();
    Array.from(body.querySelectorAll('.source-delivery-help')).filter(x=>x.textContent.includes('Attiva o riattiva la fonte prima')).forEach(x=>x.remove());
    grid.classList.add('gf-key-first-secondary');
    const code=left.querySelector('#sourceTechnicalSample');
    if(code)code.open=false;
    if(/^(localhost|127\.0\.0\.1)$/i.test(window.location.hostname)){
      const local=document.createElement('p');
      local.className='gf-key-first-local';
      local.textContent='Stai usando GiroFacile in locale: 127.0.0.1 non è raggiungibile dal gestionale su un altro computer. Per un collegamento remoto serve un indirizzo pubblico HTTPS.';
      right.querySelector('.source-doc-actions')?.after(local);
    }
  }

  function apiConnectionSample(){
    const base=example.orders[0], row={...base};
    for(const [field,external] of Object.entries(current?.mapping||{})){
      if(field in base && external)row[external]=base[field];
    }
    return {orders:[row]};
  }
  function apiDetailPage(s){
    const ownerUser=owner(), canManage=manage();
    const keyButton=canManage&&ownerUser
      ?`<button class="btn-secondary source-api-key-generate" onclick="GFOrderSources.action('rotate')">${s.has_credential?'Genera nuova chiave':'Genera chiave API'}</button>`
      :'';
    const revokeButton=canManage&&ownerUser&&s.has_credential&&s.status==='active'
      ?'<button class="source-danger-outline" type="button" onclick="GFOrderSources.action(\'revoke\')">Disattiva chiave</button>'
      :'';
    const keyState=s.has_credential
      ?'<div class="source-api-key-configured"><span class="source-api-key-status-icon" aria-hidden="true">✓</span><div><strong>Chiave API configurata</strong><p>Per sicurezza la chiave esistente non può essere visualizzata. Generane una nuova solo se devi sostituirla.</p></div></div>'
      :'<div class="source-api-key-configured is-missing"><span class="source-api-key-status-icon" aria-hidden="true">!</span><div><strong>Nessuna chiave generata</strong><p>Genera una chiave e copiala subito: verrà mostrata una sola volta.</p></div></div>';
    const waiting=!s.last_success;
    const receptionTitle=waiting?'In attesa del primo ordine':'Ricezione attiva';
    const receptionCopy=waiting
      ?(s.status==='active'?'La fonte è pronta: compariranno qui i dati non appena arriverà il primo ordine valido.':'La fonte si attiverà dopo la verifica del collegamento.')
      :`Ultima acquisizione riuscita: ${esc(new Date(s.last_success+'Z').toLocaleString('it-IT'))}.`;
    el('orderSourceDetail').innerHTML=`
      <div class="source-api-settings-layout">
        <div class="source-api-settings-main">
          <section class="source-api-card source-api-card-body">${GFOrderImport.fieldChoices(s.excluded_fields||[],'api',!canManage)}${canManage?'<button class="btn-primary" onclick="GFOrderSources.saveFields()">Salva dati da importare</button>':''}<p id="sourceFieldsMessage" role="status"></p></section>
          <section class="source-api-card source-api-key-card">
            <div class="source-api-card-head">
              <div class="source-api-card-title"><span class="source-api-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="8" cy="15" r="3"/><path d="m10.5 12.5 7-7M15 5h4v4M11 14l2 2"/></svg></span><h2>Chiave API</h2></div>
              ${keyButton}${revokeButton}
            </div>
            <div class="source-api-card-body">
              ${keyState}
              <div id="sourceCredential"></div>
            </div>
          </section>

          <section class="source-api-card source-api-test-card">
            <div class="source-api-card-head">
              <div class="source-api-card-title"><span class="source-api-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m8 9-3 3 3 3M16 9l3 3-3 3M14 5l-4 14"/></svg></span><h2>Verifica connessione</h2></div>
            </div>
            <div class="source-api-test-body">
              <div><strong>Verifica con un ordine di esempio</strong><p>GiroFacile ha già preparato un payload di prova. Esegui il test per controllare la formattazione e attivare definitivamente la fonte senza dover scrivere codice.</p><div id="sourceConnectionResult"></div><button class="btn-secondary" type="button" onclick="GFOrderSources.downloadInstructions()">Scarica istruzioni per il tuo gestionale</button></div>
              <button class="btn-primary source-api-test-button" onclick="GFOrderSources.testConnection()"><span aria-hidden="true">➤</span> Esegui test</button>
            </div>
          </section>
        </div>

        <aside class="source-api-card source-api-reception-card">
          <div class="source-api-card-head">
            <div class="source-api-card-title"><span class="source-api-card-icon is-muted" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M4 19V14M9 19V10M14 19V7M19 19V4"/></svg></span><h2>Stato ricezione</h2></div>
          </div>
          <div class="source-api-reception-body">
            <div class="source-api-reception-symbol ${waiting?'is-waiting':'is-ready'}" aria-hidden="true">${waiting?'<svg viewBox="0 0 24 24"><path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 9s-8 4-8 9M16 3c0 5-8 5-8 9s8 4 8 9"/></svg>':'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="m8.5 12 2.3 2.3 4.8-5"/></svg>'}<i></i></div>
            <strong class="source-api-reception-title">${receptionTitle}</strong>
            <p>${receptionCopy}</p>
            <div class="source-api-order-count"><span>Ordini acquisiti</span><strong>${Number(s.order_count||0)}</strong></div>
          </div>
        </aside>
      </div>`;
  }
  function detailPage(){
    hideSecret();const s=current;if(!s)return;
    syncSourceTopbar();
    const mobile=el('orderSourceMobileHead');
    if(mobile)mobile.innerHTML=`<div class="order-source-mobile-copy"><button class="btn-secondary" onclick="GFOrderSources.back()" aria-label="Torna alle fonti">←</button><h1>${esc(s.name)} ${sourceStatusBadge(s.status)}</h1><p>${esc(sourceSubtitle(s))}</p></div>${sourceTopActions(s,true)}`;
    if(s.connector){connectorDetail(s);return;}
    if(s.kind==='api'){apiDetailPage(s);return;}
    const sample=`<div class="source-file-drop"><label>File CSV o XLSX<input id="sourceFile" type="file" accept=".csv,.xlsx"></label><p>Un solo foglio, senza formule. Mantieni i codici con zeri iniziali come testo.</p></div>`;
    const sampleFooter=s.status==='paused'
      ?'<div class="source-paused-notice">La fonte è in pausa. Riattivala per caricare e verificare nuovi campioni.</div>'
      :'<div class="source-sample-footer"><span class="source-sample-note"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>Il campione verifica la compatibilità: non importa ordini.</span><button class="btn-primary" onclick="GFOrderSources.upload()">Carica campione</button></div>';
    const fileBody=`<div class="source-delivery-body"><span class="source-delivery-label">Importazione file</span><p>Carica un campione CSV o XLSX, associa le colonne e verifica l’anteprima. Gli ordini vengono inseriti solo dopo la conferma finale.</p><div class="source-delivery-divider"></div><span class="source-delivery-label">Stato fonte</span><div class="source-credential-state ${s.status==='active'?'is-ready':'is-missing'}"><span class="source-credential-icon">●</span><div><strong>${esc(statuses[s.status]||s.status)}</strong><span>${s.status==='active'?'Pronta per nuove importazioni.':'Riattiva la fonte per acquisire nuovi file.'}</span></div></div></div>`;
    el('orderSourceDetail').innerHTML=`<div class="order-source-detail-grid"><section class="order-source-panel"><div class="order-source-panel-head"><h2><svg viewBox="0 0 24 24"><path d="m8 9-3 3 3 3M16 9l3 3-3 3M14 5l-4 14"/></svg>Carica un campione</h2><p>Massimo 2 MB e 1000 ordini. L’anteprima è disponibile per 24 ore.</p></div>${sample}${sampleFooter}</section><aside class="order-source-panel"><div class="order-source-panel-head"><h2><svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="5" rx="1"/><rect x="4" y="14" width="16" height="5" rx="1"/></svg>Acquisizione file</h2><p>Controlla lo stato e prepara una nuova importazione.</p></div>${fileBody}</aside><div class="source-detail-workflow"><div id="sourceMapping"></div><div id="sourceReport"></div><div id="sourceConfirm" class="page-actions"></div></div></div>`;
  }
  function testConnection(){
    if(busy||!current||current.kind!=='api')return;
    return task(async()=>{
      staged=await request('/'+current.id+'/sample',post(apiConnectionSample()));
      const usableCurrent=current.mapping&&Object.keys(current.mapping).length&&Object.values(current.mapping).every(value=>staged.headers.includes(value));
      const selected=usableCurrent?current.mapping:staged.suggested_mapping;
      if(JSON.stringify(Object.entries(selected).sort())!==JSON.stringify(Object.entries(current.mapping||{}).sort())){
        current=await request('/'+current.id,{method:'PUT',body:JSON.stringify({version:current.version,mapping:selected})});
      }
      verified=await request(`/${current.id}/runs/${staged.run_id}/preview`,post({}));
      if(verified.status!=='preview_ready')throw new Error('Il test ha rilevato dati non validi. Controlla la configurazione della fonte e riprova.');
      if(current.status!=='active'){
        const activated=await request('/'+current.id+'/action',post({version:current.version,action:'activate',run_id:staged.run_id}));
        current=activated;
      }
      await refresh();
      current=sources.find(item=>item.id===current.id)||current;
      staged=verified=null;
      detailPage();
      const result=el('sourceConnectionResult');
      if(result)result.innerHTML='<div class="source-api-test-success"><span aria-hidden="true">✓</span><div><strong>Collegamento verificato</strong><p>Il formato è valido e la fonte è pronta a ricevere ordini dal gestionale.</p></div></div>';
    });
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
    const r=data.report;el(target).innerHTML=`<h3>${statuses[data.status]||esc(data.status)}</h3>${r.email_subject?`<p>Email: ${esc(r.email_subject)}</p>`:''}${r.provider_event?`<p>Riferimento invio: ${esc(r.provider_event)}</p>`:''}<p>Totale: ${r.total??0} · Nuovi: ${r.new??0} · Aggiornamenti: ${r.updated??0} · Invariati: ${r.unchanged??0} · Errori: ${r.invalid??0}</p>${r.error?`<p class="orders-error">${esc(r.error)}</p>`:''}<p>${data.status==='completed'?'Acquisizione conclusa. Gli ordini nuovi o aggiornati sono da verificare prima della pianificazione.':'Questa verifica non inserisce ordini. Se sono presenti errori nessun ordine del lotto viene acquisito.'}</p><ol start="${(data.offset||0)+1}">${data.rows.map(row=>`<li>${esc(row.external_id||'Riga '+row.row)}: ${row.error?esc(row.error):actions[row.action]||''}${row.customer_match&&!['certain','linked'].includes(row.customer_match)?' · Cliente da verificare':''}${row.warnings?.length?' · '+esc(row.warnings.join('; ')):''}</li>`).join('')}</ol><div class="page-actions">${data.offset?button('Righe precedenti',`report(${sid},${data.id},${data.offset-100},'${target}')`):''}${data.has_more?button('Altre righe',`report(${sid},${data.id},${data.offset+100},'${target}')`):''}</div>`;
  }
  function commit(){return task(async()=>{verified=await request(`/${current.id}/runs/${staged.run_id}/commit`,post({confirm:true}));renderReport(verified,'sourceReport',current.id);confirmation();await refresh();});}
  function action(action){
    if(busy)return;
    const warnings={remove:'Rimuovere questa fonte? Gli ordini restano disponibili; la fonte non sarà riattivabile.',rotate:current?.has_credential?'Generare una NUOVA chiave API? La precedente cesserà immediatamente di funzionare. Il gestionale non potrà più inviare ordini finché non gli verrà comunicata la nuova chiave. Confermi?':'Generare la tua prima chiave API? Copiala subito e conservala. Gli ordini potranno essere ricevuti solo dopo aver verificato e attivato la fonte.',revoke:'Disattivare la chiave e sospendere gli invii? Gli ordini già acquisiti resteranno disponibili. Per riprendere occorrerà riattivare la fonte e generare una nuova chiave.',pause:'Sospendere gli invii da questa fonte?'};
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
        if(credentialBox){credentialBox.innerHTML='<div class="source-new-token" role="region" aria-label="Nuova chiave API"><div class="source-new-token-heading"><span aria-hidden="true">✓</span><div><strong>Nuova chiave generata con successo</strong><p>Copia la chiave adesso e conservala in modo sicuro. Non sarà più mostrata.</p></div></div><div class="source-token-row"><input id="sourceToken" readonly autocomplete="off" spellcheck="false" aria-label="Chiave API generata"><button class="btn-primary" type="button" onclick="GFOrderSources.copyToken()">▣&nbsp; Copia</button></div><p id="sourceTokenMessage" role="status"></p></div>';el('sourceToken').value=secret;}
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

  function saveFields(){return task(async()=>{
    try{current=await request('/'+current.id+'/fields',{method:'PUT',body:JSON.stringify({version:current.version,excluded_fields:GFOrderImport.readChoices('api')})});el('sourceFieldsMessage').textContent='Scelte salvate per i prossimi ordini.';}
    catch(error){el('sourceFieldsMessage').textContent=error.message;}
  });}
  function history(id,next=0){return task(async()=>{
    const data=await request(`/${id}/runs?offset=${next}`);el('sourceHistory').hidden=false;
    el('sourceHistory').innerHTML='<h2>Storico della fonte</h2>'+data.items.map(r=>`<p>${esc(new Date(r.created_at+'Z').toLocaleString('it-IT'))} · ${statuses[r.status]||esc(r.status)} ${button('Report #'+r.id,`report(${id},${r.id},0,'sourceHistoryReport')`)}</p>`).join('')+`<div class="page-actions">${next?button('Precedenti',`history(${id},${next-20})`):''}${next+20<data.total?button('Successivi',`history(${id},${next+20})`):''}</div><div id="sourceHistoryReport"></div>`;el('sourceHistory').scrollIntoView({block:'start'});
  });}
  function report(sid,rid,next,target){return task(async()=>renderReport(await request(`/${sid}/runs/${rid}?offset=${next}`),target,sid));}
  window.GFOrderSources={createConnector,deleteFromList,saveFields,load,hideSecret,downloadInstructions,copyToken,unavailable,invalidate,createForm,create,open,back,deleteSource,testConnection,upload,preview,commit,action,history,report,page(delta){offset=Math.max(0,offset+delta*50);load();}};
})();
