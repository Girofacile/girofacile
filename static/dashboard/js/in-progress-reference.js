window.GFInProgressReference=(()=>{
  const state={routes:[],detail:null,id:null,filter:'all',outcome:'all',gps:new Map(),map:null,vehicle:null,circle:null,markers:new Map(),follow:false,chat:false,timer:null,loading:false,epoch:0,hash:''};
  const root=()=>document.getElementById('dashboardInProgressPage');
  const visible=()=>!document.getElementById('tab-dashboard-in-progress')?.classList.contains('hidden');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n=v=>Number.isFinite(Number(v))?Number(v):0;
  const money=v=>v==null?'—':'€ '+n(v).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
  const km=v=>v==null?'—':n(v).toLocaleString('it-IT',{maximumFractionDigits:1})+' km';
  const done=d=>(d.delivery_status||d.status)==='completata';
  const miss=d=>(d.delivery_status||d.status)==='mancata';
  const outcome=d=>done(d)?'done':miss(d)?'miss':'todo';
  const stat=r=>{
    const rows=r.consegne||[], total=rows.length?rows.length:n(r.consegne_count);
    const completed=rows.length?rows.filter(done).length:n(r.completed_count);
    const missed=rows.length?rows.filter(miss).length:n(r.missed_count);
    return {total,done:completed,miss:missed,todo:Math.max(0,total-completed-missed)};
  };
  const gpsText=p=>!p?'Verifica GPS…':p.state==='fresh'?'GPS live':p.state==='stale'?'GPS non aggiornato':'GPS non disponibile';
  const gpsClass=p=>p?.state==='fresh'?'live':p?.state==='stale'?'stale':'unknown';
  const initials=name=>String(name||'').trim().split(/\s+/).slice(0,2).map(v=>v[0]?.toUpperCase()||'').join('')||'—';
  const icon=name=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+({refresh:'<path d="M20 11a8 8 0 0 0-14.5-4M4 4v4h4M4 13a8 8 0 0 0 14.5 4M20 20v-4h-4"/>',target:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>',chat:'<path d="M21 11a9 8 0 0 1-12 8l-6 2 1-6a9 8 0 1 1 17-4Z"/>',map:'<path d="M12 22S4 13 4 9a8 8 0 0 1 16 0c0 4-8 13-8 13Z"/><circle cx="12" cy="9" r="2"/>'}[name]||'')+'</svg>';
  function stopMap(){
    state.epoch++;
    if(state.map)state.map.remove();
    state.map=state.vehicle=state.circle=null;state.markers.clear();state.follow=false;
  }
  function suspend(){if(state.timer)clearInterval(state.timer);state.timer=null;stopMap();}
  function bar(route){
    const s=stat(route),w=v=>s.total?Math.max(0,Math.min(100,Math.round(20*v/s.total)*5)):0;
    return '<span class="gf-progress__track" role="img" aria-label="'+s.done+' completate, '+s.miss+' mancate, '+s.todo+' da fare">'+
      '<span class="gf-progress__done" data-gf-width="'+w(s.done)+'"></span><span class="gf-progress__miss" data-gf-width="'+w(s.miss)+'"></span></span>';
  }
  const chip=(label,type='info')=>'<span class="gf-badge" data-status="'+type+'">'+esc(label)+'</span>';
  const gpsTone=p=>p?.state==='fresh'?'success':p?.state==='stale'?'warning':'neutral';
  // Ritardo sul rientro: rientro aggiornato con il traffico rispetto a quello previsto alla programmazione.
  const clockMin=v=>{const m=/^(\d{1,2}):(\d{2})/.exec(String(v||''));return m?Number(m[1])*60+Number(m[2]):null;};
  const delay=r=>{
    if(n(r.delay_minutes)>0)return Math.round(n(r.delay_minutes));
    const now=clockMin(r.rientro_stimato_aggiornato),planned=clockMin(r.orario_rientro_stimato);
    if(now==null||planned==null)return 0;
    const diff=(now-planned+1440)%1440;
    return diff>0&&diff<720?diff:0;
  };
  const issue=r=>stat(r).miss>0 || delay(r)>0 || r.late===true;
  // Una riga per giro (approvata il 4 novembre 2026): autista e mezzo, avanzamento, prossima
  // fermata, rientro e segnali; «Apri» mostra il giro nel dettaglio sotto.
  // Un giro partito in un giorno precedente e mai chiuso: va chiuso dall'ufficio.
  function openSince(r){
    const d=new Date(),today=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    if(!r||!r.data_giro||r.data_giro>=today)return '';
    const [y,m,g]=r.data_giro.split('-').map(Number);
    return new Intl.DateTimeFormat('it-IT',{weekday:'short',day:'numeric',month:'long'}).format(new Date(y,m-1,g));
  }
  // Variante D (20 novembre 2026): striscia «Giri attivi» con un riquadro semplice per giro.
  function routeCard(r,index){
    const chosen=Number(state.id)===Number(r.id);
    return '<label class="gf-card gf-planning-choice"'+(chosen?' data-variant="info"':'')+'>'+
      '<span class="gf-cluster"><span class="gf-avatar" data-tone="'+(index%6+1)+'" aria-hidden="true">'+esc(initials(r.driver_name))+'</span>'+
      '<span class="gf-list-item__main"><strong>'+esc(r.nome||'Giro consegne')+'</strong><small>'+esc(r.driver_name||'Autista non assegnato')+'</small></span>'+
      '<input type="radio" name="ipRoute" value="'+Number(r.id)+'" data-ip-route="'+Number(r.id)+'"'+(chosen?' checked':'')+
      ' aria-label="'+esc((r.nome||'Giro consegne')+' · '+(r.driver_name||'Autista non assegnato'))+'"></span></label>';
  }
  function filtered(){ return state.routes; }
  function paintCards(){
    const page=root();if(!page)return;
    const box=page.querySelector('[data-ip-picker]');if(!box)return;
    const visible=filtered();
    box.innerHTML=visible.map(r=>routeCard(r,state.routes.indexOf(r))).join('');
    const count=page.querySelector('[data-ip-count]');
    if(count)count.textContent=String(state.routes.length);
  }
  function stopRow(d,i,r,planned){
    const type=outcome(d),notes=d.note_operatore||d.note_autista||d.note||'';
    const title=type==='done'?'Completata':type==='miss'?'Mancata':'Da fare';
    const tone=type==='done'?'success':type==='miss'?'danger':'neutral';
    const time=gfRealArrival(d);
    return '<tr data-ip-stop="'+i+'" data-ip-outcome="'+type+'">'+
      '<td data-label="#"><span class="gf-badge" data-status="'+tone+'">'+(i+1)+'</span></td>'+
      '<td data-label="Cliente"><strong>'+esc(d.cliente_nome||'—')+'</strong></td><td data-label="Indirizzo">'+esc(d.indirizzo||'—')+'</td>'+
      '<td data-label="Arrivo previsto">'+esc(gfPlannedArrival(d)||'—')+'</td><td data-label="Arrivo reale">'+esc(time||'—')+'</td>'+
      '<td data-label="Differenza">'+gfDeltaBadge(planned[i],gfRealArrivalDate(d))+'</td>'+
      '<td data-label="Scarico">'+gfUnloadCell(d,true)+'</td>'+
      '<td data-label="Stato">'+chip(title,tone)+
      (d.motivo_mancata?'<br><small class="gf-muted">'+esc(gfMissedReason(d.motivo_mancata))+'</small>':'')+'</td>'+
      '<td data-label="Documenti e tracking"><div class="gf-cluster">'+deliverySignatureAction(d,r.driver_name)+' '+trackingButton(d,r)+
      (notes?'<button type="button" class="gf-button" data-variant="ghost" data-size="sm" data-ip-note="'+esc(notes)+'">Note</button>':'')+
      '</div></td></tr>';
  }
  function paintOutcome(){
    root()?.querySelectorAll('tr[data-ip-outcome]').forEach(tr=>tr.hidden=state.outcome!=='all'&&tr.dataset.ipOutcome!==state.outcome);
  }
  function highlight(index,on){
    root()?.querySelectorAll('[data-ip-stop="'+index+'"],[data-ip-pin="'+index+'"]').forEach(el=>el.classList.toggle(el.matches('tr')?'is-highlighted':'hl',on));
  }
  function focusStop(index){
    const marker=state.markers.get(Number(index));
    if(marker&&state.map){state.map.panTo(marker.getLatLng());marker.openPopup();}
  }
  function drawGPS(){
    const page=root(),current=state.gps.get(Number(state.id)),p=current?.position;
    const badge=page?.querySelector('.gf-ip-map-badge');
    if(badge){
      badge.className='gf-ip-map-badge '+gpsClass(current);
      const title=current?.state==='fresh'?'Posizione live':current?.state==='stale'?'Posizione non aggiornata':'Posizione GPS non disponibile';
      let detail='La posizione compare quando l’autista autorizza il GPS.';
      if(p){
        const d=new Date(p.captured_at),when=Number.isNaN(d.getTime())?'':d.toLocaleString('it-IT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
        detail=(when?'Ultimo rilevamento '+when:'Ultimo rilevamento disponibile')+(p.accuracy!=null?' · ±'+Math.round(n(p.accuracy))+' m':'');
      }
      badge.innerHTML='<i></i><span><strong>'+esc(title)+'</strong><small>'+esc(detail)+'</small></span>';
    }
    const text=page?.querySelector('.gf-ip-map-gps');
    if(text)text.textContent=gpsText(current);
    const lat=p?.latitude==null?NaN:Number(p.latitude),lon=p?.longitude==null?NaN:Number(p.longitude);
    const hasPosition=Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat)<=90&&Math.abs(lon)<=180;
    if(!hasPosition){
      state.vehicle?.remove();state.circle?.remove();
      state.vehicle=state.circle=null;state.follow=false;
    }
    const follow=page?.querySelector('[data-ip-action="follow"]');
    if(follow){follow.disabled=!hasPosition;follow.setAttribute('aria-pressed',String(state.follow));}
    if(!state.map||!hasPosition)return;
    const coord=[lat,lon],radius=Math.min(1000,Math.max(0,n(p.accuracy)));
    if(!state.vehicle){
      const mark=L.divIcon({className:'gf-ip-vehicle-icon',html:'<span>'+icon('target')+'</span>',iconSize:[38,38],iconAnchor:[19,19]});
      state.vehicle=L.marker(coord,{icon:mark,title:'Ultima posizione GPS del mezzo'}).addTo(state.map);
      state.circle=L.circle(coord,{radius,color:'#1f5bff',fillColor:'#1f5bff',fillOpacity:.06,weight:1}).addTo(state.map);
    }else{state.vehicle.setLatLng(coord);state.circle.setLatLng(coord);state.circle.setRadius(radius);}
    state.vehicle.getElement()?.classList.toggle('stale',current.state!=='fresh');
    if(state.follow)state.map.panTo(coord);
  }
  async function drawMap(routeId){
    stopMap();
    const epoch=state.epoch,canvas=root()?.querySelector('.gf-ip-map-canvas');
    if(!canvas)return;
    canvas.textContent='Caricamento mappa…';
    try{
      const [data]=await Promise.all([api('/api/routes/'+routeId+'/map-data'),loadRoadMapLibrary()]);
      if(epoch!==state.epoch||!canvas.isConnected)return;
      canvas.replaceChildren();
      state.map=L.map(canvas,{zoomControl:false,scrollWheelZoom:false});
      state.map.attributionControl.setPrefix('');
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(state.map);
      const coords=[],pos=p=>{
        if(p?.lat==null||p?.lon==null)return null;
        const lat=Number(p.lat),lon=Number(p.lon);
        return Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat)<=90&&Math.abs(lon)<=180?[lat,lon]:null;
      };
      const depot=pos(data.depot);
      if(depot){
        coords.push(depot);
        L.marker(depot,{icon:L.divIcon({className:'gf-ip-pin-icon',html:'<span class="gf-ip-pin depot">D</span>',iconSize:[32,32],iconAnchor:[16,16]})}).addTo(state.map);
      }
      const details=new Map((state.detail?.consegne||[]).map(d=>[String(d.id),d]));
      (data.stops||[]).forEach((stop,index)=>{
        const loc=pos(stop);if(!loc)return;
        coords.push(loc);
        const st=outcome(details.get(String(stop.id))||{});
        const marker=L.marker(loc,{icon:L.divIcon({className:'gf-ip-pin-icon',html:'<span class="gf-ip-pin '+st+'" data-ip-pin="'+index+'">'+(index+1)+'</span>',iconSize:[32,32],iconAnchor:[16,16]}),title:stop.name||'Fermata'}).addTo(state.map);
        const popup=document.createElement('div'),title=document.createElement('strong'),address=document.createElement('div');
        title.textContent=stop.name||'Fermata '+(index+1);address.textContent=stop.address||'';popup.append(title,address);marker.bindPopup(popup);
        marker.on('mouseover',()=>highlight(index,true));marker.on('mouseout',()=>highlight(index,false));
        marker.on('popupopen',()=>highlight(index,true));marker.on('popupclose',()=>highlight(index,false));
        state.markers.set(index,marker);
      });
      const encoded=Array.isArray(data.road_polyline?.encoded_polylines)?data.road_polyline.encoded_polylines:
        (data.road_polyline?.encoded_polyline?[data.road_polyline.encoded_polyline]:[]);
      let hasRoad=false;
      encoded.forEach(line=>{
        if(typeof line!=='string'||line.length>1000000)return;
        const path=decodeGooglePolylineV75(line).filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lng)&&Math.abs(p.lat)<=90&&Math.abs(p.lng)<=180).map(p=>[p.lat,p.lng]);
        if(path.length>1){L.polyline(path,{color:'#1f5bff',weight:4.5,opacity:.94,lineCap:'round'}).addTo(state.map);coords.push(...path);hasRoad=true;}
      });
      if(coords.length)state.map.fitBounds(L.latLngBounds(coords),{padding:[24,24],maxZoom:13,animate:false});
      else{
        canvas.textContent='Coordinate del percorso non disponibili.';
        state.map.remove();state.map=null;return;
      }
      if(!hasRoad){const note=root()?.querySelector('.gf-ip-map-warning');if(note)note.textContent='Tracciato stradale non disponibile: sono indicate solo le fermate.';}
      drawGPS();requestAnimationFrame(()=>state.map?.invalidateSize());
      setTimeout(()=>{if(epoch===state.epoch)state.map?.invalidateSize()},500);
    }catch(error){
      if(epoch!==state.epoch)return;
      if(state.map)state.map.remove();state.map=null;
      canvas.textContent='Mappa non disponibile. Le fermate restano consultabili nella tabella.';
      console.warn('Mappa giri in corso',error);
    }
  }
  async function checkGPS(id){
    try{
      const data=await api('/api/routes/'+id+'/position');
      return {state:data.state||'unavailable',position:data.position||null};
    }catch(_){return {state:'unavailable',position:null};}
  }
  async function updateGPS(){
    const epoch=state.epoch,ids=state.routes.map(r=>Number(r.id));
    for(let i=0;i<ids.length;i+=4){
      if(epoch!==state.epoch||!visible())return;
      const batch=ids.slice(i,i+4),results=await Promise.all(batch.map(checkGPS));
      if(epoch!==state.epoch||!visible())return;
      batch.forEach((id,index)=>state.gps.set(id,results[index]));
      paintCards();drawGPS();
    }
  }
  async function refresh(){
    if(state.loading||!visible()||!state.id)return;
    state.loading=true;
    try{
      const routes=(await api('/api/routes/operativi')).filter(r=>r.status==='in_corso');
      const selected=routes.find(r=>Number(r.id)===Number(state.id));
      if(!selected){await loadDashboardInProgressPage();return;}
      const detail=await api('/api/routes/'+selected.id);
      if(!visible())return;
      const hash=fingerprint(routes,detail);
      if(hash!==state.hash)render(routes,detail);
      else{state.routes=routes;await updateGPS();}
    }catch(e){console.warn('Aggiornamento giri in corso',e);}
    finally{state.loading=false;}
  }
  function fingerprint(routes,detail){
    return JSON.stringify({routes:routes.map(r=>[r.id,r.completed_count,r.missed_count,r.rientro_stimato_aggiornato,r.unread_driver_messages]),
      stops:(detail.consegne||[]).map(d=>[d.id,d.delivery_status,d.motivo_mancata,d.completata_il]),eta:detail.rientro_stimato_aggiornato});
  }
  function render(routes,detail){
    const page=root();if(!page)return;
    stopMap();
    state.routes=routes.filter(r=>r.status==='in_corso');
    state.detail=detail;state.id=detail?.id||null;
    state.gps.clear();
    if(!detail||!state.routes.length){
      page.innerHTML='<section class="gf-panel"><div class="gf-empty"><h2>Nessun giro in corso</h2><p>Qui compariranno i giri quando gli autisti li avviano.</p><button type="button" class="gf-button" data-variant="primary" data-ip-action="plan">Pianifica un giro</button></div></section>';
      suspend();return;
    }
    const draft=page.querySelector?.('#dashAdminChatInput')?.value||'';
    const chatUnread=n(state.routes.find(r=>Number(r.id)===Number(detail.id))?.unread_driver_messages);
    const rows=detail.consegne||[],s=stat(detail),progress=s.total?Math.round(100*(s.done+s.miss)/s.total):0;
    const plan=gfPlannedArrivalDates(detail,rows),fuelLabel=gfRouteEnergyMetric(detail).electric?'Costo energia':'Carburante';
    const eta=detail.rientro_stimato_aggiornato||detail.orario_rientro_stimato||'—';
    const kpi=(label,value,sub)=>'<div class="gf-details__item"><dt>'+esc(label)+'</dt><dd><strong>'+esc(value)+'</strong><br><small class="gf-muted">'+esc(sub||'')+'</small></dd></div>';
    const svgIcon=name=>icon(name).replace('<svg ','<svg class="gf-icon" ');
    const updated=new Date().toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit'});
    page.innerHTML=`
      <section class="gf-panel" aria-label="Giri attivi">
        <header class="gf-panel__header">
          <div><h2 class="gf-panel__title">Giri attivi (<span data-ip-count></span>)</h2><p class="gf-muted">Aggiornamento automatico ogni 30 secondi, ultimo alle ${esc(updated)}</p></div>
        </header>
        <div class="gf-panel__body gf-cluster" data-ip-picker role="radiogroup" aria-label="Scegli il giro da aprire"></div>
      </section>
      <section class="gf-route-panel" aria-label="Dettaglio del giro selezionato">
        <div class="gf-route-panel__map">
          <div class="gf-route-panel__heading"><div><h2 class="gf-title">${esc(detail.nome||'Giro consegne')}</h2><p class="gf-muted">Percorso stradale pianificato e posizione GPS dell’autista</p></div>
            <div class="gf-cluster">${chip('In corso')}${detail.google_maps_url?'<a class="gf-button" data-variant="primary" data-size="sm" href="'+esc(detail.google_maps_url)+'" target="_blank" rel="noopener noreferrer">'+svgIcon('map')+' Apri navigazione</a>':''}</div></div>
          <div class="gf-ip-map-wrap">
            <div class="gf-ip-map-canvas" aria-label="Mappa del giro selezionato"></div>
            <div class="gf-ip-map-badge unknown"></div>
            <div class="gf-ip-map-controls">
              <button type="button" data-ip-action="zoom-in" aria-label="Ingrandisci">+</button>
              <button type="button" data-ip-action="zoom-out" aria-label="Riduci">−</button>
              <button type="button" data-ip-action="follow" aria-label="Segui il mezzo" aria-pressed="false" disabled>${icon('target')}</button>
            </div>
            <div class="gf-ip-map-stats"><span>${gfCount(s.total,"fermata","fermate")}</span><span>${esc(km(detail.totale_km))}</span><span class="gf-ip-map-gps">GPS in attesa</span></div>
            <div class="gf-ip-map-warning" role="status"></div>
          </div>
          <div class="gf-legend"><span>${svgIcon('target')}Mezzo GPS</span><span><i data-state="done"></i>Completata</span><span><i></i>Da fare</span><span><i data-state="miss"></i>Mancata</span></div>
        </div>
        <div class="gf-route-panel__detail">
          <div class="gf-panel__body gf-stack">
            <h2 class="gf-subtitle">Indicatori del giro</h2>
            <dl class="gf-details">
              ${kpi('Avanzamento',progress+'%',s.done+s.miss+' su '+s.total+' fermate gestite')}
              ${kpi('Consegne',s.done+'/'+s.total,s.miss+' mancate · '+s.todo+' da fare')}
              ${kpi('Rientro stimato',eta,detail.eta_label||'Orario previsto')}
              ${kpi('Percorso',km(detail.totale_km),detail.totale_minuti!=null?Math.round(detail.totale_minuti)+' min previsti':'Durata non disponibile')}
              ${kpi(fuelLabel,money(detail.costo_carburante),'Costo stimato')}
              ${kpi('Pedaggi',money(detail.toll_estimated_eur),detail.toll_status==='estimated'?'Stima disponibile':'Stima non disponibile')}
            </dl>
          </div>
          <div class="gf-route-panel__footer gf-cluster">
            <button type="button" class="gf-button" data-variant="secondary" data-ip-action="refresh">${svgIcon('refresh')} Aggiorna dati</button>
            <button type="button" class="gf-button" data-variant="secondary" data-ip-action="chat" aria-haspopup="dialog" aria-expanded="${state.chat}">${svgIcon('chat')} Chat autista${chatUnread?' <span class="gf-badge" data-status="danger">'+chatUnread+'</span>':''}</button>
            ${!window.GFCompanyAccess?.isCollaborator()||window.GFCompanyAccess.can('routes.manage')?'<button type="button" class="gf-button" data-variant="secondary" data-ip-action="complete">Chiudi giro</button><button type="button" class="gf-button" data-variant="danger" data-ip-action="cancel">Annulla giro</button>':''}
          </div>
        </div>
      </section>
      <section class="gf-panel" aria-label="Fermate del giro">
        <header class="gf-panel__header"><div><h2 class="gf-panel__title">Fermate del giro</h2><p class="gf-muted">Confronto tra arrivo previsto e arrivo reale registrato dall’autista</p></div>
          <select class="gf-select" data-ip-outcome-filter aria-label="Filtra fermate per esito"><option value="all">Tutti gli esiti</option><option value="done">Completate</option><option value="miss">Mancate</option><option value="todo">Da fare</option></select></header>
        <div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards">
          <thead><tr><th scope="col">#</th><th scope="col">Cliente</th><th scope="col">Indirizzo</th><th scope="col">Arrivo previsto</th><th scope="col">Arrivo reale</th><th scope="col">Differenza</th><th scope="col">Scarico</th><th scope="col">Stato</th><th scope="col">Documenti e tracking</th></tr></thead>
          <tbody>${GFDriverBreaks.table(detail,0,9)}${rows.map((d,i)=>stopRow(d,i,detail,plan)+GFDriverBreaks.table(detail,i+1,9)).join('')||'<tr><td colspan="9"><div class="gf-empty"><p>Nessuna fermata registrata.</p></div></td></tr>'}${gfReturnRow(detail,[['#',''],['Cliente',GF_RETURN_TITLE],['Indirizzo',''],
            ['Arrivo previsto','<strong>'+gfReturnPlanned(detail)+'</strong>'],['Arrivo reale',''],['Differenza',''],['Scarico',''],['Stato',''],['Documenti e tracking','']])}</tbody>
        </table></div>
      </section>
      <div class="gf-overlay" data-ip-chat ${state.chat?'':'hidden'}>
        <div class="gf-modal" role="dialog" aria-modal="true" aria-labelledby="dashChatTitle">
          <header class="gf-modal__header"><div><p class="gf-kicker">${esc(detail.nome||'Giro in corso')}</p><h2 class="gf-modal__title" id="dashChatTitle">Chat con ${esc(detail.driver_name||'l’autista')}</h2><small class="gf-muted" id="dashChatStatus">Messaggi collegati a questo giro</small></div>
            <button type="button" class="gf-icon-button" data-ip-action="chat-close" aria-label="Chiudi la chat"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12 M18 6L6 18"/></svg></button></header>
          <div class="gf-modal__body"><div class="gf-chat">
            <div id="dashAdminChatMessages" class="gf-chat__messages" aria-live="polite"><div class="gf-loading" role="status">Caricamento chat…</div></div>
            <div class="gf-chat__composer"><textarea class="gf-textarea" id="dashAdminChatInput" rows="2" placeholder="Scrivi all’autista…" aria-label="Messaggio all'autista"></textarea><button type="button" class="gf-button" data-variant="primary" data-ip-action="send">Invia</button></div>
          </div></div>
        </div>
      </div>`;
    // Un aggiornamento della pagina non cancella il messaggio che si sta scrivendo.
    const input=page.querySelector('#dashAdminChatInput');if(input&&draft)input.value=draft;
    page.querySelector('[data-ip-outcome-filter]').value=state.outcome;
    paintCards();paintOutcome();drawGPS();drawMap(Number(detail.id));updateGPS();
    if(state.chat)loadDashboardRouteChat(Number(detail.id),false);
    if(!state.timer)state.timer=setInterval(refresh,30000);
    state.hash=fingerprint(state.routes,detail);
  }
  document.addEventListener('click',async event=>{
    const page=root();if(!page||!page.contains(event.target))return;
    // Clic sullo sfondo scuro del pop-up: la chat si chiude.
    if(event.target.matches?.('[data-ip-chat]')){openChat(false);return;}
    const filter=event.target.closest('[data-ip-filter]');
    if(filter){state.filter=filter.dataset.ipFilter;paintCards();return;}
    const card=event.target.closest('[data-ip-route]');
    if(card){const id=Number(card.dataset.ipRoute);if(id!==Number(state.id))openDashboardInProgressPage(id);return;}
    const note=event.target.closest('[data-ip-note]');
    if(note){alert(note.dataset.ipNote);return;}
    const row=event.target.closest('[data-ip-stop]');
    if(row&&!event.target.closest('button,a,details')){focusStop(row.dataset.ipStop);return;}
    const action=event.target.closest('[data-ip-action]');
    if(!action)return;
    switch(action.dataset.ipAction){
      // Un giro nuovo parte sempre dagli Ordini (o dai Clienti), mai dalla programmazione vuota.
      case 'plan':(window.openPlanningSelection||(()=>showTab('ordini')))();break;
      case 'zoom-in':state.map?.zoomIn();break;
      case 'zoom-out':state.map?.zoomOut();break;
      case 'follow':state.follow=!state.follow;drawGPS();break;
      case 'refresh':refresh();break;
      case 'complete':{
        const id=Number(state.id),name=state.detail?.nome||'Giro consegne';
        if(!id||action.disabled||!confirm('Chiudere il giro "'+name+'"? Le consegne non registrate restano senza esito; autista e mezzo tornano disponibili.'))break;
        action.disabled=true;
        try{
          await api('/api/routes/'+id+'/complete',{method:'POST'});
          toast('Giro chiuso: autista e mezzo disponibili');
          await loadDashboardInProgressPage();
        }catch(e){toast(e.message);}
        finally{action.disabled=false;}
        break;
      }
      case 'cancel':{
        const id=Number(state.id),name=state.detail?.nome||'Giro consegne';
        if(!id||action.disabled||!confirm('Annullare il giro "'+name+'"? Autista e mezzo saranno liberati. Gli esiti già registrati resteranno conservati.'))break;
        action.disabled=true;
        try{
          await api('/api/routes/'+id+'/cancel',{method:'POST'});
          toast('Giro annullato: autista e mezzo disponibili');
          await loadDashboardInProgressPage();
        }catch(e){toast(e.message);}
        finally{action.disabled=false;}
        break;
      }
      case 'chat':
        openChat(true);
        break;
      case 'chat-close':
        openChat(false);
        break;
      case 'send':sendDashboardRouteChat(Number(state.id));break;
    }
  });
  // Chat dell'autista in un pop-up: si apre dal riquadro in alto, si chiude con la X, Esc o un clic fuori.
  function openChat(open){
    const page=root(),box=page?.querySelector('[data-ip-chat]');if(!box)return;
    state.chat=open;box.hidden=!open;
    page.querySelector('[data-ip-action="chat"]')?.setAttribute('aria-expanded',String(open));
    if(open){loadDashboardRouteChat(Number(state.id),true);page.querySelector('#dashAdminChatInput')?.focus();}
    else page.querySelector('[data-ip-action="chat"]')?.focus();
  }
  document.addEventListener('change',event=>{
    if(event.target.matches('#tab-dashboard-in-progress [data-ip-outcome-filter]')){state.outcome=event.target.value;paintOutcome();}
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&state.chat&&visible()){openChat(false);return;}
  });
  return {render,suspend,refresh};
})();
