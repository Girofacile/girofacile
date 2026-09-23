function showGestionaleAfterLogin(isAdmin=false){
  // Dashboard aziendale: non attivare mai il vecchio menu Admin SaaS qui.
  // Il Super Admin usa /admin/login e /admin, separati dal gestionale aziendale.
  isAdmin = false;
  const loginCard = document.getElementById('loginCard');
  const app = document.getElementById('app');
  if(loginCard){
    loginCard.classList.add('hidden');
    loginCard.style.display = 'none';
  }
  if(app){
    app.classList.remove('hidden');
    app.style.display = 'flex';
  }
  document.body.classList.add('app-logged-in');
  document.body.classList.toggle('admin-mode', !!isAdmin);
  document.body.classList.toggle('user-mode', !isAdmin);
}

function showLoginScreen(){
  const loginCard = document.getElementById('loginCard');
  const app = document.getElementById('app');
  if(app){
    app.classList.add('hidden');
    app.style.display = 'none';
  }
  if(loginCard){
    loginCard.classList.remove('hidden');
    loginCard.style.display = 'grid';
  }
  document.body.classList.remove('app-logged-in');
}

let deliveries = [];
let selectedCustomer = null;
let customersCache = [];
let agentsCache = [];
let depositsCache = [];
let vehiclesCache = [];
let driversCache = [];
let editingDeliveryIndex = null;
let lastMapsUrl = "";
let lastRouteResult = null;
let draggedStopIndex = null;
let reportData = null;
let reportSort = {drivers:{key:'consegne', dir:-1}};
let profilePhotoData = localStorage.getItem("girofacile_profile_photo") || "";
let currentSessionUser = null;


/* ------------------------------------------------------------------
   v47 - Motore Settori Aziendali
   Una sola piattaforma, etichette/funzioni adattate al settore scelto.
------------------------------------------------------------------ */
const GF_DEFAULT_LABELS_V47 = {
  customer:"Cliente", customers:"Clienti",
  driver:"Autista", drivers:"Autisti",
  vehicle:"Mezzo", vehicles:"Mezzi",
  delivery:"Consegna", deliveries:"Consegne",
  route:"Giro", routes:"Giri",
  stop:"Fermata", stops:"Fermate",
  scheduled_routes:"Giri programmati",
  active_routes:"Giri in corso",
  completed_today:"Giri completati oggi",
  route_planning:"Pianificazione giro",
  new_route:"+ Nuovo giro"
};
let gfSectorConfigV47 = {key:"altro", name:"Altro / configurazione generica", labels:{...GF_DEFAULT_LABELS_V47}, features:[], recommended_defaults:{}};
let gfSectorOptionsV47 = [];

function gfLabelsV47(){
  return {...GF_DEFAULT_LABELS_V47, ...((gfSectorConfigV47 && gfSectorConfigV47.labels) || {})};
}
function gfLabelV47(key){ return gfLabelsV47()[key] || GF_DEFAULT_LABELS_V47[key] || key; }
function gfSectorNameV47(key){
  const found = gfSectorOptionsV47.find(x => x.key === key);
  return found ? found.name : (gfSectorConfigV47?.name || "Settore generico");
}
function setSectorConfigV47(data){
  if(!data) return;
  if(data.sector_options) gfSectorOptionsV47 = data.sector_options;
  if(data.sector_config) gfSectorConfigV47 = {...gfSectorConfigV47, ...data.sector_config, labels:{...GF_DEFAULT_LABELS_V47, ...(data.sector_config.labels || {})}};
  if(data.current) gfSectorConfigV47 = {...gfSectorConfigV47, ...data.current, labels:{...GF_DEFAULT_LABELS_V47, ...(data.current.labels || {})}};
  applySectorLabelsV47();
}
function fillSectorSelectV47(selectId, selected){
  const sel = document.getElementById(selectId);
  if(!sel || !gfSectorOptionsV47.length) return;
  const current = selected || sel.value || "";
  sel.innerHTML = `<option value="">Seleziona il settore</option>` + gfSectorOptionsV47.map(opt => `<option value="${esc(opt.key)}">${esc(opt.name)}</option>`).join("");
  if(current) sel.value = current;
}
function renderSectorFeatureChipsV47(){
  const box = document.getElementById("companySectorFeatureChips");
  if(!box) return;
  const features = gfSectorConfigV47.features || [];
  box.innerHTML = features.length ? features.map(f => `<span>${esc(f)}</span>`).join("") : `<span>Configurazione generica</span>`;
}
function applySectorLabelsV47(){
  const L = gfLabelsV47();
  document.querySelectorAll("[data-gf-label]").forEach(el => {
    const key = el.getAttribute("data-gf-label");
    if(L[key]) el.textContent = L[key];
  });
  document.querySelectorAll("[data-gf-label-prefix]").forEach(el => {
    const key = el.getAttribute("data-gf-label-prefix");
    const suffix = el.getAttribute("data-gf-label-suffix") || "";
    if(L[key]) el.textContent = L[key] + suffix;
  });
  const sectorPill = document.getElementById("companySectorPillV47");
  if(sectorPill) sectorPill.textContent = gfSectorConfigV47.name || "Settore generico";
  const sectorDesc = document.getElementById("companySectorDescriptionV47");
  if(sectorDesc) sectorDesc.textContent = `GiroFacile sta usando etichette e impostazioni consigliate per: ${gfSectorConfigV47.name || "settore generico"}.`;
  renderSectorFeatureChipsV47();
}

const STARTER_LOCKED_TABS = {
  agenti: {feature:"has_agents", title:"Agenti", text:"La gestione agenti è disponibile dal piano Business."},
  report: {feature:"has_reports", title:"Report", text:"I report avanzati sono disponibili dal piano Business."},
  "chat-autisti": {feature:"has_driver_chat", title:"Chat autisti", text:"La chat diretta con gli autisti è disponibile dal piano Business."}
};

function featureLockedForTab(name){
  if(!currentSessionUser) return null;
  const cfg = STARTER_LOCKED_TABS[name];
  if(!cfg) return null;
  const limits = currentSessionUser.limits || {};
  // La visibilità premium dipende dal piano dell'azienda, non dal ruolo "Amministratore" dell'account.
  // Così un account aziendale Starter vede la sezione nel menu, ma non il contenuto operativo.
  return limits[cfg.feature] ? null : cfg;
}

function premiumPlanCard(plan, title, price, badge, features){
  return `<div class="feature-plan-card">
    <div class="feature-plan-badge">${esc(badge)}</div>
    <h3>${esc(title)}</h3>
    <div class="feature-plan-price">${esc(price)}<span>/mese</span></div>
    <ul>${features.map(f=>`<li>${esc(f)}</li>`).join("")}</ul>
    <button class="btn-primary" onclick="openUpgradePanelFor('${plan}')">Passa a ${esc(title)}</button>
  </div>`;
}

function renderFeatureLockedTab(name, cfg){
  const tab = document.getElementById("tab-" + name);
  if(!tab || !cfg) return;
  tab.innerHTML = `<div class="feature-lock-page">
    <div class="feature-lock-layout">
      <section class="feature-lock-card">
        <div class="feature-lock-icon">🔒</div>
        <span class="feature-lock-kicker">Funzionalità premium</span>
        <h1>${esc(cfg.title)}</h1>
        <p>${esc(cfg.text)} Effettua l'upgrade al piano successivo per poter usufruire di questa sezione.</p>
        <button class="btn-primary" onclick="openUpgradePanelFor('business')">Effettua upgrade</button>
      </section>
      <aside class="feature-lock-side">
        <div class="feature-lock-side-title">Piani consigliati</div>
        ${premiumPlanCard('business','Business','€39','Consigliato',[
          'Agenti commerciali',
          'Report e analisi finali',
          'Chat autisti',
          'Export CSV'
        ])}
        ${premiumPlanCard('pro','Pro','€79','Completo',[
          'Clienti e giri illimitati',
          'Tutte le funzioni Business',
          'Mezzi e autisti illimitati',
          'Supporto prioritario'
        ])}
      </aside>
    </div>
  </div>`;
}

function showLockedOrProceed(name){
  const locked = featureLockedForTab(name);
  if(!locked) return false;
  document.querySelectorAll(".tab").forEach(x=>x.classList.add("hidden"));
  const tab = document.getElementById("tab-" + name);
  if(tab) tab.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(`.nav-item[data-tab="${name}"]`).forEach(x=>x.classList.add("active"));
  renderFeatureLockedTab(name, locked);
  return true;
}

function updatePremiumNavState(){
  Object.keys(STARTER_LOCKED_TABS).forEach(name=>{
    const cfg = featureLockedForTab(name);
    document.querySelectorAll(`.nav-item[data-tab="${name}"]`).forEach(btn=>{
      btn.classList.toggle("is-premium-locked", !!cfg);
      btn.title = cfg ? `${cfg.title}: disponibile dal piano Business` : "";
    });
  });
}

function updateDashboardStats(){
  try{
    const stops = deliveries.length;
    const kg = deliveries.reduce((a,d)=>a+(parseFloat(d.peso_kg)||0),0);
    const colli = deliveries.reduce((a,d)=>a+(parseInt(d.colli)||0),0);
    const warnings = deliveries.filter(d=>d.ztl || d.sponda).length;
    const fuel = document.getElementById("fuelPrice")?.value || "";
    const setText = (id,val)=>{ const el=document.getElementById(id); if(el) el.textContent=val; };
    setText("statDeliveries", stops);
    setText("statWarnings", warnings);
    setText("summaryStops", stops);
    setText("summaryKg", kg.toFixed(0)+" kg");
    setText("summaryColli", colli);
    setText("statColli", colli);
    const sv=vehiclesCache.find(v=>String(v.id)===String(val("routeVehicle"))); const unit=(sv?.alimentazione==="metano")?"€/kg":(sv?.alimentazione==="elettrico"?"€/kWh":"€/L"); setText("statFuel", fuel ? fuel+" "+unit : unit);
  }catch(e){}
}

async function api(path, options = {}) {
  const headers = options.body instanceof FormData ? (options.headers || {}) : {"Content-Type":"application/json", ...(options.headers || {})};
  const res = await fetch(path, {...options, headers});
  if (!res.ok) {
    let msg = "Errore";
    let errorId = null;
    try {
      const j = await res.json();
      if (j && typeof j.detail === "object") {
        msg = j.detail.message || j.detail.detail || msg;
        errorId = j.detail.error_id || j.detail.system_error_id || null;
      } else {
        msg = j.detail || msg;
        errorId = j.error_id || null;
      }
    } catch(e) {}
    const err = new Error(msg);
    err.errorId = errorId;
    throw err;
  }
  return await res.json();
}
function boolVal(id){ const el=document.getElementById(id); return el ? el.value === "true" : false; }
function val(id){ const el=document.getElementById(id); return el ? el.value : ""; }
function set(id,v){ const el=document.getElementById(id); if(el) el.value = v ?? ""; }

let settingsV41 = {delivery_signature_enabled:false, agents_enabled:false};

function agentsFeatureEnabled(){
  return !!settingsV41.agents_enabled && !featureLockedForTab("agenti");
}

function applyAgentsFeature(){
  const enabled = agentsFeatureEnabled();
  document.documentElement.dataset.gfAgents = enabled ? 'on' : 'off';
  const toggle = document.getElementById('settingAgentsEnabled');
  if(toggle){
    toggle.checked = enabled;
    toggle.disabled = !!featureLockedForTab('agenti');
  }
  if(!enabled){
    agentsCache = [];
    ['cAgent','customerFilterAgent','reportAgent'].forEach(id=>set(id,''));
  }
  ['cAgent','customerFilterAgent','reportAgent'].forEach(id=>{
    const el = document.getElementById(id);
    if(el) el.disabled = !enabled;
  });
  updateReportFilterSummary();
}

async function refreshAgentsFeature(){
  applyAgentsFeature();
  await loadAgents();
  await loadCustomers();
  await loadCustomerPicker();
  const filter = document.getElementById('reportAgent');
  if(filter) filter.innerHTML = '<option value="">Tutti gli agenti</option><option value="interno">Cliente interno</option>';
  await loadNotificationsV30(false);
}


async function loadSettingsV41(){
  try{
    settingsV41 = await api('/api/settings');
    applyAgentsFeature();
    const toggle = document.getElementById('settingDeliverySignature');
    if(toggle) toggle.checked = !!settingsV41.delivery_signature_enabled;
    const state = document.getElementById('settingsSaveState');
    if(state) state.textContent = settingsV41.delivery_signature_enabled ? 'Firma cliente attiva nel portale autista.' : 'Firma cliente disattivata nel portale autista.';
  }catch(e){
    const state = document.getElementById('settingsSaveState');
    if(state) state.textContent = 'Impossibile caricare le impostazioni: ' + e.message;
  }
}

async function saveSettingsV41(){
  const toggle = document.getElementById('settingDeliverySignature');
  const state = document.getElementById('settingsSaveState');
  if(state) state.textContent = 'Salvataggio impostazioni...';
  try{
    settingsV41 = await api('/api/settings', {method:'PUT', body:JSON.stringify({delivery_signature_enabled: !!toggle?.checked, agents_enabled: !!document.getElementById('settingAgentsEnabled')?.checked})});
    if(state) state.textContent = settingsV41.delivery_signature_enabled ? 'Firma cliente attivata nel portale autista.' : 'Firma cliente disattivata nel portale autista.';
    await refreshAgentsFeature();
    toast('Impostazioni salvate.');
  }catch(e){
    if(state) state.textContent = 'Errore salvataggio: ' + e.message;
    alert(e.message);
  }
}

async function withButtonLoading(buttonId, loadingText, fn){
  const btn = document.getElementById(buttonId);
  const oldText = btn ? btn.textContent : '';
  if(btn){
    if(btn.dataset.saving === '1') return;
    btn.dataset.saving = '1';
    btn.disabled = true;
    btn.textContent = loadingText || 'Salvataggio...';
  }
  try{
    return await fn();
  }catch(e){
    alert(e.message || 'Errore durante il salvataggio.');
    throw e;
  }finally{
    if(btn){
      btn.disabled = false;
      btn.textContent = oldText;
      btn.dataset.saving = '0';
    }
  }
}

function esc(s){ return String(s ?? "").replace(/[&<>"']/g, m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m])); }
function setImagePreview(previewId, valueId, fallback){
  const url = valueId ? (val(valueId) || "") : "";
  const el = document.getElementById(previewId);
  if(!el) return;
  el.innerHTML = url ? `<img src="${url}" alt="Foto">` : esc(fallback || "");
}
function imageThumb(photo, fallback="👤", extraClass=""){
  return `<div class="asset-thumb ${extraClass}">${photo ? `<img src="${photo}" alt="Foto">` : `<span>${esc(fallback)}</span>`}</div>`;
}
function handleImageUpload(ev, targetId, previewId, fallback){
  const file = ev?.target?.files?.[0];
  if(!file) return;
  if(file.size > 2.5 * 1024 * 1024){
    alert("L'immagine è troppo grande. Usa una foto sotto 2,5 MB.");
    ev.target.value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    set(targetId, reader.result || "");
    setImagePreview(previewId, targetId, fallback);
  };
  reader.readAsDataURL(file);
}
function clearFileInput(id){ const el=document.getElementById(id); if(el) el.value=""; }

function fascia(d){
  const m = (d.scarico_mattina_da || d.scarico_mattina_a) ? `${d.scarico_mattina_da||"--"}-${d.scarico_mattina_a||"--"}` : "--";
  const p = (d.scarico_pomeriggio_da || d.scarico_pomeriggio_a) ? `${d.scarico_pomeriggio_da||"--"}-${d.scarico_pomeriggio_a||"--"}` : "--";
  return `${m} / ${p}`;
}

/* V3.7.8.1 - Autocomplete indirizzi */
const addressAutocompleteState = {};

function markAddressVerified(input, verified){
  if(!input) return;
  input.dataset.addressVerified = verified ? "true" : "false";
  input.classList.toggle("address-verified", !!verified);
  input.classList.toggle("address-unverified", !verified && (input.value || "").trim().length >= 4);
  const wrap = input.closest(".address-autocomplete-wrap");
  const hint = wrap?.querySelector(".address-hint");
  if(hint){
    if(verified){
      hint.textContent = "Indirizzo verificato";
      hint.className = "address-hint ok";
    }else if((input.value || "").trim().length >= 4){
      hint.textContent = "Indirizzo non selezionato dai suggerimenti: verifica prima del calcolo.";
      hint.className = "address-hint warn";
    }else{
      hint.textContent = "";
      hint.className = "address-hint";
    }
  }
}

function setupAddressAutocomplete(inputId, options={}){
  const input = document.getElementById(inputId);
  if(!input || input.dataset.autocompleteReady === "true") return;
  input.dataset.autocompleteReady = "true";

  let wrap = input.closest(".address-autocomplete-wrap");
  if(!wrap){
    wrap = document.createElement("div");
    wrap.className = "address-autocomplete-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
  }

  const list = document.createElement("div");
  list.className = "address-suggestions hidden";
  wrap.appendChild(list);

  const hint = document.createElement("div");
  hint.className = "address-hint";
  wrap.appendChild(hint);

  let timer = null;

  input.addEventListener("input", () => {
    markAddressVerified(input, false);
    clearTimeout(timer);
    const q = input.value.trim();
    if(q.length < 4){
      list.classList.add("hidden");
      list.innerHTML = "";
      return;
    }

    timer = setTimeout(async () => {
      try{
        list.classList.remove("hidden");
        list.innerHTML = `<div class="address-loading">Ricerca indirizzi...</div>`;
        let extra = "";
        if(options.comuneId){
          const v = document.getElementById(options.comuneId)?.value?.trim();
          if(v) extra += `&comune=${encodeURIComponent(v)}`;
        }
        if(options.provinciaId){
          const v = document.getElementById(options.provinciaId)?.value?.trim();
          if(v) extra += `&provincia=${encodeURIComponent(v)}`;
        }
        const rows = await api(`/api/address/search?q=${encodeURIComponent(q)}${extra}`);
        if(!rows.length){
          list.innerHTML = `<div class="address-empty">Nessun indirizzo trovato. Prova con comune, provincia o CAP.</div>`;
          return;
        }

        list.innerHTML = rows.map((r, idx) => `
          <button type="button" class="address-suggestion-item" data-index="${idx}">
            <strong>${esc(r.label.split(",").slice(0,2).join(","))}</strong>
            <span>${esc(r.label)}</span>
          </button>
        `).join("");

        list.querySelectorAll(".address-suggestion-item").forEach(btn => {
          btn.addEventListener("click", () => {
            const r = rows[parseInt(btn.dataset.index)];
            input.value = r.label;
            markAddressVerified(input, true);
            list.classList.add("hidden");
            list.innerHTML = "";

            if(options.comuneId && r.comune){
              const comuneEl = document.getElementById(options.comuneId);
              if(comuneEl && !comuneEl.value) comuneEl.value = r.comune;
            }
            if(options.provinciaId && r.provincia){
              const provEl = document.getElementById(options.provinciaId);
              if(provEl && !provEl.value) provEl.value = r.provincia;
            }
          });
        });
      }catch(e){
        list.innerHTML = `<div class="address-empty">Servizio indirizzi momentaneamente non disponibile.</div>`;
      }
    }, 450);
  });

  input.addEventListener("blur", () => {
    setTimeout(() => list.classList.add("hidden"), 200);
  });

  input.addEventListener("focus", () => {
    if(list.innerHTML.trim()) list.classList.remove("hidden");
  });
}

function initAddressAutocomplete(){
  // Il cliente non usa più la ricerca live Google mentre si scrive:
  // l'indirizzo viene verificato solo dal pulsante "Verifica indirizzo con Google".
  setupAddressAutocomplete("depIndirizzo");
  setupAddressAutocomplete("dIndirizzo");
}


function mapsAddressUrl(address){ return "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(address || ""); }
async function copyText(text, msg="Copiato negli appunti"){
  try{
    await navigator.clipboard.writeText(text || "");
    toast(msg);
  }catch(e){
    prompt("Copia questo link:", text || "");
  }
}
function toast(msg){
  const old = document.querySelector(".toast"); if(old) old.remove();
  const div = document.createElement("div");
  div.className = "toast";
  div.textContent = msg;
  document.body.appendChild(div);
  setTimeout(()=>div.remove(), 2600);
}

function loadProfilePanel(){
  const name = localStorage.getItem("girofacile_profile_name") || "Admin";
  const email = localStorage.getItem("girofacile_profile_email") || "";
  const role = localStorage.getItem("girofacile_profile_role") || "Amministratore";
  const photo = localStorage.getItem("girofacile_profile_photo") || "";
  const initials = (name || "Admin").trim().charAt(0).toUpperCase() || "A";
  const setText = (id,val)=>{ const el=document.getElementById(id); if(el) el.textContent=val; };
  setText("topProfileName", name);
  setText("topProfileRole", role);
  const topAvatar = document.getElementById("topProfileAvatar");
  if(topAvatar){
    topAvatar.innerHTML = photo ? `<img src="${photo}" alt="Profilo">` : initials;
  }
  const preview = document.getElementById("profilePreview");
  if(preview){ preview.innerHTML = photo ? `<img src="${photo}" alt="Profilo">` : initials; }
  set("profileName", name); set("profileEmail", email); set("profileRole", role);
}
async function loadPlanInfo(){
  try{
    const me = await api("/api/me");
    const plan = me.plan || "starter";
    _currentPlan = plan;
    const status = me.plan_status || "trial";
    const limits = me.limits || {};
    currentSessionUser = {...(currentSessionUser || {}), ...me};
    setSectorConfigV47(me);
    updatePremiumNavState();

    // Badge piano
    const badge = document.getElementById("planBadge");
    const planNames = {starter:"Starter",business:"Business",pro:"Pro"};
    if(badge){
      badge.textContent = planNames[plan] || plan;
      badge.className = "plan-badge-ui " + plan;
    }
    const planActiveBtn = document.getElementById("btnPlanActive");
    if(planActiveBtn){
      planActiveBtn.textContent = "Piano attivo";
      planActiveBtn.title = `Piano attuale: ${planNames[plan] || plan}. Apri per confrontare gli altri piani.`;
      planActiveBtn.setAttribute("aria-label", `Piano attivo: ${planNames[plan] || plan}. Visualizza gli altri piani disponibili`);
    }

    // Stato piano
    const statusBox = document.getElementById("planStatusBox");
    const statusIcon = document.getElementById("planStatusIcon");
    const statusLabel = document.getElementById("planStatusLabel");
    const statusDesc = document.getElementById("planStatusDesc");

    if(status === "trial"){
      const trialEnd = me.trial_ends_at ? new Date(me.trial_ends_at) : null;
      const daysLeft = trialEnd ? Math.max(0, Math.ceil((trialEnd - new Date()) / (1000*60*60*24))) : 0;
      if(statusBox) statusBox.style.background = daysLeft <= 3 ? "#fef3c7" : "#eff6ff";
      if(statusIcon) statusIcon.textContent = daysLeft <= 3 ? "⚠️" : "⏳";
      if(statusLabel) statusLabel.textContent = `Prova gratuita — ${daysLeft} giorni rimanenti`;
      if(statusDesc) statusDesc.textContent = `La tua prova scade il ${trialEnd ? trialEnd.toLocaleDateString("it-IT") : "—"}. Effettua l'upgrade per continuare senza interruzioni.`;
    } else if(status === "active"){
      if(statusBox) statusBox.style.background = "#d1fae5";
      if(statusIcon) statusIcon.textContent = "✅";
      if(statusLabel) statusLabel.textContent = `Piano ${planNames[plan]} attivo`;
      if(statusDesc) statusDesc.textContent = "Il tuo abbonamento è attivo. Grazie per usare GiroFacile!";
    } else if(status === "expired" || status === "cancelled"){
      if(statusBox) statusBox.style.background = "#fee2e2";
      if(statusIcon) statusIcon.textContent = "❌";
      if(statusLabel) statusLabel.textContent = "Piano scaduto";
      if(statusDesc) statusDesc.textContent = "Il tuo piano è scaduto. Effettua l'upgrade per riprendere ad usare GiroFacile.";
    }

    // Utilizzo risorse
    try{
      const [customers, vehicles, drivers, deposits] = await Promise.all([
        api("/api/customers?limit=1000"),
        api("/api/vehicles"),
        api("/api/drivers"),
        api("/api/deposits"),
      ]);
      const usageRows = document.getElementById("planUsageRows");
      if(usageRows){
        const rows = [
          {label:"Clienti", used: customers.length, max: limits.max_customers},
          {label:"Mezzi", used: vehicles.length, max: limits.max_vehicles},
          {label:"Autisti", used: drivers.length, max: limits.max_drivers},
          {label:"Depositi", used: deposits.length, max: limits.max_deposits},
        ];
        const icons = {Clienti:"👥", Mezzi:"🚚", Autisti:"👤", Depositi:"🏢"};
        usageRows.innerHTML = rows.map(r => {
          const maxLabel = r.max ? `${r.used} / ${r.max}` : `${r.used} / ∞`;
          return `<div class="plan-usage-chip-v40"><span class="plan-usage-chip-icon">${icons[r.label] || "•"}</span><span>${r.label}</span><strong>${maxLabel}</strong></div>`;
        }).join("");
      }
    }catch(e){}

    // Cards upgrade
    const upgradeBox = document.getElementById("planUpgradeBox");
    const planCards = document.getElementById("planCards");
    if(plan !== "pro" && planCards && upgradeBox){
      upgradeBox.style.display = "block";
      const allPlans = [
        {key:"starter",name:"Starter",price:"€19"},
        {key:"business",name:"Business",price:"€39"},
        {key:"pro",name:"Pro",price:"€79"},
      ];
      planCards.innerHTML = allPlans.map(p => `
        <div class="plan-card-mini ${p.key === plan ? "current" : ""}" onclick="selectUpgradePlan('${p.key}')">
          <div class="pname">${p.name}</div>
          <div class="pprice">${p.price}<span>/mese</span></div>
          ${p.key === plan ? '<div style="font-size:10px;color:#2563eb;margin-top:2px">Piano attuale</div>' : ""}
        </div>`).join("");
    }
  }catch(e){ console.error("loadPlanInfo:", e); }
}

function fmtEuroV63(value){
  const n = Number(value || 0);
  return n.toLocaleString("it-IT", {style:"currency", currency:"EUR"});
}
function fmtDateV63(value){
  if(!value) return "—";
  try{return new Date(value).toLocaleDateString("it-IT");}catch(e){return "—";}
}
function billingStatusLabelV63(status){
  const map = {paid:"Pagata", pending:"In attesa", overdue:"Scaduta", failed:"Fallita", refunded:"Rimborsata", cancelled:"Annullata", active:"Attivo", trial:"Prova gratuita", expired:"Scaduto"};
  return map[status] || status || "—";
}
let _billingReturnTabV876 = "plan-account";
async function openBillingPanel(){
  const current = getVisibleTabV874();
  if(current !== "billing-account") _billingReturnTabV876 = current || "plan-account";
  closeProfilePanel();
  document.getElementById("billingOverlay")?.classList.add("hidden");
  showTab("billing-account");
  await loadBillingOverviewV63();
  window.scrollTo({top:0, behavior:"smooth"});
}
function closeBillingPanel(){
  // Compatibilità con il vecchio flusso: la fatturazione ora è una pagina dedicata.
  if(getVisibleTabV874() === "billing-account") returnFromBillingPageV876();
}
function returnFromBillingPageV876(){
  const target = _billingReturnTabV876 === "billing-account" ? "plan-account" : (_billingReturnTabV876 || "plan-account");
  showTab(target);
}
function managePaymentMethodsV876(){
  toast("Gestione metodo di pagamento in preparazione: il collegamento sicuro al provider verrà attivato qui.");
}
async function loadBillingOverviewV63(){
  const loading = document.getElementById("billingLoadingV63");
  const content = document.getElementById("billingContentV63");
  if(loading) loading.classList.remove("hidden");
  if(content) content.classList.add("hidden");
  try{
    const data = await api("/api/billing/overview");
    const plan = data.plan || {};
    const company = data.company || {};
    const method = data.payment_method || {};
    const setText=(id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
    setText("billingPlanNameV63", plan.name || "—");
    setText("billingPlanStatusV63", billingStatusLabelV63(plan.status));
    setText("billingNextChargeV63", plan.next_charge_amount ? fmtEuroV63(plan.next_charge_amount) : "—");
    setText("billingNextChargeDateV63", plan.next_charge_at ? `Previsto il ${fmtDateV63(plan.next_charge_at)}` : "Nessun addebito programmato");
    const methodLabel = method.label || "Non configurato";
    setText("billingPaymentMethodV63", methodLabel);
    setText("billingMethodCardLabelV876", method.label || "Nessun metodo configurato");
    setText("billingMethodCardSubV876", method.details || (method.label ? "Metodo utilizzato per il rinnovo del piano." : "Aggiungi un metodo per i rinnovi automatici."));
    const hasMethod = !!method.label;
    const defBadge = document.getElementById("billingMethodDefaultV876");
    if(defBadge) defBadge.style.display = hasMethod ? "inline-flex" : "none";
    setText("billingPaymentStatusV876", plan.status === "overdue" || plan.status === "failed" ? "Da verificare" : "Regolare");
    setText("billingPaymentStatusHintV876", plan.status === "overdue" || plan.status === "failed" ? "Controlla il metodo di pagamento" : "Nessuna azione richiesta");
    set("billingCompanyNameV63", company.company_name || "");
    set("billingCompanyEmailV63", company.billing_email || company.company_email || "");
    set("billingCompanyVatV63", company.company_vat || "");
    set("billingCompanyFiscalCodeV63", company.company_fiscal_code || "");
    set("billingCompanyPecV63", company.company_pec || "");
    set("billingCompanySdiV63", company.company_sdi || "");
    set("billingCompanyLegalAddressV63", company.company_legal_address || "");
    set("billingCompanyBillingAddressV63", company.company_billing_address || "");
    renderBillingInvoicesV63(data.invoices || []);
    renderBillingPaymentsV63(data.payments || []);
    if(loading) loading.classList.add("hidden");
    if(content) content.classList.remove("hidden");
  }catch(e){
    if(loading) loading.innerHTML = `<div class="billing-empty-v63"><strong>Errore caricamento fatturazione</strong><span>${esc(e.message)}</span></div>`;
  }
}
function renderBillingInvoicesV63(invoices){
  const host=document.getElementById("billingInvoicesV63");
  if(!host) return;
  if(!invoices.length){
    host.innerHTML = `<div class="billing-empty-v63"><strong>Nessuna fattura emessa</strong><span>Le fatture compariranno qui quando saranno generati i primi addebiti del piano.</span></div>`;
    return;
  }
  host.innerHTML = invoices.map(inv => `
    <div class="billing-row-v63">
      <div>
        <strong>Fattura ${esc(inv.number || "—")}</strong>
        <span>${fmtDateV63(inv.date)} · Periodo ${fmtDateV63(inv.period_start)} - ${fmtDateV63(inv.period_end)}</span>
      </div>
      <div><b>${fmtEuroV63(inv.total)}</b><small class="billing-status-v63 ${esc(inv.status)}">${billingStatusLabelV63(inv.status)}</small></div>
      <button ${inv.pdf_available ? "" : "disabled"} onclick="${inv.pdf_available ? `window.open('/api/billing/invoices/${inv.id}/download','_blank')` : "toast('PDF fattura in preparazione')"}">Scarica PDF</button>
    </div>`).join("");
}
function renderBillingPaymentsV63(payments){
  const host=document.getElementById("billingPaymentsV63");
  if(!host) return;
  if(!payments.length){
    host.innerHTML = `<div class="billing-empty-v63"><strong>Nessun pagamento registrato</strong><span>I pagamenti appariranno qui quando verrà collegato il sistema di pagamento.</span></div>`;
    return;
  }
  host.innerHTML = payments.map(pay => `
    <div class="billing-row-v63 payment">
      <div>
        <strong>${billingStatusLabelV63(pay.status)}</strong>
        <span>${fmtDateV63(pay.paid_at || pay.created_at)} · ${esc(pay.method || "Metodo non indicato")}</span>
      </div>
      <div><b>${fmtEuroV63(pay.amount)}</b><small>${esc(pay.transaction_id || "")}</small></div>
    </div>`).join("");
}
async function saveBillingDetailsV63(){
  try{
    await api("/api/billing/billing-details", {method:"PUT", body:JSON.stringify({
      company_name: val("billingCompanyNameV63"),
      company_email: val("billingCompanyEmailV63"),
      company_vat: val("billingCompanyVatV63"),
      company_fiscal_code: val("billingCompanyFiscalCodeV63"),
      company_pec: val("billingCompanyPecV63"),
      company_sdi: val("billingCompanySdiV63"),
      company_legal_address: val("billingCompanyLegalAddressV63"),
      company_billing_address: val("billingCompanyBillingAddressV63"),
    })});
    toast("Dati fatturazione salvati");
    loadCompanyProfile?.();
  }catch(e){ alert(e.message); }
}



let _selectedUpgradePlan = null;
let _currentPlan = null;

const PLAN_FEATURES = {
  starter: {
    name:"Starter", price:"€19", period:"/mese",
    features:["30 clienti","5 giri al giorno","2 depositi","3 mezzi · 3 autisti","Interfaccia mobile"],
    missing:["Sezione agenti","Chat autisti","Report e analisi","Export CSV"]
  },
  business: {
    name:"Business", price:"€39", period:"/mese",
    features:["150 clienti","30 giri al giorno","10 depositi","20 mezzi · 20 autisti","Agenti commerciali","Report e analisi","Export CSV","Interfaccia mobile"],
    missing:[]
  },
  pro: {
    name:"Pro", price:"€79", period:"/mese",
    features:["Clienti illimitati","Giri illimitati","Depositi illimitati","Mezzi e autisti illimitati","Tutte le funzionalità Business","Supporto prioritario"],
    missing:[]
  }
};

let _planReturnTabV874 = "dashboard";
function getVisibleTabV874(){
  const el = Array.from(document.querySelectorAll(".tab")).find(x=>!x.classList.contains("hidden"));
  return el?.id?.replace(/^tab-/, "") || "dashboard";
}
function syncPlanPageHeaderV874(){
  const names = {starter:"Starter",business:"Business",pro:"Pro"};
  const name = names[_currentPlan] || (_currentPlan || "—");
  const badge = document.getElementById("planPageBadgeV874");
  const title = document.getElementById("planPageCurrentNameV874");
  const status = document.getElementById("planPageCurrentStatusV874");
  if(title) title.textContent = `Piano ${name}`;
  if(badge){ badge.textContent=name; badge.className=`plan-badge-ui ${_currentPlan||""}`; }
  if(status) status.textContent = "Gestisci il tuo abbonamento e confrontalo con gli altri piani disponibili.";
}
function openPlanAccountPage(plan){
  const current = getVisibleTabV874();
  if(current !== "plan-account") _planReturnTabV874 = current;
  closeProfilePanel();
  closeBillingPanel();
  _selectedUpgradePlan = plan || _currentPlan || "starter";
  showTab("plan-account");
  renderUpgradeCards();
  syncPlanPageHeaderV874();
  window.scrollTo({top:0, behavior:"smooth"});
}
function returnFromPlanAccount(){
  showTab(_planReturnTabV874 || "dashboard");
  setTimeout(()=>openProfilePanel(), 40);
}
function openUpgradePanel(){ openPlanAccountPage(); }
function openUpgradePanelFor(plan){ openPlanAccountPage(plan || "business"); }
function closeUpgradePanel(){ returnFromPlanAccount(); }
function renderUpgradeCards(){
  const plans = ["starter","business","pro"];
  const descriptions = {
    starter:"Per iniziare con le funzioni essenziali di pianificazione.",
    business:"Per aziende operative che gestiscono più risorse e consegne.",
    pro:"Per realtà strutturate che vogliono limiti estesi e priorità."
  };
  document.getElementById("upgradePlanCards").innerHTML = plans.map(p => {
    const f = PLAN_FEATURES[p];
    const isCurrent = p === _currentPlan;
    const isSelected = p === _selectedUpgradePlan;
    const preview = f.features.slice(0,4);
    return `<button type="button" class="up-card-v875 ${isCurrent?"current-plan":""} ${isSelected?"selected":""}" onclick="selectUpgradePlan('${p}')">
      <div class="up-card-top-v875">
        <div>
          <div class="up-name-v875">${f.name}</div>
          <div class="up-desc-v875">${descriptions[p]}</div>
        </div>
        ${isCurrent?'<span class="up-tag-v875">Piano attuale</span>':''}
      </div>
      <div class="up-price-v875">${f.price}<span>${f.period}</span></div>
      <div class="up-divider-v875"></div>
      <div class="up-preview-v875">${preview.map(x=>`<span><i>✓</i>${x}</span>`).join("")}</div>
      <span class="up-select-v875">${isCurrent?'Attivo':(isSelected?'Selezionato':'Seleziona piano')}</span>
    </button>`;
  }).join("");
  renderUpgradeFeatures(_selectedUpgradePlan || _currentPlan);
  renderPlanComparisonV875();
}
function selectUpgradePlan(plan){
  _selectedUpgradePlan = plan;
  renderUpgradeCards();
}
function renderUpgradeFeatures(plan){
  const f = PLAN_FEATURES[plan];
  if(!f) return;
  const box = document.getElementById("upgradeFeatures");
  const checkSvg = '<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>';
  const crossSvg = '<svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  box.innerHTML = `<div class="plan-features-head-v875"><div><span>PIANO SELEZIONATO</span><h3>${f.name}</h3></div><strong>${f.price}<small>${f.period}</small></strong></div>
    <div class="plan-feature-list-v875">
      ${f.features.map(x=>`<div class="up-feat-v875 yes">${checkSvg}<span>${x}</span></div>`).join("")}
      ${f.missing.map(x=>`<div class="up-feat-v875 no">${crossSvg}<span>${x}</span></div>`).join("")}
    </div>`;
}

function renderPlanComparisonV875(){
  const box = document.getElementById("planComparisonV875");
  if(!box) return;
  const rows = [
    ["Clienti","30","150","Illimitati"],
    ["Giri giornalieri","5","30","Illimitati"],
    ["Depositi","2","10","Illimitati"],
    ["Mezzi e autisti","3 + 3","20 + 20","Illimitati"],
    ["Agenti commerciali","—","Inclusi","Inclusi"],
    ["Report e analisi","—","Inclusi","Inclusi"],
    ["Export CSV","—","Incluso","Incluso"],
    ["Supporto prioritario","—","—","Incluso"]
  ];
  box.innerHTML = `<div class="plan-comparison-head-v875"><div><span>CONFRONTO COMPLETO</span><h2>Funzionalità incluse</h2></div><p>Una vista unica per confrontare rapidamente i tre livelli.</p></div>
  <div class="plan-table-wrap-v875"><table class="plan-table-v875"><thead><tr><th>Funzionalità</th><th>Starter</th><th>Business</th><th>Pro</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${r[3]}</td></tr>`).join("")}</tbody></table></div>`;
}
async function confirmUpgrade(){
  if(!_selectedUpgradePlan || _selectedUpgradePlan === _currentPlan){
    alert("Seleziona un piano diverso da quello attuale.");return;
  }
  const planNames = {starter:"Starter",business:"Business",pro:"Pro"};
  if(!confirm(`Attivare il piano ${planNames[_selectedUpgradePlan]}?`)) return;
  try{
    const btn = document.getElementById("btnConfirmUpgrade");
    btn.textContent = "Attivazione...";btn.disabled = true;
    // Chiama endpoint per cambiare piano (test mode — senza pagamento)
    const res = await api("/api/billing/select-plan", {method:"POST", body:JSON.stringify({plan:_selectedUpgradePlan})});
    toast(`Piano ${planNames[_selectedUpgradePlan]} attivato con successo!`);
    await loadPlanInfo();
    _selectedUpgradePlan = _currentPlan;
    renderUpgradeCards();
    syncPlanPageHeaderV874();
  }catch(e){
    alert(e.message);
    const btn = document.getElementById("btnConfirmUpgrade");
    btn.textContent = "Attiva piano selezionato";btn.disabled = false;
  }
}

async function loadAccountProfileV81(){
  try{
    const data = await api("/api/account-profile");
    set("profileName", data.username || "");
    set("profileEmail", data.email || "");
    set("profileRole", data.role || "Amministratore");
    localStorage.setItem("girofacile_profile_name", data.username || "Admin");
    localStorage.setItem("girofacile_profile_email", data.email || "");
    localStorage.setItem("girofacile_profile_role", data.role || "Amministratore");
    loadProfilePanel();
    return data;
  }catch(e){
    console.warn("loadAccountProfileV81", e);
    loadProfilePanel();
    return null;
  }
}

async function openProfilePanel(){
  await loadAccountProfileV81();
  loadPlanInfo();
  const el=document.getElementById("profileOverlay"); if(el) el.classList.remove("hidden");
}
function closeProfilePanel(ev){
  const el=document.getElementById("profileOverlay"); if(el) el.classList.add("hidden");
}
function previewProfilePhoto(event){
  const file = event.target.files && event.target.files[0];
  if(!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    profilePhotoData = reader.result;
    const preview = document.getElementById("profilePreview");
    if(preview) preview.innerHTML = `<img src="${profilePhotoData}" alt="Profilo">`;
  };
  reader.readAsDataURL(file);
}
async function saveProfilePanel(){
  try{
    const payload = {
      username: val("profileName") || "Admin",
      email: val("profileEmail"),
      new_password: val("profilePassword")
    };
    const res = await api("/api/account-profile", {method:"PUT", body:JSON.stringify(payload)});
    const account = res.account || payload;
    localStorage.setItem("girofacile_profile_name", account.username || "Admin");
    localStorage.setItem("girofacile_profile_email", account.email || "");
    localStorage.setItem("girofacile_profile_role", account.role || "Amministratore");
    if(profilePhotoData) localStorage.setItem("girofacile_profile_photo", profilePhotoData);
    set("profilePassword", "");
    currentSessionUser = {...(currentSessionUser || {}), username:account.username, email:account.email};
    loadProfilePanel();
    closeProfilePanel();
    toast("Profilo account aggiornato nel database");
  }catch(e){
    alert(e.message || "Errore salvataggio profilo account");
  }
}
function printStopsTable(){
  if(!lastRouteResult){ alert("Nessun risultato giro da stampare"); return; }
  const r = lastRouteResult;
  const consegne = r.consegne || [];
  const rows = consegne.map(d => `
    <tr>
      <td>${esc(d.ordine)}</td>
      <td>${esc(d.cliente_nome)}</td>
      <td>${esc(d.indirizzo)}</td>
      <td>${esc(d.arrivo_stimato || "-")}</td>
      <td>${esc(d.partenza_stimata || "-")}</td>
      <td>${Math.round(parseFloat(d.attesa_min)||0)} min</td>
      <td>${d.km_tappa ?? "-"}</td>
      <td>${esc(d.warning || "OK")}</td>
    </tr>`).join("");
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Stampa dettaglio fermate - GiroFacile</title>
  <style>
    body{font-family:Arial,Helvetica,sans-serif;margin:28px;color:#111827;font-size:13px;}
    h1{font-size:24px;margin:0 0 6px;} .meta{margin:0 0 16px;line-height:1.7;color:#374151;}
    table{width:100%;border-collapse:collapse;} th,td{border:1px solid #d1d5db;padding:8px;text-align:left;vertical-align:top;}
    th{background:#f3f4f6;font-size:12px;} td{font-size:12px;} .footer{margin-top:18px;color:#6b7280;font-size:11px;}
    @page{size:auto;margin:12mm;}
  </style></head><body>
    <h1>GiroFacile - Dettaglio fermate</h1>
    <div class="meta">
      <strong>Giro:</strong> ${esc(r.nome || val("routeName") || "Giro consegne")}<br>
      <strong>Data:</strong> ${esc(r.data_giro || val("routeDate") || "-")} · <strong>Partenza:</strong> ${esc(r.orario_partenza || "-")} · <strong>Rientro stimato:</strong> ${esc(r.orario_rientro_stimato || "-")}<br>
      <strong>Km totali:</strong> ${r.totale_km ?? "-"} km · <strong>Tempo totale:</strong> ${Math.round(r.totale_minuti || 0)} min · <strong>Costo carburante:</strong> € ${r.costo_carburante ?? "-"}
    </div>
    <table><thead><tr><th>Ordine</th><th>Cliente</th><th>Indirizzo</th><th>Arrivo</th><th>Ripartenza</th><th>Attesa</th><th>Km tappa</th><th>Avvisi</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="footer">Stampa generata da GiroFacile</div>
  </body></html>`;
  const w = window.open("", "_blank");
  if(!w){ alert("Consenti i popup per stampare il dettaglio fermate"); return; }
  w.document.open(); w.document.write(html); w.document.close();
  setTimeout(()=>{ w.focus(); w.print(); }, 300);
}

async function checkLogin(){
  return (async () => {
    const me = await api("/api/me");
    if(me.authenticated && me.role && me.role !== "admin"){
      window.location.href = me.redirect_url || (me.role === "driver" ? "/driver" : "/agent");
      return;
    }
    if(me.authenticated){
      currentSessionUser = me;
      setSectorConfigV47(me);
      showGestionaleAfterLogin(false);
      updatePremiumNavState();
      document.getElementById("logoutBtn").classList.remove("hidden");
      document.getElementById("notificationBellBtn")?.classList.remove("hidden");
      if(me.username) localStorage.setItem("girofacile_profile_name", me.company_name || me.username);
      if(me.email) localStorage.setItem("girofacile_profile_email", me.email);
      await initApp();
    }
  })();
}
function toggleSignup(show){
  const loginPanel = document.getElementById("loginPanel");
  const signupPanel = document.getElementById("signupPanel");
  const forgotBox = document.getElementById("forgotBox");
  if(loginPanel) loginPanel.style.display = show ? "none" : "";
  if(signupPanel) signupPanel.style.display = show ? "" : "none";
  if(show){
    fillSectorSelectV47("signupSector", val("signupSector"));
    setSignupWizardStep(1);
  }
  // Quando apro la registrazione nascondo il recupero password.
  // Quando torno al login, invece, non lo richiudo automaticamente: altrimenti
  // il click su “Password dimenticata?” apre e richiude subito il box.
  if(show && forgotBox) forgotBox.classList.add("hidden");
}
function toggleForgotPassword(show){
  const loginPanel = document.getElementById("loginPanel");
  const signupPanel = document.getElementById("signupPanel");
  const resetPanel = document.getElementById("resetPasswordPanel");
  const box = document.getElementById("forgotBox");
  if(signupPanel) signupPanel.style.display = "none";
  if(resetPanel) resetPanel.classList.add("hidden");
  if(loginPanel) loginPanel.style.display = "";
  if(box) box.classList.toggle("hidden", !show);
  if(show){
    setTimeout(() => document.getElementById("forgotEmail")?.focus(), 50);
  }
}

// Fix v25: gestione robusta click recupero password anche se l'onclick inline viene coperto/non agganciato
document.addEventListener("click", function(e){
  const forgotBtn = e.target.closest && e.target.closest("#forgotPasswordBtn");
  if(forgotBtn){
    e.preventDefault();
    e.stopPropagation();
    toggleForgotPassword(true);
    return;
  }
  const cancelBtn = e.target.closest && e.target.closest("#forgotPasswordCancelBtn");
  if(cancelBtn){
    e.preventDefault();
    e.stopPropagation();
    toggleForgotPassword(false);
    return;
  }
});

// Fix v26: espone le funzioni anche per onclick inline dopo login unico
window.toggleForgotPassword = toggleForgotPassword;
window.requestPasswordReset = requestPasswordReset;
window.login = login;
window.signup = signup;
window.signupWizardNext = signupWizardNext;
window.signupWizardBack = signupWizardBack;
window.setSignupWizardStep = setSignupWizardStep;
window.confirmPasswordReset = confirmPasswordReset;

function bindLoginRecoveryActions(){
  const forgotBtn = document.getElementById("forgotPasswordBtn");
  const cancelBtn = document.getElementById("forgotPasswordCancelBtn");
  const forgotSubmit = document.getElementById("forgotPasswordSubmitBtn") || document.querySelector("#forgotBox button");
  if(forgotBtn) forgotBtn.onclick = (e) => { e.preventDefault(); toggleForgotPassword(true); };
  if(cancelBtn) cancelBtn.onclick = (e) => { e.preventDefault(); toggleForgotPassword(false); };
  if(forgotSubmit) forgotSubmit.onclick = (e) => { e.preventDefault(); requestPasswordReset(); };
}

let signupWizardCurrentStep = 1;

function selectPlan(el){
  document.querySelectorAll(".plan-option").forEach(x => x.classList.remove("selected"));
  el.classList.add("selected");
}
function getSelectedPlan(){
  const select = document.getElementById("signupPlanSelect");
  if(select && select.value) return select.value;
  const sel = document.querySelector(".plan-option.selected");
  return sel ? sel.getAttribute("data-plan") : "business";
}
function signupBool(id){
  return !!document.getElementById(id)?.checked;
}
function setSignupWizardStep(step){
  signupWizardCurrentStep = Math.max(1, Math.min(4, Number(step) || 1));
  document.querySelectorAll("[data-signup-step]").forEach(panel => {
    panel.classList.toggle("hidden", Number(panel.getAttribute("data-signup-step")) !== signupWizardCurrentStep);
  });
  document.querySelectorAll("[data-signup-step-dot]").forEach(dot => {
    const n = Number(dot.getAttribute("data-signup-step-dot"));
    dot.classList.toggle("active", n === signupWizardCurrentStep);
    dot.classList.toggle("done", n < signupWizardCurrentStep);
  });
  const back = document.getElementById("signupBackBtn");
  const next = document.getElementById("signupNextBtn");
  const create = document.getElementById("signupCreateBtn");
  if(back) back.disabled = signupWizardCurrentStep === 1;
  if(next) next.classList.toggle("hidden", signupWizardCurrentStep === 4);
  if(create) create.classList.toggle("hidden", signupWizardCurrentStep !== 4);
}
function validateSignupStep(step){
  if(step === 1){
    if(!val("signupCompany")){ alert("Inserisci il nome azienda."); return false; }
    if(!val("signupUser") || val("signupUser").length < 3){ alert("Inserisci un nome utente di almeno 3 caratteri."); return false; }
    if(!val("signupEmail")){ alert("Inserisci l'email dell'account."); return false; }
    if(!val("signupPass") || val("signupPass").length < 6){ alert("La password deve contenere almeno 6 caratteri."); return false; }
  }
  if(step === 2){
    if(!val("signupVat")){
      const ok = confirm("Non hai inserito la Partita IVA. Vuoi continuare comunque?");
      if(!ok) return false;
    }
  }

  return true;
}
function signupWizardNext(){
  if(!validateSignupStep(signupWizardCurrentStep)) return;
  setSignupWizardStep(signupWizardCurrentStep + 1);
}
function signupWizardBack(){
  setSignupWizardStep(signupWizardCurrentStep - 1);
}
async function requestPasswordReset(){
  try{
    const email = val("forgotEmail");
    const res = await api("/api/password-reset/request", {method:"POST", body:JSON.stringify({email})});
    toast(res.message || "Se l'email è associata a un account GiroFacile, riceverai un link per reimpostare la password.");
    toggleForgotPassword(false);
    set("forgotEmail", "");
  }catch(e){ alert(e.message); }
}

function resetTokenFromPath(){
  const m = window.location.pathname.match(/^\/reset-password\/([^/]+)$/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function showResetPasswordPanel(){
  const loginPanel = document.getElementById("loginPanel");
  const signupPanel = document.getElementById("signupPanel");
  const resetPanel = document.getElementById("resetPasswordPanel");
  const app = document.getElementById("app");
  const loginCard = document.getElementById("loginCard");
  if(app){ app.classList.add("hidden"); app.style.display="none"; }
  if(loginCard){ loginCard.classList.remove("hidden"); loginCard.style.display="grid"; }
  if(loginPanel) loginPanel.style.display = "none";
  if(signupPanel) signupPanel.style.display = "none";
  if(resetPanel) resetPanel.classList.remove("hidden");
  const token = resetTokenFromPath();
  try{
    const info = await api(`/api/password-reset/${encodeURIComponent(token)}`);
    const help = document.getElementById("resetPasswordHelp");
    if(help) help.textContent = `Stai reimpostando la password per ${info.email || "il tuo account"}.`;
  }catch(e){
    const help = document.getElementById("resetPasswordHelp");
    if(help) help.textContent = "Link non valido o scaduto. Richiedi un nuovo recupero password.";
    const btn = document.querySelector("#resetPasswordPanel .login-submit");
    if(btn) btn.disabled = true;
  }
}

async function confirmPasswordReset(){
  try{
    const token = resetTokenFromPath();
    const password = val("resetPassword1");
    const password2 = val("resetPassword2");
    if(password.length < 6){ alert("La password deve contenere almeno 6 caratteri"); return; }
    if(password !== password2){ alert("Le password non coincidono"); return; }
    const res = await api("/api/password-reset/confirm", {method:"POST", body:JSON.stringify({token, password})});
    toast(res.message || "Password aggiornata correttamente.");
    setTimeout(()=>{ window.location.href = "/login"; }, 900);
  }catch(e){ alert(e.message); }
}
async function signup(){
  try{
    if(!validateSignupStep(1) || !validateSignupStep(4)) return;
    const plan = getSelectedPlan();
    const createBtn = document.getElementById("signupCreateBtn");
    if(createBtn){ createBtn.disabled = true; createBtn.textContent = "Creazione account..."; }
    await api("/api/signup", {method:"POST", body:JSON.stringify({
      company_name: val("signupCompany"),
      username: val("signupUser"),
      email: val("signupEmail"),
      password: val("signupPass"),
      plan: plan,
      company_phone: val("signupPhone") || val("signupCompanyPhone"),
      company_vat: val("signupVat"),
      company_fiscal_code: val("signupFiscalCode"),
      company_pec: val("signupPec"),
      company_sdi: val("signupSdi"),
      company_address: val("signupAddress"),
      company_city: val("signupCity"),
      company_zip: val("signupZip"),
      company_country: val("signupCountry") || "Italia",
      company_legal_address: val("signupLegalAddress") || val("signupAddress"),
      company_billing_address: val("signupBillingAddress") || val("signupLegalAddress") || val("signupAddress"),
      company_sector: "distribution",
      company_activity_type: val("signupActivityType"),
      company_size: val("signupCompanySize"),
      daily_deliveries: val("signupDailyDeliveries"),
      has_time_windows: signupBool("signupHasTimeWindows"),
      needs_signature: signupBool("signupNeedsSignature"),
      needs_photo_proof: signupBool("signupNeedsPhotoProof"),
      has_refrigerated_goods: signupBool("signupRefrigerated"),
      has_ztl: signupBool("signupZtl"),
      needs_tail_lift: signupBool("signupTailLift")
    })});
    toggleSignup(false);
    await checkLogin();
    toast("Benvenuto in GiroFacile! Azienda configurata e prova gratuita avviata.");
  }catch(e){ alert(e.message); }
  finally{
    const createBtn = document.getElementById("signupCreateBtn");
    if(createBtn){ createBtn.disabled = false; createBtn.textContent = "Crea account gratuito →"; }
  }
}
async function login(){
  try{
    const res = await api("/api/login", {method:"POST", body:JSON.stringify({username:val("loginUser"), password:val("loginPass")} )});
    if(res.redirect_url && res.redirect_url !== "/dashboard"){
      window.location.href = res.redirect_url;
      return;
    }
    await checkLogin();
  }catch(e){ alert(e.message); }
}
document.getElementById("logoutBtn").onclick = async () => { await api("/api/logout", {method:"POST", body:"{}"}); location.reload(); };



async function initApp(){
  const routeDateInput = document.getElementById("routeDate");
  if(routeDateInput){
    const today = todayIso();
    routeDateInput.min = today;
    if(!routeDateInput.value || routeDateInput.value < today) routeDateInput.value = today;
  }
  document.getElementById("fuelPrice")?.addEventListener("input", updateDashboardStats);
  initRoutePlanningGateV68();
  await loadSettingsV41();
  await loadUniversalFeaturesV89();
  loadProfilePanel();
  initAddressAutocomplete();
  initResourceAvailabilityControls();
  await loadDeposits(); await loadVehicles(); await loadDrivers();
  if(agentsFeatureEnabled()) await loadAgents();
  await loadCustomers(); await loadCustomerPicker();
  await refreshResourceAvailability();
  await loadDashboardRoutes();
  await loadDashboardHome();
  await loadCompanyProfile(false);
  await loadOnboardingStatus(true);
  await loadNotificationsV30(false);
  if(notificationsPollV30) clearInterval(notificationsPollV30);
  notificationsPollV30 = setInterval(()=>loadNotificationsV30(false), 60000);
  updateDashboardStats();
}




let resourcesAvailabilityCache = {vehicles:[], drivers:[]};

function setAvailabilityHint(id, text, state="muted"){
  const el = document.getElementById(id);
  if(!el) return;
  el.textContent = text || "";
  el.className = `availability-hint ${state}`;
}

function resourcesDateTimeReady(){
  return !!(val("routeDate") && val("routeStart"));
}

function routeDateIsValid(){
  const d = val("routeDate");
  const today = todayIso();
  return !!d && d >= today;
}

function enforceRouteDateMin(){
  const el = document.getElementById("routeDate");
  if(!el) return true;
  const today = todayIso();
  el.min = today;
  if(el.value && el.value < today){
    el.value = today;
    toast("Non puoi programmare un giro in una data precedente a oggi.");
    return false;
  }
  return true;
}

function renderResourceSelects(){
  const vehicleSel = document.getElementById("routeVehicle");
  const driverSel = document.getElementById("routeDriver");
  const ready = resourcesDateTimeReady();
  const selectedVehicle = vehicleSel ? String(vehicleSel.value || "") : "";
  const selectedDriver = driverSel ? String(driverSel.value || "") : "";

  if(vehicleSel){
    vehicleSel.disabled = !ready;
    if(!ready){
      vehicleSel.innerHTML = `<option value="">Seleziona prima l'orario</option>`;
      setAvailabilityHint("vehicleAvailabilityHint", "Seleziona prima data e orario di partenza", "muted");
    }else{
      vehicleSel.innerHTML = `<option value="">Nessun mezzo</option>`;
      const rows = resourcesAvailabilityCache.vehicles?.length ? resourcesAvailabilityCache.vehicles : vehiclesCache.map(v=>({...v, available:true, status:"Disponibile"}));
      rows.forEach(v=>{
        const icon = v.available ? "✅" : "🔴";
        const label = `${icon} ${v.nome || "Mezzo"}${v.targa ? " · " + v.targa : ""} · ${v.status || (v.available ? "Disponibile" : "In uso")}`;
        const isSelected = String(v.id) === selectedVehicle;
        vehicleSel.innerHTML += `<option value="${v.id}" ${v.available || isSelected ? "" : "disabled"} ${isSelected ? "selected" : ""}>${esc(label)}</option>`;
      });
      if(selectedVehicle && !vehicleSel.value) vehicleSel.value = selectedVehicle;
      const busy = rows.filter(v=>!v.available).length;
      setAvailabilityHint("vehicleAvailabilityHint", busy ? `${busy} mezzo/i non disponibili nell'orario selezionato` : "Tutti i mezzi risultano disponibili", busy ? "warn" : "ok");
    }
    // V89.5.1: sincronizza sempre il pannello energia con il mezzo selezionato,
    // anche dopo il refresh delle disponibilità che ricostruisce il <select>.
    updateRouteEnergyPricingV895();
  }

  if(driverSel){
    driverSel.disabled = !ready;
    if(!ready){
      driverSel.innerHTML = `<option value="">Seleziona prima l'orario</option>`;
      setAvailabilityHint("driverAvailabilityHint", "Seleziona prima data e orario di partenza", "muted");
    }else{
      driverSel.innerHTML = `<option value="">Nessun autista assegnato</option>`;
      const rows = resourcesAvailabilityCache.drivers?.length ? resourcesAvailabilityCache.drivers : driversCache.map(d=>({...d, full_name: driverFullName(d), available:true, status:"Disponibile"}));
      rows.forEach(d=>{
        const icon = d.available ? "✅" : "🔴";
        const name = d.full_name || driverFullName(d);
        const label = `${icon} ${name}${d.patente ? " · " + d.patente : ""} · ${d.status || (d.available ? "Disponibile" : "In servizio")}`;
        const isSelected = String(d.id) === selectedDriver;
        driverSel.innerHTML += `<option value="${d.id}" ${d.available || isSelected ? "" : "disabled"} ${isSelected ? "selected" : ""}>${esc(label)}</option>`;
      });
      if(selectedDriver && !driverSel.value) driverSel.value = selectedDriver;
      const busy = rows.filter(d=>!d.available).length;
      setAvailabilityHint("driverAvailabilityHint", busy ? `${busy} autista/i non disponibili nell'orario selezionato` : "Tutti gli autisti risultano disponibili", busy ? "warn" : "ok");
    }
  }
}

async function refreshResourceAvailability(){
  const vehicleSel = document.getElementById("routeVehicle");
  const driverSel = document.getElementById("routeDriver");

  enforceRouteDateMin();

  if(!resourcesDateTimeReady()){
    resourcesAvailabilityCache = {vehicles:[], drivers:[]};
    renderResourceSelects();
    return;
  }

  if(vehicleSel) vehicleSel.disabled = true;
  if(driverSel) driverSel.disabled = true;
  setAvailabilityHint("vehicleAvailabilityHint", "Controllo disponibilità mezzi...", "muted");
  setAvailabilityHint("driverAvailabilityHint", "Controllo disponibilità autisti...", "muted");

  try{
    resourcesAvailabilityCache = await api(`/api/resources/availability?data_giro=${encodeURIComponent(val("routeDate"))}&orario=${encodeURIComponent(val("routeStart"))}`);
  }catch(e){
    resourcesAvailabilityCache = {vehicles: vehiclesCache.map(v=>({...v, available:true, status:"Disponibile"})), drivers: driversCache.map(d=>({...d, full_name: driverFullName(d), available:true, status:"Disponibile"}))};
    setAvailabilityHint("vehicleAvailabilityHint", "Disponibilità non verificata", "warn");
    setAvailabilityHint("driverAvailabilityHint", "Disponibilità non verificata", "warn");
  }
  renderResourceSelects();
  updateRoutePlanningGateV68();
}

function initResourceAvailabilityControls(){
  const dateEl = document.getElementById("routeDate");
  const startEl = document.getElementById("routeStart");
  dateEl?.addEventListener("change", refreshResourceAvailability);
  startEl?.addEventListener("change", refreshResourceAvailability);
  renderResourceSelects();
}




/* v68 - Pianificazione guidata: prima dettagli giro, poi inserimento clienti */
let customerPlanningStepOpenedV68 = false;

function routePlanningMissingFieldsV68(){
  const missing = [];
  if(!val("routeDate") || !routeDateIsValid()) missing.push("data");
  if(!val("routeStart")) missing.push("orario partenza");
  if(!val("routeDeposit")) missing.push("deposito");
  if(!val("routeVehicle")) missing.push("mezzo");
  if(!val("routeDriver")) missing.push("autista");
  const vehicle = vehiclesCache.find(v=>String(v.id)===String(val("routeVehicle")));
  const fuelType = vehicle?.alimentazione || "gasolio";
  const fuel = parseFloat(val("fuelPrice") || "0");
  const electricity = parseFloat(val("electricityPrice") || "0");
  if(fuelType !== "elettrico" && (!fuel || fuel <= 0)) missing.push("prezzo carburante");
  if(["elettrico","ibrido_plugin_benzina","ibrido_plugin_diesel"].includes(fuelType) && (!electricity || electricity <= 0)) missing.push("prezzo energia");
  return missing;
}

function routePlanningDetailsCompleteV68(){
  return routePlanningMissingFieldsV68().length === 0;
}

function updateRoutePlanningGateV68(){
  const btn = document.getElementById("openCustomerStepBtn");
  const hint = document.getElementById("routePlanningGateHint");
  const picker = document.getElementById("customerPlanningStep");
  const workbench = document.getElementById("deliveryWorkbenchStep");
  const missing = routePlanningMissingFieldsV68();
  const ready = missing.length === 0;
  if(btn){
    btn.disabled = !ready;
    btn.textContent = ready ? (customerPlanningStepOpenedV68 ? "Clienti aperti" : "Inserisci clienti") : "Completa dati giro";
  }
  if(hint){
    hint.textContent = ready ? "Dati giro completi: puoi selezionare i clienti e preparare il percorso." : `Campi mancanti: ${missing.join(", ")}.`;
    hint.className = `route-gate-hint ${ready ? "ok" : "warn"}`;
  }
  if(!ready){
    customerPlanningStepOpenedV68 = false;
    picker?.classList.add("hidden");
    workbench?.classList.add("hidden");
  }else if(customerPlanningStepOpenedV68){
    picker?.classList.remove("hidden");
    workbench?.classList.remove("hidden");
  }
}

function openCustomerPlanningStep(){
  if(!routePlanningDetailsCompleteV68()){
    updateRoutePlanningGateV68();
    alert("Completa prima tutti i dati del giro: data, orario, deposito, mezzo, autista e prezzo carburante.");
    return;
  }
  customerPlanningStepOpenedV68 = true;
  updateRoutePlanningGateV68();
  loadCustomerPicker();
  document.getElementById("customerPlanningStep")?.scrollIntoView({behavior:"smooth", block:"start"});
}

function closeCustomerPlanningStep(){
  customerPlanningStepOpenedV68 = false;
  document.getElementById("customerPlanningStep")?.classList.add("hidden");
  document.getElementById("deliveryWorkbenchStep")?.classList.add("hidden");
  updateRoutePlanningGateV68();
}

function initRoutePlanningGateV68(){
  ["routeName","routeDate","routeStart","routeDeposit","routeVehicle","routeDriver","fuelPrice","electricityPrice","returnDepot"].forEach(id=>{
    const el = document.getElementById(id);
    if(!el || el.dataset.gfGateBound === "1") return;
    el.dataset.gfGateBound = "1";
    el.addEventListener("input", updateRoutePlanningGateV68);
    el.addEventListener("change", updateRoutePlanningGateV68);
    if(id === "routeVehicle"){
      el.addEventListener("change", updateRouteEnergyPricingV895);
    }
  });
  updateRoutePlanningGateV68();
  updateRouteEnergyPricingV895();
}

function fmtEuro(v){ return "€ " + (Number(v||0)).toFixed(1).replace(".", ","); }
function fmtKm(v){ return (Number(v||0)).toFixed(1).replace(".", ",") + " km"; }
function todayIso(){
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth()+1).padStart(2,"0");
  const day = String(d.getDate()).padStart(2,"0");
  return `${y}-${m}-${day}`;
}
function routeProgressPercent(r){
  const fromDriver = Number(r.progress_percent || 0);
  if(fromDriver > 0) return Math.max(0, Math.min(100, fromDriver));
  try{
    if(r.status !== "in_corso") return 0;
    const now = new Date();
    const [sh,sm] = String(r.orario_partenza||"00:00").split(":").map(Number);
    const [eh,em] = String(r.orario_rientro_stimato||r.orario_partenza||"00:00").split(":").map(Number);
    const start = sh*60+(sm||0), end = eh*60+(em||0), cur = now.getHours()*60+now.getMinutes();
    if(end <= start) return 40;
    return Math.max(8, Math.min(95, Math.round(((cur-start)/(end-start))*100)));
  }catch(e){ return 0; }
}

function renderEmptyDashList(text){ return `<div class="dash-empty">${esc(text)}</div>`; }
function renderDashTrend(routes){
  const el = document.getElementById("dashTrendChart");
  if(!el) return;
  const days=[];
  const now = new Date();
  for(let i=6;i>=0;i--){ const d=new Date(now); d.setDate(now.getDate()-i); days.push(d.toISOString().slice(0,10)); }
  const values = days.map(day => routes.filter(r=>r.data_giro===day).reduce((a,r)=>a+(Number(r.consegne_count)||0),0));
  const max = Math.max(1, ...values);
  const points = values.map((v,i)=>{
    const x = 28 + i*(420/6);
    const y = 130 - (v/max)*95;
    return `${x},${y}`;
  }).join(" ");
  const area = `28,145 ${points} 448,145`;
  const labels = days.map((d,i)=>`<text x="${28+i*(420/6)}" y="168" text-anchor="middle">${d.slice(5)}</text>`).join("");
  const dots = values.map((v,i)=>{ const x=28+i*(420/6); const y=130-(v/max)*95; return `<circle cx="${x}" cy="${y}" r="4"><title>${days[i]} - ${v} consegne</title></circle>`; }).join("");
  el.innerHTML = `<svg viewBox="0 0 480 180" class="dash-svg-chart" role="img" aria-label="Andamento consegne ultimi 7 giorni">
    <defs><linearGradient id="dashAreaGrad" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#0b63f6" stop-opacity="0.24"/><stop offset="100%" stop-color="#0b63f6" stop-opacity="0.02"/></linearGradient></defs>
    <g class="grid"><line x1="28" y1="35" x2="448" y2="35"/><line x1="28" y1="70" x2="448" y2="70"/><line x1="28" y1="105" x2="448" y2="105"/><line x1="28" y1="145" x2="448" y2="145"/></g>
    <polygon points="${area}" fill="url(#dashAreaGrad)"></polygon>
    <polyline points="${points}" fill="none" stroke="#0b63f6" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></polyline>
    <g class="dots">${dots}</g>
    <g class="labels">${labels}</g>
  </svg>`;
}
async function loadDashboardHome(){
  const dash = document.getElementById("tab-dashboard");
  if(!dash) return;
  try{
    const [routes, operational, vehicles, drivers] = await Promise.all([api("/api/routes"), api("/api/routes/operativi"), api("/api/vehicles"), api("/api/drivers")]);
    const today = todayIso();
    const todayScheduled = operational.filter(r=>r.status==='programmato' && r.data_giro===today);
    const inProgressRoutes = operational.filter(r=>r.status==='in_corso');
    const completedToday = routes.filter(r=>r.status==='completato' && r.data_giro===today);

    // Le consegne completate oggi sono le fermate dei giri completati oggi.
    // Non si usano più i vecchi totali generici, così il dato è chiaro e operativo.
    const completedDeliveriesToday = completedToday.reduce((a,r)=>a+(Number(r.consegne_count)||0),0);
    const busyDrivers = drivers.filter(d=>(d.stato || "Disponibile")==="In servizio").length;
    const busyVehicles = vehicles.filter(v=>(v.stato || "Disponibile")==="In uso").length;

    const setText = (id,val)=>{ const x=document.getElementById(id); if(x) x.textContent=val; };
    setText("dashTodayScheduled", todayScheduled.length);
    // Deve combaciare con il pannello “Giri in corso” sotto: conta tutti i giri operativi attualmente in corso.
    setText("dashTodayProgress", inProgressRoutes.length);
    setText("dashTodayCompletedDeliveries", completedDeliveriesToday);
    setText("dashTodayBusyResources", `${busyDrivers}/${drivers.length} · ${busyVehicles}/${vehicles.length}`);
    setText("dashTodayBusyResourcesSub", "autisti · mezzi impegnati");

    // Dashboard semplificata: grafici e attività recenti rimossi per ridurre confusione.

    const scheduled = operational.filter(r=>r.status==='programmato');
    const progress = inProgressRoutes;
    setText("dashScheduledBadge", scheduled.length);
    setText("dashInProgressBadge", progress.length);
    setText("dashCompletedBadge", completedToday.length);
    const scheduledBox=document.getElementById("dashScheduledList");
    const progressBox=document.getElementById("dashProgressList");
    const completedBox=document.getElementById("dashCompletedList");
    renderLogisticsDashboardV50([...(operational || []), ...(routes || [])]);
    if(scheduledBox) scheduledBox.innerHTML = scheduled.slice(0,3).map(r=>dashRouteItem(r,'scheduled')).join("") || renderEmptyDashList("Nessun giro programmato.");
    if(progressBox) progressBox.innerHTML = progress.slice(0,3).map(r=>dashRouteItem(r,'progress')).join("") || renderEmptyDashList("Nessun giro in corso.");
    if(completedBox) completedBox.innerHTML = completedToday.slice(0,3).map(r=>dashRouteItem(r,'completed')).join("") || renderEmptyDashList("Nessun giro completato oggi.");

    const vehBox = document.getElementById("dashVehicleStatus");
    if(vehBox){
      vehBox.innerHTML = vehicles.slice(0,4).map(v=>{
        const inUse = (v.stato || "Disponibile") === "In uso";
        return `<div class="dash-vehicle-card"><div><span class="vehicle-dot ${inUse?'busy':'free'}"></span><strong>${esc(v.nome||'Mezzo')}</strong><small>${esc(v.targa||'')}</small><small>${esc(v.stato || (inUse?'In uso':'Disponibile'))}</small></div>${imageThumb(v.photo_url,'🚚','vehicle-thumb')}</div>`;
      }).join("") || renderEmptyDashList("Nessun mezzo registrato.");
    }

    const driverBox = document.getElementById("dashDriverStatus");
    if(driverBox){
      driverBox.innerHTML = drivers.slice(0,4).map(d=>{
        const busy = (d.stato || "Disponibile") === "In servizio";
        const name = `${d.nome||""} ${d.cognome||""}`.trim() || "Autista";
        return `<div class="dash-vehicle-card dash-driver-card"><div><span class="vehicle-dot ${busy?'busy':'free'}"></span><strong>${esc(name)}</strong><small>${esc(d.patente||'')}</small><small>${esc(d.stato || "Disponibile")}</small></div>${imageThumb(d.photo_url,'👤','driver-thumb')}</div>`;
      }).join("") || renderEmptyDashList("Nessun autista registrato.");
    }
  }catch(e){ console.warn(e); }
}

function routeStatusBadge(status, label){
  const s = status || "programmato";
  const text = label || ({bozza:"Bozza", programmato:"Programmato", in_corso:"In corso", da_completare:"Da completare", completato:"Completato", annullato:"Annullato"}[s] || "Programmato");
  return `<span class="route-status-pill ${s}">${esc(text)}</span>`;
}

async function loadDashboardRoutes(){
  const body = document.getElementById("dashboardRoutesBody");
  if(!body) return;
  try{
    const rows = await api("/api/routes/operativi");
    const counts = {programmato:0, in_corso:0, da_completare:0};
    rows.forEach(r => { if(counts[r.status] !== undefined) counts[r.status]++; });
    const setText = (id,val)=>{ const el=document.getElementById(id); if(el) el.textContent=val; };
    setText("dashScheduledCount", counts.programmato);
    setText("dashInProgressCount", counts.in_corso);
    setText("dashToCompleteCount", counts.da_completare);

    if(!rows.length){
      body.innerHTML = `<tr><td colspan="9"><div class="empty-state-small">Nessun giro programmato o in corso al momento.</div></td></tr>`;
      return;
    }

    body.innerHTML = rows.map(r => `
      <tr class="operational-route-row">
        <td><strong>${esc(r.nome || "Giro consegne")}</strong></td>
        <td>${esc(r.data_giro || "-")}</td>
        <td>${esc(r.orario_partenza || "-")} → ${esc(r.orario_rientro_stimato || "-")}</td>
        <td>${esc(r.driver_name || "-")}</td>
        <td>${esc(r.vehicle_name || "-")}</td>
        <td>${r.consegne_count || 0}</td>
        <td>${r.totale_km ?? "-"}</td>
        <td>${routeStatusBadge(r.status, r.status_label)}</td>
        <td class="row-actions compact">
          <button onclick="openDashboardRoute(${r.id})">Dettaglio</button>
        </td>
      </tr>
    `).join("");
  }catch(e){
    body.innerHTML = `<tr><td colspan="9"><div class="resultBox warn">Errore caricamento giri: ${esc(e.message)}</div></td></tr>`;
  }
}


function deliveryStatusPill(status){
  const s = status || "in_attesa";
  const label = {in_attesa:"Da fare", completata:"Completata", mancata:"Mancata"}[s] || "Da fare";
  return `<span class="delivery-status-pill ${esc(s)}">${esc(label)}</span>`;
}

function signatureDateLabel(value){
  if(!value) return '';
  try{
    const d = new Date(value);
    if(Number.isNaN(d.getTime())) return value;
    return d.toLocaleString('it-IT', {day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'});
  }catch(e){ return value; }
}
function deliverySignatureAction(d, driverName=''){
  if(!d || !d.signature_data) return '';
  const payload = encodeURIComponent(JSON.stringify({
    data:d.signature_data,
    name:d.signed_by_name || '',
    signedAt:d.signed_at || '',
    note:d.signature_note || '',
    driver:driverName || d.driver_name || ''
  }));
  return `<button type="button" class="btn-mini signature-mini-btn" onclick="openDeliverySignature('${payload}')">✍️ Firma</button>`;
}
function openDeliverySignature(payload){
  let info = {};
  try{ info = JSON.parse(decodeURIComponent(payload || '{}')); }catch(e){ info = {data:decodeURIComponent(payload || '')}; }
  const decoded = info.data || '';
  const name = esc(info.name || '');
  const signedAt = esc(signatureDateLabel(info.signedAt || ''));
  const note = esc(info.note || '');
  const driver = esc(info.driver || '');
  const html = `<div class="signature-viewer-overlay" onclick="this.remove()">
    <div class="signature-viewer-card" onclick="event.stopPropagation()">
      <div class="signature-viewer-head"><h3>Firma consegna</h3><button type="button" onclick="document.querySelector('.signature-viewer-overlay')?.remove()">×</button></div>
      <div class="signature-viewer-meta signature-viewer-meta-grid">
        <div><span>Firmatario</span><strong>${name || 'Non indicato'}</strong></div>
        <div><span>Orario firma</span><strong>${signedAt || '-'}</strong></div>
        <div><span>Autista</span><strong>${driver || '-'}</strong></div>
      </div>
      <div class="signature-viewer-img"><img src="${decoded}" alt="Firma cliente"></div>
      ${note?`<div class="signature-viewer-note"><strong>Nota firma</strong><br>${note}</div>`:''}
    </div>
  </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}
function dashboardStopRows(r){
  const rows = r.consegne || [];
  if(!rows.length){
    return `<div class="dash-detail-empty small">Nessuna fermata salvata per questo giro.</div>`;
  }
  return `<div class="tableWrap dash-detail-stops-wrap">
    <table class="result-table dash-detail-stops">
      <thead>
        <tr><th>#</th><th>Cliente</th><th>Indirizzo</th><th>Arrivo</th><th>Stato</th><th>Note autista</th></tr>
      </thead>
      <tbody>
        ${rows.map(d=>`
          <tr class="delivery-row-${esc(d.delivery_status||'in_attesa')}">
            <td><strong>${d.ordine || ""}</strong></td>
            <td><strong>${esc(d.cliente_nome || "-")}</strong></td>
            <td>${esc(d.indirizzo || "-")}</td>
            <td>${esc(d.arrivo_stimato || "-")}</td>
            <td>${deliveryStatusPill(d.delivery_status)}${d.motivo_mancata?`<small class="delivery-reason">${esc(d.motivo_mancata)}</small>`:""}</td>
            <td>${d.note_operatore?esc(d.note_operatore):warningBadges(d.warning)} ${deliverySignatureAction(d, r.driver_name)}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  </div>`;
}

function dashboardDetailActions(r){
  const status = r.status || "programmato";
  const mapsBtn = r.google_maps_url ? `<a target="_blank" href="${esc(r.google_maps_url)}"><button class="btn-primary">Apri Google Maps</button></a>` : "";
  if(status === "programmato" || status === "bozza"){
    return `
      ${mapsBtn}
      <button class="btn-secondary" onclick="openProgrammedRouteForEdit(${r.id})">Modifica completa</button>
      <button class="btn-danger-soft" onclick="cancelDashboardRoute(${r.id})">Annulla giro</button>
    `;
  }
  if(status === "in_corso" || status === "da_completare"){
    return `
      ${mapsBtn}
      <button class="btn-secondary" onclick="loadDashboardRouteChat(${r.id}, true)">Apri chat autista</button>
      <button class="btn-danger-soft" onclick="cancelDashboardRoute(${r.id})">Annulla giro</button>
    `;
  }
  return `
    ${mapsBtn}
    <button class="btn-secondary" onclick="showTab('storico')">Vai allo storico</button>
  `;
}

function renderDashboardRouteDetail(r){
  const panel = document.getElementById("dashboardRouteDetailPanel");
  if(!panel) return;
  panel.classList.remove("hidden");
  const status = r.status || "programmato";
  const rows = r.consegne || [];
  const completed = rows.filter(x=>x.delivery_status === 'completata').length;
  const missed = rows.filter(x=>x.delivery_status === 'mancata').length;
  const pending = Math.max(rows.length - completed - missed, 0);
  const perc = rows.length ? Math.round(((completed + missed) / rows.length) * 100) : 0;
  const editableNote = status === "programmato" || status === "bozza"
    ? "Questo giro è programmato: puoi modificarlo prima dell'avvio da parte dell'autista."
    : status === "in_corso"
      ? "Questo è il controllo operativo del giro: segui avanzamento, fermate e chat con l'autista."
      : "Dettaglio consultabile dalla Dashboard.";

  panel.innerHTML = `
    <div class="dash-detail-header">
      <div>
        <div class="dash-detail-eyebrow">Controllo giro</div>
        <h2>${esc(r.nome || "Giro consegne")}</h2>
        <p>${esc(editableNote)}</p>
      </div>
      <div class="dash-detail-header-actions">
        ${routeStatusBadge(r.status, r.status_label)}
        <button class="btn-light" onclick="closeDashboardRouteDetail()">Chiudi</button>
      </div>
    </div>

    <div class="dash-detail-kpis dash-detail-kpis-operative">
      <div><span>Autista</span><strong>${esc(r.driver_name || "Non assegnato")}</strong></div>
      <div><span>Mezzo</span><strong>${esc(r.vehicle_name || "-")}</strong></div>
      <div><span>Completate</span><strong>${completed}/${rows.length}</strong></div>
      <div><span>Mancate</span><strong>${missed}</strong></div>
      <div><span>Da fare</span><strong>${pending}</strong></div>
      <div><span>Avanzamento</span><strong>${perc}%</strong></div>
      <div><span>Orario</span><strong>${esc(r.orario_partenza || "-")} → ${esc(r.orario_rientro_stimato || "-")}</strong></div>
      <div><span>Km</span><strong>${r.totale_km ?? "-"} km</strong></div>
    </div>

    <div class="dash-detail-progress-large"><span style="width:${perc}%"></span></div>

    <div class="dash-detail-actions">
      ${dashboardDetailActions(r)}
    </div>

    <div class="dash-operational-split">
      <div>
        <div class="dash-detail-section-title">
          <h3>Fermate del giro</h3>
          <small>Gli stati vengono aggiornati dall'autista dal portale mobile</small>
        </div>
        ${dashboardStopRows(r)}
      </div>
      <aside class="dash-admin-chat-card">
        <div class="dash-chat-title"><h3>Chat autista</h3><small id="dashChatStatus">Messaggi collegati a questo giro</small></div>
        <div id="dashAdminChatMessages" class="dash-admin-chat-messages"><div class="dash-empty">Caricamento chat...</div></div>
        <div class="dash-admin-chat-input">
          <textarea id="dashAdminChatInput" rows="2" placeholder="Scrivi all'autista..."></textarea>
          <button class="btn-primary" onclick="sendDashboardRouteChat(${r.id})">Invia</button>
        </div>
      </aside>
    </div>
  `;
  panel.scrollIntoView({behavior:"smooth", block:"start"});
  loadDashboardRouteChat(r.id, true);
}



let dashboardInProgressSelectedId = null;





function dashboardDeliveryRowsForSubpage(r){
  const rows = r.consegne || [];
  if(!rows.length){
    return `<div class="dash-detail-empty small">Nessuna consegna collegata a questo giro.</div>`;
  }
  return `<div class="dash-sub-table-wrap">
    <table class="dash-sub-table">
      <thead><tr><th>#</th><th>Cliente</th><th>Indirizzo</th><th>Colli / consegna</th><th>Stato</th><th>Distanza</th></tr></thead>
      <tbody>
        ${rows.map(d=>`
          <tr class="delivery-row-${esc(d.delivery_status||'in_attesa')}">
            <td>${d.ordine || ''}</td>
            <td><strong>${esc(d.cliente_nome || '-')}</strong></td>
            <td>${esc(d.indirizzo || '-')}</td>
            <td>${esc(d.manual_traffic || d.colli || d.pacchi || '-')}</td>
            <td>${deliveryStatusPill(d.delivery_status)}${d.motivo_mancata?`<small class="delivery-reason">${esc(d.motivo_mancata)}</small>`:''} ${deliverySignatureAction(d, r.driver_name)}</td>
            <td>${d.distanza_km ? fmtKm(d.distanza_km) : '-'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  </div>`;
}

function dashboardStopsTimelineForSubpage(r){
  const rows = r.consegne || [];
  if(!rows.length){
    return `<div class="dash-detail-empty small">Nessuna fermata pianificata.</div>`;
  }
  return `<div class="dash-stops-timeline">
    ${rows.map(d=>`
      <div class="dash-stop-line ${esc(d.delivery_status || 'in_attesa')}">
        <div class="dash-stop-number">${d.ordine || ''}</div>
        <div><strong>${esc(d.cliente_nome || '-')}</strong><small>${esc(d.indirizzo || '-')}</small></div>
        <div class="dash-stop-status">${deliveryStatusPill(d.delivery_status)}</div>
      </div>
    `).join('')}
  </div>`;
}





let dashboardChatRouteId = null;
async function loadDashboardRouteChat(routeId, markRead=true){
  dashboardChatRouteId = routeId;
  const box = document.getElementById("dashAdminChatMessages");
  const status = document.getElementById("dashChatStatus");
  if(!box) return;
  try{
    const data = await api(`/api/driver/admin/chat/${routeId}?since_id=0&mark_read=${markRead ? 'true' : 'false'}`);
    const msgs = data.messages || [];
    if(status) status.textContent = data.unread ? `${data.unread} nuovi messaggi dall'autista` : "Messaggi collegati a questo giro";
    box.innerHTML = msgs.length ? msgs.map(m=>{
      const mine = m.sender_type === 'admin';
      const when = m.created_at ? new Date(m.created_at).toLocaleString('it-IT', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : '';
      return `<div class="dash-chat-msg ${mine?'admin':'driver'}"><div class="dash-chat-bubble"><strong>${esc(m.sender_name|| (mine?'Admin':'Autista'))}</strong><p>${esc(m.message||'')}</p><small>${esc(when)}</small></div></div>`;
    }).join("") : `<div class="dash-empty">Nessun messaggio per questo giro.</div>`;
    box.scrollTop = box.scrollHeight;
    if(markRead) await loadDashboardHome();
  }catch(e){
    box.innerHTML = `<div class="dash-empty">Errore chat: ${esc(e.message)}</div>`;
  }
}
async function sendDashboardRouteChat(routeId){
  const input = document.getElementById("dashAdminChatInput");
  const msg = (input?.value || "").trim();
  if(!msg){ alert("Scrivi un messaggio prima di inviare."); return; }
  try{
    await api(`/api/driver/admin/chat/${routeId}`, {method:"POST", body:JSON.stringify({message:msg, sender_name:"Responsabile"})});
    input.value = "";
    await loadDashboardRouteChat(routeId, true);
    toast("Messaggio inviato all'autista.");
  }catch(e){ alert(e.message); }
}

function closeDashboardRouteDetail(){
  const panel = document.getElementById("dashboardRouteDetailPanel");
  if(panel){
    panel.classList.add("hidden");
    panel.innerHTML = "";
  }
}

async function cancelDashboardRoute(id){
  if(!confirm("Annullare questo giro? Autista e mezzo torneranno disponibili e il giro resterà nello storico.")) return;
  try{
    await api(`/api/routes/${id}/cancel`, {method:"POST", body:"{}"});
    toast("Giro annullato.");
    closeDashboardRouteDetail();
    await loadDashboardRoutes();
    await loadDashboardHome();
    await loadRoutes();
    await loadVehicles();
    await loadDrivers();
    await refreshResourceAvailability();
  }catch(e){ alert(e.message); }
}


async function openDashboardRoute(id){
  try{
    const r = await api(`/api/routes/${id}`);
    renderDashboardRouteDetail(r);
  }catch(e){ alert(e.message); }
}

async function completeDashboardRoute(id){
  if(!confirm("Segnare questo giro come completato? Verrà tolto dai giri operativi della Dashboard e resterà nello Storico.")) return;
  try{
    await api(`/api/routes/${id}/complete`, {method:"POST", body:"{}"});
    toast("Giro completato e spostato nello storico.");
    closeDashboardRouteDetail();
    await loadDashboardRoutes();
    await loadDashboardHome();
    await loadRoutes();
    await loadVehicles();
    await loadDrivers();
    await refreshResourceAvailability();
  }catch(e){ alert(e.message); }
}


async function loadDeposits(){
  depositsCache = await api("/api/deposits");
  const body = document.getElementById("depositsBody"), sel = document.getElementById("routeDeposit");
  body.innerHTML = ""; sel.innerHTML = "";
  depositsCache.forEach(x=>{
    body.innerHTML += `<tr><td>${esc(x.nome)}</td><td>${esc(x.indirizzo)}</td><td>${x.predefinito?"Sì":"No"}</td><td><button onclick="editDeposit(${x.id})">Modifica</button><button onclick="deleteDeposit(${x.id})">Elimina</button></td></tr>`;
    sel.innerHTML += `<option value="${x.id}">${esc(x.nome)} - ${esc(x.indirizzo)}</option>`;
  });
}
function editDeposit(id){
  const x = depositsCache.find(d=>d.id===id); if(!x) return;
  set("depId", x.id); set("depNome", x.nome); set("depIndirizzo", x.indirizzo);
  document.getElementById("depDefault").checked = !!x.predefinito;
}
function resetDepositForm(){ set("depId",""); set("depNome",""); set("depIndirizzo",""); document.getElementById("depDefault").checked=false; }
async function saveDeposit(){
  const payload = {nome:val("depNome"), indirizzo:val("depIndirizzo"), predefinito:document.getElementById("depDefault").checked};
  const id = val("depId");
  await api(id?`/api/deposits/${id}`:"/api/deposits", {method:id?"PUT":"POST", body:JSON.stringify(payload)});
  resetDepositForm(); loadDeposits();
}
async function deleteDeposit(id){ if(confirm("Eliminare deposito?")){ await api(`/api/deposits/${id}`, {method:"DELETE"}); loadDeposits(); } }

const GF_FUEL_LABELS_V895={gasolio:"Gasolio",benzina:"Benzina",gpl:"GPL",metano:"Metano",elettrico:"Elettrico",ibrido_benzina:"Ibrido benzina",ibrido_diesel:"Ibrido diesel",ibrido_plugin_benzina:"Ibrido plug-in benzina",ibrido_plugin_diesel:"Ibrido plug-in diesel"};
function fuelBaseTypeV895(type){if(["ibrido_benzina","ibrido_plugin_benzina"].includes(type))return "benzina";if(["ibrido_diesel","ibrido_plugin_diesel"].includes(type))return "gasolio";return type;}
function energyConsumptionLabelV895(v){const t=v.alimentazione||"gasolio", p=Number(v.consumo_primario_100km??v.consumo_l_100km??0), e=Number(v.consumo_kwh_100km||0);if(t==="elettrico")return `${e} kWh/100 km`;if(t==="metano")return `${p} kg/100 km`;if(t.startsWith("ibrido_plugin"))return `${p} L + ${e} kWh/100 km`;return `${p} L/100 km`;}
function updateVehicleEnergyFieldsV895(){const t=val("vFuelType")||"gasolio";const p=document.getElementById("vPrimaryConsumptionWrap"),e=document.getElementById("vElectricConsumptionWrap"),l=document.getElementById("vPrimaryConsumptionLabel");if(p)p.classList.toggle("hidden",t==="elettrico");if(e)e.classList.toggle("hidden",!(t==="elettrico"||t.startsWith("ibrido_plugin")));if(l)l.textContent=t==="metano"?"Consumo kg/100 km":"Consumo L/100 km";}
let gfFuelPricesV895=null;
async function loadAutomaticFuelPricesV895(){try{gfFuelPricesV895=await api("/api/vehicles/fuel-prices/current");}catch(e){gfFuelPricesV895={};}return gfFuelPricesV895;}
async function updateRouteEnergyPricingV895(){
  const v=vehiclesCache.find(x=>String(x.id)===String(val("routeVehicle")));
  const box=document.getElementById("routeEnergyPriceBoxV895"),
        title=document.getElementById("routeEnergyPriceTitleV895"),
        info=document.getElementById("routeEnergyVehicleInfo"),
        auto=document.querySelector('input[name="energyPriceMode"][value="automatic"]'),
        manual=document.querySelector('input[name="energyPriceMode"][value="manual"]'),
        primaryWrap=document.getElementById("primaryEnergyPriceWrap"),
        electricWrap=document.getElementById("electricEnergyPriceWrap"),
        label=document.getElementById("primaryEnergyPriceLabel"),
        note=document.getElementById("automaticFuelPriceInfo"),
        priceInput=document.getElementById("fuelPrice");

  if(!v){
    box?.classList.add("hidden");
    if(info) info.textContent="";
    primaryWrap?.classList.remove("hidden");
    electricWrap?.classList.add("hidden");
    if(title) title.textContent="Costo del giro";
    if(label) label.textContent="Prezzo carburante €/L";
    if(auto){ auto.disabled=false; auto.closest("label")?.classList.remove("muted"); }
    if(note) note.textContent="";
    updateRoutePlanningGateV68();
    updateDashboardStats();
    return;
  }

  box?.classList.remove("hidden");
  const t=v.alimentazione||"gasolio", base=fuelBaseTypeV895(t), electric=t==="elettrico", plugin=t.startsWith("ibrido_plugin");
  if(title) title.textContent=electric?"Costo energia del giro":plugin?"Costo carburante ed energia del giro":"Costo carburante del giro";
  if(info) info.textContent=`${GF_FUEL_LABELS_V895[t]||t} · ${energyConsumptionLabelV895(v)}`;
  primaryWrap?.classList.toggle("hidden",electric);
  electricWrap?.classList.toggle("hidden",!(electric||plugin));
  if(label) label.textContent=t==="metano"?"Prezzo metano €/kg":"Prezzo carburante €/L";

  if(auto){
    auto.disabled=electric;
    auto.closest("label")?.classList.toggle("muted",electric);
  }
  if(electric){
    if(manual) manual.checked=true;
    if(auto) auto.checked=false;
  }

  const mode=document.querySelector('input[name="energyPriceMode"]:checked')?.value||"manual";
  if(mode==="automatic"&&!electric){
    const prices=gfFuelPricesV895||await loadAutomaticFuelPricesV895();
    const row=prices?.[base];
    if(row?.price){
      set("fuelPrice",row.price);
      if(priceInput) priceInput.readOnly=true;
      if(note) note.textContent=`Automatico · ${row.source} · ${row.reference_date}${row.stale?" · ultimo dato disponibile":""}`;
    }else{
      if(priceInput) priceInput.readOnly=false;
      if(note) note.textContent="Prezzo automatico non disponibile: inserisci un valore manuale.";
    }
  }else{
    if(priceInput) priceInput.readOnly=false;
    if(note) note.textContent=electric?"Mezzo elettrico: inserisci la tariffa energia aziendale in €/kWh.":plugin?"Ibrido plug-in: imposta carburante ed energia elettrica per questo giro.":"Prezzo inserito manualmente per questo giro.";
  }
  updateRoutePlanningGateV68();
  updateDashboardStats();
}
async function loadVehicles(){
  vehiclesCache = await api("/api/vehicles");
  const body = document.getElementById("vehiclesBody");
  if(body){
    body.innerHTML = "";
    vehiclesCache.forEach(x=>{
      body.innerHTML += `<tr><td><div class="entity-cell">${imageThumb(x.photo_url,'🚚','vehicle-thumb')}<div><strong>${esc(x.nome)}</strong><br><small>${esc(x.note||'')}</small></div></div></td><td>${esc(x.targa||"")}</td><td>${energyConsumptionLabelV895(x)}</td><td>${x.ha_sponda?"Sì":"No"}</td><td>${x.accesso_ztl?"Sì":"No"}</td><td><button onclick="editVehicle(${x.id})">Modifica</button><button onclick="deleteVehicle(${x.id})">Elimina</button></td></tr>`;
    });
  }
  renderResourceSelects();
}
const VEHICLE_LOOKUP_FIELDS_V8966=["vMarca","vModello","vAnnoImmatricolazione","vCarrozzeria","vCilindrata","vPotenzaKw","vClasseEuro","vFuelType"];
function clearVehicleLookupHighlightsV8966(){
  VEHICLE_LOOKUP_FIELDS_V8966.forEach(id=>document.getElementById(id)?.classList.remove("vehicle-field-from-lookup-v8966","vehicle-field-missing-v8966"));
  document.getElementById("vehiclePlateVerifiedBadgeV8966")?.classList.add("hidden");
}
function markVehicleLookupResultV8966(data){
  const mapping={vMarca:data.marca,vModello:(data.modello||data.descrizione),vAnnoImmatricolazione:data.anno_immatricolazione,vCarrozzeria:data.carrozzeria,vCilindrata:data.cilindrata_cc,vPotenzaKw:data.potenza_kw,vClasseEuro:data.classe_euro,vFuelType:data.alimentazione};
  Object.entries(mapping).forEach(([id,value])=>{
    const el=document.getElementById(id); if(!el)return;
    el.classList.remove("vehicle-field-from-lookup-v8966","vehicle-field-missing-v8966");
    el.classList.add(value!==null && value!==undefined && String(value).trim()!=="" ? "vehicle-field-from-lookup-v8966" : "vehicle-field-missing-v8966");
  });
  const badge=document.getElementById("vehiclePlateVerifiedBadgeV8966");
  if(badge){
    const provider=String(data.provider||"").toUpperCase();
    badge.textContent=provider ? `✓ Dati verificati · ${provider}` : "✓ Dati verificati da targa";
    badge.classList.toggle("hidden",!!data.manual_required);
  }
}
function normalizeVehiclePlateInputV896(){
  const el=document.getElementById("vTarga");
  if(!el) return;
  el.value=(el.value||"").toUpperCase().replace(/[^A-Z0-9]/g,"").slice(0,10);
  const state=document.getElementById("vehiclePlateLookupStateV896");
  if(state){state.className="";state.textContent="Inserisci la targa per compilare automaticamente i dati disponibili.";}
  clearVehicleLookupHighlightsV8966();
}
function setVehiclePlateLookupStateV896(message,type=""){
  const el=document.getElementById("vehiclePlateLookupStateV896");
  if(!el)return; el.textContent=message; el.className=type||"";
}
async function lookupVehiclePlateV896(){
  normalizeVehiclePlateInputV896();
  const plate=val("vTarga");
  if(!plate){setVehiclePlateLookupStateV896("Inserisci prima la targa.","error");return;}
  const btn=document.getElementById("vehiclePlateLookupBtnV896");
  if(btn){btn.disabled=true;btn.textContent="Ricerca in corso...";}
  setVehiclePlateLookupStateV896("Ricerca dati veicolo in corso...");
  try{
    const data=await api(`/api/vehicles/lookup-plate/${encodeURIComponent(plate)}`);
    set("vTarga",data.targa||plate);
    set("vMarca",data.marca||""); set("vModello",data.modello||data.descrizione||"");
    set("vAnnoImmatricolazione",data.anno_immatricolazione||""); set("vCarrozzeria",data.carrozzeria||"");
    set("vCilindrata",data.cilindrata_cc||""); set("vPotenzaKw",data.potenza_kw||""); set("vClasseEuro",data.classe_euro||"");
    if(data.alimentazione){set("vFuelType",data.alimentazione);updateVehicleEnergyFieldsV895();}
    markVehicleLookupResultV8966(data);
    if(!val("vNome")){
      const generated=[data.marca,data.modello].filter(Boolean).join(" ").trim() || data.descrizione || plate;
      set("vNome",generated);
    }
    if(data.manual_required){
      setVehiclePlateLookupStateV896(data.message||"Targa validata. Completa manualmente i dati del mezzo.","info");
      const plateEl=document.getElementById("vTarga"); if(plateEl) plateEl.dataset.lookupProvider="";
      document.getElementById("vehiclePlateVerifiedBadgeV8966")?.classList.add("hidden");
      document.getElementById("vMarca")?.focus();
      toast("Targa validata. Completa i dati del mezzo.");
    }else{
      const provider=(data.provider||"servizio targa").toUpperCase();
      setVehiclePlateLookupStateV896(data.message||`Dati recuperati correttamente · Fonte ${provider}`,"ok");
      document.getElementById("vTarga")?.dataset && (document.getElementById("vTarga").dataset.lookupProvider=data.provider||"");
      toast("Dati veicolo recuperati dalla targa.");
    }
  }catch(e){
    setVehiclePlateLookupStateV896(e.message||"Impossibile recuperare i dati della targa.","error");
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Recupera dati veicolo";}
  }
}
function editVehicle(id){
  const x = vehiclesCache.find(v=>v.id===id); if(!x) return;
  set("vId",x.id); set("vNome",x.nome); set("vTarga",x.targa); set("vMarca",x.marca||""); set("vModello",x.modello||""); set("vAnnoImmatricolazione",x.anno_immatricolazione||""); set("vCarrozzeria",x.carrozzeria||""); set("vCilindrata",x.cilindrata_cc||""); set("vPotenzaKw",x.potenza_kw||""); set("vClasseEuro",x.classe_euro||""); set("vFuelType",x.alimentazione||"gasolio"); set("vConsumo",x.consumo_primario_100km ?? x.consumo_l_100km ?? 0); set("vConsumoKwh",x.consumo_kwh_100km||0); set("vKg",x.capacita_kg); set("vColli",x.capacita_colli); updateVehicleEnergyFieldsV895();
  const t=document.getElementById("vTarga"); if(t)t.dataset.lookupProvider=x.lookup_provider||"";
  setVehiclePlateLookupStateV896(x.lookup_provider?`Dati targa già acquisiti · Fonte ${String(x.lookup_provider).toUpperCase()}`:"Puoi aggiornare i dati del mezzo effettuando una nuova ricerca targa.",x.lookup_provider?"ok":"");
  clearVehicleLookupHighlightsV8966(); if(x.lookup_provider) markVehicleLookupResultV8966({...x,provider:x.lookup_provider});
  set("vSponda",x.ha_sponda?"true":"false"); set("vZtl",x.accesso_ztl?"true":"false"); set("vPhotoUrl", x.photo_url || ""); clearFileInput("vPhotoFile"); setImagePreview("vehiclePhotoPreview","vPhotoUrl","🚚");
}
function resetVehicleForm(){ clearVehicleLookupHighlightsV8966(); ["vId","vNome","vTarga","vMarca","vModello","vAnnoImmatricolazione","vCarrozzeria","vCilindrata","vPotenzaKw","vClasseEuro","vPhotoUrl"].forEach(id=>set(id,"")); const t=document.getElementById("vTarga"); if(t)t.dataset.lookupProvider=""; setVehiclePlateLookupStateV896("Inserisci la targa per compilare automaticamente i dati disponibili."); set("vFuelType","gasolio"); set("vConsumo",8.5); set("vConsumoKwh",0); updateVehicleEnergyFieldsV895(); set("vKg",1000); set("vColli",100); set("vSponda","false"); set("vZtl","false"); clearFileInput("vPhotoFile"); setImagePreview("vehiclePhotoPreview","vPhotoUrl","🚚"); }
async function saveVehicle(){
  return withButtonLoading("saveVehicleBtn", "Salvataggio...", async()=>{
    normalizeVehiclePlateInputV896();
    const plateEl=document.getElementById("vTarga");
    const payload = {nome:val("vNome"), targa:val("vTarga"), marca:val("vMarca")||null, modello:val("vModello")||null, anno_immatricolazione:val("vAnnoImmatricolazione")?parseInt(val("vAnnoImmatricolazione")):null, cilindrata_cc:val("vCilindrata")?parseInt(val("vCilindrata")):null, potenza_kw:val("vPotenzaKw")?parseFloat(val("vPotenzaKw")):null, classe_euro:val("vClasseEuro")||null, carrozzeria:val("vCarrozzeria")||null, lookup_provider:plateEl?.dataset?.lookupProvider||null, alimentazione:val("vFuelType")||"gasolio", consumo_primario_100km:parseFloat(val("vConsumo")||0), consumo_kwh_100km:parseFloat(val("vConsumoKwh")||0), consumo_l_100km:parseFloat(val("vConsumo")||0), capacita_kg:parseFloat(val("vKg")||1000), capacita_colli:parseInt(val("vColli")||100), ha_sponda:boolVal("vSponda"), accesso_ztl:boolVal("vZtl"), photo_url:val("vPhotoUrl") || null};
    if(!payload.nome){ alert("Inserisci il nome del mezzo"); return; }
    const id = val("vId");
    await api(id?`/api/vehicles/${id}`:"/api/vehicles", {method:id?"PUT":"POST", body:JSON.stringify(payload)});
    resetVehicleForm();
    await loadVehicles();
    await loadDashboardHome?.();
    toast(id ? "Mezzo aggiornato." : "Mezzo creato.");
  });
}
async function deleteVehicle(id){ if(confirm("Eliminare mezzo?")){ await api(`/api/vehicles/${id}`, {method:"DELETE"}); loadVehicles(); } }

async function loadDrivers(){
  try{
    driversCache = await api("/api/drivers");
  }catch(e){ driversCache = []; }
  renderResourceSelects();
  renderDrivers();
}
function driverFullName(d){ return `${d.nome||""} ${d.cognome||""}`.trim() || "Autista"; }
function driverInitials(d){ return driverFullName(d).split(" ").map(x=>x[0]).join("").slice(0,2).toUpperCase() || "A"; }
function updateDriverPreview(){
  const d = {nome:val("drNome"), cognome:val("drCognome"), patente:val("drPatente")};
  const photo = val("drPhotoUrl");
  const av = document.getElementById("driverAvatarPreview"); if(av) av.innerHTML = photo ? `<img src="${photo}" alt="Foto autista">` : driverInitials(d);
  const nm = document.getElementById("driverPreviewName"); if(nm) nm.textContent = driverFullName(d)==="Autista" ? "Nuovo autista" : driverFullName(d);
  const info = document.getElementById("driverPreviewInfo"); if(info) info.textContent = d.patente ? `Patente ${d.patente}` : "Patente e contatti operativi";
}
function renderDrivers(){
  const box = document.getElementById("driversCards");
  if(!box) return;
  const q = (document.getElementById("driverSearch")?.value || "").toLowerCase();
  const status = document.getElementById("driverStatusFilter")?.value || "";
  let rows = driversCache.filter(d=>{
    const hay = [d.nome,d.cognome,d.telefono,d.email,d.patente,d.note].join(" ").toLowerCase();
    return (!q || hay.includes(q)) && (!status || d.stato === status);
  });
  const total = driversCache.length;
  const available = driversCache.filter(d=>d.stato === "Disponibile").length;
  const working = driversCache.filter(d=>d.stato === "In servizio").length;
  const setText=(id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
  setText("driversTotal", total); setText("driversAvailable", available); setText("driversWorking", working);
  if(!rows.length){ box.innerHTML = `<div class="empty-picker">Nessun autista trovato</div>`; return; }
  box.innerHTML = rows.map(d=>{
    const statusClass = d.stato === "In servizio" ? "working" : "available";
    return `<article class="driver-card">
      <div class="driver-card-top">
        <div class="driver-avatar">${d.photo_url ? `<img src="${d.photo_url}" alt="Foto autista">` : driverInitials(d)}</div>
        <div><h3>${esc(driverFullName(d))}</h3><span class="driver-status ${statusClass}">${esc(d.stato || "Disponibile")}</span></div>
      </div>
      <div class="driver-info-grid">
        <div><small>Cellulare</small><strong>${esc(d.telefono || "-")}</strong></div>
        <div><small>Email</small><strong>${esc(d.email || "-")}</strong></div>
        <div><small>Patente</small><strong>${esc(d.patente || "-")}</strong></div>
        <div><small>Scadenza</small><strong>${esc(d.scadenza_patente || "-")}</strong></div>
        <div><small>Giri assegnati</small><strong>${d.giri_assegnati || 0}</strong></div>
        <div><small>Portale</small><strong>${d.account_attivo ? "Attivo" : (d.email ? "Da invitare" : "No email")}</strong></div>
      </div>
      ${d.note ? `<p class="driver-note">${esc(d.note)}</p>` : ""}
      <div class="row-actions driver-actions"><button onclick="editDriver(${d.id})">Modifica</button>${d.email ? `<button onclick="inviteDriver(${d.id})">${d.account_attivo ? "Reinvita" : "Invita"}</button>` : ""}<button onclick="deleteDriver(${d.id})">Elimina</button></div>
    </article>`;
  }).join("");
}
function resetDriverForm(){
  ["drId","drNome","drCognome","drTelefono","drEmail","drPatente","drScadenzaPatente","drNote","drPhotoUrl"].forEach(id=>set(id,""));
  clearFileInput("drPhotoFile"); updateDriverPreview();
  const title = document.getElementById("driverModalTitle"); if(title) title.textContent = "Nuovo autista";
}
function openDriverModal(){
  const overlay = document.getElementById("driverFormOverlay");
  if(overlay) overlay.classList.remove("hidden");
  setTimeout(()=>document.getElementById("drNome")?.focus(), 60);
}
function closeDriverModal(ev){
  if(ev && ev.target && ev.target.id !== "driverFormOverlay") return;
  const overlay = document.getElementById("driverFormOverlay");
  if(overlay) overlay.classList.add("hidden");
}
function openNewDriverModal(){
  resetDriverForm();
  openDriverModal();
}
function editDriver(id){
  const d = driversCache.find(x=>x.id===id); if(!d) return;
  set("drId", d.id); set("drNome", d.nome); set("drCognome", d.cognome); set("drTelefono", d.telefono); set("drEmail", d.email);
  set("drPatente", d.patente); set("drScadenzaPatente", d.scadenza_patente); set("drNote", d.note); set("drPhotoUrl", d.photo_url || ""); clearFileInput("drPhotoFile"); updateDriverPreview();
  const title = document.getElementById("driverModalTitle"); if(title) title.textContent = "Modifica autista";
  openDriverModal();
}
async function saveDriver(){
  return withButtonLoading("saveDriverBtn", "Salvataggio...", async()=>{
    const payload = {nome:val("drNome"), cognome:val("drCognome"), telefono:val("drTelefono"), email:val("drEmail"), patente:val("drPatente"), scadenza_patente:val("drScadenzaPatente")||null, cqc:false, scadenza_cqc:null, adr:false, note:val("drNote"), photo_url:val("drPhotoUrl") || null};
    if(!payload.nome){ alert("Inserisci almeno il nome dell'autista"); return; }
    const id = val("drId");
    const r = await api(id?`/api/drivers/${id}`:"/api/drivers", {method:id?"PUT":"POST", body:JSON.stringify(payload)});
    closeDriverModal();
    resetDriverForm();
    await loadDrivers();
    await loadDashboardHome?.();
    if(r.invite_email_sent){
      toast(id ? "Autista salvato e invito inviato" : "Autista creato e invito inviato");
    }else if(r.invite_setup_url){
      await navigator.clipboard?.writeText(r.invite_setup_url || "").catch(()=>{});
      alert((r.invite_message || "Email invito non inviata.") + "\n\nLink di primo accesso copiato negli appunti se consentito:\n" + r.invite_setup_url);
    }else{
      toast(id ? "Autista aggiornato." : "Autista creato.");
    }
  });
}
async function inviteDriver(id){
  try{
    const r = await api(`/api/drivers/${id}/invite`, {method:"POST", body:"{}"});
    if(r.email_sent) toast("Invito autista inviato via email");
    else {
      await navigator.clipboard?.writeText(r.setup_url || "").catch(()=>{});
      alert("SMTP non configurato o invio non riuscito. Link di invito copiato negli appunti se consentito:\n" + (r.setup_url || ""));
    }
    await loadDrivers();
  }catch(e){ alert(e.message); }
}

async function deleteDriver(id){
  if(confirm("Eliminare questo autista? I giri già salvati resteranno nello storico ma verranno scollegati dall'autista.")){
    await api(`/api/drivers/${id}`, {method:"DELETE"});
    await loadDrivers(); toast("Autista eliminato");
  }
}



function agentDisplayName(a){
  if(!a) return "Cliente interno";
  return a.full_name || `${a.nome||""} ${a.cognome||""}`.trim() || "Agente";
}

function renderAgentOptions(){
  const selects = [document.getElementById("cAgent"), document.getElementById("customerFilterAgent")].filter(Boolean);
  selects.forEach(sel=>{
    const current = sel.value || "";
    const isFilter = sel.id === "customerFilterAgent";
    sel.innerHTML = isFilter
      ? `<option value="">Agente tutti</option><option value="interno">Cliente interno</option>`
      : `<option value="">Cliente interno</option>`;
    agentsCache.forEach(a=>{
      if(!a.attivo && !isFilter) return;
      sel.innerHTML += `<option value="${a.id}">${esc(agentDisplayName(a))}${a.zona?` · ${esc(a.zona)}`:""}</option>`;
    });
    if(current) sel.value = current;
  });
}

async function loadAgents(){
  if(!agentsFeatureEnabled()){ agentsCache = []; renderAgentOptions(); return; }
  try{
    const params = new URLSearchParams({
      q: document.getElementById("agentSearch")?.value || "",
      stato: document.getElementById("agentStatusFilter")?.value || "",
    });
    agentsCache = await api("/api/agents?"+params.toString());
  }catch(e){
    agentsCache = [];
  }

  renderAgentOptions();

  const body = document.getElementById("agentsBody");
  if(!body) return;
  if(!agentsCache.length){
    body.innerHTML = `<tr><td colspan="7"><div class="empty-state-small">Nessun agente registrato.</div></td></tr>`;
    return;
  }
  body.innerHTML = agentsCache.map(a=>`
    <tr>
      <td>${esc(a.codice_agente || "-")}</td>
      <td><div class="entity-cell">${imageThumb(a.photo_url,'👤','agent-thumb')}<div><strong>${esc(agentDisplayName(a))}</strong>${a.note?`<br><small>${esc(a.note)}</small>`:""}</div></div></td>
      <td>${esc(a.telefono || "-")}<br><small>${esc(a.email || "")}</small></td>
      <td>${esc(a.zona || "-")}</td>
      <td><span class="route-status-pill ${a.attivo ? "programmato" : "annullato"}">${a.attivo ? "Attivo" : "Non attivo"}</span></td>
      <td>${a.clienti_assegnati || 0}</td>
      <td class="row-actions"><button onclick="editAgent(${a.id})">Modifica</button>${a.email?`<button onclick="inviteAgent(${a.id})">${a.account_attivo?"Reinvita":"Invita"}</button>`:""}<button onclick="deleteAgent(${a.id})">Elimina</button></td>
    </tr>
  `).join("");
}

function editAgent(id){
  const a = agentsCache.find(x=>x.id===id); if(!a) return;
  set("agId", a.id);
  set("agCodice", a.codice_agente);
  set("agNome", a.nome);
  set("agCognome", a.cognome);
  set("agTelefono", a.telefono);
  set("agEmail", a.email);
  set("agZona", a.zona);
  set("agAttivo", a.attivo ? "true" : "false");
  set("agNote", a.note);
  set("agPhotoUrl", a.photo_url || ""); clearFileInput("agPhotoFile"); setImagePreview("agentPhotoPreview","agPhotoUrl","👤");
}

function resetAgentForm(){
  ["agId","agCodice","agNome","agCognome","agTelefono","agEmail","agZona","agNote","agPhotoUrl"].forEach(id=>set(id,""));
  set("agAttivo","true"); clearFileInput("agPhotoFile"); setImagePreview("agentPhotoPreview","agPhotoUrl","👤");
}

async function saveAgent(){
  if(showLockedOrProceed("agenti")) return;
  return withButtonLoading("saveAgentBtn", "Salvataggio...", async()=>{
    const payload = {
      codice_agente: val("agCodice") || null,
      nome: val("agNome") || "Agente",
      cognome: val("agCognome") || null,
      telefono: val("agTelefono") || null,
      email: val("agEmail") || null,
      zona: val("agZona") || null,
      attivo: boolVal("agAttivo"),
      note: val("agNote") || null,
      photo_url: val("agPhotoUrl") || null,
    };
    const id = val("agId");
    const res = await api(id ? `/api/agents/${id}` : "/api/agents", {method:id ? "PUT" : "POST", body:JSON.stringify(payload)});
    if(res.invite){
      if(res.invite.email_sent) toast("Invito agente inviato via email");
      else alert("SMTP non configurato o invio non riuscito. Link primo accesso agente:\n" + (res.invite.invite_setup_url || ""));
    }
    resetAgentForm();
    await loadAgents();
    await loadCustomers();
    await loadCustomerPicker();
    toast(id ? "Agente aggiornato." : "Agente creato.");
  });
}
async function inviteAgent(id){
  if(showLockedOrProceed("agenti")) return;
  try{
    const r = await api(`/api/agents/${id}/invite`, {method:"POST", body:"{}"});
    if(r.email_sent) toast("Invito agente inviato via email");
    else alert("SMTP non configurato o invio non riuscito. Link primo accesso agente:\n" + (r.invite_setup_url || ""));
    await loadAgents();
  }catch(e){ alert(e.message); }
}

async function deleteAgent(id){
  if(showLockedOrProceed("agenti")) return;
  if(!confirm("Eliminare agente? I clienti collegati diventeranno Cliente interno.")) return;
  await api(`/api/agents/${id}`, {method:"DELETE"});
  await loadAgents();
  await loadCustomers();
  await loadCustomerPicker();
}



function openCustomerModal(id=null){
  resetCustomerForm();
  const title = document.getElementById("customerModalTitle");
  if(title) title.textContent = id ? "Modifica cliente" : "Nuovo cliente";
  document.getElementById("customerOverlay")?.classList.remove("hidden");
  ["cIndirizzo","cComune","cProvincia"].forEach(fieldId=>{
    const el = document.getElementById(fieldId);
    if(el && el.dataset.geoClearReady !== "true"){
      el.dataset.geoClearReady = "true";
      el.addEventListener("input", clearCustomerModalGeocode);
    }
  });
  if(id) editCustomer(id, true);
}
function closeCustomerModal(e){
  if(e && e.target && e.currentTarget && e.target !== e.currentTarget) return;
  document.getElementById("customerOverlay")?.classList.add("hidden");
}
function openCustomerImportModal(){ document.getElementById("customerImportOverlay")?.classList.remove("hidden"); }
function closeCustomerImportModal(e){
  if(e && e.target && e.currentTarget && e.target !== e.currentTarget) return;
  document.getElementById("customerImportOverlay")?.classList.add("hidden");
}
function toggleCustomerFilters(){ document.getElementById("customerAdvancedFilters")?.classList.toggle("hidden"); }
function clearCustomerFilters(){
  ["customerFilterComune","customerFilterProvincia","customerFilterAgent","customerFilterZtl","customerFilterSponda"].forEach(id=>set(id,""));
  loadCustomers();
}

function setCustomerAddressStatus(text, status="muted"){
  const box = document.getElementById("customerAddressVerifyStatus");
  if(!box) return;
  box.textContent = text || "";
  box.className = `address-verify-status ${status}`;
}

function clearCustomerModalGeocode(){
  ["cLat","cLon","cGeoStatus","cGeoProvider","cGeoConfidence","cGooglePlaceId","cGeocodedAddress"].forEach(id=>set(id,""));
  setCustomerAddressStatus("Indirizzo modificato: verifica con Google prima di salvare.", "warn");
}

function applyCustomerModalGeocode(data){
  const suggested = data?.suggested || {};
  const result = data?.result || {};
  if(suggested.indirizzo) set("cIndirizzo", suggested.indirizzo);
  set("cLat", suggested.lat ?? "");
  set("cLon", suggested.lon ?? "");
  set("cGeoStatus", suggested.stato_geocodifica || result.status || "non_trovato");
  set("cGeoProvider", suggested.fonte_geocodifica || result.source || "google");
  set("cGeoConfidence", suggested.affidabilita_geocodifica ?? result.confidence ?? "");
  set("cGooglePlaceId", suggested.google_place_id || result.place_id || "");
  set("cGeocodedAddress", suggested.indirizzo || result.formatted || "");

  const status = suggested.stato_geocodifica || result.status || "non_trovato";
  if(status === "verificato") setCustomerAddressStatus("Indirizzo verificato con Google.", "ok");
  else if(status === "da_verificare") setCustomerAddressStatus("Google ha trovato un indirizzo simile: controllalo prima di salvare.", "warn");
  else setCustomerAddressStatus("Google non ha trovato un indirizzo valido.", "error");
}

function customerPayloadFromModal(){
  return {
    ...(agentsFeatureEnabled() ? {agent_id: val("cAgent") ? parseInt(val("cAgent")) : null} : {}),
    codice_cliente: val("cCodice"),
    nome: val("cNome"),
    indirizzo: val("cIndirizzo"),
    comune: val("cComune"),
    provincia: val("cProvincia"),
    telefono: val("cTelefono"),
    email: val("cEmail"),
    referente: val("cReferente"),
    scarico_mattina_da: val("cMattinaDa") || null,
    scarico_mattina_a: val("cMattinaA") || null,
    scarico_pomeriggio_da: val("cPomeriggioDa") || null,
    scarico_pomeriggio_a: val("cPomeriggioA") || null,
    tempo_scarico_min: parseInt(val("cScarico") || 10),
    ztl: boolVal("cZtl"),
    sponda: boolVal("cSponda"),
    note: val("cNote"),
    lat: val("cLat") ? parseFloat(val("cLat")) : null,
    lon: val("cLon") ? parseFloat(val("cLon")) : null,
    indirizzo_geocodificato: val("cGeocodedAddress") || null,
    stato_geocodifica: val("cGeoStatus") || "da_verificare",
    affidabilita_geocodifica: val("cGeoConfidence") ? parseFloat(val("cGeoConfidence")) : null,
    fonte_geocodifica: val("cGeoProvider") || null,
    google_place_id: val("cGooglePlaceId") || null,
  };
}

async function verifyCustomerModalAddress(){
  const payload = customerPayloadFromModal();
  if(!payload.indirizzo || payload.indirizzo.trim().length < 4){
    alert("Inserisci un indirizzo valido prima di verificare con Google.");
    return;
  }
  try{
    setCustomerAddressStatus("Verifica Google in corso...", "loading");
    const data = await api("/api/customers/verify-address-preview", {method:"POST", body:JSON.stringify(payload)});
    applyCustomerModalGeocode(data);
  }catch(e){
    setCustomerAddressStatus("Errore durante la verifica Google.", "error");
    alert(e.message);
  }
}

async function loadCustomers(){
  const q = document.getElementById("customerListSearch")?.value || "";
  const comune = document.getElementById("customerFilterComune")?.value || "";
  const provincia = document.getElementById("customerFilterProvincia")?.value || "";
  const ztl = document.getElementById("customerFilterZtl")?.value || "";
  const sponda = document.getElementById("customerFilterSponda")?.value || "";
  const agent_id = agentsFeatureEnabled() ? (val("customerFilterAgent") || "") : "";
  const params = new URLSearchParams({q, comune, provincia, ztl, sponda, agent_id, limit:"500"});
  customersCache = await api("/api/customers?"+params.toString());
  const body = document.getElementById("customersBody");
  if(!body) return;
  body.innerHTML = "";
  customersCache.forEach(x=>{
    const geo = x.stato_geocodifica || "da_verificare";
    const geoLabel = {verificato:"Verificato",da_verificare:"Da verificare",non_trovato:"Non trovato",manuale:"Manuale"}[geo] || geo;
    body.innerHTML += `<tr><td>${esc(x.codice_cliente||"")}</td><td><strong>${esc(x.nome)}</strong><br><small>${esc(x.comune||"")} ${esc(x.provincia||"")}</small></td><td data-gf-agents-only>${esc(x.agent_name||"Cliente interno")}</td><td>${esc(x.indirizzo)}</td><td>${fascia(x)}</td><td><span class="geo-badge ${geo}">${geoLabel}</span><br><button class="btn-link-small" onclick="verifyCustomerAddress(${x.id})">Verifica</button></td><td>${x.ztl?"Sì":"No"}</td><td>${x.sponda?"Sì":"No"}</td><td><button onclick="openCustomerModal(${x.id})">Modifica</button><button onclick="deleteCustomer(${x.id})">Elimina</button></td></tr>`;
  });
}
function editCustomer(id, fromModal=false){
  const c = customersCache.find(x=>x.id===id); if(!c) return;
  set("cId",c.id); set("cCodice",c.codice_cliente); set("cNome",c.nome); set("cIndirizzo",c.indirizzo); set("cComune",c.comune); set("cProvincia",c.provincia); set("cTelefono",c.telefono); set("cEmail",c.email); set("cReferente",c.referente); set("cAgent", c.agent_id || "");
  set("cMattinaDa",c.scarico_mattina_da); set("cMattinaA",c.scarico_mattina_a); set("cPomeriggioDa",c.scarico_pomeriggio_da); set("cPomeriggioA",c.scarico_pomeriggio_a);
  set("cScarico",c.tempo_scarico_min); set("cZtl",c.ztl?"true":"false"); set("cSponda",c.sponda?"true":"false"); set("cNote",c.note);
  set("cLat", c.lat ?? ""); set("cLon", c.lon ?? ""); set("cGeoStatus", c.stato_geocodifica || "da_verificare"); set("cGeoProvider", c.fonte_geocodifica || "");
  set("cGeoConfidence", c.affidabilita_geocodifica ?? ""); set("cGooglePlaceId", c.google_place_id || ""); set("cGeocodedAddress", c.indirizzo_geocodificato || "");
  if(c.stato_geocodifica === "verificato") setCustomerAddressStatus("Indirizzo già verificato con Google.", "ok");
  else if(c.stato_geocodifica === "da_verificare") setCustomerAddressStatus("Indirizzo da verificare con Google.", "warn");
  else if(c.stato_geocodifica === "non_trovato") setCustomerAddressStatus("Indirizzo non trovato da Google.", "error");
  else setCustomerAddressStatus("Indirizzo non ancora verificato.", "muted");
  if(!fromModal) document.getElementById("customerOverlay")?.classList.remove("hidden");
}
function resetCustomerForm(){
  ["cId","cCodice","cNome","cIndirizzo","cComune","cProvincia","cTelefono","cEmail","cReferente","cAgent","cMattinaDa","cMattinaA","cPomeriggioDa","cPomeriggioA","cNote","cLat","cLon","cGeoStatus","cGeoProvider","cGeoConfidence","cGooglePlaceId","cGeocodedAddress"].forEach(id=>set(id,""));
  set("cScarico",10); set("cZtl","false"); set("cSponda","false");
  setCustomerAddressStatus("Indirizzo non ancora verificato.", "muted");
}
async function saveCustomer(){
  return withButtonLoading("saveCustomerBtn", "Salvataggio...", async()=>{
    const payload = customerPayloadFromModal();
    if(!payload.nome){ alert("Inserisci il nome del cliente"); return; }
    if(!payload.indirizzo){ alert("Inserisci l'indirizzo del cliente"); return; }
    if(!payload.lat || !payload.lon){
      const ok = confirm("Indirizzo non verificato con Google. Vuoi salvare comunque il cliente senza coordinate?");
      if(!ok) return;
    }
    const id = val("cId");
    await api(id?`/api/customers/${id}`:"/api/customers", {method:id?"PUT":"POST", body:JSON.stringify(payload)});
    closeCustomerModal();
    resetCustomerForm();
    await loadCustomers();
    await loadCustomerPicker();
    toast(id ? "Cliente aggiornato." : "Cliente creato.");
  });
}
async function deleteCustomer(id){ if(confirm("Eliminare cliente?")){ await api(`/api/customers/${id}`, {method:"DELETE"}); loadCustomers(); loadCustomerPicker(); } }
async function deleteAllCustomers(){
  const msg = "ATTENZIONE!\n\nSei sicuro di voler eliminare tutti i clienti registrati?\nUna volta effettuata questa operazione, tutte le informazioni andranno perse.";
  if(!confirm(msg)) return;
  const check = prompt("Per confermare scrivi: ELIMINA");
  if(check !== "ELIMINA") { alert("Operazione annullata"); return; }
  const res = await api("/api/customers/all", {method:"DELETE"});
  customersCache = [];
  await loadCustomers(); await loadCustomerPicker();
  toast(`Clienti eliminati: ${res.deleted}`);
}

async function verifyCustomerAddress(id){
  try{
    toast("Verifica indirizzo in corso...");
    const r = await api(`/api/customers/${id}/verify-address`, {method:"POST", body:"{}"});
    const status = r.result?.status || "non_trovato";
    toast(status === "verificato" ? "Indirizzo verificato." : status === "da_verificare" ? "Indirizzo trovato ma da verificare." : "Indirizzo non trovato.");
    await loadCustomers();
    await loadCustomerPicker();
  }catch(e){ alert(e.message); }
}

async function verifyPendingAddresses(){
  const box = document.getElementById("addressValidationSummary");
  if(box) box.innerHTML = "Verifica in corso. Attendi senza chiudere la pagina...";
  try{
    const r = await api("/api/customers/verify-pending?limit=100", {method:"POST", body:"{}"});
    if(box) box.innerHTML = `<strong>Controllati ${r.processed}</strong> · Verificati ${r.verificato} · Da verificare ${r.da_verificare} · Non trovati ${r.non_trovato}`;
    await loadCustomers();
    await loadCustomerPicker();
  }catch(e){
    if(box) box.textContent = e.message;
    alert(e.message);
  }
}

async function importCustomers(){
  const file = document.getElementById("importFile").files[0];
  if(!file){ alert("Scegli un file CSV o Excel"); return; }
  const fd = new FormData(); fd.append("file", file);
  const res = await fetch("/api/customers/import", {method:"POST", body:fd});
  if(!res.ok){ alert("Errore import"); return; }
  const j = await res.json();
  toast(`Import completato. Creati: ${j.created}, aggiornati: ${j.updated}.`);
  await loadCustomers();
  await loadCustomerPicker();
}

async function loadCustomerPicker(){
  const box = document.getElementById("customerPickerList");
  if(!box) return;
  const params = new URLSearchParams({
    q: document.getElementById("pickQ")?.value || "",
    comune: document.getElementById("pickComune")?.value || "",
    provincia: document.getElementById("pickProvincia")?.value || "",
    ztl: document.getElementById("pickZtl")?.value || "",
    sponda: document.getElementById("pickSponda")?.value || "",
    limit: "50"
  });
  const rows = await api("/api/customers?"+params.toString());
  box.innerHTML = rows.map(c=>{
    const already = deliveries.some(d=>String(d.customer_id||"")===String(c.id));
    return `<div class="picker-customer-row ${already ? 'already-added' : ''}">
      <div><strong>${esc(c.codice_cliente||"")} ${esc(c.nome)}</strong><small>${esc(c.indirizzo)} · ${esc(c.comune||"")} ${esc(c.provincia||"")} · ${agentsFeatureEnabled() ? esc(c.agent_name||"Cliente interno") + " · " : ""}${fascia(c)}</small></div>
      <button onclick="quickAddCustomerToDelivery(${c.id})" ${already ? 'class="btn-secondary"' : ''}>${already ? 'Aggiunto' : '+ Aggiungi'}</button>
    </div>`;
  }).join("") || `<div class="empty-picker">Nessun cliente trovato con questi filtri</div>`;
}

function deliveryFromCustomer(c){
  return {
    customer_id:c.id || null,
    codice_cliente:c.codice_cliente || "",
    cliente_nome:c.nome || "",
    indirizzo:c.indirizzo || "",
    peso_kg:0,
    colli:0,
    scarico_mattina_da:c.scarico_mattina_da || null,
    scarico_mattina_a:c.scarico_mattina_a || null,
    scarico_pomeriggio_da:c.scarico_pomeriggio_da || null,
    scarico_pomeriggio_a:c.scarico_pomeriggio_a || null,
    tempo_scarico_min:parseInt(c.tempo_scarico_min || 10),
    ztl:!!c.ztl,
    sponda:!!c.sponda,
    note:c.note || "",
    lat:c.lat ?? null,
    lon:c.lon ?? null,
    stato_geocodifica:c.stato_geocodifica || "da_verificare",
    indirizzo_geocodificato:c.indirizzo_geocodificato || null
  };
}

function addDeliveryObject(payload, message="Consegna aggiunta. Premi Calcola percorso quando hai terminato le modifiche."){
  if(!payload || !payload.cliente_nome || !payload.indirizzo){
    alert("Cliente o indirizzo non valido");
    return;
  }
  deliveries.push(payload);
  renderDeliveries();
  loadCustomerPicker();
  toast(message);
  markRouteNeedsRecalculation("Le consegne sono state modificate. Premi Calcola percorso per aggiornare il risultato.");
}

function quickAddCustomerToDelivery(id){
  const c = customersCache.find(x=>x.id===id);
  if(c){ addDeliveryObject(deliveryFromCustomer(c)); return; }
  api("/api/customers?limit=500").then(rows=>{
    const found = rows.find(x=>x.id===id);
    if(found){ addDeliveryObject(deliveryFromCustomer(found)); }
  });
}

/* Compatibilità: la vecchia ricerca manuale non è più visibile, ma resta utilizzabile se il campo esiste in vecchie viste. */
async function searchCustomersForDelivery(){
  const q = val("customerSearch"), box = document.getElementById("customerSuggestions");
  if(!box) return;
  if(q.length < 2){ box.innerHTML=""; return; }
  const rows = await api("/api/customers?q="+encodeURIComponent(q));
  box.innerHTML = "";
  rows.slice(0,10).forEach(c=>{
    const div = document.createElement("div");
    div.className = "suggestion";
    div.innerHTML = `<b>${esc(c.codice_cliente||"")}</b> ${esc(c.nome)}<br><small>${esc(c.indirizzo)} - ${fascia(c)}</small>`;
    div.onclick = () => selectCustomer(c);
    box.appendChild(div);
  });
}

function selectCustomer(c){
  selectedCustomer = c;
  const sug = document.getElementById("customerSuggestions");
  if(sug) sug.innerHTML = "";
  set("customerSearch", `${c.codice_cliente || ""} ${c.nome}`);
  set("dCliente", c.nome); set("dIndirizzo", c.indirizzo);
  const addr = document.getElementById("dIndirizzo");
  if(addr) markAddressVerified(addr, true);
  set("dMattinaDa", c.scarico_mattina_da); set("dMattinaA", c.scarico_mattina_a); set("dPomeriggioDa", c.scarico_pomeriggio_da); set("dPomeriggioA", c.scarico_pomeriggio_a);
  set("dScarico", c.tempo_scarico_min || 10); set("dZtl", c.ztl?"true":"false"); set("dSponda", c.sponda?"true":"false"); set("dNote", c.note);
}

function markRouteNeedsRecalculation(message="Le consegne sono state modificate. Premi Calcola percorso per aggiornare il risultato."){
  if(!lastRouteResult) return;
  lastRouteResult = null;
  lastMapsUrl = "";
  const box = document.getElementById("routePreviewResult");
  if(box){
    box.innerHTML = `<section class="panel"><div class="resultBox warn">
      <strong>Anteprima da aggiornare</strong>
      <span>${esc(message)}</span>
      <button class="btn-secondary" onclick="showTab('giro')">Torna alla pianificazione</button>
    </div></section>`;
  }
}

function deliveryPayloadFromForm(){
  const cliente = val("dCliente"), indirizzo = val("dIndirizzo");
  if(!cliente || !indirizzo){ alert("Inserisci cliente e indirizzo"); return null; }
  return {customer_id:selectedCustomer?.id || null, cliente_nome:cliente, indirizzo, peso_kg:parseFloat(val("dPeso")||0), colli:parseInt(val("dColli")||0),
    scarico_mattina_da:val("dMattinaDa")||null, scarico_mattina_a:val("dMattinaA")||null, scarico_pomeriggio_da:val("dPomeriggioDa")||null, scarico_pomeriggio_a:val("dPomeriggioA")||null,
    tempo_scarico_min:parseInt(val("dScarico")||10), ztl:boolVal("dZtl"), sponda:boolVal("dSponda"), note:val("dNote")};
}

function addDelivery(){
  const payload = deliveryPayloadFromForm();
  if(!payload) return;
  const wasEditing = editingDeliveryIndex !== null;
  if(wasEditing){
    deliveries[editingDeliveryIndex] = payload;
    toast("Consegna aggiornata. Premi Calcola percorso per aggiornare il giro.");
    cancelDeliveryEdit(false);
  }else{
    deliveries.push(payload);
    toast("Consegna aggiunta. Premi Calcola percorso quando hai terminato le modifiche.");
  }
  resetDeliveryForm();
  renderDeliveries();
  markRouteNeedsRecalculation(wasEditing ? "Una consegna è stata modificata. Premi Calcola percorso per aggiornare il risultato." : "È stata aggiunta una consegna. Premi Calcola percorso per aggiornare il risultato.");
}

function editDelivery(i){
  const row = document.querySelector(`[data-delivery-row="${i}"]`);
  if(row) row.scrollIntoView({behavior:"smooth", block:"center"});
  toast("Modifica la consegna direttamente dalla riga della tabella.");
}

function cancelDeliveryEdit(clear=true){
  editingDeliveryIndex = null;
  const title = document.getElementById("deliveryFormTitle");
  if(title) title.textContent = "Aggiungi consegna";
  const saveBtn = document.getElementById("saveDeliveryBtn");
  if(saveBtn) saveBtn.textContent = "+ Aggiungi consegna";
  const cancelBtn = document.getElementById("cancelEditDeliveryBtn");
  if(cancelBtn) cancelBtn.classList.add("hidden");
  if(clear) resetDeliveryForm();
}

function resetDeliveryForm(){
  selectedCustomer = null;
  ["customerSearch","dCliente","dIndirizzo","dMattinaDa","dMattinaA","dPomeriggioDa","dPomeriggioA","dPeso","dColli","dNote"].forEach(id=>set(id,""));
  set("dScarico",10); set("dZtl","false"); set("dSponda","false");
}

function updateDeliveryField(i, field, value){
  if(!deliveries[i]) return;
  if(field === "tempo_scarico_min" || field === "colli"){
    deliveries[i][field] = parseInt(value || 0);
  }else if(field === "peso_kg"){
    deliveries[i][field] = parseFloat(value || 0);
  }else if(field === "ztl" || field === "sponda"){
    deliveries[i][field] = value === "true";
  }else{
    deliveries[i][field] = value || null;
  }
  updateDashboardStats();
  markRouteNeedsRecalculation("Una consegna è stata modificata. Premi Calcola percorso per aggiornare il risultato.");
}

function moveDelivery(i, direction){
  const target = i + direction;
  if(target < 0 || target >= deliveries.length) return;
  const temp = deliveries[i];
  deliveries[i] = deliveries[target];
  deliveries[target] = temp;
  renderDeliveries();
  markRouteNeedsRecalculation("L'ordine delle consegne è stato modificato. Premi Calcola percorso per aggiornare il risultato.");
}

function renderDeliveryEmptyRow(){
  return `<tr><td colspan="5"><div class="empty-state-small">Nessuna consegna inserita. Seleziona i clienti dalla lista superiore e premi “+ Aggiungi”.</div></td></tr>`;
}

function deliveryGeoBadge(d){
  const geo = d.stato_geocodifica || (d.lat && d.lon ? "verificato" : "da_verificare");
  const label = {verificato:"Indirizzo verificato", da_verificare:"Da verificare", non_trovato:"Non trovato", manuale:"Manuale"}[geo] || "Da verificare";
  return `<span class="geo-badge ${esc(geo)}">${esc(label)}</span>`;
}

function deliverySpecsSummary(d){
  const pieces = [];
  pieces.push(`${parseInt(d.tempo_scarico_min)||10} min scarico`);
  if(d.ztl) pieces.push("ZTL");
  if(d.sponda) pieces.push("Sponda");
  if(parseFloat(d.peso_kg)||0) pieces.push(`${parseFloat(d.peso_kg)} kg`);
  if(parseInt(d.colli)||0) pieces.push(`${parseInt(d.colli)} colli`);
  return pieces.join(" · ");
}

function renderDeliveries(){
  updateDashboardStats();
  const body = document.getElementById("deliveryBody");
  if(!body) return;
  const counter = document.getElementById("deliveryTableCounter");
  const footer = document.getElementById("deliveryFooterCount");
  if(counter) counter.textContent = `${deliveries.length} ${deliveries.length===1 ? "fermata" : "fermate"}`;
  if(footer) footer.textContent = `${deliveries.length} ${deliveries.length===1 ? "consegna inserita" : "consegne inserite"}`;
  if(!deliveries.length){
    body.innerHTML = renderDeliveryEmptyRow();
    return;
  }
  body.innerHTML = deliveries.map((d,i)=>`
    <tr data-delivery-row="${i}" class="delivery-clean-row">
      <td class="delivery-main-cell clean">
        <strong>${esc(d.cliente_nome)}</strong>
        <small>${d.codice_cliente ? `Codice cliente: ${esc(d.codice_cliente)}` : `Fermata #${i+1}`}</small>
      </td>
      <td class="delivery-address-cell">
        <strong>${esc(d.indirizzo||"")}</strong>
        ${d.indirizzo_geocodificato && d.indirizzo_geocodificato !== d.indirizzo ? `<small>Verificato come: ${esc(d.indirizzo_geocodificato)}</small>` : ""}
      </td>
      <td>${deliveryGeoBadge(d)}</td>
      <td>
        <button class="btn-secondary compact-btn" onclick="openDeliveryDetailsModal(${i})">Dettagli</button>
        <small class="delivery-specs-preview">${esc(deliverySpecsSummary(d) || "Specifiche non inserite")}</small>
      </td>
      <td class="row-actions compact">
        <button title="Sposta su" onclick="moveDelivery(${i}, -1)">↑</button>
        <button title="Sposta giù" onclick="moveDelivery(${i}, 1)">↓</button>
        <button title="Rimuovi" onclick="removeDelivery(${i})">X</button>
      </td>
    </tr>`).join("");
}

function openDeliveryDetailsModal(i){
  const d = deliveries[i];
  if(!d) return;
  set("deliveryModalIndex", i);
  const setText = (id, value)=>{ const el=document.getElementById(id); if(el) el.textContent=value; };
  setText("deliveryModalCustomer", d.cliente_nome || "Cliente");
  setText("deliveryModalCode", d.codice_cliente ? `Codice cliente: ${d.codice_cliente}` : `Fermata #${i+1}`);
  setText("deliveryModalAddressText", d.indirizzo || "-");
  const geo = d.stato_geocodifica || (d.lat && d.lon ? "verificato" : "da_verificare");
  const geoLabel = {verificato:"Indirizzo verificato", da_verificare:"Indirizzo da verificare", non_trovato:"Indirizzo non trovato", manuale:"Indirizzo manuale"}[geo] || "Indirizzo da verificare";
  setText("deliveryModalGeoStatus", geoLabel);
  set("dmMattinaDa", d.scarico_mattina_da || "");
  set("dmMattinaA", d.scarico_mattina_a || "");
  set("dmPomeriggioDa", d.scarico_pomeriggio_da || "");
  set("dmPomeriggioA", d.scarico_pomeriggio_a || "");
  set("dmScarico", parseInt(d.tempo_scarico_min)||10);
  set("dmZtl", d.ztl ? "true" : "false");
  set("dmSponda", d.sponda ? "true" : "false");
  set("dmPeso", parseFloat(d.peso_kg)||0);
  set("dmColli", parseInt(d.colli)||0);
  set("dmNote", d.note || "");
  document.getElementById("deliveryDetailsOverlay")?.classList.remove("hidden");
}

function closeDeliveryDetailsModal(ev){
  if(ev && ev.target && ev.target.id !== "deliveryDetailsOverlay") return;
  document.getElementById("deliveryDetailsOverlay")?.classList.add("hidden");
}

function saveDeliveryDetailsModal(){
  const i = parseInt(val("deliveryModalIndex"));
  if(Number.isNaN(i) || !deliveries[i]) return;
  deliveries[i].scarico_mattina_da = val("dmMattinaDa") || null;
  deliveries[i].scarico_mattina_a = val("dmMattinaA") || null;
  deliveries[i].scarico_pomeriggio_da = val("dmPomeriggioDa") || null;
  deliveries[i].scarico_pomeriggio_a = val("dmPomeriggioA") || null;
  deliveries[i].tempo_scarico_min = parseInt(val("dmScarico")||10);
  deliveries[i].ztl = boolVal("dmZtl");
  deliveries[i].sponda = boolVal("dmSponda");
  deliveries[i].peso_kg = parseFloat(val("dmPeso")||0);
  deliveries[i].colli = parseInt(val("dmColli")||0);
  deliveries[i].note = val("dmNote") || null;
  closeDeliveryDetailsModal();
  renderDeliveries();
  markRouteNeedsRecalculation("Le specifiche della consegna sono state modificate. Premi Calcola percorso per aggiornare il risultato.");
  toast("Dettagli consegna aggiornati.");
}


function removeDelivery(i){
  deliveries.splice(i,1);
  if(editingDeliveryIndex===i) cancelDeliveryEdit();
  renderDeliveries();
  loadCustomerPicker();
  markRouteNeedsRecalculation("Una consegna è stata rimossa. Premi Calcola percorso per aggiornare il risultato.");
}

function warnTypeCounts(consegne){
  const counts = {sponda:0, ztl:0, attesa:0, critici:0};
  (consegne||[]).forEach(d=>{
    const w = (d.warning||"").toLowerCase();
    if(w) counts.critici++;
    if(w.includes("sponda")) counts.sponda++;
    if(w.includes("ztl")) counts.ztl++;
    if((parseFloat(d.attesa_min)||0)>0 || w.includes("attesa") || w.includes("apertura")) counts.attesa++;
  });
  return counts;
}
function warningBadges(warning){
  if(!warning) return `<span class="badge ok-badge">OK</span>`;
  return String(warning).split(";").map(x=>x.trim()).filter(Boolean).map(x=>{
    const low=x.toLowerCase();
    const cls = low.includes("sponda") || low.includes("non fattibile") || low.includes("chiusura") ? "badge danger-badge" : (low.includes("ztl") ? "badge orange-badge" : "badge warn-badge");
    return `<span class="${cls}">${esc(x)}</span>`;
  }).join(" ");
}

function cleanDeliveryForPayload(d){
  return {
    customer_id: d.customer_id || null, cliente_nome: d.cliente_nome, indirizzo: d.indirizzo,
    peso_kg: parseFloat(d.peso_kg)||0, colli: parseInt(d.colli)||0,
    scarico_mattina_da: d.scarico_mattina_da || null, scarico_mattina_a: d.scarico_mattina_a || null,
    scarico_pomeriggio_da: d.scarico_pomeriggio_da || null, scarico_pomeriggio_a: d.scarico_pomeriggio_a || null,
    tempo_scarico_min: parseInt(d.tempo_scarico_min)||10, ztl: !!d.ztl, sponda: !!d.sponda, note: d.note || null
  };
}
function routePayloadFromResult(){
  return {
    route_id: lastRouteResult?.id || null,
    nome: lastRouteResult?.nome || val("routeName") || "Giro consegne",
    data_giro: lastRouteResult?.data_giro || val("routeDate"),
    orario_partenza: lastRouteResult?.orario_partenza || val("routeStart") || "08:00",
    deposit_id: parseInt(lastRouteResult?.deposit_id || val("routeDeposit")),
    vehicle_id: (lastRouteResult?.vehicle_id || val("routeVehicle")) ? parseInt(lastRouteResult?.vehicle_id || val("routeVehicle")) : null,
    driver_id: (lastRouteResult?.driver_id || val("routeDriver")) ? parseInt(lastRouteResult?.driver_id || val("routeDriver")) : null,
    rientro_deposito: lastRouteResult?.rientro_deposito ?? boolVal("returnDepot"),
    prezzo_carburante_litro: parseFloat(lastRouteResult?.prezzo_carburante_litro || val("fuelPrice") || 0),
    energy_price_mode: document.querySelector('input[name="energyPriceMode"]:checked')?.value || lastRouteResult?.energy_price_mode || "manual",
    energy_price_primary: parseFloat(val("fuelPrice")||lastRouteResult?.energy_price_primary||0), energy_price_electric: parseFloat(val("electricityPrice")||lastRouteResult?.energy_price_electric||0),
    consegne: (lastRouteResult?.consegne || deliveries).map(cleanDeliveryForPayload)
  };
}
async function recalcManualRoute(reason="Ordine modificato manualmente. Percorso ricalcolato."){
  if(!lastRouteResult) return;
  const box = document.getElementById("routePreviewResult");
  try{
    showTab("route-preview");
    if(box) box.insertAdjacentHTML("afterbegin", `<div class="resultBox">Ricalcolo percorso in corso...</div>`);
    const r = await api("/api/routes/recalculate-manual", {method:"POST", body:JSON.stringify(routePayloadFromResult())});
    deliveries = (r.consegne || []).map(cleanDeliveryForPayload);
    customerPlanningStepOpenedV68 = true;
    updateRoutePlanningGateV68();
    renderDeliveries();
    renderRouteResult(r, "routePreviewResult", false);
    const inlineHint = document.getElementById("routePlanningInlineHint");
    if(inlineHint) inlineHint.classList.remove("hidden");
    toast(reason);
    loadRoutes();
  }catch(e){ alert(e.message); }
}
function resultDragStart(ev, idx){ draggedStopIndex = idx; ev.dataTransfer.effectAllowed = "move"; }
function resultDragOver(ev){ ev.preventDefault(); }
function resultDrop(ev, idx){
  ev.preventDefault();
  if(draggedStopIndex === null || draggedStopIndex === idx || !lastRouteResult) return;
  const arr = lastRouteResult.consegne || [];
  const [moved] = arr.splice(draggedStopIndex, 1);
  arr.splice(idx, 0, moved);
  lastRouteResult.consegne = arr.map((d,i)=>({...d, ordine:i+1}));
  draggedStopIndex = null;
  recalcManualRoute();
}
function addExtraStopAfterResult(){
  document.getElementById("customerSearch")?.scrollIntoView({behavior:"smooth", block:"center"});
  toast("Seleziona il cliente, aggiungi la consegna e poi premi Calcola percorso.");
}


function clearRouteWorkspace(){
  deliveries = [];
  lastRouteResult = null;
  lastMapsUrl = "";
  editingDeliveryIndex = null;
  renderDeliveries();
  const result = document.getElementById("routePreviewResult");
  if(result) result.innerHTML = `<section class="panel route-preview-empty-v76"><h2>Nessuna anteprima calcolata</h2><p>Vai in Pianificazione, inserisci i dati del giro, seleziona i clienti e calcola il percorso.</p><button class="btn-primary" onclick="showTab('giro')">Vai alla pianificazione</button></section>`;
  const inlineHint = document.getElementById("routePlanningInlineHint");
  if(inlineHint) inlineHint.classList.add("hidden");
  set("routeName", "");
  set("routeDate", todayIso());
  set("routeStart", "");
  set("routeVehicle", "");
  set("routeDriver", "");
  set("fuelPrice", val("fuelPrice") || "1.75");
  updateDashboardStats();
  renderResourceSelects();
  customerPlanningStepOpenedV68 = false;
  refreshResourceAvailability();
  updateRoutePlanningGateV68();
}

async function programCurrentRoute(){
  if(!lastRouteResult || !lastRouteResult.id){
    alert("Calcola prima il percorso del giro.");
    return;
  }
  try{
    await api(`/api/routes/${lastRouteResult.id}/program`, {method:"POST", body:"{}"});
    toast("Giro programmato correttamente. Lo trovi in Giri programmati.");
    clearRouteWorkspace();
    await loadDashboardRoutes();
    await loadDashboardHome();
    await loadRoutes();
    await loadVehicles();
    await loadDrivers();
    await refreshResourceAvailability();
    showTab("dashboard-scheduled");
  }catch(e){
    alert(e.message || "Errore durante la programmazione del giro.");
  }
}

async function openProgrammedRouteForEdit(id){
  try{
    const r = await api(`/api/routes/${id}`);
    const st = r.status || "programmato";
    showTab("giro");
    set("routeName", r.nome || "Giro consegne");
    set("routeDate", r.data_giro || todayIso());
    set("routeStart", r.orario_partenza || "");
    set("routeDeposit", r.deposit_id || "");
    set("fuelPrice", r.energy_price_primary ?? r.prezzo_carburante_litro ?? val("fuelPrice") ?? "1.75");
    set("electricityPrice", r.energy_price_electric ?? val("electricityPrice") ?? "0.30");
    const savedMode=document.querySelector(`input[name="energyPriceMode"][value="${r.energy_price_mode||'manual'}"]`); if(savedMode)savedMode.checked=true;
    set("returnDepot", r.rientro_deposito ? "true" : "false");
    await refreshResourceAvailability();
    set("routeVehicle", r.vehicle_id || "");
    set("routeDriver", r.driver_id || "");
    await updateRouteEnergyPricingV895();
    deliveries = (r.consegne || []).map(cleanDeliveryForPayload);
    customerPlanningStepOpenedV68 = true;
    updateRoutePlanningGateV68();
    renderDeliveries();
    lastRouteResult = r;
    lastMapsUrl = r.google_maps_url || "";
    if(st === "programmato" || st === "bozza"){
      renderRouteResult(r, "routePreviewResult", false);
      showTab("route-preview");
      toast("Giro aperto in anteprima. Torna alla pianificazione per modificare e ricalcolare.");
    }else{
      renderRouteResult(r, "routePreviewResult", true);
      showTab("route-preview");
      toast("Giro aperto in sola visualizzazione.");
    }
    document.getElementById("routePreviewResult")?.scrollIntoView({behavior:"smooth", block:"start"});
  }catch(e){ alert(e.message); }
}


function renderRouteResult(r, targetId="routeResult", fromHistory=false){
  lastRouteResult = r;
  lastMapsUrl = r.google_maps_url || "";
  const consegne = r.consegne || [];
  const counts = warnTypeCounts(consegne);
  const target = document.getElementById(targetId);
  const routeStatus = r.status || "bozza";
  const isDraft = routeStatus === "bozza";
  const isProgrammable = !fromHistory && !!r.id && (routeStatus === "bozza" || routeStatus === "programmato");
  const title = fromHistory ? `Risultato giro salvato` : (isProgrammable ? `Anteprima giro da programmare` : `Anteprima giro`);
  let rows = "";
  consegne.forEach((d,idx)=>{
    const dragAttrs = fromHistory ? "" : `draggable="true" ondragstart="resultDragStart(event, ${idx})" ondragover="resultDragOver(event)" ondrop="resultDrop(event, ${idx})"`;
    rows += `<tr class="draggable-stop" ${dragAttrs}>
      <td><span class="drag-handle">☰</span> <strong>${d.ordine}</strong></td>
      <td><strong>${esc(d.cliente_nome)}</strong></td>
      <td>${esc(d.indirizzo)}</td>
      <td>${esc(d.arrivo_stimato||"-")}</td>
      <td>${esc(d.partenza_stimata||"-")}</td>
      <td>${Math.round(parseFloat(d.attesa_min)||0)} min</td>
      <td>${d.km_tappa ?? "-"}</td>
      <td>${warningBadges(d.warning)}</td>
      <td class="row-actions compact"><a target="_blank" href="${mapsAddressUrl(d.indirizzo)}"><button title="Apri fermata su Maps">📍</button></a><button onclick="copyText('${esc(d.indirizzo).replace(/'/g,"\\'")}', 'Indirizzo copiato')" title="Copia indirizzo">⧉</button>${deliverySignatureAction(d, r.driver_name)}</td>
    </tr>`;
  });
  target.innerHTML = `<section class="result-pro">
    <div class="result-header">
      <div><h2>${title}</h2><p>Analisi del percorso e delle fermate pianificate${fromHistory ? " dallo storico" : ""}.</p></div>
      ${fromHistory ? "" : `<div class="result-header-actions route-preview-top-actions-v76"><button class="btn-secondary" onclick="showTab('giro')">Torna alla pianificazione</button><small>Controlla il riepilogo prima di confermare. Per modificare clienti o dati del giro torna alla pianificazione e ricalcola.</small></div>`}
    </div>
    <div class="result-layout">
      <div class="result-main">
        <div class="result-cards">
          <div class="mini-card"><span class="mini-icon blue">◷</span><div><small>Partenza</small><strong>${esc(r.orario_partenza||"-")}</strong></div></div>
          <div class="mini-card"><span class="mini-icon orange">↩</span><div><small>Rientro stimato</small><strong>${esc(r.orario_rientro_stimato||"-")}</strong></div></div>
          <div class="mini-card"><span class="mini-icon green">⌖</span><div><small>Km totali</small><strong>${r.totale_km ?? "-"} km</strong></div></div>
          <div class="mini-card"><span class="mini-icon purple">◴</span><div><small>Tempo totale</small><strong>${Math.round(r.totale_minuti||0)} min</strong></div></div>
          <div class="mini-card"><span class="mini-icon blue">⛽</span><div><small>Litri stimati</small><strong>${r.litri_stimati ?? "-"} L</strong></div></div>
          <div class="mini-card"><span class="mini-icon purple">€</span><div><small>Costo carburante</small><strong>€ ${r.costo_carburante ?? "-"}</strong></div></div>
        </div>
        <div class="alerts-panel">
          <h3>Avvisi principali</h3>
          <div class="alert-grid">
            <div class="alert-card danger"><strong>🚚 Sponda richiesta non disponibile</strong><span>${counts.sponda} fermate</span></div>
            <div class="alert-card orange"><strong>🏙 Cliente in ZTL</strong><span>${counts.ztl} fermate</span></div>
            <div class="alert-card yellow"><strong>🕒 Arrivo prima dell'apertura / attesa</strong><span>${counts.attesa} fermate</span></div>
          </div>
        </div>
        <div class="stops-panel">
          <h3>Dettaglio fermate</h3>
          <div class="tableWrap"><table class="result-table"><thead><tr><th>Ordine</th><th>Cliente</th><th>Indirizzo</th><th>Arrivo</th><th>Ripartenza</th><th>Attesa</th><th>Km tappa</th><th>Avvisi</th><th>Azioni</th></tr></thead><tbody>${rows}</tbody></table></div>
        </div>
        ${r.id ? `<div class="route-map-panel-v74">
          <div class="route-map-head-v74">
            <div><h3>Mappa del giro</h3><p>Percorso stradale reale del giro, con deposito e marker numerati.</p></div>
            <div class="route-map-actions-v74">
              ${r.google_maps_url ? `<a target="_blank" href="${esc(r.google_maps_url)}"><button class="btn-secondary">Apri in Google Maps</button></a>` : ``}
              <button class="btn-secondary" onclick="renderRouteGoogleMapV74(${r.id}, 'routeGoogleMapV74_${r.id}')">Ricarica mappa</button>
            </div>
          </div>
          <div id="routeGoogleMapV74_${r.id}" class="route-google-map-v74"><div class="route-map-loading-v74">Caricamento mappa...</div></div>
          <small class="route-map-note-v74">La mappa visualizza la sequenza già calcolata da GiroFacile. Non modifica il percorso.</small>
        </div>` : ``}
      </div>
      <aside class="result-summary-card">
        <h3>Riepilogo esito</h3>
        <div class="summary-row"><span>Totale fermate</span><strong>${consegne.length}</strong></div>
        <div class="summary-row"><span>Autista</span><strong>${esc(r.driver_name||"Non assegnato")}</strong></div>
        <div class="summary-row"><span>Mezzo</span><strong>${esc(r.vehicle_name||"Nessun mezzo")}</strong></div>
        <div class="summary-row"><span>Avvisi critici</span><strong>${counts.critici}</strong></div>
        <div class="summary-row"><span>Soste con attesa</span><strong>${counts.attesa}</strong></div>
        <div class="summary-highlight"><span>Costo energetico stimato</span><strong>€ ${r.costo_totale ?? r.costo_carburante ?? "-"}</strong></div>
        <button class="btn-secondary full" onclick="printStopsTable()">Stampa dettaglio fermate</button>
        ${r.id ? `<button class="btn-secondary full" onclick="explainRouteSequenceAIv67(${r.id})">Spiega sequenza giro AI</button><div id="routeAiExplanationV67" class="ai-explanation-v67 hidden"></div>` : ""}
        ${isProgrammable ? `<button class="btn-primary full" onclick="programCurrentRoute()">Programma giro</button><small class="program-route-note">Dopo la conferma verrai portato direttamente in Giri programmati.</small>` : ""}
      </aside>
    </div>
  </section>`;
  if(r.id){ setTimeout(()=>renderRouteGoogleMapV74(r.id, `routeGoogleMapV74_${r.id}`), 120); }
}

async function loadGoogleMapsScriptV74(apiKey){
  if(window.google && window.google.maps) return true;
  if(!apiKey) return false;
  if(window.__gfGoogleMapsLoadingV74){
    return window.__gfGoogleMapsLoadingV74;
  }
  window.__gfGoogleMapsLoadingV74 = new Promise((resolve, reject)=>{
    const existing = document.querySelector('script[data-gf-google-maps-v74="1"]');
    if(existing){
      existing.addEventListener('load', ()=>resolve(true));
      existing.addEventListener('error', reject);
      return;
    }
    const script = document.createElement('script');
    script.dataset.gfGoogleMapsV74 = '1';
    script.async = true;
    script.defer = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}`;
    script.onload = ()=>resolve(true);
    script.onerror = ()=>reject(new Error('Impossibile caricare Google Maps JS'));
    document.head.appendChild(script);
  });
  return window.__gfGoogleMapsLoadingV74;
}



function decodeGooglePolylineV75(encoded){
  if(!encoded) return [];
  let index = 0;
  const len = encoded.length;
  let lat = 0;
  let lng = 0;
  const coordinates = [];
  while(index < len){
    let b, shift = 0, result = 0;
    do{
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    }while(b >= 0x20 && index < len);
    const dlat = (result & 1) ? ~(result >> 1) : (result >> 1);
    lat += dlat;

    shift = 0;
    result = 0;
    do{
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    }while(b >= 0x20 && index < len);
    const dlng = (result & 1) ? ~(result >> 1) : (result >> 1);
    lng += dlng;

    coordinates.push({lat: lat / 1e5, lng: lng / 1e5});
  }
  return coordinates;
}

function markerLabelV74(text){
  return {text: String(text), color: '#ffffff', fontWeight: '800', fontSize: '13px'};
}

async function renderRouteGoogleMapV74(routeId, elementId){
  const el = document.getElementById(elementId);
  if(!el) return;
  el.innerHTML = '<div class="route-map-loading-v74">Caricamento mappa...</div>';
  try{
    const data = await api(`/api/routes/${routeId}/map-data`);
    if(!data.api_key){
      el.innerHTML = '<div class="route-map-empty-v74"><strong>Chiave Google non configurata</strong><p>Inserisci la chiave in Super Admin → Server / Manutenzione oppure Impostazioni SaaS.</p></div>';
      return;
    }
    await loadGoogleMapsScriptV74(data.api_key);
    if(!window.google || !window.google.maps){ throw new Error('Google Maps non disponibile'); }

    const depot = data.depot || {};
    const validStops = (data.stops || []).filter(s=>s.lat !== null && s.lon !== null);
    const points = [];
    if(depot.lat !== null && depot.lon !== null) points.push({type:'deposit', title: depot.name || 'Deposito', address: depot.address || '', lat: depot.lat, lon: depot.lon});
    validStops.forEach(s=>points.push({type:'stop', order:s.order, title:s.name, address:s.address, arrival:s.arrival, departure:s.departure, lat:s.lat, lon:s.lon}));
    if(data.return_depot && depot.lat !== null && depot.lon !== null) points.push({type:'return', title:'Rientro deposito', address: depot.address || '', lat: depot.lat, lon: depot.lon});

    if(points.length < 2){
      const missing = (data.stops || []).length - validStops.length;
      el.innerHTML = `<div class="route-map-empty-v74"><strong>Coordinate insufficienti</strong><p>Verifica gli indirizzi clienti con Google per visualizzare la mappa del giro.${missing>0 ? ` Fermate senza coordinate: ${missing}.` : ''}</p>${data.google_maps_url ? `<a target="_blank" href="${esc(data.google_maps_url)}"><button class="btn-primary">Apri Google Maps</button></a>` : ''}</div>`;
      return;
    }

    const map = new google.maps.Map(el, {
      center: {lat: points[0].lat, lng: points[0].lon},
      zoom: 12,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: true,
    });
    const bounds = new google.maps.LatLngBounds();
    const path = [];
    const info = new google.maps.InfoWindow();

    points.forEach((p, idx)=>{
      const pos = {lat:p.lat, lng:p.lon};
      bounds.extend(pos);
      path.push(pos);
      const label = p.type === 'deposit' ? 'D' : (p.type === 'return' ? 'R' : p.order);
      const marker = new google.maps.Marker({
        position: pos,
        map,
        label: markerLabelV74(label),
        title: p.title || '',
      });
      marker.addListener('click', ()=>{
        const arrival = p.arrival ? `<br><small>Arrivo previsto: ${esc(p.arrival)}</small>` : '';
        const departure = p.departure ? `<br><small>Ripartenza: ${esc(p.departure)}</small>` : '';
        info.setContent(`<div class="route-map-popup-v74"><strong>${p.type==='stop' ? `${p.order}. ` : ''}${esc(p.title||'Fermata')}</strong><br><span>${esc(p.address||'')}</span>${arrival}${departure}</div>`);
        info.open(map, marker);
      });
    });

    const encodedRoadPolyline = data.road_polyline && data.road_polyline.encoded_polyline;
    const roadPath = encodedRoadPolyline ? decodeGooglePolylineV75(encodedRoadPolyline) : [];
    if(roadPath.length > 1){
      roadPath.forEach(pos=>bounds.extend(pos));
      new google.maps.Polyline({
        path: roadPath,
        geodesic: false,
        strokeOpacity: 0.95,
        strokeWeight: 5,
        map,
      });
    }else{
      new google.maps.Polyline({
        path,
        geodesic: true,
        strokeOpacity: 0.45,
        strokeWeight: 4,
        map,
      });
      const warnRoad = document.createElement('div');
      warnRoad.className = 'route-map-warn-v74';
      warnRoad.textContent = 'Percorso stradale Google non disponibile: visualizzazione provvisoria con linea diretta tra le fermate.';
      el.appendChild(warnRoad);
    }
    map.fitBounds(bounds);
    if((data.stops || []).length !== validStops.length){
      const warn = document.createElement('div');
      warn.className = 'route-map-warn-v74';
      warn.textContent = `${(data.stops||[]).length-validStops.length} fermate senza coordinate: verifica gli indirizzi con Google.`;
      el.appendChild(warn);
    }
  }catch(e){
    el.innerHTML = `<div class="route-map-empty-v74"><strong>Mappa non disponibile</strong><p>${esc(e.message || 'Errore durante il caricamento della mappa.')}</p></div>`;
  }
}

async function explainRouteSequenceAIv67(routeId){
  const box = document.getElementById("routeAiExplanationV67");
  if(!box) return;
  box.classList.remove("hidden");
  box.innerHTML = "<strong>Perché questa sequenza?</strong><p>Generazione spiegazione AI in corso...</p>";
  try{
    const r = await api(`/api/routes/${routeId}/ai-explanation`, {method:"POST"});
    box.innerHTML = `<strong>Perché GiroFacile ha scelto questa sequenza?</strong><p>${esc(r.text || "Nessuna spiegazione generata.")}</p>${r.fallback ? `<small>Nota: AI non configurata, testo locale di supporto.</small>` : ``}`;
  }catch(e){
    box.innerHTML = `<strong>AI non disponibile</strong><p>${esc(e.message || "Non è stato possibile generare la spiegazione.")}</p>`;
  }
}

async function optimizeRoute(){
  if(!routePlanningDetailsCompleteV68()){
    updateRoutePlanningGateV68();
    alert("Completa prima tutti i dati del giro: data, orario, deposito, mezzo, autista e prezzo carburante.");
    return;
  }
  if(!deliveries.length){ alert("Aggiungi almeno una consegna"); return; }
  if(!val("routeDate") || !val("routeStart")){ alert("Seleziona prima data e orario di partenza"); return; }
  if(!routeDateIsValid()){ alert("Non puoi programmare un giro in una data precedente a oggi"); enforceRouteDateMin(); return; }
  await refreshResourceAvailability();
  const payload = {nome:val("routeName") || "Giro consegne", data_giro:val("routeDate"), orario_partenza:val("routeStart"), deposit_id:parseInt(val("routeDeposit")),
    vehicle_id:val("routeVehicle") ? parseInt(val("routeVehicle")) : null, driver_id:val("routeDriver") ? parseInt(val("routeDriver")) : null, rientro_deposito:boolVal("returnDepot"), prezzo_carburante_litro:parseFloat(val("fuelPrice")||0), energy_price_mode:(document.querySelector('input[name="energyPriceMode"]:checked')?.value||"manual"), energy_price_primary:parseFloat(val("fuelPrice")||0), energy_price_electric:parseFloat(val("electricityPrice")||0), consegne:deliveries};
  const box = document.getElementById("routePreviewResult");
  if(box) box.innerHTML = `<section class="panel"><div class="resultBox">Calcolo anteprima giro in corso...</div></section>`;
  showTab("route-preview");
  try{
    const r = await api("/api/routes/optimize", {method:"POST", body:JSON.stringify(payload)});
    deliveries = (r.consegne || []).map(cleanDeliveryForPayload);
    customerPlanningStepOpenedV68 = true;
    updateRoutePlanningGateV68();
    renderDeliveries();
    renderRouteResult(r, "routePreviewResult", false);
    const setText = (id,val)=>{ const el=document.getElementById(id); if(el) el.textContent=val; };
    setText("summaryKm", r.totale_km + " km");
    setText("summaryTime", Math.round(r.totale_minuti) + " min");
    setText("summaryCost", "€ " + r.costo_carburante);
    loadRoutes();
    loadDashboardRoutes();
    await loadVehicles();
    await loadDrivers();
    await refreshResourceAvailability();
    document.getElementById("routePreviewResult")?.scrollIntoView({behavior:"smooth", block:"start"});
  }catch(e){
    const msg = e.message || "Errore sconosciuto";
    const ticketBtn = e.errorId ? `<button class="btn-secondary" style="margin-top:10px" onclick="openSupportPanelV49(${e.errorId})">Invia ticket assistenza</button>` : "";
    if(box) box.innerHTML = `
      <div class="resultBox warn route-error-box">
        <strong>Errore calcolo percorso</strong>
        <span>${esc(msg)}</span>
        <small>${msg.toLowerCase().includes("non disponibile") || msg.toLowerCase().includes("già assegnato") ? "Scegli un altro mezzo/autista oppure modifica l'orario del giro." : "Controlla l'indirizzo indicato, rendilo più completo e riprova."}</small>
        ${ticketBtn}
      </div>`;
  }
}
async function loadRoutes(){
  const rows = await api("/api/routes");
  const body = document.getElementById("routesBody");
  body.innerHTML = "";
  rows.forEach(r=>{
    body.innerHTML += `<tr><td>${esc(r.data_giro)}</td><td><strong>${esc(r.nome)}</strong></td><td>${r.orario_partenza||""}</td><td>${r.orario_rientro_stimato||""}</td><td>${esc(r.driver_name||"-")}</td><td>${r.totale_km}</td><td>€ ${r.costo_carburante}</td><td class="row-actions"><button onclick="openSavedRoute(${r.id})">Apri giro</button>${r.google_maps_url?`<a target="_blank" href="${r.google_maps_url}"><button>Maps</button></a><button onclick="copyText('${String(r.google_maps_url).replace(/'/g,"\\'")}', 'Link Google Maps copiato')">Condividi</button>`:""}</td></tr>`;
  });
}
async function openSavedRoute(id){
  try{
    const r = await api(`/api/routes/${id}`);
    renderUnifiedRouteView(r, "historyResult", "history");
    document.getElementById("historyResult").scrollIntoView({behavior:"smooth", block:"start"});
  }catch(e){ alert(e.message); }
}


async function initAdminApp(){
  loadProfilePanel();
  showTab("admin-dashboard");
  await loadAdminDashboard();
}

function adminStatusBadge(status){
  const s = status || "aperto";
  const text = {aperto:"Aperto", in_lavorazione:"In lavorazione", chiuso:"Chiuso"}[s] || s;
  return `<span class="route-status-pill ${s}">${esc(text)}</span>`;
}

function formatDateTimeLabel(value){
  if(!value) return "-";
  try{
    const d = new Date(value);
    if(Number.isNaN(d.getTime())) return value;
    return d.toLocaleString("it-IT", {day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit"});
  }catch(e){ return value; }
}

async function loadAdminDashboard(){
  try{
    const data = await api("/api/admin/summary");
    const setText = (id,val)=>{ const el=document.getElementById(id); if(el) el.textContent=val; };
    setText("adminTotalUsers", data.total_users || 0);
    setText("adminOpenTickets", data.open_tickets || 0);
    setText("adminPasswordTickets", data.password_tickets || 0);
    setText("adminTotalTickets", data.total_tickets || 0);

    const usersBox = document.getElementById("adminRecentUsers");
    if(usersBox){
      usersBox.innerHTML = (data.recent_users||[]).map(u=>`
        <div class="admin-list-item">
          <div><strong>${esc(u.company_name || u.username || "Utente")}</strong><small>${esc(u.email || "-")} · ${formatDateTimeLabel(u.created_at)}</small></div>
          <span class="admin-mini-pill">${u.is_admin ? "Admin" : "Utente"}</span>
        </div>`).join("") || renderEmptyDashList("Nessun utente registrato.");
    }

    const ticketsBox = document.getElementById("adminRecentTickets");
    if(ticketsBox){
      ticketsBox.innerHTML = (data.recent_tickets||[]).map(t=>`
        <div class="admin-list-item">
          <div><strong>${esc(t.oggetto || t.tipo || "Ticket")}</strong><small>${esc(t.email)} · ${formatDateTimeLabel(t.created_at)}</small></div>
          ${adminStatusBadge(t.status)}
        </div>`).join("") || renderEmptyDashList("Nessun ticket ricevuto.");
    }
  }catch(e){ console.warn(e); }
}

async function loadAdminUsers(){
  try{
    const rows = await api("/api/admin/users");
    const body = document.getElementById("adminUsersBody");
    if(!body) return;
    body.innerHTML = rows.map(u=>`
      <tr>
        <td><strong>${esc(u.company_name || "-")}</strong></td>
        <td>${esc(u.username || "-")}</td>
        <td>${esc(u.email || "-")}</td>
        <td>${formatDateTimeLabel(u.created_at)}</td>
        <td>${u.customers_count || 0}</td>
        <td>${u.routes_count || 0}</td>
        <td>${u.vehicles_count || 0}</td>
        <td>${u.drivers_count || 0}</td>
        <td>${u.is_admin ? '<span class="admin-mini-pill">Admin</span>' : '<span class="admin-mini-pill user">Utente</span>'}</td>
      </tr>`).join("") || `<tr><td colspan="9"><div class="empty-state-small">Nessun utente trovato.</div></td></tr>`;
  }catch(e){ alert(e.message); }
}

async function loadAdminTickets(){
  try{
    const status = document.getElementById("adminTicketStatus")?.value || "";
    const rows = await api("/api/admin/tickets" + (status ? `?status=${encodeURIComponent(status)}` : ""));
    const box = document.getElementById("adminTicketsList");
    if(!box) return;
    box.innerHTML = rows.map(t=>`
      <div class="admin-ticket-card">
        <div class="admin-ticket-head">
          <div>
            <strong>${esc(t.oggetto || "Ticket")}</strong>
            <small>${esc(t.email)} · ${esc(t.company_name || t.username || "Nessun utente collegato")} · ${formatDateTimeLabel(t.created_at)}</small>
          </div>
          ${adminStatusBadge(t.status)}
        </div>
        <p>${esc(t.messaggio || "")}</p>
        <label>Note admin</label>
        <textarea id="adminTicketNote${t.id}" rows="2" placeholder="Aggiungi una nota interna...">${esc(t.admin_note || "")}</textarea>
        <div class="actions-row">
          <button class="btn-secondary" onclick="copyText('${esc(t.email).replace(/'/g,"\\'")}', 'Email copiata')">Copia email</button>
          <button class="btn-secondary" onclick="updateAdminTicket(${t.id}, 'in_lavorazione')">In lavorazione</button>
          <button class="btn-primary" onclick="updateAdminTicket(${t.id}, 'chiuso')">Chiudi ticket</button>
        </div>
      </div>`).join("") || renderEmptyDashList("Nessun ticket trovato.");
  }catch(e){ alert(e.message); }
}

async function updateAdminTicket(id, status){
  try{
    const note = document.getElementById(`adminTicketNote${id}`)?.value || "";
    await api(`/api/admin/tickets/${id}`, {method:"PUT", body:JSON.stringify({status, admin_note:note})});
    toast("Ticket aggiornato.");
    await loadAdminTickets();
    await loadAdminDashboard();
  }catch(e){ alert(e.message); }
}

if(window.location.pathname.startsWith("/reset-password/")){
  showResetPasswordPanel();
}else{
  checkLogin().catch(()=>{});
}


/* Fix V3.6.1.1: forza la visualizzazione corretta dopo il login */
const originalGiroFacileLogin = login;
login = async function(){
  const result = await originalGiroFacileLogin.apply(this, arguments);
  setTimeout(() => {
    const app = document.getElementById('app');
    const loginCard = document.getElementById('loginCard');
    if(app && !app.classList.contains('hidden')){
      showGestionaleAfterLogin();
    } else if(loginCard && app){
      // fallback: se il login originale ha salvato la sessione ma non ha nascosto bene la schermata
      const token = localStorage.getItem('token') || localStorage.getItem('authToken') || localStorage.getItem('girofacile_token');
      if(token){
        showGestionaleAfterLogin();
      }
    }
  }, 80);
  return result;
};



// ============================================================
// CHAT AUTISTI - centro comunicazioni Dashboard
// ============================================================
let driverChatThreadsCache = [];
let driverChatCenterDriverId = null;
let driverChatCenterPoll = null;

function chatTimeLabel(value){
  if(!value) return "";
  try{
    const d = new Date(value);
    return d.toLocaleString("it-IT", {day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"});
  }catch(e){ return ""; }
}

function driverChatAvatar(thread){
  if(thread.driver_photo_url){
    return `<img src="${esc(thread.driver_photo_url)}" alt="${esc(thread.driver_name||'Autista')}">`;
  }
  const name = (thread.driver_name || "Autista").trim();
  const initials = name.split(/\s+/).slice(0,2).map(x=>x[0]||"").join("").toUpperCase() || "A";
  return `<span>${esc(initials)}</span>`;
}

async function loadDriverChatNotifications(){
  if(featureLockedForTab("chat-autisti")){
    const badge = document.getElementById("sidebarChatBadge");
    if(badge) badge.classList.add("hidden");
    return;
  }
  try{
    const rows = await api('/api/driver/admin/chat-threads');
    const total = rows.reduce((sum,r)=>sum + Number(r.unread||0), 0);
    const badge = document.getElementById('sidebarChatBadge');
    if(badge){
      if(total > 0){ badge.textContent = total > 99 ? '99+' : String(total); badge.classList.remove('hidden'); }
      else badge.classList.add('hidden');
    }
  }catch(e){}
}

async function loadDriverChatCenter(driverId=null){
  if(showLockedOrProceed("chat-autisti")) return;
  const list = document.getElementById('driverChatThreadList');
  const count = document.getElementById('driverChatCenterCount');
  if(list) list.innerHTML = '<div class="dash-empty">Caricamento conversazioni...</div>';
  try{
    driverChatThreadsCache = await api('/api/driver/admin/chat-threads');
    if(count) count.textContent = `${driverChatThreadsCache.length} chat`;
    renderDriverChatThreadList();
    const selectedId = driverId || driverChatCenterDriverId || (driverChatThreadsCache[0] && driverChatThreadsCache[0].driver_id);
    if(selectedId) await openDriverChatCenterThread(selectedId, false);
    else renderEmptyDriverChatRoom();
    await loadDriverChatNotifications();
  }catch(e){
    if(list) list.innerHTML = `<div class="dash-empty">Errore caricamento chat: ${esc(e.message||'Errore')}</div>`;
  }
}

function renderDriverChatThreadList(){
  const list = document.getElementById('driverChatThreadList');
  if(!list) return;
  if(!driverChatThreadsCache.length){
    list.innerHTML = '<div class="dash-empty">Nessuna conversazione. Le chat appariranno quando un autista scrive o quando apri la conversazione.</div>';
    return;
  }
  list.innerHTML = driverChatThreadsCache.map(t=>{
    const unread = Number(t.unread||0);
    const active = Number(t.driver_id) === Number(driverChatCenterDriverId);
    const last = t.last_message ? esc(t.last_message) : 'Nessun messaggio ancora';
    return `<button class="driver-chat-thread ${active?'active':''} ${unread?'has-unread':''}" onclick="openDriverChatCenterThread(${t.driver_id})">
      <div class="driver-chat-avatar">${driverChatAvatar(t)}</div>
      <div class="driver-chat-thread-body">
        <div class="driver-chat-thread-top"><strong>${esc(t.driver_name||'Autista')}</strong><small>${esc(chatTimeLabel(t.last_message_at) || t.date || '')}</small></div>
        <span>${esc(t.route_name || 'Chat libera')}</span>
        <p>${last}</p>
      </div>
      ${unread?`<span class="driver-chat-unread">${unread}</span>`:''}
    </button>`;
  }).join('');
}

function renderEmptyDriverChatRoom(){
  const title = document.getElementById('driverChatRoomTitle');
  const sub = document.getElementById('driverChatRoomSubtitle');
  const box = document.getElementById('driverChatRoomMessages');
  const badge = document.getElementById('driverChatRoomBadge');
  if(title) title.textContent = 'Seleziona una chat';
  if(sub) sub.textContent = 'Apri una conversazione per leggere e rispondere all\'autista.';
  if(box) box.innerHTML = '<div class="dash-empty">Nessuna chat selezionata.</div>';
  if(badge) badge.classList.add('hidden');
}

async function openDriverChatCenterThread(driverId, markRead=true){
  driverChatCenterDriverId = Number(driverId);
  renderDriverChatThreadList();
  const t = driverChatThreadsCache.find(x=>Number(x.driver_id)===Number(driverId));
  const title = document.getElementById('driverChatRoomTitle');
  const sub = document.getElementById('driverChatRoomSubtitle');
  const badge = document.getElementById('driverChatRoomBadge');
  if(title) title.textContent = t ? (t.driver_name || 'Autista') : 'Chat autista';
  if(sub) sub.textContent = t ? 'Conversazione diretta con l’amministratore' : 'Chat libera autista/amministratore';
  if(badge){
    const unread = t ? Number(t.unread||0) : 0;
    if(unread){ badge.textContent = `${unread} nuovi`; badge.classList.remove('hidden'); } else badge.classList.add('hidden');
  }
  await loadDriverChatCenterMessages(driverId, markRead);
  if(driverChatCenterPoll) clearInterval(driverChatCenterPoll);
  driverChatCenterPoll = setInterval(()=>loadDriverChatCenterMessages(driverId, false), 5000);
}

async function loadDriverChatCenterMessages(driverId, markRead=true){
  const box = document.getElementById('driverChatRoomMessages');
  if(!box) return;
  try{
    const data = await api(`/api/driver/admin/direct-chat/${driverId}?since_id=0&mark_read=${markRead?'true':'false'}`);
    const msgs = data.messages || [];
    if(!msgs.length){
      box.innerHTML = '<div class="dash-empty">Nessun messaggio. Puoi scrivere all\'autista da qui.</div>';
    }else{
      box.innerHTML = msgs.map(m=>{
        const mine = m.sender_type === 'admin';
        const when = chatTimeLabel(m.created_at);
        return `<div class="dash-chat-msg ${mine?'admin':'driver'}"><div class="dash-chat-bubble"><strong>${esc(m.sender_name || (mine?'Responsabile':'Autista'))}</strong><p>${esc(m.message||'')}</p><small>${esc(when)}</small></div></div>`;
      }).join('');
      box.scrollTop = box.scrollHeight;
    }
    if(markRead){
      await loadDriverChatCenterListSilently();
      await loadDriverChatNotifications();
    }
  }catch(e){
    box.innerHTML = `<div class="dash-empty">Errore chat: ${esc(e.message||'Errore')}</div>`;
  }
}

async function loadDriverChatCenterListSilently(){
  if(featureLockedForTab("chat-autisti")) return;
  try{
    driverChatThreadsCache = await api('/api/driver/admin/chat-threads');
    const count = document.getElementById('driverChatCenterCount');
    if(count) count.textContent = `${driverChatThreadsCache.length} chat`;
    renderDriverChatThreadList();
  }catch(e){}
}

async function sendDriverChatCenterMessage(){
  if(showLockedOrProceed("chat-autisti")) return;
  if(!driverChatCenterDriverId){ toast('Seleziona una chat prima di inviare'); return; }
  const input = document.getElementById('driverChatCenterInput');
  const msg = (input.value || '').trim();
  if(!msg) return;
  input.value = '';
  try{
    await api(`/api/driver/admin/direct-chat/${driverChatCenterDriverId}`, {method:'POST', body:JSON.stringify({message:msg, sender_name:'Responsabile'})});
    await loadDriverChatCenterMessages(driverChatCenterDriverId, true);
    await loadDriverChatCenterListSilently();
  }catch(e){ toast('Errore invio messaggio: ' + (e.message||'Errore')); }
}

/* ------------------------------------------------------------------
   Dashboard operativa v2
   - sottopagine programmati / in corso / completati
   - controllo giro solo nelle sottopagine
   - stato in corso solo da avvio autista
   - fermate unica tabella con arrivo stimato aggiornato e note per cliente
------------------------------------------------------------------ */
let dashboardScheduledSelectedId = null;
let dashboardCompletedSelectedId = null;

function showTab(name){
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
  if(name==="activity") loadActivityLogV31();
  if(name==="chat-autisti") loadDriverChatCenter();
  if(name==="settings") loadSettingsV41();
  if(name==="plan-account"){ renderUpgradeCards(); syncPlanPageHeaderV874(); }
  if(name==="integrations") renderIntegrationsV52();
  if(name==="transfer-portal") loadTransferPortalV78();
  if(name==="transfer-bookings") loadTransferBookingsV79();
  if(name==="transfer-planning") loadTransferPlanningV79();
  if(name==="transfer-settings") loadTransferSettingsV79();

  if(name==="admin-dashboard") loadAdminDashboard();
  if(name==="admin-users") loadAdminUsers();
  if(name==="admin-tickets") loadAdminTickets();
}

function dashRouteItem(r, type){
  const progress = routeProgressPercent(r);
  const meta = `${esc(r.data_giro||"-")} · ${r.consegne_count||0} consegne${r.totale_km?` · ${r.totale_km} km`:""}`;
  const pill = routeStatusBadge(r.status, r.status_label);
  const unread = Number(r.unread_driver_messages||0);
  const isProgress = type === 'progress';
  const next = r.next_delivery ? `${r.next_delivery.cliente_nome || 'Prossima consegna'}${r.next_delivery.indirizzo ? ' · ' + r.next_delivery.indirizzo : ''}` : '';
  let click = `openDashboardRoute(${r.id})`;
  if(type === 'scheduled') click = `openDashboardScheduledPage(${r.id})`;
  if(type === 'progress') click = `openDashboardInProgressPage(${r.id})`;
  if(type === 'completed') click = `openDashboardCompletedPage(${r.id})`;
  return `<div class="dash-route-item ${isProgress?'dash-route-item-live':''}" onclick="${click}">
    <div class="dash-route-main">
      <strong>${esc(r.nome||"Giro consegne")}</strong>
      <small>${meta}</small>
      ${isProgress?`
        <div class="dash-progress"><span style="width:${progress}%"></span></div>
        <div class="dash-live-grid">
          <span><b>${r.completed_count||0}</b> completate</span>
          <span><b>${r.missed_count||0}</b> mancate</span>
          <span><b>${r.remaining_count ?? 0}</b> da fare</span>
        </div>
        ${next?`<small class="dash-next-stop">Prossima: ${esc(next)}</small>`:""}
        ${unread?`<div class="dash-chat-alert">💬 ${unread} messagg${unread===1?'io':'i'} autista non lett${unread===1?'o':'i'}</div>`:""}
      `:""}
    </div>
    <div class="dash-route-side">${pill}<span class="dash-arrow">›</span></div>
  </div>`;
}

function gfTimeFromIso(value){
  if(!value) return '';
  try{
    const d = new Date(value);
    if(Number.isNaN(d.getTime())) return String(value).slice(11,16) || value;
    return d.toLocaleTimeString('it-IT', {hour:'2-digit', minute:'2-digit'});
  }catch(e){ return String(value || '').slice(11,16); }
}
function gfMinutesFromHHMM(v){
  if(!v || typeof v !== 'string') return null;
  const m = v.match(/(\d{1,2}):(\d{2})/);
  if(!m) return null;
  return Number(m[1]) * 60 + Number(m[2]);
}
function gfRealArrival(d){
  return gfTimeFromIso(d.arrivo_reale || d.arrived_at || d.completata_il || d.signed_at || '');
}
function gfPlannedArrival(d){
  return d.arrivo_stimato || d.arrivo_previsto || '-';
}
function gfDeltaBadge(planned, real){
  const p = gfMinutesFromHHMM(planned);
  const r = gfMinutesFromHHMM(real);
  if(p === null || r === null) return '<span class="muted">-</span>';
  const diff = r - p;
  const cls = diff <= 0 ? 'early' : (diff <= 10 ? 'ok' : 'late');
  const label = diff === 0 ? 'In orario' : `${diff > 0 ? '+' : ''}${diff} min`;
  return `<span class="gf-delta-badge ${cls}">${esc(label)}</span>`;
}
function dashboardRouteSummaryCards(r, rows){
  const completed = rows.filter(x=>x.delivery_status === 'completata').length;
  const missed = rows.filter(x=>x.delivery_status === 'mancata').length;
  const pending = Math.max(rows.length - completed - missed, 0);
  return `<div class="gf-route-kpi-grid">
    <div><span>Km previsti</span><strong>${esc(r.totale_km ?? '-')} km</strong></div>
    <div><span>Tempo previsto</span><strong>${Math.round(Number(r.totale_minuti||0)) || '-'} min</strong></div>
    <div><span>Consegne</span><strong>${completed}/${rows.length}</strong><small>${missed} mancate · ${pending} da fare</small></div>
    <div><span>Litri stimati</span><strong>${esc(r.litri_stimati ?? '-')} L</strong></div>
    <div><span>Costo stimato</span><strong>€ ${esc(r.costo_carburante ?? '-')}</strong></div>
    <div><span>Rientro previsto</span><strong>${esc(r.orario_rientro_stimato || '-')}</strong></div>
  </div>`;
}
function dashboardStopRowsUnified(r, mode='live'){
  const rows = r.consegne || [];
  if(!rows.length){
    return `<div class="dash-detail-empty small">Nessuna fermata collegata a questo giro.</div>`;
  }
  return `<div class="dash-sub-table-wrap gf-unified-stop-wrap">
    <table class="dash-sub-table dash-stop-table-unified gf-unified-stop-table">
      <thead>
        <tr><th>#</th><th>Cliente</th><th>Indirizzo</th><th>Arrivo previsto</th><th>Arrivo reale</th><th>Differenza</th><th>Stato</th><th>Firma</th><th>Note</th></tr>
      </thead>
      <tbody>
        ${rows.map(d=>{
          const st = d.delivery_status || d.status || 'in_attesa';
          const note = d.note_operatore || d.note_autista || d.note || '';
          const planned = gfPlannedArrival(d);
          const real = gfRealArrival(d);
          return `<tr class="delivery-row-${esc(st)}">
            <td><span class="dash-stop-number mini">${d.ordine || ''}</span></td>
            <td><strong>${esc(d.cliente_nome || '-')}</strong></td>
            <td>${esc(d.indirizzo || '-')}</td>
            <td><strong>${esc(planned)}</strong></td>
            <td>${real ? `<strong class="gf-real-arrival">${esc(real)}</strong>` : '<span class="muted">-</span>'}</td>
            <td>${gfDeltaBadge(planned, real)}</td>
            <td>${deliveryStatusPill(st)}${d.motivo_mancata?`<small class="delivery-reason">${esc(d.motivo_mancata)}</small>`:''}</td>
            <td>${deliverySignatureAction(d, r.driver_name) || '<span class="muted">-</span>'}</td>
            <td>${note ? `<button type="button" class="btn-mini note-mini-btn" onclick="alert('${esc(String(note)).replace(/'/g,"\'")}')">Note</button>` : '<span class="muted">-</span>'}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>
  </div>`;
}

function dashboardRoutePicker(routes, selectedId, onChangeFn, label){
  return `<div class="dash-sub-route-picker">
    <label>${esc(label || 'Seleziona giro')}</label>
    <select onchange="${onChangeFn}(Number(this.value))">
      ${routes.map(x=>`<option value="${x.id}" ${Number(x.id)===Number(selectedId)?'selected':''}>${esc(x.nome || 'Giro consegne')} · ${esc(x.driver_name || 'Autista non assegnato')}</option>`).join('')}
    </select>
  </div>`;
}

function renderDashboardInProgressSubpage(routes, selectedRoute){
  const page = document.getElementById('dashboardInProgressPage');
  if(!page) return;
  if(!routes.length){
    page.innerHTML = `<div class="dash-empty-subpage"><div class="dash-empty-icon">▶</div><h2>Nessun giro in corso</h2><p>Un giro entra qui solo quando l'autista preme “Avvia giro” dal suo portale.</p><button class="btn-primary" onclick="showTab('giro')">Pianifica un giro</button></div>`;
    return;
  }
  const r = selectedRoute || routes[0];
  dashboardInProgressSelectedId = r.id;
  const rows = r.consegne || [];
  const completed = rows.filter(x=>x.delivery_status === 'completata').length;
  const missed = rows.filter(x=>x.delivery_status === 'mancata').length;
  const pending = Math.max(rows.length - completed - missed, 0);
  const progress = rows.length ? Math.round(((completed + missed) / rows.length) * 100) : routeProgressPercent(r);
  const next = rows.find(x => !['completata','mancata'].includes(x.delivery_status || 'in_attesa'));
  const unread = Number(r.unread_driver_messages || 0);
  page.innerHTML = `
    <div class="dash-sub-layout">
      <aside class="dash-sub-sidebar">
        ${dashboardRoutePicker(routes, r.id, 'openDashboardInProgressPage', 'Giro attivo')}
        <div class="dash-live-summary-card">
          <div class="dash-live-header">
            <div class="dash-live-play">▶</div>
            <div><span>Stato giro in corso</span><strong>${routes.length}</strong><small>${routes.length===1?'giro attivo':'giri attivi'}</small></div>
          </div>
          <div class="dash-live-summary-body">
            <div><span>Autista</span><strong>${esc(r.driver_name || 'Non assegnato')}</strong></div>
            <div><span>Mezzo</span><strong>${esc(r.vehicle_name || '-')}</strong></div>
            <div><span>Completate</span><strong>${completed} / ${rows.length}</strong></div>
            <div><span>Mancate</span><strong>${missed}</strong></div>
            <div><span>Da fare</span><strong>${pending}</strong></div>
            <div><span>Rientro stimato</span><strong>${esc(r.rientro_stimato_aggiornato || r.orario_rientro_stimato || '-')}</strong></div>
            <div><span>Avanzamento</span><strong>${progress}%</strong></div>
            <div class="dash-side-progress"><span style="width:${progress}%"></span></div>
            ${next?`<div class="dash-next-box"><span>Prossima consegna</span><strong>${esc(next.cliente_nome || '-')}</strong><small>${esc(next.indirizzo || '')}</small></div>`:''}
            ${unread?`<div class="dash-chat-alert strong">💬 ${unread} messagg${unread===1?'io':'i'} non lett${unread===1?'o':'i'}</div>`:''}
          </div>
          <button class="btn-light full" onclick="showTab('dashboard')">Chiudi controllo</button>
        </div>
      </aside>
      <main class="dash-sub-main">
        <section class="panel dash-sub-card">
          <div class="dash-sub-card-title"><div class="dash-sub-icon">📍</div><div><h2>Fermate del giro</h2><p>Confronto tra arrivo previsto e arrivo reale registrato dall'autista.</p></div></div>
          ${dashboardRouteSummaryCards(r, rows)}
          ${dashboardStopRowsUnified(r, 'live')}
        </section>
        <section class="panel dash-sub-card">
          <aside class="dash-admin-chat-card embedded full-width">
            <div class="dash-chat-title"><h3>Chat autista</h3><small id="dashChatStatus">Messaggi collegati a questo giro</small></div>
            <div id="dashAdminChatMessages" class="dash-admin-chat-messages"><div class="dash-empty">Caricamento chat...</div></div>
            <div class="dash-admin-chat-input">
              <textarea id="dashAdminChatInput" rows="2" placeholder="Scrivi all'autista..."></textarea>
              <button class="btn-primary" onclick="sendDashboardRouteChat(${r.id})">Invia</button>
            </div>
          </aside>
        </section>
      </main>
    </div>`;
  loadDashboardRouteChat(r.id, true);
}


function renderUnifiedRouteView(r, targetId='historyResult', context='history'){
  const target = document.getElementById(targetId);
  if(!target) return;
  const rows = r.consegne || [];
  const status = r.status || 'programmato';
  const statusLabel = r.status_label || ({programmato:'Programmato', in_corso:'In corso', completato:'Completato', bozza:'Bozza'}[status] || 'Giro');
  const icon = status === 'completato' ? '✓' : (status === 'in_corso' ? '▶' : '📅');
  target.innerHTML = `<section class="panel dash-sub-card gf-unified-route-view">
    <div class="gf-unified-route-head">
      <div class="dash-sub-card-title"><div class="dash-sub-icon">${icon}</div><div><h2>${esc(r.nome || 'Giro consegne')}</h2><p>Schermata giro unificata · ${esc(statusLabel)} · ${esc(r.data_giro || '-')}</p></div></div>
      <div class="gf-unified-route-actions">
        ${routeStatusBadge(status, statusLabel)}
        ${r.google_maps_url ? `<a target="_blank" href="${esc(r.google_maps_url)}"><button class="btn-primary">Apri Maps</button></a>` : ''}
      </div>
    </div>
    <div class="gf-route-meta-grid">
      <div><span>Autista</span><strong>${esc(r.driver_name || 'Non assegnato')}</strong></div>
      <div><span>Mezzo</span><strong>${esc(r.vehicle_name || '-')}</strong></div>
      <div><span>Partenza prevista</span><strong>${esc(r.orario_partenza || '-')}</strong></div>
      <div><span>Partenza reale</span><strong>${gfTimeFromIso(r.started_at) || '-'}</strong></div>
      <div><span>Rientro previsto</span><strong>${esc(r.orario_rientro_stimato || '-')}</strong></div>
      <div><span>Rientro reale</span><strong>${gfTimeFromIso(r.completed_at) || '-'}</strong></div>
    </div>
    ${dashboardRouteSummaryCards(r, rows)}
    <div class="gf-unified-section-title"><h3>Fermate del giro</h3><p>Confronto tra orario previsto dal software e orario reale registrato dall'autista.</p></div>
    ${dashboardStopRowsUnified(r, context)}
  </section>`;
}

async function openDashboardInProgressPage(routeId=null){
  dashboardInProgressSelectedId = routeId || dashboardInProgressSelectedId;
  showTab('dashboard-in-progress');
  await loadDashboardInProgressPage(routeId);
}

async function loadDashboardInProgressPage(routeId=null){
  const page = document.getElementById('dashboardInProgressPage');
  if(page) page.innerHTML = `<div class="dash-detail-empty"><h2>Caricamento giri in corso...</h2><p>Sto recuperando avanzamento, fermate e chat.</p></div>`;
  try{
    const rows = await api('/api/routes/operativi');
    const progress = rows.filter(r=>r.status==='in_corso');
    const selectedId = routeId || dashboardInProgressSelectedId || (progress[0] && progress[0].id);
    let selected = progress.find(r=>Number(r.id)===Number(selectedId)) || progress[0] || null;
    if(selected) selected = await api(`/api/routes/${selected.id}`);
    renderDashboardInProgressSubpage(progress, selected);
    await loadDashboardHome();
  }catch(e){
    if(page) page.innerHTML = `<div class="dash-detail-empty"><h2>Errore</h2><p>${esc(e.message)}</p></div>`;
  }
}

async function openDashboardScheduledPage(routeId=null){
  dashboardScheduledSelectedId = routeId || dashboardScheduledSelectedId;
  showTab('dashboard-scheduled');
  await loadDashboardScheduledPage(routeId);
}

async function loadDashboardScheduledPage(routeId=null){
  const page = document.getElementById('dashboardScheduledPage');
  if(page) page.innerHTML = `<div class="dash-detail-empty"><h2>Caricamento giri programmati...</h2><p>Sto recuperando i giri non ancora avviati.</p></div>`;
  try{
    const rows = await api('/api/routes/operativi');
    const scheduled = rows.filter(r=>r.status==='programmato');
    const selectedId = routeId || dashboardScheduledSelectedId || (scheduled[0] && scheduled[0].id);
    let selected = scheduled.find(r=>Number(r.id)===Number(selectedId)) || scheduled[0] || null;
    if(selected) selected = await api(`/api/routes/${selected.id}`);
    renderDashboardScheduledSubpage(scheduled, selected);
  }catch(e){ if(page) page.innerHTML = `<div class="dash-detail-empty"><h2>Errore</h2><p>${esc(e.message)}</p></div>`; }
}

function renderDashboardScheduledSubpage(routes, selectedRoute){
  const page = document.getElementById('dashboardScheduledPage');
  if(!page) return;
  if(!routes.length){
    page.innerHTML = `<div class="dash-empty-subpage"><div class="dash-empty-icon">📅</div><h2>Nessun giro programmato</h2><p>I giri salvati e assegnati compariranno qui finché l'autista non li avvia.</p><button class="btn-primary" onclick="showTab('giro')">Pianifica un giro</button></div>`;
    return;
  }
  const r = selectedRoute || routes[0];
  dashboardScheduledSelectedId = r.id;
  const rows = r.consegne || [];
  page.innerHTML = `<div class="dash-sub-layout">
    <aside class="dash-sub-sidebar">
      ${dashboardRoutePicker(routes, r.id, 'openDashboardScheduledPage', 'Giro programmato')}
      <div class="dash-live-summary-card scheduled">
        <div class="dash-live-header"><div class="dash-live-play calendar">📅</div><div><span>Giro programmato</span><strong>${esc(r.nome || 'Giro consegne')}</strong><small>${esc(r.data_giro || '-')}</small></div></div>
        <div class="dash-live-summary-body">
          <div><span>Autista</span><strong>${esc(r.driver_name || 'Non assegnato')}</strong></div>
          <div><span>Mezzo</span><strong>${esc(r.vehicle_name || '-')}</strong></div>
          <div><span>Partenza prevista</span><strong>${esc(r.orario_partenza || '-')}</strong></div>
          <div><span>Rientro stimato</span><strong>${esc(r.rientro_stimato_aggiornato || r.orario_rientro_stimato || '-')}</strong></div>
          <div><span>Consegne</span><strong>${rows.length}</strong></div>
          <div><span>Km</span><strong>${esc(r.totale_km || 0)} km</strong></div>
        </div>
        <button class="btn-primary full" onclick="showTab('giro')">Modifica dalla pianificazione</button>
      </div>
    </aside>
    <main class="dash-sub-main">
      <section class="panel dash-sub-card">
        <div class="dash-sub-card-title"><div class="dash-sub-icon">📍</div><div><h2>Fermate programmate</h2><p>Sequenza prevista prima dell'avvio del giro. La colonna reale resta vuota finché l'autista non gestisce la tappa.</p></div></div>
        ${dashboardRouteSummaryCards(r, rows)}
        ${dashboardStopRowsUnified(r, 'scheduled')}
      </section>
    </main>
  </div>`;
}

async function openDashboardCompletedPage(routeId=null){
  dashboardCompletedSelectedId = routeId || dashboardCompletedSelectedId;
  showTab('dashboard-completed');
  await loadDashboardCompletedPage(routeId);
}

async function loadDashboardCompletedPage(routeId=null){
  const page = document.getElementById('dashboardCompletedPage');
  if(page) page.innerHTML = `<div class="dash-detail-empty"><h2>Caricamento giri completati...</h2><p>Sto recuperando lo storico operativo.</p></div>`;
  try{
    const rows = await api('/api/routes');
    const completed = rows.filter(r=>r.status==='completato');
    const selectedId = routeId || dashboardCompletedSelectedId || (completed[0] && completed[0].id);
    let selected = completed.find(r=>Number(r.id)===Number(selectedId)) || completed[0] || null;
    if(selected) selected = await api(`/api/routes/${selected.id}`);
    renderDashboardCompletedSubpage(completed, selected);
  }catch(e){ if(page) page.innerHTML = `<div class="dash-detail-empty"><h2>Errore</h2><p>${esc(e.message)}</p></div>`; }
}

function renderDashboardCompletedSubpage(routes, selectedRoute){
  const page = document.getElementById('dashboardCompletedPage');
  if(!page) return;
  if(!routes.length){
    page.innerHTML = `<div class="dash-empty-subpage"><div class="dash-empty-icon">✓</div><h2>Nessun giro completato</h2><p>Quando un autista completa tutte le consegne, il giro apparirà qui.</p></div>`;
    return;
  }
  const r = selectedRoute || routes[0];
  dashboardCompletedSelectedId = r.id;
  const rows = r.consegne || [];
  const completed = rows.filter(x=>x.delivery_status === 'completata').length;
  const missed = rows.filter(x=>x.delivery_status === 'mancata').length;
  page.innerHTML = `<div class="dash-sub-layout">
    <aside class="dash-sub-sidebar">
      ${dashboardRoutePicker(routes, r.id, 'openDashboardCompletedPage', 'Giro completato')}
      <div class="dash-live-summary-card completed">
        <div class="dash-live-header"><div class="dash-live-play done">✓</div><div><span>Giro completato</span><strong>${esc(r.nome || 'Giro consegne')}</strong><small>${esc(r.data_giro || '-')}</small></div></div>
        <div class="dash-live-summary-body">
          <div><span>Autista</span><strong>${esc(r.driver_name || 'Non assegnato')}</strong></div>
          <div><span>Mezzo</span><strong>${esc(r.vehicle_name || '-')}</strong></div>
          <div><span>Completate</span><strong>${completed} / ${rows.length}</strong></div>
          <div><span>Mancate</span><strong>${missed}</strong></div>
          <div><span>Rientro stimato finale</span><strong>${esc(r.rientro_stimato_aggiornato || r.orario_rientro_stimato || '-')}</strong></div>
          <div><span>Km</span><strong>${esc(r.totale_km || 0)} km</strong></div>
        </div>
        <button class="btn-light full" onclick="showTab('storico')">Apri storico completo</button>
      </div>
    </aside>
    <main class="dash-sub-main">
      <section class="panel dash-sub-card">
        <div class="dash-sub-card-title"><div class="dash-sub-icon">✓</div><div><h2>Fermate completate</h2><p>Stato finale con arrivo previsto, arrivo reale e differenza per ogni cliente.</p></div></div>
        ${dashboardRouteSummaryCards(r, rows)}
        ${dashboardStopRowsUnified(r, 'completed')}
      </section>
    </main>
  </div>`;
}


// -----------------------------------------------------------------------------
// Informativa cookie tecnici Dashboard
// -----------------------------------------------------------------------------
function showCookieNoticeIfNeeded(){
  const notice = document.getElementById("cookieNotice");
  if(!notice) return;
  if(localStorage.getItem("gf_cookie_notice_ok") === "1") return;
  // Mostra il banner solo nell'area gestionale, non mentre l'utente è ancora nella schermata login.
  const app = document.getElementById("app");
  if(app && app.classList.contains("hidden")) return;
  notice.classList.remove("hidden");
}

function acceptCookieNotice(){
  localStorage.setItem("gf_cookie_notice_ok", "1");
  const notice = document.getElementById("cookieNotice");
  if(notice) notice.classList.add("hidden");
}

window.addEventListener("DOMContentLoaded", () => {
  bindLoginRecoveryActions();
  setTimeout(showCookieNoticeIfNeeded, 900);
});


/* ------------------------------------------------------------------
   v29 - Profilo azienda + onboarding iniziale
------------------------------------------------------------------ */
let onboardingStateV29 = null;

function setCompanyLogoPreview(){
  const hidden = document.getElementById("companyLogoUrl");
  const preview = document.getElementById("companyLogoPreview");
  if(!preview) return;
  const logo = hidden?.value || "";
  const name = val("companyNameInput") || localStorage.getItem("girofacile_profile_name") || "GF";
  const initials = (name || "GF").trim().split(/\s+/).slice(0,2).map(x=>x[0]).join("").toUpperCase() || "GF";
  preview.innerHTML = logo ? `<img src="${logo}" alt="Logo azienda">` : initials;
}

async function loadCompanyProfile(showToast=false){
  try{
    const data = await api("/api/company-profile");
    set("companyNameInput", data.company_name || "");
    set("companyEmailInput", data.company_email || "");
    set("companyPhoneInput", data.company_phone || "");
    set("companyVatInput", data.company_vat || "");
    set("companyAddressInput", data.company_address || "");
    set("companyCityInput", data.company_city || "");
    set("companyZipInput", data.company_zip || "");
    set("companyCountryInput", data.company_country || "Italia");
    set("companyFiscalCodeInput", data.company_fiscal_code || "");
    set("companyPecInput", data.company_pec || "");
    set("companySdiInput", data.company_sdi || "");
    set("companyLegalAddressInput", data.company_legal_address || "");
    set("companyBillingAddressInput", data.company_billing_address || "");
    set("companyActivityTypeInput", data.company_activity_type || "");
    set("companySizeInput", data.company_size || "");
    set("companyDailyDeliveriesInput", data.daily_deliveries || "");
    setSectorConfigV47(data);
    fillSectorSelectV47("companySectorInput", data.company_sector || "");
    set("companyLogoUrl", data.company_logo_url || "");
    setCompanyLogoPreview();
    if(data.company_name) localStorage.setItem("girofacile_profile_name", data.company_name);
    // L'email aziendale è separata dall'email di accesso account e non deve sovrascriverla.
    if(data.company_logo_url) localStorage.setItem("girofacile_profile_photo", data.company_logo_url);
    loadProfilePanel();
    if(showToast) toast("Profilo azienda aggiornato");
    return data;
  }catch(e){
    console.warn("loadCompanyProfile", e);
    return null;
  }
}

async function saveCompanyProfile(){
  try{
    const payload = {
      company_name: val("companyNameInput"),
      company_email: val("companyEmailInput"),
      company_phone: val("companyPhoneInput"),
      company_vat: val("companyVatInput"),
      company_address: val("companyAddressInput"),
      company_city: val("companyCityInput"),
      company_zip: val("companyZipInput"),
      company_country: val("companyCountryInput") || "Italia",
      company_fiscal_code: val("companyFiscalCodeInput"),
      company_pec: val("companyPecInput"),
      company_sdi: val("companySdiInput"),
      company_legal_address: val("companyLegalAddressInput"),
      company_billing_address: val("companyBillingAddressInput"),
      company_activity_type: val("companyActivityTypeInput"),
      company_size: val("companySizeInput"),
      daily_deliveries: val("companyDailyDeliveriesInput"),
      company_logo_url: val("companyLogoUrl")
    };
    const res = await api("/api/company-profile", {method:"PUT", body:JSON.stringify(payload)});
    await loadCompanyProfile(false);
    await loadOnboardingStatus(false);
    toast("Profilo azienda salvato");
  }catch(e){
    alert(e.message || "Errore salvataggio profilo azienda");
  }
}

function onboardingStepHtml(step){
  const icon = step.done ? "✓" : "•";
  return `<button class="onboarding-step-v29 ${step.done ? 'done' : ''}" onclick="showTab('${esc(step.tab)}'); closeOnboardingPanel();">
    <span>${icon}</span>
    <strong>${esc(step.label)}</strong>
    <small>${step.done ? 'Completato' : 'Da completare'}</small>
  </button>`;
}

function renderOnboardingStatus(data){
  onboardingStateV29 = data;
  if(!data) return;
  const label = `${data.progress || 0}/${data.total || 0}`;
  const pct = data.percent || 0;
  const setText=(id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
  setText("onboardingProgressLabel", label);
  setText("onboardingModalProgressLabel", label);
  ["onboardingProgressFill","onboardingModalProgressFill"].forEach(id=>{ const el=document.getElementById(id); if(el) el.style.width = pct + "%"; });
  const html = (data.steps || []).map(onboardingStepHtml).join("");
  const list = document.getElementById("onboardingStepsList"); if(list) list.innerHTML = html;
  const modalList = document.getElementById("onboardingModalSteps"); if(modalList) modalList.innerHTML = html;
  const layout = document.getElementById("companyLayoutV29");
  const badge = document.getElementById("companyConfiguredBadge");
  const guideBtn = document.getElementById("showOnboardingBtn");
  const done = !!data.completed;
  if(layout) layout.classList.toggle("company-completed-v40", done);
  if(badge) badge.classList.toggle("hidden", !done);
  if(guideBtn) guideBtn.classList.toggle("hidden", done);
}

async function loadOnboardingStatus(showIfNeeded=false){
  try{
    const data = await api("/api/onboarding/status");
    renderOnboardingStatus(data);
    if(showIfNeeded && !data.completed && !data.dismissed){
      setTimeout(()=>openOnboardingPanel(), 600);
    }
    return data;
  }catch(e){
    console.warn("loadOnboardingStatus", e);
    return null;
  }
}

function openOnboardingPanel(){
  loadOnboardingStatus(false);
  const el=document.getElementById("onboardingOverlay");
  if(el) el.classList.remove("hidden");
}
function closeOnboardingPanel(ev){
  if(ev && ev.target && ev.target.id !== "onboardingOverlay") return;
  const el=document.getElementById("onboardingOverlay");
  if(el) el.classList.add("hidden");
}
async function dismissOnboarding(){
  try{ await api("/api/onboarding/dismiss", {method:"POST", body:"{}"}); }catch(e){}
  closeOnboardingPanel();
}
async function completeOnboarding(){
  try{
    await api("/api/onboarding/complete", {method:"POST", body:"{}"});
    await loadOnboardingStatus(false);
    closeOnboardingPanel();
    toast("Configurazione iniziale completata");
  }catch(e){ alert(e.message || "Errore aggiornamento onboarding"); }
}

// -----------------------------------------------------------------------------
// V30 - Notifiche interne Dashboard
// -----------------------------------------------------------------------------
let notificationsCacheV30 = [];
let notificationsPollV30 = null;

function notificationTimeLabelV30(value){
  if(!value) return "";
  const d = new Date(value);
  if(Number.isNaN(d.getTime())) return "";
  const diff = Date.now() - d.getTime();
  const min = Math.floor(diff/60000);
  if(min < 1) return "Adesso";
  if(min < 60) return `${min} min fa`;
  const h = Math.floor(min/60);
  if(h < 24) return `${h} h fa`;
  return d.toLocaleDateString("it-IT", {day:"2-digit", month:"2-digit"});
}

function notificationIconV30(type){
  const map = {
    chat: "💬",
    agent_customer: "👤",
    route_started: "▶️",
    route_completed: "✅",
    delivery_missed: "⚠️",
    address: "📍"
  };
  return map[type] || "🔔";
}

async function loadNotificationsV30(openDropdown=false){
  const bell = document.getElementById("notificationBellBtn");
  if(!bell) return;
  bell.classList.remove("hidden");
  try{
    const data = await api("/api/notifications?limit=25");
    notificationsCacheV30 = data.items || [];
    renderNotificationBadgeV30(data.unread || 0);
    renderNotificationsDropdownV30(data.unread || 0);
    if(openDropdown) showNotificationsDropdownV30(true);
  }catch(e){
    // Non bloccare mai la dashboard per le notifiche.
    console.warn("Errore notifiche", e);
  }
}

function renderNotificationBadgeV30(unread){
  const badge = document.getElementById("notificationBadge");
  if(!badge) return;
  if(unread > 0){
    badge.textContent = unread > 99 ? "99+" : String(unread);
    badge.classList.remove("hidden");
  }else{
    badge.classList.add("hidden");
  }
}

function renderNotificationsDropdownV30(unread){
  const list = document.getElementById("notificationList");
  const sub = document.getElementById("notificationSubtitle");
  if(sub) sub.textContent = unread ? `${unread} da leggere` : "Tutto aggiornato";
  if(!list) return;
  if(!notificationsCacheV30.length){
    list.innerHTML = `<div class="notification-empty-v30">Nessuna notifica operativa.</div>`;
    return;
  }
  list.innerHTML = notificationsCacheV30.map(n=>{
    const unreadCls = n.is_read ? "" : "unread";
    const action = n.action_tab ? `<button onclick="openNotificationActionV30(${n.id}, '${esc(n.action_tab)}')">${esc(n.action_label || 'Apri')}</button>` : "";
    return `<div class="notification-item-v30 ${unreadCls}">
      <div class="notification-icon-v30">${notificationIconV30(n.type)}</div>
      <div class="notification-body-v30">
        <div class="notification-title-v30"><strong>${esc(n.title || 'Notifica')}</strong><small>${esc(notificationTimeLabelV30(n.created_at))}</small></div>
        <p>${esc(n.message || '')}</p>
        <div class="notification-actions-v30">
          ${action}
          ${!n.is_read ? `<button class="light" onclick="markNotificationReadV30(${n.id})">Segna letta</button>` : ""}
        </div>
      </div>
    </div>`;
  }).join("");
}

function showNotificationsDropdownV30(show){
  const dd = document.getElementById("notificationDropdown");
  if(dd) dd.classList.toggle("hidden", !show);
}

function toggleNotificationsDropdown(){
  const dd = document.getElementById("notificationDropdown");
  const willOpen = dd && dd.classList.contains("hidden");
  showNotificationsDropdownV30(!!willOpen);
  if(willOpen) loadNotificationsV30(false);
}

async function markNotificationReadV30(id){
  try{
    await api(`/api/notifications/${id}/read`, {method:"POST", body:"{}"});
    await loadNotificationsV30(true);
  }catch(e){ toast("Errore notifica: " + (e.message || "Errore")); }
}

async function markAllNotificationsRead(){
  try{
    await api("/api/notifications/read-all", {method:"POST", body:"{}"});
    await loadNotificationsV30(true);
  }catch(e){ toast("Errore notifiche: " + (e.message || "Errore")); }
}

async function openNotificationActionV30(id, tab){
  try{ await api(`/api/notifications/${id}/read`, {method:"POST", body:"{}"}); }catch(e){}
  showNotificationsDropdownV30(false);
  showTab(tab);
  setTimeout(()=>loadNotificationsV30(false), 250);
}

document.addEventListener("click", function(e){
  const center = e.target.closest && e.target.closest(".notification-center-v30");
  if(!center) showNotificationsDropdownV30(false);
});

window.toggleNotificationsDropdown = toggleNotificationsDropdown;
window.markAllNotificationsRead = markAllNotificationsRead;
window.markNotificationReadV30 = markNotificationReadV30;
window.openNotificationActionV30 = openNotificationActionV30;


// -----------------------------------------------------------------------------
// v31 - Registro attività aziendale
// -----------------------------------------------------------------------------
function activityIconV31(type){
  const map = {company:"🏢", onboarding:"✅", agent:"🧑‍💼", driver:"🚚", customer:"👥", address:"📍", route:"🗺️", delivery:"📦", chat:"💬"};
  return map[type] || "•";
}

function activityDateV31(value){
  if(!value) return "";
  try{
    const d = new Date(value);
    return d.toLocaleString("it-IT", {day:"2-digit", month:"2-digit", year:"numeric", hour:"2-digit", minute:"2-digit"});
  }catch(e){ return String(value); }
}

async function loadActivityLogV31(){
  const box = document.getElementById("activityListV31");
  if(!box) return;
  box.innerHTML = `<div class="activity-empty-v31">Caricamento attività...</div>`;
  const type = document.getElementById("activityTypeFilter")?.value || "";
  const severity = document.getElementById("activitySeverityFilter")?.value || "";
  const params = new URLSearchParams({limit:"120"});
  if(type) params.set("type", type);
  if(severity) params.set("severity", severity);
  try{
    const data = await api("/api/activity?" + params.toString());
    renderActivityLogV31(data.items || []);
  }catch(e){
    box.innerHTML = `<div class="activity-empty-v31 danger">Errore caricamento registro attività: ${esc(e.message || "Errore")}</div>`;
  }
}

function renderActivityLogV31(items){
  const box = document.getElementById("activityListV31");
  if(!box) return;
  if(!items.length){
    box.innerHTML = `<div class="activity-empty-v31">Nessuna attività trovata con i filtri selezionati.</div>`;
    return;
  }
  box.innerHTML = items.map(x=>{
    const safeTab = esc(x.action_tab || "");
    const action = x.action_tab ? `<button type="button" onclick="openActivityTargetV31('${safeTab}')">Apri</button>` : "";
    const typeLabel = String(x.type || 'evento').replaceAll('_',' ');
    const title = x.count && x.count > 1 ? `${x.title || 'Attività'} · ${x.count}` : (x.title || 'Attività');
    return `<article class="activity-item-v31 ${esc(x.severity || 'info')}">
      <div class="activity-icon-v31" aria-hidden="true">${activityIconV31(x.type)}</div>
      <div class="activity-body-v31">
        <div class="activity-row-v31">
          <strong>${esc(title)}</strong>
          <small>${esc(activityDateV31(x.created_at))}</small>
        </div>
        <p>${esc(x.description || '')}</p>
        <div class="activity-meta-v31">
          <span>${esc(x.actor_name || 'Sistema')}</span>
          <span>${esc(typeLabel)}</span>
          <span class="sev ${esc(x.severity || 'info')}">${esc(labelSeverityV31(x.severity))}</span>
        </div>
      </div>
      <div class="activity-actions-v31">${action}</div>
    </article>`;
  }).join("");
}

function labelSeverityV31(sev){
  if(sev === "success") return "Completato";
  if(sev === "warning") return "Da controllare";
  if(sev === "danger") return "Critico";
  return "Info";
}

function openActivityTargetV31(tab){
  showTab(tab);
}

window.loadActivityLogV31 = loadActivityLogV31;
window.openActivityTargetV31 = openActivityTargetV31;

// -----------------------------------------------------------------------------
// v49 - Account legato al settore + Dashboard iniziale pulita
// -----------------------------------------------------------------------------
let gfWorkspaceOperationalV49 = true;
const GF_COMMON_TABS_V49 = new Set(["dashboard", "company", "activity", "settings"]);
const GF_OPERATIONAL_TABS_V49 = new Set([
  "giro", "clienti", "agenti", "report", "depositi", "mezzi", "autisti", "storico",
  "chat-autisti", "integrations", "dashboard-scheduled", "dashboard-in-progress", "dashboard-completed"
]);

function isWorkspaceOperationalV49(){
  return !!gfWorkspaceOperationalV49;
}

function applyWorkspaceStateV49(operational){
  gfWorkspaceOperationalV49 = !!operational;
  document.body.classList.toggle("workspace-empty-v49-active", !gfWorkspaceOperationalV49);
  document.querySelectorAll("[data-workspace-operational='1']").forEach(el => {
    el.classList.toggle("hidden", !gfWorkspaceOperationalV49);
    el.style.display = gfWorkspaceOperationalV49 ? "" : "none";
  });
  document.querySelectorAll("[data-workspace-common='1']").forEach(el => {
    el.classList.remove("hidden");
    el.style.display = "";
  });
  const empty = document.getElementById("workspaceEmptyDashboardV49");
  if(empty) empty.classList.toggle("hidden", gfWorkspaceOperationalV49);
  renderWorkspaceIntroV49();
}

function renderWorkspaceIntroV49(){
  const nameEl = document.getElementById("workspaceSectorNameV49");
  const subEl = document.getElementById("workspaceSectorSubtitleV49");
  if(nameEl) nameEl.textContent = gfSectorConfigV47?.name || "Settore non configurato";
  if(subEl) subEl.textContent = gfSectorConfigV47?.subtitle || "GiroFacile preparerà interfaccia, testi e funzioni in base al settore aziendale.";
}

function ensureSupportModalV60(){
  if(document.getElementById("supportTicketModalV60")) return;
  const wrap = document.createElement("div");
  wrap.id = "supportTicketModalV60";
  wrap.className = "support-modal-v60 hidden";
  wrap.innerHTML = `
    <div class="support-card-v60">
      <div class="support-head-v60">
        <div>
          <strong>Invia ticket assistenza</strong>
          <small id="supportTicketSubtitleV60">Descrivi il problema al supporto GiroFacile.</small>
        </div>
        <button type="button" onclick="closeSupportTicketModalV60()">×</button>
      </div>
      <div class="support-body-v60">
        <input type="hidden" id="supportTicketErrorIdV60">
        <label>Oggetto</label>
        <input id="supportTicketSubjectV60" type="text" placeholder="Es. Errore calcolo percorso">
        <label>Descrizione problema</label>
        <textarea id="supportTicketMessageV60" rows="6" placeholder="Spiega cosa stavi facendo, quale pulsante hai cliccato e cosa è successo..."></textarea>
        <label class="support-check-v60">
          <input id="supportTicketNotifyV60" type="checkbox" checked>
          Avvisami via email quando il problema è risolto
        </label>
        <div id="supportTicketLinkedErrorV60" class="support-linked-error-v60 hidden"></div>
        <button type="button" id="supportTicketAiBtnV67" class="btn-secondary hidden" onclick="generateSupportTicketTextAIv67()">Genera testo assistito AI</button>
        <small id="supportTicketAiHintV67" class="hidden" style="color:var(--muted)">Disponibile solo per ticket collegati a un errore sistema e piani Business/Pro.</small>
      </div>
      <div class="support-actions-v60">
        <button type="button" class="btn-secondary" onclick="closeSupportTicketModalV60()">Annulla</button>
        <button type="button" class="btn-primary" onclick="submitSupportTicketV60()">Invia ticket</button>
      </div>
    </div>`;
  document.body.appendChild(wrap);
}

function openSupportPanelV49(errorId=null, suggestedMessage=""){
  ensureSupportModalV60();
  const modal = document.getElementById("supportTicketModalV60");
  const subject = document.getElementById("supportTicketSubjectV60");
  const msg = document.getElementById("supportTicketMessageV60");
  const hidden = document.getElementById("supportTicketErrorIdV60");
  const linked = document.getElementById("supportTicketLinkedErrorV60");
  hidden.value = errorId || "";
  subject.value = errorId ? `Problema tecnico collegato all'errore #${errorId}` : "Richiesta assistenza";
  msg.value = suggestedMessage || "";
  const aiBtn = document.getElementById("supportTicketAiBtnV67");
  const aiHint = document.getElementById("supportTicketAiHintV67");
  if(errorId){
    linked.classList.remove("hidden");
    linked.textContent = `Questo ticket verrà collegato all'errore di sistema #${errorId}. Quando il ticket sarà chiuso, anche l'errore verrà segnato come risolto.`;
    aiBtn?.classList.remove("hidden");
    aiHint?.classList.remove("hidden");
  }else{
    linked.classList.add("hidden");
    linked.textContent = "";
    aiBtn?.classList.add("hidden");
    aiHint?.classList.add("hidden");
  }
  modal.classList.remove("hidden");
}

function closeSupportTicketModalV60(){
  document.getElementById("supportTicketModalV60")?.classList.add("hidden");
}

async function generateSupportTicketTextAIv67(){
  const errorIdRaw = document.getElementById("supportTicketErrorIdV60")?.value || "";
  if(!errorIdRaw){ alert("Testo assistito disponibile solo per ticket collegati a un errore sistema."); return; }
  const btn = document.getElementById("supportTicketAiBtnV67");
  const msg = document.getElementById("supportTicketMessageV60");
  const subject = document.getElementById("supportTicketSubjectV60");
  const old = btn?.textContent || "Genera testo assistito AI";
  if(btn) btn.textContent = "Genero testo...";
  try{
    const r = await api("/api/support/tickets/assist-text", {method:"POST", body:JSON.stringify({system_error_id: parseInt(errorIdRaw)})});
    if(subject && r.subject) subject.value = r.subject;
    if(msg){ msg.value = r.message || r.text || ""; msg.focus(); }
    toast("Testo assistito inserito. Puoi modificarlo prima di inviare il ticket.");
  }catch(e){ alert(e.message || "Impossibile generare il testo assistito."); }
  finally{ if(btn) btn.textContent = old; }
}

async function submitSupportTicketV60(){
  const subject = document.getElementById("supportTicketSubjectV60")?.value?.trim() || "Richiesta assistenza";
  const message = document.getElementById("supportTicketMessageV60")?.value?.trim() || "";
  const errorIdRaw = document.getElementById("supportTicketErrorIdV60")?.value || "";
  const notify = !!document.getElementById("supportTicketNotifyV60")?.checked;
  if(!message){ alert("Inserisci una descrizione del problema."); return; }
  try{
    const payload = {
      oggetto: subject,
      messaggio: message,
      notify_on_resolution: notify,
      tipo: errorIdRaw ? "errore_sistema" : "supporto",
      system_error_id: errorIdRaw ? parseInt(errorIdRaw) : null
    };
    const r = await api("/api/support/tickets", {method:"POST", body:JSON.stringify(payload)});
    closeSupportTicketModalV60();
    toast(`Ticket #${r.ticket?.id || ""} inviato al supporto.`);
  }catch(e){ alert(e.message || "Impossibile inviare il ticket."); }
}

function blockOperationalTabV49(name){
  if(isWorkspaceOperationalV49()) return false;
  if(!GF_OPERATIONAL_TABS_V49.has(name)) return false;
  showTab("dashboard");
  toast("Area operativa non ancora configurata. Completa prima profilo azienda e impostazioni.");
  return true;
}

const gfOriginalShowTabV49 = window.showTab;
window.showTab = function(name){
  if(blockOperationalTabV49(name)) return;
  gfOriginalShowTabV49(name);
  if(name === "dashboard") applyWorkspaceStateV49(gfWorkspaceOperationalV49);
};

const gfOriginalRenderOnboardingStatusV49 = window.renderOnboardingStatus;
window.renderOnboardingStatus = function(data){
  gfOriginalRenderOnboardingStatusV49(data);
  if(data && typeof data.workspace_operational !== "undefined"){
    applyWorkspaceStateV49(!!data.workspace_operational);
  }else if(data && typeof data.completed !== "undefined"){
    applyWorkspaceStateV49(!!data.completed);
  }
};

const gfOriginalSetSectorConfigV49 = window.setSectorConfigV47;
window.setSectorConfigV47 = function(data){
  gfOriginalSetSectorConfigV49(data);
  renderWorkspaceIntroV49();
};

const gfOriginalCheckLoginV49 = window.checkLogin;
window.checkLogin = async function(){
  await gfOriginalCheckLoginV49();
  if(currentSessionUser && typeof currentSessionUser.workspace_operational !== "undefined"){
    applyWorkspaceStateV49(!!currentSessionUser.workspace_operational);
  }
};


// -----------------------------------------------------------------------------
// v50/v51/v53/v54/v55 - Settori verticali operativi
// Distribuzione mantiene la Dashboard originale; Logistica, E-commerce, Food delivery, Transfer
// e Farmaceutico/Sanitario hanno una Dashboard dedicata. Gli altri settori restano ancora nella Dashboard pulita.
// -----------------------------------------------------------------------------
const GF_SECTOR_OPERATIONAL_KEYS_V50 = new Set(["distribution", "logistics", "ecommerce", "food_delivery", "transfer", "healthcare"]);
const GF_VERTICAL_LABELS_V51 = {
  logistics: {
    bodyClass: "sector-logistics-v50",
    dashboardTitle: "Dashboard logistica",
    dashboardSubtitle: "Panoramica di spedizioni, ritiri, consegne e tentativi dei corrieri.",
    newRoute: "+ Pianifica spedizioni",
    planning: "Pianificazione ritiri/consegne",
    customers: "Spedizioni / Destinatari",
    vehicles: "Mezzi",
    drivers: "Corrieri",
    history: "Storico spedizioni",
    reports: "Report logistici",
    chat: "Chat corrieri",
    integrations: "Integrazioni"
  },
  ecommerce: {
    bodyClass: "sector-ecommerce-v51",
    dashboardTitle: "Dashboard e-commerce",
    dashboardSubtitle: "Centro ordini per shop online, consegne proprie, tracking, contrassegni e resi.",
    newRoute: "+ Pianifica ordini",
    planning: "Giri consegna ordini",
    customers: "Ordini / Destinatari",
    vehicles: "Mezzi",
    drivers: "Corrieri",
    history: "Storico ordini",
    reports: "Report e-commerce",
    chat: "Chat corrieri",
    integrations: "Integrazioni"
  },
  food_delivery: {
    bodyClass: "sector-food-v53",
    dashboardTitle: "Dashboard food delivery",
    dashboardSubtitle: "Centro operativo per ordini food, rider, punti vendita, orari di ritiro e consegna.",
    newRoute: "+ Nuovo turno rider",
    planning: "Turni e consegne food",
    customers: "Ordini / Clienti finali",
    vehicles: "Mezzi rider",
    drivers: "Rider",
    history: "Storico ordini food",
    reports: "Report food delivery",
    chat: "Chat rider"
  },
  transfer: {
    bodyClass: "sector-transfer-v54",
    dashboardTitle: "Dashboard transfer",
    dashboardSubtitle: "Centro operativo per prenotazioni, corse, autisti, veicoli e tratte su appuntamento.",
    newRoute: "+ Nuova corsa",
    planning: "Pianificazione transfer",
    customers: "Clienti / Passeggeri",
    vehicles: "Veicoli",
    drivers: "Autisti",
    history: "Storico corse",
    reports: "Report transfer",
    chat: "Chat autisti"
  },
  healthcare: {
    bodyClass: "sector-healthcare-v55",
    dashboardTitle: "Dashboard sanitario",
    dashboardSubtitle: "Centro operativo per consegne sanitarie, priorità, firma obbligatoria, tracciabilità e conformità.",
    newRoute: "+ Nuova consegna sanitaria",
    planning: "Pianificazione sanitaria",
    customers: "Punti consegna",
    vehicles: "Veicoli",
    drivers: "Operatori",
    history: "Storico consegne sanitarie",
    reports: "Report conformità",
    chat: "Chat operatori"
  }
};

function gfCurrentSectorKeyV50(){
  return (gfSectorConfigV47 && gfSectorConfigV47.key) ? gfSectorConfigV47.key : "other";
}
function gfSectorOperationalActiveV50(){
  return GF_SECTOR_OPERATIONAL_KEYS_V50.has(gfCurrentSectorKeyV50());
}
function gfIsLogisticsV50(){
  return gfCurrentSectorKeyV50() === "logistics";
}
function setNavTextV50(tab, text){
  const btn = document.querySelector(`.nav-item[data-tab="${tab}"]`);
  if(!btn || !text) return;
  const icon = btn.querySelector(".nav-svg")?.outerHTML || "";
  const badge = btn.querySelector(".side-chat-badge")?.outerHTML || "";
  btn.innerHTML = `${icon} ${esc(text)} ${badge}`.trim();
}
function gfVerticalLabelsV51(){
  return GF_VERTICAL_LABELS_V51[gfCurrentSectorKeyV50()] || null;
}
function applyTransferMenuCleanupV83(sectorNow){
  const isTransfer = sectorNow === "transfer" && isWorkspaceOperationalV49();

  // Nel settore Transfer queste pagine restano disponibili nel software, ma non
  // occupano spazio nel menu principale perché sono raggiungibili dai flussi
  // dedicati, dalla Dashboard o dal popup account.
  const desktopTabsToHide = ["giro", "clienti", "depositi", "storico", "settings"];
  desktopTabsToHide.forEach(tab => {
    const el = document.querySelector(`.side-nav .nav-item[data-tab="${tab}"]`);
    if(el) el.style.display = isTransfer ? "none" : "";
  });


  // Menu mobile “Altro”: stessa pulizia della sidebar desktop.
  const mobileHiddenTargets = ["company-noop"]; // mantiene Azienda visibile
  const hiddenOnclickParts = [
    "mobileGoTabV62('giro')",
    "mobileGoTabV62('clienti')",
    "mobileGoTabV62('depositi')",
    "mobileGoTabV62('storico')",
    "mobileGoTabV62('settings')"
  ];
  document.querySelectorAll('#gfMobileMoreMenuV62 > button').forEach(btn => {
    const handler = btn.getAttribute('onclick') || '';
    const shouldHide = hiddenOnclickParts.some(part => handler.includes(part));
    if(shouldHide) btn.style.display = isTransfer ? "none" : "";
  });

  // Navigazione inferiore mobile specifica per Transfer.
  const bottom = document.getElementById('gfMobileBottomNavV62');
  if(bottom){
    const buttons = Array.from(bottom.querySelectorAll(':scope > button'));
    if(buttons.length >= 5){
      if(isTransfer){
        buttons[0].setAttribute('onclick', "mobileGoTabV62('dashboard')");
        buttons[0].innerHTML = '<span>▦</span><strong>Dashboard</strong>';
        buttons[1].setAttribute('onclick', "mobileGoTabV62('transfer-bookings')");
        buttons[1].innerHTML = '<span>▣</span><strong>Prenotazioni</strong>';
        buttons[2].setAttribute('onclick', "openTransferBookingModalV79()");
        buttons[2].innerHTML = '<span>+</span><strong>Nuova</strong>';
        buttons[3].setAttribute('onclick', "mobileGoTabV62('transfer-planning')");
        buttons[3].innerHTML = '<span>▤</span><strong>Planning</strong>';
      }else{
        buttons[0].setAttribute('onclick', "mobileGoTabV62('dashboard')");
        buttons[0].innerHTML = '<span>▦</span><strong>Dashboard</strong>';
        buttons[1].setAttribute('onclick', "mobileGoTabV62('dashboard-in-progress')");
        buttons[1].innerHTML = '<span>▰</span><strong>Giri</strong>';
        buttons[2].setAttribute('onclick', "mobileGoTabV62('giro')");
        buttons[2].innerHTML = '<span>+</span><strong>Nuovo giro</strong>';
        buttons[3].setAttribute('onclick', "mobileGoTabV62('activity')");
        buttons[3].innerHTML = '<span>▤</span><strong>Attività</strong>';
      }
    }
  }
}

function applyLogisticsWorkspaceV50(){
  const labels = gfVerticalLabelsV51();
  const sectorNow = gfCurrentSectorKeyV50();
  document.body.classList.toggle("sector-logistics-v50", sectorNow === "logistics");
  document.body.classList.toggle("sector-ecommerce-v51", sectorNow === "ecommerce");
  document.body.classList.toggle("sector-food-v53", sectorNow === "food_delivery");
  document.body.classList.toggle("sector-transfer-v54", sectorNow === "transfer");
  document.body.classList.toggle("sector-healthcare-v55", sectorNow === "healthcare");
  document.querySelectorAll('[data-sector-only="ecommerce"]').forEach(el => {
    const show = sectorNow === "ecommerce" && isWorkspaceOperationalV49();
    el.classList.toggle("hidden", !show);
    el.style.display = show ? "" : "none";
  });
  document.querySelectorAll('[data-sector-only="transfer"]').forEach(el => {
    const show = sectorNow === "transfer" && isWorkspaceOperationalV49();
    el.classList.toggle("hidden", !show);
    el.style.display = show ? "" : "none";
  });
  ["gfMobileTransferPortalBtnV78","gfMobileTransferBookingsBtnV79","gfMobileTransferPlanningBtnV79","gfMobileTransferSettingsBtnV79"].forEach(id=>{
    const el=document.getElementById(id); if(el) el.classList.toggle("hidden", !(sectorNow === "transfer" && isWorkspaceOperationalV49()));
  });
  refreshAdminDriverNavV79();
  applyTransferMenuCleanupV83(sectorNow);

  const heroTitle = document.querySelector("#tab-dashboard .dash-hero-row h1");
  const heroSubtitle = document.querySelector("#tab-dashboard .dash-hero-row p");
  const heroBtn = document.querySelector("#tab-dashboard .dash-hero-row .btn-primary");
  if(labels){
    if(heroTitle) heroTitle.textContent = labels.dashboardTitle;
    if(heroSubtitle) heroSubtitle.textContent = labels.dashboardSubtitle;
    if(heroBtn) heroBtn.textContent = labels.newRoute;
    setNavTextV50("giro", labels.planning);
    setNavTextV50("clienti", labels.customers);
    setNavTextV50("mezzi", labels.vehicles);
    setNavTextV50("autisti", labels.drivers);
    setNavTextV50("storico", labels.history);
    setNavTextV50("report", labels.reports);
    setNavTextV50("chat-autisti", labels.chat);
    if(labels.integrations) setNavTextV50("integrations", labels.integrations);
    const agentBtn = document.querySelector('.nav-item[data-tab="agenti"]');
    if(agentBtn) agentBtn.style.display = "none";
  }else{
    const agentBtn = document.querySelector('.nav-item[data-tab="agenti"]');
    if(agentBtn && isWorkspaceOperationalV49()) agentBtn.style.display = "";
  }
  renderLogisticsDashboardV50();
}

function renderLogisticsDashboardV50(routes=[]){
  const host = document.getElementById("logisticsDashboardV50");
  if(!host) return;
  const sector = gfCurrentSectorKeyV50();
  if(sector !== "logistics" && sector !== "ecommerce" && sector !== "food_delivery" && sector !== "transfer" && sector !== "healthcare"){
    host.classList.add("hidden");
    host.innerHTML = "";
    return;
  }
  host.classList.remove("hidden");
  const today = todayIso();
  const list = Array.isArray(routes) ? routes : [];
  const todayRoutes = list.filter(r => r.data_giro === today);
  const activeRoutes = list.filter(r => r.status === "in_corso");
  const scheduled = list.filter(r => r.status === "programmato");
  const completed = todayRoutes.filter(r => r.status === "completato");
  const itemsToday = todayRoutes.reduce((sum,r)=>sum + Number(r.consegne_count || (r.consegne ? r.consegne.length : 0) || 0), 0);
  const missed = list.reduce((sum,r)=>sum + Number(r.missed_count || 0), 0);
  const vehiclesBusy = new Set(activeRoutes.map(r=>r.vehicle_id || r.vehicle_name).filter(Boolean)).size;
  const driversBusy = new Set(activeRoutes.map(r=>r.driver_id || r.driver_name).filter(Boolean)).size;


  if(sector === "healthcare"){
    host.innerHTML = `
      <section class="vertical-dashboard-v51 healthcare-dashboard-v55">
        <div class="vertical-head-v51 healthcare-head-v55">
          <span>Modulo verticale</span>
          <h2>Centro operativo sanitario</h2>
          <p>Interfaccia dedicata a farmacie, laboratori, materiale sanitario e consegne tracciate: priorità, orari tassativi, firma obbligatoria, temperatura e conformità.</p>
        </div>
        <div class="vertical-kpi-grid-v51 healthcare-kpi-grid-v55">
          <div><small>Consegne oggi</small><strong>${itemsToday}</strong><span>Sanitarie pianificate</span></div>
          <div><small>In consegna</small><strong>${activeRoutes.length}</strong><span>Operatori attivi</span></div>
          <div><small>Urgenti</small><strong>${scheduled.length}</strong><span>Da avviare / assegnare</span></div>
          <div><small>Completate con firma</small><strong>${completed.length}</strong><span>Prove consegna raccolte</span></div>
          <div><small>Non conformità</small><strong>${missed}</strong><span>Da verificare</span></div>
          <div><small>Risorse in uso</small><strong>${driversBusy}/${vehiclesBusy}</strong><span>Operatori / veicoli</span></div>
        </div>
        <div class="vertical-modules-v51 healthcare-modules-v55">
          <button onclick="showTab('clienti')"><b>Punti consegna</b><span>Farmacie, laboratori, referenti sanitari e destinatari autorizzati.</span></button>
          <button onclick="showTab('giro')"><b>Pianificazione sanitaria</b><span>Priorità, orario tassativo, temperatura richiesta e firma obbligatoria.</span></button>
          <button onclick="openDashboardInProgressPage()"><b>Tracciabilità consegne</b><span>Monitora consegne urgenti, tappe, firme, note e anomalie.</span></button>
          <button onclick="showHealthcareComplianceComingSoonV55()"><b>Conformità</b><span>Area futura per temperatura, note conformità e controlli sanitari.</span></button>
          <button onclick="showTab('storico')"><b>Storico sanitario</b><span>Consulta prove consegna, non conformità, urgenze e report.</span></button>
        </div>
      </section>
    `;
    return;
  }

  if(sector === "transfer"){
    renderTransferDashboardV84();
    host.innerHTML = `
      <section class="vertical-dashboard-v51 transfer-dashboard-v54">
        <div class="vertical-head-v51 transfer-head-v54">
          <span>Modulo verticale</span>
          <h2>Centro operativo transfer</h2>
          <p>Interfaccia dedicata a NCC, navette hotel, transfer aeroportuali e servizi turistici: prenotazioni, passeggeri, tratte, autisti, veicoli e corse su appuntamento.</p>
        </div>
        <div class="vertical-kpi-grid-v51 transfer-kpi-grid-v54">
          <div><small>Corse oggi</small><strong>${itemsToday}</strong><span>Passeggeri/tappe pianificate</span></div>
          <div><small>Corse in corso</small><strong>${activeRoutes.length}</strong><span>Autisti operativi</span></div>
          <div><small>Prenotate</small><strong>${scheduled.length}</strong><span>Da assegnare o avviare</span></div>
          <div><small>Completate oggi</small><strong>${completed.length}</strong><span>Servizi chiusi</span></div>
          <div><small>No-show / problemi</small><strong>${missed}</strong><span>Da verificare</span></div>
          <div><small>Risorse in uso</small><strong>${driversBusy}/${vehiclesBusy}</strong><span>Autisti / veicoli</span></div>
        </div>
        <div class="vertical-modules-v51 transfer-modules-v54">
          <button onclick="showTab('clienti')"><b>Passeggeri e clienti</b><span>Telefono, email, indirizzo ritiro, destinazione e note accoglienza.</span></button>
          <button onclick="showTab('giro')"><b>Pianificazione corse</b><span>Assegna autista, veicolo, orario ritiro, tratta e priorità.</span></button>
          <button onclick="openDashboardInProgressPage()"><b>Monitoraggio corse</b><span>Segui autisti in arrivo, clienti a bordo, ritardi e servizi completati.</span></button>
          <button onclick="showTab('transfer-portal')"><b>Portale prenotazioni</b><span>Personalizza, pubblica e condividi il link per ricevere nuove richieste.</span></button>
          <button onclick="showTab('storico')"><b>Storico corse</b><span>Consulta corse completate, no-show, ritardi e report transfer.</span></button>
        </div>
      </section>
    `;
    setTimeout(hydrateTransferDashboardV79, 0);
    return;
  }

  if(sector === "food_delivery"){
    host.innerHTML = `
      <section class="vertical-dashboard-v51 food-dashboard-v53">
        <div class="vertical-head-v51">
          <span>Modulo verticale</span>
          <h2>Centro operativo food delivery</h2>
          <p>Interfaccia dedicata a ristoranti, pizzerie, dark kitchen e servizi di consegna food: ordini, rider, punti vendita, orari di ritiro e consegna.</p>
        </div>
        <div class="vertical-kpi-grid-v51">
          <div><small>Ordini oggi</small><strong>${itemsToday}</strong><span>Ordini food pianificati</span></div>
          <div><small>Turni attivi</small><strong>${activeRoutes.length}</strong><span>Rider in consegna</span></div>
          <div><small>Da ritirare</small><strong>${scheduled.length}</strong><span>Ordini pronti/programmati</span></div>
          <div><small>Completati oggi</small><strong>${completed.length}</strong><span>Turni chiusi</span></div>
          <div><small>Ritardi / problemi</small><strong>${missed}</strong><span>Da verificare</span></div>
          <div><small>Risorse in uso</small><strong>${driversBusy}/${vehiclesBusy}</strong><span>Rider / mezzi</span></div>
        </div>
        <div class="vertical-modules-v51">
          <button onclick="showTab('clienti')"><b>Ordini e clienti finali</b><span>Telefono, indirizzo, note cliente, prodotti e metodo pagamento.</span></button>
          <button onclick="showTab('giro')"><b>Turni e consegne food</b><span>Assegna rider, punto vendita, orario ritiro e orario consegna.</span></button>
          <button onclick="openDashboardInProgressPage()"><b>Monitoraggio rider</b><span>Segui ordini in corso, ritardi e consegne completate.</span></button>
          <button onclick="showFoodMenuComingSoonV53()"><b>Menu / Catalogo</b><span>Area dedicata a prodotti, categorie, prezzi e disponibilità.</span></button>
          <button onclick="showTab('storico')"><b>Storico ordini food</b><span>Consulta consegne, annullamenti, ritardi e report.</span></button>
        </div>
      </section>
    `;
    return;
  }

  if(sector === "ecommerce"){
    host.innerHTML = `
      <section class="vertical-dashboard-v51 ecommerce-dashboard-v51">
        <div class="vertical-head-v51">
          <span>Modulo verticale</span>
          <h2>Centro operativo ordini</h2>
          <p>Interfaccia dedicata a shop online e aziende che consegnano ordini con mezzi propri: ordini, tracking, contrassegni, resi e prove di consegna.</p>
        </div>
        <div class="vertical-kpi-grid-v51">
          <div><small>Ordini oggi</small><strong>${itemsToday}</strong><span>Totale consegne pianificate</span></div>
          <div><small>In consegna</small><strong>${activeRoutes.length}</strong><span>Giri ordini attivi</span></div>
          <div><small>Da programmare</small><strong>${scheduled.length}</strong><span>Ordini/giri pronti</span></div>
          <div><small>Completati oggi</small><strong>${completed.length}</strong><span>Giri chiusi</span></div>
          <div><small>Resi / problemi</small><strong>${missed}</strong><span>Da verificare</span></div>
          <div><small>Risorse in uso</small><strong>${driversBusy}/${vehiclesBusy}</strong><span>Corrieri / mezzi</span></div>
        </div>
        <div class="vertical-modules-v51">
          <button onclick="showTab('clienti')"><b>Ordini e destinatari</b><span>Numero ordine, tracking, email cliente, contrassegno e indirizzo.</span></button>
          <button onclick="showTab('giro')"><b>Giri consegna ordini</b><span>Assegna ordini, corriere, mezzo e fascia prevista.</span></button>
          <button onclick="openDashboardInProgressPage()"><b>Tracking operativo</b><span>Segui ordini in consegna, firme, note e anomalie.</span></button>
          <button onclick="showTab('integrations')"><b>Integrazioni</b><span>Shopify: integrazione in sviluppo, import automatico non ancora disponibile.</span></button>
          <button onclick="showTab('storico')"><b>Storico ordini e resi</b><span>Consulta esiti, prove consegna e ordini non riusciti.</span></button>
        </div>
      </section>
    `;
    return;
  }

  host.innerHTML = `
    <section class="vertical-dashboard-v51 logistics-dashboard-v50">
      <div class="vertical-head-v51 logistics-head-v50">
        <span>Modulo verticale</span>
        <h2>Centro operativo spedizioni</h2>
        <p>Interfaccia dedicata a corrieri locali, logistica urbana, ultimo miglio, ritiri e consegne pacchi.</p>
      </div>
      <div class="vertical-kpi-grid-v51 logistics-kpi-grid-v50">
        <div><small>Spedizioni oggi</small><strong>${itemsToday}</strong><span>Totale fermate pianificate</span></div>
        <div><small>Giri spedizioni attivi</small><strong>${activeRoutes.length}</strong><span>Corrieri in consegna</span></div>
        <div><small>Programmate</small><strong>${scheduled.length}</strong><span>Da avviare</span></div>
        <div><small>Completate oggi</small><strong>${completed.length}</strong><span>Giri chiusi</span></div>
        <div><small>Tentativi falliti</small><strong>${missed}</strong><span>Da controllare</span></div>
        <div><small>Risorse in uso</small><strong>${driversBusy}/${vehiclesBusy}</strong><span>Corrieri / mezzi</span></div>
      </div>
      <div class="vertical-modules-v51 logistics-modules-v50">
        <button onclick="showTab('clienti')"><b>Spedizioni e destinatari</b><span>Tracking, colli, peso, indirizzi e destinatari.</span></button>
        <button onclick="showTab('giro')"><b>Pianificazione ritiri/consegne</b><span>Assegna corriere, mezzo e giro spedizioni.</span></button>
        <button onclick="openDashboardInProgressPage()"><b>Controllo consegne</b><span>Stato in corso, tentativi falliti e firme.</span></button>
        <button onclick="showTab('storico')"><b>Storico spedizioni</b><span>Consulta esiti, prove consegna e report.</span></button>
      </div>
    </section>
  `;
}

const gfOriginalApplyWorkspaceStateV50 = window.applyWorkspaceStateV49;
window.applyWorkspaceStateV49 = function(operational){
  const forceOperational = gfSectorOperationalActiveV50();
  gfOriginalApplyWorkspaceStateV50(forceOperational ? true : operational);
  applyLogisticsWorkspaceV50();
};

const gfOriginalSetSectorConfigV50 = window.setSectorConfigV47;
window.setSectorConfigV47 = function(data){
  gfOriginalSetSectorConfigV50(data);
  if(gfSectorOperationalActiveV50()){
    applyWorkspaceStateV49(true);
  }else{
    applyLogisticsWorkspaceV50();
  }
};


function showFoodMenuComingSoonV53(){
  alert("Modulo Menu / Catalogo in preparazione.\n\nPer il settore Food delivery inseriremo una sezione dedicata a prodotti, categorie, prezzi, disponibilità e composizione degli ordini food.");
}
window.showFoodMenuComingSoonV53 = showFoodMenuComingSoonV53;

// -----------------------------------------------------------------------------
// v52 - Sezione Integrazioni per E-commerce
// -----------------------------------------------------------------------------
function renderIntegrationsV52(){
  const tab=document.getElementById('tab-integrations');
  if(tab) tab.innerHTML='<section class="panel"><h1>Integrazioni · In sviluppo</h1><p>Il collegamento Shopify e l’importazione automatica degli ordini non sono ancora disponibili.</p><p>Puoi già importare i clienti da CSV o XLSX nella sezione Clienti.</p></section>';
}

function showShopifyComingSoonV52(action){
  const domain = document.getElementById("shopifyDomainV52")?.value?.trim() || "";
  if(action === "test" && !domain){
    alert("Inserisci prima il dominio Shopify, ad esempio nome-negozio.myshopify.com.\n\nIl collegamento reale sarà attivato nella prossima fase dell'integrazione.");
    return;
  }
  alert("Integrazione Shopify preparata.\n\nLa sezione è già presente nell'interfaccia e-commerce. Nel prossimo step collegheremo davvero le API Shopify per test connessione e import ordini.");
}

window.renderIntegrationsV52 = renderIntegrationsV52;
window.showShopifyComingSoonV52 = showShopifyComingSoonV52;

/* ==========================================================
   v62 - Mobile shell gestionale
   Mantiene tutte le funzioni desktop: il menu in basso contiene
   le azioni principali, il menu Altro espone tutte le sezioni.
========================================================== */
function isMobileViewportV62(){ return window.matchMedia && window.matchMedia('(max-width: 820px)').matches; }
function toggleMobileMoreMenuV62(){
  const menu=document.getElementById('gfMobileMoreMenuV62');
  const backdrop=document.getElementById('gfMobileMoreBackdropV62');
  if(!menu || !backdrop) return;
  const hidden=menu.classList.contains('hidden');
  menu.classList.toggle('hidden', !hidden);
  backdrop.classList.toggle('hidden', !hidden);
}
function closeMobileMoreMenuV62(){
  document.getElementById('gfMobileMoreMenuV62')?.classList.add('hidden');
  document.getElementById('gfMobileMoreBackdropV62')?.classList.add('hidden');
}
function mobileGoTabV62(tab){
  closeMobileMoreMenuV62();
  if(typeof showTab === 'function') showTab(tab);
  setTimeout(syncMobileShellV62, 60);
}
function syncMobileShellV62(){
  try{
    const topAvatar=document.getElementById('topProfileAvatar')?.textContent?.trim() || 'A';
    const mobAvatar=document.getElementById('gfMobileAvatarTextV62');
    if(mobAvatar) mobAvatar.textContent = topAvatar.slice(0,1).toUpperCase();
    const badge=document.getElementById('notificationBadge');
    const dot=document.getElementById('gfMobileBellDotV62');
    if(dot && badge) dot.classList.toggle('hidden', badge.classList.contains('hidden') || !badge.textContent || badge.textContent === '0');
    const integrationsDesktop=document.querySelector('.nav-item[data-tab="integrations"]');
    const integrationsMobile=document.getElementById('gfMobileIntegrationsBtnV62');
    if(integrationsMobile && integrationsDesktop){
      integrationsMobile.classList.toggle('hidden', integrationsDesktop.classList.contains('hidden'));
    }
    const active=document.querySelector('.nav-item.active')?.dataset?.tab || 'dashboard';
    document.querySelectorAll('.gf-mobile-bottom-nav-v62 button').forEach(b=>b.classList.remove('active'));
    const direct=document.querySelector(`.gf-mobile-bottom-nav-v62 button[data-mobile-tab="${active}"]`);
    if(direct) direct.classList.add('active');
    else if(['giro','dashboard-scheduled','dashboard-completed'].includes(active)) document.querySelector('.gf-mobile-bottom-nav-v62 button.main')?.classList.add('active');
  }catch(e){ console.warn('syncMobileShellV62', e); }
}
(function initMobileShellV62(){
  const originalShowTab=window.showTab;
  if(typeof originalShowTab === 'function' && !window.__mobileShowTabWrappedV62){
    window.showTab=function(name){
      const result=originalShowTab.apply(this, arguments);
      setTimeout(syncMobileShellV62, 40);
      return result;
    };
    window.__mobileShowTabWrappedV62=true;
  }
  window.addEventListener('resize', syncMobileShellV62);
  document.addEventListener('DOMContentLoaded', syncMobileShellV62);
  setTimeout(syncMobileShellV62, 500);
})();

/* ------------------------------------------------------------------
   v78 - Transfer booking portal visual builder
------------------------------------------------------------------ */
let gfTransferPortalV78 = null;
let gfTransferLogoV78 = "";
let gfTransferHeroV78 = "";
let gfTransferPreviewModeV78 = "desktop";
const GF_TRANSFER_FIELDS_V78 = {
  email:"Email", phone:"Telefono", passengers:"Numero passeggeri", luggage:"Bagagli",
  flight_train:"Volo / treno", child_seat:"Seggiolino", pets:"Animali",
  notes:"Note", round_trip:"Andata e ritorno"
};

function transferValV78(id){ return document.getElementById(id)?.value ?? ""; }
function transferSetV78(id,value){ const el=document.getElementById(id); if(el) el.value=value ?? ""; }
function transferCheckedV78(id){ return !!document.getElementById(id)?.checked; }
function transferSetCheckedV78(id,value){ const el=document.getElementById(id); if(el) el.checked=!!value; }
function transferEscV78(value){ return String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function renderTransferFieldControlsV78(fields={}){
  const host=document.getElementById("tpFieldsV78"); if(!host) return;
  host.innerHTML=Object.entries(GF_TRANSFER_FIELDS_V78).map(([key,label])=>`
    <label class="transfer-field-row-v78"><span>${label}</span><select data-transfer-field="${key}" onchange="updateTransferPreviewV78()">
      <option value="hidden" ${fields[key]==='hidden'?'selected':''}>Nascosto</option>
      <option value="visible" ${(!fields[key]||fields[key]==='visible')?'selected':''}>Visibile</option>
      <option value="required" ${fields[key]==='required'?'selected':''}>Obbligatorio</option>
    </select></label>`).join("");
}

function collectTransferFieldsV78(){
  const out={}; document.querySelectorAll("[data-transfer-field]").forEach(el=>out[el.dataset.transferField]=el.value); return out;
}

async function loadTransferPortalV78(force=false){
  try{
    const data=await api("/api/transfer/booking-portal");
    gfTransferPortalV78=data; gfTransferLogoV78=data.logo_data_url||""; gfTransferHeroV78=data.hero_image_data_url||"";
    transferSetV78("tpCompanyNameV78",data.company_name); transferSetV78("tpSlugV78",data.public_slug);
    transferSetV78("tpThemeV78",data.theme); transferSetV78("tpPrimaryV78",data.primary_color);
    transferSetV78("tpSecondaryV78",data.secondary_color); transferSetV78("tpButtonV78",data.button_color);
    transferSetV78("tpTextV78",data.text_color); transferSetV78("tpBackgroundV78",data.background_color);
    transferSetV78("tpTitleV78",data.title); transferSetV78("tpSubtitleV78",data.subtitle);
    transferSetV78("tpIntroV78",data.intro_text); transferSetV78("tpConfirmationV78",data.confirmation_message);
    transferSetV78("tpClosedV78",data.closed_message); transferSetV78("tpFooterV78",data.footer_text);
    transferSetV78("tpPhoneV78",data.phone); transferSetV78("tpWhatsappV78",data.whatsapp);
    transferSetV78("tpEmailV78",data.email); transferSetV78("tpWebsiteV78",data.website);
    transferSetV78("tpAdvanceV78",data.min_advance_minutes); transferSetV78("tpStatusV78",data.portal_status);
    transferSetCheckedV78("tpAcceptV78",data.accept_bookings); transferSetCheckedV78("tpBrandV78",data.show_girofacile_brand);
    transferSetV78("tpServicesV78",(data.services||[]).join("\n"));
    renderTransferFieldControlsV78(data.fields||{});
    const logoState=document.getElementById("tpLogoStateV78"); if(logoState) logoState.textContent=gfTransferLogoV78?"Logo caricato":"Nessun logo caricato";
    const heroState=document.getElementById("tpHeroStateV78"); if(heroState) heroState.textContent=gfTransferHeroV78?"Immagine caricata":"Nessuna immagine caricata";
    updateTransferPreviewV78();
    const state=document.getElementById("tpSaveStateV78"); if(state) state.textContent=force?"Modifiche ripristinate":"Configurazione caricata";
  }catch(e){ toast(e.message||"Impossibile caricare il portale", "error"); }
}

function readTransferImageV78(input,type){
  const file=input?.files?.[0]; if(!file) return;
  if(file.size>2.5*1024*1024){ alert("L'immagine non può superare 2,5 MB."); input.value=""; return; }
  const reader=new FileReader(); reader.onload=()=>{ if(type==='logo') gfTransferLogoV78=reader.result; else gfTransferHeroV78=reader.result;
    const state=document.getElementById(type==='logo'?"tpLogoStateV78":"tpHeroStateV78"); if(state) state.textContent=file.name;
    updateTransferPreviewV78();
  }; reader.readAsDataURL(file);
}
function clearTransferImageV78(type){ if(type==='logo') gfTransferLogoV78=""; else gfTransferHeroV78=""; const input=document.getElementById(type==='logo'?"tpLogoFileV78":"tpHeroFileV78"); if(input) input.value=""; const state=document.getElementById(type==='logo'?"tpLogoStateV78":"tpHeroStateV78"); if(state) state.textContent=type==='logo'?"Nessun logo caricato":"Nessuna immagine caricata"; updateTransferPreviewV78(); }

function transferPreviewDataV78(){
  return {
    company_name:transferValV78("tpCompanyNameV78")||"La tua azienda", public_slug:transferValV78("tpSlugV78")||"nome-azienda",
    logo_data_url:gfTransferLogoV78, hero_image_data_url:gfTransferHeroV78, theme:transferValV78("tpThemeV78")||"modern",
    primary_color:transferValV78("tpPrimaryV78")||"#0f766e", secondary_color:transferValV78("tpSecondaryV78")||"#ecfdf5",
    button_color:transferValV78("tpButtonV78")||"#0f766e", text_color:transferValV78("tpTextV78")||"#102a2a",
    background_color:transferValV78("tpBackgroundV78")||"#f4fbfa", title:transferValV78("tpTitleV78")||"Prenota il tuo transfer",
    subtitle:transferValV78("tpSubtitleV78"), intro_text:transferValV78("tpIntroV78"), confirmation_message:transferValV78("tpConfirmationV78"),
    closed_message:transferValV78("tpClosedV78"), footer_text:transferValV78("tpFooterV78"), phone:transferValV78("tpPhoneV78"),
    whatsapp:transferValV78("tpWhatsappV78"), email:transferValV78("tpEmailV78"), website:transferValV78("tpWebsiteV78"),
    min_advance_minutes:Number(transferValV78("tpAdvanceV78")||0), portal_status:transferValV78("tpStatusV78"),
    accept_bookings:transferCheckedV78("tpAcceptV78"), show_girofacile_brand:transferCheckedV78("tpBrandV78"),
    fields:collectTransferFieldsV78(), services:transferValV78("tpServicesV78").split(/\n|,/).map(x=>x.trim()).filter(Boolean)
  };
}

function previewFieldV78(data,key,label,full=false){ const state=data.fields?.[key]||"visible"; if(state==='hidden') return ""; return `<div class="tp-preview-field-v78 ${full?'full':''}"><label>${label}${state==='required'?' *':''}</label><div></div></div>`; }
function updateTransferPreviewV78(){
  const data=transferPreviewDataV78(), host=document.getElementById("tpPreviewContentV78"), device=document.getElementById("tpPreviewDeviceV78"); if(!host||!device) return;
  const url=document.getElementById("tpPreviewUrlV78"); if(url) url.textContent=`girofacile.it/prenota/${data.public_slug}`;
  const publicLink=document.getElementById("tpPublicLinkV78"); if(publicLink) publicLink.textContent=`/prenota/${data.public_slug} · ${data.portal_status==='published'?'Pubblicato':data.portal_status==='closed'?'Chiuso':'Bozza'}`;
  device.className=`transfer-preview-device-v78 ${gfTransferPreviewModeV78==='mobile'?'mobile':'desktop'}`;
  if(gfTransferPreviewModeV78==='email'){
    host.innerHTML=`<div class="tp-preview-email-v78" style="--tp-primary:${data.primary_color}"><div class="tp-email-card-v78"><div class="tp-email-head-v78">${data.logo_data_url?`<img src="${data.logo_data_url}">`:''}<strong>${transferEscV78(data.company_name)}</strong></div><div class="tp-email-body-v78"><h2>Richiesta di prenotazione ricevuta</h2><p>Gentile cliente,</p><p>${transferEscV78(data.confirmation_message||'La tua richiesta è stata ricevuta.')}</p><div class="tp-email-summary-v78"><strong>Riepilogo corsa</strong><br>Napoli Centro → Aeroporto di Napoli<br>15 luglio · 10:30 · 2 passeggeri</div><p>Ti contatteremo per la conferma definitiva.</p><p><strong>${transferEscV78(data.company_name)}</strong><br>${transferEscV78(data.phone)} ${transferEscV78(data.email)}</p></div></div></div>`;
    return;
  }
  host.innerHTML=`<div class="tp-preview-page-v78 theme-${data.theme}" style="--tp-primary:${data.primary_color};--tp-button:${data.button_color};--tp-text:${data.text_color};--tp-bg:${data.background_color};--tp-hero:url('${String(data.hero_image_data_url||'').replace(/'/g,"\\'")}')"><div class="tp-preview-hero-v78 ${data.hero_image_data_url?'with-image':''}"><div class="tp-preview-brand-v78">${data.logo_data_url?`<img src="${data.logo_data_url}">`:''}<span>${transferEscV78(data.company_name)}</span></div><h2>${transferEscV78(data.title)}</h2><p>${transferEscV78(data.subtitle)}</p></div><div class="tp-preview-form-wrap-v78"><div class="tp-preview-form-v78"><p>${transferEscV78(data.intro_text)}</p><div class="tp-preview-grid-v78"><div class="tp-preview-field-v78"><label>Nome e cognome *</label><div></div></div>${previewFieldV78(data,'phone','Telefono')}${previewFieldV78(data,'email','Email')}<div class="tp-preview-field-v78 full"><label>Luogo di partenza *</label><div></div></div><div class="tp-preview-field-v78 full"><label>Destinazione *</label><div></div></div><div class="tp-preview-field-v78"><label>Data *</label><div></div></div><div class="tp-preview-field-v78"><label>Ora *</label><div></div></div>${previewFieldV78(data,'passengers','Passeggeri')}${previewFieldV78(data,'luggage','Bagagli')}<div class="tp-preview-field-v78"><label>Tipo di servizio</label><div></div></div>${previewFieldV78(data,'flight_train','Volo / treno')}<div class="tp-preview-submit-v78">Invia richiesta di prenotazione</div></div></div></div><div class="tp-preview-footer-v78">${transferEscV78(data.footer_text)}${data.show_girofacile_brand?' · Powered by GiroFacile':''}</div></div>`;
  const state=document.getElementById("tpSaveStateV78"); if(state) state.textContent="Modifiche non salvate";
  refreshTransferShareV85();
}

function setTransferPreviewModeV78(mode,button){ gfTransferPreviewModeV78=mode; document.querySelectorAll("[data-transfer-preview]").forEach(x=>x.classList.toggle("active",x.dataset.transferPreview===mode)); updateTransferPreviewV78(); }

async function saveTransferPortalV78(statusOverride=null){
  const payload=transferPreviewDataV78(); if(statusOverride) payload.portal_status=statusOverride;
  try{ const res=await api("/api/transfer/booking-portal",{method:"PUT",body:JSON.stringify(payload)}); gfTransferPortalV78=res.settings; transferSetV78("tpSlugV78",res.settings.public_slug); transferSetV78("tpStatusV78",res.settings.portal_status); updateTransferPreviewV78(); const state=document.getElementById("tpSaveStateV78"); if(state) state.textContent="Salvato nel database"; toast(res.message||"Portale aggiornato"); }
  catch(e){ alert(e.message||"Errore durante il salvataggio"); }
}
function openTransferPortalPublicV78(){ const slug=transferValV78("tpSlugV78")||gfTransferPortalV78?.public_slug; if(!slug){ alert("Salva prima il portale."); return; } window.open(`/prenota/${encodeURIComponent(slug)}`,"_blank"); }






// v89.3 - salvataggio manuale della pagina Impostazioni
let gfSettingsDirtyV893=false;
function markSettingsDirtyV893(){
  gfSettingsDirtyV893=true;
  const state=document.getElementById('settingsSaveState');
  const btn=document.getElementById('settingsSaveBtnV893');
  if(state) state.textContent='Modifiche non salvate.';
  if(btn) btn.disabled=false;
}
function markSettingsCleanV893(message='Impostazioni salvate.') {
  gfSettingsDirtyV893=false;
  const state=document.getElementById('settingsSaveState');
  const btn=document.getElementById('settingsSaveBtnV893');
  if(state) state.textContent=message;
  if(btn) btn.disabled=true;
}
async function saveAllSettingsV893(){
  const btn=document.getElementById('settingsSaveBtnV893');
  const state=document.getElementById('settingsSaveState');
  if(!gfSettingsDirtyV893) return;
  if(btn){btn.disabled=true;btn.dataset.oldText=btn.textContent;btn.textContent='Salvataggio...';}
  if(state) state.textContent='Salvataggio impostazioni...';
  const features={
    has_time_windows:!!document.getElementById('featureTimeWindowsV89')?.checked,
    needs_photo_proof:!!document.getElementById('featurePhotoProofV89')?.checked,
    has_ztl:!!document.getElementById('featureZtlV89')?.checked,
    needs_tail_lift:!!document.getElementById('featureTailLiftV89')?.checked,
    has_refrigerated_goods:!!document.getElementById('featureRefrigeratedV89')?.checked
  };
  const signature=!!document.getElementById('settingDeliverySignature')?.checked;
  try{
    await api('/api/company-profile',{method:'PUT',body:JSON.stringify(features)});
    settingsV41=await api('/api/settings',{method:'PUT',body:JSON.stringify({delivery_signature_enabled:signature,agents_enabled:!!document.getElementById('settingAgentsEnabled')?.checked})});
    gfUniversalFeaturesV891={...gfUniversalFeaturesV891,...features};
    applyUniversalFeaturesV891();
    markSettingsCleanV893('Impostazioni salvate e applicate.');
    await refreshAgentsFeature();
    toast('Impostazioni salvate.');
  }catch(e){
    gfSettingsDirtyV893=true;
    if(state) state.textContent='Errore salvataggio: '+e.message;
    if(btn) btn.disabled=false;
    alert(e.message||'Errore durante il salvataggio.');
  }finally{
    if(btn) btn.textContent=btn.dataset.oldText||'Salva modifiche';
  }
}
window.markSettingsDirtyV893=markSettingsDirtyV893;
window.saveAllSettingsV893=saveAllSettingsV893;

// -----------------------------------------------------------------------------
// v89 - GiroFacile universale per aziende che effettuano consegne
// Elimina la verticalizzazione visiva per settore mantenendo compatibilità dati.
// -----------------------------------------------------------------------------
let gfUniversalFeaturesV891={has_time_windows:true,needs_photo_proof:false,has_ztl:false,needs_tail_lift:false,has_refrigerated_goods:false};
function applyUniversalFeaturesV891(){
  const f=gfUniversalFeaturesV891;
  const root=document.documentElement;
  root.dataset.gfTimeWindows=f.has_time_windows?'on':'off';
  root.dataset.gfZtl=f.has_ztl?'on':'off';
  root.dataset.gfTailLift=f.needs_tail_lift?'on':'off';
  root.dataset.gfPhotoProof=f.needs_photo_proof?'on':'off';
  root.dataset.gfRefrigerated=f.has_refrigerated_goods?'on':'off';

  // Pulisce filtri disattivati: una funzione OFF non deve continuare a influenzare le query.
  if(!f.has_ztl){ ['pickZtl','customerFilterZtl'].forEach(id=>{const e=document.getElementById(id);if(e)e.value='';}); ['cZtl','dmZtl','vZtl'].forEach(id=>{const e=document.getElementById(id);if(e)e.value='false';}); }
  if(!f.needs_tail_lift){ ['pickSponda','customerFilterSponda'].forEach(id=>{const e=document.getElementById(id);if(e)e.value='';}); ['cSponda','dmSponda','vSponda'].forEach(id=>{const e=document.getElementById(id);if(e)e.value='false';}); }

  const hint=document.querySelector('.customer-picker-panel .picker-header small');
  if(hint){
    const extras=[]; if(f.has_ztl) extras.push('ZTL'); if(f.needs_tail_lift) extras.push('sponda');
    hint.textContent=extras.length ? `Usa i filtri per zona, ${extras.join(' o ')}` : 'Usa i filtri per zona';
  }
}
async function loadUniversalFeaturesV89(){
  try{
    const c=await api('/api/company-profile');
    gfUniversalFeaturesV891={
      has_time_windows:c.has_time_windows !== false,
      needs_photo_proof:!!c.needs_photo_proof,
      has_ztl:!!c.has_ztl,
      needs_tail_lift:!!c.needs_tail_lift,
      has_refrigerated_goods:!!c.has_refrigerated_goods
    };
    const map={featureTimeWindowsV89:'has_time_windows',featurePhotoProofV89:'needs_photo_proof',featureZtlV89:'has_ztl',featureTailLiftV89:'needs_tail_lift',featureRefrigeratedV89:'has_refrigerated_goods'};
    Object.entries(map).forEach(([id,key])=>{const el=document.getElementById(id);if(el)el.checked=!!gfUniversalFeaturesV891[key];});
    applyUniversalFeaturesV891();
  }catch(e){ console.warn('Funzionalità opzionali',e); }
}
async function saveUniversalFeaturesV89(){
  const state=document.getElementById('settingsSaveState'); if(state)state.textContent='Salvataggio funzionalità...';
  const payload={
    has_time_windows:!!document.getElementById('featureTimeWindowsV89')?.checked,
    needs_photo_proof:!!document.getElementById('featurePhotoProofV89')?.checked,
    has_ztl:!!document.getElementById('featureZtlV89')?.checked,
    needs_tail_lift:!!document.getElementById('featureTailLiftV89')?.checked,
    has_refrigerated_goods:!!document.getElementById('featureRefrigeratedV89')?.checked
  };
  try{
    await api('/api/company-profile',{method:'PUT',body:JSON.stringify(payload)});
    gfUniversalFeaturesV891={...gfUniversalFeaturesV891,...payload};
    applyUniversalFeaturesV891();
    if(state)state.textContent='Funzionalità aggiornate.'; toast('Funzionalità salvate.');
  }catch(e){ if(state)state.textContent='Errore salvataggio: '+e.message; alert(e.message); }
}
window.applyUniversalFeaturesV891=applyUniversalFeaturesV891;
window.loadUniversalFeaturesV89=loadUniversalFeaturesV89;
window.saveUniversalFeaturesV89=saveUniversalFeaturesV89;

const gfShowTabUniversalV89=window.showTab;
window.showTab=function(name){
  // Le vecchie pagine verticali restano nel codice solo per compatibilità, ma non sono navigabili.
  if(['transfer-portal','transfer-bookings','transfer-planning','transfer-settings','integrations'].includes(name)){ name='dashboard'; }
  gfShowTabUniversalV89(name);
  if(name==='settings') loadUniversalFeaturesV89();
};

const gfApplyLogisticsLegacyV89=window.applyLogisticsWorkspaceV50;
window.applyLogisticsWorkspaceV50=function(){
  // Neutralizza classi/etichette verticali legacy.
  ['sector-logistics-v50','sector-ecommerce-v51','sector-food-v53','sector-transfer-v54','sector-healthcare-v55'].forEach(c=>document.body.classList.remove(c));
  document.querySelectorAll('[data-sector-only]').forEach(el=>{el.classList.add('hidden');el.style.display='none';});
  ['gfMobileTransferPortalBtnV78','gfMobileTransferBookingsBtnV79','gfMobileTransferPlanningBtnV79','gfMobileTransferSettingsBtnV79','gfMobileTransferAdminDriverBtnV79'].forEach(id=>{const el=document.getElementById(id);if(el){el.classList.add('hidden');el.style.display='none';}});
  const transferDash=document.getElementById('transferDashboardV84'); if(transferDash){transferDash.classList.add('hidden');transferDash.style.display='none';}
  const title=document.querySelector('#tab-dashboard .dash-hero-row h1'); if(title)title.textContent='Dashboard';
  const sub=document.querySelector('#tab-dashboard .dash-hero-row p'); if(sub)sub.textContent='Panoramica operativa delle consegne e dell’attività aziendale.';
  const btn=document.querySelector('#tab-dashboard .dash-hero-row .btn-primary'); if(btn)btn.textContent='+ Nuovo giro';
  setNavTextV50('giro','Pianificazione'); setNavTextV50('clienti','Clienti'); setNavTextV50('mezzi','Mezzi'); setNavTextV50('autisti','Autisti'); setNavTextV50('storico','Storico'); setNavTextV50('report','Report'); setNavTextV50('chat-autisti','Chat autisti');
};

// La vecchia configurazione settore non deve più cambiare l'interfaccia.
const gfSetSectorLegacyV89=window.setSectorConfigV47;
window.setSectorConfigV47=function(data){ gfSetSectorLegacyV89(data); window.applyLogisticsWorkspaceV50(); };
