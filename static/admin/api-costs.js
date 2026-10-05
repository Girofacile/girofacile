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
  let html = '<div class="api-cost-setting-v73" data-api-cost-setting="' + escapeHtml(key) + '">';
  html += '<h4>' + escapeHtml(p.label || key) + '</h4>';
  html += '<div class="form-row-v64">';
  html += '<div class="form-group"><label class="form-label">Quota gratuita ' + (p.quota_period === 'daily' ? 'giornaliera' : 'mensile') + '</label><input class="form-control api-cost-free" type="number" min="0" step="1" value="' + Number(p.free_quota || 0) + '" ' + (key === 'openai' ? 'disabled' : '') + '></div>';
  html += '<div class="form-group"><label class="form-label">' + (key === 'openapi_vehicle' ? 'Costo per 1.000 lookup' : (key === 'openai' ? 'Costo' : 'Costo per 1.000 oltre quota')) + '</label><input class="form-control api-cost-price" type="number" min="0" step="0.01" value="' + (first.price_per_1000 == null ? '' : Number(first.price_per_1000)) + '" ' + (editablePrice ? '' : 'disabled') + '></div>';
  html += '</div>';
  if(key === 'mycarplate'){
    html += '<div class="form-row-v64"><div class="form-group"><label class="form-label">Piano provider (' + escapeHtml(p.currency || 'GBP') + ')</label><input class="form-control api-cost-sub-price" type="number" min="0" step="0.01" value="' + Number(p.subscription_price || 0) + '"></div><div class="form-group"><label class="form-label">Lookup inclusi</label><input class="form-control api-cost-sub-units" type="number" min="0" step="1" value="' + Number(p.subscription_units || 0) + '"></div></div>';
  }
  html += '<div class="api-cost-note-v73">' + escapeHtml(p.pricing_note || '') + '</div></div>';
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
    document.getElementById('api-cost-kpis').innerHTML =
      '<div class="api-cost-kpi-v73"><small>Chiamate mese</small><strong>' + Number(data.total_calls || 0).toLocaleString('it-IT') + '</strong><span>API esterne registrate</span></div>' +
      '<div class="api-cost-kpi-v73"><small>Costo stimato</small><strong>' + escapeHtml(apiCostMoneyMap(data.estimated_costs)) + '</strong><span>Quote gratuite già applicate</span></div>' +
      '<div class="api-cost-kpi-v73"><small>Proiezione fine mese</small><strong>' + escapeHtml(apiCostMoneyMap(data.projected_costs)) + '</strong><span>In base al ritmo attuale</span></div>' +
      '<div class="api-cost-kpi-v73"><small>Quota più utilizzata</small><strong>' + highestPct + '</strong><span>' + escapeHtml((highest && highest.label) || 'Nessuna quota monitorata') + '</span></div>';

    const alerts = data.alerts || [];
    document.getElementById('api-cost-alerts').innerHTML = alerts.length ? alerts.map(function(a){
      return '<div class="api-cost-alert-v73 ' + escapeHtml(a.level || '') + '"><strong>' + escapeHtml(a.service || '') + '</strong> · ' + escapeHtml(a.message || '') + '</div>';
    }).join('') : '<div class="api-cost-alert-v73">✓ Nessuna quota gratuita vicina alla soglia di attenzione.</div>';

    document.getElementById('api-cost-tbody').innerHTML = (data.services || []).map(function(row){
      const pct = row.free_percent == null ? null : Number(row.free_percent);
      const width = pct == null ? 100 : Math.max(0, Math.min(100, pct));
      const remaining = Number(row.free_quota || 0) ? Number(row.free_remaining || 0).toLocaleString('it-IT') : '—';
      const billable = Number(row.billable_units || 0).toLocaleString('it-IT');
      const cost = apiCostMoney(row.estimated_cost, row.currency);
      const projection = apiCostMoney(row.projected_cost, row.currency);
      const pctLabel = pct == null ? 'Costo a consumo' : pct.toFixed(1) + '% usato' + (row.quota_period === 'daily' ? ' oggi' : '');
      return '<tr>' +
        '<td data-label="Servizio" class="api-cost-provider-v73"><strong>' + escapeHtml(row.label || '') + '</strong><small>' + escapeHtml(row.pricing_note || '') + '</small></td>' +
        '<td data-label="Uso mese"><strong>' + Number(row.calls_month || 0).toLocaleString('it-IT') + '</strong><br><small class="api-cost-meta-v73">' + Number(row.errors_month || 0) + ' errori</small></td>' +
        '<td data-label="Gratis">' + escapeHtml(apiCostQuotaLabel(row)) + '</td>' +
        '<td data-label="Residuo"><strong>' + remaining + '</strong></td>' +
        '<td data-label="Avanzamento"><div class="api-cost-progress-v73"><div class="api-cost-track-v73"><div class="api-cost-fill-v73 ' + escapeHtml(row.status || 'info') + '" style="width:' + width + '%"></div></div><small>' + escapeHtml(pctLabel) + '</small></div></td>' +
        '<td data-label="Fatturabile"><strong>' + billable + '</strong></td>' +
        '<td data-label="Costo stimato" class="api-cost-money-v73 ' + (Number(row.estimated_cost || 0) === 0 ? 'zero' : '') + '">' + escapeHtml(cost) + '</td>' +
        '<td data-label="Proiezione" class="api-cost-money-v73">' + escapeHtml(projection) + '</td>' +
      '</tr>';
    }).join('');

    const companies = data.companies || [];
    document.getElementById('api-cost-companies').innerHTML = companies.length ? companies.map(function(x, i){
      return '<div class="api-cost-list-row-v73"><div><strong>' + (i+1) + '. ' + escapeHtml(x.company_name || '') + '</strong><small>' + Number(x.calls || 0).toLocaleString('it-IT') + ' chiamate</small></div><div style="text-align:right"><strong>' + escapeHtml(apiCostMoneyMap(x.cost_attribution)) + '</strong><small>attribuzione stimata</small></div></div>';
    }).join('') : '<div class="empty"><p>Nessun consumo aziendale registrato.</p></div>';

    const hist = data.history || [];
    const maxCalls = Math.max.apply(null, [1].concat(hist.map(function(x){ return Number(x.calls || 0); })));
    document.getElementById('api-cost-history').innerHTML = hist.length ? hist.map(function(x){
      const width = Math.round(Number(x.calls || 0) / maxCalls * 100);
      return '<div class="api-cost-history-row-v73"><strong>' + escapeHtml(x.month || '') + '</strong><div class="api-cost-history-bar-v73"><span style="width:' + width + '%"></span></div><div style="text-align:right"><strong>' + Number(x.calls || 0).toLocaleString('it-IT') + '</strong><small>' + escapeHtml(apiCostMoneyMap(x.costs)) + '</small></div></div>';
    }).join('') : '<div class="empty"><p>Nessuno storico disponibile.</p></div>';

    document.getElementById('api-cost-settings-list').innerHTML = renderApiCostSettings(data.settings || {});
    const usagePeriod = document.getElementById('api-usage-period');
    if(usagePeriod) usagePeriod.value = data.is_current_month ? 'month' : 'previous_month';
    if(typeof loadApiUsage === 'function') await loadApiUsage();
  } catch(e) { showToast(e.message, 'error'); }
}

async function saveApiCostSettings(){
  try {
    document.querySelectorAll('[data-api-cost-setting]').forEach(function(card){
      const key = card.dataset.apiCostSetting;
      const p = apiCostSettingsCache[key];
      if(!p) return;
      const free = card.querySelector('.api-cost-free');
      if(free && !free.disabled) p.free_quota = Math.max(0, Number(free.value || 0));
      const price = card.querySelector('.api-cost-price');
      if(price && !price.disabled){
        p.tiers = p.tiers || [];
        if(!p.tiers.length) p.tiers = [{up_to:null, price_per_1000:0}];
        p.tiers[0].price_per_1000 = Math.max(0, Number(price.value || 0));
      }
      const subPrice = card.querySelector('.api-cost-sub-price');
      if(subPrice) p.subscription_price = Math.max(0, Number(subPrice.value || 0));
      const subUnits = card.querySelector('.api-cost-sub-units');
      if(subUnits) p.subscription_units = Math.max(0, Number(subUnits.value || 0));
    });
    await api('/api/admin/api-costs/settings', {method:'PUT', body:JSON.stringify(apiCostSettingsCache)});
    showToast('Quote e tariffe API aggiornate', 'success');
    await loadApiCosts();
  } catch(e) { showToast(e.message, 'error'); }
}
