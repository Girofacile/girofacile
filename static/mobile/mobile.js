// ============================================================
// GIROFACILE MOBILE — JS COMPLETO
// ============================================================
let me=null, customers=[], deposits=[], vehicles=[], drivers=[], agents=[], deliveries=[];

const api=async(url,opts={})=>{
  const o={credentials:"same-origin",headers:{"Content-Type":"application/json"},...opts};
  const r=await fetch(url,o); let d=null;
  try{d=await r.json()}catch(e){}
  if(!r.ok) throw new Error(d?.detail||"Errore di comunicazione");
  return d;
};
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const todayIso=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`};
const fmt=(n,dec=1)=>n==null?"—":parseFloat(n).toFixed(dec);
const mval=id=>{const el=document.getElementById(id);return el?el.value.trim():""};
const mcheck=id=>{const el=document.getElementById(id);return el?el.checked:false};

// ---- BOOT ----
async function boot(){
  document.getElementById("routeDate").value=todayIso();
  const today=todayIso();
  document.getElementById("reportFrom").value=today.slice(0,8)+"01";
  document.getElementById("reportTo").value=today;
  document.getElementById("storicoFrom").value=today.slice(0,8)+"01";
  document.getElementById("storicoTo").value=today;
  try{
    const p=await api("/api/me");
    if(p.authenticated){me=p;openApp();}else openLogin();
  }catch(e){openLogin()}
}

function openLogin(){
  document.getElementById("loginView").classList.remove("hidden");
  document.getElementById("appView").classList.add("hidden");
}
async function openApp(){
  document.getElementById("loginView").classList.add("hidden");
  document.getElementById("appView").classList.remove("hidden");
  const name=me?.company_name||me?.username||"";
  document.getElementById("companyLabel").textContent=name||"Panoramica operativa";
  document.getElementById("altroUserLabel").textContent=name||"Impostazioni e risorse";
  const av=document.getElementById("userAvatar");
  if(av) av.textContent=(name||"U")[0].toUpperCase();
  await Promise.all([loadResources(),loadCustomersMobile(),loadDashboard()]);
  await populateReportFilters();
}

// ---- AUTH ----
function mobileToggleSignup(show){
  document.getElementById("mLoginCard").style.display=show?"none":"";
  document.getElementById("mSignupCard").style.display=show?"":"none";
  document.getElementById("loginError").textContent="";
  const se=document.getElementById("signupError");if(se)se.textContent="";
}
function mSelectPlan(el){document.querySelectorAll(".plan-card").forEach(x=>x.classList.remove("selected"));el.classList.add("selected");}
function mGetSelectedPlan(){const s=document.querySelector(".plan-card.selected");return s?s.getAttribute("data-plan"):"business";}
async function mobileSignup(){
  const err=document.getElementById("signupError");err.textContent="";
  try{
    await api("/api/signup",{method:"POST",body:JSON.stringify({
      company_name:mval("mSignupCompany"),username:mval("mSignupUser"),
      email:mval("mSignupEmail"),password:mval("mSignupPass"),plan:mGetSelectedPlan()
    })});
    mobileToggleSignup(false);
    const p=await api("/api/me");if(p.authenticated){me=p;openApp();}
  }catch(e){err.textContent=e.message;}
}
async function mobileLogin(){
  const err=document.getElementById("loginError");err.textContent="";
  try{
    const r=await api("/api/login",{method:"POST",body:JSON.stringify({username:mval("mUser"),password:mval("mPass")})});
    me=r;await openApp();
  }catch(e){err.textContent=e.message;}
}
async function mobileLogout(){try{await api("/api/logout",{method:"POST",body:"{}"})}catch(e){}location.reload();}

// ---- NAVIGAZIONE ----
function showView(name,btn){
  document.querySelectorAll(".view").forEach(x=>x.classList.remove("active"));
  document.getElementById("view-"+name).classList.add("active");
  document.querySelectorAll(".bnav-btn").forEach(x=>x.classList.remove("active"));
  if(btn) btn.classList.add("active");
  hideSubView();
  window.scrollTo({top:0,behavior:"smooth"});
  if(name==="giri") loadPlanningCustomers();
  if(name==="clienti") loadCustomersMobile();
  if(name==="dashboard") loadDashboard();
  if(name==="report") loadReport();
}

function showGiriTab(name,btn){
  document.querySelectorAll(".giri-tab").forEach(x=>x.classList.add("hidden"));
  document.getElementById("giriTab-"+name).classList.remove("hidden");
  document.querySelectorAll(".tab-btn").forEach(x=>x.classList.remove("active"));
  if(btn) btn.classList.add("active");
  if(name==="storico") loadStorico();
  if(name==="nuovo") loadPlanningCustomers();
}

// ---- RISORSE ----
async function loadResources(){
  try{
    [deposits,vehicles,drivers,agents]=await Promise.all([
      api("/api/deposits"),api("/api/vehicles"),api("/api/drivers"),api("/api/agents").catch(()=>[])
    ]);
    const fill=(id,rows,label,empty)=>{
      const el=document.getElementById(id);if(!el)return;
      el.innerHTML=empty?`<option value="">${empty}`:"";
      rows.forEach(x=>el.innerHTML+=`<option value="${x.id}">${esc(label(x))}</option>`);
    };
    fill("routeDeposit",deposits,x=>x.nome,false);
    fill("routeVehicle",vehicles,x=>`${x.nome}${x.targa?" · "+x.targa:""}`, "Nessun mezzo");
    fill("routeDriver",drivers,x=>`${x.nome} ${x.cognome||""}`, "Nessun autista");
  }catch(e){}
}

async function populateReportFilters(){
  try{
    const drvEl=document.getElementById("reportDriver");
    const vehEl=document.getElementById("reportVehicle");
    drivers.forEach(d=>drvEl.innerHTML+=`<option value="${d.id}">${esc(d.nome)} ${esc(d.cognome||"")}</option>`);
    vehicles.forEach(v=>vehEl.innerHTML+=`<option value="${v.id}">${esc(v.nome)}${v.targa?" · "+v.targa:""}</option>`);
  }catch(e){}
}

// ---- DASHBOARD ----
async function loadDashboard(){
  try{
    const [cs,vs,ds,routes]=await Promise.all([
      api("/api/customers?limit=1000"),api("/api/vehicles"),
      api("/api/drivers"),api("/api/routes/operativi")
    ]);
    document.getElementById("kpiCustomers").textContent=cs.length;
    document.getElementById("kpiVehicles").textContent=vs.length;
    document.getElementById("kpiDrivers").textContent=ds.length;
    document.getElementById("kpiRoutes").textContent=routes.length;
    const today=todayIso();
    const todayRoutes=routes.filter(r=>r.data_giro===today);
    document.getElementById("dashGiriOggi").textContent=todayRoutes.length;
    const km=todayRoutes.reduce((s,r)=>s+parseFloat(r.totale_km||0),0);
    const cost=todayRoutes.reduce((s,r)=>s+parseFloat(r.costo_carburante||0),0);
    document.getElementById("dashKmOggi").textContent=fmt(km)+" km";
    document.getElementById("dashCostoOggi").textContent="€"+fmt(cost,2);
    const box=document.getElementById("activeRoutes");
    box.innerHTML=routes.slice(0,8).map(r=>`
      <div class="route-history-card">
        <div class="rh-head">
          <div><div class="rh-name">${esc(r.nome)}</div><div class="rh-date">${esc(r.data_giro)} · ${esc(r.orario_partenza||"")} · ${esc(r.driver_name||"Autista n/a")}</div></div>
          <span class="badge ${r.status||"programmato"}">${esc(r.status_label||r.status||"")}</span>
        </div>
        <div class="rh-meta"><span>📍 ${r.consegne_count||0} fermate</span><span>📏 ${fmt(r.totale_km)} km</span></div>
        <div class="rh-actions">
          ${r.status==="programmato"||r.status==="in_corso"?`<button class="mini-btn green" onclick="completeRoute(${r.id})">✓ Completa</button>`:``}
          ${r.status!=="completato"&&r.status!=="annullato"?`<button class="mini-btn red" onclick="cancelRoute(${r.id})">✕ Annulla</button>`:``}
          <button class="mini-btn" onclick="viewRouteDetail(${r.id})">Dettaglio</button>
        </div>
      </div>`).join("")||`<div class="list-card"><small>Nessun giro operativo oggi.</small></div>`;
  }catch(e){}
}

async function completeRoute(id){
  if(!confirm("Segnare questo giro come completato?")) return;
  try{await api(`/api/routes/${id}/complete`,{method:"POST",body:"{}"});loadDashboard();}
  catch(e){alert(e.message);}
}
async function cancelRoute(id){
  if(!confirm("Annullare questo giro?")) return;
  try{await api(`/api/routes/${id}/cancel`,{method:"POST",body:"{}"});loadDashboard();}
  catch(e){alert(e.message);}
}
async function viewRouteDetail(id){
  try{
    const r=await api(`/api/routes/${id}`);
    const box=document.getElementById("dashRouteDetail");
    box.classList.remove("hidden");
    const stops=(r.consegne||[]).map((d,i)=>`
      <div class="stop-card">
        <div class="stop-header">
          <div class="stop-num">${i+1}</div>
          <div><div class="stop-name">${esc(d.cliente_nome)}</div><div class="stop-addr">${esc(d.indirizzo)}</div></div>
        </div>
        ${d.warning?`<div class="warning-tag">${esc(d.warning.split("|")[0])}</div>`:""}
        <div class="stop-times">
          <div class="stop-time"><span>Arrivo</span><strong>${esc(d.arrivo_stimato||"—")}</strong></div>
          <div class="stop-time"><span>Ripartenza</span><strong>${esc(d.partenza_stimata||"—")}</strong></div>
          <div class="stop-time"><span>Attesa</span><strong>${d.attesa_min>0?d.attesa_min+" min":"—"}</strong></div>
          <div class="stop-time"><span>Km</span><strong>${fmt(d.km_tappa)}</strong></div>
        </div>
      </div>`).join("");
    box.innerHTML=`
      <div class="section-card">
        <div class="section-head"><h3>${esc(r.nome)}</h3><button class="link-btn" onclick="document.getElementById('dashRouteDetail').classList.add('hidden')">Chiudi</button></div>
        <div class="route-kpi-grid">
          <div class="route-kpi"><strong>${fmt(r.totale_km)} km</strong><span>Distanza</span></div>
          <div class="route-kpi"><strong>${Math.round(r.totale_minuti||0)} min</strong><span>Durata</span></div>
          <div class="route-kpi"><strong>€${fmt(r.costo_carburante,2)}</strong><span>Carburante</span></div>
        </div>
        ${stops}
        ${r.google_maps_url?`<a class="maps-btn" target="_blank" href="${r.google_maps_url}">🗺 Apri in Google Maps</a>`:""}
      </div>`;
    box.scrollIntoView({behavior:"smooth"});
  }catch(e){alert(e.message);}
}

// ---- STORICO ----
async function loadStorico(){
  const from=mval("storicoFrom"),to=mval("storicoTo");
  const box=document.getElementById("storicoList");
  box.innerHTML=`<div style="text-align:center;padding:24px;color:#6b7280">Caricamento...</div>`;
  try{
    const rows=await api("/api/routes");
    const filtered=rows.filter(r=>{
      if(from && r.data_giro<from) return false;
      if(to && r.data_giro>to) return false;
      return true;
    });
    box.innerHTML=filtered.length?filtered.map(r=>`
      <div class="route-history-card">
        <div class="rh-head">
          <div><div class="rh-name">${esc(r.nome)}</div><div class="rh-date">${esc(r.data_giro)} · ${esc(r.driver_name||"Autista n/a")}</div></div>
          <span class="badge ${r.status||"programmato"}">${esc(r.status_label||"")}</span>
        </div>
        <div class="rh-meta"><span>📍 ${r.consegne_count||0} fermate</span><span>📏 ${fmt(r.totale_km)} km</span><span>💰 €${fmt(r.costo_carburante,2)}</span></div>
        <div class="rh-actions">
          ${r.status==="programmato"||r.status==="in_corso"?`<button class="mini-btn green" onclick="completeRoute(${r.id});loadStorico()">✓ Completa</button>`:""}
          ${r.status!=="completato"&&r.status!=="annullato"?`<button class="mini-btn red" onclick="cancelRoute(${r.id});loadStorico()">✕ Annulla</button>`:""}
          <button class="mini-btn" onclick="viewRouteDetail(${r.id})">Dettaglio</button>
        </div>
      </div>`).join("")
    :`<div class="list-card"><small>Nessun giro trovato nel periodo selezionato.</small></div>`;
  }catch(e){box.innerHTML=`<div class="list-card"><small>Errore: ${esc(e.message)}</small></div>`;}
}

// ---- CLIENTI ----
async function loadCustomersMobile(){
  try{
    const q=document.getElementById("customerListSearch")?.value||"";
    const ztl=document.getElementById("filterZtl")?.value||"";
    const sponda=document.getElementById("filterSponda")?.value||"";
    customers=await api(`/api/customers?limit=500&q=${encodeURIComponent(q)}&ztl=${ztl}&sponda=${sponda}`);
    const box=document.getElementById("customersList");if(!box)return;
    box.innerHTML=customers.map(c=>{
      const st=c.stato_geocodifica||"da_verificare";
      return `<div class="list-card">
        <div class="list-row">
          <div style="flex:1;min-width:0">
            <strong>${esc(c.codice_cliente?c.codice_cliente+" · ":"")}${esc(c.nome)}</strong>
            <small>${esc(c.comune||"")} · ${esc(c.indirizzo)}</small>
            ${c.ztl?`<small style="color:var(--red)">⚠ ZTL</small>`:""}
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">
            <span class="badge ${st}">${st.replace("_"," ")}</span>
            <div style="display:flex;gap:4px">
              <button class="mini-btn" onclick="verifyCustomer(${c.id})">Verifica</button>
              <button class="mini-btn" onclick="openEditCustomer(${c.id})">Modifica</button>
            </div>
          </div>
        </div>
      </div>`;
    }).join("")||`<div class="list-card"><small>Nessun cliente trovato.</small></div>`;
  }catch(e){}
}
async function verifyCustomer(id){
  try{await api(`/api/customers/${id}/verify-address`,{method:"POST",body:"{}"});await loadCustomersMobile();}
  catch(e){alert(e.message);}
}
async function verifyPendingMobile(){
  try{
    const r=await api("/api/customers/verify-pending?limit=100",{method:"POST",body:"{}"});
    await loadCustomersMobile();
    alert(`Controllati ${r.processed}. Verificati: ${r.verificato}, Da verificare: ${r.da_verificare}, Non trovati: ${r.non_trovato}.`);
  }catch(e){alert(e.message);}
}
async function importCustomersMobile(){
  const file=document.getElementById("importFile").files[0];
  if(!file){return;}
  const fd=new FormData();fd.append("file",file);
  try{
    const res=await fetch("/api/customers/import",{method:"POST",body:fd});
    if(!res.ok){const e=await res.json().catch(()=>({}));throw new Error(e.detail||"Errore import");}
    const j=await res.json();
    alert(`Import completato. Creati: ${j.created}, aggiornati: ${j.updated}.`);
    await loadCustomersMobile();
  }catch(e){alert(e.message);}
  document.getElementById("importFile").value="";
}

// ---- PIANIFICAZIONE ----
async function loadPlanningCustomers(){
  try{
    const q=document.getElementById("customerSearch").value||"";
    const rows=await api("/api/customers?limit=80&q="+encodeURIComponent(q));
    document.getElementById("planningCustomers").innerHTML=rows.map(c=>{
      const added=deliveries.some(d=>d.customer_id===c.id);
      return `<div class="list-card">
        <div class="list-row">
          <div><strong>${esc(c.nome)}</strong><small>${esc(c.comune||"")} · ${esc(c.indirizzo)}</small></div>
          <button class="mini-btn ${added?"remove":""}" onclick="toggleDelivery(${c.id})">${added?"Rimuovi":"Aggiungi"}</button>
        </div>
      </div>`;
    }).join("")||`<div style="text-align:center;padding:16px;color:#6b7280;font-size:13px">Nessun cliente trovato</div>`;
  }catch(e){}
}
function toggleDelivery(id){
  const found=customers.find(c=>c.id===id);
  const idx=deliveries.findIndex(d=>d.customer_id===id);
  if(idx>=0) deliveries.splice(idx,1);
  else if(found) deliveries.push({
    customer_id:found.id,cliente_nome:found.nome,indirizzo:found.indirizzo,
    peso_kg:0,colli:0,scarico_mattina_da:found.scarico_mattina_da||null,
    scarico_mattina_a:found.scarico_mattina_a||null,scarico_pomeriggio_da:found.scarico_pomeriggio_da||null,
    scarico_pomeriggio_a:found.scarico_pomeriggio_a||null,tempo_scarico_min:found.tempo_scarico_min||10,
    ztl:!!found.ztl,sponda:!!found.sponda,note:found.note||"",
    lat:found.lat??null,lon:found.lon??null,
    stato_geocodifica:found.stato_geocodifica||"da_verificare",
    indirizzo_geocodificato:found.indirizzo_geocodificato||null
  });
  renderSelected();loadPlanningCustomers();
}
function renderSelected(){
  document.getElementById("deliveryCount").textContent=deliveries.length;
  document.getElementById("selectedDeliveries").innerHTML=deliveries.map((d,i)=>`
    <div class="list-card">
      <div class="list-row">
        <div><strong>${i+1}. ${esc(d.cliente_nome)}</strong><small>${esc(d.indirizzo)}</small></div>
        <button class="mini-btn remove" onclick="removeDelivery(${i})">×</button>
      </div>
    </div>`).join("")||`<div style="text-align:center;padding:16px;color:#6b7280;font-size:13px">Nessuna consegna selezionata</div>`;
}
function removeDelivery(i){deliveries.splice(i,1);renderSelected();loadPlanningCustomers();}
function clearDeliveries(){deliveries=[];renderSelected();loadPlanningCustomers();}

async function optimizeMobileRoute(){
  if(!deliveries.length) return alert("Aggiungi almeno una consegna");
  const depositId=parseInt(document.getElementById("routeDeposit").value||0);
  if(!depositId) return alert("Seleziona un deposito");
  const box=document.getElementById("routeResult");
  box.classList.remove("hidden");
  box.innerHTML=`<div class="section-card"><div style="text-align:center;padding:20px;color:#6b7280">🚚 Calcolo percorso in corso...</div></div>`;
  box.scrollIntoView({behavior:"smooth"});
  const payload={
    nome:document.getElementById("routeName").value||"Giro consegne",
    data_giro:document.getElementById("routeDate").value,
    orario_partenza:document.getElementById("routeStart").value||"08:00",
    deposit_id:depositId,
    vehicle_id:document.getElementById("routeVehicle").value?parseInt(document.getElementById("routeVehicle").value):null,
    driver_id:document.getElementById("routeDriver").value?parseInt(document.getElementById("routeDriver").value):null,
    rientro_deposito:document.getElementById("returnDepot").checked,
    prezzo_carburante_litro:parseFloat(document.getElementById("routeFuel").value)||1.75,
    consegne:deliveries
  };
  try{
    const r=await api("/api/routes/optimize",{method:"POST",body:JSON.stringify(payload)});
    deliveries=(r.consegne||[]).map(d=>({...d}));
    renderSelected();
    const warnings=[];
    (r.consegne||[]).forEach(d=>{if(d.warning)d.warning.split("|").forEach(w=>{if(w.trim())warnings.push({nome:d.cliente_nome,w:w.trim()});});});
    const warningsHtml=warnings.length?`<div class="section-card" style="margin-bottom:12px">
      <div class="section-head"><h3>⚠️ Avvisi</h3></div>
      ${warnings.map(x=>`<div class="warning-tag" style="display:block;margin-bottom:4px"><strong>${esc(x.nome)}:</strong> ${esc(x.w)}</div>`).join("")}
    </div>`:"";
    const stopsHtml=(r.consegne||[]).map((d,i)=>`
      <div class="stop-card">
        <div class="stop-header">
          <div class="stop-num">${i+1}</div>
          <div><div class="stop-name">${esc(d.cliente_nome)}</div><div class="stop-addr">${esc(d.indirizzo)}</div></div>
        </div>
        ${d.warning?`<div class="warning-tag">${esc(d.warning.split("|")[0])}</div>`:""}
        <div class="stop-times">
          <div class="stop-time"><span>Arrivo</span><strong>${esc(d.arrivo_stimato||"—")}</strong></div>
          <div class="stop-time"><span>Ripartenza</span><strong>${esc(d.partenza_stimata||"—")}</strong></div>
          <div class="stop-time"><span>Attesa</span><strong>${d.attesa_min>0?d.attesa_min+" min":"—"}</strong></div>
          <div class="stop-time"><span>Km</span><strong>${fmt(d.km_tappa)} km</strong></div>
        </div>
      </div>`).join("");
    box.innerHTML=`
      <div class="section-card">
        <div class="section-head"><h3>Risultato giro</h3></div>
        <div class="route-kpi-grid">
          <div class="route-kpi"><strong>${fmt(r.totale_km)} km</strong><span>Distanza</span></div>
          <div class="route-kpi"><strong>${Math.round(r.totale_minuti||0)} min</strong><span>Durata</span></div>
          <div class="route-kpi"><strong>€${fmt(r.costo_carburante,2)}</strong><span>Carburante</span></div>
        </div>
      </div>
      ${warningsHtml}
      <div class="section-card" style="padding:12px">
        <div class="section-head" style="margin-bottom:10px"><h3>Dettaglio fermate</h3><span style="font-size:12px;color:#6b7280">${(r.consegne||[]).length} fermate</span></div>
        ${stopsHtml}
        ${r.google_maps_url?`<a class="maps-btn" target="_blank" href="${r.google_maps_url}">🗺 Apri in Google Maps</a>`:""}
      </div>`;
    loadDashboard();
  }catch(e){
    box.innerHTML=`<div class="section-card"><strong style="color:var(--red)">Errore</strong><p style="margin-top:8px;font-size:13px;color:#6b7280">${esc(e.message)}</p></div>`;
  }
}

// ---- REPORT ----
async function loadReport(){
  const from=mval("reportFrom"),to=mval("reportTo");
  const driver=mval("reportDriver"),vehicle=mval("reportVehicle"),status=mval("reportStatus");
  const box=document.getElementById("reportContent");
  box.innerHTML=`<div style="text-align:center;padding:24px;color:#6b7280">Caricamento...</div>`;
  try{
    const params=new URLSearchParams({date_from:from,date_to:to,driver_id:driver,vehicle_id:vehicle,status});
    const r=await api("/api/reports/summary?"+params.toString());
    const m=r.metrics||{};
    const kpis=[
      {v:m.giri_effettuati||0,l:"Giri effettuati"},
      {v:m.consegne_totali||0,l:"Consegne totali"},
      {v:(fmt(m.km_totali||0))+" km",l:"Km totali"},
      {v:fmt(m.ore_totali||0)+" h",l:"Ore totali"},
      {v:fmt(m.litri_stimati||0)+" L",l:"Litri carburante"},
      {v:"€"+fmt(m.costo_carburante||0,2),l:"Costo carburante"},
      {v:"€"+fmt(m.costo_medio_giro||0,2),l:"Costo medio/giro"},
      {v:"€"+fmt(m.costo_medio_consegna||0,2),l:"Costo medio/cons."},
      {v:fmt(m.km_medi_giro||0)+" km",l:"Km medi/giro"},
      {v:fmt(m.consegne_medie_giro||0,1),l:"Cons. medie/giro"},
    ];
    // Charts dati
    const charts=r.charts||{};
    const barChart=(title,rows,key="consegne",suffix="")=>{
      if(!rows?.length) return "";
      const max=Math.max(...rows.map(x=>x[key]||0),1);
      return `<div class="section-card"><div class="section-head"><h3>${title}</h3></div>
        ${rows.slice(0,6).map(x=>`<div class="bar-row">
          <div class="bar-label">${esc(x.nome||x.mese||"")}</div>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.round((x[key]||0)/max*100)}%"></div></div>
          <div class="bar-value">${x[key]||0}${suffix}</div>
        </div>`).join("")}
      </div>`;
    };
    box.innerHTML=`
      <div class="report-kpi-grid">${kpis.map(k=>`<div class="report-kpi"><strong>${k.v}</strong><span>${k.l}</span></div>`).join("")}</div>
      ${barChart("Andamento giornaliero",charts.andamento,"consegne")}
      ${barChart("Per autista",charts.autisti,"consegne")}
      ${barChart("Per mezzo",charts.mezzi,"consegne")}
      ${barChart("Top clienti",charts.clienti,"consegne")}
    `;
  }catch(e){
    box.innerHTML=`<div class="section-card"><small>Errore: ${esc(e.message)}</small></div>`;
  }
}

// ---- SUBVIEWS (Altro) ----
async function showSubView(name){
  const titles={autisti:"Autisti",mezzi:"Mezzi",depositi:"Depositi",agenti:"Agenti"};
  document.getElementById("subViewTitle").textContent=titles[name]||name;
  document.querySelectorAll("#view-altro .section-card").forEach(el=>el.style.display="none");
  document.querySelector("#view-altro .page-head").style.display="none";
  document.getElementById("subView").classList.remove("hidden");
  document.getElementById("subViewContent").innerHTML=`<div style="text-align:center;padding:24px;color:#6b7280">Caricamento...</div>`;
  try{
    let html="";
    if(name==="autisti"){
      const rows=await api("/api/drivers");
      html=`<button class="btn-primary" onclick="openAddDriver()">+ Nuovo autista</button>`+
        rows.map(d=>`<div class="route-history-card">
          <div class="rh-head">
            <div><div class="rh-name">${esc(d.nome)} ${esc(d.cognome||"")}</div><div class="rh-date">${esc(d.telefono||"—")} · Pat. ${esc(d.patente||"—")}</div></div>
            <span class="badge ${d.stato==="In servizio"?"in_corso":"verificato"}">${esc(d.stato||"Disponibile")}</span>
          </div>
          <div class="rh-actions"><button class="mini-btn" onclick="openEditDriver(${d.id})">Modifica</button></div>
        </div>`).join("")||`<div class="list-card"><small>Nessun autista registrato.</small></div>`;
    }
    else if(name==="mezzi"){
      const rows=await api("/api/vehicles");
      html=`<button class="btn-primary" onclick="openAddVehicle()">+ Nuovo mezzo</button>`+
        rows.map(v=>`<div class="route-history-card">
          <div class="rh-head">
            <div><div class="rh-name">${esc(v.nome)}${v.targa?" · "+esc(v.targa):""}</div><div class="rh-date">${v.capacita_kg}kg · ${v.capacita_colli}colli${v.ha_sponda?" · Sponda":""}</div></div>
            <span class="badge verificato">${esc(v.stato||"Disponibile")}</span>
          </div>
          <div class="rh-actions"><button class="mini-btn" onclick="openEditVehicle(${v.id})">Modifica</button></div>
        </div>`).join("")||`<div class="list-card"><small>Nessun mezzo registrato.</small></div>`;
    }
    else if(name==="depositi"){
      const rows=await api("/api/deposits");
      html=`<button class="btn-primary" onclick="openAddDeposit()">+ Nuovo deposito</button>`+
        rows.map(d=>`<div class="route-history-card">
          <div class="rh-head">
            <div><div class="rh-name">${esc(d.nome)}${d.predefinito?" ★":""}</div><div class="rh-date">${esc(d.indirizzo)}</div></div>
          </div>
          <div class="rh-actions"><button class="mini-btn" onclick="openEditDeposit(${d.id})">Modifica</button></div>
        </div>`).join("")||`<div class="list-card"><small>Nessun deposito registrato.</small></div>`;
    }
    else if(name==="storico"){
      html=`<button class="btn-primary" style="margin-bottom:12px" onclick="showView('giri',document.querySelector('.bnav-btn:nth-child(2)'));showGiriTab('storico',document.querySelector('.tab-btn:last-child'))">Vai a Storico giri →</button>
      <div style="text-align:center;padding:16px;color:var(--muted);font-size:13px">Usa la sezione Giri → Storico per visualizzare lo storico completo con filtri.</div>`;
    }
    else if(name==="agenti"){
      const rows=await api("/api/agents").catch(()=>[]);
      html=`<button class="btn-primary" onclick="openAddAgent()">+ Nuovo agente</button>`+
        rows.map(a=>`<div class="route-history-card">
          <div class="rh-head">
            <div><div class="rh-name">${esc(a.full_name||a.nome)}</div><div class="rh-date">${esc(a.zona||"—")} · ${a.clienti_assegnati||0} clienti</div></div>
            <span class="badge ${a.attivo?"verificato":"da_verificare"}">${a.attivo?"Attivo":"Non attivo"}</span>
          </div>
          <div class="rh-actions"><button class="mini-btn" onclick="openEditAgent(${a.id})">Modifica</button></div>
        </div>`).join("")||`<div class="list-card"><small>Nessun agente registrato.</small></div>`;
    }
    document.getElementById("subViewContent").innerHTML=html;
  }catch(e){
    document.getElementById("subViewContent").innerHTML=`<div class="list-card"><small>Errore: ${esc(e.message)}</small></div>`;
  }
}
function hideSubView(){
  document.getElementById("subView").classList.add("hidden");
  document.querySelectorAll("#view-altro .section-card").forEach(el=>el.style.display="");
  document.querySelector("#view-altro .page-head").style.display="";
}

// ============================================================
// MODAL UNIVERSALE
// ============================================================
let _modalSave=null;
function openMModal(title,bodyHTML,saveCallback,showDelete=false,deleteCb=null){
  document.getElementById("mModalTitle").textContent=title;
  document.getElementById("mModalBody").innerHTML=bodyHTML;
  _modalSave=saveCallback;
  const footer=document.getElementById("mModalFooter");
  footer.innerHTML="";
  if(showDelete&&deleteCb){
    const b=document.createElement("button");b.className="btn-danger-outline";b.textContent="Elimina";b.onclick=deleteCb;footer.appendChild(b);
  }
  const bc=document.createElement("button");bc.className="btn-secondary";bc.textContent="Annulla";bc.onclick=closeMModal;footer.appendChild(bc);
  const bs=document.createElement("button");bs.className="btn-primary";bs.textContent="Salva";bs.onclick=()=>_modalSave&&_modalSave();footer.appendChild(bs);
  document.getElementById("mModal").classList.remove("hidden");
}
function closeMModal(){document.getElementById("mModal").classList.add("hidden");_modalSave=null;}

// ============================================================
// CRUD CLIENTI
// ============================================================
function customerForm(c={}){return `
  <div class="form-group"><label>Nome *</label><input id="fNome" value="${esc(c.nome||'')}"></div>
  <div class="form-group"><label>Codice cliente</label><input id="fCodice" value="${esc(c.codice_cliente||'')}"></div>
  <div class="form-group"><label>Indirizzo *</label><input id="fIndirizzo" value="${esc(c.indirizzo||'')}"></div>
  <div class="form-row">
    <div class="form-group"><label>Comune</label><input id="fComune" value="${esc(c.comune||'')}"></div>
    <div class="form-group"><label>Provincia</label><input id="fProvincia" value="${esc(c.provincia||'')}"></div>
  </div>
  <div class="form-group"><label>Telefono</label><input id="fTelefono" type="tel" value="${esc(c.telefono||'')}"></div>
  <div class="form-group"><label>Email</label><input id="fEmail" type="email" value="${esc(c.email||'')}"></div>
  <div class="form-group"><label>Referente</label><input id="fReferente" value="${esc(c.referente||'')}"></div>
  <div class="form-row">
    <div class="form-group"><label>Scarico mattina da</label><input id="fMatDa" type="time" value="${esc(c.scarico_mattina_da||'')}"></div>
    <div class="form-group"><label>a</label><input id="fMatA" type="time" value="${esc(c.scarico_mattina_a||'')}"></div>
  </div>
  <div class="form-row">
    <div class="form-group"><label>Scarico pomeriggio da</label><input id="fPomDa" type="time" value="${esc(c.scarico_pomeriggio_da||'')}"></div>
    <div class="form-group"><label>a</label><input id="fPomA" type="time" value="${esc(c.scarico_pomeriggio_a||'')}"></div>
  </div>
  <div class="form-group"><label>Tempo scarico (min)</label><input id="fTempo" type="number" value="${c.tempo_scarico_min||10}"></div>
  <label class="check-row"><input id="fZtl" type="checkbox" ${c.ztl?"checked":""}><span>ZTL</span></label>
  <label class="check-row"><input id="fSponda" type="checkbox" ${c.sponda?"checked":""}><span>Sponda richiesta</span></label>
  <label class="check-row"><input id="fTranspallet" type="checkbox" ${c.transpallet?"checked":""}><span>Transpallet</span></label>
  <div class="form-group"><label>Note</label><textarea id="fNote" rows="3" style="width:100%;padding:10px;border:1.5px solid var(--border);border-radius:9px;font-size:14px;background:var(--bg)">${esc(c.note||'')}</textarea></div>`;}

function openAddCustomer(){
  openMModal("Nuovo cliente",customerForm(),async()=>{
    if(!mval("fNome")||!mval("fIndirizzo")) return alert("Nome e indirizzo obbligatori");
    try{await api("/api/customers",{method:"POST",body:JSON.stringify({
      nome:mval("fNome"),indirizzo:mval("fIndirizzo"),codice_cliente:mval("fCodice")||null,
      comune:mval("fComune")||null,provincia:mval("fProvincia")||null,
      telefono:mval("fTelefono")||null,email:mval("fEmail")||null,referente:mval("fReferente")||null,
      scarico_mattina_da:mval("fMatDa")||null,scarico_mattina_a:mval("fMatA")||null,
      scarico_pomeriggio_da:mval("fPomDa")||null,scarico_pomeriggio_a:mval("fPomA")||null,
      tempo_scarico_min:parseInt(mval("fTempo"))||10,
      ztl:mcheck("fZtl"),sponda:mcheck("fSponda"),transpallet:mcheck("fTranspallet"),note:mval("fNote")||null
    })});closeMModal();loadCustomersMobile();}catch(e){alert(e.message);}
  });
}
function openEditCustomer(id){
  const c=customers.find(x=>x.id===id);if(!c)return;
  openMModal("Modifica cliente",customerForm(c),async()=>{
    if(!mval("fNome")||!mval("fIndirizzo")) return alert("Nome e indirizzo obbligatori");
    try{await api(`/api/customers/${id}`,{method:"PUT",body:JSON.stringify({
      nome:mval("fNome"),indirizzo:mval("fIndirizzo"),codice_cliente:mval("fCodice")||null,
      comune:mval("fComune")||null,provincia:mval("fProvincia")||null,
      telefono:mval("fTelefono")||null,email:mval("fEmail")||null,referente:mval("fReferente")||null,
      scarico_mattina_da:mval("fMatDa")||null,scarico_mattina_a:mval("fMatA")||null,
      scarico_pomeriggio_da:mval("fPomDa")||null,scarico_pomeriggio_a:mval("fPomA")||null,
      tempo_scarico_min:parseInt(mval("fTempo"))||10,
      ztl:mcheck("fZtl"),sponda:mcheck("fSponda"),transpallet:mcheck("fTranspallet"),note:mval("fNote")||null
    })});closeMModal();loadCustomersMobile();}catch(e){alert(e.message);}
  },true,async()=>{
    if(!confirm("Eliminare questo cliente?")) return;
    try{await api(`/api/customers/${id}`,{method:"DELETE"});closeMModal();loadCustomersMobile();}catch(e){alert(e.message);}
  });
}

// ============================================================
// CRUD AUTISTI
// ============================================================
function driverForm(d={}){return `
  <div class="form-row">
    <div class="form-group"><label>Nome *</label><input id="fNome" value="${esc(d.nome||'')}"></div>
    <div class="form-group"><label>Cognome</label><input id="fCognome" value="${esc(d.cognome||'')}"></div>
  </div>
  <div class="form-group"><label>Telefono</label><input id="fTelefono" type="tel" value="${esc(d.telefono||'')}"></div>
  <div class="form-group"><label>Email</label><input id="fEmail" type="email" value="${esc(d.email||'')}"></div>
  <div class="form-group"><label>Patente</label><input id="fPatente" value="${esc(d.patente||'')}"></div>
  <div class="form-group"><label>Scadenza patente</label><input id="fScadPatente" type="date" value="${esc(d.scadenza_patente||'')}"></div>
  <label class="check-row"><input id="fCqc" type="checkbox" ${d.cqc?"checked":""}><span>CQC</span></label>
  <div class="form-group"><label>Scadenza CQC</label><input id="fScadCqc" type="date" value="${esc(d.scadenza_cqc||'')}"></div>
  <label class="check-row"><input id="fAdr" type="checkbox" ${d.adr?"checked":""}><span>ADR</span></label>
  <div class="form-group"><label>Note</label><textarea id="fNote" rows="3" style="width:100%;padding:10px;border:1.5px solid var(--border);border-radius:9px;font-size:14px;background:var(--bg)">${esc(d.note||'')}</textarea></div>`;}

function openAddDriver(){openMModal("Nuovo autista",driverForm(),async()=>{
  if(!mval("fNome")) return alert("Nome obbligatorio");
  try{await api("/api/drivers",{method:"POST",body:JSON.stringify({nome:mval("fNome"),cognome:mval("fCognome")||null,telefono:mval("fTelefono")||null,email:mval("fEmail")||null,patente:mval("fPatente")||null,scadenza_patente:mval("fScadPatente")||null,cqc:mcheck("fCqc"),scadenza_cqc:mval("fScadCqc")||null,adr:mcheck("fAdr"),note:mval("fNote")||null})});
  closeMModal();showSubView("autisti");loadResources();}catch(e){alert(e.message);}});}

async function openEditDriver(id){
  try{const rows=await api("/api/drivers");const d=rows.find(x=>x.id===id);if(!d)return;
  openMModal("Modifica autista",driverForm(d),async()=>{
    if(!mval("fNome")) return alert("Nome obbligatorio");
    try{await api(`/api/drivers/${id}`,{method:"PUT",body:JSON.stringify({nome:mval("fNome"),cognome:mval("fCognome")||null,telefono:mval("fTelefono")||null,email:mval("fEmail")||null,patente:mval("fPatente")||null,scadenza_patente:mval("fScadPatente")||null,cqc:mcheck("fCqc"),scadenza_cqc:mval("fScadCqc")||null,adr:mcheck("fAdr"),note:mval("fNote")||null})});
    closeMModal();showSubView("autisti");loadResources();}catch(e){alert(e.message);}
  },true,async()=>{if(!confirm("Eliminare?"))return;try{await api(`/api/drivers/${id}`,{method:"DELETE"});closeMModal();showSubView("autisti");loadResources();}catch(e){alert(e.message);}});
  }catch(e){alert(e.message);}
}

// ============================================================
// CRUD MEZZI
// ============================================================
function vehicleForm(v={}){return `
  <div class="form-group"><label>Nome *</label><input id="fNome" value="${esc(v.nome||'')}"></div>
  <div class="form-group"><label>Targa</label><input id="fTarga" value="${esc(v.targa||'')}"></div>
  <div class="form-row">
    <div class="form-group"><label>Consumo (L/100km)</label><input id="fConsumo" type="number" step="0.1" value="${v.consumo_l_100km||8.5}"></div>
    <div class="form-group"><label>Capacità (kg)</label><input id="fKg" type="number" value="${v.capacita_kg||1000}"></div>
  </div>
  <div class="form-group"><label>Capacità (colli)</label><input id="fColli" type="number" value="${v.capacita_colli||100}"></div>
  <label class="check-row"><input id="fSponda" type="checkbox" ${v.ha_sponda?"checked":""}><span>Ha sponda</span></label>
  <label class="check-row"><input id="fZtl" type="checkbox" ${v.accesso_ztl?"checked":""}><span>Accesso ZTL</span></label>
  <div class="form-group"><label>Note</label><textarea id="fNote" rows="3" style="width:100%;padding:10px;border:1.5px solid var(--border);border-radius:9px;font-size:14px;background:var(--bg)">${esc(v.note||'')}</textarea></div>`;}

function openAddVehicle(){openMModal("Nuovo mezzo",vehicleForm(),async()=>{
  if(!mval("fNome")) return alert("Nome obbligatorio");
  try{await api("/api/vehicles",{method:"POST",body:JSON.stringify({nome:mval("fNome"),targa:mval("fTarga")||null,consumo_l_100km:parseFloat(mval("fConsumo"))||8.5,capacita_kg:parseFloat(mval("fKg"))||1000,capacita_colli:parseInt(mval("fColli"))||100,ha_sponda:mcheck("fSponda"),accesso_ztl:mcheck("fZtl"),note:mval("fNote")||null})});
  closeMModal();showSubView("mezzi");loadResources();}catch(e){alert(e.message);}});}

async function openEditVehicle(id){
  try{const rows=await api("/api/vehicles");const v=rows.find(x=>x.id===id);if(!v)return;
  openMModal("Modifica mezzo",vehicleForm(v),async()=>{
    if(!mval("fNome")) return alert("Nome obbligatorio");
    try{await api(`/api/vehicles/${id}`,{method:"PUT",body:JSON.stringify({nome:mval("fNome"),targa:mval("fTarga")||null,consumo_l_100km:parseFloat(mval("fConsumo"))||8.5,capacita_kg:parseFloat(mval("fKg"))||1000,capacita_colli:parseInt(mval("fColli"))||100,ha_sponda:mcheck("fSponda"),accesso_ztl:mcheck("fZtl"),note:mval("fNote")||null})});
    closeMModal();showSubView("mezzi");loadResources();}catch(e){alert(e.message);}
  },true,async()=>{if(!confirm("Eliminare?"))return;try{await api(`/api/vehicles/${id}`,{method:"DELETE"});closeMModal();showSubView("mezzi");loadResources();}catch(e){alert(e.message);}});
  }catch(e){alert(e.message);}
}

// ============================================================
// CRUD DEPOSITI
// ============================================================
function depositForm(d={}){return `
  <div class="form-group"><label>Nome *</label><input id="fNome" value="${esc(d.nome||'')}"></div>
  <div class="form-group"><label>Indirizzo *</label><input id="fIndirizzo" value="${esc(d.indirizzo||'')}"></div>
  <label class="check-row"><input id="fDefault" type="checkbox" ${d.predefinito?"checked":""}><span>Deposito predefinito</span></label>
  <div class="form-group"><label>Note</label><textarea id="fNote" rows="3" style="width:100%;padding:10px;border:1.5px solid var(--border);border-radius:9px;font-size:14px;background:var(--bg)">${esc(d.note||'')}</textarea></div>`;}

function openAddDeposit(){openMModal("Nuovo deposito",depositForm(),async()=>{
  if(!mval("fNome")||!mval("fIndirizzo")) return alert("Nome e indirizzo obbligatori");
  try{await api("/api/deposits",{method:"POST",body:JSON.stringify({nome:mval("fNome"),indirizzo:mval("fIndirizzo"),predefinito:mcheck("fDefault"),note:mval("fNote")||null})});
  closeMModal();showSubView("depositi");loadResources();}catch(e){alert(e.message);}});}

async function openEditDeposit(id){
  try{const rows=await api("/api/deposits");const d=rows.find(x=>x.id===id);if(!d)return;
  openMModal("Modifica deposito",depositForm(d),async()=>{
    if(!mval("fNome")||!mval("fIndirizzo")) return alert("Nome e indirizzo obbligatori");
    try{await api(`/api/deposits/${id}`,{method:"PUT",body:JSON.stringify({nome:mval("fNome"),indirizzo:mval("fIndirizzo"),predefinito:mcheck("fDefault"),note:mval("fNote")||null})});
    closeMModal();showSubView("depositi");loadResources();}catch(e){alert(e.message);}
  },true,async()=>{if(!confirm("Eliminare?"))return;try{await api(`/api/deposits/${id}`,{method:"DELETE"});closeMModal();showSubView("depositi");loadResources();}catch(e){alert(e.message);}});
  }catch(e){alert(e.message);}
}

// ============================================================
// CRUD AGENTI
// ============================================================
function agentForm(a={}){return `
  <div class="form-row">
    <div class="form-group"><label>Nome *</label><input id="fNome" value="${esc(a.nome||'')}"></div>
    <div class="form-group"><label>Cognome</label><input id="fCognome" value="${esc(a.cognome||'')}"></div>
  </div>
  <div class="form-group"><label>Codice agente</label><input id="fCodice" value="${esc(a.codice_agente||'')}"></div>
  <div class="form-group"><label>Telefono</label><input id="fTelefono" type="tel" value="${esc(a.telefono||'')}"></div>
  <div class="form-group"><label>Email</label><input id="fEmail" type="email" value="${esc(a.email||'')}"></div>
  <div class="form-group"><label>Zona</label><input id="fZona" value="${esc(a.zona||'')}"></div>
  <label class="check-row"><input id="fAttivo" type="checkbox" ${a.attivo!==false?"checked":""}><span>Attivo</span></label>
  <div class="form-group"><label>Note</label><textarea id="fNote" rows="3" style="width:100%;padding:10px;border:1.5px solid var(--border);border-radius:9px;font-size:14px;background:var(--bg)">${esc(a.note||'')}</textarea></div>`;}

function openAddAgent(){openMModal("Nuovo agente",agentForm(),async()=>{
  if(!mval("fNome")) return alert("Nome obbligatorio");
  try{await api("/api/agents",{method:"POST",body:JSON.stringify({nome:mval("fNome"),cognome:mval("fCognome")||null,codice_agente:mval("fCodice")||null,telefono:mval("fTelefono")||null,email:mval("fEmail")||null,zona:mval("fZona")||null,attivo:mcheck("fAttivo"),note:mval("fNote")||null})});
  closeMModal();showSubView("agenti");}catch(e){alert(e.message);}});}

async function openEditAgent(id){
  try{const rows=await api("/api/agents");const a=rows.find(x=>x.id===id);if(!a)return;
  openMModal("Modifica agente",agentForm(a),async()=>{
    if(!mval("fNome")) return alert("Nome obbligatorio");
    try{await api(`/api/agents/${id}`,{method:"PUT",body:JSON.stringify({nome:mval("fNome"),cognome:mval("fCognome")||null,codice_agente:mval("fCodice")||null,telefono:mval("fTelefono")||null,email:mval("fEmail")||null,zona:mval("fZona")||null,attivo:mcheck("fAttivo"),note:mval("fNote")||null})});
    closeMModal();showSubView("agenti");}catch(e){alert(e.message);}
  },true,async()=>{if(!confirm("Eliminare?"))return;try{await api(`/api/agents/${id}`,{method:"DELETE"});closeMModal();showSubView("agenti");}catch(e){alert(e.message);}});
  }catch(e){alert(e.message);}
}

boot();
