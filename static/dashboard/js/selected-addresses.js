/* Verify only the current selection; resolve uncertain destinations explicitly.
   Each address is fixed by the customer, one row at a time: the app never accepts
   Google's proposal on their behalf, so there is no "accept all" shortcut. */
window.GFSelectedAddresses=(()=>{
 'use strict';
 const el=id=>document.getElementById(id);
 const issues=new Map();
 const resolved=[];
 const GROUP=6; // indirizzi per richiesta: il server li chiede a Google in parallelo
 let busy=false,active=null,map=null,marker=null,point=null,mapEpoch=0;
 const state=()=>GFOrderPlanning.selection();
 const message=text=>{el('selectedAddressesMessage').textContent=text;};
 const REASONS={
  non_trovato:['Non trovato','danger'],
  altro_comune:['Altro comune','danger'],
  approssimativo:['Posizione approssimativa','warning'],
  servizio:['Verifica non riuscita','neutral'],
 };
 const reason=row=>REASONS[row.reason]||(row.kind==='service'?REASONS.servizio:['Da controllare','warning']);
 // The proposal in another town must not drive the map: the pin would start in the wrong place.
 const usableCandidate=row=>{
  const c=row?.candidate;
  return row?.reason!=='altro_comune'&&c?.lat!=null&&c?.lon!=null&&Number.isFinite(Number(c.lat))&&Number.isFinite(Number(c.lon));
 };
 function park(){el('selectedAddressEditorHome').append(el('selectedAddressEditor'));}
 function cancelEdit(){
  mapEpoch++;if(map){map.remove();map=null;}marker=null;point=null;active=null;
  park();el('selectedAddressEditor').hidden=true;
  el('selectedAddressError').hidden=true;
 }
 function progress(){
  const total=issues.size+resolved.length,done=resolved.length;
  el('selectedAddressesDone').textContent=`${done} su ${total}`;
  el('selectedAddressesLeft').textContent=issues.size?`${issues.size} da sistemare`:'Tutto sistemato';
  el('selectedAddressesBar').dataset.gfWidth=String(total?Math.round(done/total*20)*5:0);
  el('selectedAddressesResolvedSection').hidden=!resolved.length;
  el('selectedAddressesResolved').innerHTML=resolved.map(item=>`<li class="gf-list-item"><div class="gf-list-item__main"><strong>${esc(item.number)} · ${esc(item.name||'Destinatario mancante')}</strong><small>${esc(item.detail)}</small></div><span class="gf-badge" data-status="${item.tone}" data-dot>${esc(item.label)}</span></li>`).join('');
 }
 function drawIssues(){
  park();
  const canEdit=!window.GFCompanyAccess||GFCompanyAccess.can('orders.update');
  el('selectedAddressesList').innerHTML=[...issues.values()].map(row=>{
   const [label,tone]=reason(row);
   const proposal=row.candidate?.formatted?`<strong>${esc(row.candidate.formatted)}</strong>`:'<span class="gf-muted">Nessuna proposta</span>';
   return `<tr data-address-row="${row.id}"${active?.id===row.id?' aria-current="true"':''}>`
    +`<td data-label="Cliente"><strong>${esc(row.recipient_name||'Destinatario mancante')}</strong><br><small class="gf-muted">${esc(row.number)}</small></td>`
    +`<td data-label="Scritto">${esc(row.address||'Indirizzo mancante')}</td>`
    +`<td data-label="Proposta di Google">${proposal}</td>`
    +`<td data-label="Motivo"><span class="gf-badge" data-status="${tone}" data-dot>${esc(label)}</span></td>`
    +`<td data-label="Azioni"><div class="gf-cluster">${canEdit?`<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-address-action="edit" data-order-id="${row.id}">${active?.id===row.id?'Chiudi':'Modifica'}</button>`:''}<button type="button" class="gf-button" data-variant="ghost" data-size="sm" data-address-action="exclude" data-order-id="${row.id}">Escludi</button></div></td></tr>`;
  }).join('');
  if(active&&issues.has(active.id)){
   const anchor=el('selectedAddressesList').querySelector(`[data-address-row="${active.id}"]`);
   const holder=document.createElement('tr');const cell=document.createElement('td');
   cell.colSpan=5;holder.append(cell);anchor.after(holder);cell.append(el('selectedAddressEditor'));
   requestAnimationFrame(()=>map?.invalidateSize());
  }
  el('selectedAddressesTable').hidden=!issues.size;
  progress();
  el('selectedAddressesContinue').disabled=busy||issues.size>0||!state().order_ids.length;
 }
 function lock(value){
  busy=value;
  el('selectedAddressesDialog').querySelectorAll('button,input').forEach(node=>node.disabled=value);
  if(!value){el('selectedAddressManual').disabled=!point;drawIssues();}
 }
 async function verify(ids=null,retry=false){
  if(busy)return false;
  if(ids===null){issues.clear();resolved.length=0;ids=[...state().order_ids];cancelEdit();}
  lock(true);
  let completed=0;
  // Verifica di tutta la selezione: schermata di attesa come nel calcolo del giro, con l'avanzamento.
  const full=ids.length>1;
  const progressText=()=>`Controllo ${completed} di ${ids.length} indirizzi…`;
  const wait=full?globalThis.GFDesignSystem?.showWait({title:'Sto verificando gli indirizzi',messages:[progressText()],
   hint:'Controllo ogni indirizzo con Google: di solito bastano pochi secondi.',minMs:800}):null;
  const waitMessage=wait?.element.querySelector('.gf-loader__message');
  try{
   for(let offset=0;offset<ids.length;offset+=GROUP){
    const chunk=ids.slice(offset,offset+GROUP);
    el('ordersMessage').textContent=`Verifica indirizzi selezionati: ${completed} di ${ids.length}…`;
    if(waitMessage)waitMessage.textContent=progressText();
    chunk.forEach(id=>issues.delete(id));
    const result=await api('/api/order-planning/verify-selected',{method:'POST',body:JSON.stringify({version:state().version,order_ids:chunk,retry})});
    GFOrderPlanning.acceptSelection(result.selection);
    result.issues.forEach(row=>issues.set(row.id,row));completed+=chunk.length;
    if(waitMessage)waitMessage.textContent=progressText();
    if(result.aborted)break;
   }
   await wait?.close();
   message(issues.size?`${issues.size} indirizzi vanno sistemati prima di pianificare. Correggi l'indirizzo o metti lo spillo sul punto di consegna, oppure escludi l'ordine.`:'Indirizzi confermati. Puoi continuare alla pianificazione.');
   el('ordersMessage').textContent=issues.size?'Alcuni indirizzi selezionati richiedono attenzione.':'Indirizzi selezionati verificati.';
   if(issues.size&&!el('selectedAddressesDialog').open)el('selectedAddressesDialog').showModal();
   return issues.size===0;
  }finally{
   wait?.dispose();
   lock(false);
   await GFOrders.load().catch(()=>{});
  }
 }
 async function edit(id){
  if(busy)return;
  const reopen=active?.id!==id;
  cancelEdit();
  if(!reopen){drawIssues();return;}
  active=issues.get(id);if(!active)return;
  el('selectedAddressName').value=active.recipient_name;el('selectedAddressText').value=active.address;
  el('selectedAddressHint').textContent=active.message||'';
  el('selectedAddressEditor').hidden=false;el('selectedAddressManual').disabled=true;
  el('selectedAddressPosition').textContent='Clicca sulla mappa sul punto di consegna, oppure correggi l’indirizzo e premi «Verifica».';
  drawIssues();
  el('selectedAddressText').focus();
  const epoch=mapEpoch;
  try{
   await loadRoadMapLibrary();if(epoch!==mapEpoch||!active)return;
   const candidate=active.candidate,hasCandidate=usableCandidate(active);
   map=L.map(el('selectedAddressMap'),{scrollWheelZoom:false}).setView(hasCandidate?[candidate.lat,candidate.lon]:[42.5,12.5],hasCandidate?15:5);
   L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap contributors'}).addTo(map);
   function choose(lat,lon){
    point={lat,lon};
    if(marker)marker.setLatLng([lat,lon]);else{marker=L.marker([lat,lon],{draggable:true}).addTo(map);marker.on('dragend',()=>{const p=marker.getLatLng();choose(p.lat,p.lng);});}
    el('selectedAddressManual').disabled=false;
    el('selectedAddressPosition').textContent='Spillo posizionato. Controlla che sia sul punto di consegna, poi premi «Conferma la posizione dello spillo».';
   }
   map.on('click',event=>choose(event.latlng.lat,event.latlng.lng));
   if(hasCandidate)choose(Number(candidate.lat),Number(candidate.lon));
   requestAnimationFrame(()=>map?.invalidateSize());
  }catch(error){if(epoch===mapEpoch)el('selectedAddressPosition').textContent='Mappa non disponibile. Puoi correggere l’indirizzo e premere «Verifica».';}
 }
 function done(row,label,tone,detail){
  resolved.unshift({number:row.number,name:row.recipient_name,label,tone,detail});
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
   if(action==='exclude')done(row,'Escluso','neutral','Tolto da questa pianificazione');
   if(action==='manual')done(row,'Posizione confermata','info',`${payload.address} · spillo confermato sulla mappa`);
   message(issues.size?`${issues.size} indirizzi da sistemare.`:state().order_ids.length?'Puoi continuare alla pianificazione.':'Nessun ordine selezionato. Chiudi e scegli altri ordini.');
  }catch(error){
   if(action==='exclude')message(error.message);
   else{el('selectedAddressError').textContent=error.message;el('selectedAddressError').hidden=false;}
   return;
  }
  finally{lock(false);}
  if(action==='correct'){
   await verify([id],true).catch(error=>message(error.message));
   if(issues.has(id)){
    // Still not verified: reopen the row with the new reason instead of losing the edit.
    await edit(id);
    el('selectedAddressError').textContent='Questo indirizzo non è ancora verificato. Correggilo ancora oppure metti lo spillo sul punto di consegna.';
    el('selectedAddressError').hidden=false;
   }else done(row,'Verificato','success',`Corretto in: ${payload.address}`);
   progress();
  }
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
 return {verify,correct:()=>resolve('correct'),manual:()=>resolve('manual'),cancelEdit:()=>{cancelEdit();drawIssues();},
  close(){if(busy)return;cancelEdit();el('selectedAddressesDialog').close();},
  retry:()=>verify(null,true).catch(error=>message(error.message)),
  continue(){if(busy||issues.size||!state().order_ids.length)return;cancelEdit();el('selectedAddressesDialog').close();GFOrderPlanning.go(true);}};
})();
