/* Pianificazione: finestre «Aggiungi clienti» e «Aggiungi ordini».
   Stessa disposizione per entrambe: filtri in alto, risultati in tabella con caselle
   di spunta, riepilogo e conferma in basso. I clienti entrano nel giro come oggi
   (deliveryFromCustomer); gli ordini si accodano alle consegne senza rigenerarle. */
(function(){
  'use strict';
  const el = id => document.getElementById(id);
  const state = {cliente: {rows: [], picked: new Set()}, ordine: {rows: [], picked: new Set()}};
  const word = {cliente: ['cliente', 'clienti'], ordine: ['ordine', 'ordini']};
  const plural = (kind, n) => `${n} ${n === 1 ? word[kind][0] : word[kind][1]}`;
  const badge = (status, text) => `<span class="gf-badge" data-status="${status}">${esc(text)}</span>`;
  const options = (values, all) => `<option value="">${esc(all)}</option>` + [...new Set(values.filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'it')).map(v => `<option>${esc(v)}</option>`).join('');
  const agentName = c => c.agent_name || 'Cliente interno';
  const inRoute = c => deliveries.some(d => String(d.customer_id || '') === String(c.id));
  const window_ = o => o.time_from && o.time_to ? `${o.time_from}–${o.time_to}` : 'Tutto il giorno';

  function blocked(kind, row){
    if(row.ferry_reason) return true;
    return kind === 'cliente' && (inRoute(row) || !customerIsPlannable(row));
  }
  function visible(kind){
    const dialog = el(kind === 'cliente' ? 'planningCustomerDialog' : 'planningOrderDialog');
    const read = key => dialog.querySelector(`[data-filter="${key}"]`)?.value || '';
    const q = read('q').trim().toLowerCase();
    return state[kind].rows.filter(row => {
      const text = (kind === 'cliente'
        ? [row.nome, row.codice_cliente, row.indirizzo, row.comune]
        : [row.number, row.recipient_name, row.address]).join(' ').toLowerCase();
      if(q && !text.includes(q)) return false;
      if(kind === 'cliente'){
        if(read('comune') && row.comune !== read('comune')) return false;
        if(read('provincia') && row.provincia !== read('provincia')) return false;
        if(read('agente') && agentName(row) !== read('agente')) return false;
      }else if(read('fonte') && row.source !== read('fonte')) return false;
      return true;
    });
  }

  function customerRow(c, picked){
    const flags = (c.ztl ? ' <span class="gf-badge" data-kind="ztl">ZTL</span>' : '') + (c.sponda ? ' <span class="gf-badge" data-kind="tail-lift">Sponda</span>' : '');
    const status = c.ferry_reason ? ' ' + badge('danger', 'Solo in traghetto') : inRoute(c) ? ' ' + badge('info', 'Già nel giro') : '';
    return `<tr><td data-label="Scegli"><label class="gf-check"><input type="checkbox" data-pick="${c.id}" ${picked.has(c.id) ? 'checked' : ''} ${blocked('cliente', c) ? 'disabled' : ''} aria-label="Seleziona ${esc(c.nome)}"></label></td>
      <td data-label="Cliente"><strong>${esc(c.nome)}</strong>${status}<br><small class="gf-muted">${esc(c.codice_cliente || '')}</small></td>
      <td data-label="Indirizzo">${esc(c.indirizzo)}${c.comune ? ', ' + esc(c.comune) : ''}${c.provincia ? ' (' + esc(c.provincia) + ')' : ''}${flags}</td>
      ${agentsFeatureEnabled() ? `<td data-label="Agente">${esc(agentName(c))}</td>` : ''}
      <td data-label="Scarico">${esc(fascia(c))}</td></tr>`;
  }
  function orderRow(o, picked){
    const kg = o.weight_kg == null ? 'peso non indicato' : `${gfDecimal(o.weight_kg)} kg`;
    const colli = o.packages == null ? 'colli non indicati' : gfCount(o.packages, 'collo', 'colli');
    return `<tr><td data-label="Scegli"><label class="gf-check"><input type="checkbox" data-pick="${o.id}" ${picked.has(o.id) ? 'checked' : ''} ${blocked('ordine', o) ? 'disabled' : ''} aria-label="Seleziona ordine ${esc(o.number)}"></label></td>
      <td data-label="Ordine"><strong>${esc(o.number)}</strong><br><small class="gf-muted">${esc(o.source)}</small></td>
      <td data-label="Destinatario">${esc(o.recipient_name)}${o.ferry_reason ? ' ' + badge('danger', 'Solo in traghetto') : ''}<br><small class="gf-muted">${esc(o.address)}</small></td>
      <td data-label="Data richiesta">${o.requested_date ? esc(gfDateIt(o.requested_date)) : 'Nessuna'}</td>
      <td data-label="Merce">${esc(colli)} · ${esc(kg)}</td><td data-label="Scarico">${esc(window_(o))}</td></tr>`;
  }

  function draw(kind){
    const dialog = el(kind === 'cliente' ? 'planningCustomerDialog' : 'planningOrderDialog');
    const {picked} = state[kind];
    const rows = visible(kind);
    const all = '<label class="gf-check"><input type="checkbox" data-pick-all aria-label="Seleziona tutti i risultati"></label>';
    const head = kind === 'cliente'
      ? `<th scope="col">${all}</th><th scope="col">Cliente</th><th scope="col">Indirizzo</th>${agentsFeatureEnabled() ? '<th scope="col">Agente</th>' : ''}<th scope="col">Scarico</th>`
      : `<th scope="col">${all}</th><th scope="col">Ordine</th><th scope="col">Destinatario</th><th scope="col">Data richiesta</th><th scope="col">Merce</th><th scope="col">Scarico</th>`;
    dialog.querySelector('[data-results]').innerHTML = rows.length
      ? `<table class="gf-table" data-gf-responsive="cards"><caption>${plural(kind, rows.length)}</caption><thead><tr>${head}</tr></thead><tbody>${rows.map(row => kind === 'cliente' ? customerRow(row, picked) : orderRow(row, picked)).join('')}</tbody></table>`
      : `<div class="gf-empty"><p>${state[kind].rows.length ? 'Nessun risultato con questi filtri' : kind === 'cliente' ? 'Nessun cliente con indirizzo verificato' : 'Nessun ordine pronto per questa data'}</p><small>${state[kind].rows.length ? 'Togli un filtro o cerca con un altro nome.' : kind === 'cliente' ? 'Verifica gli indirizzi dalla pagina Clienti.' : 'Gli ordini devono essere pronti, con indirizzo verificato e senza un giro assegnato.'}</small></div>`;
    const chosen = state[kind].rows.filter(row => picked.has(row.id));
    let summary = chosen.length ? `${plural(kind, chosen.length)} ${chosen.length === 1 ? 'selezionato' : 'selezionati'}` : `Nessun ${word[kind][0]} selezionato`;
    if(kind === 'ordine' && chosen.length){
      summary += ` · ${gfCount(chosen.reduce((s, o) => s + (Number(o.packages) || 0), 0), 'collo', 'colli')} · ${gfDecimal(chosen.reduce((s, o) => s + (Number(o.weight_kg) || 0), 0))} kg`;
    }
    dialog.querySelector('[data-selected]').textContent = summary;
    const submit = dialog.querySelector('[data-submit]');
    submit.disabled = !chosen.length;
    submit.textContent = chosen.length ? `Aggiungi ${plural(kind, chosen.length)}` : `Aggiungi ${word[kind][1]}`;
    const allBox = dialog.querySelector('[data-pick-all]');
    if(allBox){
      const free = rows.filter(row => !blocked(kind, row));
      allBox.checked = free.length > 0 && free.every(row => picked.has(row.id));
      allBox.indeterminate = !allBox.checked && free.some(row => picked.has(row.id));
      allBox.disabled = !free.length;
    }
  }

  function bind(kind){
    const dialog = el(kind === 'cliente' ? 'planningCustomerDialog' : 'planningOrderDialog');
    if(!dialog || dialog.dataset.bound) return dialog;
    dialog.dataset.bound = '1';
    dialog.addEventListener('input', event => {
      const target = event.target, {picked} = state[kind];
      if(target.matches('[data-pick]')){
        const id = Number(target.dataset.pick);
        target.checked ? picked.add(id) : picked.delete(id);
      }else if(target.matches('[data-pick-all]')){
        visible(kind).filter(row => !blocked(kind, row)).forEach(row => target.checked ? picked.add(row.id) : picked.delete(row.id));
      }
      draw(kind);
    });
    dialog.addEventListener('change', event => { if(event.target.matches('select[data-filter]')) draw(kind); });
    dialog.addEventListener('click', event => {
      if(event.target.closest('[data-close]')) dialog.close();
      if(event.target.closest('[data-submit]')) (kind === 'cliente' ? addCustomers : addOrders)();
    });
    return dialog;
  }

  async function open(kind, url){
    const dialog = bind(kind);
    if(!dialog) return;
    state[kind].picked.clear();
    dialog.querySelectorAll('[data-filter]').forEach(node => { node.value = ''; });
    dialog.querySelector('[data-results]').innerHTML = '<div class="gf-loading" role="status">Caricamento…</div>';
    dialog.querySelector('[data-submit]').disabled = true;
    dialog.showModal();
    dialog.querySelector('[data-filter="q"]')?.focus();
    try{
      const data = await api(url);
      state[kind].rows = kind === 'cliente' ? data : data.orders;
    }catch(error){
      dialog.querySelector('[data-results]').innerHTML = `<div class="gf-alert" data-status="danger" role="alert"><div class="gf-alert__body"><p class="gf-alert__text">${esc(error.message || 'Caricamento non riuscito. Riprova.')}</p></div></div>`;
      return;
    }
    if(kind === 'cliente'){
      const rows = state.cliente.rows;
      dialog.querySelector('[data-filter="comune"]').innerHTML = options(rows.map(c => c.comune), 'Tutti i comuni');
      dialog.querySelector('[data-filter="provincia"]').innerHTML = options(rows.map(c => c.provincia), 'Tutte');
      const agent = dialog.querySelector('[data-filter="agente"]');
      agent.innerHTML = options(rows.map(agentName), 'Tutti');
      agent.closest('.gf-field').classList.toggle('gf-hidden', !agentsFeatureEnabled());
    }else{
      dialog.querySelector('[data-filter="fonte"]').innerHTML = options(state.ordine.rows.map(o => o.source), 'Tutte');
    }
    draw(kind);
  }

  function openCustomers(){
    const deposit = val('routeDeposit');
    open('cliente', '/api/customers?planning_only=true&limit=1000' + (deposit ? '&deposit_id=' + encodeURIComponent(deposit) : ''));
  }
  function openOrders(){
    if(!val('routeDate')){ alert('Scegli prima la data del giro: gli ordini si filtrano su quella data.'); return; }
    const deposit = val('routeDeposit');
    open('ordine', '/api/order-planning/available?data_giro=' + encodeURIComponent(val('routeDate')) + (deposit ? '&deposit_id=' + encodeURIComponent(deposit) : ''));
  }

  function addCustomers(){
    const chosen = state.cliente.rows.filter(c => state.cliente.picked.has(c.id) && !blocked('cliente', c));
    if(!chosen.length) return;
    chosen.forEach(c => deliveries.push(deliveryFromCustomer(c)));
    el('planningCustomerDialog').close();
    renderDeliveries();
    toast(`${plural('cliente', chosen.length)} ${chosen.length === 1 ? 'aggiunto' : 'aggiunti'}. Premi Calcola percorso quando hai terminato le modifiche.`);
    markRouteNeedsRecalculation('Le consegne sono state modificate. Premi Calcola percorso per aggiornare il risultato.');
  }

  async function addOrders(){
    const dialog = el('planningOrderDialog'), submit = dialog.querySelector('[data-submit]');
    const ids = state.ordine.rows.filter(o => state.ordine.picked.has(o.id) && !blocked('ordine', o)).map(o => o.id);
    if(!ids.length) return;
    const planning = globalThis.GFOrderPlanning;
    const fromSelection = !!planning?.active();
    submit.disabled = true;
    try{
      if(fromSelection) await planning.flush();
      const result = await api('/api/order-planning/stops', {method: 'POST', body: JSON.stringify({
        order_ids: ids, data_giro: val('routeDate'), stops: deliveries,
        group_orders: fromSelection && !!planning.config().group_orders,
        version: fromSelection ? planning.selection().version : null,
        // Stesso giro in modifica usato dal ricalcolo in core.js.
        route_id: planning?.routeId() || (lastRouteResult?.id && deliveries.some(d => d.order_refs?.length) ? lastRouteResult.id : null)})});
      result.merged.forEach(({index, stop}) => { deliveries[index] = stop; });
      deliveries.push(...result.added);
      if(result.selection) planning.acceptSelection(result.selection);
      dialog.close();
      renderDeliveries();
      const joined = result.merged.length ? ` (${result.merged.length} unit${result.merged.length === 1 ? 'o' : 'i'} a fermate già presenti)` : '';
      toast(`${plural('ordine', ids.length)} ${ids.length === 1 ? 'aggiunto' : 'aggiunti'}${joined}. Premi Calcola percorso quando hai terminato le modifiche.`);
      markRouteNeedsRecalculation('Le consegne sono state modificate. Premi Calcola percorso per aggiornare il risultato.');
    }catch(error){
      alert(error.message || 'Non è stato possibile aggiungere gli ordini. Riprova.');
      draw('ordine');
    }
  }

  window.GFPlanningPickers = {openCustomers, openOrders};
})();
