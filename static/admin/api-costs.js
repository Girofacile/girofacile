let apiCostSettingsCache = {};

function apiCostMoney(value, currency){
  if(value === null || value === undefined) return '—';
  const n = Number(value || 0);
  const symbols = {EUR:'€', USD:'$', GBP:'£'};
  const decimals = Math.abs(n) < 1 ? 4 : 2;
  return (symbols[currency] || ((currency || 'EUR') + ' ')) + n.toLocaleString('it-IT', {minimumFractionDigits:2, maximumFractionDigits:decimals});
}

function apiCostMoneyMap(map){
  const entries = Object.entries(map || {});
  return entries.length ? entries.map(function(entry){ return apiCostMoney(entry[1], entry[0]); }).join(' + ') : '€0,00';
}

function apiCostQuotaLabel(row){
  if(!Number(row.free_quota || 0)) return 'Nessuna quota';
  return Number(row.free_quota).toLocaleString('it-IT') + (row.quota_period === 'daily' ? '/giorno' : '/mese');
}

function apiCostSettingCard(key, p){
  const first = (p.tiers || [])[0] || {};
  const editablePrice = key !== 'openai' && p.billing_model !== 'subscription';
  let html = '<div class="gf-card gf-stack" data-gap="sm" data-api-cost-setting="' + escapeHtml(key) + '">';
  html += '<h3 class="gf-subtitle">' + escapeHtml(p.label || key) + '</h3>';
  html += '<div class="gf-form-grid">';
  html += '<label class="gf-field"><span class="gf-field__label">Quota gratuita ' + (p.quota_period === 'daily' ? 'giornaliera' : 'mensile') + '</span><input class="gf-input" data-api-cost-field="free" type="number" min="0" step="1" value="' + Number(p.free_quota || 0) + '" ' + (key === 'openai' ? 'disabled' : '') + '></label>';
  html += '<label class="gf-field"><span class="gf-field__label">' + (key === 'openapi_vehicle' ? 'Costo per 1.000 lookup' : (key === 'openai' ? 'Costo' : 'Costo per 1.000 oltre quota')) + '</span><input class="gf-input" data-api-cost-field="price" type="number" min="0" step="0.01" value="' + (first.price_per_1000 == null ? '' : Number(first.price_per_1000)) + '" ' + (editablePrice ? '' : 'disabled') + '></label>';
  if(key === 'mycarplate'){
    html += '<label class="gf-field"><span class="gf-field__label">Piano provider (' + escapeHtml(p.currency || 'GBP') + ')</span><input class="gf-input" data-api-cost-field="sub-price" type="number" min="0" step="0.01" value="' + Number(p.subscription_price || 0) + '"></label><label class="gf-field"><span class="gf-field__label">Lookup inclusi</span><input class="gf-input" data-api-cost-field="sub-units" type="number" min="0" step="1" value="' + Number(p.subscription_units || 0) + '"></label>';
  }
  html += '</div>';
  html += '<p class="gf-field__hint">' + escapeHtml(p.pricing_note || '') + '</p></div>';
  return html;
}

function renderApiCostSettings(settings){
  apiCostSettingsCache = JSON.parse(JSON.stringify(settings || {}));
  const order = ['google_geocoding','mapbox_traffic','mycarplate','openapi_vehicle','openai'];
  return order.filter(function(key){ return apiCostSettingsCache[key]; }).map(function(key){ return apiCostSettingCard(key, apiCostSettingsCache[key]); }).join('');
}

async function loadApiCosts(){
  const monthEl = document.getElementById('api-cost-month');
  if(monthEl && !monthEl.value){
    const d = new Date();
    monthEl.value = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0');
  }
  const month = monthEl ? monthEl.value : '';
  try {
    const data = await api('/api/admin/api-costs?month=' + encodeURIComponent(month));
    if(!data) return;
    const periodLabel = document.getElementById('api-cost-period-label');
    if(periodLabel) periodLabel.textContent = 'Periodo ' + data.month + ' · ' + Number(data.total_calls || 0).toLocaleString('it-IT') + ' chiamate monitorate';
    const highest = data.highest_free_tier;
    const highestPct = highest && highest.free_percent != null ? Number(highest.free_percent).toFixed(1) + '%' : '—';
    const kpi = function(label, value, note){ return '<div class="gf-stat-card"><span class="gf-stat-card__label">' + label + '</span><strong class="gf-stat-card__value">' + value + '</strong><span class="gf-stat-card__change">' + note + '</span></div>'; };
    document.getElementById('api-cost-kpis').innerHTML =
      kpi('Chiamate mese', Number(data.total_calls || 0).toLocaleString('it-IT'), 'API esterne registrate') +
      kpi('Costo stimato', escapeHtml(apiCostMoneyMap(data.estimated_costs)), 'Quote gratuite già applicate') +
      kpi('Proiezione fine mese', escapeHtml(apiCostMoneyMap(data.projected_costs)), 'In base al ritmo attuale') +
      kpi('Quota più utilizzata', highestPct, escapeHtml((highest && highest.label) || 'Nessuna quota monitorata'));

    const alerts = data.alerts || [];
    document.getElementById('api-cost-alerts').innerHTML = alerts.length ? alerts.map(function(a){
      const level = {critical:'danger', danger:'danger', warning:'warning'}[a.level] || 'info';
      return '<p class="gf-alert" data-status="' + level + '"><strong>' + escapeHtml(a.service || '') + '</strong> · ' + escapeHtml(a.message || '') + '</p>';
    }).join('') : '<p class="gf-alert" data-status="success">✓ Nessuna quota gratuita vicina alla soglia di attenzione.</p>';

    document.getElementById('api-cost-tbody').innerHTML = (data.services || []).map(function(row){
      const pct = row.free_percent == null ? null : Number(row.free_percent);
      const width = pct == null ? 100 : Math.max(0, Math.min(100, Math.round(pct / 5) * 5));
      const tone = {danger:'danger', critical:'danger', warning:'warning', ok:'success', success:'success'}[row.status] || 'info';
      const remaining = Number(row.free_quota || 0) ? Number(row.free_remaining || 0).toLocaleString('it-IT') : '—';
      const billable = Number(row.billable_units || 0).toLocaleString('it-IT');
      const cost = apiCostMoney(row.estimated_cost, row.currency);
      const projection = apiCostMoney(row.projected_cost, row.currency);
      const pctLabel = pct == null ? 'Costo a consumo' : pct.toFixed(1) + '% usato' + (row.quota_period === 'daily' ? ' oggi' : '');
      return '<tr>' +
        '<td data-label="Servizio"><strong>' + escapeHtml(row.label || '') + '</strong><br><small class="gf-muted">' + escapeHtml(row.pricing_note || '') + '</small></td>' +
        '<td data-label="Uso mese"><strong>' + Number(row.calls_month || 0).toLocaleString('it-IT') + '</strong><br><small class="gf-muted">' + Number(row.errors_month || 0) + ' errori</small></td>' +
        '<td data-label="Gratis">' + escapeHtml(apiCostQuotaLabel(row)) + '</td>' +
        '<td data-label="Residuo"><strong>' + remaining + '</strong></td>' +
        '<td data-label="Avanzamento"><div class="gf-stack" data-gap="sm"><span class="gf-bar-chart__track"><span class="gf-bar-chart__fill" data-tone="' + tone + '" data-gf-width="' + width + '"></span></span><small class="gf-muted">' + escapeHtml(pctLabel) + '</small></div></td>' +
        '<td data-label="Fatturabile"><strong>' + billable + '</strong></td>' +
        '<td data-label="Costo stimato"><strong>' + escapeHtml(cost) + '</strong></td>' +
        '<td data-label="Proiezione">' + escapeHtml(projection) + '</td>' +
      '</tr>';
    }).join('');

    const companies = data.companies || [];
    document.getElementById('api-cost-companies').innerHTML = companies.length ? companies.map(function(x, i){
      return '<li class="gf-list-item"><div class="gf-list-item__main"><strong>' + (i+1) + '. ' + escapeHtml(x.company_name || '') + '</strong><small>' + Number(x.calls || 0).toLocaleString('it-IT') + ' chiamate</small></div><div class="gf-list-item__main"><strong>' + escapeHtml(apiCostMoneyMap(x.cost_attribution)) + '</strong><small>attribuzione stimata</small></div></li>';
    }).join('') : '<li class="gf-empty"><p>Nessun consumo aziendale registrato.</p></li>';

    const hist = data.history || [];
    const maxCalls = Math.max.apply(null, [1].concat(hist.map(function(x){ return Number(x.calls || 0); })));
    document.getElementById('api-cost-history').innerHTML = hist.length ? hist.map(function(x){
      const width = Math.round(Number(x.calls || 0) / maxCalls * 20) * 5;
      return '<li class="gf-bar-chart__row"><span class="gf-bar-chart__label">' + escapeHtml(x.month || '') + '</span><span class="gf-bar-chart__track"><span class="gf-bar-chart__fill" data-gf-width="' + width + '"></span></span><span class="gf-bar-chart__value">' + Number(x.calls || 0).toLocaleString('it-IT') + ' · ' + escapeHtml(apiCostMoneyMap(x.costs)) + '</span></li>';
    }).join('') : '<li class="gf-empty"><p>Nessuno storico disponibile.</p></li>';

    document.getElementById('api-cost-settings-list').innerHTML = renderApiCostSettings(data.settings || {});
    const usagePeriod = document.getElementById('api-usage-period');
    if(usagePeriod) usagePeriod.value = data.is_current_month ? 'month' : 'previous_month';
    if(typeof loadApiUsage === 'function') await loadApiUsage(data.month);
  } catch(e) { showToast(e.message, 'error'); }
}

async function saveApiCostSettings(){
  try {
    document.querySelectorAll('[data-api-cost-setting]').forEach(function(card){
      const key = card.dataset.apiCostSetting;
      const p = apiCostSettingsCache[key];
      if(!p) return;
      const free = card.querySelector('[data-api-cost-field="free"]');
      if(free && !free.disabled) p.free_quota = Math.max(0, Number(free.value || 0));
      const price = card.querySelector('[data-api-cost-field="price"]');
      if(price && !price.disabled){
        p.tiers = p.tiers || [];
        if(!p.tiers.length) p.tiers = [{up_to:null, price_per_1000:0}];
        p.tiers[0].price_per_1000 = Math.max(0, Number(price.value || 0));
      }
      const subPrice = card.querySelector('[data-api-cost-field="sub-price"]');
      if(subPrice) p.subscription_price = Math.max(0, Number(subPrice.value || 0));
      const subUnits = card.querySelector('[data-api-cost-field="sub-units"]');
      if(subUnits) p.subscription_units = Math.max(0, Number(subUnits.value || 0));
    });
    await api('/api/admin/api-costs/settings', {method:'PUT', body:JSON.stringify(apiCostSettingsCache)});
    showToast('Quote e tariffe API aggiornate', 'success');
    await loadApiCosts();
  } catch(e) { showToast(e.message, 'error'); }
}
