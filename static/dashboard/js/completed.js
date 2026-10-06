/* Completed routes: presentation and local table controls, no data mutations. */
window.GFCompleted = (() => {
  let route, rows = [], page = 1, size = 10;
  const paths = {
    route:'M5 5h7a4 4 0 0 1 0 8H8a4 4 0 0 0 0 8h11M5 2v6m14 10v4',
    date:'M4 5h16v16H4zM8 2v6m8-6v6M4 11h16',
    user:'M8 7a4 4 0 1 0 8 0 4 4 0 0 0-8 0M4 22v-3a8 6 0 0 1 16 0v3',
    truck:'M3 5h12v13H3zM15 10h4l3 5v3h-7M5 18v3m13-3v3',
    check:'m4 12 5 5L20 5', clock:'M12 6v6l4 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
    road:'M7 3 3 21M17 3l4 18M12 3v4m0 3v4m0 3v4',
    fuel:'M4 21V4h10v17M4 9h10m0 4h3v5a2 2 0 0 0 4 0v-8l-3-3M2 21h14',
    cost:'M18 6a7 7 0 1 0 0 12M3 10h12M3 14h10', chart:'M5 21V11m7 10V3m7 18V8'
  };
  const icon = (name, color='blue') => `<span class="completed-icon ${color}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[name]}"/></svg></span>`;
  const card = (label, value, symbol, color='blue', detail='') => `<div class="completed-card">${icon(symbol,color)}<div><span>${esc(label)}</span><strong>${esc(value)}</strong>${detail ? `<small>${esc(detail)}</small>` : ''}</div></div>`;
  const status = d => d.delivery_status || d.status || 'in_attesa';
  function filtered(){
    const query = document.getElementById('completedSearch').value.trim().toLocaleLowerCase('it');
    const state = document.getElementById('completedStatus').value;
    return rows.map((d,i)=>({d,i})).filter(({d}) => (!state || status(d)===state) && `${d.cliente_nome || ''} ${d.indirizzo || ''}`.toLocaleLowerCase('it').includes(query));
  }
  function update(reset=false){
    if(reset) page=1;
    const matches=filtered(), pages=Math.max(1,Math.ceil(matches.length/size));
    page=Math.min(page,pages);
    const visible=new Set(matches.slice((page-1)*size,page*size).map(x=>x.i));
    document.querySelectorAll('#completedTable tbody tr').forEach((tr,i)=>{tr.hidden=!visible.has(i);});
    document.getElementById('completedNoMatches').hidden=matches.length>0;
    document.getElementById('completedCount').textContent=matches.length ? `${(page-1)*size+1}–${Math.min(page*size,matches.length)} di ${matches.length} fermate${matches.length!==rows.length ? ` (${rows.length} totali)` : ''}` : 'Nessuna fermata trovata';
    const numbers=[...new Set([1,page-1,page,page+1,pages])].filter(n=>n>=1&&n<=pages).sort((a,b)=>a-b);
    document.getElementById('completedPages').innerHTML=`<button type="button" aria-label="Pagina precedente" ${page===1?'disabled':''} onclick="GFCompleted.go(${page-1})">‹</button>`+numbers.map((n,i)=>`${i&&n>numbers[i-1]+1?'<span>…</span>':''}<button type="button" aria-label="Pagina ${n}" ${n===page?'aria-current="page"':''} onclick="GFCompleted.go(${n})">${n}</button>`).join('')+`<button type="button" aria-label="Pagina successiva" ${page===pages?'disabled':''} onclick="GFCompleted.go(${page+1})">›</button>`;
  }
  function render(routes, selected){
    const el=document.getElementById('dashboardCompletedPage');
    if(!routes.length){el.innerHTML='<div class="dash-detail-empty"><h2>Nessun giro completato</h2><p>I giri conclusi appariranno qui.</p></div>';return;}
    route=selected || routes[0]; rows=route.consegne || [];page=1;
    dashboardCompletedSelectedId=route.id;
    const done=rows.filter(d=>status(d)==='completata').length, missed=rows.filter(d=>status(d)==='mancata').length;
    const vehicle=String(route.vehicle_name || 'Non assegnato').split(' · ');
    const cost=route.costo_totale ?? route.costo_carburante;
    const money=cost==null?'—':Number(cost).toLocaleString('it-IT',{style:'currency',currency:'EUR'});
    const energyMetric=window.gfRouteEnergyMetric ? window.gfRouteEnergyMetric(route) : {label:'Litri stimati',value:String(route.litri_stimati ?? '—')+' L'};
    const date=value=>value ? String(value).split('-').reverse().join('/') : '—';
    const dates=[...new Set(routes.map(r=>r.data_giro).filter(Boolean))].sort().reverse();
    el.innerHTML=`<div class="completed-picker">${icon('route')}${dashboardRoutePicker(routes,route.id,'openDashboardCompletedPage','Seleziona giro completato')}<label class="completed-date">Data<select id="completedDate" aria-label="Data del giro">${dates.map(d=>`<option value="${esc(d)}" ${d===route.data_giro?'selected':''}>${esc(date(d))}</option>`).join('')}</select></label><button type="button" class="btn-light" onclick="showTab('storico')">Tutti i giri completati ›</button></div>
    <div class="completed-identity">${card('Nome giro',route.nome || 'Giro consegne','route','purple',`ID #${route.id}`)}${card('Data',date(route.data_giro),'date','blue','Giro completato')}${card('Autista',route.driver_name || 'Non assegnato','user')}${card('Mezzo',vehicle[0],'truck','blue',vehicle.slice(1).join(' · '))}${card('Stato','Completato','check','green','Giro concluso')}${card('Rientro finale stimato',route.rientro_stimato_aggiornato || route.orario_rientro_stimato || '—','clock','purple','Orario previsto')}</div>
    <div class="completed-metrics">${card('Km previsti',`${route.totale_km ?? '—'} km`,'road')}${card('Tempo previsto',`${Math.round(route.totale_minuti || 0)} min`,'clock','purple')}${card(energyMetric.label,energyMetric.value,'fuel','green')}${card('Costo stimato',money,'cost','orange')}${card('Consegne',`${done} / ${rows.length}`,'clock','red',`${missed} mancate`)}</div>
    <div class="completed-content"><section class="completed-stops" aria-label="Fermate completate"><div class="completed-heading">${icon('route')}<div><h2>Fermate completate</h2><p>Orari, stato e dettagli di consegna.</p></div><div class="completed-tools"><input id="completedSearch" type="search" placeholder="Cerca cliente o indirizzo…" aria-label="Cerca cliente o indirizzo"><button type="button" class="btn-light" id="completedExport">Esporta</button><select id="completedStatus" aria-label="Filtra per esito"><option value="">Tutti gli esiti</option><option value="completata">Consegnate</option><option value="mancata">Mancate</option><option value="in_attesa">Non gestite</option></select></div></div><div id="completedTable">${dashboardStopRowsUnified(route,'completed')}</div><p id="completedNoMatches" hidden>Nessuna fermata corrisponde ai filtri.</p><div class="completed-pagination"><span id="completedCount" role="status" aria-live="polite"></span><label>Righe per pagina <select id="completedSize">${[10,25,50].map(n=>`<option ${n===size?'selected':''}>${n}</option>`).join('')}</select></label><nav id="completedPages" aria-label="Pagine delle fermate"></nav></div></section>
    <aside class="completed-summary"><div class="completed-heading">${icon('chart')}<h2>Riepilogo esito</h2></div>${[['Totale fermate',rows.length,'blue'],['Consegne completate',done,'green'],['Consegne mancate',missed,'red'],['Clienti assenti',rows.filter(d=>status(d)==='mancata'&&d.motivo_mancata==='assente').length,'orange'],['Locali chiusi',rows.filter(d=>status(d)==='mancata'&&d.motivo_mancata==='chiuso').length,'purple'],...(rows.length-done-missed?[['Non gestite',rows.length-done-missed,'blue']]:[])].map(([label,n,color])=>`<div class="completed-outcome"><i class="${color}" aria-hidden="true"></i><span>${label}</span><strong>${n}</strong></div>`).join('')}<div class="completed-cost">${icon('cost')}<div><span>Costo totale stimato</span><strong>${esc(money)}</strong></div></div></aside></div>`;
    document.getElementById('completedSearch').oninput=()=>update(true);
    document.getElementById('completedStatus').onchange=()=>update(true);
    document.getElementById('completedSize').onchange=e=>{size=Number(e.target.value);update(true);};
    document.getElementById('completedDate').onchange=e=>openDashboardCompletedPage(routes.find(r=>r.data_giro===e.target.value).id);
    document.getElementById('completedExport').onclick=exportRows;
    update();
  }
  function exportRows(){
    const cell=value=>'"'+String(value ?? '').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';
    const data=[['Ordine','Cliente','Indirizzo','Arrivo previsto','Arrivo reale','Stato','Motivo','Note'],...filtered().map(({d})=>[d.ordine,d.cliente_nome,d.indirizzo,gfPlannedArrival(d),gfRealArrival(d),status(d),d.motivo_mancata,d.note_operatore || d.note_autista || d.note])];
    const url=URL.createObjectURL(new Blob(['\uFEFF'+data.map(row=>row.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`giro-${route.id}-fermate.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return {render,go(n){page=Math.max(1,n);update();}};
})();
