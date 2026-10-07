let fleetView='cards';
function fleetIcon(kind){
 const paths={car:'<path d="m4 10 2-6h12l2 6M3 10h18v9H3ZM5 19v2m14-2v2M6 14h2m8 0h2"/>',fuel:'<path d="M4 21V3h10v18M4 10h10M2 21h14M14 8h3l3 4v6a2 2 0 0 1-4 0v-4m2-8 3 3v4"/>',gauge:'<path d="M4 19a9 9 0 1 1 16 0M12 13l5-5M5 12h1m6-7v1m7 6h1"/><circle cx="12" cy="14" r="1"/>',edit:'<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z"/>',trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>'};
 return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[kind]||paths.car}</svg>`;
}
function fleetIsAvailable(vehicle){return String(vehicle.stato||'').toLocaleLowerCase('it')==='disponibile';}
function fleetFilteredVehicles(){
 const q=(document.getElementById('fleetSearch')?.value||'').trim().toLocaleLowerCase('it');
 const filter=document.getElementById('fleetStatusFilter')?.value||'';
 const plateQuery=q.replace(/\s/g,'');
 return vehiclesCache.filter(x=>(!q||[x.nome,x.marca,x.modello,x.targa].some(v=>String(v||'').toLocaleLowerCase('it').includes(q))||String(x.targa||'').toLowerCase().replace(/\s/g,'').includes(plateQuery))&&(!filter||(filter==='available'?fleetIsAvailable(x):String(x.stato||'').toLowerCase()==='in uso')));
}
function fleetPhoto(x){
 const url=String(x.photo_url||'');
 const safe=/^(https?:\/\/|\/[^/]|data:image\/(png|jpe?g|webp|gif);base64,)/i.test(url);
 return `<div class="fleet-photo">${safe?`<img src="${esc(url)}" alt="${esc(x.nome||'Mezzo')}" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span hidden aria-hidden="true">🚚</span>`:'<span aria-hidden="true">🚚</span>'}</div>`;
}
function fleetStatus(x){return `<span class="fleet-status ${fleetIsAvailable(x)?'available':'busy'}"><i aria-hidden="true"></i>${esc(x.stato||'Stato non disponibile')}</span>`;}
function fleetActions(x){return `<div class="fleet-card-actions"><button type="button" class="fleet-edit" onclick="editVehicle(${Number(x.id)})" aria-label="Modifica ${esc(x.nome)}">${fleetIcon('edit')}Modifica</button><button type="button" class="fleet-delete" onclick="deleteVehicle(${Number(x.id)})" aria-label="Elimina ${esc(x.nome)}">${fleetIcon('trash')}Elimina</button></div>`;}
function setFleetView(view){fleetView=view==='table'?'table':'cards';renderFleetDirectory();}
function renderFleetDirectory(){
 const cards=document.getElementById('fleetCards'),body=document.getElementById('vehiclesBody');if(!cards||!body)return;
 const rows=fleetFilteredVehicles();
 cards.innerHTML=rows.map(x=>`<article class="fleet-card"><div class="fleet-card-head">${fleetPhoto(x)}<div class="fleet-identity"><h2>${esc(x.nome||'Mezzo')}</h2><span class="fleet-plate">${esc(x.targa||'Targa non indicata')}</span></div>${fleetStatus(x)}</div><div class="fleet-specs">${[['car','Tipo veicolo',x.carrozzeria||'Non specificato'],['fuel','Alimentazione',GF_FUEL_LABELS_V895[x.alimentazione]||x.alimentazione||'Non specificata'],['gauge','Consumo',energyConsumptionLabelV895(x)]].map(([icon,label,value])=>`<div>${fleetIcon(icon)}<div><span>${label}</span><strong>${esc(value)}</strong></div></div>`).join('')}</div>${fleetActions(x)}</article>`).join('');
 body.innerHTML=rows.map(x=>`<tr><td><div class="fleet-table-name">${fleetPhoto(x)}<strong>${esc(x.nome||'Mezzo')}</strong></div></td><td>${esc(x.targa||'—')}</td><td>${esc(x.carrozzeria||'Non specificato')}</td><td>${esc(GF_FUEL_LABELS_V895[x.alimentazione]||x.alimentazione||'—')}</td><td>${esc(energyConsumptionLabelV895(x))}</td><td>${fleetStatus(x)}</td><td data-gf-feature="tail_lift">${x.ha_sponda?'Sì':'No'}</td><td data-gf-feature="ztl">${x.accesso_ztl?'Sì':'No'}</td><td>${fleetActions(x)}</td></tr>`).join('');
 cards.classList.toggle('hidden',fleetView!=='cards'||!rows.length);
 document.getElementById('fleetTable').classList.toggle('hidden',fleetView!=='table'||!rows.length);
 document.getElementById('fleetEmpty').classList.toggle('hidden',rows.length>0);
 document.getElementById('fleetEmpty').textContent=vehiclesCache.length?'Nessun mezzo corrisponde ai filtri selezionati.':'Non hai ancora registrato mezzi. Clicca su “Crea mezzo” per iniziare.';
 document.getElementById('fleetCardsButton').setAttribute('aria-pressed',String(fleetView==='cards'));
 document.getElementById('fleetTableButton').setAttribute('aria-pressed',String(fleetView==='table'));
}
function renderFleetPlanNotice(usage){
 const node=document.getElementById('fleetPlanNotice');if(!node)return;
 const message=usage?.over_limit?(usage.message||'La flotta supera i limiti del piano. Apri Crea mezzo per consultare gli slot disponibili.'):usage?.plan_active===false?'Abbonamento non attivo: rinnova il piano per aggiungere mezzi.':'';
 node.textContent=message;node.classList.toggle('hidden',!message);
}
function createFleetVehicle(){if(document.getElementById('saveVehicleBtn')?.disabled)return;resetVehicleForm();openVehicleDrawer(false);}
function openVehicleDrawer(editing=false){
 const dialog=document.getElementById('vehicleDrawer');if(!dialog)return;
 document.getElementById('vehicleFormTitle').textContent=editing?'Modifica mezzo':'Crea mezzo';
 if(!dialog.open)dialog.showModal();
 dialog.scrollTop=0;
 document.getElementById(editing?'vNome':'vTarga')?.focus({preventScroll:true});
}
function closeVehicleDrawer(saved=false){if(saved||!document.getElementById('saveVehicleBtn')?.disabled)document.getElementById('vehicleDrawer')?.close();}
