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
    if(!customersCache.length) customersCache = await api("/api/customers?limit=1000");
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
    btn.classList.toggle("open", shouldOpen);
    btn.innerHTML = `<span class="filter-icon-v40">${shouldOpen ? '⌃' : '⌄'}</span> ${shouldOpen ? 'Nascondi filtri' : 'Mostra filtri'}`;
  }
}

function updateReportFilterSummary(){
  const summary = document.getElementById("reportFilterSummary");
  if(!summary) return;
  const ids = ["reportDateFrom","reportDateTo","reportAgent","reportCustomer","reportDriver","reportVehicle","reportStatus"];
  const active = ids.filter(id=>{ const el=document.getElementById(id); return el && String(el.value || "").trim(); }).length;
  summary.textContent = active ? `${active} filtro${active>1?'i':''} applicat${active>1?'i':'o'}` : "Nessun filtro applicato";
}

async function loadReport(){
  if(showLockedOrProceed("report")) return;
  await ensureReportFilters();
  updateReportFilterSummary();
  const box = document.getElementById("tab-report");
  if(!box) return;
  try{
    reportData = await api("/api/reports/summary?" + reportParams().toString());
    renderReportMetrics(reportData.metrics || {});
    renderReportCharts(reportData.charts || {});
    renderReportTables();
    renderReportInsights(reportData.insights || []);
  }catch(e){
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
  setText("repGiri", fmtNumber(m.giri_effettuati));
  setText("repConsegne", fmtNumber(m.consegne_totali));
  setText("repKm", fmtNumber(m.km_totali,2) + " km");
  setText("repOre", fmtNumber(m.ore_totali,2) + " h");
  setText("repLitri", fmtNumber(m.litri_stimati,2) + " L");
  setText("repCosto", fmtMoney(m.costo_carburante));
  setText("repCostoGiro", fmtMoney(m.costo_medio_giro));
  setText("repCostoConsegna", fmtMoney(m.costo_medio_consegna));
  setText("repKmGiro", fmtNumber(m.km_medi_giro,2) + " km");
  setText("repConsegneGiro", fmtNumber(m.consegne_medie_giro,2));
}

function chartEmpty(id, text="Nessun dato disponibile"){
  const el=document.getElementById(id); if(el) el.innerHTML = `<div class="report-chart-empty">${esc(text)}</div>`;
}

function compactDateLabel(value){
  const s = String(value || "");
  if(/^\d{4}-\d{2}-\d{2}$/.test(s)) return s.slice(8,10) + "/" + s.slice(5,7);
  return s;
}

function reportSinglePointCard(id, row, mode){
  const el=document.getElementById(id); if(!el) return;
  if(mode === "trend"){
    el.innerHTML = `<div class="report-single-chart">
      <div class="single-date">${esc(compactDateLabel(row.data))}</div>
      <div class="single-values">
        <div><span class="dot blue"></span><small>Consegne</small><strong>${fmtNumber(row.consegne || 0)}</strong></div>
        <div><span class="dot purple"></span><small>Km pianificati</small><strong>${fmtNumber(row.km || 0,2)} km</strong></div>
      </div>
      <p>Nel periodo selezionato è presente un solo giorno con dati. Il grafico andamento completo apparirà con più giornate.</p>
    </div>`;
    return;
  }
  el.innerHTML = `<div class="report-single-chart fuel">
    <div class="single-date">${esc(compactDateLabel(row.data))}</div>
    <div class="single-fuel-box">
      <small>Costo carburante stimato</small>
      <strong>${fmtMoney(row.costo || 0)}</strong>
    </div>
    <p>Con più giorni nel filtro verrà mostrato il confronto a colonne.</p>
  </div>`;
}

function svgLineChart(id, rows){
  const el=document.getElementById(id); if(!el) return;
  rows = rows || [];
  if(!rows.length){ chartEmpty(id); return; }
  if(rows.length === 1){ reportSinglePointCard(id, rows[0], "trend"); return; }

  const w=760,h=310,pL=54,pR=54,pT=38,pB=48;
  const plotW=w-pL-pR, plotH=h-pT-pB;
  const maxC=Math.max(1,...rows.map(r=>Number(r.consegne)||0));
  const maxK=Math.max(1,...rows.map(r=>Number(r.km)||0));
  const x=(i)=> pL + i*plotW/(rows.length-1);
  const yC=(v)=> pT + plotH - (Number(v)||0)/maxC*plotH;
  const yK=(v)=> pT + plotH - (Number(v)||0)/maxK*plotH;
  const pathC=rows.map((r,i)=>`${i?'L':'M'}${x(i)},${yC(r.consegne)}`).join(" ");
  const pathK=rows.map((r,i)=>`${i?'L':'M'}${x(i)},${yK(r.km)}`).join(" ");
  const areaC=`${pathC} L ${x(rows.length-1)},${pT+plotH} L ${x(0)},${pT+plotH} Z`;
  const step=Math.max(1, Math.ceil(rows.length/7));
  const labels=rows.map((r,i)=> i%step===0 || i===rows.length-1 ? `<text x="${x(i)}" y="${h-16}" text-anchor="middle">${esc(compactDateLabel(r.data))}</text>` : "").join("");
  const grid=[0,1,2,3,4].map(i=>{
    const y=pT+i*plotH/4;
    const val=Math.round(maxC-(maxC*i/4));
    return `<line x1="${pL}" x2="${w-pR}" y1="${y}" y2="${y}"/><text x="${pL-10}" y="${y+4}" text-anchor="end">${val}</text>`;
  }).join("");
  const kmAxis=[0,1,2,3,4].map(i=>{
    const y=pT+i*plotH/4;
    const val=Math.round(maxK-(maxK*i/4));
    return `<text x="${w-pR+10}" y="${y+4}" text-anchor="start">${val}</text>`;
  }).join("");
  const points=rows.map((r,i)=>`<g class="hover-point"><circle cx="${x(i)}" cy="${yC(r.consegne)}" r="5"><title>${r.data}: ${r.consegne} consegne</title></circle><circle class="km" cx="${x(i)}" cy="${yK(r.km)}" r="5"><title>${r.data}: ${fmtNumber(r.km,2)} km</title></circle></g>`).join("");
  el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" class="report-svg line improved">
    <defs>
      <linearGradient id="reportTrendFill" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-opacity=".18"></stop>
        <stop offset="100%" stop-opacity="0"></stop>
      </linearGradient>
    </defs>
    <g class="grid">${grid}${kmAxis}</g>
    <path class="area-consegne" d="${areaC}"/>
    <path class="line-consegne" d="${pathC}"/><path class="line-km" d="${pathK}"/>
    ${points}${labels}
    <g class="legend"><circle cx="58" cy="20" r="5"/><text x="70" y="24">Consegne</text><circle class="km" cx="165" cy="20" r="5"/><text x="177" y="24">Km pianificati</text></g>
    <text class="axis-title left" x="${pL}" y="18">Consegne</text>
    <text class="axis-title right" x="${w-pR}" y="18" text-anchor="end">Km</text>
  </svg>`;
}

function svgBarChart(id, rows, key="costo", suffix="€"){
  const el=document.getElementById(id); if(!el) return;
  rows=(rows||[]).slice(-10);
  if(!rows.length){ chartEmpty(id); return; }
  if(rows.length === 1){ reportSinglePointCard(id, rows[0], "fuel"); return; }

  const w=560,h=310,pL=46,pR=24,pT=34,pB=48;
  const plotW=w-pL-pR, plotH=h-pT-pB;
  const max=Math.max(1,...rows.map(r=>Number(r[key])||0));
  const slot=plotW/rows.length;
  const bw=Math.min(44, slot*.58);
  const grid=[0,1,2,3,4].map(i=>{
    const y=pT+i*plotH/4;
    const val=max-(max*i/4);
    return `<line x1="${pL}" x2="${w-pR}" y1="${y}" y2="${y}"/><text x="${pL-8}" y="${y+4}" text-anchor="end">${fmtNumber(val,0)}</text>`;
  }).join("");
  const bars=rows.map((r,i)=>{
    const val=Number(r[key])||0, bh=Math.max(2, val/max*plotH);
    const x=pL+i*slot+(slot-bw)/2, y=pT+plotH-bh;
    return `<g class="bar-item"><rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="10"><title>${r.data||r.nome}: ${fmtMoney(val)}</title></rect><text x="${x+bw/2}" y="${h-16}" text-anchor="middle">${esc(compactDateLabel(r.data||r.nome))}</text></g>`;
  }).join("");
  el.innerHTML=`<svg viewBox="0 0 ${w} ${h}" class="report-svg bar improved">
    <defs>
      <linearGradient id="fuelBarGradient" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-opacity="1"></stop>
        <stop offset="100%" stop-opacity=".72"></stop>
      </linearGradient>
    </defs>
    <g class="grid">${grid}</g>${bars}
    <g class="legend"><rect x="46" y="14" width="12" height="12" rx="3"></rect><text x="66" y="24">Costo energetico stimato (€)</text></g>
  </svg>`;
}


function svgDonutChart(id, rows){
  const el=document.getElementById(id); if(!el) return;
  rows=(rows||[]).slice(0,6);
  const total=rows.reduce((a,r)=>a+(Number(r.consegne)||0),0);
  if(!rows.length || !total){ chartEmpty(id); return; }
  const cx=130, cy=130, r=82, c=2*Math.PI*r;
  let acc=0;
  const slices=rows.map((row,i)=>{
    const val=Number(row.consegne)||0;
    const len=val/total*c;
    const dash=`${len} ${c-len}`;
    const off=-acc;
    acc+=len;
    return `<circle class="slice s${i}" cx="${cx}" cy="${cy}" r="${r}" stroke-dasharray="${dash}" stroke-dashoffset="${off}"><title>${row.nome}: ${val} consegne</title></circle>`;
  }).join("");
  const legend=rows.map((r,i)=>`<div><span class="donut-dot s${i}"></span><strong>${esc(r.nome)}</strong><small>${Math.round((r.consegne/total)*100)}%</small></div>`).join("");
  el.innerHTML=`<div class="report-donut-wrap"><svg viewBox="0 0 260 260" class="report-svg donut"><circle class="base" cx="${cx}" cy="${cy}" r="${r}"></circle>${slices}<text x="${cx}" y="${cy-5}" text-anchor="middle">${fmtNumber(total)}</text><text x="${cx}" y="${cy+18}" text-anchor="middle">consegne</text></svg><div class="report-donut-legend">${legend}</div></div>`;
}

function svgHorizontalBars(id, rows, key="consegne", suffix=""){
  const el=document.getElementById(id); if(!el) return;
  rows=(rows||[]).slice(0,7);
  if(!rows.length){ chartEmpty(id); return; }
  const max=Math.max(1,...rows.map(r=>Number(r[key])||0));
  el.innerHTML = `<div class="report-hbars">${rows.map(r=>{
    const val=Number(r[key])||0, pct=Math.max(2, val/max*100);
    return `<div class="report-hbar-row"><span>${esc(r.nome)}</span><div class="report-hbar-track"><b style="width:${pct}%"></b></div><strong>${fmtNumber(val, key==='costo'?2:0)}${suffix}</strong></div>`;
  }).join("")}</div>`;
}

function renderReportCharts(charts){
  svgLineChart("reportLineChart", charts.andamento || []);
  svgBarChart("reportCostChart", charts.andamento || [], "costo", "€");
  svgDonutChart("reportAgentDonut", charts.agenti || []);
  svgHorizontalBars("reportDriversChart", charts.autisti || [], "consegne", "");
  svgHorizontalBars("reportVehiclesChart", charts.mezzi || [], "km", " km");
  svgHorizontalBars("reportCustomersChart", charts.clienti || [], "consegne", "");
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
  const driverBody=document.getElementById("reportDriversBody");
  if(driverBody) driverBody.innerHTML=drivers.map(r=>`<tr><td><strong>${esc(r.nome)}</strong></td><td>${r.giri}</td><td>${r.consegne}</td><td>${fmtNumber(r.km,2)}</td><td>${fmtNumber(r.ore,2)}</td><td>${fmtMoney(r.costo)}</td><td>${fmtNumber(r.consegne_per_giro,2)}</td></tr>`).join("") || `<tr><td colspan="7">Nessun dato</td></tr>`;

  const agentBody=document.getElementById("reportAgentsBody");
  const agents=t.agenti||[];
  if(agentBody) agentBody.innerHTML=agents.map(r=>`<tr><td><strong>${esc(r.nome)}</strong></td><td>${r.giri}</td><td>${r.consegne}</td><td>${fmtNumber(r.km,2)}</td><td>${fmtMoney(r.costo)}</td><td>${fmtNumber(r.consegne_per_giro,2)}</td></tr>`).join("") || `<tr><td colspan="6">Nessun dato</td></tr>`;

  const customerQ=(document.getElementById("reportCustomersSearch")?.value || "").toLowerCase();
  const customerBody=document.getElementById("reportCustomersBody");
  const customers=(t.clienti||[]).filter(r=>!customerQ || String(r.nome||"").toLowerCase().includes(customerQ)).slice(0,80);
  if(customerBody) customerBody.innerHTML=customers.map(r=>`<tr><td><strong>${esc(r.nome||"Cliente")}</strong></td><td>${r.consegne}</td><td>${r.giri}</td><td>${fmtNumber(r.km_tappe,2)} km</td></tr>`).join("") || `<tr><td colspan="4">Nessun cliente trovato</td></tr>`;
}

function renderReportInsights(rows){
  const el=document.getElementById("reportInsights"); if(!el) return;
  el.innerHTML=(rows||[]).map((x,i)=>`<div class="report-insight"><span class="report-insight-icon i${i}">✦</span><div><strong>${esc(x.titolo)}</strong><p>${esc(x.testo)}</p></div></div>`).join("") || `<div class="dash-empty">Nessun insight disponibile.</div>`;
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
    const data=await api('/api/reports/summary?' + reportParams().toString());
    const filters=Array.from(reportParams().entries()).filter(([,v])=>v).map(([k,v])=>`${esc(k)}: ${esc(v)}`).join(' · ');
    const rows=(data.tables?.giri||[]).map(r=>`<tr><td>${esc(r.data_giro)}</td><td>${esc(r.nome)}</td><td>${esc(r.driver_name)}</td><td>${r.consegne}</td><td>${fmtNumber(r.km,2)}</td><td>${fmtNumber(r.ore,2)}</td><td>${fmtMoney(r.costo)}</td></tr>`).join('');
    popup.document.open();
    popup.document.write(`<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Report GiroFacile</title><style>body{font:14px Arial;padding:24px;color:#172033}table{border-collapse:collapse;width:100%}th,td{padding:8px;text-align:left;border-bottom:1px solid #ccc}thead{display:table-header-group}tr{break-inside:avoid}small{color:#475569}@media print{button{display:none}@page{size:A4 landscape;margin:12mm}}</style></head><body><h1>Report GiroFacile</h1><p>${filters||'Tutti i giri completati'}</p><p>${data.metrics.giri_effettuati} giri · ${data.metrics.consegne_totali} consegne · ${fmtNumber(data.metrics.km_totali,2)} km pianificati · ${fmtMoney(data.metrics.costo_carburante)} di energia stimata</p><small>Km, consumi e costi energetici sono stime. Le ore sono rilevate quando disponibili, altrimenti stimate. Personale, pedaggi e manutenzione esclusi.</small><table><thead><tr><th>Data</th><th>Giro</th><th>Autista</th><th>Consegne</th><th>Km pianificati</th><th>Ore rilevate/stimate</th><th>Energia stimata</th></tr></thead><tbody>${rows||'<tr><td colspan="7">Nessun giro nel periodo</td></tr>'}</tbody></table><button id="printButton">Stampa / Salva PDF</button></body></html>`);
    popup.document.close();
    popup.document.getElementById('printButton').onclick=()=>popup.print();
    popup.focus();
    popup.print();
  }catch(error){ popup.document.body.textContent='Impossibile preparare il report: '+error.message; }
}
