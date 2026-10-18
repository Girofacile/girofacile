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

  const CITY_CENTERS = Object.freeze({
    "agrigento":[37.3111,13.5765],"alessandria":[44.9125,8.6154],"ancona":[43.6158,13.5189],
    "aosta":[45.7370,7.3200],"arezzo":[43.4633,11.8796],"ascoli piceno":[42.8536,13.5749],
    "asti":[44.9008,8.2064],"avellino":[40.9144,14.7906],"bari":[41.1171,16.8719],
    "barletta":[41.3197,16.2837],"belluno":[46.1426,12.2167],"benevento":[41.1298,14.7826],
    "bergamo":[45.6983,9.6773],"biella":[45.5629,8.0583],"bologna":[44.4949,11.3426],
    "bolzano":[46.4983,11.3548],"brescia":[45.5416,10.2118],"brindisi":[40.6327,17.9418],
    "cagliari":[39.2238,9.1217],"caltanissetta":[37.4901,14.0629],"campobasso":[41.5603,14.6627],
    "caserta":[41.0748,14.3323],"catania":[37.5079,15.0830],"catanzaro":[38.9098,16.5877],
    "chieti":[42.3510,14.1675],"como":[45.8081,9.0852],"cosenza":[39.2983,16.2531],
    "cremona":[45.1332,10.0227],"crotone":[39.0808,17.1271],"cuneo":[44.3845,7.5427],
    "enna":[37.5670,14.2790],"ferrara":[44.8381,11.6198],"firenze":[43.7696,11.2558],
    "foggia":[41.4622,15.5446],"forli":[44.2227,12.0407],"frosinone":[41.6396,13.3426],
    "genova":[44.4056,8.9463],"gorizia":[45.9415,13.6210],"grosseto":[42.7635,11.1124],
    "imperia":[43.8897,8.0395],"isernia":[41.5960,14.2339],"la spezia":[44.1025,9.8241],
    "l aquila":[42.3498,13.3995],"latina":[41.4676,12.9037],"lecce":[40.3515,18.1750],
    "lecco":[45.8566,9.3977],"livorno":[43.5485,10.3106],"lodi":[45.3140,9.5035],
    "lucca":[43.8429,10.5027],"macerata":[43.2984,13.4535],"mantova":[45.1564,10.7914],
    "massa":[44.0354,10.1396],"matera":[40.6664,16.6043],"messina":[38.1938,15.5540],
    "milano":[45.4642,9.1900],"modena":[44.6471,10.9252],"monza":[45.5845,9.2744],
    "napoli":[40.8518,14.2681],"novara":[45.4469,8.6222],"nuoro":[40.3210,9.3290],
    "oristano":[39.9062,8.5884],"padova":[45.4064,11.8768],"palermo":[38.1157,13.3615],
    "parma":[44.8015,10.3279],"pavia":[45.1847,9.1582],"perugia":[43.1107,12.3908],
    "pesaro":[43.9102,12.9133],"pescara":[42.4618,14.2161],"piacenza":[45.0526,9.6929],
    "pisa":[43.7228,10.4017],"pistoia":[43.9303,10.9079],"pordenone":[45.9564,12.6615],
    "potenza":[40.6404,15.8056],"prato":[43.8777,11.1022],"ravenna":[44.4184,12.2035],
    "reggio calabria":[38.1113,15.6473],"reggio emilia":[44.6989,10.6297],
    "reggio nell emilia":[44.6989,10.6297],"rieti":[42.4049,12.8622],"rimini":[44.0678,12.5695],
    "roma":[41.9028,12.4964],"rovigo":[45.0706,11.7900],"salerno":[40.6824,14.7681],
    "sassari":[40.7259,8.5557],"savona":[44.3070,8.4810],"siena":[43.3188,11.3308],
    "siracusa":[37.0755,15.2866],"sondrio":[46.1699,9.8788],"taranto":[40.4644,17.2470],
    "teramo":[42.6589,13.7044],"terni":[42.5636,12.6427],"torino":[45.0703,7.6869],
    "trapani":[38.0176,12.5372],"trento":[46.0748,11.1217],"treviso":[45.6669,12.2430],
    "trieste":[45.6495,13.7768],"udine":[46.0711,13.2346],"varese":[45.8206,8.8251],
    "venezia":[45.4408,12.3155],"verbania":[45.9214,8.5518],"vercelli":[45.3234,8.4231],
    "verona":[45.4384,10.9916],"vibo valentia":[38.6758,16.0983],"vicenza":[45.5455,11.5354],
    "viterbo":[42.4207,12.1077],"andria":[41.2312,16.2979],"trani":[41.2773,16.4179],
    "cesena":[44.1396,12.2464],"imola":[44.3559,11.7160],"viareggio":[43.8669,10.2502],
    "empoli":[43.7176,10.9477],"carpi":[44.7833,10.8833],"busto arsizio":[45.6119,8.8521],
    "legnano":[45.5969,8.9150],"seregno":[45.6500,9.2050],"sesto san giovanni":[45.5333,9.2333],
    "acerra":[40.9440,14.3710],"castellammare di stabia":[40.6940,14.4800],"pompei":[40.7462,14.4989],
    "torre annunziata":[40.7530,14.4520],"pozzuoli":[40.8230,14.1210],"giugliano in campania":[40.9280,14.2010],
    "casoria":[40.9070,14.2950],"aversa":[40.9730,14.2070],"nola":[40.9260,14.5280]
  });

  function normalizeCityName(value){
    return String(value||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"")
      .toLocaleLowerCase("it").replace(/[’']/g," ").replace(/[^a-z0-9]+/g," ").trim();
  }

  function cityCenter(value){
    const raw=String(value||"").split(",")[0].replace(/\s*\([^)]*\)/g,"").split(/\s+-\s+/)[0].trim();
    const coords=CITY_CENTERS[normalizeCityName(raw)];
    return coords?{lat:coords[0],lon:coords[1]}:null;
  }

  async function renderEmpty(element, area = {}){
    reset();
    host=element;
    const version=generation;
    if(!element || !element.isConnected)return;
    showMessage(element,"Caricamento area operativa…");
    try{
      await loadRoadMapLibrary();
      if(version!==generation || !element.isConnected)return;
      const deposits=Array.isArray(area.deposits)?area.deposits:[];
      const depot=deposits.find(item=>item?.predefinito && validPosition(item))
        || deposits.find(item=>validPosition(item)) || null;
      const depotPosition=validPosition(depot);
      const cityPosition=depotPosition?null:cityCenter(area.city);
      const position=depotPosition||cityPosition;
      const center=position?[position.lat,position.lon]:[42.8,12.5];
      const zoom=depotPosition?9:cityPosition?8:5;
      const city=String(area.city||"").trim();
      const label=depot?(depot.nome||"Deposito aziendale"):(city||"Area operativa");
      element.replaceChildren();
      element.classList.add("gf-ref-map-ready");
      const canvas=document.createElement("div");
      canvas.className="gf-ref-map-canvas";
      canvas.setAttribute("role","region");
      canvas.setAttribute("aria-label","Mappa dell’area operativa aziendale");
      element.appendChild(canvas);
      map=L.map(canvas,{scrollWheelZoom:false,zoomControl:true});
      map.attributionControl.setPrefix("");
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{
        maxZoom:19,
        attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>'
      }).addTo(map);
      if(position){
        L.circle([position.lat,position.lon],{
          radius:2500,color:"#1f5bff",weight:1.5,fillColor:"#1f5bff",fillOpacity:0.08
        }).addTo(map);
        L.marker([position.lat,position.lon],{
          icon:makeIcon("A","depot",null),title:label
        }).addTo(map).bindPopup(makePopup(label,depot?.indirizzo||area.address||"","Area operativa",""));
      }
      map.setView(center,zoom,{animate:false});
      const subtitle=document.getElementById("gfRefRouteSubtitle");
      if(subtitle){
        if(depotPosition)subtitle.textContent=city?"Area del deposito aziendale · "+city:"Area del deposito aziendale";
        else if(cityPosition)subtitle.textContent="Vista regionale di "+city;
        else if(city)subtitle.textContent="Vista generale dell’Italia · aggiungi un deposito per centrare "+city;
        else subtitle.textContent="Imposta la città nel profilo aziendale o aggiungi un deposito per personalizzare la mappa";
      }
      const refreshSize=()=>{if(version===generation && map && element.isConnected)map.invalidateSize({pan:false});};
      requestAnimationFrame(refreshSize);
      revealTimer=setTimeout(refreshSize,500);
      if(typeof ResizeObserver==="function"){
        resizeObserver=new ResizeObserver(refreshSize);
        resizeObserver.observe(element);
      }
    }catch(error){
      if(version!==generation || !element.isConnected)return;
      if(map){map.remove();map=null;}
      showMessage(element,"Mappa dell’area operativa temporaneamente non disponibile.");
      console.warn("Mappa area operativa",error);
    }
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

  window.GiroFacileDashboardMap = Object.freeze({render,renderEmpty,reset,highlight,focusStop});
})();
