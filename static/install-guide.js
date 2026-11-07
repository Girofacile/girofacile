/* «Aggiungi GiroFacile alla tua Home» (variante B): finestra all'apertura dell'app, una volta sola.
   iPhone: tre passaggi (Condividi → Aggiungi alla schermata Home → Aggiungi), Apple non permette un pulsante.
   Android: pulsante «Installa» del browser. Non compare se l'app è già installata; «Più tardi» la
   rimanda di qualche giorno, «Fatto» o l'installazione non la mostrano più. */
window.GFInstallGuide = (() => {
  'use strict';
  const KEY = 'gf-install-guide';
  const LATER_DAYS = 3;
  let prompt = null;   // evento del browser per installare (Android, Chrome)
  let pending = false; // l'app è pronta ma il browser non ha ancora proposto l'installazione

  const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } };
  const write = value => { try { localStorage.setItem(KEY, JSON.stringify(value)); } catch (e) { /* senza memoria si riproporrà */ } };
  const installed = () => window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true;
  const isIos = () => /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const snoozed = () => { const state = read(); return state.done || (state.later && Date.now() - state.later < LATER_DAYS * 864e5); };

  const ICON = {
    share: 'M12 3v12 M8 7l4-4 4 4 M5 11v9h14v-9', add: 'M4 4h16v16H4z M12 8v8 M8 12h8', check: 'M5 12l4 4 10-10',
    x: 'M6 6l12 12M18 6 6 18', download: 'M12 3v12 M7 10l5 5 5-5 M5 21h14',
    truck: 'M3 6h11v10H3z M14 10h4l3 3v3h-7 M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  };
  const svg = name => `<svg class="gf-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${ICON[name]}"/></svg>`;
  const STEPS = [['share', 'Tocca Condividi', 'Il quadrato con la freccia, nella barra di Safari'],
                 ['add', 'Aggiungi alla schermata Home', 'Scorri l’elenco se non la vedi subito'],
                 ['check', 'Tocca «Aggiungi»', 'L’icona GiroFacile compare sulla Home']];

  function close(overlay, state) {
    if (state) write(state);
    overlay.remove();
  }

  function open(appName) {
    if (document.querySelector('[data-install-guide]')) return;
    const ios = isIos();
    const overlay = document.createElement('div');
    overlay.className = 'gf-overlay';
    overlay.dataset.installGuide = ios ? 'ios' : 'android';
    const body = ios
      ? '<p class="gf-muted">Così la ritrovi come un’app: si apre a schermo intero e resti collegato.</p><ol class="gf-list">'
        + STEPS.map(([icon, title, hint], i) => `<li class="gf-list-item"><span class="gf-cluster"><span class="gf-avatar" data-tone="${i + 1}">${svg(icon)}</span><span class="gf-list-item__main"><strong>${i + 1}. ${title}</strong><small>${hint}</small></span></span></li>`).join('')
        + '</ol>'
      : `<div class="gf-cluster"><span class="gf-avatar" data-tone="1">${svg('truck')}</span><span class="gf-list-item__main"><strong>${appName}</strong><small>Si apre a schermo intero, anche con rete debole</small></span></div>`;
    overlay.innerHTML = `<div class="gf-modal" role="dialog" aria-modal="true" aria-labelledby="gfInstallTitle">
      <header class="gf-modal__header"><div><p class="gf-kicker">${ios ? 'Un minuto, una volta sola' : 'Un tocco, una volta sola'}</p><h2 class="gf-modal__title" id="gfInstallTitle">Aggiungi GiroFacile alla tua Home</h2></div>
        <button class="gf-icon-button" type="button" aria-label="Chiudi" data-install-later>${svg('x')}</button></header>
      <div class="gf-modal__body gf-stack">${body}</div>
      <footer class="gf-modal__footer"><button class="gf-button" data-variant="ghost" type="button" data-install-later>Più tardi</button>
        ${ios ? '<button class="gf-button" data-variant="primary" type="button" data-install-done>Fatto</button>'
              : `<button class="gf-button" data-variant="primary" type="button" data-install-now>${svg('download')}Installa</button>`}</footer>
    </div>`;
    overlay.addEventListener('click', async event => {
      if (event.target.closest('[data-install-later]')) close(overlay, {later: Date.now()});
      else if (event.target.closest('[data-install-done]')) close(overlay, {done: true});
      else if (event.target.closest('[data-install-now]') && prompt) {
        const offer = prompt; prompt = null;
        offer.prompt();
        const choice = await offer.userChoice.catch(() => ({outcome: 'dismissed'}));
        close(overlay, choice.outcome === 'accepted' ? {done: true} : {later: Date.now()});
      }
    });
    document.body.appendChild(overlay);
    overlay.querySelector('[data-install-now],[data-install-done]')?.focus();
  }

  // Chiamata quando l'app è pronta (dopo l'accesso). Su Android aspetta la proposta del browser.
  function maybeShow(appName = 'GiroFacile') {
    if (installed() || snoozed()) return;
    if (isIos()) { setTimeout(() => open(appName), 1200); return; }
    if (prompt) open(appName);
    else pending = appName;
  }

  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    prompt = event;
    if (pending && !installed() && !snoozed()) { open(pending); pending = false; }
  });
  window.addEventListener('appinstalled', () => {
    write({done: true});
    document.querySelector('[data-install-guide]')?.remove();
  });

  return {maybeShow, open, isIos, installed};
})();
