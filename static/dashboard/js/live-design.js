/* Live-route presentation; the GPS host is moved, never duplicated, in the dialog. */
window.GFLiveDesign = (() => {
  let dialog, placeholder, previousFocus;
  const paths={
    user:'<circle cx="12" cy="7" r="4"/><path d="M4 21v-2c0-7 16-7 16 0v2z"/>',
    car:'<path d="m4 10 2-6h12l2 6M3 10h18v9H3zM5 19v2m14-2v2M6 14h2m8 0h2"/>',
    chart:'<rect x="3" y="14" width="3" height="7" rx="1"/><rect x="10" y="9" width="3" height="12" rx="1"/><rect x="17" y="3" width="3" height="18" rx="1"/>',
    box:'<path d="M4 8h16v13H4zM4 8l4-5h9l3 5M9 3v5h11M13 12h7"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    fuel:'<path d="M4 21V3h10v18M4 8h10M2 21h14m-2-10h2v7a2 2 0 0 0 4 0V9l-3-3"/>',
    toll:'<path d="M3 5h18v4H3zM5 9v12h5V9m6 0v12h4V9M6 7h1m5 0h1m5 0h1"/>',
    coins:'<ellipse cx="9" cy="12" rx="7" ry="3"/><path d="M2 12v4c0 4 14 4 14 0v-4M2 16v4c0 4 14 4 14 0v-4M11 5c0-4 12-4 12 0s-12 4-12 0Zm12 0v4c0 2-3 3-6 3m6-3v5c0 2-2 3-5 3"/>',
    pin:'<path d="M12 22S4 13 4 9a8 8 0 0 1 16 0c0 4-8 13-8 13Z"/><circle cx="12" cy="9" r="2"/>',
    map:'<path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2zM9 3v16m6-14v16"/>',
    bolt:'<path d="m14 2-10 12h7l-1 8 10-13h-7z"/>',
    chat:'<path d="M21 11a9 8 0 0 1-12 8l-6 2 1-6a9 8 0 1 1 17-4ZM7 8h10M7 12h7"/>',
    expand:'<path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>',
    calendar:'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 2v6m8-6v6M4 11h16"/>',
    close:'<path d="m5 5 14 14M5 19 19 5"/>'
  };
  const svg=name=>`<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
  const icon=(name,color='blue')=>`<span class="live-design-icon ${color}">${svg(name)}</span>`;
  const card=(label,value,name,color='blue',detail='')=>`<div class="live-design-card">${icon(name,color)}<div><span>${esc(label)}</span><strong>${esc(value)}</strong>${detail?`<small>${esc(detail)}</small>`:''}</div></div>`;
  function closeMap(){if(dialog?.open)dialog.close();}
  function openMap(){
    const host=document.getElementById('dashboardLiveGPS');
    if(!host || dialog?.open)return;
    previousFocus=document.activeElement;
    placeholder=document.createElement('div');host.before(placeholder);
    dialog=document.createElement('dialog');dialog.className='live-map-dialog';
    const modal=dialog, slot=placeholder, focusTarget=previousFocus;
    dialog.setAttribute('aria-labelledby','liveMapDialogTitle');
    dialog.innerHTML=`<header><h2 id="liveMapDialogTitle">Posizione del mezzo</h2><button type="button" aria-label="Chiudi mappa">${svg('close')}</button></header><div class="live-map-dialog-body"></div>`;
    document.body.append(dialog);dialog.querySelector('.live-map-dialog-body').append(host);
    dialog.querySelector('button').onclick=closeMap;
    dialog.addEventListener('click',e=>{if(e.target===dialog){const b=dialog.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)closeMap();}});
    dialog.addEventListener('close',()=>{
      if(slot.isConnected)slot.replaceWith(host);
      modal.remove();if(dialog===modal)dialog=null;
      if(!dialog?.open)document.body.classList.remove('live-map-dialog-open');
      window.GiroFacileLiveMap.resize();
      if(!dialog?.open && focusTarget?.isConnected)focusTarget.focus();
    },{once:true});
    document.body.classList.add('live-map-dialog-open');dialog.showModal();
    requestAnimationFrame(()=>window.GiroFacileLiveMap.resize());
  }
  function decorate(page,r,progress){
    const old=page.querySelector('.dash-sub-layout');if(!old)return;
    const sections=old.querySelectorAll('.dash-sub-main > section');
    const gps=sections[0],stops=sections[1],chat=sections[2];
    const rows=r.consegne || [],done=rows.filter(d=>(d.delivery_status||d.status)==='completata').length;
    const picker=old.querySelector('.dash-sub-route-picker');
    const summary=stops.querySelector('.gf-routing-summary');
    const eta=summary?.querySelector('.gf-routing-eta');
    const costs=summary?.querySelector('.gf-routing-costs');
    const header=document.createElement('div');header.className='live-design-top';
    header.innerHTML=`<div class="live-design-picker"></div><div class="live-design-identity">${card('Autista',r.driver_name||'Non assegnato','user')}${card('Mezzo',r.vehicle_name||'Non assegnato','car')}${card('Avanzamento',`${progress}%`,'chart','green')}${card('Consegne',`${done} / ${rows.length}`,'box','purple')}${card('Rientro stimato',r.rientro_stimato_aggiornato||r.orario_rientro_stimato||'—','clock')}</div><div class="live-design-costs"></div>`;
    header.querySelector('.live-design-picker').append(picker);
    const date=r.data_giro===todayIso()?'Oggi':(r.data_giro||'—').split('-').reverse().join('/');
    header.querySelector('.live-design-picker').insertAdjacentHTML('beforeend',`<span class="live-design-date">${icon('calendar')}${esc(date)}</span>`);
    const metrics=header.querySelector('.live-design-costs');
    if(eta){eta.classList.add('live-design-card','live-eta');eta.insertAdjacentHTML('afterbegin',icon('car','red'));const content=document.createElement('div');Array.from(eta.children).slice(1).forEach(el=>content.append(el));eta.append(content);metrics.append(eta);}
    if(costs)Array.from(costs.children).forEach((el,i)=>{el.classList.add('live-design-card');const content=document.createElement('div');while(el.firstChild)content.append(el.firstChild);el.append(content);el.insertAdjacentHTML('afterbegin',icon(['fuel','toll','coins'][i],['green','purple','orange'][i]));metrics.append(el);});
    metrics.insertAdjacentHTML('beforeend',card('Km previsti',`${r.totale_km??'—'} km`,'pin')+card('Tempo previsto',`${Math.round(r.totale_minuti||0)} min`,'clock'));
    summary?.remove();
    stops.querySelector('.gf-route-summary-cards')?.remove();
    // Keep only the existing heading and complete table, preserving documents and notes.
    Array.from(stops.children).forEach(el=>{if(!el.matches('.dash-sub-card-title,.gf-unified-stop-wrap,.dash-detail-empty'))el.remove();});
    const heading=stops.querySelector('.dash-sub-card-title');heading.querySelector('.dash-sub-icon').innerHTML=icon('pin','red');
    heading.insertAdjacentHTML('beforeend',`<div class="live-design-table-actions"><select aria-label="Filtra fermate per stato"><option value="">Tutti gli esiti</option><option value="in_attesa">Da fare</option><option value="completata">Completate</option><option value="mancata">Mancate</option></select><button type="button" onclick="GFLiveDesign.openMap()">${svg('map')}Visualizza su mappa</button></div>`);
    heading.querySelector('select').onchange=e=>stops.querySelectorAll('tbody tr').forEach((tr,i)=>{tr.hidden=!!e.target.value&&(rows[i].delivery_status||rows[i].status||'in_attesa')!==e.target.value;});
    const table=stops.querySelector('table');
    if(table){
      table.querySelector('thead tr').insertAdjacentHTML('beforeend','<th>Azioni</th>');
      table.querySelectorAll('tbody tr').forEach((tr,i)=>{
        const cell=document.createElement('td');cell.className='live-stop-actions';
        cell.innerHTML=`<details><summary aria-label="Azioni fermata ${i+1}">›</summary><a href="${esc(mapsAddressUrl(rows[i].indirizzo||''))}" target="_blank" rel="noopener noreferrer">Apri indirizzo in Maps</a></details>`;
        tr.append(cell);
      });
    }
    gps.querySelector('.dash-sub-icon').innerHTML=icon('pin','red');
    gps.querySelector('.dash-sub-card-title').insertAdjacentHTML('beforeend',`<button type="button" class="live-expand" aria-label="Espandi mappa" title="Espandi mappa" onclick="GFLiveDesign.openMap()">${svg('expand')}</button>`);
    gps.querySelector('.gf-live-map-wrap').after(gps.querySelector('.gf-live-meta'));
    const sidebar=document.createElement('aside');sidebar.className='live-design-side';sidebar.append(gps);
    const actions=document.createElement('section');actions.className='live-design-actions';
    actions.innerHTML=`<h2>${icon('bolt')}Azioni rapide</h2>${r.google_maps_url?`<a class="live-primary" href="${esc(r.google_maps_url)}" target="_blank" rel="noopener noreferrer">${svg('map')}Apri in Google Maps</a>`:`<button type="button" disabled>Google Maps non disponibile</button>`}<button type="button" disabled title="Il ricalcolo del traffico è disponibile prima dell’avvio del giro">${svg('clock')}Aggiorna ETA con traffico</button><small>Ricalcolo traffico disponibile prima dell’avvio.</small><button type="button" class="live-chat-toggle" aria-expanded="false">${svg('chat')}Apri chat autista${r.unread_driver_messages?` (${Number(r.unread_driver_messages)})`:''}</button><button type="button" onclick="showTab('dashboard')">${svg('close')}Chiudi controllo</button>`;
    sidebar.append(actions);chat.classList.add('live-design-chat');chat.hidden=true;
    actions.querySelector('.live-chat-toggle').onclick=e=>{chat.hidden=!chat.hidden;e.currentTarget.setAttribute('aria-expanded',String(!chat.hidden));if(!chat.hidden){chat.scrollIntoView({behavior:'smooth',block:'center'});chat.querySelector('textarea').focus({preventScroll:true});}};
    const content=document.createElement('div');content.className='live-design-content';
    const main=document.createElement('main');main.className='dash-sub-main live-design-main';main.append(stops,chat);content.append(main,sidebar);
    page.replaceChildren(header,content);
  }
  return {decorate,openMap,closeMap};
})();
