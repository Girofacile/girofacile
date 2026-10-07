let driverDirectoryView='cards';
try{
 const saved=window.localStorage?.getItem('gfDriverView');
 if(saved==='cards'||saved==='table') driverDirectoryView=saved;
}catch(_error){}

function driverDirectoryIcon(kind){
 const paths={phone:'<path d="m5 3 4 4-2 3a15 15 0 0 0 7 7l3-2 4 4c-2 5-8 2-12-2S2 7 5 3Z"/>',mail:'<rect x="3" y="5" width="18" height="14" rx="1"/><path d="m3 6 9 7 9-7"/>',license:'<rect x="5" y="2" width="14" height="20" rx="1"/><circle cx="12" cy="8" r="2"/><path d="M10 13h4m-4 3h4"/>',route:'<circle cx="6" cy="5" r="2"/><circle cx="18" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="19" r="2"/><path d="M6 7v10m2 2h8m2-12v4l-6 4"/>',vehicle:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4m8-4v4M4 10h16M8 14h2m4 0h2M7 20v2m10-2v2"/>'};return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[kind]||paths.license}</svg>`;
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
function driverDirectoryStatus(d){const cls=d.stato==='Disponibile'?'available':d.stato==='In servizio'?'working':'rest';return `<span class="driver-status ${cls}"><i aria-hidden="true"></i>${esc(d.stato||'Stato non disponibile')}</span>`;}
function driverDirectoryAvatar(d){const url=String(d.photo_url||'');return /^(https?:\/\/|\/[^/]|data:image\/(png|jpe?g|webp|gif);base64,)/i.test(url)?`<img src="${esc(url)}" alt="${esc(driverFullName(d))}" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span hidden>${esc(driverInitials(d))}</span>`:esc(driverInitials(d));}
function setDriverView(view){
 driverDirectoryView=view==='table'?'table':'cards';
 try{window.localStorage?.setItem('gfDriverView',driverDirectoryView);}catch(_error){}
 renderDriverDirectory();
}
function driverTableActions(d){
 const id=Number(d.id);
 return `<div class="row-actions gf-directory-row-actions"><button type="button" onclick="editDriver(${id})">Modifica</button><button type="button" onclick="showDriverDetails(${id})">Dettagli</button></div>`;
}
function renderDriverDirectory(){
 const box=document.getElementById('driversCards');if(!box)return;
 for(const [id,value] of [['driversTotal',driversCache.length],['driversAvailable',driversCache.filter(d=>d.stato==='Disponibile').length],['driversWorking',driversCache.filter(d=>d.stato==='In servizio').length]]){const el=document.getElementById(id);if(el)el.textContent=value;}
 const rows=driverDirectoryRows();
 box.innerHTML=rows.map(d=>{const id=Number(d.id),vehicle=d.mezzo_abituale;return `<article class="driver-directory-card"><div class="driver-directory-top"><div class="driver-directory-avatar tone-${id%4}">${driverDirectoryAvatar(d)}</div><div class="driver-directory-identity"><h2>${esc(driverFullName(d))}</h2><p>${driverDirectoryIcon('phone')}<span>${esc(d.telefono||'Telefono non indicato')}</span></p><p>${driverDirectoryIcon('mail')}<span>${esc(d.email||'Email non indicata')}</span></p></div><div class="driver-directory-controls">${driverDirectoryStatus(d)}<details class="driver-menu" name="driver-actions"><summary aria-label="Azioni per ${esc(driverFullName(d))}">•••</summary><div><button onclick="editDriver(${id});this.closest('details').open=false">Modifica</button>${d.email?`<button onclick="inviteDriver(${id});this.closest('details').open=false">${d.account_attivo?'Reinvita':'Invita'} al portale</button>`:''}<button class="driver-delete" onclick="deleteDriver(${id})">Elimina</button></div></details></div></div><div class="driver-directory-bottom"><div class="driver-directory-spec">${driverDirectoryIcon('license')}<div><small>Patente</small><strong>${esc(d.patente||'—')}</strong><span>Scadenza ${esc(d.scadenza_patente||'non indicata')}</span></div></div><div class="driver-directory-spec">${driverDirectoryIcon('route')}<div><small>Giri assegnati</small><strong>${esc(d.giri_assegnati??0)}</strong></div></div><div class="driver-directory-spec" title="Veicolo più frequentemente assegnato nei giri">${driverDirectoryIcon('vehicle')}<div><small>Mezzo abituale</small><strong>${esc(vehicle?.nome||'Non assegnato')}</strong><span>${esc(vehicle?.targa||'—')}</span></div></div><button class="driver-view" onclick="showDriverDetails(${id})" aria-label="Visualizza ${esc(driverFullName(d))}">Visualizza</button></div></article>`;}).join('')||'<p class="driver-directory-empty">Nessun autista trovato.</p>';

 const body=document.getElementById('driversBody');
 if(body){
   body.innerHTML=rows.length?rows.map(d=>{const vehicle=d.mezzo_abituale;return `<tr><td><strong>${esc(driverFullName(d))}</strong><small>${esc(d.email||'Email non indicata')}</small></td><td>${esc(d.telefono||'—')}</td><td><strong>${esc(d.patente||'—')}</strong><small>${esc(d.scadenza_patente||'Scadenza non indicata')}</small></td><td>${Number(d.giri_assegnati||0)}</td><td><strong>${esc(vehicle?.nome||'Non assegnato')}</strong><small>${esc(vehicle?.targa||'—')}</small></td><td>${driverDirectoryStatus(d)}</td><td>${driverTableActions(d)}</td></tr>`;}).join(''):'<tr><td colspan="7" class="gf-directory-empty">Nessun autista trovato.</td></tr>';
 }
 box.classList.toggle('hidden',driverDirectoryView!=='cards');
 document.getElementById('driverTableWrap')?.classList.toggle('hidden',driverDirectoryView!=='table');
 document.getElementById('driverListView')?.setAttribute('aria-pressed',String(driverDirectoryView==='table'));
 document.getElementById('driverGridView')?.setAttribute('aria-pressed',String(driverDirectoryView==='cards'));
}
function showDriverDetails(id){
 const d=driversCache.find(x=>x.id===id);if(!d)return;
 const fields=[['Telefono',d.telefono],['Email',d.email],['Patente',d.patente],['Scadenza patente',d.scadenza_patente],['Giri assegnati',d.giri_assegnati??0],['Mezzo abituale',d.mezzo_abituale?[d.mezzo_abituale.nome,d.mezzo_abituale.targa].filter(Boolean).join(' · '):'Non assegnato'],['Portale',d.account_attivo?'Attivo':d.email?'Da invitare':'Email non indicata'],['Note',d.note]];
 document.getElementById('driverDetailsContent').innerHTML=`<h2 id="driverDetailsTitle">${esc(driverFullName(d))}</h2>${driverDirectoryStatus(d)}<dl>${fields.map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v??'—')||'—'}</dd></div>`).join('')}</dl><button class="btn-primary" onclick="document.getElementById('driverDetailsDialog').close();editDriver(${Number(id)})">Modifica autista</button>`;
 document.getElementById('driverDetailsDialog').showModal();
}
