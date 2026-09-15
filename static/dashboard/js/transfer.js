// -----------------------------------------------------------------------
// v84 — Dashboard operativa Transfer dedicata
// -----------------------------------------------------------------------
function transferBookingDateTimeV84(b){
  if(!b?.pickup_date || !b?.pickup_time) return null;
  const dt=new Date(`${b.pickup_date}T${String(b.pickup_time).slice(0,5)}:00`);
  return Number.isNaN(dt.getTime())?null:dt;
}
function transferMinutesLabelV84(minutes){
  if(minutes<0) return 'In ritardo';
  if(minutes===0) return 'Adesso';
  if(minutes<60) return `Tra ${minutes} min`;
  const h=Math.floor(minutes/60), m=minutes%60;
  return `Tra ${h}h${m?` ${m}m`:''}`;
}
function transferStatusToneV84(s){
  if(['completed'].includes(s)) return 'done';
  if(['in_progress','passenger_on_board','arrived'].includes(s)) return 'live';
  if(['cancelled','rejected','no_show'].includes(s)) return 'alert';
  if(['new','pending','to_assign'].includes(s)) return 'warn';
  return 'planned';
}
function transferDriverNameV84(b,drivers){
  const d=(drivers||[]).find(x=>Number(x.id)===Number(b.driver_id));
  return d?`${d.nome||''} ${d.cognome||''}`.trim():(b.driver_name||'Da assegnare');
}
function transferVehicleNameV84(b,vehicles){
  const v=(vehicles||[]).find(x=>Number(x.id)===Number(b.vehicle_id));
  return v?`${v.nome||'Veicolo'}${v.targa?` · ${v.targa}`:''}`:(b.vehicle_name||'Nessun veicolo');
}
async function renderTransferDashboardV84(){
  const host=document.getElementById('transferDashboardV84');
  if(!host) return;
  if(gfCurrentSectorKeyV50()!=='transfer'){
    host.classList.add('hidden'); host.innerHTML=''; return;
  }
  host.classList.remove('hidden');
  host.innerHTML='<div class="transfer-dashboard-loading-v84">Caricamento centro operativo…</div>';
  try{
    const today=todayIso();
    const [summary,bookings,drivers,vehicles]=await Promise.all([
      api('/api/transfer/dashboard'),
      api(`/api/transfer/bookings?date=${today}`),
      api('/api/drivers'),
      api('/api/vehicles')
    ]);
    const now=new Date();
    const sorted=[...(bookings||[])].sort((a,b)=>(transferBookingDateTimeV84(a)?.getTime()||0)-(transferBookingDateTimeV84(b)?.getTime()||0));
    const upcoming=sorted.filter(b=>{
      const dt=transferBookingDateTimeV84(b); return dt && dt.getTime()>=now.getTime()-15*60000 && !['completed','cancelled','rejected','no_show'].includes(b.status);
    }).slice(0,4);
    const unassigned=sorted.filter(b=>!b.driver_id && !['completed','cancelled'].includes(b.status));
    const awaiting=sorted.filter(b=>['proposed','pending'].includes(b.status));
    const live=sorted.filter(b=>['in_progress','arrived','passenger_on_board'].includes(b.status));
    const confirmed=sorted.filter(b=>['accepted','planned','confirmed'].includes(b.status));
    const completed=sorted.filter(b=>b.status==='completed');
    const availableDrivers=(drivers||[]).filter(d=>!['occupato','in_corsa','non_disponibile'].includes(String(d.stato||'').toLowerCase()));
    const busyDrivers=(drivers||[]).filter(d=>['occupato','in_corsa'].includes(String(d.stato||'').toLowerCase()));

    const upcomingHtml=upcoming.length?upcoming.map((b,i)=>{
      const dt=transferBookingDateTimeV84(b); const mins=dt?Math.max(0,Math.round((dt-now)/60000)):0;
      return `<article class="transfer-next-card-v84 ${i===0?'primary':''}">
        <div class="transfer-next-time-v84"><span>${transferMinutesLabelV84(mins)}</span><strong>${esc(String(b.pickup_time||'').slice(0,5))}</strong></div>
        <div class="transfer-next-route-v84"><small>${esc(b.customer_name||'Passeggero')}</small><h3>${esc(b.pickup_address||'Partenza')}</h3><div>→ ${esc(b.destination_address||'Destinazione')}</div><p>${transferDriverNameV84(b,drivers)} · ${transferVehicleNameV84(b,vehicles)}</p></div>
        <div class="transfer-next-actions-v84"><button onclick="openGoogleRouteV79('${encodeURIComponent(b.pickup_address||'')}','${encodeURIComponent(b.destination_address||'')}')">Naviga</button><button onclick="showTab('transfer-bookings')">Dettagli</button></div>
      </article>`;
    }).join(''):'<div class="transfer-empty-v84"><strong>Nessuna partenza imminente</strong><span>Le prossime corse compariranno qui in ordine di orario.</span></div>';

    const timelineHtml=sorted.length?sorted.slice(0,8).map(b=>`<button class="transfer-timeline-item-v84 ${transferStatusToneV84(b.status)}" onclick="showTab('transfer-bookings')"><time>${esc(String(b.pickup_time||'').slice(0,5))}</time><span><b>${esc(b.customer_name||'Passeggero')}</b><small>${esc(b.pickup_address||'')} → ${esc(b.destination_address||'')}</small></span><em>${transferStatusLabelV79(b.status)}</em></button>`).join(''):'<div class="transfer-empty-v84 compact"><strong>Agenda vuota</strong><span>Nessuna prenotazione per oggi.</span></div>';

    const driversHtml=(drivers||[]).length?(drivers||[]).slice(0,6).map(d=>{
      const next=sorted.find(b=>Number(b.driver_id)===Number(d.id) && !['completed','cancelled'].includes(b.status));
      const state=String(d.stato||'Disponibile');
      const tone=['occupato','in_corsa'].includes(state.toLowerCase())?'busy':'available';
      return `<article class="transfer-driver-card-v84"><div class="transfer-driver-avatar-v84">${esc((d.nome||'A').slice(0,1).toUpperCase())}</div><div><h4>${esc(`${d.nome||''} ${d.cognome||''}`.trim()||'Autista')}</h4><span class="${tone}">${esc(state)}</span>${next?`<small>Prossima ${esc(String(next.pickup_time||'').slice(0,5))} · ${esc(next.pickup_address||'')}</small>`:'<small>Nessuna corsa assegnata</small>'}</div></article>`;
    }).join(''):'<div class="transfer-empty-v84 compact"><strong>Nessun autista</strong><span>Aggiungi il primo autista operativo.</span></div>';

    host.innerHTML=`
      <section class="transfer-ops-shell-v84">
        <header class="transfer-ops-header-v84">
          <div><span class="transfer-live-pill-v84"><i></i> Centro operativo live</span><h1>Buona giornata, gestisci le corse di oggi</h1><p>Prenotazioni, autisti e partenze imminenti in un’unica vista operativa.</p></div>
          <div class="transfer-header-actions-v84"><button class="secondary" onclick="showTab('transfer-planning')">Apri planning</button><button class="primary" onclick="openTransferBookingModalV79()">+ Nuova prenotazione</button></div>
        </header>

        <div class="transfer-live-strip-v84">
          <div><span class="dot green"></span><b>${availableDrivers.length}</b><small>autisti disponibili</small></div>
          <div><span class="dot blue"></span><b>${live.length}</b><small>corse in viaggio</small></div>
          <div><span class="dot orange"></span><b>${unassigned.length}</b><small>da assegnare</small></div>
          <div><span class="dot purple"></span><b>${awaiting.length}</b><small>in attesa risposta</small></div>
          <div><span class="dot red"></span><b>${summary?.issues||0}</b><small>criticità operative</small></div>
        </div>

        <div class="transfer-ops-grid-v84">
          <section class="transfer-panel-v84 transfer-next-v84">
            <div class="transfer-panel-head-v84"><div><span>Priorità</span><h2>Partenze imminenti</h2></div><button onclick="showTab('transfer-bookings')">Vedi prenotazioni</button></div>
            <div class="transfer-next-list-v84">${upcomingHtml}</div>
          </section>
          <aside class="transfer-panel-v84 transfer-summary-v84">
            <div class="transfer-panel-head-v84"><div><span>Situazione odierna</span><h2>Riepilogo operativo</h2></div></div>
            <div class="transfer-summary-grid-v84">
              <button onclick="showTab('transfer-bookings')"><strong>${bookings.length}</strong><span>Prenotazioni oggi</span></button>
              <button class="warn" onclick="showTab('transfer-bookings')"><strong>${unassigned.length}</strong><span>Da assegnare</span></button>
              <button class="info" onclick="showTab('transfer-bookings')"><strong>${awaiting.length}</strong><span>In attesa autista</span></button>
              <button class="live" onclick="showTab('transfer-bookings')"><strong>${live.length}</strong><span>In viaggio</span></button>
              <button class="ok" onclick="showTab('transfer-bookings')"><strong>${confirmed.length}</strong><span>Confermate</span></button>
              <button class="done" onclick="showTab('transfer-bookings')"><strong>${completed.length}</strong><span>Completate</span></button>
            </div>
          </aside>
        </div>

        <div class="transfer-bottom-grid-v84">
          <section class="transfer-panel-v84"><div class="transfer-panel-head-v84"><div><span>Agenda</span><h2>Programma della giornata</h2></div><button onclick="showTab('transfer-planning')">Planning completo</button></div><div class="transfer-timeline-v84">${timelineHtml}</div></section>
          <section class="transfer-panel-v84"><div class="transfer-panel-head-v84"><div><span>Squadra</span><h2>Stato autisti</h2></div><button onclick="showTab('autisti')">Gestisci autisti</button></div><div class="transfer-drivers-v84">${driversHtml}</div></section>
        </div>

        <section class="transfer-map-placeholder-v84">
          <div><span>Mappa operativa</span><h2>Vista live della flotta</h2><p>La posizione degli autisti e le tratte attive saranno visualizzate qui quando il tracking sarà disponibile.</p></div>
          <button onclick="showTab('transfer-planning')">Apri planning corse</button>
        </section>
      </section>`;
  }catch(e){
    host.innerHTML=`<div class="transfer-dashboard-error-v84"><strong>Impossibile caricare la Dashboard Transfer</strong><span>${esc(e.message||e)}</span><button onclick="renderTransferDashboardV84()">Riprova</button></div>`;
  }
}

// -----------------------------------------------------------------------
// v79 — Centro operativo Transfer
// -----------------------------------------------------------------------
let gfTransferBookingsV79=[];
let gfTransferDriversV79=[];
let gfTransferVehiclesV79=[];

function transferStatusLabelV79(s){ return ({new:'Nuova',pending:'In attesa',to_assign:'Da assegnare',proposed:'Proposta',accepted:'Accettata',arrived:'Autista arrivato',passenger_on_board:'Passeggero a bordo',in_progress:'In corso',completed:'Completata',rejected:'Rifiutata',cancelled:'Annullata',no_show:'No-show'})[s]||s||'Nuova'; }
function transferStatusClassV79(s){ return ['completed','accepted'].includes(s)?'ok':['cancelled','rejected','no_show'].includes(s)?'bad':['proposed','in_progress','arrived','passenger_on_board'].includes(s)?'info':'warn'; }
function transferDateHumanV79(v){ if(!v)return '—'; const [y,m,d]=v.split('-'); return `${d}/${m}/${y}`; }

async function hydrateTransferDashboardV79(){
  if(gfCurrentSectorKeyV50()!=='transfer') return;
  try{
    const d=await api('/api/transfer/dashboard');
    const kpis=document.querySelectorAll('#logisticsDashboardV50 .transfer-kpi-grid-v54 > div strong');
    const values=[d.today,d.active,d.pending,d.completed,d.unassigned,`${d.drivers_busy}/${d.drivers_available}`];
    kpis.forEach((x,i)=>{if(values[i]!==undefined)x.textContent=values[i]});
    const modules=document.querySelector('#logisticsDashboardV50 .transfer-modules-v54');
    if(modules){ modules.innerHTML=`
      <button onclick="showTab('transfer-bookings')"><b>Prenotazioni</b><span>${d.pending} nuove richieste e ${d.unassigned} corse da assegnare.</span></button>
      <button onclick="showTab('transfer-planning')"><b>Planning giornaliero</b><span>Agenda autisti, orari e compatibilità delle corse.</span></button>
      <button onclick="showTab('autisti')"><b>Autisti e disponibilità</b><span>${d.drivers_available} disponibili, ${d.drivers_busy} impegnati.</span></button>
      <button onclick="showTab('transfer-portal')"><b>Portale prenotazioni</b><span>Personalizza e condividi il link pubblico.</span></button>
      <button onclick="showTab('transfer-settings')"><b>Impostazioni Transfer</b><span>Modalità manuale, assistita o automatica e profilo admin-autista.</span></button>`; }
  }catch(e){ console.warn('Dashboard Transfer non aggiornata',e); }
}

async function loadTransferBookingsV79(){
  try{
    const status=document.getElementById('transferBookingStatusV79')?.value||'';
    const date=document.getElementById('transferBookingDateV79')?.value||'';
    const qs=new URLSearchParams(); if(status)qs.set('status',status); if(date)qs.set('date',date);
    [gfTransferBookingsV79,gfTransferDriversV79,gfTransferVehiclesV79]=await Promise.all([
      api('/api/transfer/bookings'+(qs.toString()?`?${qs}`:'')),api('/api/drivers'),api('/api/vehicles')
    ]);
    renderTransferBookingsV79();
    const d=await api('/api/transfer/dashboard');
    const host=document.getElementById('transferBookingKpisV79'); if(host) host.innerHTML=`<div><small>Oggi</small><strong>${d.today}</strong></div><div><small>Nuove</small><strong>${d.pending}</strong></div><div><small>Da assegnare</small><strong>${d.unassigned}</strong></div><div><small>In corso</small><strong>${d.active}</strong></div><div><small>Completate</small><strong>${d.completed}</strong></div>`;
  }catch(e){ const h=document.getElementById('transferBookingsListV79'); if(h)h.innerHTML=`<div class="empty-state error">${esc(e.message||e)}</div>`; }
}
function renderTransferBookingsV79(){
  const host=document.getElementById('transferBookingsListV79'); if(!host)return;
  const q=(document.getElementById('transferBookingSearchV79')?.value||'').toLowerCase();
  const rows=gfTransferBookingsV79.filter(b=>!q||[b.customer_name,b.phone,b.pickup_address,b.destination_address].join(' ').toLowerCase().includes(q));
  if(!rows.length){host.innerHTML='<div class="empty-state">Nessuna prenotazione trovata.</div>';return;}
  host.innerHTML=rows.map(b=>`<article class="transfer-booking-card-v79">
    <div class="transfer-booking-time-v79"><strong>${esc(b.pickup_time)}</strong><span>${transferDateHumanV79(b.pickup_date)}</span></div>
    <div class="transfer-booking-main-v79"><div class="transfer-booking-title-v79"><h3>${esc(b.customer_name)}</h3><span class="transfer-status-v79 ${transferStatusClassV79(b.status)}">${transferStatusLabelV79(b.status)}</span></div><p><b>${esc(b.pickup_address)}</b><span>→</span>${esc(b.destination_address)}</p><div class="transfer-booking-meta-v79"><span>👥 ${b.passengers||1}</span><span>☎ ${esc(b.phone||'—')}</span><span>🧳 ${esc(b.luggage||'—')}</span>${b.flight_train?`<span>✈ ${esc(b.flight_train)}</span>`:''}</div></div>
    <div class="transfer-booking-assign-v79"><label>Autista<select onchange="assignTransferBookingV79(${b.id},this.value)"><option value="">Da assegnare</option>${gfTransferDriversV79.map(d=>`<option value="${d.id}" ${Number(b.driver_id)===Number(d.id)?'selected':''}>${esc((d.nome||'')+' '+(d.cognome||''))}</option>`).join('')}</select></label><label>Mezzo<select onchange="updateTransferBookingV79(${b.id},{vehicle_id:this.value})"><option value="">Nessun mezzo</option>${gfTransferVehiclesV79.map(v=>`<option value="${v.id}" ${Number(b.vehicle_id)===Number(v.id)?'selected':''}>${esc(v.nome)}${v.targa?' · '+esc(v.targa):''}</option>`).join('')}</select></label><div class="transfer-booking-actions-v79"><button class="primary" onclick="openTransferBookingDetailV86(${b.id})">Dettagli</button><button onclick="openGoogleRouteV79('${encodeURIComponent(b.pickup_address)}','${encodeURIComponent(b.destination_address)}')">Mappa</button><button class="danger-text" onclick="updateTransferBookingV79(${b.id},{status:'cancelled'})">Annulla</button></div></div>
  </article>`).join('');
}
async function assignTransferBookingV79(id,driverId){ await updateTransferBookingV79(id,{driver_id:driverId}); }
async function updateTransferBookingV79(id,payload){ try{await api(`/api/transfer/bookings/${id}`,{method:'PUT',body:JSON.stringify(payload)}); toast('Prenotazione aggiornata'); await loadTransferBookingsV79();}catch(e){alert(e.message||e);} }
function openGoogleRouteV79(a,b){window.open(`https://www.google.com/maps/dir/?api=1&origin=${a}&destination=${b}`,'_blank');}
function openTransferBookingModalV79(){document.getElementById('transferBookingModalV79')?.classList.remove('hidden'); if(!document.getElementById('tbDateV79').value)document.getElementById('tbDateV79').value=todayIso();}
function closeTransferBookingModalV79(){document.getElementById('transferBookingModalV79')?.classList.add('hidden');}
async function saveManualTransferBookingV79(){
  const payload={customer_name:document.getElementById('tbCustomerV79').value,phone:document.getElementById('tbPhoneV79').value,email:document.getElementById('tbEmailV79').value,passengers:document.getElementById('tbPassengersV79').value,pickup_address:document.getElementById('tbPickupV79').value,destination_address:document.getElementById('tbDestinationV79').value,pickup_date:document.getElementById('tbDateV79').value,pickup_time:document.getElementById('tbTimeV79').value,service_type:document.getElementById('tbServiceV79').value,flight_train:document.getElementById('tbFlightV79').value,luggage:document.getElementById('tbLuggageV79').value,notes:document.getElementById('tbNotesV79').value};
  try{await api('/api/transfer/bookings',{method:'POST',body:JSON.stringify(payload)});closeTransferBookingModalV79();toast('Prenotazione inserita');loadTransferBookingsV79();}catch(e){alert(e.message||e);}
}

async function loadTransferPlanningV79(){
  const dateEl=document.getElementById('transferPlanningDateV79'); if(dateEl&&!dateEl.value)dateEl.value=todayIso(); const date=dateEl?.value||todayIso();
  try{[gfTransferBookingsV79,gfTransferDriversV79]=await Promise.all([api(`/api/transfer/bookings?date=${date}`),api('/api/drivers')]); renderTransferPlanningV79();}catch(e){document.getElementById('transferPlanningTimelineV79').innerHTML=`<div class="empty-state error">${esc(e.message||e)}</div>`;}
}
function renderTransferPlanningV79(){
  const host=document.getElementById('transferPlanningTimelineV79'), sum=document.getElementById('transferPlanningSummaryV79'); if(!host)return;
  const unassigned=gfTransferBookingsV79.filter(b=>!b.driver_id); if(sum)sum.innerHTML=`<div><b>${gfTransferBookingsV79.length}</b><span>corse</span></div><div><b>${gfTransferDriversV79.length}</b><span>autisti</span></div><div class="${unassigned.length?'warning':''}"><b>${unassigned.length}</b><span>da assegnare</span></div>`;
  const lanes=[{id:0,nome:'Da assegnare'},...gfTransferDriversV79.map(d=>({id:d.id,nome:`${d.nome||''} ${d.cognome||''}`.trim(),stato:d.stato}))];
  host.innerHTML=lanes.map(l=>{const bookings=gfTransferBookingsV79.filter(b=>Number(b.driver_id||0)===Number(l.id));return `<div class="transfer-lane-v79"><div class="transfer-lane-driver-v79"><strong>${esc(l.nome)}</strong><span>${l.id?(l.stato||'Disponibile'):'Trascina/assegna dal pannello Prenotazioni'}</span></div><div class="transfer-lane-events-v79">${bookings.length?bookings.map(b=>`<button class="transfer-event-v79 ${transferStatusClassV79(b.status)}" onclick="showTab('transfer-bookings')"><time>${esc(b.pickup_time)}</time><b>${esc(b.customer_name)}</b><span>${esc(b.pickup_address)} → ${esc(b.destination_address)}</span></button>`).join(''):'<div class="transfer-lane-empty-v79">Nessuna corsa</div>'}</div></div>`}).join('');
}

async function loadTransferSettingsV79(){
  try{const d=await api('/api/transfer/operations/settings'); const radio=document.querySelector(`input[name="transferDispatchModeV79"][value="${d.dispatch_mode}"]`);if(radio)radio.checked=true;document.getElementById('transferAutoStrategyV79').value=d.auto_strategy;document.getElementById('transferResponseSecondsV79').value=d.driver_response_seconds;document.getElementById('transferBufferV79').value=d.min_buffer_minutes;document.getElementById('transferAirportBufferV79').value=d.airport_buffer_minutes;document.getElementById('transferNotifyEmailV79').checked=d.notify_email;document.getElementById('transferNotifyInternalV79').checked=d.notify_internal;document.getElementById('transferAllowRejectV79').checked=d.allow_driver_reject;await refreshAdminDriverNavV79();}catch(e){console.warn(e);}
}
async function saveTransferOperationsV79(){const payload={dispatch_mode:document.querySelector('input[name="transferDispatchModeV79"]:checked')?.value||'manual',auto_strategy:document.getElementById('transferAutoStrategyV79').value,driver_response_seconds:Number(document.getElementById('transferResponseSecondsV79').value||60),min_buffer_minutes:Number(document.getElementById('transferBufferV79').value||15),airport_buffer_minutes:Number(document.getElementById('transferAirportBufferV79').value||30),notify_email:document.getElementById('transferNotifyEmailV79').checked,notify_internal:document.getElementById('transferNotifyInternalV79').checked,allow_driver_reject:document.getElementById('transferAllowRejectV79').checked};try{const r=await api('/api/transfer/operations/settings',{method:'PUT',body:JSON.stringify(payload)});toast(r.message);}catch(e){alert(e.message||e);}}
async function refreshAdminDriverNavV79(){
  if(gfCurrentSectorKeyV50()!=='transfer')return; try{const d=await api('/api/transfer/admin-driver'); const nav=document.getElementById('transferAdminDriverNavV79'),mob=document.getElementById('gfMobileTransferAdminDriverBtnV79'); [nav,mob].forEach(x=>{if(x){x.classList.toggle('hidden',!d.exists);x.style.display=d.exists?'':'none';}}); const host=document.getElementById('transferAdminDriverContentV79'); if(host)host.innerHTML=d.exists?`<div class="admin-driver-ready-v79"><span>✓ Profilo attivo</span><h3>${esc((d.driver.nome||'')+' '+(d.driver.cognome||''))}</h3><p>${esc(d.driver.email||'Account amministratore collegato')}</p><button class="primary" onclick="openAdminDriverPortalV79()">Apri portale autista</button></div>`:`<h3>Profilo autista amministratore</h3><p>Usa lo stesso account per passare dalla Dashboard al portale autista senza un secondo login.</p><button class="primary" onclick="createAdminDriverProfileV79()">Crea profilo autista per amministratore</button>`;}catch(e){}
}
async function createAdminDriverProfileV79(){if(!confirm('Creare il profilo autista collegato al tuo account amministratore?'))return;try{const r=await api('/api/transfer/admin-driver',{method:'POST',body:'{}'});toast(r.message);refreshAdminDriverNavV79();}catch(e){alert(e.message||e);}}
async function openAdminDriverPortalV79(){try{const r=await api('/api/transfer/admin-driver/enter',{method:'POST',body:'{}'});window.location.href=r.url||'/driver';}catch(e){alert(e.message||e);}}


// -----------------------------------------------------------------------
// v85 — Condivisione portale prenotazioni Transfer
// -----------------------------------------------------------------------
function transferPortalBaseUrlV85(){
  const slug=(transferValV78('tpSlugV78')||gfTransferPortalV78?.public_slug||'').trim();
  return slug?`${location.origin}/prenota/${encodeURIComponent(slug)}`:'';
}
function transferSourceSlugV85(value){
  return String(value||'').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,80);
}
function transferTrackedUrlV85(){
  const base=transferPortalBaseUrlV85();
  const source=transferSourceSlugV85(document.getElementById('tpShareSourceV85')?.value);
  return base?(source?`${base}?source=${encodeURIComponent(source)}`:base):'';
}
function refreshTransferShareV85(){
  const base=transferPortalBaseUrlV85();
  const tracked=transferTrackedUrlV85();
  const link=document.getElementById('tpShareLinkV85'); if(link) link.value=base||'Configura e salva il portale';
  const preview=document.getElementById('tpTrackedPreviewV85'); if(preview) preview.textContent=tracked||'Inserisci un nome canale per generare il link.';
  const source=transferSourceSlugV85(document.getElementById('tpShareSourceV85')?.value);
  const qr=document.getElementById('tpQrImageV85');
  if(qr && base){ qr.src=`/api/transfer/booking-portal/qr.png?size=520${source?`&source=${encodeURIComponent(source)}`:''}&_=${Date.now()}`; }
  const qrLabel=document.getElementById('tpQrSourceV85'); if(qrLabel) qrLabel.textContent=source?`QR tracciato: ${source}`:'QR collegato al link generale';
  const embed=document.getElementById('tpEmbedCodeV85');
  if(embed) embed.textContent=base?`<a href="${base}" target="_blank" rel="noopener">Prenota ora</a>`:'Salva prima il portale';
}
async function transferCopyV85(text,message){
  if(!text){ toast('Salva prima il portale','error'); return; }
  try{ await navigator.clipboard.writeText(text); toast(message||'Copiato'); }
  catch(_){ const ta=document.createElement('textarea'); ta.value=text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); toast(message||'Copiato'); }
}
function copyTransferPortalLinkV85(){ transferCopyV85(transferPortalBaseUrlV85(),'Link prenotazione copiato'); }
function copyTransferTrackedLinkV85(){ transferCopyV85(transferTrackedUrlV85(),'Link tracciato copiato'); }
function setTransferSourceV85(source){ const el=document.getElementById('tpShareSourceV85'); if(el){el.value=source;refreshTransferShareV85();} }
function transferShareMessageV85(){
  const name=transferValV78('tpCompanyNameV78')||'il nostro servizio transfer';
  return `Prenota il tuo transfer con ${name}. Inserisci partenza, destinazione, data e orario dal nostro portale:`;
}
function shareTransferWhatsappV85(){
  const url=transferTrackedUrlV85()||transferPortalBaseUrlV85(); if(!url){toast('Salva prima il portale','error');return;}
  window.open(`https://wa.me/?text=${encodeURIComponent(`${transferShareMessageV85()}\n${url}`)}`,'_blank');
}
function shareTransferEmailV85(){
  const url=transferTrackedUrlV85()||transferPortalBaseUrlV85(); if(!url){toast('Salva prima il portale','error');return;}
  const name=transferValV78('tpCompanyNameV78')||'Servizio Transfer';
  location.href=`mailto:?subject=${encodeURIComponent(`Prenota il tuo transfer con ${name}`)}&body=${encodeURIComponent(`${transferShareMessageV85()}\n\n${url}`)}`;
}
async function nativeShareTransferV85(){
  const url=transferTrackedUrlV85()||transferPortalBaseUrlV85(); if(!url){toast('Salva prima il portale','error');return;}
  const data={title:`Prenotazioni ${transferValV78('tpCompanyNameV78')||'Transfer'}`,text:transferShareMessageV85(),url};
  if(navigator.share){ try{await navigator.share(data);}catch(e){if(e?.name!=='AbortError') copyTransferPortalLinkV85();} }
  else transferCopyV85(url,'Link copiato: condividilo con l’app che preferisci');
}
function downloadTransferQrV85(){
  const source=transferSourceSlugV85(document.getElementById('tpShareSourceV85')?.value);
  const base=transferPortalBaseUrlV85(); if(!base){toast('Salva prima il portale','error');return;}
  const a=document.createElement('a'); a.href=`/api/transfer/booking-portal/qr.png?size=900${source?`&source=${encodeURIComponent(source)}`:''}`; a.download=`qr-prenotazioni-${source||'generale'}.png`; document.body.appendChild(a); a.click(); a.remove();
}
function printTransferQrV85(){
  const image=document.getElementById('tpQrImageV85')?.src; if(!image){toast('QR Code non disponibile','error');return;}
  const url=transferTrackedUrlV85()||transferPortalBaseUrlV85(); const name=transferValV78('tpCompanyNameV78')||'Servizio Transfer';
  const w=window.open('','_blank','width=720,height=850'); if(!w)return;
  w.document.write(`<!doctype html><html><head><title>QR Prenotazioni</title><style>body{font-family:Arial;text-align:center;padding:42px;color:#0f172a}img{width:420px;max-width:90%}h1{margin-bottom:8px}p{color:#475569;word-break:break-all}.box{border:1px solid #dbe3ee;border-radius:22px;padding:28px}</style></head><body><div class="box"><h1>${name}</h1><p>Scansiona per prenotare il tuo transfer</p><img src="${image}"><p>${url}</p></div><script>window.onload=()=>setTimeout(()=>window.print(),350)<\/script></body></html>`); w.document.close();
}
function copyTransferEmbedV85(){ const code=document.getElementById('tpEmbedCodeV85')?.textContent||''; if(code==='Salva prima il portale')return toast('Salva prima il portale','error'); transferCopyV85(code,'Codice HTML copiato'); }

// -----------------------------------------------------------------------
// v86 — Dettaglio prenotazione, cronologia e assegnazione assistita
// -----------------------------------------------------------------------
let gfTransferDetailV86=null;
function v86Val(id){return document.getElementById(id)?.value||'';}
async function openTransferBookingDetailV86(id){
  try{
    gfTransferDetailV86=await api(`/api/transfer/bookings/${id}`);
    const b=gfTransferDetailV86;
    document.getElementById('tbDetailTitleV86').textContent=`${b.customer_name} · ${b.pickup_date} ${b.pickup_time}`;
    const map={tbdCustomerV86:'customer_name',tbdPhoneV86:'phone',tbdEmailV86:'email',tbdPassengersV86:'passengers',tbdPickupV86:'pickup_address',tbdDestinationV86:'destination_address',tbdDateV86:'pickup_date',tbdTimeV86:'pickup_time',tbdServiceV86:'service_type',tbdFlightV86:'flight_train',tbdMinutesV86:'estimated_minutes',tbdKmV86:'estimated_km',tbdLuggageV86:'luggage',tbdNotesV86:'notes',tbdAdminNoteV86:'admin_note'};
    Object.entries(map).forEach(([id,k])=>{const el=document.getElementById(id);if(el)el.value=b[k]??''});
    document.getElementById('tbdChildSeatV86').checked=!!b.child_seat;document.getElementById('tbdPetsV86').checked=!!b.pets;document.getElementById('tbdRoundTripV86').checked=!!b.round_trip;
    document.getElementById('tbDetailSummaryV86').innerHTML=`<span class="transfer-status-v79 ${transferStatusClassV79(b.status)}">${transferStatusLabelV79(b.status)}</span><dl><div><dt>Provenienza</dt><dd>${esc(b.booking_source||'diretta')}</dd></div><div><dt>Autista</dt><dd>${esc(b.driver_name||'Da assegnare')}</dd></div><div><dt>Mezzo</dt><dd>${esc(b.vehicle_name||'Non assegnato')}</dd></div><div><dt>Creata</dt><dd>${b.created_at?new Date(b.created_at).toLocaleString('it-IT'):'—'}</dd></div></dl>`;
    renderTransferHistoryV86(b.history||[]);document.getElementById('tbSuggestionsV86').innerHTML='';
    document.getElementById('transferBookingDetailModalV86').classList.remove('hidden');
  }catch(e){alert(e.message||e)}
}
function closeTransferBookingDetailV86(){document.getElementById('transferBookingDetailModalV86')?.classList.add('hidden');gfTransferDetailV86=null;}
function renderTransferHistoryV86(rows){const h=document.getElementById('tbHistoryV86');if(!h)return;if(!rows.length){h.innerHTML='<div class="empty-state">Nessuna attività registrata.</div>';return;}h.innerHTML=rows.map(x=>`<div class="transfer-history-item-v86"><i></i><div><b>${esc(x.title)}</b><span>${esc(x.detail||'')}</span><small>${x.created_at?new Date(x.created_at).toLocaleString('it-IT'):''}${x.actor?' · '+esc(x.actor):''}</small></div></div>`).join('');}
async function saveTransferBookingDetailV86(){if(!gfTransferDetailV86)return;const payload={customer_name:v86Val('tbdCustomerV86'),phone:v86Val('tbdPhoneV86'),email:v86Val('tbdEmailV86'),passengers:Number(v86Val('tbdPassengersV86')||1),pickup_address:v86Val('tbdPickupV86'),destination_address:v86Val('tbdDestinationV86'),pickup_date:v86Val('tbdDateV86'),pickup_time:v86Val('tbdTimeV86'),service_type:v86Val('tbdServiceV86'),flight_train:v86Val('tbdFlightV86'),estimated_minutes:Number(v86Val('tbdMinutesV86')||60),estimated_km:Number(v86Val('tbdKmV86')||0),luggage:v86Val('tbdLuggageV86'),notes:v86Val('tbdNotesV86'),admin_note:v86Val('tbdAdminNoteV86'),child_seat:document.getElementById('tbdChildSeatV86').checked,pets:document.getElementById('tbdPetsV86').checked,round_trip:document.getElementById('tbdRoundTripV86').checked};try{await api(`/api/transfer/bookings/${gfTransferDetailV86.id}`,{method:'PUT',body:JSON.stringify(payload)});toast('Prenotazione aggiornata');await loadTransferBookingsV79();await openTransferBookingDetailV86(gfTransferDetailV86.id);}catch(e){alert(e.message||e)}}
async function loadTransferSuggestionsV86(){if(!gfTransferDetailV86)return;const host=document.getElementById('tbSuggestionsV86');host.innerHTML='<div class="empty-state">Analisi disponibilità...</div>';try{const r=await api(`/api/transfer/bookings/${gfTransferDetailV86.id}/suggestions`);const rows=r.suggestions||[];host.innerHTML=rows.length?rows.map((x,i)=>`<button class="transfer-suggestion-item-v86 ${i===0?'best':''}" onclick="applyTransferSuggestionV86(${x.driver_id})"><span><b>${esc(x.driver_name)}</b><small>${x.reasons.map(esc).join(' · ')}</small></span><strong>${x.score}%</strong></button>`).join(''):'<div class="empty-state warning">Nessun autista compatibile con gli orari indicati.</div>';}catch(e){host.innerHTML=`<div class="empty-state error">${esc(e.message||e)}</div>`}}
async function applyTransferSuggestionV86(driverId){if(!gfTransferDetailV86)return;try{await updateTransferBookingV79(gfTransferDetailV86.id,{driver_id:driverId});toast('Autista proposto assegnato');await openTransferBookingDetailV86(gfTransferDetailV86.id);}catch(e){alert(e.message||e)}}
function openDetailRouteV86(){if(!gfTransferDetailV86)return;openGoogleRouteV79(encodeURIComponent(gfTransferDetailV86.pickup_address),encodeURIComponent(gfTransferDetailV86.destination_address));}
