// One navigation entry point; dependencies are provided by the feature modules.
const WORKSPACE_TOPBAR_META = {
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

function syncWorkspaceTopbar(name){
  const company=name==="company";
  const meta=WORKSPACE_TOPBAR_META[name] || WORKSPACE_TOPBAR_META.dashboard;
  const title=document.getElementById("workspacePageTitle");
  const subtitle=document.getElementById("workspacePageSubtitle");
  if(title) title.textContent=meta.title;
  if(subtitle) subtitle.textContent=meta.subtitle;
  if(document.body){
    document.body.classList.toggle("gf-company-page-active",company);
  }
}

function showTab(name){
  window.GFLiveDesign?.closeMap();
  if(name==='integrations') name='dashboard';
  if(name !== "company" && typeof blockCompanyNavigationForUnsavedChanges === "function" && blockCompanyNavigationForUnsavedChanges()) return;
  if(blockOperationalTabV49(name)) return;
  if(name === "agenti" && !agentsFeatureEnabled()) name = "settings";
  if(showLockedOrProceed(name)) return;
  document.querySelectorAll(".tab").forEach(x=>x.classList.add("hidden"));
  const tab = document.getElementById("tab-"+name);
  if(tab) tab.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(`.nav-item[data-tab="${name}"]`).forEach(x=>x.classList.add("active"));
  syncWorkspaceTopbar(name);

  if(name==="dashboard"){ loadDashboardHome(); loadNotificationsV30(false); if(!featureLockedForTab("chat-autisti")) loadDriverChatNotifications(); }
  if(name==="company") { loadCompanyProfile(); loadOnboardingStatus(false); }
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
  setTimeout(syncMobileShellV62, 40);
}
