/* GiroFacile · comportamenti della landing (stile «sito moderno», 17/11/2026).
   Comparsa delle sezioni, numeri che salgono, galleria dei piani con pallini e barra d'acquisto sul telefono.
   Tutto è facoltativo: senza JavaScript la pagina resta completa e leggibile. */
(function(){
  'use strict';
  const body = document.body;
  body.classList.add('gf-js');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function countUp(root){
    root.querySelectorAll('[data-count]').forEach(el => {
      const end = Number(el.dataset.count), t0 = performance.now(), dur = reduce ? 0 : 1400;
      if (!Number.isFinite(end)) return;
      const step = t => {
        const k = dur ? Math.min(1, (t - t0) / dur) : 1;
        el.textContent = Math.round(end * (1 - Math.pow(1 - k, 3))).toLocaleString('it-IT');
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }
  const reveal = 'IntersectionObserver' in window ? new IntersectionObserver(entries => entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    entry.target.classList.add('is-visible'); countUp(entry.target); reveal.unobserve(entry.target);
  }), {threshold: .15}) : null;
  document.querySelectorAll('[data-reveal]').forEach(el => reveal ? reveal.observe(el) : (el.classList.add('is-visible'), countUp(el)));

  /* Galleria: pallini creati in base alle schede e partenza dalla scheda consigliata. */
  document.querySelectorAll('.gf-snap').forEach(snap => {
    const dots = document.querySelector(`[data-dots="${snap.id}"]`);
    const cards = [...snap.children];
    if (dots) dots.innerHTML = cards.map(() => '<i></i>').join('');
    const sync = () => {
      const width = snap.scrollWidth / Math.max(cards.length, 1);
      const index = Math.round(snap.scrollLeft / width);
      dots?.querySelectorAll('i').forEach((dot, k) => dot.classList.toggle('is-active', k === index));
    };
    snap.addEventListener('scroll', sync, {passive: true});
    const start = cards.findIndex(card => card.dataset.recommended === 'true');
    requestAnimationFrame(() => {
      const card = cards[start > -1 ? start : 0];
      if (card && snap.scrollWidth > snap.clientWidth) snap.scrollLeft = card.offsetLeft - snap.offsetLeft - (snap.clientWidth - card.clientWidth) / 2;
      sync();
    });
  });

  /* Barra d'acquisto: piano consigliato dal catalogo, compare dopo la prima schermata. */
  const bar = document.querySelector('[data-buybar]');
  if (bar){
    const plans = window.GF_PLANS || {};
    const key = plans.business ? 'business' : Object.keys(plans)[0];
    const plan = plans[key];
    if (plan){
      bar.querySelector('[data-buy-name]').textContent = `${plan.name} · € ${plan.price_eur}/mese`;
      bar.querySelector('[data-buy-link]').href = '/login?plan=' + encodeURIComponent(key);
      const days = typeof window.publicTrialDays === 'function' ? window.publicTrialDays() : null;
      if (days > 0){
        bar.querySelector('[data-buy-link]').textContent = 'Prova gratis';
        bar.querySelector('[data-buy-note]').textContent = `${days} giorni gratis · nessuna carta`;
      }
    }
    const toggle = () => bar.classList.toggle('is-visible', scrollY > innerHeight * .7);
    addEventListener('scroll', toggle, {passive: true}); toggle();
  }
})();
