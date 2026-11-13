/* Guided source configuration. Secrets live only in the visible credential control. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id), can=k=>!window.GFCompanyAccess||GFCompanyAccess.can(k);
  const manage=()=>can('orders.integrations'), owner=()=>!window.GFCompanyAccess?.isCollaborator();
  const integrationsEnabled=()=>window.GFPlanAccess?.has('has_order_integrations')===true;
  const requireIntegration=()=>window.GFPlanAccess?.require('has_order_integrations','API, Shopify e WooCommerce')===true;
  const upgradeMarkup=()=>'<section class="gf-panel"><div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">Integrazioni dal piano Business</h2><p class="gf-muted">API, Shopify e WooCommerce richiedono il piano Business o Pro. Puoi continuare a importare gli ordini da file CSV/Excel.</p><div class="gf-cluster"><button type="button" class="gf-button" data-variant="secondary" onclick="GFOrderImport.start()">Importa un file</button>'+ (owner()?'<button type="button" class="gf-button" data-variant="primary" onclick="openUpgradePanelFor(\'business\')">Scopri Business</button>':'')+'</div></div></section>';
  function showIntegrationUpgrade(){el('sourceWizard').hidden=false;el('sourceWizard').innerHTML=upgradeMarkup();}

  const names={external_id:'Identificativo esterno *',number:'Numero ordine *',external_customer_id:'Codice cliente',recipient_name:'Destinatario',phone:'Telefono destinatario',delivery_address:'Indirizzo consegna',requested_date:'Data richiesta',time_from:'Dalle',time_to:'Alle',weight_kg:'Peso (kg)',packages:'Colli',pallets:'Pallet',volume_m3:'Volume (m³)',tail_lift:'Sponda',pallet_truck:'Transpallet',ztl:'ZTL',requirements:'Requisiti',notes:'Note',items:'Articoli (JSON)'};
  const statuses={development:'In fase di sviluppo',draft:'Da configurare',active:'Attiva',paused:'In pausa',removed:'Rimossa',uploaded:'Campione caricato',preview_ready:'Anteprima valida',preview_invalid:'Anteprima con errori',completed:'Acquisizione completata',failed:'Acquisizione fallita',source_activate:'Fonte attivata',source_pause:'Fonte sospesa',source_resume:'Fonte riattivata',source_remove:'Fonte rimossa',source_rotate:'Credenziale generata',source_revoke:'Credenziale revocata',source_fields_updated:'Dati da importare aggiornati'};
  const actions={new:'Nuovo',updated:'Da aggiornare',unchanged:'Invariato'};
  const sourceStatusTone=status=>status==='active'?'success':status==='paused'?'warning':status==='draft'?'info':'neutral';
  const sourceStatusBadge=status=>`<span class="gf-badge" data-dot data-status="${sourceStatusTone(status)}">${esc(statuses[status]||status)}</span>`;
  let sources=[],fields=[],offset=0,current=null,staged=null,verified=null,busy=false,erpRequestPending=false;
  const example={orders:[{external_id:'ORD-001',number:'ORD-001',external_customer_id:'CLI-001',recipient_name:'Esempio cliente',delivery_address:'Via Roma 1, Milano',packages:3,weight_kg:12.5,tail_lift:false}]};
  const button=(label,call)=>`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFOrderSources.${call}">${label}</button>`;
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
  function hideSecret(){const dialog=el('sourceKeyDialog');if(dialog?.open)dialog.close();const token=el('sourceToken');if(token)token.value='';const secret=el('connectorSecret');if(secret)secret.value='';}
  // La chiave appena generata si vede solo in questa finestra: chiudendola il valore viene cancellato.
  // «Ho salvato la chiave» si abilita dopo la copia, così è difficile chiudere senza averla copiata.
  function showKey(secret){
    const dialog=el('sourceKeyDialog');if(!dialog)return;
    el('sourceToken').value=secret;el('sourceTokenMessage').textContent='';el('sourceKeyDone').disabled=true;
    if(!dialog.dataset.bound){dialog.dataset.bound='1';dialog.addEventListener('close',()=>{el('sourceToken').value='';});dialog.addEventListener('cancel',event=>{if(el('sourceKeyDone').disabled)event.preventDefault();});}
    dialog.showModal();
  }
  function sourceCard(s){
    const isRemoved=s.status==='removed';
    const isApi=s.kind==='api';
    const planLocked=!isRemoved && (isApi || !!s.connector) && !integrationsEnabled();
    const count=Number(s.order_count)||0;
    const last=s.last_success?esc(new Date(s.last_success+'Z').toLocaleString('it-IT')):'nessuna';
    const type=s.connector?({email:'EMAIL',shopify:'SHOPIFY',woocommerce:'WOOCOMMERCE'}[s.connector.provider]):isApi?'API STANDARD':'FILE CSV / XLSX';
    const description=isRemoved
      ?'Questa fonte è stata rimossa. Puoi consultare lo storico degli ordini importati.'
      :planLocked?'Ricezione non disponibile nel piano attuale. Richiede Business o Pro; puoi continuare a importare file CSV/Excel.'
      :s.connector?.provider==='email'?'Inoltro email in fase di sviluppo. Configurazione e ricezione non disponibili.'
      :s.connector?(s.status==='paused'?'Ricezione in pausa.':s.connector.received?'Invii ricevuti. Controlla lo storico per gli esiti.':'In attesa del primo invio dal collegamento configurato.')
      :isApi&&s.status==='active'
        ?(s.has_credential?'Pronta a ricevere richieste autenticate. Il gestionale deve essere configurato per inviarle.':'Credenziale da generare: nessun invio autorizzato.')
        :s.status==='paused'?'Fonte in pausa. Puoi riattivarla dalle impostazioni.':'';
    const hasIssue=s.last_run?.status==='failed'||s.last_run?.status==='preview_invalid';
    const importBtn=!isRemoved&&s.kind==='file'&&['active','draft'].includes(s.status)
      ?`<button type='button' class='gf-button' data-variant='primary' data-size='sm' onclick='GFOrderImport.start(${s.id})'>Importa file</button>`:'';
    const openBtn=!isRemoved?`<button type='button' class='gf-button' data-variant='secondary' data-size='sm' onclick='GFOrderSources.open(${s.id})'>Apri</button>`:'';
    const historyBtn=`<button type='button' class='gf-button' data-variant='secondary' data-size='sm' onclick='GFOrderSources.history(${s.id},0)'>Storico <span aria-hidden='true'>›</span></button>`;
    const removeBtn=isRemoved&&manage()?`<button type='button' class='gf-button' data-variant='danger' data-size='sm' onclick='GFOrderSources.deleteFromList(${s.id})'><span aria-hidden='true'>⌫</span> Rimuovi</button>`:'';
    return `<article class='gf-card gf-stack' data-source-removed='${isRemoved}'>
      <div class='gf-stack' data-gap='sm'>
        <h3 class='gf-subtitle'>${esc(s.name)}</h3>
        <div class='gf-cluster'><span class='gf-badge' data-status='neutral'>${type}</span>${planLocked?'<span class="gf-badge" data-status="warning">Business richiesto</span>':sourceStatusBadge(s.status)}</div>
        <p><strong>${count} ${count===1?'ordine':'ordini'}</strong><span aria-hidden='true'> · </span><span class='gf-muted'>Ultima acquisizione: ${last}</span></p>
        ${description&&!isRemoved?`<p class='gf-muted'>${description}</p>`:''}
        ${hasIssue?`<p class='gf-alert' data-status='warning'>Ultima verifica o acquisizione con errori. Consulta lo storico.</p>`:''}
      </div>
      <div class='gf-cluster'>${importBtn}${openBtn}${historyBtn}${removeBtn}</div>
      ${isRemoved?`<p class='gf-muted'>${description}</p>`:''}
    </article>`;
  }
  async function refresh(){
    const data=await request('?offset='+offset);
    sources=data.items;
    fields=['external_id','number',...data.fields.filter(k=>!['external_id','number'].includes(k))];
    const canImport=can('orders.import')||manage(),canRequestSupport=can('support.write');
    el('sourceCategories').hidden=!canImport&&!manage()&&!canRequestSupport;
    const fileOption=el('sourceFileOption'),erpOption=el('sourceErpOption'),ecommerceOption=el('sourceEcommerceOption'),additionalOptions=el('sourceAdditionalOptions');
    if(fileOption)fileOption.hidden=!canImport;
    if(erpOption)erpOption.hidden=!manage()&&!canRequestSupport;
    if(ecommerceOption)ecommerceOption.hidden=!manage();
    if(additionalOptions)additionalOptions.hidden=!manage()&&!canRequestSupport;
    const createTopButton=el('ordersConnectionsNewSource');
    if(createTopButton)createTopButton.hidden=!canImport;
    const upgradeNotice=el('sourcePlanUpgradeNotice');if(upgradeNotice)upgradeNotice.hidden=integrationsEnabled();
    document.querySelectorAll('[data-plan-feature="has_order_integrations"]').forEach(button=>{button.disabled=!integrationsEnabled();button.title=integrationsEnabled()?'':'Disponibile dal piano Business';});
    const count=el('sourceCount');
    if(count)count.textContent=`${data.total} ${data.total===1?'fonte':'fonti'}`;
    el('sourceList').innerHTML=sources.length
      ?'<div class="gf-grid" data-cols="3">'+sources.map(sourceCard).join('')+'</div>'
      :'<div class="gf-empty"><p>Nessuna fonte configurata.</p></div>';
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
    if(!manage()||busy||erpRequestPending)return;hideSecret();current=staged=verified=null;el('sourceWizard').hidden=false;
    const email=kind==='email';
    if(!email && !requireIntegration()){showIntegrationUpgrade();return;}
    if(email){el('sourceWizard').innerHTML='<div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">Email · In fase di sviluppo</h2><p class="gf-muted">Stiamo studiando la ricezione automatica degli ordini via email. La configurazione non è ancora disponibile.</p></div>';return;}
    const field=(label,control,hidden)=>`<label class="gf-field"${hidden?' hidden':''}><span class="gf-field__label">${label}</span>${control}</label>`;
    el('sourceWizard').innerHTML=`<div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">${email?'Ricevi ordini via email':'Collega il negozio online'}</h2><p class="gf-muted">${email?'Ogni azienda riceve un indirizzo dedicato: imposta una regola di inoltro nella casella dove arrivano gli ordini.':'Scegli la piattaforma. Dopo il collegamento, i nuovi ordini arrivano automaticamente in GiroFacile, da verificare prima del giro.'}</p>${!owner()?'<p class="gf-alert" data-status="info">Il titolare deve configurare questo collegamento.</p>':`<form class="gf-stack" onsubmit="GFOrderSources.createConnector(event)"><div class="gf-form-grid">${field('Nome collegamento',`<input class="gf-input" id="connectorName" maxlength="160" required placeholder="${email?'Ordini via email':'Negozio online'}">`)}${field('Piattaforma',`<select class="gf-select" id="connectorProvider"><option value="${email?'email':'shopify'}">${email?'Email':'Shopify'}</option>${email?'':'<option value="woocommerce">WooCommerce</option>'}</select>`,email)}${email?'':field('Dominio del negozio','<input class="gf-input" id="connectorStore" required placeholder="negozio.myshopify.com">')+field('Chiave di firma','<input class="gf-input" id="connectorSecret" type="password" autocomplete="new-password" minlength="16" maxlength="500" required>')}</div>${email?'<p class="gf-muted">Importazione automatica da allegati CSV/Excel e messaggi con righe Numero ordine:, Destinatario:, Indirizzo:. PDF, immagini e testo libero vanno controllati manualmente e sono segnalati nello storico.</p>':'<details class="gf-panel" open><summary class="gf-panel__header">Dove trovare la chiave</summary><div class="gf-panel__body gf-stack"><p>Shopify: Impostazioni → Notifiche → Webhook, chiave di firma. WooCommerce: scegli una chiave di almeno 16 caratteri e usa la stessa nella configurazione del webhook.</p><p>Dopo il salvataggio ti mostreremo l’indirizzo da inserire nel negozio. Non viene letto lo storico degli ordini.</p></div></details>'}<div><button class="gf-button" data-variant="primary" type="submit">${email?'Crea indirizzo di ricezione':'Prepara collegamento'}</button></div><p id="connectorMessage" class="gf-muted" role="status"></p></form>`}${email?'':'<details class="gf-panel"><summary class="gf-panel__header">Uso un’altra piattaforma</summary><div class="gf-panel__body gf-stack"><p>Per un’altra piattaforma, richiedi assistenza per valutare la compatibilità con le API di GiroFacile.</p><div><button type="button" class="gf-button" data-variant="secondary" onclick="GFOrderSources.requestErpConnection()">Richiedi assistenza</button></div></div></details>'}</div>`;
    el('sourceWizard').scrollIntoView({block:'start'});
  }
  function createConnector(event){event.preventDefault();if(!requireIntegration())return;return task(async()=>{
    const message=el('connectorMessage'),secret=el('connectorSecret');
    try{
      const created=await request('/connectors',post({name:el('connectorName').value,provider:el('connectorProvider').value,store:el('connectorStore')?.value||'',secret:secret?.value||''}));
      if(secret)secret.value='';await refresh();current=created;el('sourceWizard').hidden=true;showTab('ordine-fonte');detailPage();window.scrollTo({top:0,behavior:'auto'});
    }catch(error){message.textContent=error.message;}
  });}
  function connectorDetail(s){
    const c=s.connector,email=c.provider==='email';
    if(email){el('orderSourceDetail').innerHTML='<section class="gf-panel"><div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">Inoltro email in fase di sviluppo</h2><p class="gf-muted">Configurazione e ricezione automatica non ancora disponibili.</p></div></section>';return;}
    el('orderSourceDetail').innerHTML=`<section class="gf-panel"><div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">${email?'Inoltra qui gli ordini': 'Completa il collegamento nel negozio'}</h2><label class="gf-field"><span class="gf-field__label">${email?'Indirizzo dedicato all’azienda':'Indirizzo di ricezione'}</span><input class="gf-input" readonly value="${esc(email?c.address:c.webhook_url)}" onclick="this.select()"></label>${email?'<ol><li>Nella casella aziendale crea una regola che inoltri solo le email degli ordini a questo indirizzo.</li><li>Invia un ordine con allegato CSV/Excel oppure con righe Numero ordine:, Destinatario:, Indirizzo:.</li><li>Apri Ordini per controllare la consegna.</li></ol><p>PDF e messaggi non strutturati sono segnalati nello storico: consulta l’email originale e inserisci l’ordine manualmente. L’indirizzo dedicato va condiviso solo con chi deve inviare ordini.</p>':`<ol><li>${c.provider==='shopify'?'Shopify: Impostazioni → Notifiche → Webhook. Crea un webhook Ordine creato, formato JSON.':'WooCommerce: Impostazioni → Avanzate → Webhook. Crea un webhook Ordine creato, stato Attivo.'}</li><li>Incolla l’indirizzo di ricezione qui sopra. Usa la stessa chiave di firma inserita in GiroFacile.</li><li>Crea un ordine di prova con nome e indirizzo di spedizione completi.</li></ol><p class="gf-muted">Si ricevono i nuovi ordini. Modifiche, annullamenti e ordini precedenti devono essere gestiti separatamente.</p>`}<p class="gf-alert" data-status="${c.received?'success':'info'}" role="status">${c.received?'Ricezione verificata: almeno un messaggio autenticato è arrivato. Controlla gli esiti nello storico.':'In attesa del primo invio reale. La creazione del collegamento non verifica l’inoltro.'}</p>${s.last_run?.summary?.error?`<p class="gf-alert" data-status="danger">${esc(s.last_run.summary.error)}</p>`:''}</div></section><section class="gf-panel"><div class="gf-panel__body gf-stack">${GFOrderImport.fieldChoices(s.excluded_fields||[],'api',!manage())}${manage()?'<div><button type="button" class="gf-button" data-variant="primary" onclick="GFOrderSources.saveFields()">Salva dati da importare</button></div>':''}<p id="sourceFieldsMessage" class="gf-muted" role="status"></p></div></section>`;
  }
  function invalidate(){verified=null;el('sourceConfirm')?.replaceChildren();}
  // I nuovi collegamenti gestionali partono da una richiesta di assistenza.
  // Le impostazioni delle fonti già esistenti restano accessibili dai relativi dettagli.
  function createForm(kind){
    if(!kind||kind==='file'){GFOrderImport.start();return;}
    return requestErpConnection();
  }
  function create(event){event.preventDefault();return requestErpConnection();}
  function closeErpRequest(){
    if(erpRequestPending)return;
    el('sourceWizard').hidden=true;
    el('sourceErpOption')?.querySelector('button')?.focus();
  }
  function requestErpConnection(){
    if(busy||erpRequestPending)return;
    hideSecret();current=staged=verified=null;
    const wizard=el('sourceWizard');wizard.hidden=false;
    if(!can('support.write')){
      wizard.innerHTML='<div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">Richiedi il collegamento del gestionale</h2><p class="gf-alert" data-status="info">Per inviare la richiesta serve il permesso di scrivere all’assistenza. Chiedi al titolare dell’azienda di inviarla o di abilitarti.</p><div><button type="button" class="gf-button" data-variant="secondary" onclick="GFOrderSources.closeErpRequest()">Chiudi</button></div></div>';
      wizard.scrollIntoView({block:'start'});return;
    }
    wizard.innerHTML=`<div class="gf-panel__body gf-stack">
      <div><p class="gf-kicker">Collegamento con assistenza</p><h2 class="gf-panel__title" id="erpRequestTitle">Quale gestionale vuoi collegare?</h2></div>
      <p class="gf-muted">Descrivi il software e gli ordini da ricevere. Il supporto ti ricontatterà per verificare la compatibilità e aiutarti nella configurazione. Nel frattempo puoi importare gli ordini da CSV o Excel.</p>
      <form id="erpRequestForm" class="gf-stack" aria-labelledby="erpRequestTitle" onsubmit="GFOrderSources.submitErpRequest(event)">
        <fieldset id="erpRequestFields" class="gf-fieldset gf-stack">
          <div class="gf-form-grid">
            <label class="gf-field" for="erpSoftware"><span class="gf-field__label">Nome del gestionale *</span><input class="gf-input" id="erpSoftware" name="software" required maxlength="160" placeholder="Es. nome del software aziendale"></label>
            <label class="gf-field" for="erpVersion"><span class="gf-field__label">Versione o fornitore (facoltativo)</span><input class="gf-input" id="erpVersion" name="version" maxlength="160" placeholder="Se lo conosci"></label>
            <label class="gf-field" for="erpPhone"><span class="gf-field__label">Telefono per ricontattarti (facoltativo)</span><input class="gf-input" id="erpPhone" name="phone" type="tel" autocomplete="tel" maxlength="100"></label>
          </div>
          <label class="gf-field" for="erpMessage"><span class="gf-field__label">Cosa vuoi collegare? *</span><textarea class="gf-textarea" id="erpMessage" name="message" rows="4" required maxlength="3000" aria-describedby="erpMessageHint" placeholder="Come ricevi gli ordini oggi? Quali dati vorresti trasferire in GiroFacile?"></textarea><span class="gf-field__hint" id="erpMessageHint">Non inserire password, chiavi API o dati dei tuoi clienti.</span></label>
          <p class="gf-muted">Useremo l’indirizzo email del profilo azienda per risponderti.</p>
          <label class="gf-check"><input type="checkbox" id="erpRequestNotify" checked>Avvisami via email quando la richiesta viene chiusa</label>
          <div class="gf-cluster"><button id="erpRequestSubmit" class="gf-button" data-variant="primary" type="submit">Invia richiesta di assistenza</button><button type="button" class="gf-button" data-variant="ghost" onclick="GFOrderSources.closeErpRequest()">Annulla</button></div>
        </fieldset>
        <p id="erpRequestStatus" class="gf-field__error" role="alert" tabindex="-1"></p>
      </form>
    </div>`;
    wizard.scrollIntoView({block:'start'});el('erpSoftware').focus({preventScroll:true});
  }
  async function submitErpRequest(event){
    event.preventDefault();
    if(erpRequestPending)return;
    const status=el('erpRequestStatus');
    if(!can('support.write')){status.textContent='Non hai il permesso di inviare richieste di assistenza. Chiedi al titolare dell’azienda.';status.focus();return;}
    const payload={software:el('erpSoftware').value.trim(),version:el('erpVersion').value.trim(),message:el('erpMessage').value.trim(),phone:el('erpPhone').value.trim(),notify_on_resolution:el('erpRequestNotify').checked};
    if(!payload.software||!payload.message){status.textContent='Inserisci il nome del gestionale e una descrizione della richiesta.';status.focus();return;}
    erpRequestPending=true;status.textContent='';
    const form=el('erpRequestForm'),fieldset=el('erpRequestFields'),submit=el('erpRequestSubmit');
    fieldset.disabled=true;form.setAttribute('aria-busy','true');submit.textContent='Invio in corso…';
    try{
      const response=await fetch('/api/support/erp-connection',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const data=await response.json();
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Controlla i campi e riprova.');
      const ticket=data.ticket;
      if(!ticket?.id)throw new Error('Non è stato possibile confermare la richiesta. Controlla le tue richieste di assistenza prima di riprovare.');
      el('sourceWizard').innerHTML=`<div class="gf-panel__body gf-stack"><h2 class="gf-panel__title" id="erpRequestSuccess" tabindex="-1">Richiesta #${esc(ticket.id)} inviata</h2><p>Il supporto ti ricontatterà all’indirizzo <strong>${esc(ticket.email)}</strong> per valutare il collegamento del gestionale.</p><p class="gf-muted">La richiesta non attiva automaticamente il collegamento. Puoi già usare un file CSV o Excel per importare i tuoi ordini.</p><div class="gf-cluster"><button type="button" class="gf-button" data-variant="primary" onclick="GFOrderImport.start()">Carica un file</button>${can('support.read')?'<button type="button" class="gf-button" data-variant="secondary" onclick="openSupportPanelV49()">Le mie richieste</button>':''}<button type="button" class="gf-button" data-variant="ghost" onclick="GFOrderSources.closeErpRequest()">Chiudi</button></div></div>`;
      el('erpRequestSuccess').focus();
    }catch(error){status.textContent=error.message||'Invio non riuscito. Riprova tra poco.';status.focus();}
    finally{erpRequestPending=false;if(form.isConnected){fieldset.disabled=false;form.setAttribute('aria-busy','false');submit.textContent='Invia richiesta di assistenza';}}
  }
  function sourceSubtitle(s){if(s.connector)return 'Ricezione automatica degli ordini aziendali';return s.kind==='api'?'Genera la chiave API e verifica il collegamento per attivare la fonte.':'Gestione fonte file e validazione degli ordini importati.';}
  function sourceTopActions(s,mobile=false){
    if(!manage())return '';
    const toggle=s.status==='active'
      ?'<button type="button" class="gf-button" data-variant="secondary" onclick="GFOrderSources.action(\'pause\')">Ⅱ&nbsp; Metti in pausa</button>'
      :s.status==='paused' && (s.kind==='file'||integrationsEnabled())
        ?'<button type="button" class="gf-button" data-variant="primary" onclick="GFOrderSources.action(\'resume\')">Riattiva fonte</button>'
        :'';
    const remove='<button type="button" class="gf-button" data-variant="danger" onclick="GFOrderSources.deleteSource()">⌫&nbsp; Elimina fonte</button>';
    return `<div class="gf-cluster"${mobile?' data-source-mobile-actions':''}>${toggle}${remove}</div>`;
  }
  function syncSourceTopbar(){
    if(!current)return;
    const title=el('workspacePageTitle'),subtitle=el('workspacePageSubtitle'),badge=el('workspacePageBadge'),actions=el('orderSourceTopbarActionsHost');
    if(title)title.textContent=current.name;
    if(subtitle)subtitle.textContent=sourceSubtitle(current);
    if(badge){badge.hidden=false;badge.textContent=statuses[current.status]||current.status;badge.className='gf-badge';badge.dataset.status=sourceStatusTone(current.status);}
    if(actions)actions.innerHTML=sourceTopActions(current);
  }

  function apiConnectionSample(){
    const base=example.orders[0], row={...base};
    for(const [field,external] of Object.entries(current?.mapping||{})){
      if(field in base && external)row[external]=base[field];
    }
    return {orders:[row]};
  }
  // Fonte API (variante B, approvata il 12/11/2026): impostazioni a righe come nella pagina Impostazioni;
  // la scelta dei dati si apre nella finestra sourceFieldsDialog, la nuova chiave nella finestra sourceKeyDialog.
  function apiFieldRows(excluded,disabled){
    return GFOrderImport.fieldOptions().map(({key,label},i)=>`<div class="gf-setting"><div class="gf-setting__copy"><strong id="sourceField${i}">${esc(label)}</strong></div><div class="gf-setting__control"><label class="gf-switch"><input type="checkbox" role="switch" data-choice="api" value="${key}" aria-labelledby="sourceField${i}" ${excluded.includes(key)?'':'checked'} ${disabled?'disabled':''}></label></div></div>`).join('');
  }
  function apiFieldsSummary(excluded){
    const options=GFOrderImport.fieldOptions(),on=options.filter(o=>!excluded.includes(o.key)).length;
    return `Destinatario e indirizzo sempre, più ${on} dati facoltativi su ${options.length}.`;
  }
  function openFields(){
    const dialog=el('sourceFieldsDialog');if(!dialog||!current)return;
    const canManage=manage();
    el('sourceFieldsList').innerHTML=apiFieldRows(current.excluded_fields||[],!canManage);
    el('sourceFieldsDialogMessage').textContent=canManage?'':'Chiedi al responsabile di modificare queste impostazioni.';
    el('sourceFieldsSave').hidden=!canManage;
    dialog.showModal();
  }
  function apiDetailPage(s){
    const ownerUser=owner(), canManage=manage();
    const keyButton=canManage&&ownerUser
      ?`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFOrderSources.action('rotate')">${s.has_credential?'Genera nuova chiave':'Genera chiave API'}</button>`
      :'';
    const revokeButton=canManage&&ownerUser&&s.has_credential&&s.status==='active'
      ?'<button type="button" class="gf-button" data-variant="ghost" data-size="sm" onclick="GFOrderSources.action(\'revoke\')">Disattiva chiave</button>'
      :'';
    const keyBadge=s.has_credential?'<span class="gf-badge" data-status="success">Attiva</span>':'<span class="gf-badge" data-status="warning">Da generare</span>';
    const keyCopy=s.has_credential
      ?'Per sicurezza la chiave esistente non può essere visualizzata: se l’hai persa, generane una nuova.'
      :'Genera la chiave da inserire nel tuo gestionale: la vedrai una sola volta.';
    const waiting=!s.last_success;
    const receptionTitle=waiting?'In attesa del primo ordine':'Ricezione attiva';
    const receptionCopy=waiting
      ?(s.status==='active'?'La fonte è pronta: compariranno qui i dati non appena arriverà il primo ordine valido.':'La fonte si attiverà dopo la verifica del collegamento.')
      :`Ultima acquisizione riuscita: ${esc(new Date(s.last_success+'Z').toLocaleString('it-IT'))}.`;
    el('orderSourceDetail').innerHTML=`
      <div class="gf-grid" data-cols="main-side" data-source-api-settings>
        <section class="gf-panel">
          <header class="gf-panel__header"><h2 class="gf-panel__title">Collegamento con il gestionale</h2></header>
          <div class="gf-panel__body">
            <div class="gf-setting"><div class="gf-setting__copy"><strong>Dati da importare</strong><p class="gf-muted">${apiFieldsSummary(s.excluded_fields||[])}</p><p id="sourceFieldsMessage" class="gf-muted" role="status"></p></div>
              <div class="gf-setting__control"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFOrderSources.openFields()">${canManage?'Scegli dati':'Vedi dati'}</button></div></div>
            <div class="gf-setting"><div class="gf-setting__copy"><strong>Chiave API ${keyBadge}</strong><p class="gf-muted">${keyCopy}</p></div>
              <div class="gf-setting__control gf-cluster">${revokeButton}${keyButton}</div></div>
            <div class="gf-setting"><div class="gf-setting__copy"><strong>Verifica con un ordine di esempio</strong><p class="gf-muted">Inviamo un ordine di prova per controllare il formato e attivare la fonte, senza scrivere codice.</p><div id="sourceConnectionResult"></div></div>
              <div class="gf-setting__control"><button type="button" class="gf-button" data-variant="primary" data-size="sm" onclick="GFOrderSources.testConnection()">Esegui test</button></div></div>
            <div class="gf-setting"><div class="gf-setting__copy"><strong>Istruzioni per il tuo gestionale</strong><p class="gf-muted">Indirizzo, formato dell’ordine ed esempio pronto da girare a chi gestisce il software.</p></div>
              <div class="gf-setting__control"><button type="button" class="gf-button" data-variant="ghost" data-size="sm" onclick="GFOrderSources.downloadInstructions()" aria-label="Scarica istruzioni per il tuo gestionale">Scarica</button></div></div>
          </div>
        </section>

        <aside class="gf-panel">
          <header class="gf-panel__header"><h2 class="gf-panel__title">Stato ricezione</h2></header>
          <div class="gf-panel__body gf-stack">
            <span class="gf-badge" data-dot data-status="${waiting?'warning':'success'}">${receptionTitle}</span>
            <p class="gf-muted">${receptionCopy}</p>
            <dl class="gf-details"><div class="gf-details__item"><dt>Ordini acquisiti</dt><dd><strong>${Number(s.order_count||0)}</strong></dd></div>
            <div class="gf-details__item"><dt>Chiave API</dt><dd>${s.has_credential?'Attiva':'Da generare'}</dd></div></dl>
          </div>
        </aside>
      </div>`;
  }
  function detailPage(){
    hideSecret();const s=current;if(!s)return;
    syncSourceTopbar();
    const mobile=el('orderSourceMobileHead');
    // Titolo, stato, indietro e azioni sono nell'intestazione condivisa, visibile a ogni larghezza.
    if(mobile)mobile.replaceChildren();
    if((s.connector || s.kind==='api') && !integrationsEnabled()){el('orderSourceDetail').innerHTML=upgradeMarkup();return;}
    if(s.connector){connectorDetail(s);return;}
    if(s.kind==='api'){apiDetailPage(s);return;}
    const sample=`<div class="gf-upload"><div class="gf-upload__copy"><label class="gf-button gf-upload__button" data-variant="secondary">File CSV o XLSX<input id="sourceFile" type="file" accept=".csv,.xlsx" aria-label="File CSV o XLSX"></label><p class="gf-field__hint">Un solo foglio, senza formule. Mantieni i codici con zeri iniziali come testo.</p></div></div>`;
    const sampleFooter=s.status==='paused'
      ?'<div class="gf-alert" data-status="warning">La fonte è in pausa. Riattivala per caricare e verificare nuovi campioni.</div>'
      :'<div class="gf-cluster" data-justify="between"><span class="gf-muted">Il campione verifica la compatibilità: non importa ordini.</span><button type="button" class="gf-button" data-variant="primary" onclick="GFOrderSources.upload()">Carica campione</button></div>';
    const fileBody=`<div class="gf-panel__body gf-stack"><p class="gf-kicker">Importazione file</p><p>Carica un campione CSV o XLSX, associa le colonne e verifica l’anteprima. Gli ordini vengono inseriti solo dopo la conferma finale.</p><p class="gf-kicker">Stato fonte</p><div class="gf-alert" data-status="${s.status==='active'?'success':'warning'}"><div class="gf-alert__body"><strong class="gf-alert__title">${esc(statuses[s.status]||s.status)}</strong><p>${s.status==='active'?'Pronta per nuove importazioni.':'Riattiva la fonte per acquisire nuovi file.'}</p></div></div></div>`;
    el('orderSourceDetail').innerHTML=`<div class="gf-stack" data-gap="lg"><div class="gf-grid" data-cols="main-side"><section class="gf-panel"><header class="gf-panel__header"><div><h2 class="gf-panel__title">Carica un campione</h2><p class="gf-muted">Massimo 2 MB e 1000 ordini. L’anteprima è disponibile per 24 ore.</p></div></header><div class="gf-panel__body gf-stack">${sample}${sampleFooter}</div></section><aside class="gf-panel"><header class="gf-panel__header"><div><h2 class="gf-panel__title">Acquisizione file</h2><p class="gf-muted">Controlla lo stato e prepara una nuova importazione.</p></div></header>${fileBody}</aside></div><div class="gf-stack"><div id="sourceMapping"></div><div id="sourceReport"></div><div id="sourceConfirm" class="gf-cluster"></div></div></div>`;
  }
  function testConnection(){
    if(busy||!current||current.kind!=='api'||!requireIntegration())return;
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
      if(result)result.innerHTML='<div class="gf-alert" data-status="success"><div class="gf-alert__body"><strong class="gf-alert__title">✓ Collegamento verificato</strong><p>Il formato è valido e la fonte è pronta a ricevere ordini dal gestionale.</p></div></div>';
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
    el('sourceWizard').innerHTML=`<div class="gf-panel__body gf-stack"><h2 class="gf-panel__title">${esc(s.name)} · ${statuses[s.status]}</h2><div class="gf-cluster">${manage()&&s.status==='active'?button('Metti in pausa',"action('pause')"):''}${manage()&&s.status==='paused'?button('Riattiva',"action('resume')"):''}${manage()&&s.status!=='removed'?button('Rimuovi fonte',"action('remove')"):''}</div>${s.status==='paused'||s.status==='removed'?'<p class="gf-alert" data-status="warning">La fonte non riceve ordini. Gli ordini acquisiti restano disponibili.</p>':`<h3 class="gf-subtitle">2. Carica un campione</h3><p class="gf-muted">Massimo 2 MB e 1000 ordini. L'anteprima è disponibile per 24 ore.</p>${s.kind==='file'?'<label class="gf-field"><span class="gf-field__label">File CSV o XLSX</span><input id="sourceFile" type="file" accept=".csv,.xlsx"></label><p class="gf-field__hint">Un solo foglio, senza formule. Mantieni i codici con zeri iniziali come testo.</p>':`<label class="gf-field"><span class="gf-field__label">Campione JSON</span><textarea class="gf-textarea" id="sourceSample" rows="10" spellcheck="false">${esc(JSON.stringify(example,null,2))}</textarea></label><p class="gf-field__hint">Il campione verifica i dati ma non importa ordini.</p>`}<div>${button('Carica campione','upload()')}</div><div id="sourceMapping"></div><div id="sourceReport"></div><div id="sourceConfirm" class="gf-cluster"></div>`}${s.kind==='api'&&s.status==='active'?`<h3 class="gf-subtitle">Invio dal gestionale</h3><p>Endpoint: <code class="gf-code">POST /api/order-ingestion</code>. Autenticazione Bearer. Aggiungi un batch_id univoco e invia ordini completi, non modifiche parziali.</p><p class="gf-muted">${s.has_credential?'Credenziale presente.':'Credenziale mancante: generala per autorizzare gli invii.'}</p>${manage()&&owner()?`<div class="gf-cluster">${button(s.has_credential?'Ruota credenziale':'Genera credenziale',"action('rotate')")}${s.has_credential?button('Revoca credenziale',"action('revoke')"):''}</div>`:'<p class="gf-muted">Le credenziali sono gestite dal titolare.</p>'}`:''}</div>`;
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
    el('sourceMapping').innerHTML=`<section class="gf-panel"><header class="gf-panel__header"><div><h3 class="gf-panel__title">3. Associa le colonne</h3><p class="gf-muted">${staged.total} ordini. Prime ${staged.sample.length} righe del campione:</p></div></header><div class="gf-table-wrap"><table class="gf-table"><thead><tr>${staged.headers.map(h=>`<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${staged.sample.map(r=>'<tr>'+staged.headers.map(h=>`<td>${esc(typeof r[h]==='object'?JSON.stringify(r[h]):String(r[h]??''))}</td>`).join('')+'</tr>').join('')}</tbody></table></div><div class="gf-panel__body gf-stack"><p class="gf-muted">* Identificativo esterno e numero ordine sono obbligatori. L'identificativo deve essere stabile e univoco per questa fonte: i successivi invii aggiornano lo stesso ordine.</p><div class="gf-form-grid">${fields.map(k=>`<label class="gf-field"><span class="gf-field__label">${names[k]||esc(k)}</span><select class="gf-select" onchange="GFOrderSources.invalidate()" data-source-field="${esc(k)}" ${manage()?'':'disabled'}><option value="">Non associato</option>${staged.headers.map(h=>`<option value="${esc(h)}" ${selected[k]===h?'selected':''}>${esc(h)}</option>`).join('')}</select></label>`).join('')}</div><p class="gf-muted">${manage()?'Modificare le associazioni sospende gli invii fino alla nuova verifica e attivazione.':'Le associazioni sono gestite da chi configura le integrazioni.'}</p><div>${button('Verifica anteprima','preview()')}</div></div></section>`;
  }
  function confirmation(){
    const ready=verified?.status==='preview_ready';
    el('sourceConfirm').innerHTML=ready?(current.status!=='active'?(manage()?button('Attiva fonte verificata',"action('activate')"):'<p class="gf-muted">Il responsabile deve attivare la fonte verificata.</p>'):current.kind==='file'?(can('orders.import')?'<button type="button" class="gf-button" data-variant="primary" onclick="GFOrderSources.commit()">Conferma importazione</button>':'<p class="gf-muted">Serve il permesso di importazione per confermare.</p>'):'<p class="gf-alert" data-status="success">Campione verificato. Gli ordini saranno acquisiti solo quando il gestionale li invierà alle API.</p>'):'';
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
    const r=data.report;el(target).innerHTML=`<section class="gf-panel"><div class="gf-panel__body gf-stack"><h3 class="gf-subtitle">${statuses[data.status]||esc(data.status)}</h3>${r.email_subject?`<p>Email: ${esc(r.email_subject)}</p>`:''}${r.provider_event?`<p>Riferimento invio: ${esc(r.provider_event)}</p>`:''}<p>Totale: ${r.total??0} · Nuovi: ${r.new??0} · Aggiornamenti: ${r.updated??0} · Invariati: ${r.unchanged??0} · Errori: ${r.invalid??0}</p>${r.error?`<p class="gf-alert" data-status="danger">${esc(r.error)}</p>`:''}<p class="gf-muted">${data.status==='completed'?'Acquisizione conclusa. Gli ordini nuovi o aggiornati sono da verificare prima della pianificazione.':'Questa verifica non inserisce ordini. Se sono presenti errori nessun ordine del lotto viene acquisito.'}</p><ol start="${(data.offset||0)+1}">${data.rows.map(row=>`<li>${esc(row.external_id||'Riga '+row.row)}: ${row.error?esc(row.error):actions[row.action]||''}${row.customer_match&&!['certain','linked'].includes(row.customer_match)?' · Cliente da verificare':''}${row.warnings?.length?' · '+esc(row.warnings.join('; ')):''}</li>`).join('')}</ol><div class="gf-cluster">${data.offset?button('Righe precedenti',`report(${sid},${data.id},${data.offset-100},'${target}')`):''}${data.has_more?button('Altre righe',`report(${sid},${data.id},${data.offset+100},'${target}')`):''}</div></div></section>`;
  }
  function commit(){return task(async()=>{verified=await request(`/${current.id}/runs/${staged.run_id}/commit`,post({confirm:true}));renderReport(verified,'sourceReport',current.id);confirmation();await refresh();});}
  function action(action){
    if(busy)return;
    if(current?.kind==='api' && !['pause','remove','revoke'].includes(action) && !requireIntegration())return;
    const warnings={remove:'Rimuovere questa fonte? Gli ordini restano disponibili; la fonte non sarà riattivabile.',rotate:current?.has_credential?'Generare una NUOVA chiave API? La precedente cesserà immediatamente di funzionare. Il gestionale non potrà più inviare ordini finché non gli verrà comunicata la nuova chiave. Confermi?':'Generare la tua prima chiave API? Copiala subito e conservala. Gli ordini potranno essere ricevuti solo dopo aver verificato e attivato la fonte.',revoke:'Disattivare la chiave e sospendere gli invii? Gli ordini già acquisiti resteranno disponibili. Per riprendere occorrerà riattivare la fonte e generare una nuova chiave.',pause:'Sospendere gli invii da questa fonte?'};
    if(warnings[action]&&!confirm(warnings[action]))return;
    const detailOpen=!el('tab-ordine-fonte').classList.contains('hidden');
    return task(async()=>{
      const result=await request('/'+current.id+'/action',post({version:current.version,action,...(action==='activate'?{run_id:staged.run_id}:{})}));
      const secret=result.credential;delete result.credential;current=result;
      if(detailOpen){staged=verified=null;detailPage();}
      else if(action==='activate'){editor();if(staged){mapping();renderReport(verified,'sourceReport',current.id);confirmation();}}
      else{staged=verified=null;editor();}
      if(secret)showKey(secret);
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
    const done=el('sourceKeyDone');if(done)done.disabled=false;
  }

  function saveFields(){if(!requireIntegration())return;return task(async()=>{
    try{
      current=await request('/'+current.id+'/fields',{method:'PUT',body:JSON.stringify({version:current.version,excluded_fields:GFOrderImport.readChoices('api')})});
      el('sourceFieldsDialog')?.close();detailPage();el('sourceFieldsMessage').textContent='Scelte salvate per i prossimi ordini.';
    }catch(error){(el('sourceFieldsDialog')?.open?el('sourceFieldsDialogMessage'):el('sourceFieldsMessage')).textContent=error.message;}
  });}
  function history(id,next=0){return task(async()=>{
    const data=await request(`/${id}/runs?offset=${next}`);el('sourceHistory').hidden=false;
    el('sourceHistory').innerHTML='<header class="gf-panel__header"><h2 class="gf-panel__title">Storico della fonte</h2></header><div class="gf-panel__body gf-stack">'+data.items.map(r=>`<p class="gf-cluster"><span>${esc(new Date(r.created_at+'Z').toLocaleString('it-IT'))} · ${statuses[r.status]||esc(r.status)}</span> ${button('Report #'+r.id,`report(${id},${r.id},0,'sourceHistoryReport')`)}</p>`).join('')+`<div class="gf-cluster">${next?button('Precedenti',`history(${id},${next-20})`):''}${next+20<data.total?button('Successivi',`history(${id},${next+20})`):''}</div><div id="sourceHistoryReport"></div></div>`;el('sourceHistory').scrollIntoView({block:'start'});
  });}
  function report(sid,rid,next,target){return task(async()=>renderReport(await request(`/${sid}/runs/${rid}?offset=${next}`),target,sid));}
  window.GFOrderSources={requestErpConnection,submitErpRequest,closeErpRequest,createConnector,deleteFromList,saveFields,openFields,load,hideSecret,downloadInstructions,copyToken,unavailable,invalidate,createForm,create,open,back,deleteSource,testConnection,upload,preview,commit,action,history,report,page(delta){offset=Math.max(0,offset+delta*50);load();}};
})();
