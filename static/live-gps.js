/* Browser adapter. The server contract is also suitable for native GPS clients. */
(() => {
  let route = null, timer, generation = 0, busy = false, denied = false;
  let lastCapture = null, lastPreciseAttempt = 0, message = 'Il GPS si attiva quando avvii il giro.', state = 'idle';
  const hosts = () => document.querySelectorAll('[data-gps-status]');
  function paint(nextState, text) {
    state = nextState; message = text;
    hosts().forEach(host => {
      host.dataset.state = state;
      host.querySelector('[data-gps-message]').textContent = message;
      host.querySelector('[data-gps-retry]').hidden = !['denied', 'error'].includes(state);
    });
  }
  function stop(text = 'Giro terminato. Condivisione della posizione disattivata.') {
    generation++; clearTimeout(timer); route = null; lastCapture = null; busy = false;
    paint('idle', text);
  }
  function later(delay = 30000) {
    clearTimeout(timer);
    if (route && !document.hidden && !denied) timer = setTimeout(tick, delay);
  }
  async function tick() {
    clearTimeout(timer);
    if (!route || busy || denied || document.hidden) return;
    if (!navigator.onLine) { paint('error', 'Connessione assente. Il GPS riprende quando torni online.'); later(); return; }
    if (!navigator.geolocation || !window.isSecureContext) {
      denied = true; paint('denied', 'GPS non disponibile. Apri il portale in HTTPS e verifica i permessi.'); return;
    }
    const current = route, version = generation;
    busy = true;
    try {
      // Check the authoritative lifecycle before every acquisition, including reconnection.
      const response = await fetch(current.statusUrl, {cache:'no-store', signal:AbortSignal.timeout(10000)});
      if ([401,403,404,410].includes(response.status)) { stop('Accesso al giro scaduto. Posizione disattivata.'); return; }
      if (!response.ok) throw new Error('network');
      const data = await response.json();
      if (version !== generation) return;
      if (!data.active) { stop(); return; }
      if (document.hidden) return;
      let position = await new Promise((resolve,reject) => navigator.geolocation.getCurrentPosition(resolve,reject,
        {enableHighAccuracy:false, maximumAge:20000, timeout:12000}));
      if (version !== generation || document.hidden) return;
      // Only request an expensive precise fix when coarse positioning is unusable.
      if (position.coords.accuracy > 150 && Date.now() - lastPreciseAttempt >= 120000) {
        lastPreciseAttempt = Date.now();
        position = await new Promise((resolve,reject) => navigator.geolocation.getCurrentPosition(resolve,reject,
          {enableHighAccuracy:true, maximumAge:0, timeout:10000}));
        if (version !== generation || document.hidden) return;
      }
      if (position.coords.accuracy > 150 || Date.now() - position.timestamp > 90000) {
        paint('error', 'Posizione poco precisa. Riprovo automaticamente.'); return;
      }
      lastCapture = {latitude:position.coords.latitude, longitude:position.coords.longitude,
        accuracy:position.coords.accuracy, captured_at:new Date(position.timestamp).toISOString()};
      const upload = await fetch(current.uploadUrl, {method:'POST', cache:'no-store',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(lastCapture), signal:AbortSignal.timeout(20000)});
      if (version !== generation) return;
      if ([401,403,404,409,410].includes(upload.status)) { stop(); return; }
      if (!upload.ok) throw new Error('network');
      const saved = await upload.json();
      if (!saved.accepted) {
        paint('error', saved.reason === 'throttled' ? 'Aggiornamento già ricevuto. Prossimo invio tra poco.' : 'Posizione non utilizzabile. Riprovo automaticamente.');
      } else {
        const time = new Date(saved.captured_at).toLocaleTimeString('it-IT', {hour:'2-digit', minute:'2-digit'});
        paint('active', `Posizione condivisa alle ${time} · solo durante il giro`);
      }
      lastCapture = null;
    } catch (error) {
      if (version !== generation) return;
      if (error.code === 1) {
        denied = true; paint('denied', 'Permesso GPS negato. Abilita la posizione nelle impostazioni del browser, poi riprova.');
      } else {
        paint('error', error.code ? 'Posizione non disponibile. Riprovo automaticamente.' : 'Aggiornamento non inviato. Riprovo alla riconnessione.');
      }
    } finally {
      if (version === generation) { busy = false; later(); }
    }
  }
  window.GiroFacileGPS = {
    sync(config) {
      if (config.status !== 'in_corso') { if (route) stop(); return; }
      if (route?.uploadUrl === config.uploadUrl) { paint(state, message); return; }
      generation++; busy = false; route = config; lastCapture = null;
      paint('idle', 'GPS attivo per questo giro. Rilevamento della posizione…'); tick();
    },
    stop,
    retry() { denied = false; tick(); },
  };
  document.addEventListener('click', event => { if (event.target.closest('[data-gps-retry]')) window.GiroFacileGPS.retry(); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(timer); lastCapture = null;
      if (route) paint('idle', 'Portale in background. Il GPS riprende quando torni qui.');
    } else tick();
  });
  window.addEventListener('online', tick);
  window.addEventListener('offline', () => { if (route) paint('error', 'Connessione assente. Il GPS riprende quando torni online.'); });
  window.addEventListener('pagehide', () => { generation++; busy = false; clearTimeout(timer); lastCapture = null; });
  window.addEventListener('pageshow', tick);
})();
