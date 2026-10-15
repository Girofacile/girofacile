/* Completed routes: presentation and local table controls, no data mutations. */
window.GFCompleted = (() => {
  let route, rows = [], page = 1, size = 10;
  const card = (label, value, detail='') => `<div class="gf-stat-strip__cell"><span class="gf-stat-strip__label">${esc(label)}</span><strong class="gf-stat-strip__value">${esc(value)}</strong>${detail ? `<small class="gf-stat-strip__unit">${esc(detail)}</small>` : ''}</div>`;
  const item = (label, value, detail='') => `<div class="gf-details__item"><dt>${esc(label)}</dt><dd><strong>${esc(value)}</strong>${detail ? `<br><small class="gf-muted">${esc(detail)}</small>` : ''}</dd></div>`;
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
    document.querySelectorAll('#completedTable tbody tr[data-delivery-status]').forEach((tr,i)=>{tr.hidden=!visible.has(i);});
    document.querySelectorAll('#completedTable .driver-break-row').forEach(tr=>{const after=Number(tr.dataset.breakAfter);tr.hidden=!visible.has(after<rows.length?after:after-1);});
    document.getElementById('completedNoMatches').hidden=matches.length>0;
    document.getElementById('completedCount').textContent=matches.length ? `${(page-1)*size+1}–${Math.min(page*size,matches.length)} di ${matches.length} fermate${matches.length!==rows.length ? ` (${rows.length} totali)` : ''}` : 'Nessuna fermata trovata';
    const numbers=[...new Set([1,page-1,page,page+1,pages])].filter(n=>n>=1&&n<=pages).sort((a,b)=>a-b);
    const pageButton=(n,label,text,extra='')=>`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" aria-label="${label}" ${extra} onclick="GFCompleted.go(${n})">${text}</button>`;
    document.getElementById('completedPages').innerHTML=pageButton(page-1,'Pagina precedente','‹',page===1?'disabled':'')+numbers.map((n,i)=>`${i&&n>numbers[i-1]+1?'<span>…</span>':''}${pageButton(n,'Pagina '+n,n,n===page?'aria-current="page"':'')}`).join('')+pageButton(page+1,'Pagina successiva','›',page===pages?'disabled':'');
  }
  function render(routes, selected){
    const el=document.getElementById('dashboardCompletedPage');
    if(!routes.length){el.innerHTML='<div class="gf-empty"><h2>Nessun giro completato</h2><p>I giri conclusi appariranno qui.</p></div>';return;}
    route=selected || routes[0]; rows=route.consegne || [];page=1;
    dashboardCompletedSelectedId=route.id;
    const done=rows.filter(d=>status(d)==='completata').length, missed=rows.filter(d=>status(d)==='mancata').length;
    const vehicle=String(route.vehicle_name || 'Non assegnato').split(' · ');
    const cost=route.costo_totale ?? route.costo_carburante;
    const money=cost==null?'—':Number(cost).toLocaleString('it-IT',{style:'currency',currency:'EUR'});
    const energyMetric=window.gfRouteEnergyMetric ? window.gfRouteEnergyMetric(route) : {label:'Litri stimati',value:String(route.litri_stimati ?? '—')+' L'};
    const date=value=>value ? String(value).split('-').reverse().join('/') : '—';
    const dates=[...new Set(routes.map(r=>r.data_giro).filter(Boolean))].sort().reverse();
    el.innerHTML=`<div class="gf-cluster">${dashboardRoutePicker(routes,route.id,'openDashboardCompletedPage','Seleziona giro completato')}<label class="gf-field" for="completedDate"><span class="gf-field__label">Data</span><select class="gf-select" id="completedDate" aria-label="Data del giro">${dates.map(d=>`<option value="${esc(d)}" ${d===route.data_giro?'selected':''}>${esc(date(d))}</option>`).join('')}</select></label><button type="button" class="gf-button" data-variant="ghost" onclick="showTab('storico')">Tutti i giri completati ›</button></div>
    <section class="gf-panel" aria-label="Dati del giro"><div class="gf-panel__body"><dl class="gf-details">${item('Nome giro',route.nome || 'Giro consegne',`ID #${route.id}`)}${item('Data',date(route.data_giro),'Giro completato')}${item('Autista',route.driver_name || 'Non assegnato')}${item('Mezzo',vehicle[0],vehicle.slice(1).join(' · '))}${item('Stato','Completato','Giro concluso')}${item('Rientro finale stimato',route.rientro_stimato_aggiornato || route.orario_rientro_stimato || '—','Orario previsto')}</dl></div></section>
    <div class="gf-stat-strip" aria-label="Indicatori del giro">${card('Km previsti',`${route.totale_km ?? '—'} km`)}${card('Tempo previsto',`${Math.round(route.totale_minuti || 0)} min`)}${card(energyMetric.label,energyMetric.value)}${card('Costo stimato',money)}${card('Consegne',`${done} / ${rows.length}`,`${missed} mancate`)}</div>
    <div class="gf-grid" data-cols="main-side"><section class="gf-panel" aria-label="Fermate completate"><header class="gf-panel__header"><div><h2 class="gf-panel__title">Fermate completate</h2><p class="gf-muted">Orari, stato e dettagli di consegna.</p></div><div class="gf-cluster"><input class="gf-input" id="completedSearch" type="search" placeholder="Cerca cliente o indirizzo…" aria-label="Cerca cliente o indirizzo"><button type="button" class="gf-button" data-variant="secondary" id="completedExport">Esporta</button><select class="gf-select" id="completedStatus" aria-label="Filtra per esito"><option value="">Tutti gli esiti</option><option value="completata">Consegnate</option><option value="mancata">Mancate</option><option value="in_attesa">Non gestite</option></select></div></header><div id="completedTable">${dashboardStopRowsUnified(route,'completed')}</div><p id="completedNoMatches" class="gf-empty" hidden>Nessuna fermata corrisponde ai filtri.</p><footer class="gf-panel__footer gf-cluster" data-justify="between"><span id="completedCount" class="gf-muted"></span><div id="completedPages" class="gf-cluster" aria-label="Pagine"></div><label class="gf-cluster"><span class="gf-muted">Righe</span><select class="gf-select" id="completedSize">${[10,25,50].map(n=>`<option ${n===size?'selected':''}>${n}</option>`).join('')}</select></label></footer></section>
    <aside class="gf-panel" aria-labelledby="completedSummaryTitle"><header class="gf-panel__header"><h2 class="gf-panel__title" id="completedSummaryTitle">Riepilogo esito</h2></header><div class="gf-panel__body"><dl class="gf-details">${[['Totale fermate',rows.length,'neutral'],['Consegne completate',done,'success'],['Consegne mancate',missed,'danger'],['Clienti assenti',rows.filter(d=>status(d)==='mancata'&&d.motivo_mancata==='assente').length,'warning'],['Locali chiusi',rows.filter(d=>status(d)==='mancata'&&d.motivo_mancata==='chiuso').length,'warning'],...(rows.length-done-missed?[['Non gestite',rows.length-done-missed,'info']]:[])].map(([label,n,tone])=>`<div class="gf-details__item"><dt>${label}</dt><dd><span class="gf-badge" data-status="${tone}">${n}</span></dd></div>`).join('')}<div class="gf-details__item"><dt>Costo totale stimato</dt><dd><strong>${esc(money)}</strong></dd></div></dl></div></aside></div>`;
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
