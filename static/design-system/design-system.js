/* Presentation only. No requests, persistence, routing, permissions or business state. */
(function(global){
  'use strict';
  const doc = global.document;
  const BUTTONS = '.dash-link-btn,.deposit-delete-danger,.fleet-edit,.fleet-delete,.driver-delete,.driver-menu summary,.customer-tracking-trigger,.fleet-create,.fleet-views button,.driver-view,.completed-tools button,.live-design-table-actions button,.live-design-actions>button,.live-design-actions>a,.preview-program,.plan-billing-btn-v875,.payment-add-v876,.customer-view-controls button,.deposit-view-controls button,.gf-routing-summary button,.btn-login-submit,.btn-start,.btn-view,.btn-note,.btn-note-small,.btn-signature-open,.btn-clear-signature,.mini-btn,.fab,.popup-confirm,.popup-cancel,.maps-btn,.btn-danger-outline,.btn-login,.btn-cta-nav,.btn-hero,.btn-hero-ghost,.btn-plan,.btn-white,.btn-ghost-white,.lm-btn,.gf-button,.btn,.btn-primary,.btn-secondary,.btn-light,.btn-ghost,.btn-danger,.btn-danger-soft,.customer-delete-danger,.btn-navigate,.btn-done,.btn-missed,.btn-confirm,.customer-row-actions button,.deposit-row-actions button,.fleet-card-actions button,.row-actions button,.driver-actions button,.gf-pagination button,#customerPagination button,#depositPagination button,#fleetPagination button';
  const NAV = '.nav-item,.bnav-btn,.bnav,.bnav-item,.bnav-item button,.admin-mobile-bottom-nav-v62 button';
  const LABEL_TABLES = '.customer-table,.deposit-table,.fleet-table,.drivers-table,#tab-autisti .tableWrap table,#tab-agenti table,#tab-report .tableWrap table,#tab-storico .tableWrap table,#tab-dashboard-scheduled .dash-sub-table,#tab-dashboard-completed .dash-sub-table,body[data-gf-surface="agent"] .table-wrap table,body[data-gf-surface="admin"] .table-wrap table,table[data-gf-responsive="cards"]';
  const VARIANTS = new Set(['primary','secondary','ghost','danger']);
  const STATES = new Set(['success','warning','danger','info','neutral']);
  function nodes(root, selector){
    const result = root.querySelectorAll ? Array.from(root.querySelectorAll(selector)) : [];
    if(root.matches && root.matches(selector)) result.unshift(root);
    return result;
  }
  function mark(el, name){ if(!el.classList.contains(name)) el.classList.add(name); }
  function classifyButton(el){
    if(VARIANTS.has(el.dataset.variant) && !el.dataset.gfDerivedVariant) return;
    const variant = el.matches('.deposit-delete-danger,.fleet-delete,.driver-delete,.btn-danger,.btn-danger-soft,.customer-delete-danger,.btn-missed,.btn.danger,.danger,.btn-confirm.red,.mini-btn.red,.mini-btn.remove,.btn-danger-outline')
      ? 'danger' : el.matches('.btn-primary,.btn.primary,.btn-navigate,.btn-done,.btn-confirm,.btn-login-submit,.btn-start,.btn-signature-open,.fab,.popup-confirm,.maps-btn,.btn-cta-nav,.btn-hero,.btn-plan,.lm-btn,.fleet-create,.preview-program,.live-primary')
      ? 'primary' : el.matches('.btn-ghost,.btn.ghost,.ghost,.btn-note,.btn-note-small,.btn-clear-signature,.btn-hero-ghost,.btn-ghost-white') ? 'ghost' : 'secondary';
    el.dataset.variant = variant; el.dataset.gfDerivedVariant = 'true';
    if(el.matches('.btn-done,.btn-confirm.green,.mini-btn.green')) { el.dataset.status='success'; el.dataset.gfDerivedSuccess='true'; }
    else if(el.dataset.gfDerivedSuccess) { delete el.dataset.status; delete el.dataset.gfDerivedSuccess; }
  }
  function classifyBadge(el){
    if(STATES.has(el.dataset.status) && !el.dataset.gfDerivedStatus) return;
    const names = Array.from(el.classList).join(' ').toLowerCase();
    const raw = String(el.dataset.state || '').toLowerCase();
    const state = names + ' ' + raw;
    const status = /(?:^|[\s-])(completed|completato|completata|consegnato|consegnata|verificato|verified|configured|complete|available|default|done|ok|success|active|attivo|paid)(?:$|[\s-])/.test(state)
      ? 'success' : /(?:^|[\s-])(mancata|failed|error|danger|cancel|cancelled|annullato|annullata|non_trovato|ztl|unpaid|expired)(?:$|[\s-])/.test(state)
      ? 'danger' : /(?:^|[\s-])(programmato|scheduled|pending|da_verificare|da_completare|sponda|partial|rest|warn|warning|trial|prog)(?:$|[\s-])/.test(state)
      ? 'warning' : /(?:^|[\s-])(in_corso|in_attesa|working|busy|time|corso|progress|info|running|in-progress)(?:$|[\s-])/.test(state) ? 'info' : 'neutral';
    el.dataset.status = status; el.dataset.gfDerivedStatus = 'true';
  }
  function labelTable(table){
    const headers = table.tHead && table.tHead.rows.length ? Array.from(table.tHead.rows[table.tHead.rows.length-1].cells) : [];
    if(!headers.length || headers.some(cell => cell.colSpan !== 1 || cell.rowSpan !== 1)) return;
    const labels = headers.map(cell => cell.textContent.trim().replace(/\s+/g,' ') || cell.getAttribute('aria-label') || 'Azioni');
    table.dataset.gfResponsive = 'cards';
    table.setAttribute('role','table');
    for(const body of Array.from(table.tBodies)){
      body.setAttribute('role','rowgroup');
      for(const row of Array.from(body.rows)){
        row.setAttribute('role','row');
        const cells = Array.from(row.cells);
        if(cells.length !== headers.length || cells.some(cell => cell.colSpan !== 1)) continue;
        cells.forEach((cell,index) => {
          if(cell.dataset.label !== labels[index]) cell.dataset.label = labels[index];
          cell.setAttribute('role','cell');
        });
      }
    }
  }
  function enhance(root){
    root = root || doc;
    if(!doc || !doc.body || !doc.body.dataset.gfSurface) return;
    nodes(root,BUTTONS).forEach(el => { if(el.closest('.leaflet-control,.signature-pad')) return; mark(el,'gf-button'); classifyButton(el); });
    nodes(root,'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]):not([type="range"]):not([type="color"])')
      .forEach(el => { if(!el.closest('.leaflet-control')) mark(el,'gf-input'); });
    nodes(root,'select').forEach(el => mark(el,'gf-select'));
    nodes(root,'textarea').forEach(el => mark(el,'gf-textarea'));
    nodes(root,'.badge,.rc-badge,.di-badge,.dc-badge,.badge-count,.customer-status,.route-status-pill,.delivery-status-pill,.deposit-default-badge,.fleet-status,.driver-status,.driver-state,.company-configured-badge-v40')
      .forEach(el => { mark(el,'gf-badge'); classifyBadge(el); });
    nodes(root,'table:not(.leaflet-control table)').forEach(el => mark(el,'gf-table'));
    nodes(root,LABEL_TABLES).forEach(labelTable);
    nodes(root,'.customer-details-dialog,dialog.customer-tracking-dialog').forEach(el => mark(el,'gf-dialog'));
    nodes(root,'.gf-dropdown').forEach(el => {
      const menu = Array.from(el.children).find(child => child.tagName !== 'SUMMARY');
      if(menu) menu.dataset.gfMenu = '';
    });
    nodes(root,'#customerPagination,#depositPagination,#fleetPagination,.db-pagination-v71').forEach(el => mark(el,'gf-pagination'));
    nodes(root,'.nav-item[onclick]:not(button),.dash-kpi-click[onclick]:not(button)').forEach(el => {
      if(!el.hasAttribute('tabindex')) el.setAttribute('tabindex','0');
      if(!el.hasAttribute('role')) el.setAttribute('role','button');
      if(!el._gfKeyboardBound){
        el.addEventListener('keydown', event => {
          if(event.target !== el || !['Enter',' '].includes(event.key)) return;
          event.preventDefault(); el.click();
        });
        el._gfKeyboardBound = true;
      }
    });
    nodes(root,NAV).forEach(el => {
      const current = el.classList.contains('active');
      if(current && el.getAttribute('aria-current') !== 'page') el.setAttribute('aria-current','page');
      if(!current && el.getAttribute('aria-current') === 'page') el.removeAttribute('aria-current');
    });
  }
  function breakpoints(){
    const styles = global.getComputedStyle && doc ? global.getComputedStyle(doc.documentElement) : null;
    const values = {};
    ['sm','md','lg','xl'].forEach(key => values[key] = styles ? parseFloat(styles.getPropertyValue('--gf-breakpoint-'+key)) : NaN);
    return values;
  }
  function createButton(label, options){
    options = options || {};
    const el = doc.createElement('button');
    el.type = ['button','submit','reset'].includes(options.type) ? options.type : 'button';
    el.className = 'gf-button';
    el.dataset.variant = VARIANTS.has(options.variant) ? options.variant : 'secondary';
    el.textContent = String(label || '');
    if(options.disabled) el.disabled = true;
    return el;
  }
  function createBadge(label,status){
    const el = doc.createElement('span'); el.className = 'gf-badge';
    el.dataset.status = STATES.has(status) ? status : 'neutral'; el.textContent = String(label || ''); return el;
  }
  function createEmptyState(options){
    options = options || {}; const el = doc.createElement('div'); el.className = 'gf-empty';
    const title = doc.createElement('h2'); title.textContent = String(options.title || 'Nessun risultato'); el.appendChild(title);
    if(options.description){ const p = doc.createElement('p'); p.textContent = String(options.description); el.appendChild(p); }
    return el;
  }
  function createLoading(label){
    const el = doc.createElement('div'); el.className = 'gf-loading'; el.setAttribute('role','status');
    el.textContent = String(label || 'Caricamento in corso…'); return el;
  }
  function pageHeader(options){
    options = options || {}; const el = doc.createElement('header'); el.className = 'gf-page-header';
    const content = doc.createElement('div'); const title = doc.createElement('h1'); title.textContent = String(options.title || '');
    content.appendChild(title);
    if(options.description){const p = doc.createElement('p'); p.textContent = String(options.description); content.appendChild(p);}
    el.appendChild(content); if(options.action && options.action.nodeType === 1) el.appendChild(options.action); return el;
  }
  function announce(message,kind){
    let el = doc.getElementById('gfDesignAnnouncement');
    if(!el){el = doc.createElement('div'); el.id = 'gfDesignAnnouncement'; el.className = 'gf-toast gf-alert'; el.setAttribute('role','status'); el.setAttribute('aria-live','polite'); doc.body.appendChild(el);}
    el.dataset.status = STATES.has(kind) ? kind : 'info'; el.textContent = String(message); el.hidden = false;
    if(el._gfTimer) global.clearTimeout(el._gfTimer);
    el._gfTimer = global.setTimeout(() => { el.hidden = true; },5000); return el;
  }
  global.GFDesignSystem = Object.freeze({enhance,breakpoints,announce,createButton,createBadge,createEmptyState,createLoading,pageHeader});
  if(!doc) return;

  // Icone lineari coerenti con la sidebar del riferimento HTML.
  // Intervento esclusivamente grafico sui pulsanti di navigazione esistenti.
  const outlineIcons = {
    dashboard:"M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z",
    company:"M4 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17 M15 9h4a1 1 0 0 1 1 1v11 M3 21h18 M8 7h3 M8 11h3 M8 15h3",
    giro:"M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M16 3v4 M8 3v4 M4 11h16",
    "dashboard-scheduled":"M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M16 3v4 M8 3v4 M4 11h16",
    ordini:"M9 4h6v3H9z M7 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1 M9 12h6 M9 16h6",
    clienti:"M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1 M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M21 20v-1a4 4 0 0 0-3-3.9 M16 4.1a3.5 3.5 0 0 1 0 6.8",
    collaboratori:"M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21a8 8 0 0 1 16 0",
    agenti:"M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21a8 8 0 0 1 16 0",
    report:"M3 3v18h18 M7 15l4-4 3 3 5-6",
    depositi:"M3 10l9-6 9 6v10H3z M8 20v-6h8v6",
    mezzi:"M2 6h11v10H2z M13 9h5l3 3v4h-8z M6.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z M17.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
    autisti:"M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M5 16h4 M14 10h5 M14 14h5 M7 11.5a1.5 1.5 0 1 0 0-.01",
    storico:"M3 12a9 9 0 1 0 3-6.7 M3 4v5h5 M12 7v5l3 2",
    "chat-autisti":"M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z",
    supporto:"M4 14v-2a8 8 0 0 1 16 0v2 M4 14h3v5H5a1 1 0 0 1-1-1z M20 14h-3v5h2a1 1 0 0 0 1-1z",
    settings:"M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1L7 17 M17 7l2.1-2.1"
  };
  function syncReferenceSidebarIcons(){
    doc.querySelectorAll('body[data-gf-surface="workspace"] #app .nav-item[data-tab]').forEach(item=>{
      const d=outlineIcons[item.dataset.tab];
      const svg=item.querySelector('.nav-svg svg');
      if(!d || !svg || svg.dataset.gfRefIcon==='true') return;
      svg.setAttribute('viewBox','0 0 24 24');
      svg.setAttribute('aria-hidden','true');
      svg.style.fill='none';
      svg.style.stroke='currentColor';
      svg.style.strokeWidth='1.8';
      svg.style.strokeLinecap='round';
      svg.style.strokeLinejoin='round';
      svg.innerHTML='<path d="'+d+'"/>';
      svg.dataset.gfRefIcon='true';
    });
  }

  function start(){
    syncReferenceSidebarIcons();
    enhance(doc);
    let pending = false;
    if(global.MutationObserver){
      const observer = new global.MutationObserver(() => {
        if(pending) return; pending = true;
        const schedule = global.requestAnimationFrame || (callback => global.setTimeout(callback,0));
        schedule(() => { pending = false; enhance(doc); });
      });
      observer.observe(doc.body,{childList:true,subtree:true,attributes:true,attributeFilter:['class','data-state']});
    }
  }
  if(doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})(typeof window !== 'undefined' ? window : globalThis);
