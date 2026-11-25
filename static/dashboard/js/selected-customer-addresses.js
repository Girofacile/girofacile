/* Controllo indirizzi dei clienti selezionati (variante A, 25/11/2026).
   Una tabella con «Hai scritto» e «Google propone» affiancati: Conferma (posizione di Google),
   Modifica (la tabella lascia il posto alla mappa a tutta larghezza) o Escludi. Niente scorrimento
   dentro il pop-up: elenco e mappa non sono mai visibili insieme. */
window.GFCustomerAddresses=(()=>{
 'use strict';
 const el=id=>document.getElementById(id);
 const issues=new Map();
 let busy=false,active=null,map=null,marker=null,point=null,mapEpoch=0;
 const selection=()=>[...customerDirectory.selected];
 const message=text=>{const node=el('selectedCustomerAddressesMessage');if(node)node.textContent=text;};
 const hasCandidate=row=>row?.candidate?.lat!=null&&row?.candidate?.lon!=null&&Number.isFinite(Number(row.candidate.lat))&&Number.isFinite(Number(row.candidate.lon));
 const typed=row=>[row.address,row.comune,row.provincia].filter(Boolean).join(', ')||'Indirizzo mancante';
 // Elenco oppure modifica: le due viste si alternano nello stesso pop-up.
 function view(name){
  el('selectedCustomerAddressesList').hidden=name!=='list';
  el('selectedCustomerAddressesListFooter').hidden=name!=='list';
  el('selectedCustomerAddressEditor').hidden=name!=='edit';
  el('selectedCustomerAddressesEditFooter').hidden=name!=='edit';
 }
 function cancelEdit(){
  mapEpoch++;if(map){map.remove();map=null;}marker=null;point=null;active=null;
  view('list');
 }
 function drawIssues(){
  const canEdit=!window.GFCompanyAccess||GFCompanyAccess.can('customers.update');
  const rows=[...issues.values()].map(row=>`<tr data-customer-address-row="${row.id}">
    <td data-label="Cliente"><strong>${cxEsc(row.recipient_name||'Cliente')}</strong></td>
    <td data-label="Hai scritto"><span class="gf-muted">${cxEsc(typed(row))}</span></td>
    <td data-label="Google propone">${hasCandidate(row)?`<strong>${cxEsc(row.candidate.formatted||'Posizione sulla mappa')}</strong>`:`<span class="gf-muted">${cxEsc(row.message||'Nessuna proposta')}</span>`}</td>
    <td data-label="Azioni"><div class="gf-cluster">${canEdit&&hasCandidate(row)?`<button type="button" class="gf-button" data-variant="primary" data-size="sm" data-customer-address-action="accept" data-customer-id="${row.id}">Conferma</button>`:''}${canEdit?`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-customer-address-action="edit" data-customer-id="${row.id}">Modifica</button>`:''}<button type="button" class="gf-button" data-variant="ghost" data-size="sm" data-customer-address-action="exclude" data-customer-id="${row.id}">Escludi</button></div></td></tr>`).join('');
  el('selectedCustomerAddressesList').innerHTML=issues.size
   ?`<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards" aria-label="Indirizzi da controllare"><thead><tr><th scope="col">Cliente</th><th scope="col">Hai scritto</th><th scope="col">Google propone</th><th scope="col">Azioni</th></tr></thead><tbody>${rows}</tbody></table></div>`
   :'<div class="gf-empty"><p>Tutti gli indirizzi sono a posto.</p></div>';
  const pending=issues.size,proposals=[...issues.values()].filter(hasCandidate).length;
  el('selectedCustomerAddressesCount').textContent=pending?gfCount(pending,'da controllare','da controllare'):'Tutto pronto';
  el('selectedCustomerAddressesAcceptAll').hidden=proposals<2||!(!window.GFCompanyAccess||GFCompanyAccess.can('customers.update'));
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
   message(unresolved?'Google ha trovato una posizione simile: conferma la proposta o modificala.':'Tutti gli indirizzi selezionati sono verificati.');
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
  view('edit');
  el('selectedCustomerAddressManual').disabled=true;
  el('selectedCustomerAddressPosition').textContent='Trascina il segnaposto o clicca sulla mappa, oppure correggi l’indirizzo e verificalo di nuovo.';
  el('selectedCustomerAddressText').focus();
  const epoch=mapEpoch;
  try{
   await loadRoadMapLibrary();if(epoch!==mapEpoch||!active)return;
   const candidate=active.candidate,known=hasCandidate(active);
   map=L.map(el('selectedCustomerAddressMap'),{scrollWheelZoom:false}).setView(known?[candidate.lat,candidate.lon]:[42.5,12.5],known?16:5);
   L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
   function choose(lat,lon){
    point={lat,lon};
    if(marker)marker.setLatLng([lat,lon]);
    else {marker=L.marker([lat,lon],{draggable:true}).addTo(map);marker.on('dragend',()=>{const p=marker.getLatLng();choose(p.lat,p.lng);});}
    el('selectedCustomerAddressManual').disabled=false;
    el('selectedCustomerAddressPosition').textContent='Posizione scelta: premi «Usa questa posizione» per salvarla.';
   }
   map.on('click',event=>choose(event.latlng.lat,event.latlng.lng));
   if(known)choose(Number(candidate.lat),Number(candidate.lon));
   requestAnimationFrame(()=>map?.invalidateSize());
  }catch(error){
   if(epoch===mapEpoch)el('selectedCustomerAddressPosition').textContent='Mappa non disponibile. Correggi l’indirizzo e verificalo di nuovo.';
  }
 }
 function afterChange(){message(issues.size?gfCount(issues.size,'indirizzo da controllare','indirizzi da controllare')+'.':selection().length?'Tutto pronto: puoi continuare alla pianificazione.':'Nessun cliente selezionato.');}
 async function resolve(action,id=active?.id){
  if(busy)return;
  const row=issues.get(id);if(!row)return;
  if(action==='exclude'){
   customerDirectory.selected.delete(id);issues.delete(id);cancelEdit();
   renderCustomerDirectory();drawIssues();afterChange();
   return;
  }
  const payload={customer_id:id,action,original_address:row.address,original_comune:row.comune,
   address:row.address||'-',comune:row.comune||'-',provincia:row.provincia||''};
  if(action!=='accept'){
   const form=el('selectedCustomerAddressEditor');
   if(!form.reportValidity()||(action==='manual'&&!point))return;
   Object.assign(payload,{address:el('selectedCustomerAddressText').value,comune:el('selectedCustomerAddressCity').value,
    provincia:el('selectedCustomerAddressProvince').value},action==='manual'?point:{});
  }
  lock(true);
  try{
   await api('/api/customers/resolve-selected-address',{method:'POST',body:JSON.stringify(payload)});
   issues.delete(id);cancelEdit();
   await refreshCustomerDirectory();
  }catch(error){message(error.message||'Correzione non riuscita.');return false;}
  finally{lock(false);}
  if(action==='correct')await verify([id],true).catch(error=>message(error.message));
  else afterChange();
  return true;
 }
 // «Conferma tutte le proposte»: una alla volta, si ferma al primo errore.
 async function acceptAll(){
  for(const row of [...issues.values()].filter(hasCandidate)){if(await resolve('accept',row.id)===false)break;}
 }
 document.addEventListener('click',event=>{
  const button=event.target.closest?.('[data-customer-address-action]');
  if(!button||busy)return;
  const id=Number(button.dataset.customerId),action=button.dataset.customerAddressAction;
  if(action==='edit')edit(id);else resolve(action,id);
 });
 document.addEventListener('DOMContentLoaded',()=>{
  el('selectedCustomerAddressesDialog')?.addEventListener('cancel',event=>{if(busy)event.preventDefault();else cancelEdit();});
  ['selectedCustomerAddressText','selectedCustomerAddressCity','selectedCustomerAddressProvince'].forEach(id=>{
   el(id)?.addEventListener('input',()=>{
    if(!point)return;
    point=null;if(marker){marker.remove();marker=null;}
    el('selectedCustomerAddressManual').disabled=true;
    el('selectedCustomerAddressPosition').textContent='Indirizzo modificato: verificalo di nuovo oppure scegli la posizione sulla mappa.';
   });
  });
 });
 return {verify,cancelEdit,acceptAll,back:cancelEdit,correct:()=>resolve('correct'),manual:()=>resolve('manual'),
  close(){if(busy)return;cancelEdit();el('selectedCustomerAddressesDialog').close();},
  retry:()=>verify().catch(error=>message(error.message)),
  continue(){
   if(busy||issues.size||!selection().length)return;
   cancelEdit();el('selectedCustomerAddressesDialog').close();goCustomerPlanning(true);
  }
 };
})();
