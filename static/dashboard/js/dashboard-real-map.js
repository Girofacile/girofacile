/* Dashboard: percorso stradale salvato + fermate, senza ricalcoli di routing.
   Riutilizza Leaflet, OSRM polyline e gli endpoint aziendali gia' presenti. */
(() => {
  'use strict';
  let generation = 0;
  let map = null;
  let host = null;
  let resizeObserver = null;
  let revealTimer = null;
  const stopMarkers = new Map();

  const validPosition = point => {
    if (!point || point.lat == null || point.lon == null) return null;
    const lat = Number(point.lat), lon = Number(point.lon);
    return Number.isFinite(lat) && Number.isFinite(lon) &&
      Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? {lat,lon} : null;
  };
  const stopStatus = delivery => {
    const status = String(delivery?.delivery_status || delivery?.status || '').toLowerCase();
    if (['completata','consegnata','completed'].includes(status)) return 'done';
    if (['mancata','non_consegnata','missed'].includes(status)) return 'miss';
    return 'todo';
  };
  const statusLabel = status => status === 'done' ? 'Completata' : status === 'miss' ? 'Mancata' : 'Da fare';

  function showMessage(element, message) {
    if (!element) return;
    element.classList.remove('gf-ref-map-ready');
    element.replaceChildren();
    const label = document.createElement('div');
    label.className = 'gf-empty';
    label.textContent = message;
    element.appendChild(label);
  }

  function reset() {
    generation += 1;
    if (revealTimer) clearTimeout(revealTimer);
    revealTimer = null;
    if (resizeObserver) resizeObserver.disconnect();
    resizeObserver = null;
    if (map) { map.remove(); map = null; }
    stopMarkers.clear();
    if (host) host.classList.remove('gf-ref-map-ready');
    host = null;
  }

  function highlight(index, active) {
    const root = document.getElementById('gfRefHeroWrap');
    if (!root) return;
    root.querySelectorAll('[data-gf-ref-stop="' + index + '"]').forEach(node => {
      node.classList.toggle('hl', !!active);
    });
  }

  function focusStop(index) {
    const marker = stopMarkers.get(Number(index));
    if (!marker || !map) return;
    map.panTo(marker.getLatLng());
    marker.openPopup();
  }

  function makeIcon(text, status, index) {
    const suffix = Number.isInteger(index) ? ' data-gf-ref-stop="' + index + '"' : '';
    const cls = status === 'depot' ? 'depot' : 'is-' + status;
    return L.divIcon({
      className: 'gf-ref-map-marker',
      html: '<span class="gf-ref-map-pin ' + cls + '"' + suffix + '>' + text + '</span>',
      iconSize: [34,34],
      iconAnchor: [17,17],
      popupAnchor: [0,-14]
    });
  }

  function makePopup(name, address, state, arrival) {
    const element = document.createElement('div');
    element.className = 'gf-ref-map-popup';
    const strong = document.createElement('strong');
    strong.textContent = name || 'Fermata';
    element.appendChild(strong);
    if (address) {
      const line = document.createElement('div');
      line.textContent = address;
      element.appendChild(line);
    }
    if (state || arrival) {
      const line = document.createElement('small');
      line.textContent = [state, arrival ? 'Arrivo previsto: ' + arrival : ''].filter(Boolean).join(' · ');
      element.appendChild(line);
    }
    return element;
  }

  async function render(routeId, routeDeliveries, element) {
    reset();
    host = element;
    const version = generation;
    if (!element || !element.isConnected || !Number.isSafeInteger(Number(routeId)) || Number(routeId) <= 0) return;
    showMessage(element, 'Caricamento mappa stradale…');
    try {
      // L'endpoint restituisce dati salvati, senza nuove chiamate OSRM o Mapbox.
      const data = await api('/api/routes/' + Number(routeId) + '/map-data');
      if (version !== generation || !element.isConnected) return;
      const depot = validPosition(data.depot);
      const orderedStops = Array.isArray(data.stops) ? data.stops : [];
      const deliveries = new Map((Array.isArray(routeDeliveries) ? routeDeliveries : [])
        .map(d => [String(d.id),d]));
      const positions = [];
      if (depot) positions.push([depot.lat,depot.lon]);
      const validStops = [];
      orderedStops.forEach((stop,index) => {
        const point = validPosition(stop);
        if (!point) return;
        const row = deliveries.get(String(stop.id)) || {};
        const status = stopStatus(row);
        validStops.push({stop,index,point,status});
        positions.push([point.lat,point.lon]);
      });

      const encoded = Array.isArray(data.road_polyline?.encoded_polylines)
        ? data.road_polyline.encoded_polylines
        : (data.road_polyline?.encoded_polyline ? [data.road_polyline.encoded_polyline] : []);
      const roadPaths = [];
      encoded.forEach(value => {
        if (typeof value !== 'string' || value.length > 1000000) return;
        const points = decodeGooglePolylineV75(value).filter(p =>
          Number.isFinite(p.lat) && Number.isFinite(p.lng) &&
          Math.abs(p.lat) <= 90 && Math.abs(p.lng) <= 180);
        if (points.length > 1) roadPaths.push(points.map(p => [p.lat,p.lng]));
      });
      if (!positions.length && !roadPaths.length) {
        showMessage(element, 'Coordinate del deposito e delle fermate non disponibili per questo giro.');
        return;
      }

      await loadRoadMapLibrary();
      if (version !== generation || !element.isConnected) return;
      element.replaceChildren();
      element.classList.add('gf-ref-map-ready');
      const canvas = document.createElement('div');
      canvas.className = 'gf-ref-map-canvas';
      canvas.setAttribute('role','region');
      canvas.setAttribute('aria-label','Mappa geografica del giro di consegne');
      element.appendChild(canvas);
      map = L.map(canvas, {scrollWheelZoom:false, zoomControl:true});
      // Il prefisso Leaflet include una bandierina SVG: il tema globale della
      // dashboard la ingrandiva. Manteniamo visibile il credito OSM del layer.
      map.attributionControl.setPrefix('');
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom:19,
        attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>'
      }).addTo(map);
      const bounds = positions.length ? L.latLngBounds(positions) : L.latLngBounds([]);
      let hasRoad = false;
      roadPaths.forEach(path => {
        const line = L.polyline(path, {color:'#1665ff',weight:4.5,opacity:0.95,lineCap:'round',lineJoin:'round'}).addTo(map);
        bounds.extend(line.getBounds());
        hasRoad = true;
      });
      // Mai unire le fermate con segmenti rettilinei fittizi.
      if (depot) {
        L.marker([depot.lat,depot.lon], {icon:makeIcon('D','depot',null),
          title:data.depot?.name || 'Deposito'})
          .addTo(map)
          .bindPopup(makePopup(data.depot?.name || 'Deposito',data.depot?.address || '','Partenza',''));
      }
      validStops.forEach(({stop,index,point,status}) => {
        const label = stop.name || 'Fermata ' + (index+1);
        const marker = L.marker([point.lat,point.lon], {
          icon:makeIcon(String(index+1),status,index), title:label,
          keyboard:true
        }).addTo(map);
        marker.bindPopup(makePopup(label,stop.address || '',statusLabel(status),stop.arrival || ''));
        marker.on('mouseover',() => highlight(index,true));
        marker.on('mouseout',() => highlight(index,false));
        marker.on('popupopen',() => highlight(index,true));
        marker.on('popupclose',() => highlight(index,false));
        stopMarkers.set(index,marker);
      });
      if (bounds.isValid()) map.fitBounds(bounds,{padding:[18,18],maxZoom:13,animate:false});
      const subtitle = document.getElementById('gfRefRouteSubtitle');
      if (subtitle) subtitle.textContent = hasRoad
        ? 'Percorso stradale pianificato, con fermate e consegne aggiornate'
        : 'Fermate sulla mappa · tracciato stradale non disponibile';

      if (!hasRoad || validStops.length < orderedStops.length) {
        const notice = document.createElement('div');
        notice.className = 'gf-ref-map-notice';
        let message = hasRoad ? '' : 'Tracciato stradale non disponibile: visualizzate le posizioni delle fermate.';
        if (validStops.length < orderedStops.length) {
          message += (message ? ' ' : '') + (orderedStops.length - validStops.length) + ' fermate senza coordinate.';
        }
        notice.textContent = message;
        element.appendChild(notice);
      }

      // La dashboard contiene animazioni e layout responsivi.
      const refreshSize = () => {
        if (version === generation && map && element.isConnected) map.invalidateSize({pan:false});
      };
      requestAnimationFrame(refreshSize);
      revealTimer = setTimeout(refreshSize,3100);
      if (typeof ResizeObserver === 'function') {
        resizeObserver = new ResizeObserver(refreshSize);
        resizeObserver.observe(element);
      }
    } catch (error) {
      if (version !== generation || !element.isConnected) return;
      if (map) {map.remove();map=null;}
      stopMarkers.clear();
      showMessage(element,'Mappa temporaneamente non disponibile. Le fermate restano consultabili a destra.');
      console.warn('Mappa dashboard',error);
    }
  }

  window.GiroFacileDashboardMap = Object.freeze({render,reset,highlight,focusStop});
})();
