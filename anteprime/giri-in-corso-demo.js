/* Anteprime «Giri in corso» · solo dimostrazione.
   Dati di esempio, nessuna chiamata all'app. Ogni variante dichiara il modello di un giro
   (<template data-demo-template="route">) e dove inserirlo (data-demo-list="route"); lo script
   riempie i campi, gestisce filtri e selezione e aggiorna il dettaglio sotto, uguale in tutte. */
(function () {
  'use strict';
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const ROUTES = [
    { id: 1, driver: 'Alessandro Paglietta', initials: 'AP', tone: '1', vehicle: 'Peugeot 2008 · GH 214 PL',
      name: 'Mer 4/11 · Torre Annunziata', done: 1, miss: 0, total: 5, eta: '13:27', planned: '13:27', delay: 0,
      next: 'Bar Pompei Scavi', nextAddress: 'Via Roma 78, Pompei', nextTime: '11:56',
      gps: 'none', messages: 0, km: '106,2 km', minutes: '174 min previsti', fuel: '€ 15,80' },
    { id: 2, driver: 'Marco Esposito', initials: 'ME', tone: '2', vehicle: 'Ford Transit · FT 552 KD',
      name: 'Mer 4/11 · Nola e Vesuviano', done: 6, miss: 1, total: 9, eta: '13:52', planned: '13:40', delay: 12,
      next: 'Pasticceria Del Corso', nextAddress: 'Corso Umberto I 2, Cicciano', nextTime: '12:31',
      gps: 'live', messages: 0, km: '84,7 km', minutes: '205 min previsti', fuel: '€ 13,10' },
    { id: 3, driver: 'Giuseppe Russo', initials: 'GR', tone: '3', vehicle: 'Fiat Ducato · EZ 908 TR',
      name: 'Mer 4/11 · Napoli centro', done: 3, miss: 0, total: 12, eta: '15:10', planned: '15:10', delay: 0,
      next: 'Salumeria San Carlo', nextAddress: 'Via Duomo 5, Napoli', nextTime: '12:24',
      gps: 'stale', messages: 2, km: '41,3 km', minutes: '238 min previsti', fuel: '€ 7,40' },
    { id: 4, driver: 'Luca Romano', initials: 'LR', tone: '4', vehicle: 'Iveco Daily · FX 482 KL',
      name: 'Mer 4/11 · Pozzuoli e Flegrei', done: 10, miss: 0, total: 11, eta: '12:40', planned: '12:40', delay: 0,
      next: 'Hotel Posillipo', nextAddress: 'Corso Trieste 49, Caserta', nextTime: '12:22',
      gps: 'live', messages: 0, km: '63,9 km', minutes: '190 min previsti', fuel: '€ 10,20' },
  ];
  const GPS = { live: ['GPS live', 'success'], stale: ['GPS fermo da 9 min', 'warning'], none: ['GPS non disponibile', 'neutral'] };
  const issue = r => r.miss > 0 || r.delay > 0;
  const gpsIssue = r => r.gps !== 'live';
  const step5 = v => String(Math.max(0, Math.min(100, Math.round(v / 5) * 5)));
  let selected = 1, filter = 'all';

  function values(r) {
    const status = issue(r) ? ['Da verificare', 'warning'] : ['In corso', 'info'];
    return {
      driver: r.driver, initials: r.initials, vehicle: r.vehicle, name: r.name,
      count: `${r.done}/${r.total}`, countLong: `${r.done} su ${r.total} consegne`,
      todo: `${r.total - r.done - r.miss} da fare`, eta: r.eta,
      etaNote: r.delay ? `+${r.delay} min sul previsto` : 'in orario',
      next: r.next, nextLine: `${r.next} · ${r.nextTime}`, nextAddress: r.nextAddress, nextTime: r.nextTime,
      status: status[0], gps: GPS[r.gps][0],
      miss: r.miss ? `${r.miss} mancata` : '', delay: r.delay ? `+${r.delay} min` : '',
      messages: r.messages ? `${r.messages} messaggi` : '',
      percent: `${Math.round(100 * (r.done + r.miss) / r.total)}%`,
    };
  }
  function fill(node, r) {
    const v = values(r);
    $$('[data-demo-field]', node).forEach(el => { el.textContent = v[el.dataset.demoField] || ''; });
    $$('[data-demo-if]', node).forEach(el => { if (!v[el.dataset.demoIf]) el.remove(); });
    $$('[data-demo-status]', node).forEach(el => { el.dataset.status = issue(r) ? 'warning' : 'info'; });
    $$('[data-demo-gps]', node).forEach(el => { el.dataset.status = GPS[r.gps][1]; });
    $$('[data-demo-tone]', node).forEach(el => { el.dataset.tone = r.tone; });
    $$('[data-demo-done]', node).forEach(el => { el.dataset.gfWidth = step5(100 * r.done / r.total); });
    $$('[data-demo-miss]', node).forEach(el => { el.dataset.gfWidth = step5(100 * r.miss / r.total); });
    $$('[data-demo-route]', node).forEach(el => { el.dataset.demoRoute = String(r.id); });
  }
  function visibleRoutes() {
    return ROUTES.filter(r => filter === 'issue' ? issue(r) : filter === 'gps' ? gpsIssue(r) : true);
  }
  function renderList() {
    const template = $('template[data-demo-template="route"]');
    const target = $('[data-demo-list="route"]');
    if (!template || !target) return;
    target.querySelectorAll('[data-demo-route]').forEach(n => { if (n.parentElement === target) n.remove(); });
    $$(':scope > :not(template)', target).forEach(n => n.remove());
    const list = visibleRoutes();
    list.forEach(r => {
      const fragment = template.content.cloneNode(true);
      fill(fragment, r);
      target.appendChild(fragment);
    });
    if (!list.length) {
      const empty = $('template[data-demo-template="empty"]');
      if (empty) target.appendChild(empty.content.cloneNode(true));
    }
    markSelected();
    counts();
  }
  function markSelected() {
    $$('[data-demo-route]').forEach(el => {
      const on = Number(el.dataset.demoRoute) === selected;
      if (el.matches('[data-demo-select-card]')) { if (on) el.dataset.variant = 'info'; else delete el.dataset.variant; }
      if (el.matches('[data-demo-select-current]')) el.setAttribute('aria-current', String(on));
      if (el.matches('[data-demo-select-button]')) {
        el.dataset.variant = on ? 'primary' : 'secondary';
        el.textContent = on ? 'Aperto sotto' : 'Apri';
        el.setAttribute('aria-pressed', String(on));
      }
    });
  }
  function counts() {
    const all = ROUTES.length, iss = ROUTES.filter(issue).length, gps = ROUTES.filter(gpsIssue).length;
    const done = ROUTES.reduce((s, r) => s + r.done, 0), total = ROUTES.reduce((s, r) => s + r.total, 0);
    const miss = ROUTES.reduce((s, r) => s + r.miss, 0), late = ROUTES.filter(r => r.delay > 0).length;
    const set = (key, text) => $$(`[data-demo-count="${key}"]`).forEach(n => { n.textContent = text; });
    set('all', String(all)); set('issue', String(iss)); set('gps', String(gps));
    set('delivered', `${done}/${total}`); set('miss', String(miss)); set('late', String(late));
    set('label-all', `Tutti (${all})`); set('label-issue', `Con mancate o ritardi (${iss})`); set('label-gps', `GPS da controllare (${gps})`);
    $$('[data-demo-filter]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.demoFilter === filter)));
  }
  function renderDetail() {
    const r = ROUTES.find(x => x.id === selected);
    const host = $('[data-demo-detail]');
    if (!r || !host) return;
    const v = values(r);
    $$('[data-demo-detail-field]', host).forEach(el => { el.textContent = ({
      title: `${r.name} · ${r.driver}`, progress: v.percent, progressNote: `${r.done + r.miss} su ${r.total} fermate gestite`,
      deliveries: v.count, deliveriesNote: `${r.miss} mancate · ${r.total - r.done - r.miss} da fare`,
      eta: r.eta, etaNote: r.delay ? `+${r.delay} min sul previsto` : 'ETA con traffico aggiornato',
      km: r.km, minutes: r.minutes, fuel: r.fuel, gps: GPS[r.gps][0],
    })[el.dataset.demoDetailField] || ''; });
    $$('[data-demo-detail-gps]', host).forEach(el => { el.dataset.status = GPS[r.gps][1]; });
  }

  document.addEventListener('click', event => {
    const pick = event.target.closest('[data-demo-pick]');
    if (pick) {
      selected = Number(pick.closest('[data-demo-route]')?.dataset.demoRoute || pick.dataset.demoRoute);
      markSelected(); renderDetail();
      return;
    }
    const button = event.target.closest('[data-demo-filter]');
    if (button) { filter = button.dataset.demoFilter; renderList(); }
  });
  document.addEventListener('DOMContentLoaded', () => { renderList(); renderDetail(); });
})();
