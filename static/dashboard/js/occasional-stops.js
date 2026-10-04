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
  document.getElementById('osVerificationStatus').textContent = 'Indirizzo da verificare';
  document.getElementById('osSave').disabled = true;
  document.getElementById('osVerify').disabled = false;
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

async function verifyOccasionalAddress(){
  const address = val('osAddress');
  invalidateOccasionalAddress();
  if(address.length < 4) return;
  const version = occasionalVerificationVersion;
  const button = document.getElementById('osVerify');
  const status = document.getElementById('osVerificationStatus');
  button.disabled = true;
  status.textContent = 'Verifica in corso…';
  try{
    const result = await api('/api/routes/verify-stop-address',{method:'POST',body:JSON.stringify({indirizzo:address})});
    if(version !== occasionalVerificationVersion || val('osAddress') !== address) return;
    if(!occasionalProofMatches(result,result.indirizzo)) throw new Error('Indirizzo da verificare');
    occasionalAddressProof = result;
    set('osAddress',result.indirizzo);
    status.textContent = '✓ Indirizzo verificato';
    document.getElementById('osSave').disabled = false;
  }catch(e){
    if(version === occasionalVerificationVersion) status.textContent = e.message || 'Indirizzo da verificare';
  }finally{
    if(version === occasionalVerificationVersion) button.disabled = false;
  }
}

function saveOccasionalStop(){
  if(!document.getElementById('occasionalStopForm').reportValidity()) return;
  if(!val('osName')){ document.getElementById('osName').focus(); return; }
  const address = val('osAddress');
  if(!occasionalProofMatches(occasionalAddressProof,address)){
    invalidateOccasionalAddress(); return;
  }
  const f = gfUniversalFeaturesV891;
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
