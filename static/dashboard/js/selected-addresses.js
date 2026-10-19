/* Verify only the current selection; resolve uncertain destinations explicitly. */
window.GFSelectedAddresses=(()=>{
 'use strict';
 const el=id=>document.getElementById(id);
 const issues=new Map();
 let busy=false,active=null,map=null,marker=null,point=null,mapEpoch=0;
 const state=()=>GFOrderPlanning.selection();
 const message=text=>{el('selectedAddressesMessage').textContent=text;};
 function cancelEdit(){
  mapEpoch++;if(map){map.remove();map=null;}marker=null;point=null;active=null;
  el('selectedAddressEditor').hidden=true;
 }
 function drawIssues(){
  const canEdit=!window.GFCompanyAccess||GFCompanyAccess.can('orders.update');
  el('selectedAddressesList').innerHTML=[...issues.values()].map(row=>`<article class="gf-card gf-stack" data-gap="sm"><strong>${esc(row.number)} · ${esc(row.recipient_name||'Destinatario mancante')}</strong><span class="gf-muted">${esc(row.address||'Indirizzo mancante')}</span><p>${esc(row.message)}</p><div class="gf-cluster">${canEdit?`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-address-action="edit" data-order-id="${row.id}">Correggi o scegli posizione</button>`:''}<button type="button" class="gf-button" data-variant="ghost" data-size="sm" data-address-action="exclude" data-order-id="${row.id}">Escludi dalla selezione</button></div></article>`).join('');
  el('selectedAddressesContinue').disabled=busy||issues.size>0||!state().order_ids.length;
 }
 function lock(value){
  busy=value;
  el('selectedAddressesDialog').querySelectorAll('button,input').forEach(node=>node.disabled=value);
  if(!value){el('selectedAddressManual').disabled=!point;drawIssues();}
 }
 async function verify(ids=null,retry=false){
  if(busy)return false;
  if(ids===null){issues.clear();ids=[...state().order_ids];cancelEdit();}
  lock(true);
  let completed=0;
  try{
   for(let offset=0;offset<ids.length;offset+=3){
    const chunk=ids.slice(offset,offset+3);
    el('ordersMessage').textContent=`Verifica indirizzi selezionati: ${completed} di ${ids.length}…`;
    chunk.forEach(id=>issues.delete(id));
    const result=await api('/api/order-planning/verify-selected',{method:'POST',body:JSON.stringify({version:state().version,order_ids:chunk,retry})});
    GFOrderPlanning.acceptSelection(result.selection);
    result.issues.forEach(row=>issues.set(row.id,row));completed+=chunk.length;
    if(result.aborted)break;
   }
   message(issues.size?`${issues.size} indirizzi richiedono attenzione. Risolvi i problemi o escludi gli ordini interessati.`:'Indirizzi confermati. Puoi continuare alla pianificazione.');
   el('ordersMessage').textContent=issues.size?'Alcuni indirizzi selezionati richiedono attenzione.':'Indirizzi selezionati verificati.';
   if(issues.size&&!el('selectedAddressesDialog').open)el('selectedAddressesDialog').showModal();
   return issues.size===0;
  }finally{
   lock(false);
   await GFOrders.load().catch(()=>{});
  }
 }
 async function edit(id){
  if(busy)return;cancelEdit();active=issues.get(id);if(!active)return;
  el('selectedAddressName').value=active.recipient_name;el('selectedAddressText').value=active.address;
  el('selectedAddressEditor').hidden=false;el('selectedAddressManual').disabled=true;
  el('selectedAddressPosition').textContent='Clicca sulla mappa per scegliere la posizione, oppure correggi l’indirizzo e ripeti la verifica.';
  el('selectedAddressName').focus();
  const epoch=mapEpoch;
  try{
   await loadRoadMapLibrary();if(epoch!==mapEpoch||!active)return;
   const candidate=active.candidate;
   const hasCandidate=candidate?.lat!=null&&candidate?.lon!=null&&Number.isFinite(Number(candidate.lat))&&Number.isFinite(Number(candidate.lon));
   map=L.map(el('selectedAddressMap'),{scrollWheelZoom:false}).setView(hasCandidate?[candidate.lat,candidate.lon]:[42.5,12.5],hasCandidate?15:5);
   L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
   function choose(lat,lon){
    point={lat,lon};
    if(marker)marker.setLatLng([lat,lon]);else{marker=L.marker([lat,lon],{draggable:true}).addTo(map);marker.on('dragend',()=>{const p=marker.getLatLng();choose(p.lat,p.lng);});}
    el('selectedAddressManual').disabled=false;
    el('selectedAddressPosition').textContent='Posizione scelta. Con “Conferma questa posizione” la salvi come conferma manuale.';
   }
   map.on('click',event=>choose(event.latlng.lat,event.latlng.lng));
   if(hasCandidate)choose(Number(candidate.lat),Number(candidate.lon));
   requestAnimationFrame(()=>map?.invalidateSize());
  }catch(error){if(epoch===mapEpoch)el('selectedAddressPosition').textContent='Mappa non disponibile. Puoi correggere l’indirizzo e riprovare la verifica.';}
 }
 async function resolve(action,id=active?.id){
  if(busy)return;
  const row=issues.get(id);if(!row)return;
  if(action!=='exclude'&&!el('selectedAddressEditor').reportValidity())return;
  if(action==='manual'&&!point)return;
  const payload={version:state().version,order_id:id,order_version:row.version,action,
   ...(action!=='exclude'?{recipient_name:el('selectedAddressName').value,address:el('selectedAddressText').value}:{}),
   ...(action==='manual'?point:{})};
  lock(true);
  try{
   const result=await api('/api/order-planning/resolve-address',{method:'POST',body:JSON.stringify(payload)});
   GFOrderPlanning.acceptSelection(result.selection);issues.delete(id);cancelEdit();
   message(issues.size?`${issues.size} indirizzi da risolvere.`:state().order_ids.length?'Puoi continuare alla pianificazione.':'Nessun ordine selezionato. Chiudi e scegli altri ordini.');
  }catch(error){message(error.message);return;}
  finally{lock(false);}
  if(action==='correct')await verify([id],true).catch(error=>message(error.message));
  else await GFOrders.load().catch(()=>{});
 }
 document.addEventListener('click',event=>{
  const button=event.target.closest('[data-address-action]');if(!button||busy)return;
  const id=Number(button.dataset.orderId);
  if(button.dataset.addressAction==='edit')edit(id);else resolve('exclude',id);
 });
 document.addEventListener('DOMContentLoaded',()=>{
  el('selectedAddressesDialog')?.addEventListener('cancel',event=>{if(busy)event.preventDefault();else cancelEdit();});
 });
 return {verify,correct:()=>resolve('correct'),manual:()=>resolve('manual'),cancelEdit,
  close(){if(busy)return;cancelEdit();el('selectedAddressesDialog').close();},
  retry:()=>verify(null,true).catch(error=>message(error.message)),
  continue(){if(busy||issues.size||!state().order_ids.length)return;cancelEdit();el('selectedAddressesDialog').close();GFOrderPlanning.go(true);}};
})();
