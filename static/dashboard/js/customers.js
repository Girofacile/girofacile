const customerIcons = {"users": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75\"/><circle cx=\"9\" cy=\"7\" r=\"4\"/></svg>", "check": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"m8 12 3 3 5-6\"/></svg>", "clock": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 7v5l3 2\"/></svg>", "building": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M3 21V7l10-4v18M13 9h7v12H3m4-12v2m0 3v2m3-8v2m0 3v2m6-1v2m0-6v1\"/></svg>", "search": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><circle cx=\"10.5\" cy=\"10.5\" r=\"6.5\"/><path d=\"m16 16 5 5\"/></svg>", "filter": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M3 4h18l-7 8v7l-4 2V12Z\"/></svg>", "list": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M8 6h13M8 12h13M8 18h13M3 6h1M3 12h1M3 18h1\"/></svg>", "grid": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><rect x=\"3\" y=\"3\" width=\"6\" height=\"6\" rx=\"1\"/><rect x=\"15\" y=\"3\" width=\"6\" height=\"6\" rx=\"1\"/><rect x=\"3\" y=\"15\" width=\"6\" height=\"6\" rx=\"1\"/><rect x=\"15\" y=\"15\" width=\"6\" height=\"6\" rx=\"1\"/></svg>", "edit": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z\"/></svg>", "details": "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M6 3h8l4 4v14H6ZM14 3v5h4M9 12h6m-6 4h6\"/></svg>"};
const customerDirectory = {all:[], rows:[], page:1, size:8, sort:'nome', direction:'asc', view:'list', request:0};
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
  return `<div class="customer-row-actions"><button onclick="openCustomerModal(${id})" aria-label="Modifica" title="Modifica">${customerIcons.edit}Modifica</button><button onclick="showCustomerDetails(${id})">${customerIcons.details}Dettagli</button></div>`;
}
function renderCustomerDirectory(){
  const body=document.getElementById('customersBody');if(!body)return;
  const state=customerDirectory, rows=customerFilteredRows();
  state.rows=rows;
  const pages=Math.max(1,Math.ceil(rows.length/state.size));
  state.page=Math.max(1,Math.min(state.page,pages));
  const start=(state.page-1)*state.size, visible=rows.slice(start,start+state.size);
  body.innerHTML=visible.map(x=>`<tr><td>${esc(x.codice_cliente||'—')}</td><td><strong>${esc(x.nome)}</strong><small>${esc([x.comune,x.provincia].filter(Boolean).join(' '))}</small></td><td>${esc(x.indirizzo)}</td><td data-gf-feature="time_windows" class="customer-unloading">${esc(fascia(x))}</td><td>${customerStatusMarkup(x)}</td><td>${customerActionsMarkup(x)}</td></tr>`).join('')||'<tr><td colspan="6" class="customer-empty">Nessun cliente trovato.</td></tr>';
  document.getElementById('customerCards').innerHTML=visible.map(x=>`<article class="customer-card"><div class="customer-card-heading"><span>${esc(x.codice_cliente||'—')}</span>${customerStatusMarkup(x)}</div><h3>${esc(x.nome)}</h3><p>${esc(x.indirizzo)}</p><p>${esc([x.comune,x.provincia].filter(Boolean).join(' '))}</p><p data-gf-feature="time_windows">Scarico: ${esc(fascia(x))}</p>${customerActionsMarkup(x)}</article>`).join('')||'<p class="customer-empty">Nessun cliente trovato.</p>';
  document.getElementById('customerTableWrap').classList.toggle('hidden',state.view!=='list');
  document.getElementById('customerCards').classList.toggle('hidden',state.view!=='grid');
  document.getElementById('customerListView').setAttribute('aria-pressed',String(state.view==='list'));
  document.getElementById('customerGridView').setAttribute('aria-pressed',String(state.view==='grid'));
  document.getElementById('customerCount').textContent=`Vista ${rows.length?start+1:0}–${Math.min(start+state.size,rows.length)} di ${rows.length} clienti`;
  const pageButton=(p,label,disabled=false)=>`<button aria-label="${label==='‹'?'Pagina precedente':label==='›'?'Pagina successiva':'Pagina '+p}" ${disabled?'disabled':''} ${p===state.page&&label!=='‹'&&label!=='›'?'aria-current="page"':''} onclick="customerGoPage(${p})">${label}</button>`;
  const numbers=[...new Set([1,state.page-1,state.page,state.page+1,pages])].filter(p=>p>=1&&p<=pages).sort((a,b)=>a-b);
  document.getElementById('customerPagination').innerHTML=pageButton(state.page-1,'‹',state.page===1)+numbers.map((p,i)=>(i&&p>numbers[i-1]+1?'<span>…</span>':'')+pageButton(p,p)).join('')+pageButton(state.page+1,'›',state.page===pages);
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
function showCustomerDetails(id){
  const x=customerDirectory.all.find(x=>x.id===id);if(!x)return;
  const fields=[['Codice',x.codice_cliente],['Indirizzo',x.indirizzo],['Comune',x.comune],['Provincia',x.provincia],['Referente',x.referente],['Telefono',x.telefono],['Email',x.email],['Scarico',fascia(x),'time_windows'],['Tempo di scarico',`${x.tempo_scarico_min??10} min`],['ZTL',x.ztl?'Sì':'No','ztl'],['Sponda',x.sponda?'Sì':'No','tail_lift'],['Note',x.note]];
  if(agentsFeatureEnabled())fields.push(['Agente',x.agent_name||'Cliente interno']);
  document.getElementById('customerDetailsContent').innerHTML=`<h2 id="customerDetailsTitle">${esc(x.nome)}</h2>${customerStatusMarkup(x)}<dl>${fields.map(([label,value,feature])=>`<div ${feature?`data-gf-feature="${feature}"`:''}><dt>${label}</dt><dd>${esc(value||'—')}</dd></div>`).join('')}</dl><div class="customer-detail-actions"><button class="btn-secondary" onclick="document.getElementById('customerDetailsDialog').close();verifyCustomerAddress(${Number(id)})">Verifica indirizzo</button><button class="btn-primary" onclick="document.getElementById('customerDetailsDialog').close();openCustomerModal(${Number(id)})">Modifica cliente</button></div>`;
  document.getElementById('customerDetailsDialog').showModal();
}


/* Active Customers interaction module, initialized after core.js is available. */
document.addEventListener('DOMContentLoaded', function initCustomerDirectoryEnhancements(){
/* GiroFacile: customer directory enhancement based on supplied Customers HTML.
   Uses real customerDirectory records and existing API. Does not touch sidebar. */
(function(){
  'use strict';
  if(typeof renderCustomerDirectory!=='function'||typeof customerFilteredRows!=='function'||typeof refreshCustomerDirectory!=='function')return;
  const ui={quick:'all',selected:new Set(),busy:false};
  const id=x=>Number(x.id);
  const hasSlot=x=>Boolean((x.scarico_mattina_da&&x.scarico_mattina_a)||(x.scarico_pomeriggio_da&&x.scarico_pomeriggio_a));
  const isVerified=x=>x.stato_geocodifica==='verificato';
  const safe=x=>esc(String(x==null?'':x));
  const originalFilter=customerFilteredRows;
  customerFilteredRows=function(){
    return originalFilter().filter(x=>ui.quick==='all'
      ||(ui.quick==='verified'&&isVerified(x))
      ||(ui.quick==='unverified'&&!isVerified(x))
      ||(ui.quick==='withSlot'&&hasSlot(x))
      ||(ui.quick==='noSlot'&&!hasSlot(x)));
  };
  function setQuick(quick){
    ui.quick=quick;customerDirectory.page=1;renderCustomerDirectory();
  }
  window.setCustomerQuickFilter=setQuick;
  window.reverseCustomerSort=function(){
    setCustomerSort(customerDirectory.sort+':'+(customerDirectory.direction==='asc'?'desc':'asc'));
  };
  window.clearCustomerListAllFilters=function(){
    ['customerListSearch','customerFilterComune','customerFilterProvincia','customerFilterAgent','customerFilterZtl','customerFilterSponda']
      .forEach(k=>{const el=document.getElementById(k);if(el)el.value='';});
    ui.quick='all';filterCustomerList();
  };
  window.clearCustomerSelection=function(){ui.selected.clear();renderCustomerDirectory();};
  function initials(name){
    return (String(name||'?').trim().split(/\s+/).slice(0,2).map(w=>w.charAt(0)).join('')||'?').toLocaleUpperCase('it');
  }
  function avatar(x){
    const span=document.createElement('span');
    span.className='gf-customer-avatar gf-customer-avatar-'+(id(x)%6);
    span.setAttribute('aria-hidden','true');span.textContent=initials(x.nome);
    return span;
  }
  function renderQuick(){
    const root=document.getElementById('customerQuickFilters');
    const all=customerDirectory.all,unver=all.filter(x=>!isVerified(x)).length,noslot=all.filter(x=>!hasSlot(x)).length;
    const chips=[['all','Tutti',all.length],['unverified','Da verificare',unver],['noSlot','Senza fascia di scarico',noslot]];
    if(root){
      root.replaceChildren();
      chips.forEach(([key,label,num])=>{
        const btn=document.createElement('button');btn.type='button';
        btn.dataset.quick=key;btn.setAttribute('aria-pressed',String(ui.quick===key));
        btn.textContent=label;
        const n=document.createElement('span');n.textContent=String(num);btn.append(n);
        btn.addEventListener('click',()=>setQuick(key));root.append(btn);
      });
    }
    document.querySelectorAll('#tab-clienti [data-customer-quick]').forEach(btn=>{
      btn.setAttribute('aria-pressed',String(btn.dataset.customerQuick===ui.quick));
    });
    const advanced=['customerFilterComune','customerFilterProvincia','customerFilterAgent','customerFilterZtl','customerFilterSponda']
      .filter(k=>document.getElementById(k)?.value).length;
    const counter=document.getElementById('customerAdvancedFilterCount');
    if(counter){counter.textContent=String(advanced);counter.classList.toggle('hidden',!advanced);}
  }
  function renderSelection(){
    const bar=document.getElementById('customerBulkBar');
    if(!bar)return;
    const n=ui.selected.size;
    bar.classList.toggle('hidden',!n);
    document.getElementById('customerSelectedCount').textContent=n+' '+(n===1?'cliente selezionato':'clienti selezionati');
    const start=(customerDirectory.page-1)*customerDirectory.size;
    const page=customerDirectory.rows.slice(start,start+customerDirectory.size);
    const chosen=page.filter(x=>ui.selected.has(id(x))).length;
    const selectAll=document.getElementById('customerSelectPage');
    if(selectAll){
      selectAll.checked=!!page.length&&chosen===page.length;
      selectAll.indeterminate=chosen>0&&chosen<page.length;
      selectAll.disabled=!page.length;
    }
  }
  function enhanceTable(){
    const tbody=document.getElementById('customersBody');if(!tbody)return;
    const from=(customerDirectory.page-1)*customerDirectory.size;
    const page=customerDirectory.rows.slice(from,from+customerDirectory.size);
    Array.from(tbody.querySelectorAll('tr')).forEach((tr,i)=>{
      const x=page[i];if(!x)return;
      const cells=tr.querySelectorAll('td');
      if(cells.length!==6)return;
      tr.dataset.customerRow=String(id(x));
      if(ui.selected.has(id(x)))tr.classList.add('gf-customer-row-selected');
      const choice=document.createElement('td');choice.className='gf-customer-select-col';
      const cb=document.createElement('input');cb.type='checkbox';cb.className='gf-customer-checkbox';cb.dataset.customerId=String(id(x));cb.checked=ui.selected.has(id(x));cb.setAttribute('aria-label','Seleziona '+x.nome);
      choice.append(cb);tr.insertBefore(choice,tr.firstElementChild);
      const cell=cells[1],strong=cell.querySelector('strong');
      if(strong){
        const wrap=document.createElement('div');wrap.className='gf-customer-name-wrap';
        wrap.append(avatar(x));
        const name=document.createElement('div');name.className='gf-customer-name-text';
        while(cell.firstChild)name.append(cell.firstChild);
        wrap.append(name);cell.append(wrap);
        const smaller=name.querySelector('small');
        if(smaller)smaller.textContent=x.codice_cliente||'—';
      }
      const addr=cells[2];
      if(addr){
        addr.replaceChildren();
        const b=document.createElement('strong');b.textContent=x.indirizzo||'—';
        const sm=document.createElement('small');sm.textContent=[x.comune,x.provincia].filter(Boolean).join(' · ');
        addr.append(b,sm);
      }
      const slot=cells[3];
      if(slot&&hasSlot(x)){
        const span=document.createElement('span');span.className='gf-customer-slot';
        const ranges=[];
        if(x.scarico_mattina_da&&x.scarico_mattina_a)ranges.push(x.scarico_mattina_da+'–'+x.scarico_mattina_a);
        if(x.scarico_pomeriggio_da&&x.scarico_pomeriggio_a)ranges.push(x.scarico_pomeriggio_da+'–'+x.scarico_pomeriggio_a);
        span.innerHTML=customerIcons.clock;span.append(document.createTextNode(ranges.join(' / ')));slot.replaceChildren(span);
      }else if(slot){
        const button=document.createElement('button');button.type='button';button.className='gf-customer-slot gf-customer-slot-empty';
        button.textContent='Non impostata';button.addEventListener('click',()=>openCustomerModal(id(x)));slot.replaceChildren(button);
      }
    });
    const empty=tbody.querySelector('tr:not([data-customer-row]) td');
    if(empty){empty.colSpan=7;empty.innerHTML='<strong>Nessun cliente trovato</strong><p>Prova a modificare la ricerca o i filtri.</p><button type="button" class="btn-secondary" onclick="clearCustomerListAllFilters()">Azzera filtri</button>';}
  }
  function enhanceCards(){
    const cards=document.querySelectorAll('#customerCards .customer-card');
    const from=(customerDirectory.page-1)*customerDirectory.size;
    const page=customerDirectory.rows.slice(from,from+customerDirectory.size);
    Array.from(cards).forEach((card,i)=>{
      const x=page[i];if(!x)return;
      if(ui.selected.has(id(x)))card.classList.add('gf-customer-card-selected');
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.className='gf-customer-checkbox gf-customer-card-checkbox';
      checkbox.dataset.customerId=String(id(x));checkbox.checked=ui.selected.has(id(x));
      checkbox.setAttribute('aria-label','Seleziona '+x.nome);card.prepend(checkbox);
      const title=card.querySelector('h3');if(title)title.prepend(avatar(x));
      const addr=card.querySelectorAll('p');if(addr.length>1)addr[1].textContent=[x.comune,x.provincia].filter(Boolean).join(' · ');
    });
  }
  const originalRender=renderCustomerDirectory;
  renderCustomerDirectory=function(){
    originalRender();
    enhanceTable();enhanceCards();renderQuick();renderSelection();
  };
  const originalRefresh=refreshCustomerDirectory;
  refreshCustomerDirectory=async function(){
    await originalRefresh();
    const set=new Set(customerDirectory.all.map(id));
    for(const customerId of ui.selected)if(!set.has(customerId))ui.selected.delete(customerId);
    const total=customerDirectory.all.length;
    const verified=customerDirectory.all.filter(isVerified).length;
    const withSlot=customerDirectory.all.filter(hasSlot).length;
    const measure=document.getElementById('customerMetricWithSlot');
    if(measure)measure.textContent=String(withSlot);
    const verifiedRatio=document.getElementById('customerMetricVerifiedTotal');
    if(verifiedRatio)verifiedRatio.textContent='su '+total;
    const slotRatio=document.getElementById('customerMetricWithSlotTotal');
    if(slotRatio)slotRatio.textContent='su '+total;
    const remaining=document.getElementById('customerMetricSlotsRemaining');
    if(remaining){
      const pending=total-withSlot;
      remaining.textContent=pending?(pending+' da impostare'):'Tutte impostate';
      remaining.style.color=pending?'#b7791f':'#127a52';
    }
    const progress=document.getElementById('customerMetricSlotProgress');
    if(progress)progress.style.width=(total?Math.round(withSlot/total*100):0)+'%';
    renderSelection();
  };
  document.addEventListener('click',event=>{
    const kpi=event.target.closest('#tab-clienti [data-customer-quick]');
    if(kpi){setQuick(kpi.dataset.customerQuick);return;}
    const row=event.target.closest('#tab-clienti tr[data-customer-row]');
    if(row&&!event.target.closest('button,input,a,label,select'))showCustomerDetails(Number(row.dataset.customerRow));
  });
  document.addEventListener('change',event=>{
    const t=event.target;
    if(t.id==='customerSelectPage'){
      const from=(customerDirectory.page-1)*customerDirectory.size;
      customerDirectory.rows.slice(from,from+customerDirectory.size).forEach(x=>{
        if(t.checked)ui.selected.add(id(x));else ui.selected.delete(id(x));
      });
      renderCustomerDirectory();return;
    }
    if(t.matches('.gf-customer-checkbox')){
      const n=Number(t.dataset.customerId);
      if(t.checked)ui.selected.add(n);else ui.selected.delete(n);
      renderCustomerDirectory();
    }
  });
  window.openCustomerBulkSlotDialog=function(){
    if(!ui.selected.size)return;
    const d=document.getElementById('customerBulkSlotDialog');
    document.getElementById('customerBulkStatus').textContent='';
    if(!d.open)d.showModal();
  };
  window.applyCustomerBulkSlot=async function(mode){
    if(ui.busy)return;
    const slots={
      morning:{scarico_mattina_da:'06:00',scarico_mattina_a:'12:00'},
      afternoon:{scarico_pomeriggio_da:'14:00',scarico_pomeriggio_a:'18:00'},
      day:{scarico_mattina_da:'06:00',scarico_mattina_a:'18:00'},
      clear:{}
    };
    let spec=slots[mode];
    const status=document.getElementById('customerBulkStatus');
    if(mode==='custom'){
      const from=document.getElementById('customerBulkFrom').value;
      const to=document.getElementById('customerBulkTo').value;
      if(!from||!to||from>=to){status.textContent='Inserisci un orario di inizio e fine valido.';return;}
      spec={scarico_mattina_da:from,scarico_mattina_a:to};
    }
    if(!spec)return;
    const selected=customerDirectory.all.filter(x=>ui.selected.has(id(x)));
    if(!selected.length)return;
    if(!confirm('Sostituire le fasce orarie per '+selected.length+' '+(selected.length===1?'cliente':'clienti')+'?'))return;
    const fields=['agent_id','codice_cliente','nome','indirizzo','comune','provincia','telefono','referente','email',
      'scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a','tempo_scarico_min',
      'ztl','sponda','transpallet','note','lat','lon','indirizzo_geocodificato','stato_geocodifica',
      'affidabilita_geocodifica','fonte_geocodifica','google_place_id'];
    const buttons=[...document.querySelectorAll('#customerBulkSlotDialog button')];
    ui.busy=true;buttons.forEach(b=>b.disabled=true);
    let done=0,error=null;
    try{
      for(const x of selected){
        const payload=Object.fromEntries(fields.map(key=>[key,x[key]??null]));
        ['scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a'].forEach(k=>payload[k]=spec[k]||null);
        try{
          await api('/api/customers/'+id(x),{method:'PUT',body:JSON.stringify(payload)});
          ui.selected.delete(id(x));done++;
          status.textContent='Aggiornati '+done+' di '+selected.length+' clienti…';
        }catch(e){error=e;break;}
      }
      await refreshCustomerDirectory();
      if(done&&typeof loadCustomerPicker==='function')await loadCustomerPicker();
      if(error)status.textContent='Aggiornati '+done+' clienti. Errore: '+(error.message||'Salvataggio non riuscito')+'. Gli altri restano selezionati.';
      else {
        document.getElementById('customerBulkSlotDialog').close();
        if(typeof toast==='function')toast('Fasce aggiornate per '+done+' clienti.');
      }
    }finally{buttons.forEach(b=>b.disabled=false);ui.busy=false;}
  };
  if(document.getElementById('customersBody'))renderCustomerDirectory();
})();

}, {once:true});
