/* Customer selections use the same verify/correct/choose-position flow as orders. */
window.GFCustomerAddresses=(()=>{
 'use strict';
 const el=id=>document.getElementById(id);
 const issues=new Map();
 let busy=false,active=null,map=null,marker=null,point=null,mapEpoch=0;
 const selection=()=>[...customerDirectory.selected];
 const message=text=>{const node=el('selectedCustomerAddressesMessage');if(node)node.textContent=text;};
 function cancelEdit(){
  mapEpoch++;if(map){map.remove();map=null;}marker=null;point=null;active=null;
  el('selectedCustomerAddressEditor').hidden=true;
 }
 function drawIssues(){
  const canEdit=!window.GFCompanyAccess||GFCompanyAccess.can('customers.update');
  el('selectedCustomerAddressesList').innerHTML=[...issues.values()].map(row=>
   `<article class="gf-card gf-stack" data-gap="sm"><strong>${cxEsc(row.recipient_name||'Cliente')}</strong><span class="gf-muted">${cxEsc([row.address,row.comune,row.provincia].filter(Boolean).join(', ')||'Indirizzo mancante')}</span><p>${cxEsc(row.message)}</p><div class="gf-cluster">${canEdit?`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-customer-address-action="edit" data-customer-id="${row.id}">Correggi o scegli posizione</button>`:''}<button type="button" class="gf-button" data-variant="ghost" data-size="sm" data-customer-address-action="exclude" data-customer-id="${row.id}">Escludi dalla selezione</button></div></article>`).join('');
  el('selectedCustomerAddressesContinue').disabled=busy||issues.size>0||selection().length===0;
 }
 function lock(value){
  busy=value;
  el('selectedCustomerAddressesDialog').querySelectorAll('button,input').forEach(node=>node.disabled=value);
  if(!value){el('selectedCustomerAddressManual').disabled=!point;drawIssues();}
 }
 async function verify(ids=null,retain=false){
  if(busy)return false;
  if(!retain){issues.clear();cancelEdit();}
  if(ids===null)ids=selection();
  lock(true);
  let completed=0;
  try{
   for(let offset=0;offset<ids.length;offset+=3){
    const chunk=ids.slice(offset,offset+3);
    chunk.forEach(id=>issues.delete(id));
    message(`Verifica indirizzi selezionati: ${completed} di ${ids.length}…`);
    const result=await api('/api/customers/verify-selected',{method:'POST',body:JSON.stringify({customer_ids:chunk})});
    (result.issues||[]).forEach(row=>issues.set(row.id,row));
    completed+=chunk.length;
    if(result.aborted)break;
   }
   const unresolved=issues.size;
   message(unresolved?`${unresolved} indirizzi richiedono attenzione. Correggili o escludi i clienti interessati.`:'Tutti gli indirizzi selezionati sono verificati.');
   if(unresolved&&!el('selectedCustomerAddressesDialog').open)el('selectedCustomerAddressesDialog').showModal();
   return unresolved===0;
  }finally{
   lock(false);
   await refreshCustomerDirectory().catch(()=>{});
  }
 }
 async function edit(id){
  if(busy)return;cancelEdit();active=issues.get(id);if(!active)return;
  el('selectedCustomerAddressName').textContent=active.recipient_name||'Cliente';
  el('selectedCustomerAddressText').value=active.address||'';
  el('selectedCustomerAddressCity').value=active.comune||'';
  el('selectedCustomerAddressProvince').value=active.provincia||'';
  el('selectedCustomerAddressEditor').hidden=false;
  el('selectedCustomerAddressManual').disabled=true;
  el('selectedCustomerAddressPosition').textContent='Clicca sulla mappa per scegliere la posizione oppure correggi l’indirizzo e ripeti la verifica.';
  el('selectedCustomerAddressText').focus();
  const epoch=mapEpoch;
  try{
   await loadRoadMapLibrary();if(epoch!==mapEpoch||!active)return;
   const candidate=active.candidate;
   const hasCandidate=candidate?.lat!=null&&candidate?.lon!=null&&Number.isFinite(Number(candidate.lat))&&Number.isFinite(Number(candidate.lon));
   map=L.map(el('selectedCustomerAddressMap'),{scrollWheelZoom:false}).setView(hasCandidate?[candidate.lat,candidate.lon]:[42.5,12.5],hasCandidate?15:5);
   L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
   function choose(lat,lon){
    point={lat,lon};
    if(marker)marker.setLatLng([lat,lon]);
    else {marker=L.marker([lat,lon],{draggable:true}).addTo(map);marker.on('dragend',()=>{const p=marker.getLatLng();choose(p.lat,p.lng);});}
    el('selectedCustomerAddressManual').disabled=false;
    el('selectedCustomerAddressPosition').textContent='Posizione scelta. Premi “Conferma questa posizione” per salvarla manualmente.';
   }
   map.on('click',event=>choose(event.latlng.lat,event.latlng.lng));
   if(hasCandidate)choose(Number(candidate.lat),Number(candidate.lon));
   requestAnimationFrame(()=>map?.invalidateSize());
  }catch(error){
   if(epoch===mapEpoch)el('selectedCustomerAddressPosition').textContent='Mappa non disponibile. Correggi l’indirizzo e riprova la verifica.';
  }
 }
 async function resolve(action,id=active?.id){
  if(busy)return;
  const row=issues.get(id);if(!row)return;
  if(action==='exclude'){
   customerDirectory.selected.delete(id);issues.delete(id);cancelEdit();
   renderCustomerDirectory();drawIssues();
   message(issues.size?`${issues.size} indirizzi da risolvere.`:selection().length?'Puoi continuare alla pianificazione.':'Nessun cliente selezionato.');
   return;
  }
  const form=el('selectedCustomerAddressEditor');
  if(!form.reportValidity()||(action==='manual'&&!point))return;
  const payload={
   customer_id:id,action,original_address:row.address,original_comune:row.comune,
   address:el('selectedCustomerAddressText').value,
   comune:el('selectedCustomerAddressCity').value,
   provincia:el('selectedCustomerAddressProvince').value,
   ...(action==='manual'?point:{})
  };
  lock(true);
  try{
   await api('/api/customers/resolve-selected-address',{method:'POST',body:JSON.stringify(payload)});
   issues.delete(id);cancelEdit();
   await refreshCustomerDirectory();
  }catch(error){message(error.message||'Correzione non riuscita.');return;}
  finally{lock(false);}
  if(action==='correct')await verify([id],true).catch(error=>message(error.message));
  else message(issues.size?`${issues.size} indirizzi da risolvere.`:'Puoi continuare alla pianificazione.');
 }
 document.addEventListener('click',event=>{
  const button=event.target.closest?.('[data-customer-address-action]');
  if(!button||busy)return;
  const id=Number(button.dataset.customerId);
  if(button.dataset.customerAddressAction==='edit')edit(id);else resolve('exclude',id);
 });
 document.addEventListener('DOMContentLoaded',()=>{
  el('selectedCustomerAddressesDialog')?.addEventListener('cancel',event=>{if(busy)event.preventDefault();else cancelEdit();});
 });
 return {verify,cancelEdit,correct:()=>resolve('correct'),manual:()=>resolve('manual'),
  close(){if(busy)return;cancelEdit();el('selectedCustomerAddressesDialog').close();},
  retry:()=>verify().catch(error=>message(error.message)),
  continue(){
   if(busy||issues.size||!selection().length)return;
   cancelEdit();el('selectedCustomerAddressesDialog').close();goCustomerPlanning(true);
  }
 };
})();
