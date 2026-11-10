function fmtNumber(n, digits=0){
  const num = Number(n || 0);
  return num.toLocaleString("it-IT", {minimumFractionDigits:digits, maximumFractionDigits:digits});
}
function fmtMoney(n){ return "€ " + fmtNumber(n, 2); }

function reportParams(){
  return new URLSearchParams({
    date_from: val("reportDateFrom") || "",
    date_to: val("reportDateTo") || "",
    agent_id: agentsFeatureEnabled() ? (val("reportAgent") || "") : "",
    customer_id: val("reportCustomer") || "",
    driver_id: val("reportDriver") || "",
    vehicle_id: val("reportVehicle") || "",
    status: val("reportStatus") || ""
  });
}

function fillSelectOptions(id, rows, labelFn, firstLabel){
  const sel = document.getElementById(id);
  if(!sel) return;
  const current = sel.value || "";
  sel.innerHTML = `<option value="">${firstLabel}</option>`;
  rows.forEach(x=>{ sel.innerHTML += `<option value="${x.id}">${esc(labelFn(x))}</option>`; });
  if(current) sel.value = current;
}

async function ensureReportFilters(){
  if(featureLockedForTab("report")) return;
  try{
    if(agentsFeatureEnabled() && !agentsCache.length) await loadAgents();
    if(!customersCache.length){
      const customers = [];
      for(let offset=0;;offset+=1000){
        const batch = await api(`/api/customers?limit=1000&offset=${offset}`);
        customers.push(...batch);
        if(batch.length < 1000) break;
      }
      customersCache = customers;
    }
    if(!driversCache.length) await loadDrivers();
    if(!vehiclesCache.length) await loadVehicles();
  }catch(e){}
  const ag = document.getElementById("reportAgent");
  if(ag && ag.options.length <= 2){
    const cur = ag.value;
    ag.innerHTML = `<option value="">Tutti gli agenti</option><option value="interno">Cliente interno</option>`;
    agentsCache.forEach(a=> ag.innerHTML += `<option value="${a.id}">${esc(agentDisplayName(a))}</option>`);
    ag.value = cur || "";
  }
  fillSelectOptions("reportCustomer", customersCache, c => `${c.codice_cliente ? c.codice_cliente + " · " : ""}${c.nome}`, "Tutti i clienti");
  fillSelectOptions("reportDriver", driversCache, d => driverFullName(d), "Tutti gli autisti");
  fillSelectOptions("reportVehicle", vehiclesCache, v => `${v.nome}${v.targa ? " · " + v.targa : ""}`, "Tutti i mezzi");
  updateReportFilterSummary();
}

function resetReportFilters(){
  if(showLockedOrProceed("report")) return;
  ["reportDateFrom","reportDateTo","reportAgent","reportCustomer","reportDriver","reportVehicle","reportStatus"].forEach(id=>set(id,""));
  updateReportFilterSummary();
  loadReport();
}

function toggleReportFilters(forceOpen){
  const panel = document.getElementById("reportFilterPanel");
  const btn = document.getElementById("reportFilterToggleBtn");
  if(!panel) return;
  const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !shouldOpen);
  if(btn){
    btn.setAttribute("aria-expanded", String(shouldOpen));
    btn.textContent = `${shouldOpen ? '⌃' : '⌄'} ${shouldOpen ? 'Nascondi filtri' : 'Mostra filtri'}`;
  }
}

function updateReportFilterSummary(){
  const summary = document.getElementById("reportFilterSummary");
  if(!summary) return;
  const ids = ["reportDateFrom","reportDateTo","reportAgent","reportCustomer","reportDriver","reportVehicle","reportStatus"];
  const active = ids.filter(id=>{ const el=document.getElementById(id); return el && String(el.value || "").trim(); }).length;
  summary.textContent = active ? `${active} filtro${active>1?'i':''} applicat${active>1?'i':'o'}` : "Nessun filtro applicato";
  syncReportPeriodChips();
}

// Scorciatoie di periodo: compilano le date del filtro (stesso comportamento dei campi Da/A data).
function reportPeriodRange(kind, today=new Date()){
  const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  const y=today.getFullYear(), m=today.getMonth();
  if(kind === "7"){ const from=new Date(y, m, today.getDate()-6); return [iso(from), iso(today)]; }
  if(kind === "month") return [iso(new Date(y, m, 1)), iso(today)];
  if(kind === "last-month") return [iso(new Date(y, m-1, 1)), iso(new Date(y, m, 0))];
  if(kind === "year") return [iso(new Date(y, 0, 1)), iso(today)];
  return ["", ""];
}

function syncReportPeriodChips(){
  if(typeof document.querySelectorAll !== "function") return;
  const from=val("reportDateFrom") || "", to=val("reportDateTo") || "";
  document.querySelectorAll("#reportPeriod [data-period]").forEach(b=>{
    const [a,c]=reportPeriodRange(b.dataset.period);
    b.setAttribute("aria-pressed", String(a === from && c === to));
  });
}

function setReportPeriod(kind){
  if(showLockedOrProceed("report")) return;
  const [from,to]=reportPeriodRange(kind);
  set("reportDateFrom", from);
  set("reportDateTo", to);
  updateReportFilterSummary();
  loadReport();
}

let reportRequest = 0;
async function loadReport(){
  if(showLockedOrProceed("report")) return;
  const request = ++reportRequest;
  await ensureReportFilters();
  if(request !== reportRequest) return;
  updateReportFilterSummary();
  const box = document.getElementById("tab-report");
  if(!box) return;
  try{
    const data = await api("/api/reports/summary?" + reportParams().toString());
    if(request !== reportRequest) return;
    reportData = data;
    renderReportMetrics(reportData.metrics || {});
    renderReportCharts(reportData.charts || {});
    renderReportTables();
    renderReportInsights(reportData.insights || []);
  }catch(e){
    if(request !== reportRequest) return;
    toast("Errore caricamento report: " + (e.message || "Errore"));
  }
}

async function generateReportAIv67(){
  if(showLockedOrProceed("report")) return;
  const box = document.getElementById("reportAiSummaryV67");
  if(!box) return;
  box.classList.remove("hidden");
  box.innerHTML = `<strong>Report AI</strong><p>Generazione riepilogo assistito in corso...</p>`;
  try{
    const r = await api("/api/reports/ai-summary?" + reportParams().toString());
    box.innerHTML = `<strong>Report AI</strong><p>${esc(r.text || "Nessun riepilogo generato.")}</p>${r.fallback ? `<small>Nota: AI non configurata, testo locale di supporto.</small>` : ``}`;
  }catch(e){
    box.innerHTML = `<strong>AI non disponibile</strong><p>${esc(e.message || "Non è stato possibile generare il report AI.")}</p>`;
  }
}

function renderReportMetrics(m){
  const setText=(id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
  const total=Number(m.consegne_totali)||0, done=Number(m.consegnate)||0;
  const success=total ? done/total*100 : 0;
  setText("repRiuscite", total ? fmtNumber(success) + "%" : "–");
  setText("repConsegnate", fmtNumber(done));
  setText("repMancate", fmtNumber(m.mancate));
  setText("repGiri", fmtNumber(m.giri_effettuati));
  setText("repConsegne", fmtNumber(m.consegne_totali));
  setText("repKm", fmtNumber(m.km_totali, Number(m.km_totali) >= 100 ? 0 : 2) + " km");
  setText("repOre", fmtNumber(m.ore_totali,2) + " h");
  setText("repLitri", fmtNumber(m.litri_stimati,2) + " L");
  setText("repCosto", fmtMoney(m.costo_carburante));
  setText("repCostoGiro", fmtMoney(m.costo_medio_giro));
  setText("repCostoConsegna", fmtMoney(m.costo_medio_consegna));
  setText("repKmGiro", fmtNumber(m.km_medi_giro,2) + " km");
  setText("repConsegneGiro", fmtNumber(m.consegne_medie_giro,2));
  reportChart("reportKpiRing", "ring", {value: success, tone: 6, label: "Consegne riuscite", display: total ? fmtNumber(success) + "%" : "–", note: `${fmtNumber(done)} su ${fmtNumber(total)} fermate`});
}

/* Grafici del Report: componente .gf-chart del sistema di stile (static/design-system/charts.js). */
function chartEmpty(id, text="Nessun dato nel periodo"){
  const host=document.getElementById(id); if(!host) return;
  const target=host.querySelector(".gf-chart__canvas") || host;
  target.innerHTML = `<div class="gf-empty"><p>${esc(text)}</p></div>`;
  const legend=host.querySelector(".gf-chart__legend"); if(legend) legend.innerHTML = "";
}

function reportChart(id, type, cfg){
  const host=document.getElementById(id);
  if(!host || typeof window === "undefined" || !window.GFCharts) return;
  host.querySelector(".gf-chart__canvas .gf-empty")?.remove();
  window.GFCharts.draw(host, type, cfg);
}

function compactDateLabel(value){
  const s = String(value || "");
  if(/^\d{4}-\d{2}-\d{2}$/.test(s)) return s.slice(8,10) + "/" + s.slice(5,7);
  return s;
}

function reportDayTitle(value){
  return typeof gfDateIt === "function" ? (gfDateIt(value) || compactDateLabel(value)) : compactDateLabel(value);
}

// Le prime voci con il proprio colore; oltre l'ottava si raccolgono in «Altri».
function reportTopSegments(rows, key, labelFn = r => r.nome){
  const sorted=[...(rows||[])].filter(r=>Number(r[key])>0).sort((a,b)=>Number(b[key])-Number(a[key]));
  const head=sorted.length > 8 ? sorted.slice(0,7) : sorted;
  const segments=head.map((r,i)=>({label: labelFn(r), value: Number(r[key]), tone: i+1}));
  if(sorted.length > 8) segments.push({label: "Altri", value: sorted.slice(7).reduce((s,r)=>s+Number(r[key]),0), tone: 8});
  return segments;
}

const REPORT_FUEL_TONES = {gasolio: 2, benzina: 4, elettrico: 3, gpl: 1, metano: 7, ibrido_benzina: 5, ibrido_diesel: 6, ibrido_plugin_benzina: 5, ibrido_plugin_diesel: 6};
function reportFuelOf(vehicleId){
  const v=(vehiclesCache||[]).find(x=>String(x.id)===String(vehicleId));
  return v ? (v.alimentazione || "gasolio") : "";
}
function reportFuelLabel(type){
  if(!type) return "Senza mezzo";
  const labels = typeof GF_FUEL_LABELS_V895 !== "undefined" ? GF_FUEL_LABELS_V895 : {};
  return labels[type] || type;
}

const REPORT_DRIVER_METRICS = {
  consegne: {sub: "Fermate nel periodo", format: {}},
  km: {sub: "Km pianificati nel periodo", format: {suffix: " km"}},
  ore: {sub: "Ore di guida, rilevate o stimate", format: {suffix: " h", decimals: 1}},
  costo: {sub: "Energia stimata nel periodo", format: {prefix: "€ ", decimals: 2}}
};
let reportDriverMetric = "consegne";
function setReportDriverMetric(metric){
  if(!REPORT_DRIVER_METRICS[metric]) return;
  reportDriverMetric = metric;
  document.querySelectorAll("#reportDriverMetric [data-metric]").forEach(b=>b.setAttribute("aria-pressed", String(b.dataset.metric === metric)));
  renderReportDriversChart();
}
function renderReportDriversChart(){
  const rows=(reportData?.charts?.autisti || []).slice(0,8);
  const sub=document.getElementById("reportDriversChartSub");
  const meta=REPORT_DRIVER_METRICS[reportDriverMetric];
  if(sub) sub.textContent = `${meta.sub}, un colore per autista`;
  if(!rows.length){ chartEmpty("reportDriversChart"); return; }
  // Il colore segue l'autista (ordine alfabetico), l'ordine delle colonne segue la misura scelta.
  const tones=new Map([...rows].sort((a,b)=>String(a.nome).localeCompare(String(b.nome),"it")).map((r,i)=>[r.id ?? r.nome, i+1]));
  const sorted=[...rows].sort((a,b)=>Number(b[reportDriverMetric]||0)-Number(a[reportDriverMetric]||0));
  const short=name=>{ const p=String(name||"").trim().split(/\s+/); return p.length > 1 ? `${p[0]} ${p[1][0]}.` : (p[0] || "–"); };
  reportChart("reportDriversChart", "columns", {
    label: "Rendimento per autista", labels: sorted.map(r=>short(r.nome)), titles: sorted.map(r=>r.nome),
    series: [{name: meta.sub, values: sorted.map(r=>Number(r[reportDriverMetric])||0), tones: sorted.map(r=>tones.get(r.id ?? r.nome))}],
    format: meta.format, showValues: true, height: 250
  });
}

function reportBarList(id, rows, key, tone){
  const el=document.getElementById(id); if(!el) return;
  rows=(rows||[]).filter(r=>Number(r[key])>0).slice(0,8);
  if(!rows.length){ el.innerHTML = `<div class="gf-empty"><p>Nessun dato nel periodo</p></div>`; return; }
  const max=Math.max(1,...rows.map(r=>Number(r[key])||0));
  el.innerHTML = `<ul class="gf-bar-chart">${rows.map(r=>{
    const v=Number(r[key])||0;
    return `<li class="gf-bar-chart__row"><span class="gf-bar-chart__label">${esc(r.nome || "Cliente")}</span><span class="gf-bar-chart__track"><span class="gf-bar-chart__fill" data-tone="${tone}" data-gf-width="${reportWidthStep(v, max)}"></span></span><span class="gf-bar-chart__value">${fmtNumber(v)}</span></li>`;
  }).join("")}</ul>`;
}

function reportWidthStep(value, max){
  const v=Number(value)||0;
  return v > 0 ? Math.max(5, Math.round(v/(max||1)*20)*5) : 0;
}
function reportCellBar(value, max, tone, label){
  return `<div class="gf-cellbar"><span class="gf-bar-chart__track"><span class="gf-bar-chart__fill" data-tone="${tone}" data-gf-width="${reportWidthStep(value, max)}"></span></span><span>${label}</span></div>`;
}

function renderReportCharts(charts){
  const days=charts.andamento || [];
  const labels=days.map(r=>compactDateLabel(r.data)), titles=days.map(r=>reportDayTitle(r.data));
  const sparks=[["reportSparkStops","consegne",1],["reportSparkKm","km",2],["reportSparkCost","costo",7]];
  sparks.forEach(([id,key,tone])=>{
    const host=document.getElementById(id); if(!host) return;
    if(days.length < 2){ const c=host.querySelector(".gf-chart__canvas"); if(c) c.innerHTML=""; return; }
    reportChart(id, "spark", {values: days.map(r=>Number(r[key])||0), tone});
  });
  if(!days.length){ chartEmpty("reportKmChart"); chartEmpty("reportCostChart"); }
  else{
    reportChart("reportKmChart", "area", {label: "Chilometri al giorno", labels, titles, series: [{name: "Km", tone: 2, values: days.map(r=>Number(r.km)||0)}], format: {suffix: " km"}});
    reportChart("reportCostChart", "area", {label: "Energia al giorno", labels, titles, series: [{name: "Energia", tone: 7, values: days.map(r=>Number(r.costo)||0)}], format: {prefix: "€ ", decimals: 2}});
  }

  const tables=reportData?.tables || {};
  const vehicles=tables.mezzi || charts.mezzi || [];
  const stops=reportTopSegments(vehicles, "consegne", r=>r.nome || "Nessun mezzo");
  if(stops.length) reportChart("reportVehiclesChart", "pie", {label: "Fermate per mezzo", segments: stops});
  else chartEmpty("reportVehiclesChart");

  const byFuel=new Map();
  vehicles.forEach(r=>{ const t=reportFuelOf(r.id); byFuel.set(t, (byFuel.get(t)||0) + (Number(r.costo)||0)); });
  const fuel=[...byFuel.entries()].filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]).map(([t,v])=>({label: reportFuelLabel(t), value: v, tone: REPORT_FUEL_TONES[t] || 8}));
  const fuelTotal=fuel.reduce((s,x)=>s+x.value,0);
  if(fuel.length) reportChart("reportEnergyChart", "donut", {label: "Spesa per alimentazione", segments: fuel, format: {prefix: "€ ", decimals: 2}, thickness: 24, center: {value: fuelTotal >= 1000 ? "€ " + fmtNumber(fuelTotal) : fmtMoney(fuelTotal), label: "energia stimata"}});
  else chartEmpty("reportEnergyChart");

  renderReportDriversChart();
  reportBarList("reportCustomersChart", charts.clienti || [], "consegne", 5);

  const agents=reportTopSegments(charts.agenti || [], "consegne");
  if(agents.length) reportChart("reportAgentDonut", "donut", {label: "Fermate per agente", segments: agents, center: {value: fmtNumber(agents.reduce((s,x)=>s+x.value,0)), label: "fermate"}});
  else chartEmpty("reportAgentDonut");
}

function sortReportTable(table, key){
  if(!reportSort[table]) reportSort[table] = {key, dir:-1};
  reportSort[table].dir = reportSort[table].key === key ? reportSort[table].dir * -1 : -1;
  reportSort[table].key = key;
  renderReportTables();
}

function renderReportTables(){
  if(!reportData) return;
  const t=reportData.tables || {};
  const driverQ=(document.getElementById("reportDriverTableSearch")?.value || "").toLowerCase();
  let drivers=[...(t.autisti||[])].filter(r=>!driverQ || String(r.nome||"").toLowerCase().includes(driverQ));
  const s=reportSort.drivers || {key:"consegne", dir:-1};
  drivers.sort((a,b)=>((a[s.key]>b[s.key])?1:-1)*s.dir);
  const maxDriver=Math.max(1,...(t.autisti||[]).map(r=>Number(r.consegne)||0));
  const driverBody=document.getElementById("reportDriversBody");
  if(driverBody) driverBody.innerHTML=drivers.map(r=>`<tr><td data-label="Autista"><strong>${esc(r.nome)}</strong></td><td data-label="Giri">${r.giri}</td><td data-label="Fermate">${reportCellBar(r.consegne, maxDriver, 1, fmtNumber(r.consegne))}</td><td data-label="Km">${fmtNumber(r.km,2)}</td><td data-label="Ore">${fmtNumber(r.ore,2)}</td><td data-label="Costo">${fmtMoney(r.costo)}</td><td data-label="Fermate/giro">${fmtNumber(r.consegne_per_giro,2)}</td></tr>`).join("") || `<tr><td colspan="7"><div class="gf-empty"><p>Nessun dato</p></div></td></tr>`;

  const agentBody=document.getElementById("reportAgentsBody");
  const agents=t.agenti||[];
  if(agentBody) agentBody.innerHTML=agents.map(r=>`<tr><td data-label="Agente"><strong>${esc(r.nome)}</strong></td><td data-label="Giri">${r.giri}</td><td data-label="Fermate">${r.consegne}</td><td data-label="Km">${fmtNumber(r.km,2)}</td><td data-label="Costo">${fmtMoney(r.costo)}</td><td data-label="Fermate/giro">${fmtNumber(r.consegne_per_giro,2)}</td></tr>`).join("") || `<tr><td colspan="6"><div class="gf-empty"><p>Nessun dato</p></div></td></tr>`;

  const vehicleBody=document.getElementById("reportVehiclesBody");
  const vehicles=[...(t.mezzi||[])].sort((a,b)=>(Number(b.km)||0)-(Number(a.km)||0));
  const maxKm=Math.max(1,...vehicles.map(r=>Number(r.km)||0));
  if(vehicleBody) vehicleBody.innerHTML=vehicles.map(r=>{
    const fuel=reportFuelOf(r.id);
    return `<tr><td data-label="Mezzo"><strong>${esc(r.nome || "Nessun mezzo")}</strong></td><td data-label="Alimentazione"><span class="gf-badge" data-status="${fuel === "elettrico" ? "success" : "neutral"}">${esc(reportFuelLabel(fuel))}</span></td><td data-label="Km">${reportCellBar(r.km, maxKm, 2, fmtNumber(r.km,0) + " km")}</td><td data-label="Energia">${fmtMoney(r.costo)}</td></tr>`;
  }).join("") || `<tr><td colspan="4"><div class="gf-empty"><p>Nessun dato</p></div></td></tr>`;

  const customerQ=(document.getElementById("reportCustomersSearch")?.value || "").toLowerCase();
  const customerBody=document.getElementById("reportCustomersBody");
  const maxCustomer=Math.max(1,...(t.clienti||[]).map(r=>Number(r.consegne)||0));
  const customers=(t.clienti||[]).filter(r=>!customerQ || String(r.nome||"").toLowerCase().includes(customerQ)).slice(0,80);
  if(customerBody) customerBody.innerHTML=customers.map(r=>`<tr><td data-label="Cliente"><strong>${esc(r.nome||"Cliente")}</strong></td><td data-label="Fermate">${reportCellBar(r.consegne, maxCustomer, 5, fmtNumber(r.consegne))}</td><td data-label="Giri">${r.giri}</td><td data-label="Km tappe">${fmtNumber(r.km_tappe,2)} km</td></tr>`).join("") || `<tr><td colspan="4"><div class="gf-empty"><p>Nessun cliente trovato</p></div></td></tr>`;
}

function renderReportInsights(rows){
  const el=document.getElementById("reportInsights"); if(!el) return;
  el.innerHTML=(rows||[]).map(x=>`<div class="gf-alert" data-status="info"><div class="gf-alert__body"><strong class="gf-alert__title">${esc(x.titolo)}</strong><p>${esc(x.testo)}</p></div></div>`).join("") || `<div class="gf-empty"><p>Nessun insight disponibile.</p></div>`;
}

function exportReportCsv(){
  if(showLockedOrProceed("report")) return;
  window.open("/api/reports/export?" + reportParams().toString(), "_blank");
}

async function printReport(){
  if(showLockedOrProceed('report')) return;
  const popup=window.open('', '_blank');
  if(!popup){ alert('Consenti i popup per stampare il report'); return; }
  popup.document.body.textContent='Preparazione report...';
  try{
    const params=reportParams();
    const data=await api('/api/reports/summary?' + params.toString());
    const filters=Array.from(params.entries()).filter(([,v])=>v).map(([k,v])=>`${esc(k)}: ${esc(v)}`).join(' · ');
    const rows=(data.tables?.giri||[]).map(r=>`<tr><td>${esc(gfDateIt(r.data_giro))}</td><td>${esc(r.nome)}</td><td>${esc(r.driver_name)}</td><td>${r.consegne}</td><td>${fmtNumber(r.km,2)}</td><td>${fmtNumber(r.ore,2)}</td><td>${fmtMoney(r.costo)}</td></tr>`).join('');
    popup.document.open();
    popup.document.write(`<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Report GiroFacile</title><style>body{font:14px Arial;padding:24px;color:#172033}table{border-collapse:collapse;width:100%}th,td{padding:8px;text-align:left;border-bottom:1px solid #ccc}thead{display:table-header-group}tr{break-inside:avoid}small{color:#475569}@media print{button{display:none}@page{size:A4 landscape;margin:12mm}}</style></head><body><h1>Report GiroFacile</h1><p>${filters||'Tutti i giri completati'}</p><p>${data.metrics.giri_effettuati} giri · ${data.metrics.consegne_totali} fermate previste · ${fmtNumber(data.metrics.km_totali,2)} km pianificati · ${fmtMoney(data.metrics.costo_carburante)} di energia stimata</p><small>Le fermate previste comprendono consegnate, mancate e non gestite. Km, ore e costi dei giri filtrati sono ripartiti per numero di fermate. Km, consumi e costi energetici sono stime. Le ore sono rilevate quando disponibili, altrimenti stimate. Personale, pedaggi e manutenzione esclusi.</small><table><thead><tr><th>Data</th><th>Giro</th><th>Autista</th><th>Fermate previste</th><th>Km pianificati</th><th>Ore rilevate/stimate</th><th>Energia stimata</th></tr></thead><tbody>${rows||'<tr><td colspan="7">Nessun giro nel periodo</td></tr>'}</tbody></table><button id="printButton">Stampa / Salva PDF</button></body></html>`);
    popup.document.close();
    popup.document.getElementById('printButton').onclick=()=>popup.print();
    popup.focus();
    popup.print();
  }catch(error){ popup.document.body.textContent='Impossibile preparare il report: '+error.message; }
}
