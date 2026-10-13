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
    const s=stat(route);
    return '<span class="gf-ip-bar" role="img" aria-label="'+s.done+' completate, '+s.miss+' mancate, '+s.todo+' da fare">'+
      (s.done?'<i class="done" style="flex:'+s.done+'"></i>':'')+
      (s.miss?'<i class="miss" style="flex:'+s.miss+'"></i>':'')+
      (s.todo?'<i class="todo" style="flex:'+s.todo+'"></i>':'')+'</span>';
  }
  const chip=(label,type='blue')=>'<span class="gf-ip-chip '+type+'">'+esc(label)+'</span>';
  const issue=r=>stat(r).miss>0 || n(r.delay_minutes)>0 || r.late===true;
  function routeCard(r){
    const s=stat(r),p=state.gps.get(Number(r.id)),chosen=Number(state.id)===Number(r.id);
    return '<button type="button" class="gf-ip-route-card" role="radio" data-ip-route="'+Number(r.id)+'" aria-checked="'+chosen+'" tabindex="'+(chosen?0:-1)+'">'+
      '<span class="gf-ip-route-top"><span class="gf-ip-avatar">'+esc(initials(r.driver_name))+'</span><span class="gf-ip-route-person"><b>'+esc(r.driver_name||'Autista non assegnato')+
      '</b><small>'+esc(r.vehicle_name||'Mezzo non assegnato')+'</small></span>'+chip(issue(r)?'Da verificare':'In corso',issue(r)?'amber':'blue')+'</span>'+bar(r)+
      '<span class="gf-ip-route-meta"><span><b>'+s.done+'/'+s.total+'</b> consegne</span>'+
      (s.miss?'<span class="gf-ip-danger"><b>'+s.miss+'</b> mancate</span>':'')+
      '<span>Rientro <b>'+esc(r.rientro_stimato_aggiornato||r.orario_rientro_stimato||'—')+'</b></span>'+
      '<span class="gf-ip-gps '+gpsClass(p)+'"><i></i>'+esc(gpsText(p))+'</span></span></button>';
  }
  function filtered(){
    return state.routes.filter(r=>state.filter==='issue'?issue(r):
      state.filter==='gps'?(state.gps.get(Number(r.id))?.state||'fresh')!=='fresh':true);
  }
  function paintCards(){
    const page=root();if(!page)return;
    const box=page.querySelector('.gf-ip-picker');if(!box)return;
    const visible=filtered();
    box.innerHTML=visible.length?visible.map(routeCard).join(''):'<p class="gf-ip-empty-filter">Nessun giro corrisponde al filtro selezionato.</p>';
    const issueCount=state.routes.filter(issue).length;
    const gpsCount=state.routes.filter(r=>state.gps.has(Number(r.id))&&state.gps.get(Number(r.id)).state!=='fresh').length;
    [['all','Tutti ('+state.routes.length+')'],['issue','Con mancate o ritardi ('+issueCount+')'],['gps','GPS non aggiornato ('+gpsCount+')']].forEach(([key,label])=>{
      const b=page.querySelector('[data-ip-filter="'+key+'"]');
      if(b){b.textContent=label;b.setAttribute('aria-pressed',String(state.filter===key));}
    });
    const count=page.querySelector('.gf-ip-count');
    if(count)count.textContent=state.routes.length+' '+(state.routes.length===1?'giro attivo':'giri attivi');
  }
  function stopRow(d,i,r,planned){
    const type=outcome(d),notes=d.note_operatore||d.note_autista||d.note||'';
    const title=type==='done'?'Completata':type==='miss'?'Mancata':'Da fare';
    const time=gfRealArrival(d);
    return '<tr data-ip-stop="'+i+'" data-ip-outcome="'+type+'">'+
      '<td><span class="gf-ip-index '+type+'">'+(i+1)+'</span></td>'+
      '<td><strong>'+esc(d.cliente_nome||'—')+'</strong></td><td>'+esc(d.indirizzo||'—')+'</td>'+
      '<td>'+esc(gfPlannedArrival(d)||'—')+'</td><td>'+esc(time||'—')+'</td>'+
      '<td>'+gfDeltaBadge(planned[i],gfRealArrivalDate(d))+'</td>'+
      '<td>'+chip(title,type==='done'?'green':type==='miss'?'red':'neutral')+
      (d.motivo_mancata?'<small class="gf-ip-reason">'+esc(d.motivo_mancata)+'</small>':'')+'</td>'+
      '<td><div class="gf-ip-table-actions">'+deliverySignatureAction(d,r.driver_name)+' '+trackingButton(d,r)+
      (notes?'<button type="button" class="gf-ip-mini" data-ip-note="'+esc(notes)+'">Note</button>':'')+
      '</div></td></tr>';
  }
  function paintOutcome(){
    root()?.querySelectorAll('tr[data-ip-outcome]').forEach(tr=>tr.hidden=state.outcome!=='all'&&tr.dataset.ipOutcome!==state.outcome);
  }
  function highlight(index,on){
    root()?.querySelectorAll('[data-ip-stop="'+index+'"],[data-ip-pin="'+index+'"]').forEach(el=>el.classList.toggle('hl',on));
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
    const follow=page?.querySelector('[data-ip-action="follow"]');
    if(follow){follow.disabled=!p;follow.setAttribute('aria-pressed',String(state.follow));}
    if(!state.map||!p)return;
    const lat=Number(p.latitude),lon=Number(p.longitude);
    if(!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180)return;
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
      page.innerHTML='<section class="gf-ip-panel gf-ip-empty"><h2>Nessun giro in corso</h2><p>Qui compariranno i giri quando gli autisti li avviano.</p><button type="button" data-ip-action="plan">Pianifica un giro</button></section>';
      suspend();return;
    }
    const rows=detail.consegne||[],s=stat(detail),progress=s.total?Math.round(100*(s.done+s.miss)/s.total):0;
    const plan=gfPlannedArrivalDates(detail,rows),fuelLabel=gfRouteEnergyMetric(detail).electric?'Costo energia':'Carburante';
    const eta=detail.rientro_stimato_aggiornato||detail.orario_rientro_stimato||'—';
    const kpi=(label,value,sub)=>'<div class="gf-ip-kpi"><dt>'+esc(label)+'</dt><dd>'+esc(value)+'</dd><small>'+esc(sub||'')+'</small></div>';
    page.innerHTML=`
      <section class="gf-ip-panel gf-ip-picker-panel" aria-label="Giri attivi">
        <div class="gf-ip-panel-heading"><h2>Giri attivi</h2><span class="gf-ip-count"></span><span class="gf-ip-auto"><i></i>Aggiornamento automatico</span>
          <div class="gf-ip-filters" role="group" aria-label="Filtra i giri">
            <button type="button" data-ip-filter="all">Tutti</button>
            <button type="button" data-ip-filter="issue">Con mancate o ritardi</button>
            <button type="button" data-ip-filter="gps">GPS non aggiornato</button>
          </div>
        </div>
        <div class="gf-ip-picker" role="radiogroup" aria-label="Seleziona un giro"></div>
      </section>
      <section class="gf-ip-panel gf-ip-hero" aria-label="Dettaglio del giro selezionato">
        <div class="gf-ip-hero-map">
          <div class="gf-ip-hero-heading"><div><h2>${esc(detail.nome||'Giro consegne')}</h2><p>Percorso stradale pianificato e posizione GPS dell’autista</p></div>${chip('In corso')}</div>
          <div class="gf-ip-map-wrap">
            <div class="gf-ip-map-canvas" aria-label="Mappa del giro selezionato"></div>
            <div class="gf-ip-map-badge unknown"></div>
            <div class="gf-ip-map-controls">
              <button type="button" data-ip-action="zoom-in" aria-label="Ingrandisci">+</button>
              <button type="button" data-ip-action="zoom-out" aria-label="Riduci">−</button>
              <button type="button" data-ip-action="follow" aria-label="Segui il mezzo" aria-pressed="false" disabled>${icon('target')}</button>
            </div>
            <div class="gf-ip-map-stats"><span>${s.total} fermate</span><span>${esc(km(detail.totale_km))}</span><span class="gf-ip-map-gps">GPS in attesa</span></div>
            <div class="gf-ip-map-warning" role="status"></div>
          </div>
          <div class="gf-ip-legend"><span><i class="van"></i>Mezzo GPS</span><span><i class="done"></i>Completata</span><span><i></i>Da fare</span><span><i class="miss"></i>Mancata</span></div>
        </div>
        <div class="gf-ip-hero-side">
          <h2 class="gf-ip-side-title">Indicatori del giro</h2>
          <dl class="gf-ip-kpis">
            ${kpi('Avanzamento',progress+'%',s.done+s.miss+' su '+s.total+' fermate gestite')}
            ${kpi('Consegne',s.done+'/'+s.total,s.miss+' mancate · '+s.todo+' da fare')}
            ${kpi('Rientro stimato',eta,detail.eta_label||'Orario previsto')}
            ${kpi('Percorso',km(detail.totale_km),detail.totale_minuti!=null?Math.round(detail.totale_minuti)+' min previsti':'Durata non disponibile')}
            ${kpi(fuelLabel,money(detail.costo_carburante),'Costo stimato')}
            ${kpi('Pedaggi',money(detail.toll_estimated_eur),detail.toll_status==='estimated'?'Stima disponibile':'Stima non disponibile')}
          </dl>
          <div class="gf-ip-hero-actions">
            <button type="button" data-ip-action="refresh">${icon('refresh')} Aggiorna dati</button>
            ${detail.google_maps_url?'<a href="'+esc(detail.google_maps_url)+'" target="_blank" rel="noopener noreferrer">'+icon('map')+' Apri navigazione</a>':''}
          </div>
        </div>
      </section>
      <section class="gf-ip-panel gf-ip-stops" aria-label="Fermate del giro">
        <div class="gf-ip-panel-heading gf-ip-stops-heading"><div><h2>Fermate del giro</h2><p>Confronto tra arrivo previsto e arrivo reale registrato dall’autista</p></div>
          <select class="gf-ip-outcome" aria-label="Filtra fermate per esito"><option value="all">Tutti gli esiti</option><option value="done">Completate</option><option value="miss">Mancate</option><option value="todo">Da fare</option></select></div>
        <div class="gf-ip-table-wrap"><table class="gf-ip-table">
          <thead><tr><th>#</th><th>Cliente</th><th>Indirizzo</th><th>Arrivo previsto</th><th>Arrivo reale</th><th>Differenza</th><th>Stato</th><th>Documenti e tracking</th></tr></thead>
          <tbody>${GFDriverBreaks.table(detail,0,8)}${rows.map((d,i)=>stopRow(d,i,detail,plan)+GFDriverBreaks.table(detail,i+1,8)).join('')||'<tr><td colspan="8" class="gf-ip-empty-rows">Nessuna fermata registrata.</td></tr>'}</tbody>
        </table></div>
        <div class="gf-ip-footer"><button type="button" data-ip-action="chat" aria-expanded="${state.chat}">${icon('chat')} ${state.chat?'Chiudi':'Apri'} chat autista</button></div>
      </section>
      <section class="gf-ip-panel gf-ip-chat" ${state.chat?'':'hidden'} aria-label="Chat autista">
        <div class="gf-ip-panel-heading"><h2>Chat autista</h2><small id="dashChatStatus">Messaggi collegati a questo giro</small></div>
        <div id="dashAdminChatMessages" class="dash-admin-chat-messages"><div class="dash-empty">Caricamento chat…</div></div>
        <div class="dash-admin-chat-input"><textarea id="dashAdminChatInput" rows="2" placeholder="Scrivi all’autista…"></textarea><button type="button" data-ip-action="send">Invia</button></div>
      </section>`;
    page.querySelector('.gf-ip-outcome').value=state.outcome;
    paintCards();paintOutcome();drawGPS();drawMap(Number(detail.id));updateGPS();
    if(state.chat)loadDashboardRouteChat(Number(detail.id),false);
    if(!state.timer)state.timer=setInterval(refresh,30000);
    state.hash=fingerprint(state.routes,detail);
  }
  document.addEventListener('click',event=>{
    const page=root();if(!page||!page.contains(event.target))return;
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
      case 'plan':showTab('giro');break;
      case 'zoom-in':state.map?.zoomIn();break;
      case 'zoom-out':state.map?.zoomOut();break;
      case 'follow':state.follow=!state.follow;drawGPS();break;
      case 'refresh':refresh();break;
      case 'chat':
        state.chat=!state.chat;page.querySelector('.gf-ip-chat').hidden=!state.chat;
        action.setAttribute('aria-expanded',String(state.chat));
        action.innerHTML=icon('chat')+(state.chat?' Chiudi chat autista':' Apri chat autista');
        if(state.chat)loadDashboardRouteChat(Number(state.id),true);
        break;
      case 'send':sendDashboardRouteChat(Number(state.id));break;
    }
  });
  document.addEventListener('change',event=>{
    if(event.target.matches('#tab-dashboard-in-progress .gf-ip-outcome')){state.outcome=event.target.value;paintOutcome();}
  });
  document.addEventListener('keydown',event=>{
    if(!event.target.matches('#tab-dashboard-in-progress [data-ip-route]'))return;
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
    const arr=filtered(),i=arr.findIndex(r=>Number(r.id)===Number(event.target.dataset.ipRoute));
    if(i<0||!arr.length)return;
    event.preventDefault();
    const next=arr[(i+(['ArrowRight','ArrowDown'].includes(event.key)?1:-1)+arr.length)%arr.length];
    openDashboardInProgressPage(next.id);
  });
  return {render,suspend,refresh};
})();
