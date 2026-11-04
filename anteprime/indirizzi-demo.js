/* Anteprime «Controlla gli indirizzi» · solo dimostrazione.
   Nessuna chiamata all'app né a Google: i dati sono di esempio e la verifica è simulata
   (un indirizzo corretto con CAP a 5 cifre risulta verificato).
   Ogni variante dichiara i propri modelli <template data-demo-template="…">: questo script
   li riempie con i dati e gestisce le azioni comuni (usa, verifica, forza, escludi). */
(function () {
  'use strict';
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const ROWS = [
    { id: '1233', number: 'TEST-1233', name: 'Salumeria Da Gennaro',
      written: 'Via Nazionale, 100, 80013 Casalnuovo di Napoli NA',
      found: 'Via Nazionale, 100, 80013 Casalnuovo di Napoli NA',
      reason: 'Civico non trovato', tone: 'warning', safe: true, lat: 40.9086, lon: 14.3459,
      hint: 'Google ha trovato la via ma non il civico: la posizione è a metà strada.' },
    { id: '1238', number: 'TEST-1238', name: 'Panificio Due Sicilie',
      written: 'Via Roma 12, Pomigliano',
      found: "Via Roma, 12, 80038 Pomigliano d'Arco NA",
      reason: 'Manca il CAP', tone: 'warning', safe: true, lat: 40.9097, lon: 14.3826,
      hint: 'Nell’indirizzo mancano CAP e provincia: Google li ha completati.' },
    { id: '1241', number: 'TEST-1241', name: 'Bar Sport Pollena',
      written: 'Corso Italia 45, 80040 Pollena',
      found: 'Corso Italia, 45, 80040 Pollena Trocchia NA',
      reason: 'Comune incompleto', tone: 'warning', safe: true, lat: 40.8547, lon: 14.3769,
      hint: 'Il comune scritto è incompleto: il CAP corrisponde a Pollena Trocchia.' },
    { id: '1244', number: 'TEST-1244', name: 'Pizzeria Sole Mio',
      written: 'Via Nazionale 95, 80031 Brusciano NA',
      found: 'Via Nazionale, 95, 08028 Orosei NU',
      reason: 'Altro comune', tone: 'danger', safe: false, lat: 40.9223, lon: 14.4237,
      hint: 'Google propone la stessa via a Orosei (NU), non a Brusciano: correggi l’indirizzo o metti lo spillo sulla mappa.' },
    { id: '1246', number: 'TEST-1246', name: 'Ortofrutta Esposito',
      written: 'Via Garibaldi, 80034 Marigliano',
      found: 'Via Giuseppe Garibaldi, 80034 Marigliano NA',
      reason: 'Manca il civico', tone: 'warning', safe: true, lat: 40.9244, lon: 14.4575,
      hint: 'Senza numero civico la posizione è a metà via: aggiungilo se lo conosci.' },
    { id: '1249', number: 'TEST-1249', name: 'Tabacchi Pezzalunga',
      written: 'Contrada Pezzalunga snc, Acerra',
      found: '',
      reason: 'Non trovato', tone: 'danger', safe: false, lat: 40.9455, lon: 14.3720,
      hint: 'Google non ha trovato niente: correggi l’indirizzo o metti lo spillo sulla mappa.' },
  ];
  const TOTAL = ROWS.length;
  const SELECTED = 15;
  const byId = Object.fromEntries(ROWS.map(row => [row.id, row]));
  const outcome = {}; // id -> {label, tone}

  /* ---------- Modelli ---------- */
  function fill(fragment, row) {
    $$('[data-demo-if]', fragment).forEach(node => {
      const key = node.dataset.demoIf, negate = key.startsWith('!');
      const value = !!row[negate ? key.slice(1) : key];
      if (negate ? value : !value) node.remove();
    });
    $$('[data-demo-field]', fragment).forEach(node => { node.textContent = row[node.dataset.demoField] || ''; });
    $$('[data-demo-value]', fragment).forEach(node => { node.value = row[node.dataset.demoValue] || ''; });
    $$('[data-demo-tone]', fragment).forEach(node => { node.dataset.status = row.tone; });
    $$('[data-demo-id]', fragment).forEach(node => { node.dataset.demoId = row.id; });
    ['demoRow', 'demoItem', 'demoEdit'].forEach(key => {
      const attr = 'data-' + key.replace(/[A-Z]/g, c => '-' + c.toLowerCase());
      $$(`[${attr}]`, fragment).forEach(node => { node.dataset[key] = row.id; });
    });
  }
  function render() {
    $$('template[data-demo-template]').forEach(template => {
      const target = $(`[data-demo-list="${template.dataset.demoTemplate}"]`);
      if (!target) return;
      ROWS.forEach(row => {
        const fragment = template.content.cloneNode(true);
        fill(fragment, row);
        target.appendChild(fragment);
      });
    });
  }

  /* ---------- Mappe (Leaflet, come nella pagina reale) ---------- */
  let leaflet = null;
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    if (leaflet) return leaflet;
    leaflet = new Promise((resolve, reject) => {
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(css);
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = resolve; script.onerror = reject;
      document.head.appendChild(script);
    });
    return leaflet;
  }
  const maps = new Map();
  async function showMap(id) {
    const holder = $(`[data-demo-map][data-demo-id="${id}"]`);
    if (!holder) return;
    if (maps.has(id)) { requestAnimationFrame(() => maps.get(id).invalidateSize()); return; }
    try { await loadLeaflet(); } catch (error) { holder.textContent = 'Mappa non disponibile in anteprima.'; return; }
    const row = byId[id];
    const map = L.map(holder, { scrollWheelZoom: false }).setView([row.lat, row.lon], 16);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    const marker = L.marker([row.lat, row.lon], { draggable: true }).addTo(map);
    map.on('click', event => marker.setLatLng(event.latlng));
    maps.set(id, map);
    requestAnimationFrame(() => map.invalidateSize());
  }

  /* ---------- Stato e avanzamento ---------- */
  function left() { return ROWS.filter(row => !outcome[row.id]); }
  function excluded() { return ROWS.filter(row => outcome[row.id]?.excluded).length; }
  function step5(value) { return Math.max(0, Math.min(100, Math.round(value / 5) * 5)); }
  function update() {
    const remaining = left().length, done = TOTAL - remaining;
    $$('[data-demo-done-count]').forEach(n => { n.textContent = `${done} su ${TOTAL}`; });
    $$('[data-demo-left-count]').forEach(n => {
      n.textContent = remaining ? `${remaining} da sistemare` : 'Tutto sistemato';
    });
    $$('[data-demo-progress]').forEach(n => { n.dataset.gfWidth = String(step5(done / TOTAL * 100)); });
    const safe = left().filter(row => row.safe).length;
    $$('[data-demo-safe-count]').forEach(n => { n.textContent = String(safe); });
    $$('[data-demo-bulk]').forEach(n => { n.hidden = safe === 0; });
    const orders = SELECTED - excluded();
    $$('[data-demo-continue]').forEach(button => {
      button.disabled = remaining > 0 || orders === 0;
      button.textContent = remaining ? `Continua alla pianificazione` : `Continua con ${orders} ordini`;
    });
    $$('[data-demo-message]').forEach(n => {
      n.textContent = remaining
        ? `${remaining} indirizzi su ${SELECTED} ordini selezionati vanno sistemati prima di pianificare.`
        : 'Tutti gli indirizzi sono sistemati. Puoi continuare alla pianificazione.';
    });
    $$('[data-demo-done-section]').forEach(n => { n.hidden = done === 0; });
  }
  function addDone(row) {
    const list = $('[data-demo-list="done"]');
    if (!list) return;
    const item = document.createElement('li');
    item.className = 'gf-list-item';
    item.dataset.demoDoneId = row.id;
    const main = document.createElement('div'); main.className = 'gf-list-item__main';
    const title = document.createElement('strong'); title.textContent = `${row.number} · ${row.name}`;
    const detail = document.createElement('small'); detail.textContent = outcome[row.id].detail;
    main.append(title, detail);
    const badge = document.createElement('span');
    badge.className = 'gf-badge'; badge.dataset.status = outcome[row.id].tone; badge.dataset.dot = '';
    badge.textContent = outcome[row.id].label;
    const undo = document.createElement('button');
    undo.type = 'button'; undo.className = 'gf-button'; undo.dataset.variant = 'link'; undo.dataset.size = 'sm';
    undo.dataset.demoAction = 'undo'; undo.dataset.demoId = row.id; undo.textContent = 'Annulla';
    const side = document.createElement('div'); side.className = 'gf-cluster'; side.append(badge, undo);
    item.append(main, side);
    list.prepend(item);
  }
  function resolve(id, result) {
    const row = byId[id];
    if (!row || outcome[id]) return;
    outcome[id] = result;
    $$(`[data-demo-row="${id}"], [data-demo-edit="${id}"]`).forEach(n => { n.hidden = true; });
    $$(`[data-demo-item="${id}"]`).forEach(item => {
      const badge = $('.gf-badge', item);
      if (badge) { badge.dataset.status = result.tone; badge.textContent = result.label; }
    });
    addDone(row);
    update();
    document.dispatchEvent(new CustomEvent('demo:resolved', { detail: { id } }));
  }
  function undo(id) {
    delete outcome[id];
    $$(`[data-demo-row="${id}"]`).forEach(n => { n.hidden = false; });
    $$(`[data-demo-item="${id}"]`).forEach(item => {
      const badge = $('.gf-badge', item);
      if (badge) { badge.dataset.status = byId[id].tone; badge.textContent = byId[id].reason; }
    });
    $$(`[data-demo-done-id="${id}"]`).forEach(n => n.remove());
    update();
    document.dispatchEvent(new CustomEvent('demo:select', { detail: { id } }));
  }

  /* ---------- Azioni ---------- */
  function say(id, text) {
    $$(`[data-demo-note][data-demo-id="${id}"]`).forEach(n => { n.textContent = text; n.hidden = !text; });
  }
  function verify(id) {
    const input = $(`[data-demo-input][data-demo-id="${id}"]`);
    const value = (input?.value || '').trim();
    if (!/(^|\D)\d{5}(\D|$)/.test(value)) {
      say(id, 'Ancora da verificare: aggiungi il CAP (5 cifre) o il comune completo, oppure metti lo spillo sulla mappa.');
      return;
    }
    resolve(id, { label: 'Verificato', tone: 'success', detail: `Corretto in: ${value}` });
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-demo-action]');
    if (!button) return;
    const id = button.dataset.demoId || button.closest('[data-demo-id]')?.dataset.demoId;
    const row = byId[id];
    switch (button.dataset.demoAction) {
      case 'use':
        resolve(id, { label: 'Proposta usata', tone: 'success', detail: row.found });
        break;
      case 'verify':
        verify(id);
        break;
      case 'force': {
        const wrap = $(`[data-demo-map-wrap][data-demo-id="${id}"]`);
        if (wrap) { wrap.hidden = !wrap.hidden; if (!wrap.hidden) showMap(id); }
        button.textContent = wrap && !wrap.hidden ? 'Chiudi la mappa' : 'Forza posizione sulla mappa';
        break;
      }
      case 'pin':
        resolve(id, { label: 'Posizione forzata', tone: 'info', detail: `${row.written} · spillo confermato a mano` });
        break;
      case 'exclude':
        resolve(id, { label: 'Escluso', tone: 'neutral', detail: 'Tolto da questa pianificazione', excluded: true });
        break;
      case 'accept-safe':
        left().filter(r => r.safe).forEach(r => resolve(r.id, { label: 'Proposta usata', tone: 'success', detail: r.found }));
        break;
      case 'undo':
        undo(id);
        break;
      case 'edit': {
        const edit = $(`[data-demo-edit="${id}"]`);
        if (edit) { edit.hidden = !edit.hidden; if (!edit.hidden) showMap(id); }
        break;
      }
      case 'select':
        document.dispatchEvent(new CustomEvent('demo:select', { detail: { id } }));
        break;
      case 'close':
      case 'continue':
        $$('[data-demo-message]').forEach(n => {
          n.textContent = button.dataset.demoAction === 'close'
            ? 'Anteprima: la finestra si chiuderebbe e la selezione resterebbe com’è.'
            : 'Anteprima: si aprirebbe la pianificazione del giro con gli ordini rimasti.';
        });
        break;
    }
  });
  document.addEventListener('submit', event => {
    const form = event.target.closest('[data-demo-verify]');
    if (!form) return;
    event.preventDefault();
    verify(form.dataset.demoId);
  });

  /* ---------- Variante elenco e dettaglio: una scheda alla volta ---------- */
  document.addEventListener('demo:select', event => {
    const id = event.detail.id;
    if (!$('[data-demo-item]')) return;
    $$('[data-demo-item]').forEach(item => item.setAttribute('aria-current', String(item.dataset.demoItem === id)));
    $$('[data-demo-row]').forEach(panel => { panel.hidden = panel.dataset.demoRow !== id || !!outcome[panel.dataset.demoRow]; });
    $$('[data-demo-empty]').forEach(n => { n.hidden = !!left().length; });
    if (!outcome[id]) showMap(id);
  });
  document.addEventListener('demo:resolved', () => {
    if (!$('[data-demo-item]')) return;
    const next = left()[0];
    if (next) document.dispatchEvent(new CustomEvent('demo:select', { detail: { id: next.id } }));
    else {
      $$('[data-demo-item]').forEach(item => item.setAttribute('aria-current', 'false'));
      $$('[data-demo-empty]').forEach(n => { n.hidden = false; });
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    render();
    update();
    const dialog = $('dialog[data-demo-dialog]');
    if (dialog && !dialog.open) dialog.showModal();
    if ($('[data-demo-item]')) document.dispatchEvent(new CustomEvent('demo:select', { detail: { id: ROWS[0].id } }));
  });
})();
