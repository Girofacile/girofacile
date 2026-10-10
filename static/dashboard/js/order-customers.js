/* Customer recognition and actionable order anomalies, without nested dialogs. */
(function(){
  'use strict';
  let order=null, sequence=0;
  const can=key=>!window.GFCompanyAccess || GFCompanyAccess.can(key);
  const panel=()=>document.getElementById('orderCustomerPanel');
  function render(value){
    order=value;const request=++sequence;
    const host=panel();if(!host)return;
    const issues=value.anomalies||[];
    host.innerHTML=`<h2>Verifiche e cliente</h2>${issues.length?'<ul>'+issues.map(a=>`<li>${a.blocking?'Da risolvere: ':'Da controllare: '}${esc(a.message)}</li>`).join('')+'</ul>':'<p>Nessuna anomalia rilevata.</p>'}<p>L’indirizzo e gli orari specificati nell’ordine prevalgono sull’anagrafica. I dati originali restano conservati.</p>`;
    if(value.inherited_fields?.includes('time_windows'))host.innerHTML+=`<p>Fasce dal cliente: ${['scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a'].map(k=>esc(value.effective_data[k]||'—')).join(' · ')}</p>`;
    if(!can('orders.match') || !['nuovo','da_verificare','pronto'].includes(value.status) || value.assignments.length)return;
    host.innerHTML+=`<div class="page-actions"><button class="btn-secondary" onclick="GFOrderCustomers.action('recognize')">Riconosci cliente</button><button class="btn-secondary" onclick="GFOrderCustomers.action('separate')">No, mantieni separati</button>${can('customers.create')?'<button class="btn-secondary" onclick="GFOrderCustomers.create()">Crea nuova anagrafica cliente</button>':''}</div><label for="orderCustomerSearch">Cerca un altro cliente</label><div class="page-actions"><input id="orderCustomerSearch" maxlength="200" placeholder="Nome o indirizzo"><button class="btn-secondary" onclick="GFOrderCustomers.search()">Cerca</button></div><p id="orderCustomerMessage" role="status"></p><div id="orderCustomerCandidates"></div>`;
    GFOrders.request(`/api/orders/${value.id}/customers`).then(result=>{if(request===sequence)show(result);}).catch(e=>{if(request===sequence)message(e.message);});
  }
  function message(text){const target=document.getElementById('orderCustomerMessage');if(target)target.textContent=text;}
  function show(result){
    message(({linked:'Cliente già collegato.',separate:'Destinatario mantenuto separato dall’anagrafica.',none:'Nessun cliente riconosciuto. Puoi usare il destinatario solo per questo ordine.',invalid:'Il collegamento precedente non è più valido. Scegli un cliente attivo o mantieni separato il destinatario.',certain:'Corrispondenza certa: premi Riconosci cliente per collegarla.',probable:'Abbiamo trovato clienti che potrebbero corrispondere. Confronta i dati prima di associarli.',search:'Risultati della ricerca (massimo 20). Restringi il testo se necessario.'})[result.kind]||'');
    const rows=result.customer?[result.customer]:result.candidates||[];
    document.getElementById('orderCustomerCandidates').innerHTML=rows.map(c=>`<article class="panel"><p><strong>Ordine:</strong> ${esc(order.recipient_name||'Non indicato')} · ${esc(order.delivery_address||'Non indicato')}</p><p><strong>Cliente:</strong> ${esc(c.name)} · ${esc(c.address)}</p><p>${esc(c.reason)}</p>${result.kind!=='linked'?`<button class="btn-primary" onclick="GFOrderCustomers.action('link',${c.id})">Sì, associa</button>`:''}</article>`).join('');
  }
  async function action(action,customer_id){
    const id=order.id;const request=++sequence;
    panel().querySelectorAll('button').forEach(b=>b.disabled=true);
    message('Salvataggio…');
    try{const value=await GFOrders.request(`/api/orders/${id}/customer`,{method:'POST',body:JSON.stringify({version:order.version,action,customer_id})});if(request===sequence)GFOrders.apply(value);}
    catch(e){if(request===sequence){message(e.message);panel()?.querySelectorAll('button').forEach(b=>b.disabled=false);}}
  }
  async function search(){const request=++sequence;try{const result=await GFOrders.request(`/api/orders/${order.id}/customers?q=${encodeURIComponent(document.getElementById('orderCustomerSearch').value)}`);if(request===sequence)show(result);}catch(e){if(request===sequence)message(e.message);}}
  window.GFOrderCustomers={render,action,search,create(){if(confirm('Creare una nuova anagrafica con nome e indirizzo dell’ordine? L’indirizzo del cliente dovrà essere verificato separatamente.'))action('create');}};
})();
