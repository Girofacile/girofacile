const customerIcons = {"users": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75\"/><circle cx=\"9\" cy=\"7\" r=\"4\"/></svg>", "check": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"m8 12 3 3 5-6\"/></svg>", "clock": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 7v5l3 2\"/></svg>", "building": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M3 21V7l10-4v18M13 9h7v12H3m4-12v2m0 3v2m3-8v2m0 3v2m6-1v2m0-6v1\"/></svg>", "search": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"10.5\" cy=\"10.5\" r=\"6.5\"/><path d=\"m16 16 5 5\"/></svg>", "filter": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M3 4h18l-7 8v7l-4 2V12Z\"/></svg>", "list": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M8 6h13M8 12h13M8 18h13M3 6h1M3 12h1M3 18h1\"/></svg>", "grid": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><rect x=\"3\" y=\"3\" width=\"6\" height=\"6\" rx=\"1\"/><rect x=\"15\" y=\"3\" width=\"6\" height=\"6\" rx=\"1\"/><rect x=\"3\" y=\"15\" width=\"6\" height=\"6\" rx=\"1\"/><rect x=\"15\" y=\"15\" width=\"6\" height=\"6\" rx=\"1\"/></svg>", "delete": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7\"/></svg>", "edit": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z\"/></svg>", "details": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M6 3h8l4 4v14H6ZM14 3v5h4M9 12h6m-6 4h6\"/></svg>"};
const customerDirectory = {all:[], rows:[], page:1, size:8, sort:'nome', direction:'asc', view:'list', selected:new Set(), request:0};
async function refreshCustomerDirectory(){
  const request = ++customerDirectory.request;
  try {
    const all = [];
    for(let offset=0;;offset+=1000){
      const batch = await api(`/api/customers?limit=1000&offset=${offset}`);
      if(request !== customerDirectory.request) return;
      all.push(...batch);
      if(batch.length < 1000) break;
    }
    customerDirectory.all = all;
    customersCache = all;
    const ids = new Set(all.map(x=>x.id));
    customerDirectory.selected.forEach(id=>{if(!ids.has(id)) customerDirectory.selected.delete(id);});
    const verified = all.filter(x=>x.stato_geocodifica === 'verificato').length;
    for(const [key,value] of Object.entries({Total:all.length,Verified:verified,Pending:all.length-verified,Active:all.length})){
      const el=document.getElementById('customerMetric'+key); if(el) el.textContent=value;
    }
    renderCustomerDirectory();
  } catch(error){
    if(request !== customerDirectory.request) return;
    const count=document.getElementById('customerCount');
    if(count) count.textContent='Impossibile caricare i clienti. Riprova aprendo la sezione.';
    throw error;
  }
}
function customerFilteredRows(){
  const value=id=>(document.getElementById(id)?.value||'').trim().toLocaleLowerCase('it');
  const q=value('customerListSearch'), city=value('customerFilterComune'), province=value('customerFilterProvincia');
  const agent=agentsFeatureEnabled()?value('customerFilterAgent'):'';
  const ztl=value('customerFilterZtl'), lift=value('customerFilterSponda');
  const contains=(text,part)=>String(text||'').toLocaleLowerCase('it').includes(part);
  return customerDirectory.all.filter(x=>(!q||[x.nome,x.codice_cliente,x.indirizzo,x.comune].some(t=>contains(t,q))) && contains(x.comune,city) && contains(x.provincia,province) && (!agent||(agent==='interno'?!x.agent_id:String(x.agent_id)===agent)) && (!ztl||Boolean(x.ztl)===(ztl==='true')) && (!lift||Boolean(x.sponda)===(lift==='true'))).sort((a,b)=>{
    const comparison=String(a[customerDirectory.sort]||'').localeCompare(String(b[customerDirectory.sort]||''),'it',{numeric:true,sensitivity:'base'});
    return (customerDirectory.direction==='asc'?comparison:-comparison)||a.id-b.id;
  });
}
function filterCustomerList(){ customerDirectory.page=1; renderCustomerDirectory(); }
function setCustomerSort(value){
  [customerDirectory.sort,customerDirectory.direction]=value.split(':');
  filterCustomerList();
}
function toggleCustomerSort(key){
  setCustomerSort(key+':'+(customerDirectory.sort===key&&customerDirectory.direction==='asc'?'desc':'asc'));
}
function setCustomerView(view){ customerDirectory.view=view; renderCustomerDirectory(); }
function customerGoPage(page){customerDirectory.page=page;renderCustomerDirectory();}
function customerStatusMarkup(x){
  const status=x.stato_geocodifica||'da_verificare';
  const label={verificato:'Verificato',da_verificare:'Da verificare',non_trovato:'Non trovato',manuale:'Manuale'}[status]||'Da verificare';
  return `<span class="customer-status ${status==='verificato'?'verified':'pending'}">${customerIcons[status==='verificato'?'check':'clock']}${label}</span>`;
}
function customerActionsMarkup(x){
  const id=Number(x.id);
  return `<div class="customer-row-actions"><button onclick="openCustomerModal(${id})">${customerIcons.edit}Modifica</button><button onclick="showCustomerDetails(${id})">${customerIcons.details}Dettagli</button><button class="customer-delete" aria-label="Elimina ${esc(x.nome)}" title="Elimina cliente" onclick="deleteCustomer(${id})">${customerIcons.delete}</button></div>`;
}
function renderCustomerDirectory(){
  const body=document.getElementById('customersBody');if(!body)return;
  const state=customerDirectory, rows=customerFilteredRows();
  state.rows=rows;
  const pages=Math.max(1,Math.ceil(rows.length/state.size));
  state.page=Math.max(1,Math.min(state.page,pages));
  const start=(state.page-1)*state.size, visible=rows.slice(start,start+state.size);
  body.innerHTML=visible.map(x=>`<tr class="${state.selected.has(x.id)?'is-selected':''}"><td class="customer-checkbox"><input type="checkbox" aria-label="Seleziona ${esc(x.nome)}" ${state.selected.has(x.id)?'checked':''} onchange="selectDirectoryCustomer(${Number(x.id)},this.checked)"></td><td>${esc(x.codice_cliente||'—')}</td><td><strong>${esc(x.nome)}</strong><small>${esc([x.comune,x.provincia].filter(Boolean).join(' '))}</small></td><td>${esc(x.indirizzo)}</td><td data-gf-feature="time_windows" class="customer-unloading">${esc(fascia(x))}</td><td>${customerStatusMarkup(x)}</td><td>${customerActionsMarkup(x)}</td></tr>`).join('')||'<tr><td colspan="7" class="customer-empty">Nessun cliente trovato.</td></tr>';
  document.getElementById('customerCards').innerHTML=visible.map(x=>`<article class="customer-card"><div class="customer-card-heading"><label><input type="checkbox" aria-label="Seleziona ${esc(x.nome)}" ${state.selected.has(x.id)?'checked':''} onchange="selectDirectoryCustomer(${Number(x.id)},this.checked)"> ${esc(x.codice_cliente||'—')}</label>${customerStatusMarkup(x)}</div><h3>${esc(x.nome)}</h3><p>${esc(x.indirizzo)}</p><p>${esc([x.comune,x.provincia].filter(Boolean).join(' '))}</p><p data-gf-feature="time_windows">Scarico: ${esc(fascia(x))}</p>${customerActionsMarkup(x)}</article>`).join('')||'<p class="customer-empty">Nessun cliente trovato.</p>';
  document.getElementById('customerTableWrap').classList.toggle('hidden',state.view!=='list');
  document.getElementById('customerCards').classList.toggle('hidden',state.view!=='grid');
  document.getElementById('customerListView').setAttribute('aria-pressed',String(state.view==='list'));
  document.getElementById('customerGridView').setAttribute('aria-pressed',String(state.view==='grid'));
  document.getElementById('customerCount').textContent=`Vista ${rows.length?start+1:0}–${Math.min(start+state.size,rows.length)} di ${rows.length} clienti`;
  const pageButton=(p,label,disabled=false)=>`<button aria-label="${label==='‹'?'Pagina precedente':label==='›'?'Pagina successiva':'Pagina '+p}" ${disabled?'disabled':''} ${p===state.page&&label!=='‹'&&label!=='›'?'aria-current="page"':''} onclick="customerGoPage(${p})">${label}</button>`;
  const numbers=[...new Set([1,state.page-1,state.page,state.page+1,pages])].filter(p=>p>=1&&p<=pages).sort((a,b)=>a-b);
  document.getElementById('customerPagination').innerHTML=pageButton(state.page-1,'‹',state.page===1)+numbers.map((p,i)=>(i&&p>numbers[i-1]+1?'<span>…</span>':'')+pageButton(p,p)).join('')+pageButton(state.page+1,'›',state.page===pages);
  const selected=visible.filter(x=>state.selected.has(x.id)).length, all=document.getElementById('customerSelectAll');
  all.checked=!!visible.length&&selected===visible.length;all.indeterminate=selected>0&&selected<visible.length;all.disabled=!visible.length;
  const selection=document.getElementById('customerSelection');
  selection.classList.toggle('hidden',state.selected.size===0);
  selection.innerHTML=`${state.selected.size} clienti selezionati <button onclick="clearCustomerSelection()">Deseleziona tutti</button>`;
  document.querySelectorAll('[data-customer-sort]').forEach(th=>{
    const active=th.dataset.customerSort===state.sort;
    th.setAttribute('aria-sort',active?(state.direction==='asc'?'ascending':'descending'):'none');
    th.querySelector('span').textContent=active?(state.direction==='asc'?'↑':'↓'):'↕';
  });
  const sort=document.getElementById('customerSort'), sortValue=state.sort+':'+state.direction;
  // Header sorting also supports descending values absent from the initial menu.
  if(!Array.from(sort.options).some(option=>option.value===sortValue)){
    const option=document.createElement('option');option.value=sortValue;option.textContent=({indirizzo:'Indirizzo',stato_geocodifica:'Stato indirizzo',scarico_mattina_da:'Orario di scarico'}[state.sort]||'Nome')+': decrescente';sort.append(option);
  }
  sort.value=sortValue;
}
function selectDirectoryCustomer(id,checked){if(checked)customerDirectory.selected.add(id);else customerDirectory.selected.delete(id);renderCustomerDirectory();}
function selectCustomerPage(checked){
  const state=customerDirectory;
  state.rows.slice((state.page-1)*state.size,state.page*state.size).forEach(x=>{if(checked)state.selected.add(x.id);else state.selected.delete(x.id);});
  renderCustomerDirectory();
}
function clearCustomerSelection(){customerDirectory.selected.clear();renderCustomerDirectory();}
function showCustomerDetails(id){
  const x=customerDirectory.all.find(x=>x.id===id);if(!x)return;
  const fields=[['Codice',x.codice_cliente],['Indirizzo',x.indirizzo],['Comune',x.comune],['Provincia',x.provincia],['Referente',x.referente],['Telefono',x.telefono],['Email',x.email],['Scarico',fascia(x),'time_windows'],['Tempo di scarico',`${x.tempo_scarico_min??10} min`],['ZTL',x.ztl?'Sì':'No','ztl'],['Sponda',x.sponda?'Sì':'No','tail_lift'],['Note',x.note]];
  if(agentsFeatureEnabled())fields.push(['Agente',x.agent_name||'Cliente interno']);
  document.getElementById('customerDetailsContent').innerHTML=`<h2 id="customerDetailsTitle">${esc(x.nome)}</h2>${customerStatusMarkup(x)}<dl>${fields.map(([label,value,feature])=>`<div ${feature?`data-gf-feature="${feature}"`:''}><dt>${label}</dt><dd>${esc(value||'—')}</dd></div>`).join('')}</dl><div class="customer-detail-actions"><button class="btn-secondary" onclick="document.getElementById('customerDetailsDialog').close();verifyCustomerAddress(${Number(id)})">Verifica indirizzo</button><button class="btn-primary" onclick="document.getElementById('customerDetailsDialog').close();openCustomerModal(${Number(id)})">Modifica cliente</button></div>`;
  document.getElementById('customerDetailsDialog').showModal();
}
