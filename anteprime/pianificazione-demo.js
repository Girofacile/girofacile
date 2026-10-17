/* Anteprime Pianificazione giro · solo dimostrazione.
   Nessuna chiamata all'app, nessun salvataggio: i dati sono di esempio.
   Gestisce: un mezzo / più mezzi, prezzo automatico / manuale, passaggi (variante B),
   schede (variante C), finestra delle specifiche consegna, controllo "Cosa manca?". */
(function () {
  'use strict';
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // Un mezzo / più mezzi.
  function syncMode() {
    const fleet = $('input[name="demoMode"][value="fleet"]')?.checked;
    $$('[data-demo-single]').forEach(el => { el.hidden = !!fleet; });
    $$('[data-demo-fleet]').forEach(el => { el.hidden = !fleet; });
    $$('[data-demo-mode-label]').forEach(el => { el.textContent = fleet ? 'Più mezzi · suddivisione automatica' : 'Un solo mezzo'; });
    // Card di scelta: quella selezionata usa la variante "info" della card e l'icona colorata.
    $$('[data-demo-mode-card]').forEach(card => {
      const on = !!$('input[name="demoMode"]', card)?.checked;
      if (on) card.dataset.variant = 'info'; else delete card.dataset.variant;
      const icon = $('[data-demo-mode-icon]', card);
      if (icon) { if (on) delete icon.dataset.tone; else icon.dataset.tone = 'neutral'; }
    });
    check();
  }

  // Prezzo carburante automatico / manuale.
  function syncPrice() {
    const manual = $('input[name="demoPrice"][value="manual"]')?.checked;
    $$('[data-demo-price-auto]').forEach(el => { el.hidden = !!manual; });
    $$('[data-demo-price-manual]').forEach(el => { el.hidden = !manual; });
    $$('[data-demo-price-label]').forEach(el => {
      el.textContent = manual ? (String($('#demoFuelManual')?.value || '—').replace('.', ',') + ' €/L · manuale') : '1,689 €/L · automatico';
    });
  }

  // "Cosa manca?": campi indispensabili prima del calcolo.
  const REQUIRED = [
    ['#demoDate', 'Data'], ['#demoStart', 'Orario di partenza'], ['#demoDeposit', 'Deposito'],
    ['#demoVehicle', 'Mezzo', 'single'], ['#demoDriver', 'Autista', 'single']
  ];
  function check() {
    const fleet = $('input[name="demoMode"][value="fleet"]')?.checked;
    const missing = REQUIRED.filter(([sel, , mode]) => {
      if (mode === 'single' && fleet) return false;
      const field = $(sel);
      return field && !field.value;
    }).map(([, label]) => label);
    $$('[data-demo-checklist]').forEach(list => {
      list.innerHTML = '';
      const items = REQUIRED.filter(([, , mode]) => !(mode === 'single' && fleet)).map(([, label]) => label);
      if (fleet) items.push('Mezzi e autisti');
      items.forEach(label => {
        const badge = document.createElement('span');
        const ok = !missing.includes(label);
        badge.className = 'gf-badge';
        badge.dataset.status = ok ? 'success' : 'warning';
        badge.textContent = (ok ? '✓ ' : '! ') + label;
        list.appendChild(badge);
      });
    });
    $$('[data-demo-missing]').forEach(el => {
      el.textContent = missing.length ? 'Mancano: ' + missing.join(', ') + '.' : 'Tutto pronto: puoi calcolare il percorso.';
    });
    $$('[data-demo-calc]').forEach(btn => { btn.disabled = missing.length > 0; });
    $$('[data-demo-section-status]').forEach(el => {
      const fields = (el.dataset.demoSectionStatus || '').split(',').filter(Boolean);
      const empty = fields.some(sel => { const f = $(sel); return f && !f.closest('[hidden]') && !f.value; });
      el.dataset.status = empty ? 'warning' : 'success';
      el.textContent = empty ? 'Da completare' : 'Completo';
    });
  }

  // Passaggi (variante B).
  function showStep(index) {
    const panels = $$('[data-demo-step]');
    if (!panels.length) return;
    const max = panels.length - 1;
    const current = Math.max(0, Math.min(max, index));
    panels.forEach((panel, i) => { panel.hidden = i !== current; });
    $$('.gf-steps .gf-step').forEach((step, i) => {
      step.classList.toggle('is-done', i < current);
      if (i === current) step.setAttribute('aria-current', 'step'); else step.removeAttribute('aria-current');
    });
    document.body.dataset.demoCurrent = String(current);
    const prev = $('[data-demo-prev]'), next = $('[data-demo-next]');
    if (prev) prev.disabled = current === 0;
    if (next) next.hidden = current === max;
  }

  // Schede (variante C).
  function selectTab(tab) {
    const list = tab.closest('[role="tablist"]');
    $$('[role="tab"]', list).forEach(t => {
      const on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      const panel = document.getElementById(t.getAttribute('aria-controls'));
      if (panel) panel.hidden = !on;
    });
  }

  // Finestra delle specifiche consegna.
  function openSpecs(button) {
    const overlay = $('#demoSpecs');
    if (!overlay) return;
    const name = button.dataset.demoSpecs || 'Consegna';
    $('#demoSpecsTitle').textContent = 'Specifiche · ' + name;
    overlay.hidden = false;
    overlay._opener = button;
    $('#demoSpecs input, #demoSpecs select')?.focus();
  }
  function closeSpecs() {
    const overlay = $('#demoSpecs');
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    overlay._opener?.focus();
  }

  // Avviso di prova (nessun calcolo reale).
  function toast(text) {
    let box = $('[data-demo-toast]');
    if (!box) {
      box = document.createElement('div');
      box.className = 'gf-toast';
      box.setAttribute('role', 'status');
      box.dataset.demoToast = '';
      document.body.appendChild(box);
    }
    box.textContent = text;
    box.hidden = false;
    clearTimeout(box._timer);
    box._timer = setTimeout(() => { box.hidden = true; }, 3200);
  }

  // Nome automatico del giro: data · autista · zona più frequente tra le fermate.
  // Non si imposta in pianificazione: si potrà cambiare dopo il calcolo, nell'anteprima del giro.
  const ZONE = 'Milano'; // comune più frequente tra le fermate di esempio (5 su 7)
  function optionName(sel) {
    const s = $(sel);
    return s && s.value ? s.options[s.selectedIndex].text.split(' · ')[0] : '';
  }
  function syncAutoName() {
    const value = $('#demoDate')?.value;
    const date = value ? new Date(value + 'T12:00:00') : null;
    const short = date ? date.toLocaleDateString('it-IT', { weekday: 'short' }).replace('.', '') : '';
    const day = date ? short.charAt(0).toUpperCase() + short.slice(1) + ' ' + date.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) : 'Data da scegliere';
    const long = date ? date.toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' }) : 'data da scegliere';
    const fleet = $('input[name="demoMode"][value="fleet"]')?.checked;
    $$('[data-demo-auto-kicker]').forEach(el => { el.textContent = fleet ? 'Nuovi giri · ' + long + ' · 2 mezzi' : 'Nuovo giro · ' + long; });
    $$('[data-demo-auto-name]').forEach(el => {
      if (fleet) {
        const names = ['#aFleetDriver1', '#aFleetDriver2'].map(optionName).filter(Boolean);
        el.textContent = names.map(n => day + ' · ' + n).join('  /  ');
      } else {
        el.textContent = day + ' · ' + (optionName('#demoDriver') || optionName('#demoVehicle') || 'autista da scegliere') + ' · ' + ZONE;
      }
    });
    $$('[data-demo-auto-hint]').forEach(el => {
      el.textContent = fleet
        ? 'Un nome per ogni giro: data · autista · zona, assegnata dopo la suddivisione delle fermate. Potrai cambiarli nella revisione dei giri.'
        : 'Nome automatico: data · autista · zona più frequente tra le fermate. Potrai cambiarlo dopo il calcolo, nell\'anteprima del giro.';
    });
  }

  // Nome del giro: titolo ben visibile, modificabile sul posto.
  function toggleRename(show) {
    const field = $('[data-demo-rename-field]');
    if (!field) return;
    field.hidden = !show;
    $$('[data-demo-rename]').forEach(b => { b.hidden = show; });
    if (show) { const input = $('input', field); input.value = $('[data-demo-route-name]').textContent; input.focus(); input.select(); }
  }
  function applyRename() {
    const input = $('[data-demo-rename-field] input');
    if (input && input.value.trim()) $$('[data-demo-route-name]').forEach(el => { el.textContent = input.value.trim(); });
    toggleRename(false);
  }

  // Filtri delle fermate (ZTL, sponda, fascia oraria, da verificare).
  function filterStops(chip) {
    const value = chip.dataset.demoFilter;
    $$('[data-demo-filter]').forEach(c => c.setAttribute('aria-pressed', String(c === chip)));
    $$('[data-demo-tags]').forEach(item => {
      item.hidden = value !== 'all' && !item.dataset.demoTags.split(' ').includes(value);
    });
  }

  // Autista e mezzo scelti, riportati nel riquadro "equipaggio".
  function syncCrew() {
    const text = sel => { const s = $(sel); return s && s.value ? s.options[s.selectedIndex].text.split(' · ')[0] : 'Da scegliere'; };
    $$('[data-demo-crew-driver]').forEach(el => { el.textContent = text('#demoDriver'); });
    $$('[data-demo-crew-vehicle]').forEach(el => { el.textContent = text('#demoVehicle'); });
  }

  document.addEventListener('change', event => {
    const t = event.target;
    if (t.id === 'demoDriver' || t.id === 'demoVehicle') syncCrew();
    syncAutoName();
    if (t.name === 'demoMode') syncMode();
    if (t.name === 'demoPrice') syncPrice();
    if (t.id === 'demoFuelManual') syncPrice();
    check();
  });
  document.addEventListener('input', event => { if (event.target.matches('input,select')) { check(); syncAutoName(); } });
  document.addEventListener('click', event => {
    const t = event.target.closest('button,[role="tab"]');
    if (!t) { if (event.target.id === 'demoSpecs') closeSpecs(); return; }
    if (t.matches('[role="tab"]')) selectTab(t);
    if (t.matches('[data-demo-next]')) showStep(Number(document.body.dataset.demoCurrent || 0) + 1);
    if (t.matches('[data-demo-prev]')) showStep(Number(document.body.dataset.demoCurrent || 0) - 1);
    if (t.matches('[data-demo-goto]')) showStep(Number(t.dataset.demoGoto));
    if (t.matches('[data-demo-specs]')) openSpecs(t);
    if (t.matches('[data-demo-close]')) closeSpecs();
    if (t.matches('[data-demo-calc]')) toast('Anteprima: qui partirebbe il calcolo del percorso. Nessun dato viene salvato.');
    if (t.matches('[data-demo-toast-text]')) toast(t.dataset.demoToastText);
    if (t.matches('[data-demo-rename]')) toggleRename(true);
    if (t.matches('[data-demo-rename-save]')) applyRename();
    if (t.matches('[data-demo-rename-cancel]')) toggleRename(false);
    if (t.matches('[data-demo-filter]')) filterStops(t);
    if (t.matches('[data-demo-toggle]')) {
      // Apre/chiude un'area (es. la tabella di tutte le fermate).
      const area = document.getElementById(t.getAttribute('aria-controls'));
      const open = t.getAttribute('aria-expanded') !== 'true';
      if (area) area.hidden = !open;
      t.setAttribute('aria-expanded', String(open));
      $('[data-demo-toggle-text]', t).textContent = open ? t.dataset.demoClose : t.dataset.demoOpen;
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.closest?.('[data-demo-rename-field]')) applyRename();
    if (event.key === 'Escape') { closeSpecs(); toggleRename(false); }
    const tab = event.target.closest?.('[role="tab"]');
    if (tab && (event.key === 'ArrowRight' || event.key === 'ArrowLeft')) {
      const tabs = $$('[role="tab"]', tab.closest('[role="tablist"]'));
      const next = tabs[(tabs.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length];
      selectTab(next); next.focus();
    }
  });
  document.addEventListener('DOMContentLoaded', () => { syncMode(); syncPrice(); syncCrew(); syncAutoName(); showStep(0); check(); });
})();
