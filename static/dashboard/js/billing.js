/* Commercial catalogue and explicit sandbox subscription controls. */
const GF_PLAN_FEATURES = [
  ['has_customer_tracking', 'Tracking clienti'],
  ['has_fleet_planning', 'Suddivisione automatica su più mezzi'],
  ['has_driver_chat', 'Chat autisti'],
  ['has_agents', 'Agenti commerciali e portale'],
  ['has_delivery_signature', 'Firma alla consegna'],
  ['has_photo_proof', 'Foto prova consegna'],
  ['has_pod_pdf', 'Prova di consegna PDF'],
  ['has_order_integrations', 'API, Shopify e WooCommerce'],
  ['has_reports', 'Report avanzati'],
  ['has_ai', 'Integrazione AI']
];
function planComparisonRows() {
  return [['Ordini al mese','max_orders_per_month'], ['Clienti','max_customers'],
    ['Depositi','max_deposits'], ['Autisti','max_drivers'], ['Mezzi standard','max_vehicles'],
    ['Veicoli elettrici bonus','electric_vehicle_bonus'], ['Collaboratori aziendali','max_collaborators'],
    ['Portale autista e GPS','has_driver_portal'], ...GF_PLAN_FEATURES.map(([key,label])=>[label,key])];
}
// Funzioni della pagina Piani: firma, foto e PDF di consegna formano una sola voce.
const GF_PLAN_PAGE_FEATURES = [
  ['Portale autista e GPS autista', () => true],
  ['Importazione CSV/Excel ed esportazione dati', () => true],
  ['Tracking clienti', p => p.has_customer_tracking === true],
  ['Suddivisione automatica su più mezzi', p => p.has_fleet_planning === true],
  ['Chat autisti', p => p.has_driver_chat === true],
  ['Agenti commerciali e portale', p => p.has_agents === true],
  ['Firma, foto e prova di consegna', p => p.has_delivery_signature === true && p.has_photo_proof === true && p.has_pod_pdf === true],
  ['API, Shopify e WooCommerce', p => p.has_order_integrations === true],
  ['Report avanzati', p => p.has_reports === true],
  ['Integrazione AI', p => p.has_ai === true]
];
function planPageFeatures(plan) {
  const p = window.GF_PLANS[plan];
  return GF_PLAN_PAGE_FEATURES.map(([label, included]) => [included(p), label]);
}
function planFeatureGroups(plan) {
  const p=window.GF_PLANS[plan];
  return [[true,'Portale autista e GPS autista'],
    [p.has_customer_tracking===true && p.has_fleet_planning===true,'Tracking clienti e distribuzione automatica su più mezzi'],
    [p.has_driver_chat===true && p.has_agents===true && p.has_reports===true,'Chat autisti, agenti e report avanzati'],
    [p.has_delivery_signature===true && p.has_photo_proof===true && p.has_pod_pdf===true,'Firma, foto e PDF di consegna'],
    [p.has_order_integrations===true,'Integrazioni API, Shopify e WooCommerce'],
    [p.has_ai===true,'Integrazione AI']];
}
function planFeatures(plan) {
  const p = window.GF_PLANS[plan];
  const resourceFeatures = [`${p.max_orders_per_month} ordini/mese`, `${p.max_customers} clienti`,
    `${p.max_deposits} ${Number(p.max_deposits)===1?'deposito':'depositi'}`,
    `${p.max_vehicles} mezzi · ${p.max_drivers} autisti`, `${p.max_collaborators} collaboratori aziendali`];
  const features = [...resourceFeatures, 'Portale autista e GPS autista',
    'Pianificazione giri e storico', 'Importazione CSV/Excel ed esportazione dati'];
  const missing = [];
  for (const [key, label] of GF_PLAN_FEATURES) (p[key] ? features : missing).push(label);
  const bonus=Number(p.electric_vehicle_bonus||0);
  const electricBenefit=bonus>0?`⚡ +${bonus} ${bonus===1?'veicolo elettrico':'veicoli elettrici'} bonus`:'';
  return {name:p.name, price:`€${p.price_eur}`, period:'/mese', resourceFeatures, features, missing, electricBenefit};
}

// The API supplies effective company entitlements; stored preferences never grant access.
function planAccessLimits() {
  const session=typeof currentSessionUser==='undefined' ? null : currentSessionUser;
  return {...(window.GF_PLANS?.[session?.plan] || {}), ...(session?.limits || {})};
}
function planFeatureEnabled(key) { return planAccessLimits()[key] === true; }
function requirePlanFeature(key,label) {
  if(planFeatureEnabled(key)) return true;
  const message=`${label || 'Questa funzione'} è disponibile ${key==='has_ai'?'nel piano Pro':'dal piano Business'}.`;
  if(typeof toast==='function') toast(message);
  return false;
}
function applyPlanFeatureControls() {
  for(const [id,key] of [['settingDeliverySignature','has_delivery_signature'],['featurePhotoProofV89','has_photo_proof']]) {
    const input=document.getElementById(id);
    if(!input) continue;
    const enabled=planFeatureEnabled(key);
    input.disabled=!enabled;
    if(!enabled) input.checked=false;
    const copy=input.closest('.gf-setting')?.querySelector('.gf-setting__copy');
    let note=copy?.querySelector('[data-plan-upgrade-note]');
    if(copy && !note) { note=document.createElement('p');note.className='gf-field__hint';note.dataset.planUpgradeNote='';copy.append(note); }
    if(note) { note.hidden=enabled;note.textContent='Disponibile dal piano Business. Gestisci il piano nella sezione Piani e abbonamento.'; }
  }
  const fleetEnabled=planFeatureEnabled('has_fleet_planning');
  document.querySelectorAll('[data-plan-feature="has_fleet_planning"]').forEach(control=>{
    control.disabled=!fleetEnabled;control.setAttribute('aria-disabled',String(!fleetEnabled));
    control.title=fleetEnabled?'':'Disponibile dal piano Business';
  });
  const mode=document.getElementById('planningMode');
  if(mode?.value==='fleet' && !fleetEnabled) { mode.value='single';window.GFFleetPlanning?.restore({planning_mode:'single'}); }
  document.getElementById('fleetPlanUpgradeNotice')?.toggleAttribute('hidden',fleetEnabled);
  window.GFCompanyAccess?.apply();
}
window.GFPlanAccess={limits:planAccessLimits,has:planFeatureEnabled,require:requirePlanFeature,apply:applyPlanFeatureControls};

function monthlyOrderUsageMarkup(usage) {
  const orders=usage.orders;
  if(!orders) return '';
  const used=Math.max(0,Number(orders.used)||0),limit=Math.max(0,Number(orders.limit)||0);
  const remaining=Math.max(0,limit-used),percent=limit?Math.min(100,Math.round(used/limit*100)):0;
  const warning=orders.warning || (limit>0 && used>=limit*.8);
  return `<section class="gf-card gf-stack" data-gap="sm" aria-label="Utilizzo ordini mensili"><div class="gf-cluster" data-justify="between"><strong>Ordini del mese · ${esc(usage.month || '')}</strong><span>${used.toLocaleString('it-IT')} / ${limit.toLocaleString('it-IT')}</span></div><div class="gf-progress__track" role="progressbar" aria-label="Ordini utilizzati nel mese" aria-valuemin="0" aria-valuemax="${limit}" aria-valuenow="${Math.min(used,limit)}" aria-valuetext="${used} ordini utilizzati su ${limit}"><span class="gf-progress__done" data-gf-width="${Math.round(percent/5)*5}"></span></div><p class="gf-muted">${remaining.toLocaleString('it-IT')} ordini ancora disponibili questo mese. La quota si rinnova ogni mese.</p>${warning?`<p class="gf-alert" data-status="warning" role="status">${remaining===0?'Quota mensile ordini esaurita.':'Hai utilizzato almeno l’80% degli ordini mensili.'} Puoi valutare un piano superiore.</p>`:''}</section>`;
}

// Consumi del mese nella pagina Piani: barra dei numeri con icone, come nelle altre pagine.
function planUsageStripMarkup(usage) {
  const r=usage.resources || {},orders=usage.orders,fmt=n=>Number(n||0).toLocaleString('it-IT',{useGrouping:'always'});
  const width=(used,limit)=>limit?Math.round(Math.min(100,used/limit*100)/5)*5:0;
  const icons={orders:'M9 4h6v3H9z M7 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1 M9 12h6 M9 16h6',
    customers:'M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1 M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M21 20v-1a4 4 0 0 0-3-3.9 M16 4.1a3.5 3.5 0 0 1 0 6.8',
    vehicles:'M2 6h11v10H2z M13 9h5l3 3v4h-8z M6.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z M17.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z',
    drivers:'M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M5 16h4 M14 10h5 M14 14h5 M7 11.5a1.5 1.5 0 1 0 0-.01'};
  const cell=(icon,tone,label,used,limit,unit,meter='')=>`<div class="gf-stat-strip__cell"><span class="gf-stat-strip__icon" data-tone="${tone}" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="${icons[icon]}"/></svg></span><span class="gf-stat-strip__label">${label}</span><strong class="gf-stat-strip__value">${fmt(used)}</strong><small class="gf-stat-strip__unit">${unit}</small>${meter || `<span class="gf-progress__track" aria-hidden="true"><span class="gf-progress__done" data-gf-width="${width(used,limit)}"></span></span>`}</div>`;
  const cells=[];
  if(orders){
    const used=Math.max(0,Number(orders.used)||0),limit=Math.max(0,Number(orders.limit)||0);
    cells.push(cell('orders','1','Ordini del mese',used,limit,`su ${fmt(limit)}`,`<span class="gf-progress__track" role="progressbar" aria-label="Ordini utilizzati nel mese" aria-valuemin="0" aria-valuemax="${limit}" aria-valuenow="${Math.min(used,limit)}" aria-valuetext="${used} ordini utilizzati su ${limit}"><span class="gf-progress__done" data-gf-width="${width(used,limit)}"></span></span>`));
  }
  if(r.customers) cells.push(cell('customers','1','Clienti',r.customers.used,r.customers.limit,`su ${r.customers.limit==null?'∞':fmt(r.customers.limit)}`));
  const v=r.vehicles;
  if(v) {
    const standard=v.standard_used ?? v.used, limit=v.standard_limit ?? v.limit, bonus=Number(v.electric_bonus||0);
    cells.push(cell('vehicles','neutral','Mezzi',standard,limit,`su ${limit==null?'∞':fmt(limit)}${bonus?` · elettrici bonus ${fmt(v.bonus_used)} su ${fmt(bonus)}`:''}`));
  }
  if(r.drivers) cells.push(cell('drivers','5','Autisti',r.drivers.used,r.drivers.limit,`su ${r.drivers.limit==null?'∞':fmt(r.drivers.limit)}`));
  const extra=[['Depositi',r.deposits],['Collaboratori (attivi e inviti in attesa)',r.collaborators]].filter(([,q])=>q)
    .map(([label,q])=>`${label} ${fmt(q.used)} su ${q.limit==null?'∞':fmt(q.limit)}`);
  const remaining=orders?Math.max(0,Number(orders.limit||0)-Number(orders.used||0)):0;
  const warning=orders && (orders.warning || (orders.limit>0 && orders.used>=orders.limit*.8));
  return `${cells.length?`<div class="gf-stat-strip" data-icons="side" aria-label="Consumi del piano · ${esc(usage.month || '')}">${cells.join('')}</div>`:''}
    ${extra.length||orders?`<p class="gf-muted">${extra.join(' · ')}${extra.length&&orders?'. ':''}${orders?`${fmt(remaining)} ordini ancora disponibili questo mese: la quota si rinnova ogni mese.`:''}</p>`:''}
    ${warning?`<p class="gf-alert" data-status="warning" role="status">${remaining===0?'Quota mensile ordini esaurita.':'Hai utilizzato almeno l’80% degli ordini mensili.'} Puoi valutare un piano superiore.</p>`:''}
    ${v?.over_limit?`<p class="gf-alert" data-status="warning" role="status">${esc(v.message||'La flotta supera i limiti del piano. I mezzi esistenti sono conservati.')}</p>`:''}`;
}

function renderOrderUsage(usage) {
  document.querySelectorAll('[data-monthly-order-usage]').forEach(box=>{
    box.innerHTML=monthlyOrderUsageMarkup(usage || {});box.hidden=!usage?.orders;
  });
}
async function refreshMonthlyOrderUsage() {
  if(window.GFCompanyAccess?.isCollaborator()) return;
  try { const data=await api('/api/billing/my-plan');renderOrderUsage(data.usage); } catch(error) { console.warn('Utilizzo ordini non disponibile',error); }
}
function renderSubscriptionControls(data) {
  if(window.GFCompanyAccess?.isCollaborator()) return;
  let box = document.getElementById('subscriptionControls');
  const host = document.getElementById('upgradePlanCards');
  if (!host) return;
  if (!box) { box = document.createElement('div'); box.id = 'subscriptionControls'; host.before(box); }
  const b = data.billing || {};
  const usage = data.usage || {};
  renderOrderUsage(usage);
  const status = data.plan_status || data.plan?.status;
  const messages = [b.checkout_enabled ? 'Ambiente di prova: nessun denaro reale viene addebitato.' :
    'Acquisti non ancora disponibili. Nessun addebito automatico alla fine della prova.'];
  if (b.source === 'legacy' || b.source === 'manual') messages.push('Accesso assegnato amministrativamente; non equivale a un abbonamento pagato.');
  if (b.cancel_at_period_end) messages.push('Disdetta registrata: accesso fino alla fine del periodo pagato.');
  if (b.pending_plan) messages.push(`Piano ${b.pending_plan} programmato dal prossimo rinnovo.`);
  if (status === 'past_due') messages.push(`Pagamento da completare. Tolleranza fino al ${fmtDateV63(b.grace_until)}.`);
  if (['expired','cancelled','incomplete'].includes(status)) messages.push('Puoi consultare ed esportare i dati e terminare i giri già avviati. Nuovi giri non disponibili.');
  box.innerHTML = `${planUsageStripMarkup(usage)}${messages.length?`<div class="gf-alert" data-status="info"><div class="gf-alert__body">${messages.map(m=>`<p>${esc(m)}</p>`).join('')}</div></div>`:''}
    ${b.checkout_enabled ? `<div class="gf-cluster"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="subscriptionAction('sync')">Aggiorna stato</button>
      <button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="subscriptionAction('cancel-checkout')">Annulla checkout aperto</button>
    ${b.subscription ? `<button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="managePaymentMethodsV876()">Metodo di pagamento e documenti</button>
      <button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="subscriptionAction('${b.cancel_at_period_end?'resume':'cancel'}')">${b.cancel_at_period_end?'Ripristina rinnovo':'Disdici a fine periodo'}</button>`:''}</div>` : ''}`;
  const button = document.getElementById('btnConfirmUpgrade');
  if (button) { button.disabled = !b.checkout_enabled; button.textContent = b.subscription ? 'Modifica piano di prova' : 'Acquista in modalità di prova'; button.title = b.checkout_enabled ? '' : 'Acquisti non ancora disponibili'; }
}

async function subscriptionAction(action) {
  if(window.GFCompanyAccess?.isCollaborator()) return;
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
  if(window.GFCompanyAccess?.isCollaborator()) return;
  const plan = _selectedUpgradePlan || _currentPlan;
  const button = document.getElementById('btnConfirmUpgrade');
  if (button) button.disabled = true;
  try {
    const state = await api('/api/billing/my-plan');
    if (!state.billing.checkout_enabled) throw new Error('Acquisti non disponibili; incassi reali disabilitati.');
    if (state.billing.subscription && ['active','past_due'].includes(state.plan_status)) {
      const preview = await api('/api/billing/change-preview', {method:'POST', body:JSON.stringify({plan})});
      let message = preview.direction === 'upgrade' ? `Conguaglio di prova: ${fmtEuroV63(preview.amount_due_cents/100)}. Il nuovo piano si attiva dopo il pagamento. Confermi?` :
        `Passare a ${plan} dal ${new Date(preview.effective_at*1000).toLocaleDateString('it-IT')}?`;
      if(preview.resources_over_limit?.length)message+=' Le risorse già presenti saranno conservate; le nuove aggiunte resteranno bloccate finché rientri nei limiti: '+preview.resources_over_limit.join(', ')+'.';
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
