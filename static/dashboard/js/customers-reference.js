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
