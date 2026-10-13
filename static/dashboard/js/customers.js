/* GiroFacile · pagina Clienti (riferimento grafico del 14 ottobre 2026).
   Ricrea fedelmente il layout di riferimento usando i dati reali e le API
   esistenti: striscia indicatori, elenco/schede, filtri, pannello laterale per
   dettagli, modifica e nuovo cliente, selezione multipla con fascia di scarico. */

const customerDirectory = {all:[], rows:[], page:1, size:8, sort:'nome', direction:'asc', view:'list', request:0, quick:'all', selected:new Set(), busy:false};

const CX_ICONS = {
  check:'M5 12.5l4.5 4.5L19 7.5',
  clock:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2',
  edit:'M4 20h4L19 9l-4-4L4 16z M14 6l4 4',
  eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  close:'M6 6l12 12 M18 6L6 18',
  sort:'M7 4v16 M3 8l4-4 4 4 M17 20V4 M13 16l4 4 4-4',
  up:'M12 19V5 M6 11l6-6 6 6',
  down:'M12 5v14 M6 13l6 6 6-6',
  chevl:'M15 6l-6 6 6 6',
  chevr:'M9 6l6 6-6 6',
  pin:'M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
  plus:'M12 5v14 M5 12h14'
};
const CX_PRESETS = [['Mattina','06:00','12:00'],['Pomeriggio','14:00','18:00'],['Giornata','06:00','18:00']];
const CX_FIELDS = ['agent_id','codice_cliente','nome','indirizzo','comune','provincia','telefono','referente','email',
  'scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a','tempo_scarico_min',
  'ztl','sponda','transpallet','note','lat','lon','indirizzo_geocodificato','stato_geocodifica',
  'affidabilita_geocodifica','fonte_geocodifica','google_place_id'];
const CX_GEO_FIELDS = ['lat','lon','indirizzo_geocodificato','stato_geocodifica','affidabilita_geocodifica','fonte_geocodifica','google_place_id'];

function cxIcon(name){return '<svg class="cx-i" viewBox="0 0 24 24" aria-hidden="true"><path d="'+CX_ICONS[name]+'"/></svg>';}
function cxEsc(value){return typeof esc==='function'?esc(value==null?'':value):String(value==null?'':value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function cxEl(id){return typeof document!=='undefined'&&document.getElementById?document.getElementById(id):null;}
function cxVerified(x){return x.stato_geocodifica==='verificato';}
function cxHasSlot(x){return Boolean((x.scarico_mattina_da&&x.scarico_mattina_a)||(x.scarico_pomeriggio_da&&x.scarico_pomeriggio_a));}
function cxSlots(x){
  const out=[];
  if(x.scarico_mattina_da&&x.scarico_mattina_a)out.push(x.scarico_mattina_da+' – '+x.scarico_mattina_a);
  if(x.scarico_pomeriggio_da&&x.scarico_pomeriggio_a)out.push(x.scarico_pomeriggio_da+' – '+x.scarico_pomeriggio_a);
  return out;
}
function cxInitials(name){
  const words=String(name||'').split(/\s+/).filter(w=>/^[A-Za-zÀ-ÿ0-9]/.test(w));
  return (((words[0]||'?')[0]||'?')+(words[1]?words[1][0]:'')).toLocaleUpperCase('it');
}
function cxColor(x){
  const key=String(x.codice_cliente||x.id||'');let h=0;
  for(let i=0;i<key.length;i++)h=(h*31+key.charCodeAt(i))%6;
  return 'var(--cx-a'+(h+1)+')';
}
function cxPlace(x){return [x.comune,x.provincia?'('+x.provincia+')':''].filter(Boolean).join(' ');}

/* ---------- Dati ---------- */
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
    const verified = all.filter(cxVerified).length;
    for(const [key,value] of Object.entries({Total:all.length,Verified:verified,Pending:all.length-verified,Active:all.length})){
      const el=cxEl('customerMetric'+key); if(el) el.textContent=value;
    }
    const ids=new Set(all.map(x=>Number(x.id)));
    for(const id of customerDirectory.selected) if(!ids.has(id)) customerDirectory.selected.delete(id);
    cxFillPlaceFilters();
    renderCustomerDirectory();
  } catch(error){
    if(request !== customerDirectory.request) return;
    const count=cxEl('customerCount');
    if(count) count.textContent='Impossibile caricare i clienti. Riprova aprendo la sezione.';
    throw error;
  }
}

/* ---------- Filtri e ordinamento ---------- */
function customerFilteredRows(){
  const value=id=>(cxEl(id)?.value||'').trim().toLocaleLowerCase('it');
  const lower=text=>String(text||'').trim().toLocaleLowerCase('it');
  const q=value('customerListSearch'), city=value('customerFilterComune'), province=value('customerFilterProvincia');
  const agent=(typeof agentsFeatureEnabled==='function'&&agentsFeatureEnabled())?value('customerFilterAgent'):'';
  const ztl=value('customerFilterZtl'), lift=value('customerFilterSponda');
  const quick=customerDirectory.quick;
  const key=customerDirectory.sort, dir=customerDirectory.direction==='desc'?-1:1;
  const sortValue=x=>key==='scarico_mattina_da'?(x.scarico_mattina_da||x.scarico_pomeriggio_da||'99')
    : key==='indirizzo'?[x.comune,x.indirizzo].filter(Boolean).join(' ')
    : key==='stato_geocodifica'?(cxVerified(x)?'1':'0')
    : String(x[key]||'');
  return customerDirectory.all.filter(x=>
    (!q||[x.nome,x.codice_cliente,x.indirizzo,x.comune,x.provincia].some(t=>lower(t).includes(q)))
    && (!city||lower(x.comune)===city)
    && (!province||lower(x.provincia)===province)
    && (!agent||(agent==='interno'?!x.agent_id:String(x.agent_id)===agent))
    && (!ztl||Boolean(x.ztl)===(ztl==='true'))
    && (!lift||Boolean(x.sponda)===(lift==='true'))
    && (quick==='all'||(quick==='unverified'&&!cxVerified(x))||(quick==='noSlot'&&!cxHasSlot(x))||(quick==='verified'&&cxVerified(x))||(quick==='withSlot'&&cxHasSlot(x)))
  ).sort((a,b)=>{
    let r=String(sortValue(a)).localeCompare(String(sortValue(b)),'it',{numeric:true,sensitivity:'base'});
    if(r===0)r=String(a.nome||'').localeCompare(String(b.nome||''),'it',{sensitivity:'base'});
    return (r*dir)||Number(a.id)-Number(b.id);
  });
}
function filterCustomerList(){ customerDirectory.page=1; renderCustomerDirectory(); }
function setCustomerSort(value){
  const [key,direction]=String(value).split(':');
  customerDirectory.sort=key||'nome';
  customerDirectory.direction=direction==='desc'?'desc':'asc';
  filterCustomerList();
}
function toggleCustomerSort(key){
  setCustomerSort(key+':'+(customerDirectory.sort===key&&customerDirectory.direction==='asc'?'desc':'asc'));
}
function reverseCustomerSort(){ setCustomerSort(customerDirectory.sort+':'+(customerDirectory.direction==='asc'?'desc':'asc')); }
function setCustomerView(view){ customerDirectory.view=view==='grid'?'grid':'list'; renderCustomerDirectory(); }
function customerGoPage(page){ customerDirectory.page=page; renderCustomerDirectory(); }
function setCustomerQuickFilter(quick){ customerDirectory.quick=quick; filterCustomerList(); }
function clearCustomerListAllFilters(){
  ['customerListSearch','customerFilterComune','customerFilterProvincia','customerFilterAgent','customerFilterZtl','customerFilterSponda']
    .forEach(k=>{const el=cxEl(k);if(el)el.value='';});
  customerDirectory.quick='all';filterCustomerList();
}
function cxFillPlaceFilters(){
  const fill=(id,values)=>{
    const select=cxEl(id);if(!select)return;
    const current=select.value;
    select.innerHTML='<option value="">Tutte</option>'+values.map(v=>'<option value="'+cxEsc(v)+'">'+cxEsc(v)+'</option>').join('');
    select.value=values.includes(current)?current:'';
  };
  const unique=values=>[...new Set(values.map(v=>String(v||'').trim()).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'it'));
  fill('customerFilterProvincia',unique(customerDirectory.all.map(x=>String(x.provincia||'').toUpperCase())));
  fill('customerFilterComune',unique(customerDirectory.all.map(x=>x.comune)));
}

/* ---------- Render ---------- */
function customerStatusMarkup(x){
  return cxVerified(x)
    ? '<span class="cx-chip cx-green">'+cxIcon('check')+'Verificato</span>'
    : x.stato_geocodifica==='non_trovato'
      ? '<span class="cx-chip cx-red">Non trovato</span>'
      : '<span class="cx-chip cx-amber">Da verificare</span>';
}
function cxSlotMarkup(x){
  const slots=cxSlots(x);
  return slots.length
    ? '<span class="cx-slot">'+cxIcon('clock')+cxEsc(slots.join(' / '))+'</span>'
    : '<button type="button" class="cx-slot cx-none" data-cx-slot="'+Number(x.id)+'" title="Imposta la fascia di scarico">Non impostata</button>';
}
function cxActions(x){
  const id=Number(x.id);
  return '<div class="cx-acts"><button type="button" class="cx-ibtn" data-cx-edit="'+id+'" title="Modifica" aria-label="Modifica '+cxEsc(x.nome)+'">'+cxIcon('edit')+'</button>'
    +'<button type="button" class="cx-btn cx-line cx-sm" data-cx-open="'+id+'">'+cxIcon('eye')+'Dettagli</button></div>';
}
function cxAvatar(x,big){
  return '<span class="cx-av'+(big?' cx-big':'')+'" style="--a:'+cxColor(x)+'" aria-hidden="true">'+cxEsc(x.nome?cxInitials(x.nome):'+')+'</span>';
}
function cxNameCell(x){
  return '<div class="cx-cl">'+cxAvatar(x)+'<div><b>'+cxEsc(x.nome)+'</b><small>'+cxEsc(x.codice_cliente||'Senza codice')+'</small></div></div>';
}
function cxAddressCell(x){
  return '<div class="cx-ad"><b>'+cxEsc(x.indirizzo||'—')+'</b><small>'+cxEsc(cxPlace(x)||'Comune non indicato')+'</small></div>';
}
function renderCustomerKpis(){
  const root=cxEl('customerKpis');if(!root)return;
  const all=customerDirectory.all,t=all.length,ver=all.filter(cxVerified).length,un=t-ver,wf=all.filter(cxHasSlot).length;
  const cell=(quick,label,value,note,warn,bar,feature,id)=>'<button type="button" data-cx-quick="'+quick+'"'+(feature?' data-gf-feature="'+feature+'"':'')+'>'
    +'<span class="cx-kl">'+label+'</span><span class="cx-kv" id="'+id+'">'+value+'</span><span class="cx-kn'+(warn?' cx-warn':'')+'">'+note+'</span>'
    +(bar!=null?'<span class="cx-bar2"><i style="width:'+bar+'%"></i></span>':'')+'</button>';
  root.innerHTML=
    cell('all','Totale clienti',t,'Tutti i clienti registrati',false,null,'','customerMetricTotal')+
    cell('all','Indirizzi verificati',ver+'<small>su '+t+'</small>','Indirizzi con verifica completata',false,null,'','customerMetricVerified')+
    cell('unverified','Da verificare',un,'Indirizzi ancora da verificare',un>0,null,'','customerMetricPending')+
    cell('noSlot','Con fascia di scarico',wf+'<small>su '+t+'</small>',wf<t?(t-wf)+' da impostare':'Tutte impostate',wf<t,t?Math.round(wf/t*100):0,'time_windows','customerMetricWithSlot');
}
function renderCustomerQuick(){
  const root=cxEl('customerQuickFilters');
  const all=customerDirectory.all,un=all.filter(x=>!cxVerified(x)).length,nf=all.filter(x=>!cxHasSlot(x)).length;
  const chips=[['all','Tutti',all.length,''],['unverified','Da verificare',un,''],['noSlot','Senza fascia di scarico',nf,'time_windows']];
  if(root)root.innerHTML=chips.map(([key,label,n,feature])=>'<button type="button" data-cx-quick="'+key+'"'+(feature?' data-gf-feature="'+feature+'"':'')+' aria-pressed="'+(customerDirectory.quick===key)+'">'+label+'<em>'+n+'</em></button>').join('');
  const active=['customerFilterComune','customerFilterProvincia','customerFilterAgent','customerFilterZtl','customerFilterSponda'].filter(k=>cxEl(k)?.value).length;
  const counter=cxEl('customerAdvancedFilterCount');
  if(counter){counter.hidden=!active;counter.textContent=String(active);}
}
function renderCustomerDirectory(){
  const target=cxEl('customerResults');if(!target)return;
  const state=customerDirectory, rows=customerFilteredRows();
  state.rows=rows;
  const pages=Math.max(1,Math.ceil(rows.length/state.size));
  state.page=Math.max(1,Math.min(state.page,pages));
  const from=(state.page-1)*state.size, visible=rows.slice(from,from+state.size);
  const sel=state.selected;
  let html='';
  if(!rows.length){
    const none=!state.all.length;
    html='<div class="cx-empty customer-empty"><b>'+(none?'Nessun cliente registrato':'Nessun cliente trovato')+'</b>'
      +(none?'Aggiungi il primo cliente oppure importa un file CSV/Excel.':'Prova a cambiare la ricerca o i filtri.')+'<br>'
      +(none?'<button type="button" class="cx-btn cx-sm" onclick="openCustomerDrawer(null,\'new\')">'+cxIcon('plus')+'Nuovo cliente</button>'
            :'<button type="button" class="cx-btn cx-line cx-sm" onclick="clearCustomerListAllFilters()">Azzera ricerca e filtri</button>')+'</div>';
  }else if(state.view==='list'){
    const allSel=visible.every(x=>sel.has(Number(x.id)));
    const head=(key,label,feature)=>{
      const on=state.sort===key;
      const icon=on?(state.direction==='desc'?'down':'up'):'sort';
      return '<th'+(feature?' data-gf-feature="'+feature+'"':'')+' aria-sort="'+(on?(state.direction==='desc'?'descending':'ascending'):'none')+'"><button type="button" data-cx-sort="'+key+'" class="'+(on?'cx-on':'')+'">'+label+cxIcon(icon)+'</button></th>';
    };
    html='<div class="cx-table-wrap" id="customerTableWrap"><table class="cx-table"><thead><tr>'
      +'<th class="cx-ck" data-gf-feature="time_windows"><input type="checkbox" class="cx-cb" id="customerSelectPage" aria-label="Seleziona tutti i clienti della pagina"'+(allSel?' checked':'')+'></th>'
      +head('nome','Cliente')+head('indirizzo','Indirizzo')+head('scarico_mattina_da','Fascia di scarico','time_windows')+head('stato_geocodifica','Stato indirizzo')
      +'<th class="cx-right">Azioni</th></tr></thead><tbody id="customersBody">'
      +visible.map(x=>{
        const id=Number(x.id),on=sel.has(id);
        return '<tr data-cx-row="'+id+'" class="'+(on?'cx-sel':'')+'">'
          +'<td class="cx-ck" data-gf-feature="time_windows"><input type="checkbox" class="cx-cb" data-cx-cb="'+id+'" aria-label="Seleziona '+cxEsc(x.nome)+'"'+(on?' checked':'')+'></td>'
          +'<td>'+cxNameCell(x)+'</td><td>'+cxAddressCell(x)+'</td>'
          +'<td data-gf-feature="time_windows">'+cxSlotMarkup(x)+'</td><td>'+customerStatusMarkup(x)+'</td><td>'+cxActions(x)+'</td></tr>';
      }).join('')+'</tbody></table></div>';
  }else{
    html='<div class="cx-grid" id="customerCards">'+visible.map(x=>{
      const id=Number(x.id),on=sel.has(id);
      return '<article class="cx-card'+(on?' cx-sel':'')+'" data-cx-row="'+id+'">'
        +'<input type="checkbox" class="cx-cb" data-gf-feature="time_windows" data-cx-cb="'+id+'" aria-label="Seleziona '+cxEsc(x.nome)+'"'+(on?' checked':'')+'>'
        +cxNameCell(x)+cxAddressCell(x)
        +'<div class="cx-meta"><span data-gf-feature="time_windows">'+cxSlotMarkup(x)+'</span>'+customerStatusMarkup(x)+'</div>'+cxActions(x)+'</article>';
    }).join('')+'</div>';
  }
  target.innerHTML=html;
  const pageCheck=cxEl('customerSelectPage');
  if(pageCheck)pageCheck.indeterminate=!pageCheck.checked&&visible.some(x=>sel.has(Number(x.id)));
  const count=cxEl('customerCount');
  if(count)count.textContent=rows.length?('Mostrati '+(from+1)+'–'+(from+visible.length)+' di '+rows.length+' clienti'):'0 clienti';
  const pager=cxEl('customerPagination');
  if(pager){
    if(pages<=1){pager.innerHTML='';}
    else{
      const numbers=[...new Set([1,state.page-1,state.page,state.page+1,pages])].filter(p=>p>=1&&p<=pages).sort((a,b)=>a-b);
      let p='<button type="button" data-cx-page="'+(state.page-1)+'"'+(state.page<=1?' disabled':'')+' aria-label="Pagina precedente">'+cxIcon('chevl')+'</button>';
      numbers.forEach((n,i)=>{
        if(i&&n>numbers[i-1]+1)p+='<span class="cx-gap" aria-hidden="true">…</span>';
        p+='<button type="button" data-cx-page="'+n+'"'+(n===state.page?' aria-current="page"':'')+'>'+n+'</button>';
      });
      p+='<button type="button" data-cx-page="'+(state.page+1)+'"'+(state.page>=pages?' disabled':'')+' aria-label="Pagina successiva">'+cxIcon('chevr')+'</button>';
      pager.innerHTML=p;
    }
  }
  const sort=cxEl('customerSort');if(sort)sort.value=state.sort;
  cxEl('customerListView')?.setAttribute('aria-pressed',String(state.view==='list'));
  cxEl('customerGridView')?.setAttribute('aria-pressed',String(state.view==='grid'));
  renderCustomerKpis();renderCustomerQuick();renderCustomerSelection();
}

/* ---------- Pannello laterale: dettagli, modifica, nuovo ---------- */
const customerDrawer = {current:null, mode:'view', saving:false};
function cxFindCustomer(id){return customerDirectory.all.find(x=>Number(x.id)===Number(id));}
function showCustomerDetails(id){ openCustomerDrawer(id,'view'); }
function openCustomerDrawer(id,mode,focusSlot){
  const drawer=cxEl('customerDrawer');if(!drawer)return;
  const existing=id!=null?cxFindCustomer(id):null;
  if(id!=null&&!existing)return;
  customerDrawer.mode=existing?(mode||'view'):'new';
  customerDrawer.current=existing||{id:null,nome:'',indirizzo:'',comune:'',provincia:'',codice_cliente:'',stato_geocodifica:'da_verificare',isNew:true};
  const c=customerDrawer.current, edit=customerDrawer.mode!=='view';
  const second=Boolean(c.scarico_pomeriggio_da||c.scarico_pomeriggio_a);
  const head='<div class="cx-dr-h">'+cxAvatar(c,true)+'<div><h2>'+(c.isNew?'Nuovo cliente':cxEsc(c.nome))+'</h2><small>'
    +cxEsc(c.isNew?'I dati potranno essere completati anche in seguito':(c.codice_cliente||'Senza codice'))+(c.isNew?'':' '+customerStatusMarkup(c))+'</small></div>'
    +'<button type="button" class="cx-ibtn" data-cx-close aria-label="Chiudi">'+cxIcon('close')+'</button></div>';
  let address;
  if(edit){
    address='<div class="cx-f"><label for="cxName">Nome cliente</label><input class="cx-in" id="cxName" value="'+cxEsc(c.nome)+'" autocomplete="off" maxlength="250"></div>'
      +'<div class="cx-f"><label for="cxAddress">Indirizzo</label><input class="cx-in" id="cxAddress" value="'+cxEsc(c.indirizzo)+'" placeholder="Via e numero civico" autocomplete="off"></div>'
      +'<div class="cx-row3"><div class="cx-f"><label for="cxCode">Codice</label><input class="cx-in" id="cxCode" value="'+cxEsc(c.codice_cliente)+'" autocomplete="off"></div>'
      +'<div class="cx-f"><label for="cxCity">Città</label><input class="cx-in" id="cxCity" value="'+cxEsc(c.comune)+'" autocomplete="off"></div>'
      +'<div class="cx-f"><label for="cxProv">Prov.</label><input class="cx-in" id="cxProv" value="'+cxEsc(c.provincia)+'" maxlength="2" style="text-transform:uppercase"></div></div>'
      +'<p class="cx-hint">'+(c.isNew?'Il nuovo indirizzo verrà verificato prima di essere usato nei giri.':'Se cambi l\'indirizzo, dovrà essere verificato di nuovo.')+'</p>'
      +'<p class="cx-err" id="cxAddressError" role="alert"></p>'
      +'<button type="button" class="cx-btn cx-ghost" data-cx-full>Tutti i campi: contatti, vincoli'+((typeof agentsFeatureEnabled==='function'&&agentsFeatureEnabled())?', agente':'')+'</button>';
  }else{
    address='<div class="cx-addr-v"><b>'+cxEsc(c.indirizzo||'—')+'</b><small>'+cxEsc(cxPlace(c)||'Comune non indicato')+'</small>'
      +(cxVerified(c)&&c.indirizzo_geocodificato?'<small class="cx-geo">'+cxIcon('pin')+'Verificato come: '+cxEsc(c.indirizzo_geocodificato)+'</small>':'')+'</div>'
      +(cxVerified(c)?'':'<button type="button" class="cx-btn cx-line cx-sm cx-verify" data-cx-verify>Verifica indirizzo</button>');
  }
  const pair=(prefix,label,from,to)=>'<div class="cx-row2"><div class="cx-f"><label for="'+prefix+'From">'+label+'dalle</label><input class="cx-in" type="time" id="'+prefix+'From" value="'+cxEsc(from||'')+'"></div>'
    +'<div class="cx-f"><label for="'+prefix+'To">'+label+'alle</label><input class="cx-in" type="time" id="'+prefix+'To" value="'+cxEsc(to||'')+'"></div></div>';
  const slot='<section id="cxSlotSection" data-gf-feature="time_windows"><h3>Fascia di scarico</h3>'
    +'<div class="cx-presets">'+CX_PRESETS.map((p,i)=>'<button type="button" data-cx-preset="'+i+'">'+p[0]+' <small>'+p[1]+'–'+p[2]+'</small></button>').join('')+'</div>'
    +pair('cxSlot1','',c.scarico_mattina_da,c.scarico_mattina_a).replace(/>dalle</,'>Dalle<').replace(/>alle</,'>Alle<')
    +'<div id="cxSecondSlot"'+(second?'':' hidden')+'>'+pair('cxSlot2','Seconda fascia ',c.scarico_pomeriggio_da,c.scarico_pomeriggio_a)+'</div>'
    +(second?'':'<button type="button" class="cx-btn cx-ghost" data-cx-second>'+cxIcon('plus')+'Aggiungi una seconda fascia</button>')
    +'<p class="cx-hint">Gli autisti possono consegnare solo in questa fascia. Lascia vuoto per nessun vincolo.</p><p class="cx-err" id="cxSlotError" role="alert"></p></section>';
  let extra='';
  if(!edit){
    const rows=[];
    if(c.referente)rows.push(['Referente',c.referente]);
    if(c.telefono)rows.push(['Telefono',c.telefono]);
    if(c.email)rows.push(['Email',c.email]);
    rows.push(['Tempo di scarico',(c.tempo_scarico_min??10)+' min']);
    if(typeof agentsFeatureEnabled==='function'&&agentsFeatureEnabled())rows.push(['Agente',c.agent_name||'Cliente interno']);
    const flags=[c.ztl?'<span class="cx-chip cx-amber" data-gf-feature="ztl">ZTL</span>':'',c.sponda?'<span class="cx-chip" data-gf-feature="tail_lift">Sponda</span>':'',c.transpallet?'<span class="cx-chip">Transpallet</span>':''].join('');
    extra='<section><h3>Contatti e vincoli</h3><dl class="cx-dl">'+rows.map(r=>'<div><dt>'+r[0]+'</dt><dd>'+cxEsc(r[1])+'</dd></div>').join('')+'</dl>'
      +(flags?'<div class="cx-meta">'+flags+'</div>':'')+(c.note?'<p class="cx-note">'+cxEsc(c.note)+'</p>':'')+'</section>';
  }
  const body='<div class="cx-dr-b"><section><h3>'+(edit?'Dati del cliente':'Indirizzo')+'</h3>'+address+'</section>'+slot+extra+'</div>';
  const foot='<div class="cx-dr-f">'+(customerDrawer.mode==='view'
      ?'<button type="button" class="cx-btn cx-line" data-cx-edit-current>'+cxIcon('edit')+'Modifica dati</button>'
      :'<button type="button" class="cx-btn cx-line" data-cx-cancel>Annulla</button>')
    +'<button type="button" class="cx-btn" data-cx-save>Salva</button></div>';
  drawer.innerHTML=head+body+foot;
  drawer.classList.add('cx-open');drawer.setAttribute('aria-hidden','false');
  cxEl('customerDrawerScrim')?.classList.add('cx-open');
  setTimeout(()=>{const t=focusSlot?cxEl('cxSlot1From'):(edit?cxEl('cxName'):drawer.querySelector('[data-cx-close]'));t?.focus();},280);
  if(focusSlot)setTimeout(()=>cxEl('cxSlotSection')?.scrollIntoView({block:'center',behavior:'smooth'}),120);
}
function closeCustomerDrawer(){
  cxEl('customerDrawer')?.classList.remove('cx-open');
  cxEl('customerDrawer')?.setAttribute('aria-hidden','true');
  cxEl('customerDrawerScrim')?.classList.remove('cx-open');
  customerDrawer.current=null;
}
function cxReadSlot(prefix,label,errors){
  const from=cxEl(prefix+'From')?.value||'', to=cxEl(prefix+'To')?.value||'';
  if((from&&!to)||(!from&&to))errors.push(label+': inserisci sia l\'orario di inizio sia quello di fine.');
  else if(from&&to&&from>=to)errors.push(label+': l\'orario di fine deve essere successivo a quello di inizio.');
  return [from||null,to||null];
}
async function saveCustomerDrawer(){
  if(customerDrawer.saving)return;
  const c=customerDrawer.current;if(!c)return;
  const timeWindows=document.documentElement?.dataset?.gfTimeWindows!=='off';
  const errors=[];
  const slot1=timeWindows?cxReadSlot('cxSlot1','Fascia di scarico',errors):[c.scarico_mattina_da||null,c.scarico_mattina_a||null];
  const slot2=timeWindows&&!cxEl('cxSecondSlot')?.hidden?cxReadSlot('cxSlot2','Seconda fascia',errors):(timeWindows?[null,null]:[c.scarico_pomeriggio_da||null,c.scarico_pomeriggio_a||null]);
  if(!errors.length&&slot1[0]&&slot2[0]&&slot2[0]<slot1[1])errors.push('La seconda fascia deve iniziare dopo la fine della prima.');
  const slotError=cxEl('cxSlotError');if(slotError)slotError.textContent=errors.join(' ');
  if(errors.length)return;
  const payload=Object.fromEntries(CX_FIELDS.map(k=>[k,c[k]??null]));
  if(payload.tempo_scarico_min==null)payload.tempo_scarico_min=10;
  ['ztl','sponda','transpallet'].forEach(k=>payload[k]=Boolean(payload[k]));
  if(customerDrawer.mode!=='view'){
    const value=id=>(cxEl(id)?.value||'').trim();
    const required=['cxName','cxAddress','cxCity'];
    let bad=false;
    required.forEach(id=>{const el=cxEl(id);const empty=!value(id);el?.classList.toggle('cx-bad',empty);if(empty)bad=true;});
    const addressError=cxEl('cxAddressError');
    if(addressError)addressError.textContent=bad?'Compila nome, indirizzo e città.':'';
    if(bad)return;
    payload.nome=value('cxName');payload.indirizzo=value('cxAddress');payload.codice_cliente=value('cxCode')||null;
    payload.comune=value('cxCity');payload.provincia=value('cxProv').toUpperCase()||null;
    const key=x=>[x.indirizzo,x.comune,x.provincia].map(v=>String(v||'').trim().toLowerCase()).join('|');
    if(c.isNew||key(payload)!==key(c))CX_GEO_FIELDS.forEach(k=>payload[k]=null);
  }
  [payload.scarico_mattina_da,payload.scarico_mattina_a]=slot1;
  [payload.scarico_pomeriggio_da,payload.scarico_pomeriggio_a]=slot2;
  const save=cxEl('customerDrawer')?.querySelector('[data-cx-save]');
  customerDrawer.saving=true;if(save){save.disabled=true;save.textContent='Salvataggio…';}
  try{
    const saved=await api(c.isNew?'/api/customers':'/api/customers/'+Number(c.id),{method:c.isNew?'POST':'PUT',body:JSON.stringify(payload)});
    const unverified=saved&&saved.stato_geocodifica!=='verificato'&&customerDrawer.mode!=='view';
    closeCustomerDrawer();
    await refreshCustomerDirectory();
    if(typeof loadCustomerPicker==='function')await loadCustomerPicker();
    if(typeof toast==='function')toast(c.isNew?'Cliente aggiunto: indirizzo da verificare':(unverified?'Cliente salvato: indirizzo da verificare':'Cliente aggiornato'));
  }catch(error){
    const target=cxEl(customerDrawer.mode==='view'?'cxSlotError':'cxAddressError')||cxEl('cxSlotError');
    if(target)target.textContent=error?.message||'Salvataggio non riuscito.';
  }finally{
    customerDrawer.saving=false;if(save){save.disabled=false;save.textContent='Salva';}
  }
}

/* ---------- Selezione multipla e fascia per più clienti ---------- */
let customerBulkMenu=null;
function renderCustomerSelection(){
  const bar=cxEl('customerBulkBar');if(!bar)return;
  const n=customerDirectory.selected.size;
  bar.classList.toggle('cx-show',n>0);
  const msg=cxEl('customerSelectedCount');if(msg)msg.textContent=n+(n===1?' cliente selezionato':' clienti selezionati');
  if(!n)closeCustomerBulkMenu();
}
function clearCustomerSelection(){ customerDirectory.selected.clear(); closeCustomerBulkMenu(); renderCustomerDirectory(); }
function closeCustomerBulkMenu(){ if(customerBulkMenu){customerBulkMenu.remove();customerBulkMenu=null;} }
function toggleCustomerBulkMenu(event){
  event?.stopPropagation?.();
  if(customerBulkMenu){closeCustomerBulkMenu();return;}
  const button=cxEl('customerBulkButton');if(!button)return;
  const menu=document.createElement('div');menu.className='cx-menu';menu.setAttribute('role','menu');
  menu.innerHTML='<div class="cx-mh">Imposta per i clienti selezionati</div>'
    +CX_PRESETS.map((p,i)=>'<button type="button" role="menuitem" data-cx-bulk="'+i+'">'+p[0]+'<small>'+p[1]+' – '+p[2]+'</small></button>').join('')
    +'<button type="button" role="menuitem" data-cx-bulk="clear">Rimuovi la fascia</button>';
  document.body.appendChild(menu);
  const r=button.getBoundingClientRect(),w=menu.offsetWidth,h=menu.offsetHeight;
  menu.style.left=Math.max(8,Math.min(window.innerWidth-w-8,r.left))+'px';
  menu.style.top=Math.max(8,r.top-h-8)+'px';
  customerBulkMenu=menu;
}
async function applyCustomerBulkSlot(choice){
  if(customerDirectory.busy)return;
  // Mattina e giornata usano la prima fascia, pomeriggio la seconda; "Rimuovi" le azzera entrambe.
  const spec={0:{scarico_mattina_da:'06:00',scarico_mattina_a:'12:00'},1:{scarico_pomeriggio_da:'14:00',scarico_pomeriggio_a:'18:00'},2:{scarico_mattina_da:'06:00',scarico_mattina_a:'18:00'},clear:{}}[choice];
  if(!spec)return;
  const selected=customerDirectory.all.filter(x=>customerDirectory.selected.has(Number(x.id)));
  if(!selected.length)return;
  closeCustomerBulkMenu();
  customerDirectory.busy=true;
  let done=0,error=null;
  try{
    for(const x of selected){
      const payload=Object.fromEntries(CX_FIELDS.map(k=>[k,x[k]??null]));
      if(payload.tempo_scarico_min==null)payload.tempo_scarico_min=10;
      ['ztl','sponda','transpallet'].forEach(k=>payload[k]=Boolean(payload[k]));
      ['scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a'].forEach(k=>payload[k]=spec[k]||null);
      try{
        await api('/api/customers/'+Number(x.id),{method:'PUT',body:JSON.stringify(payload)});
        customerDirectory.selected.delete(Number(x.id));done++;
      }catch(e){error=e;break;}
    }
    await refreshCustomerDirectory();
    if(done&&typeof loadCustomerPicker==='function')await loadCustomerPicker();
    if(typeof toast==='function'){
      const label=choice==='clear'?'Fascia rimossa':'Fascia '+CX_PRESETS[choice][1]+' – '+CX_PRESETS[choice][2]+' impostata';
      toast(error?'Aggiornati '+done+' clienti. Errore: '+(error.message||'salvataggio non riuscito')+'. Gli altri restano selezionati.'
        :label+' per '+done+(done===1?' cliente':' clienti'));
    }
  }finally{customerDirectory.busy=false;}
}
function openCustomerBulkSlotDialog(){ toggleCustomerBulkMenu(); }

/* ---------- Eventi ---------- */
if(typeof document!=='undefined'&&document.addEventListener){
  document.addEventListener('click',event=>{
    const t=event.target;
    if(!t||!t.closest)return;
    if(customerBulkMenu&&!t.closest('.cx-menu')&&!t.closest('#customerBulkButton'))closeCustomerBulkMenu();
    const bulk=t.closest('.cx-menu [data-cx-bulk]');
    if(bulk){applyCustomerBulkSlot(bulk.dataset.cxBulk==='clear'?'clear':Number(bulk.dataset.cxBulk));return;}
    const drawer=t.closest('#customerDrawer');
    if(drawer){
      if(t.closest('[data-cx-close],[data-cx-cancel]')){
        if(t.closest('[data-cx-cancel]')&&customerDrawer.current&&!customerDrawer.current.isNew){openCustomerDrawer(customerDrawer.current.id,'view');return;}
        closeCustomerDrawer();return;
      }
      if(t.closest('[data-cx-edit-current]')){openCustomerDrawer(customerDrawer.current.id,'edit');return;}
      if(t.closest('[data-cx-save]')){saveCustomerDrawer();return;}
      if(t.closest('[data-cx-full]')){const id=customerDrawer.current?.id;closeCustomerDrawer();if(typeof openCustomerModal==='function')openCustomerModal(id||null);return;}
      if(t.closest('[data-cx-verify]')){const id=customerDrawer.current?.id;closeCustomerDrawer();if(id&&typeof verifyCustomerAddress==='function')verifyCustomerAddress(id);return;}
      if(t.closest('[data-cx-second]')){const box=cxEl('cxSecondSlot');if(box)box.hidden=false;t.closest('[data-cx-second]').remove();cxEl('cxSlot2From')?.focus();return;}
      const preset=t.closest('[data-cx-preset]');
      if(preset){
        const p=CX_PRESETS[Number(preset.dataset.cxPreset)];
        const from=cxEl('cxSlot1From'),to=cxEl('cxSlot1To');if(from)from.value=p[1];if(to)to.value=p[2];
        const err=cxEl('cxSlotError');if(err)err.textContent='';
      }
      return;
    }
    if(!t.closest('#tab-clienti'))return;
    const quick=t.closest('[data-cx-quick]');
    if(quick){
      customerDirectory.quick=quick.dataset.cxQuick;
      if(quick.closest('#customerKpis')){const s=cxEl('customerListSearch');if(s)s.value='';}
      filterCustomerList();
      if(quick.closest('#customerKpis'))cxEl('customerListPanel')?.scrollIntoView({behavior:'smooth',block:'start'});
      return;
    }
    const page=t.closest('[data-cx-page]');if(page&&!page.disabled){customerGoPage(Number(page.dataset.cxPage));return;}
    const sort=t.closest('[data-cx-sort]');if(sort){toggleCustomerSort(sort.dataset.cxSort);return;}
    const slot=t.closest('[data-cx-slot]');if(slot){openCustomerDrawer(Number(slot.dataset.cxSlot),'view',true);return;}
    const edit=t.closest('[data-cx-edit]');if(edit){openCustomerDrawer(Number(edit.dataset.cxEdit),'edit');return;}
    const open=t.closest('[data-cx-open]');if(open){openCustomerDrawer(Number(open.dataset.cxOpen),'view');return;}
    if(t.closest('.cx-cb'))return;
    const row=t.closest('[data-cx-row]');
    if(row&&!t.closest('button,a,input,select,label'))openCustomerDrawer(Number(row.dataset.cxRow),'view');
  });
  document.addEventListener('change',event=>{
    const t=event.target;if(!t||!t.closest||!t.closest('#tab-clienti'))return;
    if(t.id==='customerSelectPage'){
      const from=(customerDirectory.page-1)*customerDirectory.size;
      customerDirectory.rows.slice(from,from+customerDirectory.size).forEach(x=>{
        if(t.checked)customerDirectory.selected.add(Number(x.id));else customerDirectory.selected.delete(Number(x.id));
      });
      renderCustomerDirectory();return;
    }
    if(t.dataset&&t.dataset.cxCb){
      const id=Number(t.dataset.cxCb);
      if(t.checked)customerDirectory.selected.add(id);else customerDirectory.selected.delete(id);
      renderCustomerDirectory();
    }
  });
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape')return;
    if(customerBulkMenu){closeCustomerBulkMenu();return;}
    if(customerDrawer.current)closeCustomerDrawer();
  });
  document.addEventListener('DOMContentLoaded',()=>{
    if(typeof window!=='undefined'&&window.innerWidth<760)customerDirectory.view='grid';
    if(cxEl('customerResults'))renderCustomerDirectory();
  },{once:true});
}
