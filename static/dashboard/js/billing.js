/* Commercial catalogue and explicit sandbox subscription controls. */
function planFeatures(plan) {
  const p = window.GF_PLANS[plan];
  const features = [`${p.max_customers} clienti`, `${p.max_routes_per_month} giri/mese`,
    `${p.max_deliveries_per_month} consegne/mese`, `${p.max_deposits} depositi`,
    `${p.max_vehicles} mezzi · ${p.max_drivers} autisti`,
    'Portale autista, firma e storico', 'Importazione ed esportazione dati', 'Assistenza tramite ticket'];
  const missing = [];
  for (const [key, label] of [['has_agents','Agenti commerciali'],['has_driver_chat','Chat autisti'],
      ['has_reports','Report operativi'],['has_ai','Funzioni AI senza quota mensile']]) {
    (p[key] ? features : missing).push(label);
  }
  return {name:p.name, price:`€${p.price_eur}`, period:'/mese', features, missing};
}

function renderSubscriptionControls(data) {
  let box = document.getElementById('subscriptionControls');
  const host = document.getElementById('upgradePlanCards');
  if (!host) return;
  if (!box) { box = document.createElement('div'); box.id = 'subscriptionControls'; host.before(box); }
  const b = data.billing || {};
  const usage = data.usage || {};
  const status = data.plan_status || data.plan?.status;
  const messages = [b.checkout_enabled ? 'Ambiente di prova: nessun denaro reale viene addebitato.' :
    'Acquisti non ancora disponibili. Nessun addebito automatico alla fine della prova.'];
  if (b.source === 'legacy' || b.source === 'manual') messages.push('Accesso assegnato amministrativamente; non equivale a un abbonamento pagato.');
  if (b.cancel_at_period_end) messages.push('Disdetta registrata: accesso fino alla fine del periodo pagato.');
  if (b.pending_plan) messages.push(`Piano ${b.pending_plan} programmato dal prossimo rinnovo.`);
  if (status === 'past_due') messages.push(`Pagamento da completare. Tolleranza fino al ${fmtDateV63(b.grace_until)}.`);
  if (['expired','cancelled','incomplete'].includes(status)) messages.push('Puoi consultare ed esportare i dati e terminare i giri già avviati. Nuovi giri non disponibili.');
  box.innerHTML = `<div class="billing-empty-v63">${messages.map(m=>`<p>${esc(m)}</p>`).join('')}
    <p><a href="/api/billing/data-export">Esporta i tuoi dati (CSV in ZIP)</a></p>
    ${Object.entries(usage.resources || {}).map(([key,value])=>`<p>${({customers:'Clienti',vehicles:'Mezzi',drivers:'Autisti',deposits:'Depositi'})[key]}: ${value.used} / ${value.limit}${value.warning?' — Quota utilizzata almeno all’80%':''}</p>`).join('')}
    ${['routes','deliveries'].map(k=>usage[k] ? `<p>${k==='routes'?'Giri':'Consegne'} nel mese ${esc(usage.month)}: <strong>${usage[k].used} / ${usage[k].limit}</strong>${usage[k].warning?' — Attenzione: quota utilizzata almeno all’80%':''}</p>`:'').join('')}
    ${b.checkout_enabled ? `<button class="btn-light" onclick="subscriptionAction('sync')">Aggiorna stato</button>
      <button class="btn-light" onclick="subscriptionAction('cancel-checkout')">Annulla checkout aperto</button>` : ''}
    ${b.checkout_enabled && b.subscription ? `<button class="btn-light" onclick="managePaymentMethodsV876()">Metodo di pagamento e documenti</button>
      <button class="btn-light" onclick="subscriptionAction('${b.cancel_at_period_end?'resume':'cancel'}')">${b.cancel_at_period_end?'Ripristina rinnovo':'Disdici a fine periodo'}</button>`:''}</div>`;
  const button = document.getElementById('btnConfirmUpgrade');
  if (button) { button.disabled = !b.checkout_enabled; button.textContent = b.subscription ? 'Modifica piano di prova' : 'Acquista in modalità di prova'; }
}

async function subscriptionAction(action) {
  if (['cancel','resume'].includes(action) && !confirm(action==='cancel' ?
    'Disdire il rinnovo? Il periodo già pagato resta disponibile.' : 'Ripristinare il rinnovo automatico?')) return;
  try {
    const data = await api(`/api/billing/${action}`, {method:'POST',body:'{}'});
    toast(data.message || 'Stato aggiornato');
    await loadPlanInfo();
    renderSubscriptionControls(await api('/api/billing/my-plan'));
  } catch(e) { alert(e.message); }
}

async function checkoutOrChangePlan() {
  const plan = _selectedUpgradePlan || _currentPlan;
  const button = document.getElementById('btnConfirmUpgrade');
  if (button) button.disabled = true;
  try {
    const state = await api('/api/billing/my-plan');
    if (!state.billing.checkout_enabled) throw new Error('Acquisti non disponibili; incassi reali disabilitati.');
    if (state.billing.subscription && ['active','past_due'].includes(state.plan_status)) {
      const preview = await api('/api/billing/change-preview', {method:'POST', body:JSON.stringify({plan})});
      const message = preview.direction === 'upgrade' ? `Conguaglio di prova: ${fmtEuroV63(preview.amount_due_cents/100)}. Il nuovo piano si attiva dopo il pagamento. Confermi?` :
        `Passare a ${plan} dal ${new Date(preview.effective_at*1000).toLocaleDateString('it-IT')}?`;
      if (!confirm(message)) return;
      const result = await api('/api/billing/change-plan', {method:'POST',body:JSON.stringify({plan,...preview})});
      toast(result.message);
      if (result.payment_url) window.location.assign(result.payment_url);
      else await subscriptionAction('sync');
    } else {
      if (!confirm(`Aprire il checkout di prova per ${plan} a ${fmtEuroV63(window.GF_PLANS[plan].price_eur)}/mese? Nessun denaro reale verrà addebitato.`)) return;
      const result = await api('/api/billing/create-checkout-session', {method:'POST',body:JSON.stringify({plan})});
      window.location.assign(result.checkout_url);
    }
  } catch(e) { alert(e.message); }
  finally { if(button) button.disabled = false; }
}
