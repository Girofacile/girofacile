/* Storico giri: settimana a 7 card, giri del giorno in tabella, ricerca e filtri, dettaglio nel pannello laterale.
   Unisce il vecchio Storico e la pagina Giri completati; legge le stesse API (/api/routes, /api/routes/{id}). */
window.GFHistory = (() => {
  const PERIODS = {'':'Qualsiasi data','7':'Ultimi 7 giorni','30':'Ultimi 30 giorni','month':'Questo mese','last-month':'Mese scorso','90':'Ultimi 3 mesi','custom':'Date a scelta'};
  const STATES = {'':'Tutti gli stati','completato':'Completati','annullato':'Annullati'};
  const state = {routes:[], day:null, query:'', period:'', from:'', to:'', driver:'', vehicle:'', status:''};
  let route = null, request = 0;
  const $ = id => document.getElementById(id);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const shortDate = iso => iso ? String(iso).split('-').reverse().join('/') : '—';
  const money = value => value === null || value === undefined || value === '' ? '—' : '€ '+Number(value).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
  const status = d => d.delivery_status || d.status || 'in_attesa';
  const statusBadge = r => r.status === 'annullato' ? '<span class="gf-badge" data-status="danger">Annullato</span>' : '<span class="gf-badge" data-status="success">Completato</span>';
  const vehicleCell = name => { const parts = String(name || '-').split(' · '); return `<span class="gf-list-item__main"><strong>${esc(parts[0])}</strong>${parts.length > 1 ? `<small>${esc(parts.slice(1).join(' · '))}</small>` : ''}</span>`; };

  /* --- Ricerca e filtri -------------------------------------------------------- */
  function periodRange(){
    const today = todayIso(), p = state.period;
    if(['7','30','90'].includes(p)) return [dashScheduledAddDays(today, -Number(p)), today];
    if(p === 'month') return [today.slice(0,8)+'01', today];
    if(p === 'last-month'){ const end = dashScheduledAddDays(today.slice(0,8)+'01', -1); return [end.slice(0,8)+'01', end]; }
    if(p === 'custom') return [state.from || '0000-00-00', state.to || '9999-12-31'];
    return null;
  }
  function activeFilters(){
    const list = [];
    if(state.period) list.push(['period', state.period === 'custom' ? `Dal ${state.from ? shortDate(state.from) : '…'} al ${state.to ? shortDate(state.to) : '…'}` : PERIODS[state.period]]);
    if(state.driver) list.push(['driver', 'Autista: '+state.driver]);
    if(state.vehicle) list.push(['vehicle', 'Mezzo: '+state.vehicle]);
    if(state.status) list.push(['status', STATES[state.status]]);
    return list;
  }
  const searching = () => !!(state.query.trim() || activeFilters().length);
  function matches(r){
    const q = state.query.trim().toLocaleLowerCase('it');
    const text = `${r.nome || ''} ${r.vehicle_name || ''}`.toLocaleLowerCase('it');
    if(q && !text.includes(q) && !text.replace(/\s/g,'').includes(q.replace(/\s/g,''))) return false;
    const range = periodRange();
    if(range && (!r.data_giro || r.data_giro < range[0] || r.data_giro > range[1])) return false;
    if(state.driver && (r.driver_name || '') !== state.driver) return false;
    if(state.vehicle && (r.vehicle_name || '') !== state.vehicle) return false;
    if(state.status && r.status !== state.status) return false;
    return true;
  }
  const routesOf = iso => state.routes.filter(r => r.data_giro === iso).sort((a,b) => String(a.orario_partenza || '').localeCompare(String(b.orario_partenza || '')));
  function visibleRoutes(){
    return searching() ? state.routes.filter(matches).sort((a,b) => `${b.data_giro}${b.orario_partenza}`.localeCompare(`${a.data_giro}${a.orario_partenza}`)) : routesOf(state.day);
  }

  function select(id, label, options, value){
    return `<label class="gf-field" for="${id}"><span class="gf-field__label">${esc(label)}</span><select class="gf-select" id="${id}">${options.map(([v,t]) => `<option value="${esc(v)}" ${v === value ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
  }
  function openFilters(){
    const unique = key => [...new Set(state.routes.map(r => r[key]).filter(Boolean))].sort((a,b) => a.localeCompare(b,'it'));
    $('historyFilterFields').innerHTML =
      select('historyPeriod','Periodo',Object.entries(PERIODS),state.period) +
      `<label class="gf-field" for="historyFrom"><span class="gf-field__label">Dal</span><input class="gf-input" id="historyFrom" type="date" value="${esc(state.from)}"></label>` +
      `<label class="gf-field" for="historyTo"><span class="gf-field__label">Al</span><input class="gf-input" id="historyTo" type="date" value="${esc(state.to)}"></label>` +
      select('historyDriver','Autista',[['','Tutti gli autisti'],...unique('driver_name').map(d => [d,d])],state.driver) +
      select('historyVehicle','Mezzo',[['','Tutti i mezzi'],...unique('vehicle_name').map(v => [v,v])],state.vehicle) +
      select('historyStatus','Stato',Object.entries(STATES),state.status);
    const syncDates = () => ['historyFrom','historyTo'].forEach(id => { $(id).closest('.gf-field').hidden = $('historyPeriod').value !== 'custom'; });
    $('historyPeriod').onchange = syncDates; syncDates();
    $('historyFilterDialog').showModal();
  }
  function applyFilters(){
    Object.assign(state, {period:$('historyPeriod').value, from:$('historyFrom').value, to:$('historyTo').value, driver:$('historyDriver').value, vehicle:$('historyVehicle').value, status:$('historyStatus').value});
    $('historyFilterDialog').close();
    render();
  }
  function clearFilters(){
    Object.assign(state, {query:'', period:'', from:'', to:'', driver:'', vehicle:'', status:''});
    $('historySearch').value = '';
    $('historyFilterDialog')?.close();
    render();
  }
  function removeFilter(key){
    if(key === 'query'){ state.query = ''; $('historySearch').value = ''; }
    else if(key === 'period') Object.assign(state, {period:'', from:'', to:''});
    else state[key] = '';
    render();
  }

  /* --- Settimana e tabelle ------------------------------------------------------- */
  function weekHtml(){
    const monday = dashScheduledMonday(state.day);
    const days = Array.from({length:7}, (_, i) => dashScheduledAddDays(monday, i));
    const first = dashScheduledDate(days[0]), last = dashScheduledDate(days[6]);
    $('historyWeekTitle').textContent = 'Settimana ' + (first.getMonth() === last.getMonth()
      ? `${first.getDate()} – ${last.getDate()} ${DASH_SCHEDULED_MONTHS[last.getMonth()]} ${last.getFullYear()}`
      : `${first.getDate()} ${DASH_SCHEDULED_MONTHS[first.getMonth()]} – ${last.getDate()} ${DASH_SCHEDULED_MONTHS[last.getMonth()]} ${last.getFullYear()}`);
    return `<div class="gf-grid" data-cols="7">${days.map(iso => {
      const d = dashScheduledDate(iso), list = routesOf(iso);
      const items = list.length
        ? list.map(r => `<li><button type="button" class="gf-list-item" onclick="GFHistory.open(${Number(r.id)})"><span class="gf-list-item__main"><strong>${esc(r.orario_partenza || '-')}</strong><small>${esc(r.nome || 'Giro consegne')}</small></span></button></li>`).join('')
        : `<li class="gf-list-item"><span class="gf-muted">${iso > todayIso() ? 'Giorno futuro' : 'Nessun giro'}</span></li>`;
      return `<section class="gf-panel" aria-label="${esc(dashScheduledDayLabel(iso))}">
        <header class="gf-panel__header"><button type="button" class="gf-chip" aria-pressed="${iso === state.day}" onclick="GFHistory.day('${iso}')">${DASH_SCHEDULED_DAY_NAMES[d.getDay()]}&nbsp;${d.getDate()} <span class="gf-chip__count">${list.length}</span></button></header>
        <ul class="gf-list">${items}</ul>
      </section>`;
    }).join('')}</div>`;
  }
  function routesTable(list, withDate){
    return `<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards">
      <thead><tr>${withDate ? '<th scope="col">Data</th>' : ''}<th scope="col">Orario</th><th scope="col">Giro</th><th scope="col">Fermate</th><th scope="col">Stato</th><th scope="col">Autista</th><th scope="col">Mezzo</th><th scope="col">Km</th><th scope="col">Costo</th><th scope="col">Azioni</th></tr></thead>
      <tbody>${list.map(r => `<tr>
        ${withDate ? `<td data-label="Data"><strong>${esc(shortDate(r.data_giro))}</strong></td>` : ''}
        <td data-label="Orario"><span class="gf-badge" data-status="success" data-dot>${esc(r.orario_partenza || '-')} – ${esc(r.orario_rientro_stimato || '-')}</span></td>
        <td data-label="Giro"><strong>${esc(r.nome || 'Giro consegne')}</strong></td>
        <td data-label="Fermate">${plural(Number(r.consegne_count || 0),'fermata','fermate')}</td>
        <td data-label="Stato">${statusBadge(r)}</td>
        <td data-label="Autista">${esc(r.driver_name || 'Non assegnato')}</td>
        <td data-label="Mezzo">${vehicleCell(r.vehicle_name)}</td>
        <td data-label="Km">${esc(r.totale_km ?? '-')} km</td>
        <td data-label="Costo">${money(r.costo_totale ?? r.costo_carburante)}</td>
        <td data-label="Azioni"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="GFHistory.open(${Number(r.id)})">Apri giro</button></td>
      </tr>`).join('')}</tbody>
    </table></div>`;
  }
  function chipsHtml(){
    const list = activeFilters();
    if(state.query.trim()) list.unshift(['query', `Cerca: “${state.query.trim()}”`]);
    $('historyActiveFilters').hidden = !list.length;
    $('historyActiveFilters').innerHTML = list.map(([key, text]) => `<button type="button" class="gf-chip" aria-pressed="true" aria-label="Rimuovi filtro ${esc(text)}" onclick="GFHistory.remove('${key}')">${esc(text)} ×</button>`).join('') +
      (list.length ? '<button type="button" class="gf-button" data-variant="link" onclick="GFHistory.clear()">Azzera tutto</button>' : '');
    const count = activeFilters().length;
    $('historyFilterCount').hidden = !count;
    $('historyFilterCount').textContent = count;
  }

  function render(){
    const empty = !state.routes.length;
    $('historyEmptyState').classList.toggle('hidden', !empty);
    $('historyPage').hidden = empty;
    if(empty) return;
    chipsHtml();
    const results = searching();
    $('historyWeekSection').hidden = results;
    $('historyDaySection').hidden = results;
    $('historyResultsSection').hidden = !results;
    if(results){
      const list = visibleRoutes();
      $('historyResultsMeta').textContent = list.length ? `${plural(list.length,'giro','giri')} · ${plural(list.reduce((s,r) => s + Number(r.consegne_count || 0), 0),'fermata','fermate')}` : '';
      $('historyResultsList').innerHTML = list.length ? routesTable(list, true) : '<div class="gf-empty"><h3 class="gf-subtitle">Nessun giro trovato</h3><p>Prova con un altro nome, una targa o un periodo diverso.</p><button type="button" class="gf-button" data-variant="secondary" onclick="GFHistory.clear()">Azzera ricerca e filtri</button></div>';
      return;
    }
    $('historyWeek').innerHTML = weekHtml();
    const list = routesOf(state.day);
    $('historyDayTitle').textContent = dashScheduledDayLabel(state.day);
    $('historyDayMeta').textContent = list.length ? `${plural(list.length,'giro','giri')} · ${plural(list.reduce((s,r) => s + Number(r.consegne_count || 0), 0),'fermata','fermate')}` : '';
    $('historyDayList').innerHTML = list.length ? routesTable(list, false) : '<div class="gf-empty"><h3 class="gf-subtitle">Nessun giro</h3><p>In questa giornata non ci sono giri conclusi.</p></div>';
  }

  /* --- Pannello del giro -------------------------------------------------------- */
  function stopsHtml(r){
    const rows = r.consegne || [];
    if(!rows.length) return '<div class="gf-empty"><p>Nessuna fermata collegata a questo giro.</p></div>';
    const planned = gfPlannedArrivalDates(r, rows);
    const breaks = after => (r.driver_breaks || []).filter(b => b.after_order === after).map(b => `<li class="gf-stop"><span class="gf-stop__number" aria-label="Pausa">Ⅱ</span><span class="gf-stop__main"><span class="gf-stop__name">Pausa autista dalle ${esc(b.start)} alle ${esc(b.end)}</span><span class="gf-stop__meta">Riposo pianificato · ${Number(b.duration_min)} minuti</span></span></li>`).join('');
    return `<ol class="gf-stop-list" data-height="auto" aria-label="Fermate del giro">${breaks(0)}${rows.map((d, idx) => {
      const st = status(d), note = d.note_operatore || d.note_autista || d.note || '', real = gfRealArrival(d);
      return `<li class="gf-stop${st === 'completata' ? ' is-done' : st === 'mancata' ? ' is-miss' : ''}"><span class="gf-stop__number">${esc(d.ordine || idx+1)}</span>
        <span class="gf-stop__main"><span class="gf-stop__name">${esc(d.cliente_nome || '-')}</span>
          <span class="gf-stop__meta">${esc(d.indirizzo || '-')} · previsto ${esc(gfPlannedArrival(d))}${real ? ` · reale ${esc(real)}` : ''} ${gfDeltaBadge(planned[idx], gfRealArrivalDate(d))}</span>
          <span class="gf-stop__meta">${deliveryStatusPill(st)}${d.motivo_mancata ? ` <small>${esc(d.motivo_mancata)}</small>` : ''} ${deliverySignatureAction(d, r.driver_name)} ${trackingButton(d, r)}${note ? ` <button type="button" class="gf-button" data-variant="ghost" data-size="sm" data-note="${esc(String(note))}" onclick="alert(this.dataset.note)">Note</button>` : ''}</span>
        </span><span class="gf-stop__time">${esc(real || gfPlannedArrival(d))}</span></li>${breaks(idx+1)}`;
    }).join('')}</ol>`;
  }
  function dialogHtml(r){
    const rows = r.consegne || [];
    const done = rows.filter(d => status(d) === 'completata').length, missed = rows.filter(d => status(d) === 'mancata').length;
    const absent = rows.filter(d => status(d) === 'mancata' && d.motivo_mancata === 'assente').length;
    const closed = rows.filter(d => status(d) === 'mancata' && d.motivo_mancata === 'chiuso').length;
    const energy = gfRouteEnergyMetric(r);
    const item = (label, value) => `<div class="gf-details__item"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`;
    const outcome = [[`${done} consegnate`,'success'], [plural(missed,'mancata','mancate'),'danger', missed], [plural(absent,'cliente assente','clienti assenti'),'warning', absent], [plural(closed,'locale chiuso','locali chiusi'),'warning', closed], [`${rows.length-done-missed} non gestite`,'info', rows.length-done-missed]]
      .filter(([, , show]) => show === undefined || show > 0).map(([text, tone]) => `<span class="gf-badge" data-status="${tone}">${esc(text)}</span>`).join('');
    return `<header class="gf-modal__header">
        <div><p class="gf-kicker">${r.status === 'annullato' ? 'Giro annullato' : 'Giro completato'} · ${esc(r.data_giro ? dashScheduledDayLabel(r.data_giro).toLowerCase() : '-')}</p><h2 class="gf-modal__title" id="historyRouteTitle">${esc(r.nome || 'Giro consegne')}</h2></div>
        ${statusBadge(r)}
        <button type="button" class="gf-icon-button" aria-label="Chiudi" onclick="GFHistory.close()"><svg class="gf-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12 M18 6L6 18"/></svg></button>
      </header>
      <div class="gf-modal__body gf-stack">
        <div class="gf-crew"><div><small>Autista</small><strong>${esc(r.driver_name || 'Non assegnato')}</strong></div><div><small>Mezzo</small><strong>${esc(r.vehicle_name || '-')}</strong></div></div>
        <dl class="gf-details">
          ${item('Partenza', gfTimeFromIso(r.started_at) || r.orario_partenza || '-')}${item('Rientro', gfTimeFromIso(r.completed_at) || r.rientro_stimato_aggiornato || r.orario_rientro_stimato || '-')}
          ${item('Km previsti', `${r.totale_km ?? '-'} km`)}${item('Tempo previsto', dashScheduledMinutes(r.totale_minuti))}
          ${item(energy.label, energy.value)}${item('Costo stimato', money(r.costo_totale ?? r.costo_carburante))}
        </dl>
        <h3 class="gf-subtitle">Esito</h3>
        <div class="gf-cluster">${outcome}</div>
        <h3 class="gf-subtitle">${plural(rows.length,'fermata','fermate')}</h3>
        ${stopsHtml(r)}
      </div>
      <footer class="gf-modal__footer">
        ${r.google_maps_url ? `<a class="gf-button" data-variant="secondary" target="_blank" rel="noopener" href="${esc(r.google_maps_url)}">Apri Maps</a>` : ''}
        <button type="button" class="gf-button" data-variant="secondary" onclick="GFHistory.exportStops()">Esporta fermate (CSV)</button>
      </footer>`;
  }
  async function open(id){
    try{
      route = await api(`/api/routes/${id}`);
      if(route.data_giro && !searching()){ state.day = route.data_giro; render(); }
      const dialog = $('historyRouteDialog');
      dialog.innerHTML = dialogHtml(route);
      if(typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
    }catch(e){ toast(e.message); }
  }

  /* --- Esportazioni CSV ------------------------------------------------------------ */
  const cell = value => '"'+String(value ?? '').replace(/^[=+@-]/,"'$&").replace(/"/g,'""')+'"';
  function download(name, data){
    const url = URL.createObjectURL(new Blob(['﻿'+data.map(row => row.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportRoutes(){
    download('storico-giri.csv', [['Data','Giro','Partenza','Rientro','Autista','Mezzo','Km','Costo','Stato','Fermate'],
      ...visibleRoutes().map(r => [r.data_giro, r.nome, r.orario_partenza, r.orario_rientro_stimato, r.driver_name, r.vehicle_name, r.totale_km, r.costo_totale ?? r.costo_carburante, r.status_label || r.status, r.consegne_count])]);
  }
  function exportStops(){
    if(!route) return;
    download(`giro-${route.id}-fermate.csv`, [['Ordine','Cliente','Indirizzo','Arrivo previsto','Arrivo reale','Stato','Motivo','Note'],
      ...(route.consegne || []).map(d => [d.ordine, d.cliente_nome, d.indirizzo, gfPlannedArrival(d), gfRealArrival(d), status(d), d.motivo_mancata, d.note_operatore || d.note_autista || d.note])]);
  }

  /* --- Caricamento ------------------------------------------------------------------ */
  // Ogni caricamento annulla quelli precedenti ancora in corso: vince l'ultima richiesta.
  async function load(routeId=null){
    const ticket = ++request;
    const rows = await api('/api/routes');
    if(ticket !== request) return;
    state.routes = Array.isArray(rows) ? rows : [];
    const today = todayIso();
    if(!state.day || !state.routes.some(r => r.data_giro === state.day)){
      state.day = state.routes.map(r => r.data_giro).filter(d => d && d <= today).sort().pop() || today;
    }
    render();
    if(routeId) await open(routeId);
  }
  function bind(){
    const search = $('historySearch');
    if(!search || search.dataset.bound) return;
    search.dataset.bound = '1';
    search.addEventListener('input', () => { state.query = search.value; render(); });
    $('historyRouteDialog').addEventListener('click', e => { if(e.target === e.currentTarget) e.currentTarget.close(); });
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind); else bind();

  return {
    load, open, render, exportRoutes, exportStops, openFilters, applyFilters, remove:removeFilter, clear:clearFilters,
    close(){ $('historyRouteDialog').close(); },
    day(iso){ state.day = iso; render(); },
    week(step){ state.day = step ? dashScheduledAddDays(dashScheduledMonday(state.day), step*7) : (state.routes.map(r => r.data_giro).filter(d => d && d <= todayIso()).sort().pop() || todayIso()); render(); }
  };
})();
