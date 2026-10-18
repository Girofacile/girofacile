// One navigation entry point; dependencies are provided by the feature modules.
const WORKSPACE_TOPBAR_META = {
  ordini: {title:"Ordini",subtitle:"Gestisci gli ordini ricevuti e prepara le tue consegne."},
  "ordine-dettaglio": {title:"Dettaglio ordine",subtitle:"Dati operativi e storico delle correzioni."},
  "ordine-modifica": {title:"Modifica ordine",subtitle:"Completa le informazioni disponibili."},
  "ordini-collegamenti": {title:"Collega i tuoi ordini",subtitle:"Importa un file o prepara l’invio dal tuo gestionale. Controlla sempre l’anteprima prima di attivare una fonte."},
  "ordini-importa": {title:"Importa ordini",subtitle:"Carica il file, controlla i dati e conferma.",back:{label:"Torna agli ordini",go:()=>showTab("ordini")}},
  "ordine-fonte": {title:"Fonte ordini",subtitle:"Gestione fonte e validazione dei dati in ingresso."},
  collaboratori: {title:"Collaboratori",subtitle:"Accessi personali al gestionale, con le funzioni che decidi di assegnare."},
  "collaborator-home": {title:"Il tuo accesso",subtitle:"Funzioni operative assegnate dal titolare dell’azienda."},
  settings: {title:"Impostazioni",subtitle:"Configura le preferenze operative applicate al gestionale aziendale."},
  report: {title:"Report consegne",subtitle:"Analizza i giri completati: chilometri, tempi, consumi e costi stimati."},
  storico: {title:"Storico giri",subtitle:"Consulta i percorsi completati, i chilometri e i dati operativi dei tuoi giri."},
  "plan-account": {title:"Piani e abbonamento",subtitle:"Gestisci il piano attivo e confronta le funzionalità disponibili.",back:{label:"Torna al profilo",go:()=>returnFromPlanAccount()}},
  "billing-account": {title:"Fatturazione e pagamenti",subtitle:"Abbonamento, metodo di pagamento, dati fiscali, fatture e addebiti.",back:{label:"Torna a Piani e abbonamento",go:()=>returnFromBillingPageV876()}},
  "dashboard-scheduled": {title:"Giri programmati",subtitle:"Giri assegnati ma non ancora avviati dall’autista.",back:{label:"Torna alla Dashboard",go:()=>showTab("dashboard")}},
  "dashboard-completed": {title:"Giri completati",subtitle:"Archivio operativo dei giri conclusi dall’autista.",back:{label:"Torna allo Storico",go:()=>showTab("storico")}},
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

// Il saluto segue l'ora italiana, indipendentemente dal fuso del computer.
function dashboardGreetingPrefix(now = new Date()){
  const hourPart=new Intl.DateTimeFormat("it-IT",{
    timeZone:"Europe/Rome",
    hour:"2-digit",
    hourCycle:"h23"
  }).formatToParts(now).find(part=>part.type==="hour");
  const hour=Number(hourPart?.value);
  if(hour>=5 && hour<12) return "Buongiorno";
  if(hour>=12 && hour<18) return "Buon pomeriggio";
  return "Buonasera";
}

// Il titolo della home saluta l'azienda, non il nome dell'account personale.
function dashboardGreetingTitle(){
  const companyName=(typeof currentSessionUser!=="undefined" && currentSessionUser?.company_name) || "";
  const savedCompanyName=localStorage.getItem("girofacile_company_name") || "";
  const accountName=(typeof currentSessionUser!=="undefined" && currentSessionUser?.username)
    || localStorage.getItem("girofacile_account_name") || "";
  // Le vecchie sessioni salvavano talvolta lo username nel campo nome azienda.
  const name=String(companyName || (savedCompanyName !== accountName ? savedCompanyName : "")).trim();
  const greeting=dashboardGreetingPrefix();
  return name ? greeting + ", " + name : greeting;
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
  // Pulsante "indietro" unico, nella barra in alto come nelle altre sottopagine.
  const back=document.getElementById("workspaceTopbarBack");
  if(back){
    const target=meta.back && WORKSPACE_TOPBAR_META[name]===meta ? meta.back : null;
    back.hidden=!target;
    back.onclick=target?target.go:null;
    if(target){back.setAttribute("aria-label",target.label);back.title=target.label;}
    document.body?.classList.toggle("gf-has-topbar-back",!!target);
  }
  const badge=document.getElementById("workspacePageBadge");
  if(badge){badge.hidden=true;badge.textContent="";badge.className="gf-badge";delete badge.dataset.status;}
  // Elementi legati a una sezione (azioni dell'intestazione, voci di menu): visibili solo lì.
  document.querySelectorAll("[data-show-on-tabs]").forEach(el=>el.classList.toggle("gf-hidden",!el.dataset.showOnTabs.split(" ").includes(name)));
  document.querySelectorAll("[data-hide-on-tabs]").forEach(el=>el.classList.toggle("gf-hidden",el.dataset.hideOnTabs.split(" ").includes(name)));
  if(document.body){
    document.body.classList.toggle("gf-company-page-active",company);
  }
}

// Voce attiva della sidebar del layout base (aria-current, come in shell.js).
function setActiveNavItem(name){
  document.querySelectorAll(".gf-sidebar__item[data-tab]").forEach(x=>{
    if(x.dataset.tab===name) x.setAttribute("aria-current","page"); else x.removeAttribute("aria-current");
  });
}

function showTab(name){
  if(window.GFCompanyAccess && !GFCompanyAccess.allowedTab(name)){toast("Funzione non assegnata al tuo account");return;}
  if(name!=="dashboard-in-progress")window.GFInProgressReference?.suspend();
  if(name==='integrations') name='dashboard';
  if(name !== "company" && typeof blockCompanyNavigationForUnsavedChanges === "function" && blockCompanyNavigationForUnsavedChanges()) return;
  if(blockOperationalTabV49(name)) return;
  if(name === "agenti" && !agentsFeatureEnabled()) name = "settings";
  if(showLockedOrProceed(name)) return;
  document.querySelectorAll(".tab").forEach(x=>x.classList.add("hidden"));
  const tab = document.getElementById("tab-"+name);
  if(tab) tab.classList.remove("hidden");
  const navTab=["ordini-importa","ordine-fonte","ordine-dettaglio","ordine-modifica","ordini-collegamenti"].includes(name)?"ordini":name;
  setActiveNavItem(navTab);
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

  if(name === 'dashboard') applyWorkspaceStateV49(gfWorkspaceOperationalV49);
  setTimeout(()=>{syncMobileShellV62();window.GFCompanyAccess?.apply();}, 40);
}

// Se la Dashboard resta aperta, aggiorna il saluto al cambio della fascia oraria.
function refreshDashboardGreeting(){
  const dashboard=document.getElementById("tab-dashboard");
  if(!dashboard || dashboard.classList.contains("hidden")) return;
  const title=document.getElementById("workspacePageTitle");
  if(title) title.textContent=dashboardGreetingTitle();
}
if(typeof window!=="undefined" && typeof window.setInterval==="function"){
  window.setInterval(refreshDashboardGreeting,60_000);
}

/* New routes start from a delivery selection; the planner remains available for saved routes. */
function openPlanningSelection(){
  if(!window.GFCompanyAccess||GFCompanyAccess.can('orders.plan')){
    showTab('ordini');return;
  }
  if(GFCompanyAccess.can('routes.plan')&&GFCompanyAccess.allowedTab('clienti')){
    showTab('clienti');return;
  }
  toast('La selezione delle consegne non è assegnata al tuo account.');
}
