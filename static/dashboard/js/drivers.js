let driverDirectoryView='cards';
try{
 const saved=window.localStorage?.getItem('gfDriverView');
 if(saved==='cards'||saved==='table') driverDirectoryView=saved;
}catch(_error){}

function driverDirectoryIcon(kind){
 const paths={phone:'<path d="m5 3 4 4-2 3a15 15 0 0 0 7 7l3-2 4 4c-2 5-8 2-12-2S2 7 5 3Z"/>',mail:'<rect x="3" y="5" width="18" height="14" rx="1"/><path d="m3 6 9 7 9-7"/>',license:'<rect x="5" y="2" width="14" height="20" rx="1"/><circle cx="12" cy="8" r="2"/><path d="M10 13h4m-4 3h4"/>',route:'<circle cx="6" cy="5" r="2"/><circle cx="18" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="19" r="2"/><path d="M6 7v10m2 2h8m2-12v4l-6 4"/>',vehicle:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4m8-4v4M4 10h16M8 14h2m4 0h2M7 20v2m10-2v2"/>'};return `<svg class="gf-icon" viewBox="0 0 24 24" aria-hidden="true">${paths[kind]||paths.license}</svg>`;
}
function driverDirectoryRows(){
 const q=(document.getElementById('driverSearch')?.value||'').trim().toLocaleLowerCase('it'),status=document.getElementById('driverStatusFilter')?.value||'',sort=document.getElementById('driverSort')?.value||'name';
 return driversCache.filter(d=>(!q||[d.nome,d.cognome,driverFullName(d),d.telefono,d.email,d.patente,d.note].some(v=>String(v||'').toLocaleLowerCase('it').includes(q)))&&(!status||d.stato===status)).sort((a,b)=>{
 const names=driverFullName(a).localeCompare(driverFullName(b),'it',{sensitivity:'base'});
 if(sort==='routes')return (Number(b.giri_assegnati||0)-Number(a.giri_assegnati||0))||names;
 if(sort==='expiry')return String(a.scadenza_patente||'9999').localeCompare(String(b.scadenza_patente||'9999'))||names;
 return sort==='name_desc'?-names:names;
 });
}
function driverDirectoryStatus(d){const status=d.stato==='Disponibile'?'success':d.stato==='In servizio'?'info':'neutral';return `<span class="gf-badge" data-dot data-status="${status}">${esc(d.stato||'Stato non disponibile')}</span>`;}
function driverDirectoryAvatar(d){const url=String(d.photo_url||'');return /^(https?:\/\/|\/[^/]|data:image\/(png|jpe?g|webp|gif);base64,)/i.test(url)?`<img src="${esc(url)}" alt="${esc(driverFullName(d))}" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span hidden>${esc(driverInitials(d))}</span>`:esc(driverInitials(d));}
function setDriverView(view){
 driverDirectoryView=view==='table'?'table':'cards';
 try{window.localStorage?.setItem('gfDriverView',driverDirectoryView);}catch(_error){}
 renderDriverDirectory();
}
function driverTableActions(d){
 const id=Number(d.id);
 return `<div class="gf-cluster"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="editDriver(${id})">Modifica</button><button type="button" class="gf-button" data-variant="ghost" data-size="sm" onclick="showDriverDetails(${id})">Dettagli</button></div>`;
}
function renderDriverDirectory(){
 const box=document.getElementById('driversCards');if(!box)return;
 for(const [id,value] of [['driversTotal',driversCache.length],['driversAvailable',driversCache.filter(d=>d.stato==='Disponibile').length],['driversWorking',driversCache.filter(d=>d.stato==='In servizio').length]]){const el=document.getElementById(id);if(el)el.textContent=value;}
 const rows=driverDirectoryRows();
 box.innerHTML=rows.map(d=>{const id=Number(d.id),vehicle=d.mezzo_abituale;return `<article class="gf-card gf-stack"><div class="gf-cluster" data-justify="between"><div class="gf-cluster"><span class="gf-avatar">${driverDirectoryAvatar(d)}</span><div><h3 class="gf-subtitle">${esc(driverFullName(d))}</h3><p class="gf-muted">${esc(d.telefono||'Telefono non indicato')}</p><p class="gf-muted">${esc(d.email||'Email non indicata')}</p></div></div><div class="gf-cluster">${driverDirectoryStatus(d)}<details class="gf-dropdown" name="driver-actions"><summary class="gf-icon-button" aria-label="Azioni per ${esc(driverFullName(d))}">•••</summary><div data-gf-menu><button type="button" class="gf-button" data-variant="ghost" onclick="editDriver(${id});this.closest('details').open=false">Modifica</button>${d.email?`<button type="button" class="gf-button" data-variant="ghost" onclick="inviteDriver(${id});this.closest('details').open=false">${d.account_attivo?'Reinvita':'Invita'} al portale</button>`:''}<button type="button" class="gf-button" data-variant="danger" onclick="deleteDriver(${id})">Elimina</button></div></details></div></div><dl class="gf-details"><div class="gf-details__item"><dt>Patente</dt><dd><strong>${esc(d.patente||'—')}</strong> · Scadenza ${esc(gfDateIt(d.scadenza_patente)||'non indicata')}</dd></div><div class="gf-details__item"><dt>Giri assegnati</dt><dd><strong>${esc(d.giri_assegnati??0)}</strong></dd></div><div class="gf-details__item" title="Veicolo più frequentemente assegnato nei giri"><dt>Mezzo abituale</dt><dd><strong>${esc(vehicle?.nome||'Non assegnato')}</strong> · ${esc(vehicle?.targa||'—')}</dd></div></dl><div><button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="showDriverDetails(${id})" aria-label="Visualizza ${esc(driverFullName(d))}">Visualizza</button></div></article>`;}).join('')||'<div class="gf-empty"><p>Nessun autista trovato.</p></div>';

 const body=document.getElementById('driversBody');
 if(body){
   body.innerHTML=rows.length?rows.map(d=>{const vehicle=d.mezzo_abituale;return `<tr><td data-label="Autista"><strong>${esc(driverFullName(d))}</strong><br><small class="gf-muted">${esc(d.email||'Email non indicata')}</small></td><td data-label="Contatti">${esc(d.telefono||'—')}</td><td data-label="Patente"><strong>${esc(d.patente||'—')}</strong><br><small class="gf-muted">${esc(gfDateIt(d.scadenza_patente)||'Scadenza non indicata')}</small></td><td data-label="Giri">${Number(d.giri_assegnati||0)}</td><td data-label="Mezzo abituale"><strong>${esc(vehicle?.nome||'Non assegnato')}</strong><br><small class="gf-muted">${esc(vehicle?.targa||'—')}</small></td><td data-label="Stato">${driverDirectoryStatus(d)}</td><td data-label="Azioni">${driverTableActions(d)}</td></tr>`;}).join(''):'<tr><td colspan="7"><div class="gf-empty"><p>Nessun autista trovato.</p></div></td></tr>';
 }
 box.classList.toggle('hidden',driverDirectoryView!=='cards');
 document.getElementById('driverTableWrap')?.classList.toggle('hidden',driverDirectoryView!=='table');
 document.getElementById('driverListView')?.setAttribute('aria-pressed',String(driverDirectoryView==='table'));
 document.getElementById('driverGridView')?.setAttribute('aria-pressed',String(driverDirectoryView==='cards'));
}
function showDriverDetails(id){
 const d=driversCache.find(x=>x.id===id);if(!d)return;
 const fields=[['Turno abituale',d.work_schedule?.start?d.work_schedule.start+'–'+d.work_schedule.end:'Non impostato'],['Pause',(d.work_schedule?.breaks||[]).map(b=>b.start+'–'+b.end).join(', ')||'Nessuna pausa impostata'],['Telefono',d.telefono],['Email',d.email],['Patente',d.patente],['Scadenza patente',gfDateIt(d.scadenza_patente)],['Giri assegnati',d.giri_assegnati??0],['Mezzo abituale',d.mezzo_abituale?[d.mezzo_abituale.nome,d.mezzo_abituale.targa].filter(Boolean).join(' · '):'Non assegnato'],['Portale',d.account_attivo?'Attivo':d.email?'Da invitare':'Email non indicata'],['Note',d.note]];
 document.getElementById('driverDetailsContent').innerHTML=`<div class="gf-cluster"><h2 class="gf-modal__title" id="driverDetailsTitle">${esc(driverFullName(d))}</h2>${driverDirectoryStatus(d)}</div><dl class="gf-details">${fields.map(([k,v])=>`<div class="gf-details__item"><dt>${k}</dt><dd>${esc(v??'—')||'—'}</dd></div>`).join('')}</dl><div><button type="button" class="gf-button" data-variant="primary" onclick="document.getElementById('driverDetailsDialog').close();editDriver(${Number(id)})">Modifica autista</button></div>`;
 document.getElementById('driverDetailsDialog').showModal();
}
