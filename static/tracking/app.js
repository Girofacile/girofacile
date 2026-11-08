/* The capability stays in the fragment and request header, never a URL query. */
(() => {
  let token = location.hash.slice(1);
  let timer, loading = false, stopped = false, timeZone = 'Europe/Rome';
  const el = id => document.getElementById(id);
  // [testo del badge, tono del badge, messaggio]
  const labels = {
    programmata: ['Consegna programmata', 'neutral', 'La consegna è stata pianificata.'],
    in_consegna: ['In viaggio verso di te', 'info', 'Il giro di consegne è iniziato. Qui trovi gli aggiornamenti disponibili.'],
    completata: ['Consegna completata', 'success', 'La tua consegna risulta completata.'],
    mancata: ['Consegna non effettuata', 'warning', 'Non è stato possibile completare la consegna. Contatta il mittente per i prossimi passi.'],
    annullata: ['Consegna annullata', 'danger', 'Questa consegna è stata annullata. Contatta il mittente per maggiori informazioni.'],
    non_disponibile: ['Aggiornamento non disponibile', 'neutral', 'Contatta il mittente per informazioni sulla consegna.'],
  };
  const STEPS = ['programmata', 'in_consegna', 'completata'];
  function date(value, timeOnly = false, zone = timeZone) {
    return new Intl.DateTimeFormat('it-IT', timeOnly
      ? {hour:'2-digit', minute:'2-digit', timeZone:zone}
      : {day:'numeric', month:'long', year:'numeric', timeZone:zone}).format(new Date(value));
  }
  // Identità dell'azienda: nome, logo (scaricato con il token, mai nell'indirizzo) e colore del brand.
  let brandDone = false;
  function brand(company) {
    if (brandDone || !company) return;
    brandDone = true;
    const name = company.name || '';
    if (name) {
      el('companyName').textContent = name;
      el('companyLogo').textContent = name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
      el('kicker').textContent = `Un aggiornamento da ${name}`;
      document.title = `La tua consegna · ${name}`;
    }
    const color = company.brand_color;
    if (/^#[0-9a-f]{6}$/i.test(color || '')) {
      const s = document.body.style;
      s.setProperty('--gf-color-primary', color);
      s.setProperty('--gf-color-primary-hover', `color-mix(in srgb, ${color} 85%, black)`);
      s.setProperty('--gf-color-info', `color-mix(in srgb, ${color} 80%, black)`);
      s.setProperty('--gf-color-info-bg', `color-mix(in srgb, ${color} 12%, white)`);
    }
    if (company.has_logo) {
      fetch('/api/public/tracking/logo', {headers: {'X-Tracking-Token': token}, credentials:'omit', referrerPolicy:'no-referrer'})
        .then(r => r.ok ? r.blob() : null)
        .then(blob => {
          if (!blob) return;
          const img = document.createElement('img');
          img.alt = '';
          img.src = URL.createObjectURL(blob);
          el('companyLogo').replaceChildren(img);
        }).catch(() => {});
    }
  }
  function render(data) {
    timeZone = data.timezone || 'Europe/Rome';
    brand(data.company);
    const [label, tone, message] = labels[data.status] || labels.non_disponibile;
    el('details').hidden = false;
    el('statusRow').hidden = false;
    el('title').textContent = data.status === 'completata' ? 'Consegna completata' : 'La tua consegna';
    el('message').textContent = message;
    el('status').textContent = label;
    el('status').dataset.status = tone;
    el('status').dataset.state = data.status;
    // A calendar date must not shift when the recipient travels abroad.
    const day = data.scheduled_date + 'T00:00:00Z';
    el('date').textContent = date(day, false, 'UTC');
    el('dateShort').textContent = new Intl.DateTimeFormat('it-IT', {day:'numeric', month:'short', timeZone:'UTC'}).format(new Date(day)).replace('.', '');
    el('etaLabel').textContent = data.eta.source === 'gps' ? 'Arrivo stimato dalla posizione' : data.eta.source === 'execution' ? 'Arrivo stimato aggiornato' : 'Arrivo previsto';
    const terminal = data.refresh_after_seconds === 0;
    // Senza orario valido (stima scaduta o giro chiuso) il numero non compare: niente orari inventati.
    const shown = data.eta.at || data.completed_at;
    el('etaFigure').hidden = !shown;
    el('eta').textContent = shown ? date(shown, true) : '';
    if (data.completed_at) el('etaLabel').textContent = 'Esito registrato alle';
    el('etaDate').textContent = data.completed_at ? date(data.completed_at) : data.eta.at ? `Arrivo ~${date(data.eta.at, true)}` : '';
    // Avanzamento in tre passi; nascosto se la consegna non è andata a buon fine.
    const reached = STEPS.indexOf(data.status);
    el('steps').hidden = reached < 0;
    el('steps').querySelectorAll('[data-step]').forEach((step, i) => {
      const done = i < reached || data.status === 'completata';
      step.classList.toggle('is-done', done);
      if (i === reached && !done) step.setAttribute('aria-current', 'step'); else step.removeAttribute('aria-current');
    });
    const before = data.stops_before;
    el('stopsFigure').hidden = before === null;
    el('stopsCount').textContent = before === null ? '' : String(before);
    el('stopsAlert').hidden = before === null;
    el('stops').textContent = before === 0 ? 'La tua è la prossima fermata prevista.'
      : `${before} ${before === 1 ? 'fermata prevista' : 'fermate previste'} prima della tua.`;
    el('stopsText').textContent = before === 0 ? 'L’autista sta arrivando da te.' : 'Il numero si aggiorna mentre l’autista completa le consegne.';
    el('completed').hidden = !data.completed_at;
    el('completed').textContent = data.completed_at ? `Esito registrato il ${date(data.completed_at)} alle ${date(data.completed_at, true)}.` : '';
    el('updated').textContent = data.eta.updated_at ? `Ultimo aggiornamento: ${date(data.eta.updated_at)} alle ${date(data.eta.updated_at, true)}.` : '';
    el('estimateNote').hidden = terminal;
    stopped = terminal;
    el('refresh').hidden = terminal;
  }
  async function refresh() {
    clearTimeout(timer);
    if (loading || stopped || document.hidden) return;
    if (!/^[0-9a-f]{64}\.[0-9a-f]{64}$/.test(token)) {
      el('message').textContent = 'Link non disponibile o incompleto. Richiedi il link al mittente.';
      el('details').hidden = true;
      el('statusRow').hidden = true;
      el('refresh').hidden = true;
      stopped = true;
      return;
    }
    loading = true;
    el('refresh').disabled = true;
    let delay = 30000;
    try {
      const response = await fetch('/api/public/tracking', {
        headers: {'X-Tracking-Token': token}, credentials:'omit', cache:'no-store', referrerPolicy:'no-referrer',
        signal: AbortSignal.timeout(15000),
      });
      if (response.status === 404) {
        el('message').textContent = 'Link non disponibile o scaduto. Richiedi un nuovo link al mittente.';
        el('details').hidden = true;
        el('statusRow').hidden = true;
        el('refresh').hidden = true;
        stopped = true;
        return;
      }
      if (!response.ok) {
        if (response.status === 429) delay = Math.max(60000, Number(response.headers.get('Retry-After') || 60) * 1000);
        throw new Error('unavailable');
      }
      render(await response.json());
    } catch (_) {
      el('details').hidden = true;
      el('statusRow').hidden = true;
      el('message').textContent = 'Aggiornamento temporaneamente non disponibile. Riproveremo automaticamente.';
    } finally {
      loading = false;
      el('refresh').disabled = false;
      if (!stopped && !document.hidden) timer = setTimeout(refresh, delay);
    }
  }
  el('refresh').addEventListener('click', refresh);
  document.addEventListener('visibilitychange', () => { clearTimeout(timer); if (!document.hidden) refresh(); });
  window.addEventListener('hashchange', () => {
    // Reload rather than let an in-flight response show a different delivery.
    location.reload();
  });
  refresh();
})();
