// One navigation entry point; dependencies are provided by the feature modules.
function showTab(name){
  window.GFLiveDesign?.closeMap();
  if(['transfer-portal','transfer-bookings','transfer-planning','transfer-settings','integrations'].includes(name)) name='dashboard';
  if(blockOperationalTabV49(name)) return;
  if(name === "agenti" && !agentsFeatureEnabled()) name = "settings";
  if(showLockedOrProceed(name)) return;
  document.querySelectorAll(".tab").forEach(x=>x.classList.add("hidden"));
  const tab = document.getElementById("tab-"+name);
  if(tab) tab.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(`.nav-item[data-tab="${name}"]`).forEach(x=>x.classList.add("active"));

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
  if(name==="transfer-portal") loadTransferPortalV78();
  if(name==="transfer-bookings") loadTransferBookingsV79();
  if(name==="transfer-planning") loadTransferPlanningV79();
  if(name==="transfer-settings") loadTransferSettingsV79();

  if(name==="admin-dashboard") loadAdminDashboard();
  if(name==="admin-users") loadAdminUsers();
  if(name==="admin-tickets") loadAdminTickets();
  if(name === 'dashboard') applyWorkspaceStateV49(gfWorkspaceOperationalV49);
  setTimeout(syncMobileShellV62, 40);
}
