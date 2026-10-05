(() => {
  let timer, generation = 0, map, marker, host;
  const visible = () => host?.isConnected && !!host.getClientRects().length && !document.hidden;
  const time = value => new Date(value).toLocaleString('it-IT', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
  function status(state, text) {
    host.dataset.state = state;
    host.querySelector('[data-gps-state]').textContent = text;
    if (marker) marker.setOpacity(state === 'fresh' ? 1 : 0.45);
  }
  async function refresh(routeId, version) {
    clearTimeout(timer);
    if (version !== generation || !host?.isConnected) return;
    if (!visible()) { timer = setTimeout(() => refresh(routeId,version), 30000); return; }
    try {
      const response = await fetch(`/api/routes/${routeId}/position`, {cache:'no-store',signal:AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error('unavailable');
      const data = await response.json();
      if (version !== generation) return;
      host.querySelector('[data-gps-route]').textContent = data.route_name;
      host.querySelector('[data-gps-vehicle]').textContent = data.vehicle_name || 'Mezzo non assegnato';
      host.querySelector('[data-gps-next]').textContent = data.next_stop || 'Fermate terminate';
      host.querySelector('[data-gps-progress]').textContent = `${data.progress}%`;
      const p = data.position;
      status(data.state, data.route_status !== 'in_corso' ? 'Giro terminato · GPS disattivato' : data.state === 'fresh' ? 'Posizione aggiornata' : data.state === 'stale' ? 'Posizione non aggiornata' : 'In attesa della posizione');
      host.querySelector('[data-gps-updated]').textContent = p ? `Ultimo rilevamento: ${time(p.captured_at)} · precisione circa ${Math.round(p.accuracy)} m` : 'La posizione appare quando l’autista apre il portale e autorizza il GPS.';
      const empty = host.querySelector('[data-gps-empty]');
      if (p) {
        try {
          await loadRoadMapLibrary();
          if (version !== generation || !host.isConnected) return;
          if (!map) {
            map = L.map(host.querySelector('[data-gps-map]')).setView([p.latitude,p.longitude],14);
            L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,
              attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);
            marker = L.marker([p.latitude,p.longitude], {icon:L.divIcon({className:'gf-live-vehicle',html:'<span aria-label="Mezzo">➤</span>',iconSize:[38,38]})}).addTo(map);
          } else {
            marker.setLatLng([p.latitude,p.longitude]);
            if (!map.getBounds().contains(marker.getLatLng())) map.panTo(marker.getLatLng());
          }
          marker.setOpacity(data.state === 'fresh' ? 1 : 0.45);
          empty.hidden = true;
          map.invalidateSize();
        } catch (_) { empty.hidden = false; empty.textContent = 'Mappa non disponibile. I dati della posizione restano consultabili.'; }
      } else {
        if (marker) { map.removeLayer(marker); marker = null; map.remove(); map = null; }
        empty.hidden = false;
      }
      if (data.route_status !== 'in_corso') return;
    } catch (_) {
      if (version !== generation) return;
      status('stale', 'Connessione non disponibile · dati non aggiornati');
    }
    if (version === generation) timer = setTimeout(() => refresh(routeId,version),30000);
  }
  window.GiroFacileLiveMap = {
    mount(routeId) {
      generation++; clearTimeout(timer);
      if (map) map.remove(); map = marker = null;
      host = document.getElementById('dashboardLiveGPS');
      if (!host) return;
      host.dataset.routeId = routeId;
      refresh(routeId,generation);
    },
  };
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && host?.isConnected) refresh(host.dataset.routeId,generation);
  });
})();
