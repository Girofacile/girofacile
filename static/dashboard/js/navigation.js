// One navigation entry point; dependencies are provided by the feature modules.
const WORKSPACE_TOPBAR_META = {
  ordini: {title:"Ordini",subtitle:"Gestisci gli ordini ricevuti e prepara le tue consegne."},
  "ordine-dettaglio": {title:"Dettaglio ordine",subtitle:"Dati operativi e storico delle correzioni."},
  "ordine-modifica": {title:"Modifica ordine",subtitle:"Completa le informazioni disponibili."},
  "ordini-collegamenti": {title:"Collega i tuoi ordini",subtitle:"Importa un file o prepara l’invio dal tuo gestionale. Controlla sempre l’anteprima prima di attivare una fonte."},
  "ordini-importa": {title:"Importa ordini",subtitle:"Carica il file, controlla i dati e conferma."},
  "ordine-fonte": {title:"Fonte ordini",subtitle:"Gestione fonte e validazione dei dati in ingresso."},
  collaboratori: {title:"Collaboratori",subtitle:"Gestisci accessi personali e funzioni assegnate."},
  "dashboard-in-progress": {
    title: "Giri in corso",
    subtitle: "Avanzamento delle consegne, stato delle fermate e posizione GPS degli autisti."
  },
  dashboard: {
    title: "Dashboard",
    subtitle: "Panoramica operativa delle consegne e dell’attività aziendale."
  },
  company: {
    title: "Profilo azienda",
    subtitle: "Configura i dati principali della tua azienda e completa la prima configurazione di GiroFacile."
  },
  clienti: {
    title: "Clienti",
    subtitle: "Anagrafica clienti e fasce orarie di scarico."
  },
  depositi: {
    title: "Depositi",
    subtitle: "Gestisci gli indirizzi di partenza e rientro dei tuoi giri."
  },
  mezzi: {
    title: "Mezzi",
    subtitle: "Gestisci i tuoi mezzi aziendali e le relative caratteristiche."
  },
  autisti: {
    title: "Autisti",
    subtitle: "Gestisci anagrafiche, contatti, patenti e assegnazioni operative."
  },
  agenti: {
    title: "Agenti",
    subtitle: "Anagrafica agenti collegabili ai clienti."
  },
  giro: {
    title: "Pianificazione giro consegne",
    subtitle: "Seleziona clienti, configura risorse e calcola il percorso prima della programmazione."
  },
  "chat-autisti": {
    title: "Chat autisti",
    subtitle: "Centro comunicazioni con gli autisti: conversazioni collegate ai giri e messaggi non letti."
  }
};

// Il titolo della home saluta l'azienda, non il nome dell'account personale.
function dashboardGreetingTitle(){
  const companyName=(typeof currentSessionUser!=="undefined" && currentSessionUser?.company_name) || "";
  const savedCompanyName=localStorage.getItem("girofacile_company_name") || "";
  const accountName=(typeof currentSessionUser!=="undefined" && currentSessionUser?.username)
    || localStorage.getItem("girofacile_account_name") || "";
  // Le vecchie sessioni salvavano talvolta lo username nel campo nome azienda.
  const name=String(companyName || (savedCompanyName !== accountName ? savedCompanyName : "")).trim();
  return name?`Buongiorno, ${name}`:"Buongiorno";
}

function syncWorkspaceTopbar(name){
  const company=name==="company";
  const meta=WORKSPACE_TOPBAR_META[name] || WORKSPACE_TOPBAR_META.dashboard;
  const title=document.getElementById("workspacePageTitle");
  const subtitle=document.getElementById("workspacePageSubtitle");
  if(title) title.textContent=name==="dashboard"?dashboardGreetingTitle():meta.title;
  if(subtitle){
    if(name==="dashboard-in-progress"){
      const day=new Intl.DateTimeFormat("it-IT",{weekday:"long",day:"numeric",month:"long"}).format(new Date());
      subtitle.textContent=day.charAt(0).toUpperCase()+day.slice(1)+": "+
        meta.subtitle.charAt(0).toLowerCase()+meta.subtitle.slice(1);
    }else subtitle.textContent=meta.subtitle;
  }
  const badge=document.getElementById("workspacePageBadge");
  if(badge){badge.hidden=true;badge.textContent="";badge.className="order-source-topbar-badge";}
  if(document.body){
    document.body.classList.toggle("gf-company-page-active",company);
  }
}

function showTab(name){
  if(window.GFCompanyAccess && !GFCompanyAccess.allowedTab(name)){toast("Funzione non assegnata al tuo account");return;}
  window.GFLiveDesign?.closeMap();
  if(name!=="dashboard-in-progress")window.GFInProgressReference?.suspend();
  if(name==='integrations') name='dashboard';
  if(name !== "company" && typeof blockCompanyNavigationForUnsavedChanges === "function" && blockCompanyNavigationForUnsavedChanges()) return;
  if(blockOperationalTabV49(name)) return;
  if(name === "agenti" && !agentsFeatureEnabled()) name = "settings";
  if(showLockedOrProceed(name)) return;
  document.querySelectorAll(".tab").forEach(x=>x.classList.add("hidden"));
  const tab = document.getElementById("tab-"+name);
  if(tab) tab.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));
  const navTab=["ordini-importa","ordine-fonte","ordine-dettaglio","ordine-modifica","ordini-collegamenti"].includes(name)?"ordini":name;
  document.querySelectorAll(`.nav-item[data-tab="${navTab}"]`).forEach(x=>x.classList.add("active"));
  syncWorkspaceTopbar(name);

  if(name==="dashboard"){ loadDashboardHome(); if(!window.GFCompanyAccess || GFCompanyAccess.can("notifications.read")) loadNotificationsV30(false); if(!featureLockedForTab("chat-autisti") && (!window.GFCompanyAccess || GFCompanyAccess.can("chat.read"))) loadDriverChatNotifications(); }
  if(name==="company") { loadCompanyProfile(); if(!window.GFCompanyAccess?.isCollaborator()) loadOnboardingStatus(false); }
  if(name!=="ordini-collegamenti") window.GFOrderSources?.hideSecret();
  if(name==="ordini-collegamenti") window.GFOrderSources?.load();
  if(name==="ordini") GFOrders.load();
  if(name==="collaboratori") GFCollaborators.load();
  if(name==="dashboard-scheduled") loadDashboardScheduledPage();
  if(name==="dashboard-in-progress") loadDashboardInProgressPage();
  if(name==="dashboard-completed") loadDashboardCompletedPage();
  if(name==="giro") loadDashboardRoutes();
  if(name==="clienti"){ loadCustomers(); if(agentsFeatureEnabled()) loadAgents(); }
  if(name==="agenti") loadAgents();
  if(name==="report") loadReport();
  if(name==="depositi") loadDeposits();
  if(name==="mezzi") loadVehicles();
  if(name==="autisti") loadDrivers();
  if(name==="storico") loadRoutes();
  if(name==="chat-autisti") loadDriverChatCenter();
  if(name==="settings"){ loadSettingsV41(); loadUniversalFeaturesV89(); }
  if(name==="plan-account"){ renderUpgradeCards(); syncPlanPageHeaderV874(); }
  if(name==="integrations") renderIntegrationsV52();

  if(name==="admin-dashboard") loadAdminDashboard();
  if(name==="admin-users") loadAdminUsers();
  if(name==="admin-tickets") loadAdminTickets();
  if(name === 'dashboard') applyWorkspaceStateV49(gfWorkspaceOperationalV49);
  setTimeout(()=>{syncMobileShellV62();window.GFCompanyAccess?.apply();}, 40);
}
