const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Tendina notifiche (variante A): righe con icona, titolo e ora; gruppi per giorno; «Segna tutte lette» in fondo.
function render(items, unread) {
  const core = fs.readFileSync('static/dashboard/js/core.js', 'utf8');
  const nodes = {notificationList:{innerHTML:''}, notificationSubtitle:{textContent:''}, notificationReadAll:{disabled:false}};
  const ctx = vm.createContext({document:{getElementById:id=>nodes[id]||null}, Date,
    esc:s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))});
  const start = core.indexOf('const GF_NOTIFICATION_ICONS');
  vm.runInContext(core.slice(start, core.indexOf('function showNotificationsDropdownV30(')).replace('function renderOrdersBadgeV30','function _unused'), ctx);
  vm.runInContext(core.slice(core.indexOf('function notificationTimeLabelV30('), core.indexOf('const GF_NOTIFICATION_ICONS')), ctx);
  ctx.notificationsCacheV30 = items;
  vm.runInContext('notificationsCacheV30 = this.notificationsCacheV30; renderNotificationsDropdownV30(' + unread + ')', ctx);
  return nodes;
}

test('notifications are grouped by day with coloured icons and one read-all button', () => {
  const now = new Date();
  const yesterday = new Date(now.getTime() - 86400000);
  const nodes = render([
    {id:1, type:'delivery_missed', title:'Consegna mancata', message:'Bar <Roma>: cliente assente', created_at:now.toISOString(), is_read:false, action_tab:'dashboard-in-progress', action_label:'Apri giro'},
    {id:2, type:'route_completed', title:'Giro completato', message:'12 consegnate', created_at:yesterday.toISOString(), is_read:true},
  ], 1);
  const html = nodes.notificationList.innerHTML;
  assert.match(html, /<p class="gf-kicker">Oggi<\/p>[^]*Consegna mancata[^]*<p class="gf-kicker">Ieri<\/p>[^]*Giro completato/);
  assert.match(html, /class="gf-stat-strip__icon" data-tone="5"/);
  assert.match(html, /<div class="gf-list-item" aria-current="true">/);
  assert.match(html, /Bar &lt;Roma&gt;/);
  assert.match(html, /openNotificationActionV30\(1, 'dashboard-in-progress'\)">Apri giro/);
  assert.equal((html.match(/Segna letta/g) || []).length, 1);
  assert.doesNotMatch(html, /[🔔✅⚠️📦]/u);
  assert.equal(nodes.notificationSubtitle.textContent, '1 da leggere');
  assert.equal(nodes.notificationReadAll.disabled, false);
  const empty = render([], 0);
  assert.match(empty.notificationList.innerHTML, /Nessuna notifica operativa/);
  assert.equal(empty.notificationSubtitle.textContent, 'Tutto letto');
  assert.equal(empty.notificationReadAll.disabled, true);
});
