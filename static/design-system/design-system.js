/* Presentation only. No requests, persistence, routing, permissions or business state. */
(function(global){
  'use strict';
  const doc = global.document;
  const BUTTONS = '.dash-link-btn,.deposit-delete-danger,.fleet-edit,.fleet-delete,.driver-delete,.driver-menu summary,.customer-tracking-trigger,.fleet-create,.fleet-views button,.driver-view,.completed-tools button,.live-design-table-actions button,.live-design-actions>button,.live-design-actions>a,.preview-program,.plan-billing-btn-v875,.payment-add-v876,.customer-view-controls button,.deposit-view-controls button,.gf-routing-summary button,.btn-login-submit,.btn-start,.btn-view,.btn-note,.btn-note-small,.btn-signature-open,.btn-clear-signature,.mini-btn,.fab,.popup-confirm,.popup-cancel,.maps-btn,.btn-danger-outline,.btn-login,.btn-cta-nav,.btn-hero,.btn-hero-ghost,.btn-plan,.btn-white,.btn-ghost-white,.lm-btn,.gf-button,.btn,.btn-primary,.btn-secondary,.btn-light,.btn-ghost,.btn-danger,.btn-danger-soft,.customer-delete-danger,.btn-navigate,.btn-done,.btn-missed,.btn-confirm,.customer-row-actions button,.deposit-row-actions button,.fleet-card-actions button,.row-actions button,.driver-actions button,.gf-pagination button,#customerPagination button,#depositPagination button,#fleetPagination button';
  const NAV = '.nav-item,.bnav-btn,.bnav,.bnav-item,.bnav-item button,.admin-mobile-bottom-nav-v62 button';
  const LABEL_TABLES = '.customer-table,.deposit-table,.fleet-table,.drivers-table,#tab-autisti .tableWrap table,#tab-agenti table,#tab-report .tableWrap table,#tab-storico .tableWrap table,#tab-dashboard-scheduled .dash-sub-table,#tab-dashboard-completed .dash-sub-table,body[data-gf-surface="agent"] .table-wrap table,body[data-gf-surface="admin"] .table-wrap table,table[data-gf-responsive="cards"]';
  const VARIANTS = new Set(['primary','secondary','ghost','danger','link']);
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
    // Solo i menu a tendina (<details>): il contenitore dei suggerimenti indirizzo non ha un menu da marcare.
    nodes(root,'details.gf-dropdown').forEach(el => {
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
  // Schermata di attesa a tutto schermo per le operazioni lunghe (approvata il 1° novembre 2026): logo GiroFacile
  // che si disegna, titolo e frasi passati dalla pagina (es. il numero di mezzi), barra senza percentuale.
  // Resta almeno minMs (2 secondi) anche se il calcolo finisce prima, poi quanto serve; dopo slowMs avvisa
  // che ci vuole più del solito. Il gestionale sotto diventa inert finché la schermata è aperta.
  // Uso: const wait=GFDesignSystem.showWait({title,messages,hint}); ... await wait.close();
  const WAIT_LOGO = '<svg class="gf-loader__art" viewBox="0 0 100 100" aria-hidden="true"><rect class="gf-anim-logo__bg" width="100" height="100" rx="22"/><g class="gf-anim-logo__mark"><path class="gf-anim-logo__stroke gf-anim-logo__arc" pathLength="1" d="M54 25A26 26 0 1 0 47 77"/><g><path class="gf-anim-logo__dash" d="M52.7 76.9A26 26 0 0 0 58 75.7"/><path class="gf-anim-logo__dash" d="M61.4 74.4A26 26 0 0 0 66 71.5"/><path class="gf-anim-logo__dash" d="M68.7 69.1A26 26 0 0 0 72.5 64"/></g><path class="gf-anim-logo__stroke gf-anim-logo__bar" pathLength="1" d="M54 52H75.5A1.5 1.5 0 0 1 77 53.5V58"/><g class="gf-anim-logo__ring"><circle cx="47" cy="77" r="5.6"/><circle cx="47" cy="77" r="2.5"/></g><g class="gf-anim-logo__pin"><path d="M66.5 17.5c-5 0-9 3.9-9 8.8 0 6.1 9 14.2 9 14.2s9-8.1 9-14.2c0-4.9-4-8.8-9-8.8z"/><circle cx="66.5" cy="26.4" r="3.3"/></g></g></svg>';
  const WAIT_SLOW = 'Ci vuole un po’ più del solito: stiamo ancora calcolando, non chiudere la pagina.';
  let activeWait = null;
  function showWait(options){
    options = options || {};
    if(activeWait) activeWait.dispose();
    const started = Date.now();
    const minMs = options.minMs == null ? 2000 : options.minMs, slowMs = options.slowMs == null ? 45000 : options.slowMs;
    const messages = (options.messages || []).filter(Boolean);
    const part = (tag, className, text) => { const node = doc.createElement(tag); node.className = className; if(text != null) node.textContent = text; return node; };
    const overlay = part('div','gf-wait'), card = part('div','gf-wait__card'), loader = part('div','gf-loader');
    loader.setAttribute('role','status');
    loader.setAttribute('aria-live','polite');
    loader.insertAdjacentHTML('afterbegin', WAIT_LOGO); // disegno fisso, nessun testo della pagina
    const title = part('p','gf-loader__title',options.title || 'Attendi qualche secondo');
    const message = part('p','gf-loader__message',messages[0] || '');
    const bar = part('div','gf-loader__bar'); bar.setAttribute('aria-hidden','true');
    const hint = part('p','gf-loader__hint',options.hint || 'Di solito bastano pochi secondi.');
    loader.append(title, message, bar, hint);
    card.append(loader);
    overlay.append(card);
    const shell = doc.querySelector('[data-gf-shell]');
    if(shell) shell.inert = true;
    doc.body.append(overlay);
    let index = 0;
    const rotate = messages.length > 1 ? global.setInterval(() => {
      message.setAttribute('data-fading','');
      global.setTimeout(() => { index = (index + 1) % messages.length; message.textContent = messages[index]; message.removeAttribute('data-fading'); }, 250);
    }, 2600) : null;
    const slow = global.setTimeout(() => { hint.textContent = options.slowHint || WAIT_SLOW; }, slowMs);
    const handle = {
      element: overlay,
      dispose(){
        if(rotate) global.clearInterval(rotate);
        global.clearTimeout(slow);
        overlay.remove();
        if(shell) shell.inert = false;
        if(activeWait === handle) activeWait = null;
      },
      close(){
        const remaining = Math.max(0, minMs - (Date.now() - started));
        return new Promise(resolve => global.setTimeout(() => { handle.dispose(); resolve(); }, remaining));
      }
    };
    activeWait = handle;
    return handle;
  }
  global.GFDesignSystem = Object.freeze({enhance,breakpoints,announce,createButton,createBadge,createEmptyState,createLoading,pageHeader,showWait});
  if(!doc) return;
  // Campi obbligatori vuoti: scritta rossa dentro il campo (.gf-field[data-invalid]) al posto del fumetto del browser.
  function fieldOf(control){ return control.closest ? control.closest('.gf-field') : null; }
  function markInvalid(event){
    const control = event.target, field = fieldOf(control);
    if(!field) return;
    event.preventDefault();
    let error = field.querySelector('.gf-field__error');
    if(!error){ error = doc.createElement('p'); error.className = 'gf-field__error'; error.dataset.gfAuto = ''; field.appendChild(error); }
    if(error.dataset.gfAuto !== undefined) error.textContent = control.validity.valueMissing ? 'Campo obbligatorio' : control.validationMessage;
    field.setAttribute('data-invalid','');
    const form = control.form || field.closest('[role="dialog"],dialog') || doc;
    if(form.querySelector(':invalid') === control) control.focus();
  }
  function clearInvalid(event){
    const field = fieldOf(event.target);
    if(field && field.hasAttribute('data-invalid') && event.target.checkValidity && event.target.checkValidity()) field.removeAttribute('data-invalid');
  }
  function start(){
    doc.addEventListener('invalid',markInvalid,true);
    doc.addEventListener('input',clearInvalid,true);
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
