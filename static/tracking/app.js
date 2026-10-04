/* The capability stays in the fragment and request header, never a URL query. */
(() => {
  let token = location.hash.slice(1);
  let timer, loading = false, stopped = false, timeZone = 'Europe/Rome';
  const el = id => document.getElementById(id);
  const labels = {
    programmata: ['Consegna programmata', 'La consegna è stata pianificata.'],
    in_consegna: ['Consegna in corso', 'Il giro di consegne è iniziato. Qui trovi gli aggiornamenti disponibili.'],
    completata: ['Consegna completata', 'La tua consegna risulta completata.'],
    mancata: ['Consegna non effettuata', 'Non è stato possibile completare la consegna. Contatta il mittente per i prossimi passi.'],
    annullata: ['Consegna annullata', 'Questa consegna è stata annullata. Contatta il mittente per maggiori informazioni.'],
    non_disponibile: ['Aggiornamento non disponibile', 'Contatta il mittente per informazioni sulla consegna.'],
  };
  function date(value, timeOnly = false, zone = timeZone) {
    return new Intl.DateTimeFormat('it-IT', timeOnly
      ? {hour:'2-digit', minute:'2-digit', timeZone:zone}
      : {day:'numeric', month:'long', year:'numeric', timeZone:zone}).format(new Date(value));
  }
  function render(data) {
    timeZone = data.timezone || 'Europe/Rome';
    const [label, message] = labels[data.status] || labels.non_disponibile;
    el('details').hidden = false;
    el('title').textContent = data.status === 'completata' ? 'Consegna completata' : 'La tua consegna';
    el('message').textContent = message;
    el('status').textContent = label;
    // A calendar date must not shift when the recipient travels abroad.
    el('date').textContent = date(data.scheduled_date + 'T00:00:00Z', false, 'UTC');
    el('etaLabel').textContent = data.eta.source === 'execution' ? 'Arrivo stimato aggiornato' : 'Arrivo previsto';
    const terminal = data.refresh_after_seconds === 0;
    el('eta').textContent = data.eta.at ? `${date(data.eta.at, true)} · ${date(data.eta.at)}` : terminal ? '—' : 'In aggiornamento';
    el('stops').hidden = data.stops_before === null;
    el('stops').textContent = data.stops_before === 0 ? 'La tua è la prossima fermata prevista.'
      : `${data.stops_before} ${data.stops_before === 1 ? 'fermata prevista' : 'fermate previste'} prima della tua.`;
    el('completed').hidden = !data.completed_at;
    el('completed').textContent = data.completed_at ? `Esito registrato il ${date(data.completed_at)} alle ${date(data.completed_at, true)}.` : '';
    el('updated').textContent = data.eta.updated_at ? `Ultimo aggiornamento operativo: ${date(data.eta.updated_at)} alle ${date(data.eta.updated_at, true)}.` : '';
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
