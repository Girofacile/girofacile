/* Company collaborators. Server checks are authoritative; this module adapts UI. */
(function(){
  'use strict';
  const tabs = {dashboard:'dashboard.read',giro:'routes.plan','route-preview':'routes.plan',
    'dashboard-scheduled':'routes.read','dashboard-in-progress':'routes.read',
    'dashboard-completed':'routes.read',storico:'routes.read',clienti:'customers.read',
    depositi:'deposits.read',mezzi:'vehicles.read',autisti:'drivers.read',agenti:'agents.read',
    report:'reports.read',company:'company.read','chat-autisti':'chat.read',settings:'settings.update',
    'collaborator-home':'session'};
  const isCollaborator = () => !!currentSessionUser?.is_collaborator;
  const can = key => !isCollaborator() || key === 'session' || (currentSessionUser.permissions || []).includes(key);
  const allowedTab = name => !isCollaborator() || (!!tabs[name] && can(tabs[name]));
  let observer;
  const companyDisabled=new WeakMap();
  function apply(){
    const collaborator=isCollaborator();
    document.body.classList.toggle('company-collaborator-session',collaborator);
    // Read-only company forms must not create an unsavable dirty draft.
    document.querySelectorAll('#tab-company .company-card-v29 input,#tab-company .company-card-v29 select,#tab-company .company-card-v29 textarea').forEach(el=>{
      if(collaborator && !can('company.update')){
        if(!companyDisabled.has(el)) companyDisabled.set(el,el.disabled);
        el.disabled=true;
      }else if(companyDisabled.has(el)){
        el.disabled=companyDisabled.get(el); companyDisabled.delete(el);
      }
      if(el.type==='file') el.closest('.file-btn')?.setAttribute('aria-disabled',String(el.disabled));
    });
    const email=document.getElementById('profileEmail'); if(email) email.readOnly=collaborator;
    if(!collaborator){
      document.querySelectorAll('.collaborator-denied').forEach(el=>el.classList.remove('collaborator-denied'));
      return;
    }
    const denied=new Set();
    document.querySelectorAll('[data-tab],[data-mobile-tab]').forEach(el=>{
      const name=el.dataset.tab || el.dataset.mobileTab;
      if(!allowedTab(name)) denied.add(el);
    });
    const controls = {
      'routes.plan':'.topbar-new-route,.gf-mobile-bottom-nav-v62 .main',
      'notifications.read':'#notificationBellBtn,.gf-mobile-top-actions-v62 [aria-label="Notifiche"]',
      'customers.create':'#newCustomerBtn,#customerImportBtn',
      'deposits.create':'#newDepositBtn', 'vehicles.create':'.fleet-create',
      'drivers.create':'#newDriverBtn', 'company.update':'#companySaveChangesBtn,#companyDiscardChangesBtn',
    };
    for(const [key,selector] of Object.entries(controls)) if(!can(key)) document.querySelectorAll(selector).forEach(el=>denied.add(el));
    const actions = [
      [/openNewCustomer|openCustomerImport|importCustomers/,'customers.create'],
      [/editCustomer|saveCustomer|verifyCustomer|verifyPending/,'customers.update'],
      [/deleteCustomer/,'customers.delete'], [/openNewDeposit|newDeposit/,'deposits.create'],
      [/editDeposit|saveDeposit/,'deposits.update'], [/deleteDeposit/,'deposits.delete'],
      [/openNewVehicle|createFleetVehicle/,'vehicles.create'], [/editVehicle|saveVehicle/,'vehicles.update'], [/deleteVehicle/,'vehicles.delete'],
      [/openNewDriver/,'drivers.create'], [/editDriver|saveDriver|inviteDriver/,'drivers.update'], [/deleteDriver/,'drivers.delete'],
      [/openNewAgent/,'agents.create'], [/editAgent|saveAgent|inviteAgent/,'agents.update'], [/deleteAgent/,'agents.delete'],
      [/programRoute|programCurrentRoute|programDashboard|saveRoute|openProgrammedRouteForEdit/,'routes.program'],
      [/cancelDashboardRoute|completeDashboardRoute/,'routes.manage'],
      [/generateOperator|generate.*Token|TrackingLink|openCustomerTracking/,'routes.tracking'],
      [/send.*Chat|sendDriverMessage/,'chat.write'],
      [/openSupportPanel|submitSupportTicketV60|generateSupportTicketTextAIv67/,'support.write'],
    ];
    document.querySelectorAll('[onclick]').forEach(el=>{
      const code=el.getAttribute('onclick') || '';
      const customerModal=code.match(/openCustomerModal\(([^)]*)\)/);
      if(customerModal && !can(customerModal[1].trim() ? 'customers.update' : 'customers.create')) denied.add(el);
      if(/openDepositModal\(\)/.test(code) && !can('deposits.create')) denied.add(el);
      const nav=code.match(/(?:showTab|mobileGoTabV62)\(['"]([^'"]+)/);
      if(nav && !allowedTab(nav[1])) denied.add(el);
      // Form submit buttons remain usable for create-only accounts. API differentiates methods.
      for(const [pattern,key] of actions){
        if(pattern.test(code) && !can(key) && !(/^save/.test(code) && can(key.replace('.update','.create')))) denied.add(el);
      }
    });
    document.querySelectorAll('.company-owner-only,#btnPlanActive,.btn-billing-v63,#showOnboardingBtn,.onboarding-card-v29').forEach(el=>denied.add(el));
    const plan=document.querySelector('#profileOverlay .profile-plan-section');
    if(plan) denied.add(plan);
    // Recompute visibility, including newly granted actions and owner login switches.
    document.querySelectorAll('.collaborator-denied').forEach(el=>el.classList.toggle('collaborator-denied',denied.has(el)));
    for(const el of denied) el.classList.add('collaborator-denied');
    const role=document.getElementById('topProfileRole'); if(role && role.textContent!=='Collaboratore') role.textContent='Collaboratore';
  }
  function startObserver(){
    if(observer) return;
    let queued=false;
    observer=new MutationObserver(()=>{
      if(queued) return; queued=true;
      requestAnimationFrame(()=>{queued=false;observer.disconnect();apply();observer.observe(document.getElementById('app'),{childList:true,subtree:true});});
    });
    observer.observe(document.getElementById('app'),{childList:true,subtree:true});
  }
  async function initialize(){
    document.body.classList.add('company-collaborator-session');
    // Do not reuse the owner's saved photo/name after a role switch in this browser.
    for(const key of ['girofacile_profile_photo','girofacile_profile_name','girofacile_profile_role']) localStorage.removeItem(key);
    localStorage.setItem('girofacile_account_name',currentSessionUser.username || 'Collaboratore');
    localStorage.setItem('girofacile_profile_email',currentSessionUser.email || '');
    await loadSettingsV41(); await loadUniversalFeaturesV89(); loadProfilePanel();
    const date=document.getElementById('routeDate');if(date){date.min=todayIso();date.value=date.value || todayIso();}
    initAddressAutocomplete(); initResourceAvailabilityControls(); initRoutePlanningGateV68();
    for(const [permission,loader] of [
      ['deposits.read',loadDeposits],['vehicles.read',loadVehicles],['drivers.read',loadDrivers],
      ['agents.read',()=>agentsFeatureEnabled()?loadAgents():Promise.resolve()],['customers.read',loadCustomers],
      ['routes.plan',loadCustomerPicker],['routes.read',loadDashboardRoutes]
    ]) if(can(permission)) await loader();
    if(notificationsPollV30) clearInterval(notificationsPollV30);
    if(can('notifications.read')){
      await loadNotificationsV30(false);
      notificationsPollV30=setInterval(()=>loadNotificationsV30(false),60000);
    }
    apply(); startObserver();
    const preferred=['dashboard','giro','clienti','depositi','mezzi','autisti','agenti','storico','report','chat-autisti','company','settings'];
    showTab(preferred.find(name=>allowedTab(name) && (name!=='agenti' || agentsFeatureEnabled())) || 'collaborator-home');
  }
  function rewrite(path){
    if(!isCollaborator()) return path;
    if(path==='/api/account-profile') return '/api/collaborator/account';
    if(path==='/api/account-password/change') return '/api/collaborator/password';
    return path;
  }
  window.GFCompanyAccess={isCollaborator,can,allowedTab,initialize,apply,rewrite};

  let records=[], catalog=[], presets=[], dependencies={}, editId=null;
  const setupRequired=record=>record.password_setup_required===true;
  const accessState=record=>!record.is_active?'inactive':(setupRequired(record)?'pending':'active');
  function invitationDescription(record){
    if(!record.is_active) return 'Accesso disattivato. Gli eventuali link di invito precedenti non sono utilizzabili.';
    if(!setupRequired(record)) return 'Il collaboratore ha già scelto la password. Può modificarla dal proprio profilo o recuperarla dalla pagina Login.';
    if(record.invitation_status==='failed') return 'Collaboratore salvato, ma l’email di invito non è stata inviata. Puoi riprovare con Invia nuovo invito.';
    if(record.invitation_status==='expired') return 'Invito scaduto. Invia un nuovo invito per consentire al collaboratore di scegliere la password.';
    return 'In attesa che il collaboratore scelga la propria password tramite il link personale ricevuto via email.';
  }
  const root=()=>document.getElementById('collaboratorsBody');
  const escape=value=>esc(String(value ?? ''));
  async function load(){
    if(isCollaborator()) return;
    root().innerHTML='<tr><td colspan="5">Caricamento collaboratori…</td></tr>';
    try{
      const [items,config]=await Promise.all([api('/api/collaborators'),api('/api/collaborators/permissions')]);
      records=items;catalog=config.permissions;presets=Array.isArray(config.presets)?config.presets:[];dependencies=config.dependencies;render();
    }catch(e){root().innerHTML=`<tr><td colspan="5">${escape(e.message)} <button class="btn-secondary" onclick="GFCollaborators.load()">Riprova</button></td></tr>`;}
  }
  function render(){
    const term=(document.getElementById('collaboratorSearch').value || '').trim().toLocaleLowerCase();
    const state=document.getElementById('collaboratorStatus').value;
    const rows=records.filter(r=>(`${r.full_name} ${r.email}`).toLocaleLowerCase().includes(term) && (!state || accessState(r)===state));
    document.getElementById('collaboratorsTotal').textContent=records.length;
    document.getElementById('collaboratorsActive').textContent=records.filter(r=>accessState(r)==='active').length;
    document.getElementById('collaboratorsPending').textContent=records.filter(r=>accessState(r)==='pending').length;
    document.getElementById('collaboratorsInactive').textContent=records.filter(r=>!r.is_active).length;
    root().innerHTML=rows.map(r=>{
      const status=accessState(r);
      const label=status==='pending'?'Invito in attesa':(status==='active'?'Attivo':'Disattivato');
      const detail=status==='pending' && r.invitation_status==='failed'?'Email non inviata':(status==='pending' && r.invitation_status==='expired'?'Invito scaduto':'');
      return `<tr><td data-label="Collaboratore"><strong>${escape(r.full_name)}</strong><small>${escape(r.email)}</small></td><td data-label="Accesso"><span class="gf-badge" data-status="${status==='pending'?'warning':(status==='active'?'success':'neutral')}">${label}</span>${detail?'<small class="collaborator-invitation-warning">'+escape(detail)+'</small>':''}</td><td data-label="Funzioni">${escape([...new Set(catalog.filter(p=>(r.permissions || []).includes(p.key)).map(p=>p.group))].join(', ') || 'Nessuna funzione assegnata')}</td><td data-label="Ultimo accesso">${r.last_login?escape(new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(r.last_login)?r.last_login:r.last_login+'Z').toLocaleString('it-IT')):'Mai effettuato'}</td><td data-label="Azioni"><button class="btn-secondary" onclick="GFCollaborators.edit(${Number(r.id)})">Gestisci</button></td></tr>`;
    }).join('') || '<tr><td colspan="5" class="collaborators-empty">Nessun collaboratore trovato. Invita un collaboratore e scegli le funzioni da assegnare.</td></tr>';
  }
  function selectedPermissions(){
    return [...document.querySelectorAll('#collaboratorPermissions input:checked')].map(el=>el.value);
  }
  function updateSelectionSummary(){
    const selector=document.getElementById('collaboratorPreset');
    const preset=presets.find(item=>item.key===selector.value);
    document.getElementById('collaboratorPresetDescription').textContent=preset?.description || 'Scegli liberamente le funzioni di questo collaboratore. Abbonamento, fatturazione e gestione collaboratori restano riservati al titolare.';
    document.getElementById('collaboratorPermissionsCount').textContent=selectedPermissions().length+' di '+catalog.length+' selezionate';
  }
  function expand(){
    const checked=new Set(selectedPermissions());
    let changed=true;while(changed){changed=false;for(const key of checked)for(const dependency of dependencies[key] || [])if(!checked.has(dependency)){checked.add(dependency);changed=true;}}
    document.querySelectorAll('#collaboratorPermissions input').forEach(el=>el.checked=checked.has(el.value));
    updateSelectionSummary();
  }
  function selectPreset(){
    const selector=document.getElementById('collaboratorPreset');
    const preset=presets.find(item=>item.key===selector.value);
    if(preset){
      const grants=new Set(preset.permissions);
      document.querySelectorAll('#collaboratorPermissions input').forEach(el=>el.checked=grants.has(el.value));
      expand();
    }else updateSelectionSummary();
    document.getElementById('collaboratorPermissionsDetails').open=!preset;
  }
  function customize(){
    document.getElementById('collaboratorPreset').value='custom';
    expand();
  }
  function edit(id){
    if(!catalog.length){toast('Attendi il caricamento dei permessi.');return;}
    const record=records.find(r=>r.id===id);editId=record?.id || null;
    document.getElementById('collaboratorForm').reset();
    document.getElementById('collaboratorFormTitle').textContent=record?'Gestisci collaboratore':'Invita collaboratore';
    document.getElementById('collaboratorSave').textContent=record?'Salva modifiche':'Invia invito';
    document.getElementById('collaboratorName').value=record?.full_name || '';
    document.getElementById('collaboratorEmail').value=record?.email || '';
    document.getElementById('collaboratorActive').checked=record?record.is_active:true;
    document.getElementById('collaboratorInvitationNote').textContent=record?invitationDescription(record):'L’azienda non sceglie e non riceve la password. Quando l’accesso è abilitato inviamo automaticamente un’email con un link personale: il collaboratore sceglie la propria password prima di accedere.';
    document.getElementById('collaboratorResendInvite').hidden=!(record && record.is_active && setupRequired(record));
    document.getElementById('collaboratorError').textContent='';
    const groups=[...new Set(catalog.map(p=>p.group))];
    document.getElementById('collaboratorPermissions').innerHTML=groups.map(group=>`<fieldset><legend>${escape(group)}</legend>${catalog.filter(p=>p.group===group).map(p=>`<label><input type="checkbox" value="${escape(p.key)}" ${record?.permissions.includes(p.key)?'checked':''}> <span>${escape(p.label)}</span></label>`).join('')}</fieldset>`).join('');
    const selector=document.getElementById('collaboratorPreset');
    selector.innerHTML=presets.map(preset=>'<option value="'+escape(preset.key)+'">'+escape(preset.label)+'</option>').join('')+'<option value="custom">Personalizzato</option>';
    const grants=new Set(record?.permissions || []);
    const matching=record && presets.find(preset=>preset.permissions.length===grants.size && preset.permissions.every(key=>grants.has(key)));
    selector.value=record?(matching?.key || 'custom'):(presets.some(preset=>preset.key==='operator')?'operator':'custom');
    if(record){
      // Opening an existing account never replaces its stored grants.
      updateSelectionSummary();
      document.getElementById('collaboratorPermissionsDetails').open=!matching;
    }else selectPreset();
    document.getElementById('collaboratorDialog').showModal();
  }
  async function save(event){
    event.preventDefault();const button=document.getElementById('collaboratorSave');button.disabled=true;
    try{
      expand();const payload={full_name:document.getElementById('collaboratorName').value,email:document.getElementById('collaboratorEmail').value,
        is_active:document.getElementById('collaboratorActive').checked,permissions:[...document.querySelectorAll('#collaboratorPermissions input:checked')].map(el=>el.value)};
      const result=await api('/api/collaborators'+(editId?'/'+editId:''),{method:editId?'PUT':'POST',body:JSON.stringify(payload)});
      await load();
      if(result.is_active && setupRequired(result) && result.invitation_sent===false){
        // The account exists even when email delivery fails: keep editing it so retry cannot create a duplicate.
        edit(result.id);
        document.getElementById('collaboratorError').textContent=result.message || 'Collaboratore salvato, ma l’email di invito non è stata inviata. Puoi riprovare con Invia nuovo invito.';
      }else{
        document.getElementById('collaboratorDialog').close();
        toast(result.invitation_sent===true?'Invito inviato. Il collaboratore sceglierà la propria password.':'Accesso collaboratore salvato');
      }
    }catch(e){document.getElementById('collaboratorError').textContent=e.message;}
    finally{button.disabled=false;}
  }
  async function invite(){
    const record=records.find(item=>item.id===editId);
    if(!record || !record.is_active || !setupRequired(record)) return;
    const selected=new Set(selectedPermissions());
    if(document.getElementById('collaboratorName').value!==record.full_name || document.getElementById('collaboratorEmail').value!==record.email || document.getElementById('collaboratorActive').checked!==record.is_active || selected.size!==record.permissions.length || record.permissions.some(key=>!selected.has(key))){
      document.getElementById('collaboratorError').textContent='Salva prima le modifiche al collaboratore, poi invia un nuovo invito.';
      return;
    }
    const button=document.getElementById('collaboratorResendInvite');
    const saveButton=document.getElementById('collaboratorSave');
    button.disabled=true;saveButton.disabled=true;
    document.getElementById('collaboratorError').textContent='';
    try{
      const result=await api('/api/collaborators/'+record.id+'/invite',{method:'POST'});
      await load();edit(record.id);
      if(result.invitation_sent===true){
        document.getElementById('collaboratorInvitationNote').textContent=result.message || 'Nuovo invito inviato. Il link precedente non è più valido.';
        toast('Nuovo invito inviato');
      }else document.getElementById('collaboratorError').textContent=result.message || 'L’email di invito non è stata inviata. Riprova più tardi.';
    }catch(e){document.getElementById('collaboratorError').textContent=e.message;}
    finally{button.disabled=false;saveButton.disabled=false;}
  }
  window.GFCollaborators={load,render,edit,save,invite,expand,selectPreset,customize};
})();
