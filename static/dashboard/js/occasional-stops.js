let occasionalStopIndex = null;
let occasionalAddressProof = null;
let occasionalVerificationVersion = 0;
let planningDraggedStop = null;

function occasionalProofMatches(proof, address){
  return customerIsPlannable(proof) && !!proof.geocoding_token && proof.indirizzo === address;
}

function invalidateOccasionalAddress(){
  occasionalVerificationVersion++;
  occasionalAddressProof = null;
  document.getElementById('osVerificationStatus').textContent = 'L’indirizzo viene verificato con Google quando salvi.';
  document.getElementById('osSave').disabled = false;
}

function openOccasionalStopModal(index=null){
  const d = index === null ? {} : deliveries[index];
  if(!d || d.customer_id != null) return;
  occasionalStopIndex = index;
  document.getElementById('occasionalStopForm').reset();
  invalidateOccasionalAddress();
  const fields = {osName:'cliente_nome',osAddress:'indirizzo',osWeight:'peso_kg',osPackages:'colli',
    osMorningFrom:'scarico_mattina_da',osMorningTo:'scarico_mattina_a',
    osAfternoonFrom:'scarico_pomeriggio_da',osAfternoonTo:'scarico_pomeriggio_a',osUnloading:'tempo_scarico_min',osNotes:'note'};
  for(const [id,key] of Object.entries(fields)) if(d[key] != null) set(id,d[key]);
  set('osZtl',d.ztl ? 'true':'false'); set('osTailLift',d.sponda ? 'true':'false');
  if(occasionalProofMatches(d,d.indirizzo)){
    occasionalAddressProof = {...d};
    document.getElementById('osVerificationStatus').textContent = '✓ Indirizzo verificato';
    document.getElementById('osSave').disabled = false;
  }
  document.getElementById('osSave').textContent = index === null ? 'Aggiungi fermata' : 'Salva modifiche';
  document.getElementById('occasionalStopDialog').showModal();
  document.getElementById('osName').focus();
}

function closeOccasionalStopModal(){
  occasionalVerificationVersion++;
  document.getElementById('occasionalStopDialog').close();
}

// Verifica automatica al salvataggio: true se l'indirizzo è confermato da Google.
async function verifyOccasionalAddress(){
  const address = val('osAddress');
  invalidateOccasionalAddress();
  const status = document.getElementById('osVerificationStatus');
  if(address.length < 4){ status.textContent = 'Scrivi via, numero civico e comune.'; return false; }
  const version = occasionalVerificationVersion;
  const button = document.getElementById('osSave');
  button.disabled = true;
  status.textContent = 'Verifica dell’indirizzo con Google in corso…';
  try{
    const result = await api('/api/routes/verify-stop-address',{method:'POST',body:JSON.stringify({indirizzo:address})});
    if(version !== occasionalVerificationVersion || val('osAddress') !== address) return false;
    if(!occasionalProofMatches(result,result.indirizzo)) throw new Error('Indirizzo inesistente o non trovato da Google: controlla via, numero civico e comune.');
    occasionalAddressProof = result;
    set('osAddress',result.indirizzo);
    status.textContent = '✓ Indirizzo verificato';
    return true;
  }catch(e){
    if(version === occasionalVerificationVersion) status.textContent = e.message || 'Indirizzo inesistente o non trovato da Google: controlla via, numero civico e comune.';
    return false;
  }finally{
    if(version === occasionalVerificationVersion) button.disabled = false;
  }
}

// Salvando, l'indirizzo non ancora confermato si verifica da solo; se Google non lo trova
// la finestra resta aperta con il motivo.
async function saveOccasionalStop(){
  if(!document.getElementById('occasionalStopForm').reportValidity()) return;
  if(!val('osName')){ document.getElementById('osName').focus(); return; }
  if(!occasionalProofMatches(occasionalAddressProof,val('osAddress')) && !await verifyOccasionalAddress()) return;
  const address = val('osAddress');
  const f = deliveries[occasionalStopIndex]?.order_refs?.length ? {...gfUniversalFeaturesV891,has_time_windows:true,has_ztl:true,needs_tail_lift:true} : gfUniversalFeaturesV891;
  const windowValue = id => f.has_time_windows ? val(id)||null : null;
  const d = {customer_id:null,cliente_nome:val('osName'),indirizzo:address,
    lat:occasionalAddressProof.lat,lon:occasionalAddressProof.lon,
    stato_geocodifica:'verificato',indirizzo_geocodificato:address,geocoding_token:occasionalAddressProof.geocoding_token,
    peso_kg:Number(val('osWeight')||0),colli:Number(val('osPackages')||0),
    scarico_mattina_da:windowValue('osMorningFrom'),scarico_mattina_a:windowValue('osMorningTo'),
    scarico_pomeriggio_da:windowValue('osAfternoonFrom'),scarico_pomeriggio_a:windowValue('osAfternoonTo'),
    tempo_scarico_min:Number(val('osUnloading')||0),ztl:!!f.has_ztl && boolVal('osZtl'),
    sponda:!!f.needs_tail_lift && boolVal('osTailLift'),note:val('osNotes')||null};
  if(occasionalStopIndex === null) addDeliveryObject(d);
  else{
    if(!deliveries[occasionalStopIndex] || deliveries[occasionalStopIndex].customer_id != null) return;
    Object.assign(d,globalThis.GFOrderPlanning?.metadata(deliveries[occasionalStopIndex])||{});
    deliveries[occasionalStopIndex] = d;
    renderDeliveries();
    markRouteNeedsRecalculation();
  }
  closeOccasionalStopModal();
}

function planningStopDragStart(event,index){
  planningDraggedStop = index;
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain',String(index));
}

function planningStopDrop(event,index){
  event.preventDefault();
  const source = planningDraggedStop;
  planningDraggedStop = null;
  if(source === null || source === index || !deliveries[source] || !deliveries[index]) return;
  deliveries.splice(index,0,deliveries.splice(source,1)[0]);
  renderDeliveries();
  markRouteNeedsRecalculation();
}

function planningStopDragEnd(){ planningDraggedStop = null; }
