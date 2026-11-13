/* GiroFacile · pagina Clienti.
   Disposizione del riferimento del 14 ottobre 2026 sui componenti del sistema, con i dati reali e le API
   esistenti: striscia indicatori, elenco/schede, filtri, pannello laterale per
   dettagli, modifica e nuovo cliente, selezione multipla con fascia di scarico. */

const customerDirectory = {all:[], rows:[], visible:[], page:1, size:cxSavedPageSize(), sort:'nome', direction:'asc', view:'list', request:0, quick:'all', selected:new Set(), busy:false};

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
const CX_FIELDS = ['agent_id','codice_cliente','nome','indirizzo','cap','comune','provincia','telefono','email',
  'scarico_mattina_da','scarico_mattina_a','scarico_pomeriggio_da','scarico_pomeriggio_a','tempo_scarico_min',
  'ztl','sponda','transpallet','note','lat','lon','indirizzo_geocodificato','stato_geocodifica',
  'affidabilita_geocodifica','fonte_geocodifica','google_place_id'];
const CX_GEO_FIELDS = ['lat','lon','indirizzo_geocodificato','stato_geocodifica','affidabilita_geocodifica','fonte_geocodifica','google_place_id'];

// «Via Roma 10» → ['Via Roma','10']: il civico è l'ultimo numero (anche 12/B, 7A).
function cxStreetParts(line){
  const text=String(line||'').trim();
  const match=text.match(/^(.*?\D)[\s,]+(\d+\s*[a-zA-Z]?(?:\s*\/\s*\w+)?)$/);
  return match?[match[1].replace(/[\s,]+$/,''),match[2]]:[text,''];
}
// Sotto i campi: l'indirizzo esatto che arriverà a Google.
function cxSyncExact(root){
  const hint=root?.querySelector?.('[data-cx-exact]');if(!hint)return;
  const v=id=>(root.querySelector('#'+id)?.value||'').trim();
  const line=[[v('cxStreet'),v('cxNumber')].filter(Boolean).join(' '),[v('cxCap'),v('cxCity'),v('cxProv').toUpperCase()].filter(Boolean).join(' ')].filter(Boolean).join(', ');
  hint.innerHTML=line?'Verifichiamo esattamente: <strong>'+cxEsc(line)+'</strong>':'Indica via, civico, CAP e comune: li verifichiamo così come li scrivi.';
}
function cxIcon(name){return '<svg class="gf-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="'+CX_ICONS[name]+'"/></svg>';}
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
// Clienti per pagina: 25 o 50, ricordati nel browser.
function cxSavedPageSize(){
  try{ return Number(localStorage.getItem('gf_customers_page_size'))===50?50:25; }catch(e){ return 25; }
}
function setCustomerPageSize(value){
  customerDirectory.size=Number(value)===50?50:25;
  try{ localStorage.setItem('gf_customers_page_size',String(customerDirectory.size)); }catch(e){}
  filterCustomerList();
}
// «Seleziona tutti»: i clienti della pagina (casella nell'intestazione) o tutti quelli del filtro (barra in basso).
function toggleVisibleCustomers(on){
  for(const x of customerDirectory.visible){const id=Number(x.id);if(on)customerDirectory.selected.add(id);else customerDirectory.selected.delete(id);}
  renderCustomerDirectory();
}
function selectAllFilteredCustomers(){
  for(const x of customerDirectory.rows)customerDirectory.selected.add(Number(x.id));
  renderCustomerDirectory();
}
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
    ? '<span class="gf-badge" data-status="success">'+cxIcon('check')+'Verificato</span>'
    : x.stato_geocodifica==='non_trovato'
      ? '<span class="gf-badge" data-status="danger">Non trovato</span>'
      : '<span class="gf-badge" data-status="warning">Da verificare</span>';
}
function cxSlotMarkup(x){
  const slots=cxSlots(x);
  return slots.length
    ? '<span class="gf-badge" data-status="info">'+cxIcon('clock')+cxEsc(slots.join(' / '))+'</span>'
    : '<button type="button" class="gf-button" data-variant="link" data-size="sm" data-cx-slot="'+Number(x.id)+'" title="Imposta la fascia di scarico">Non impostata</button>';
}
function cxActions(x){
  const id=Number(x.id);
  return '<div class="gf-cluster"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-cx-open="'+id+'" aria-label="Apri la scheda di '+cxEsc(x.nome)+'">'+cxIcon('eye')+'Dettagli</button></div>';
}
// Ogni cliente ha sempre lo stesso colore: deriva dal nome (6 toni di gf-avatar).
function cxAvatarTone(name){
  // FNV-1a con mescolamento finale: nomi simili ("Hotel …") finiscono comunque su colori diversi.
  let hash=2166136261;
  for(const ch of String(name||'').trim().toLocaleLowerCase('it')){hash^=ch.codePointAt(0);hash=Math.imul(hash,16777619)>>>0;}
  hash=(hash^(hash>>>16))>>>0;
  hash=Math.imul(hash,2246822507)>>>0;
  hash=(hash^(hash>>>13))>>>0;
  return hash%6+1;
}
function cxAvatar(x){
  const tone=x.nome?' data-tone="'+cxAvatarTone(x.nome)+'"':'';
  return '<span class="gf-avatar"'+tone+' aria-hidden="true">'+cxEsc(x.nome?cxInitials(x.nome):'+')+'</span>';
}
function cxNameCell(x){
  return '<div class="gf-cluster">'+cxAvatar(x)+'<div><b>'+cxEsc(x.nome)+'</b><br><small class="gf-muted">'+cxEsc(x.codice_cliente||'Senza codice')+'</small></div></div>';
}
function cxAccessBadges(x){
  const marks=[];
  if(x.ztl)marks.push('<span class="gf-badge" data-kind="ztl" title="Attenzione: cliente in zona ZTL. Verifica le condizioni di accesso.">ZTL</span>');
  if(x.pedestrian_area)marks.push('<span class="gf-badge" data-status="warning" title="Attenzione: cliente in area pedonale. Verifica le modalità di consegna.">Area pedonale</span>');
  return marks.length?'<div class="gf-cluster" data-gap="xs" aria-label="Avvisi geografici">'+marks.join(' ')+'</div>':'';
}
function cxAddressCell(x){
  return '<div><b>'+cxEsc(x.indirizzo||'—')+'</b><br><small class="gf-muted">'+cxEsc(cxPlace(x)||'Comune non indicato')+'</small>'+cxAccessBadges(x)+'</div>';
}
function renderCustomerKpis(){
  const root=cxEl('customerKpis');if(!root)return;
  const all=customerDirectory.all,t=all.length,ver=all.filter(cxVerified).length,un=t-ver,wf=all.filter(cxHasSlot).length;
  // Icone e colori condivisi con le altre barre dei numeri.
  const icons={customers:['1','M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1 M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M21 20v-1a4 4 0 0 0-3-3.9 M16 4.1a3.5 3.5 0 0 1 0 6.8'],pin:['2','M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z M12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z'],alert:['5','M12 3 2 20h20L12 3z M12 10v4 M12 17h.01'],clock:['3','M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2']};
  const cell=(icon,quick,label,value,note,warn,bar,feature,id)=>'<button type="button" class="gf-stat-strip__cell" data-cx-quick="'+quick+'"'+(feature?' data-gf-feature="'+feature+'"':'')+'>'
    +'<span class="gf-stat-strip__icon" data-tone="'+icons[icon][0]+'" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="'+icons[icon][1]+'"/></svg></span>'
    +'<span class="gf-stat-strip__label">'+label+'</span><strong class="gf-stat-strip__value" id="'+id+'">'+value+'</strong><small class="gf-stat-strip__unit">'+(warn?'<span class="gf-badge" data-status="warning">'+note+'</span>':note)+'</small>'
    +(bar!=null?'<span class="gf-progress__track"><span class="gf-progress__done" data-gf-width="'+Math.round(bar/5)*5+'"></span></span>':'')+'</button>';
  root.innerHTML=
    cell('customers','all','Totale clienti',t,'Tutti i clienti registrati',false,null,'','customerMetricTotal')+
    cell('pin','all','Indirizzi verificati',ver,'Indirizzi con verifica completata',false,null,'','customerMetricVerified')+
    cell('alert','unverified','Da verificare',un,'Indirizzi ancora da verificare',un>0,null,'','customerMetricPending')+
    cell('clock','noSlot','Con fascia di scarico',wf,wf<t?(t-wf)+' da impostare':'Tutte impostate',wf<t,t?Math.round(wf/t*100):0,'time_windows','customerMetricWithSlot');
}
function renderCustomerQuick(){
  const root=cxEl('customerQuickFilters');
  const all=customerDirectory.all,un=all.filter(x=>!cxVerified(x)).length,nf=all.filter(x=>!cxHasSlot(x)).length;
  const chips=[['all','Tutti',all.length,''],['unverified','Da verificare',un,''],['noSlot','Senza fascia di scarico',nf,'time_windows']];
  if(root)root.innerHTML=chips.map(([key,label,n,feature])=>'<button type="button" class="gf-chip" data-cx-quick="'+key+'"'+(feature?' data-gf-feature="'+feature+'"':'')+' aria-pressed="'+(customerDirectory.quick===key)+'">'+label+' <span class="gf-badge" data-status="neutral">'+n+'</span></button>').join('');
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
  state.visible=visible;
  const sel=state.selected;
  const pageSelected=visible.filter(x=>sel.has(Number(x.id))).length;
  const allBox='<input type="checkbox" data-cx-cb-all aria-label="Seleziona tutti i clienti della pagina"'+(visible.length&&pageSelected===visible.length?' checked':'')+'>';
  let html='';
  if(!rows.length){
    const none=!state.all.length;
    html='<div class="gf-empty"><p><strong>'+(none?'Nessun cliente registrato':'Nessun cliente trovato')+'</strong></p><p>'
      +(none?'Aggiungi il primo cliente oppure importa un file CSV/Excel.':'Prova a cambiare la ricerca o i filtri.')+'</p>'
      +(none?'<button type="button" class="gf-button" data-variant="primary" data-size="sm" onclick="openCustomerModal()">'+cxIcon('plus')+'Nuovo cliente</button>'
            :'<button type="button" class="gf-button" data-variant="secondary" data-size="sm" onclick="clearCustomerListAllFilters()">Azzera ricerca e filtri</button>')+'</div>';
  }else if(state.view==='list'){
    // Nell'intestazione la casella «seleziona tutti» i clienti della pagina; l'ordinamento sta nella casella Filtri.
    html='<div class="gf-table-wrap" id="customerTableWrap"><table class="gf-table" data-gf-responsive="cards" aria-label="Elenco clienti"><thead><tr>'
      +'<th scope="col">'+allBox+'</th><th scope="col">Cliente</th><th scope="col">Indirizzo</th>'
      +'<th scope="col" data-gf-feature="time_windows">Fascia di scarico</th><th scope="col">Stato indirizzo</th><th scope="col">Azioni</th>'
      +'</tr></thead><tbody id="customersBody">'
      +visible.map(x=>{
        const id=Number(x.id),on=sel.has(id);
        return '<tr data-cx-row="'+id+'" aria-selected="'+on+'">'
          +'<td data-label="Seleziona"><input type="checkbox" class="cx-cb" data-cx-cb="'+id+'" aria-label="Seleziona '+cxEsc(x.nome)+'"'+(on?' checked':'')+'></td>'
          +'<td data-label="Cliente">'+cxNameCell(x)+'</td><td data-label="Indirizzo">'+cxAddressCell(x)+'</td>'
          +'<td data-label="Fascia di scarico" data-gf-feature="time_windows">'+cxSlotMarkup(x)+'</td><td data-label="Stato indirizzo">'+customerStatusMarkup(x)+'</td><td data-label="Azioni">'+cxActions(x)+'</td></tr>';
      }).join('')+'</tbody></table></div>';
  }else{
    html='<div class="gf-panel__body"><label class="gf-check">'+allBox+'<span>Seleziona tutti quelli della pagina</span></label></div>'
      +'<div class="gf-panel__body gf-grid" data-cols="3" id="customerCards">'+visible.map(x=>{
      const id=Number(x.id),on=sel.has(id);
      return '<article class="gf-card gf-stack" data-cx-row="'+id+'" aria-selected="'+on+'">'
        +'<label class="gf-check"><input type="checkbox" class="cx-cb" data-cx-cb="'+id+'" aria-label="Seleziona '+cxEsc(x.nome)+'"'+(on?' checked':'')+'><span>Seleziona</span></label>'
        +cxNameCell(x)+cxAddressCell(x)
        +'<div class="gf-cluster"><span data-gf-feature="time_windows">'+cxSlotMarkup(x)+'</span>'+customerStatusMarkup(x)+'</div>'+cxActions(x)+'</article>';
    }).join('')+'</div>';
  }
  target.innerHTML=html;
  // Pagina selezionata solo in parte: la casella dell'intestazione mostra il trattino.
  target.querySelectorAll('[data-cx-cb-all]').forEach(box=>{box.indeterminate=pageSelected>0&&pageSelected<visible.length;});
  const size=cxEl('customerPageSize');if(size)size.value=String(state.size);
  const count=cxEl('customerCount');
  if(count)count.textContent=rows.length?('Mostrati '+(from+1)+'–'+(from+visible.length)+' di '+rows.length+' clienti'):'0 clienti';
  const pager=cxEl('customerPagination');
  if(pager){
    if(pages<=1){pager.innerHTML='';}
    else{
      const numbers=[...new Set([1,state.page-1,state.page,state.page+1,pages])].filter(p=>p>=1&&p<=pages).sort((a,b)=>a-b);
      const pageButton=(n,text,extra)=>'<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-cx-page="'+n+'"'+extra+'>'+text+'</button>';
      let p=pageButton(state.page-1,cxIcon('chevl'),(state.page<=1?' disabled':'')+' aria-label="Pagina precedente"');
      numbers.forEach((n,i)=>{
        if(i&&n>numbers[i-1]+1)p+='<span aria-hidden="true">…</span>';
        p+=pageButton(n,n,n===state.page?' aria-current="page"':'');
      });
      p+=pageButton(state.page+1,cxIcon('chevr'),(state.page>=pages?' disabled':'')+' aria-label="Pagina successiva"');
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
// Riquadro con titolo e righe etichetta → valore della scheda cliente (i valori arrivano già sicuri).
function cxCard(title,inner){return '<section class="gf-card gf-stack" data-gap="sm"><h3 class="gf-subtitle">'+title+'</h3>'+inner+'</section>';}
function cxRows(rows){return '<dl class="gf-details" data-layout="rows">'+rows.map(r=>'<div class="gf-details__item"'+(r[2]?' '+r[2]:'')+'><dt>'+r[0]+'</dt><dd>'+r[1]+'</dd></div>').join('')+'</dl>';}
function openCustomerDrawer(id,mode,focusSlot){
  const drawer=cxEl('customerDrawer');if(!drawer)return;
  const existing=id!=null?cxFindCustomer(id):null;
  if(id!=null&&!existing)return;
  // I dettagli sono solo da leggere: modificare o creare un cliente apre sempre la finestra completa
  // (openCustomerModal), con tutti i campi in un unico posto.
  // Scheda unica (13/11/2026): vedere, modificare e creare passano tutti dalla stessa finestra completa.
  closeCustomerDrawer();
  if(typeof openCustomerModal==='function'){
    openCustomerModal(existing?existing.id:null);
    if(focusSlot)setTimeout(()=>document.getElementById('cMattinaDa')?.focus(),50);
  }
  return;
  customerDrawer.mode=existing?(mode||'view'):'new';
  customerDrawer.current=existing||{id:null,nome:'',indirizzo:'',comune:'',provincia:'',codice_cliente:'',stato_geocodifica:'da_verificare',isNew:true};
  const c=customerDrawer.current, edit=customerDrawer.mode!=='view';
  const second=Boolean(c.scarico_pomeriggio_da||c.scarico_pomeriggio_a);
  const head='<header class="gf-modal__header">'+cxAvatar(c)+'<div><p class="gf-kicker">Anagrafica cliente</p><h2 class="gf-modal__title">'+(c.isNew?'Nuovo cliente':cxEsc(c.nome))+'</h2><p class="gf-muted">'
    +cxEsc(c.isNew?'I dati potranno essere completati anche in seguito':(c.codice_cliente||'Senza codice'))+(c.isNew?'':' '+customerStatusMarkup(c))+'</p></div>'
    +'<button type="button" class="gf-icon-button" data-cx-close aria-label="Chiudi">'+cxIcon('close')+'</button></header>';
  const field=(id,label,value,attrs)=>'<label class="gf-field" for="'+id+'"><span class="gf-field__label">'+label+'</span><input class="gf-input" id="'+id+'" value="'+cxEsc(value)+'" '+(attrs||'')+'></label>';
  let address;
  if(edit){
    address=field('cxName','Nome cliente',c.nome,'autocomplete="off" maxlength="250"')
      // Indirizzo a campi separati: via e civico, poi CAP e comune (due per riga nella colonna della finestra).
      +'<fieldset class="gf-fieldset gf-stack" data-gap="sm" data-cx-address><legend class="gf-field__label">Indirizzo di consegna</legend><div class="gf-grid" data-cols="2">'
      +field('cxStreet','Via',cxStreetParts(c.indirizzo)[0],'placeholder="Via Roma" autocomplete="off"')
      +field('cxNumber','Civico',cxStreetParts(c.indirizzo)[1],'placeholder="10" maxlength="20" autocomplete="off"')
      +field('cxCap','CAP',c.cap,'placeholder="80026" maxlength="5" inputmode="numeric" autocomplete="off"')
      +field('cxCity','Comune',c.comune,'placeholder="Casoria" autocomplete="off"')+'</div>'
      +'<p class="gf-field__hint" data-cx-exact></p></fieldset>'
      +'<div class="gf-grid" data-cols="2">'+field('cxCode','Codice',c.codice_cliente,'autocomplete="off"')
      +field('cxProv','Prov.',c.provincia,'maxlength="2" autocapitalize="characters"')+'</div>'
      +'<p class="gf-field__hint">'+(c.isNew?'Il nuovo indirizzo verrà verificato prima di essere usato nei giri.':'Se cambi l\'indirizzo, dovrà essere verificato di nuovo.')+'</p>'
      +'<div class="gf-field" data-invalid><p class="gf-field__error" id="cxAddressError" role="alert"></p></div>'
      +'<div><button type="button" class="gf-button" data-variant="ghost" data-cx-full>Tutti i campi: contatti, vincoli'+((typeof agentsFeatureEnabled==='function'&&agentsFeatureEnabled())?', agente':'')+'</button></div>';
  }else{
    address=cxRows([['Via',cxEsc(c.indirizzo||'—')],['Comune',cxEsc(cxPlace(c)||'Non indicato')],
        ['Posizione',cxVerified(c)?'<span class="gf-badge" data-status="success">Verificata</span> '+cxEsc(c.indirizzo_geocodificato||''):customerStatusMarkup(c)]])
      +(cxVerified(c)?'':'<div><button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-cx-verify>Verifica indirizzo</button></div>');
  }
  const pair=(prefix,label,from,to)=>'<div class="gf-grid" data-cols="2"><label class="gf-field" for="'+prefix+'From"><span class="gf-field__label">'+label+'dalle</span><input class="gf-input" type="time" id="'+prefix+'From" value="'+cxEsc(from||'')+'"></label>'
    +'<label class="gf-field" for="'+prefix+'To"><span class="gf-field__label">'+label+'alle</span><input class="gf-input" type="time" id="'+prefix+'To" value="'+cxEsc(to||'')+'"></label></div>';
  const saved=[[c.scarico_mattina_da,c.scarico_mattina_a],[c.scarico_pomeriggio_da,c.scarico_pomeriggio_a]].filter(w=>w[0]&&w[1]).map(w=>w[0]+'–'+w[1]);
  const slot='<section class="gf-card gf-stack" data-gap="sm" id="cxSlotSection" data-gf-feature="time_windows"><h3 class="gf-subtitle">Fascia di scarico</h3>'
    +'<p>'+(saved.length?'<strong>Fascia attuale</strong>: '+saved.join(' e ')+'.':'<strong>Nessuna fascia impostata</strong>: si può consegnare a qualsiasi ora.')+'</p>'
    +'<p class="gf-field__label">Scegli una fascia pronta</p>'
    +'<div class="gf-cluster">'+CX_PRESETS.map((p,i)=>'<button type="button" class="gf-chip" data-cx-preset="'+i+'">'+p[0]+' <small>'+p[1]+'–'+p[2]+'</small></button>').join('')+'</div>'
    +'<p class="gf-field__label">oppure indica gli orari</p>'
    +pair('cxSlot1','',c.scarico_mattina_da,c.scarico_mattina_a).replace(/>dalle</,'>Dalle<').replace(/>alle</,'>Alle<')
    +'<div id="cxSecondSlot"'+(second?'':' hidden')+'>'+pair('cxSlot2','Seconda fascia ',c.scarico_pomeriggio_da,c.scarico_pomeriggio_a)+'</div>'
    +(second?'':'<div><button type="button" class="gf-button" data-variant="ghost" data-cx-second>'+cxIcon('plus')+'Aggiungi una seconda fascia</button></div>')
    +'<p class="gf-field__hint">Gli autisti consegnano solo in questa fascia. Lascia vuoto per nessun vincolo.</p><div class="gf-field" data-invalid><p class="gf-field__error" id="cxSlotError" role="alert"></p></div></section>';
  let extra='';
  if(!edit){
    const contacts=[['Telefono',c.telefono],['Email',c.email]].filter(r=>r[1]).map(r=>[r[0],cxEsc(r[1])]);
    const flags=[cxAccessBadges(c),c.sponda?'<span class="gf-badge" data-kind="tail-lift" data-gf-feature="tail_lift">Sponda</span>':'',c.transpallet?'<span class="gf-badge" data-status="neutral">Transpallet</span>':''].join('');
    const delivery=[['Tempo di scarico',cxEsc((c.tempo_scarico_min??10)+' min')],
      ['Fascia oraria',saved.length?cxEsc(saved.join(' e ')):'Fascia oraria non presente','data-gf-feature="time_windows"']];
    if(flags)delivery.push(['Accesso','<span class="gf-cluster">'+flags+'</span>']);
    if(typeof agentsFeatureEnabled==='function'&&agentsFeatureEnabled())delivery.push(['Agente',cxEsc(c.agent_name||'Cliente interno')]);
    if(c.note)delivery.push(['Note',cxEsc(c.note)]);
    extra=cxCard('Contatti',contacts.length?cxRows(contacts):'<p class="gf-muted">Nessun contatto indicato.</p>')+cxCard('Consegna',cxRows(delivery));
  }
  // Dettagli (13/11/2026): finestra al centro, solo lettura. A sinistra indirizzo e contatti, a destra la consegna.
  const body=edit
    ?'<div class="gf-modal__body"><div class="gf-grid" data-cols="2"><div class="gf-stack">'+cxCard('Dati del cliente',address)+'</div><div class="gf-stack">'+slot+'</div></div></div>'
    :'<div class="gf-modal__body"><div class="gf-grid" data-cols="2"><div class="gf-stack">'+cxCard('Indirizzo di consegna',address)
      +extra.slice(0,extra.indexOf('<section',1))+'</div><div class="gf-stack">'+extra.slice(extra.indexOf('<section',1))+'</div></div></div>';
  const foot='<footer class="gf-modal__footer">'+(customerDrawer.mode==='view'
      ?'<button type="button" class="gf-button" data-variant="secondary" data-cx-close>Chiudi</button>'
        +'<button type="button" class="gf-button" data-variant="primary" data-cx-edit-current>'+cxIcon('edit')+'Modifica</button></footer>'
      :'<button type="button" class="gf-button" data-variant="secondary" data-cx-cancel>Annulla</button><button type="button" class="gf-button" data-variant="primary" data-cx-save>Salva</button></footer>');
  drawer.innerHTML=head+body+foot;
  // Riga «Verifichiamo esattamente» aggiornata mentre si scrive.
  cxSyncExact(drawer);
  drawer.querySelector?.('[data-cx-address]')?.addEventListener('input',()=>cxSyncExact(drawer));
  drawer.querySelector?.('#cxProv')?.addEventListener('input',()=>cxSyncExact(drawer));
  drawer.setAttribute('aria-hidden','false');
  cxEl('customerDrawerScrim')?.classList.remove('hidden');
  setTimeout(()=>{const t=focusSlot?cxEl('cxSlot1From'):(edit?cxEl('cxName'):drawer.querySelector('[data-cx-close]'));t?.focus();},280);
  if(focusSlot)setTimeout(()=>cxEl('cxSlotSection')?.scrollIntoView({block:'center',behavior:'smooth'}),120);
}
function closeCustomerDrawer(){
  cxEl('customerDrawer')?.setAttribute('aria-hidden','true');
  cxEl('customerDrawerScrim')?.classList.add('hidden');
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
  // Non trasformare un rilevamento OSM in un flag manuale permanente.
  payload.ztl=Boolean(c.ztl_manual ?? c.ztl);
  if(customerDrawer.mode!=='view'){
    const value=id=>(cxEl(id)?.value||'').trim();
    const required=['cxName','cxStreet','cxCap','cxCity'];
    let bad=false;
    required.forEach(id=>{const el=cxEl(id);const empty=!value(id);el?.closest?.('.gf-field')?.toggleAttribute('data-invalid',empty);if(empty)bad=true;});
    const addressError=cxEl('cxAddressError');
    const capOk=/^\d{5}$/.test(value('cxCap'));
    if(!bad&&!capOk){cxEl('cxCap')?.closest?.('.gf-field')?.toggleAttribute('data-invalid',true);}
    if(addressError)addressError.textContent=bad?'Compila nome, via, CAP e comune.':(!capOk?'Il CAP ha 5 cifre.':'');
    if(bad||!capOk)return;
    payload.nome=value('cxName');payload.indirizzo=[value('cxStreet'),value('cxNumber')].filter(Boolean).join(' ');payload.codice_cliente=value('cxCode')||null;
    payload.cap=value('cxCap');payload.comune=value('cxCity');payload.provincia=value('cxProv').toUpperCase()||null;
    const key=x=>[x.indirizzo,x.cap,x.comune,x.provincia].map(v=>String(v||'').trim().toLowerCase()).join('|');
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

/* ---------- Selezione multipla ---------- */
function renderCustomerSelection(){
  const bar=cxEl('customerBulkBar');if(!bar)return;
  const n=customerDirectory.selected.size;
  bar.classList.toggle('hidden',n===0);
  const badge=cxEl('customerSelectionBadge');if(badge)badge.textContent=String(n);
  const planning=cxEl('customersGoPlanning');
  if(planning){
    planning.hidden=!!window.GFCompanyAccess&&!GFCompanyAccess.can('routes.plan');
    planning.disabled=customerDirectory.busy||customerPlanningTransferBusy||!n;
    planning.textContent='Vai alla pianificazione ('+n+')';
  }
  const msg=cxEl('customerSelectedCount');if(msg)msg.textContent=n+(n===1?' cliente selezionato':' clienti selezionati');
  // Filtro con più clienti di quelli in pagina: si possono selezionare tutti in un colpo.
  const rows=customerDirectory.rows||[],missing=rows.filter(x=>!customerDirectory.selected.has(Number(x.id))).length;
  const all=cxEl('customerSelectAllFiltered');
  if(all){all.hidden=!n||!missing||rows.length<=customerDirectory.visible.length;all.textContent='Seleziona tutti i '+rows.length+' clienti del filtro';}
}

let customerPlanningTransferBusy=false;
async function goCustomerPlanning(resume=false){
  if(customerPlanningTransferBusy||customerDirectory.busy)return;
  if(window.GFCompanyAccess&&!GFCompanyAccess.can('routes.plan')){
    alert('La pianificazione non è assegnata al tuo account.');return;
  }
  const ids=[...customerDirectory.selected];
  if(!ids.length)return;
  if(ids.some(id=>!customerDirectory.all.some(c=>Number(c.id)===id))){
    alert('La selezione clienti è cambiata. Ricarica la pagina e riprova.');return;
  }
  if(deliveries.length&&!resume&&!confirm('Sostituire le fermate aperte nel pianificatore con questa selezione? I giri già salvati restano disponibili nello storico.'))return;
  customerPlanningTransferBusy=true;renderCustomerSelection();
  try{
    // Come per gli ordini: verifica soltanto i selezionati, poi risolvi le anomalie nel dialog.
    if(!await window.GFCustomerAddresses.verify(ids))return;
    // Rileggi l'anagrafica dopo la geocodifica: mai utilizzare vecchie coordinate.
    if(ids.some(id=>!customerDirectory.selected.has(id))){
      alert('La selezione clienti è cambiata durante la verifica. Riprova.');return;
    }
    const selected=ids.map(id=>customerDirectory.all.find(c=>Number(c.id)===id));
    if(selected.some(c=>!c||!customerIsPlannable(c))){
      alert('Alcuni indirizzi risultano ancora da verificare. Riprova la verifica dalla selezione.');return;
    }
    const stops=selected.map(deliveryFromCustomer);
    await window.GFOrderPlanning?.flush();
    // The existing navigation guards must succeed before replacing the workspace.
    showTab('giro');
    if(cxEl('tab-giro')?.classList.contains('hidden'))return;
    clearRouteWorkspace();
    deliveries=stops;
    customerDirectoryPlanning=true;
    // La selezione passa al pianificatore: tornando in Clienti non resta spuntata.
    customerDirectory.selected.clear();renderCustomerSelection();
    renderDeliveries();
    updateRoutePlanningGateV68();
  }catch(error){
    alert(error.message||'Impossibile aprire la pianificazione. La selezione è stata conservata.');
  }finally{
    customerPlanningTransferBusy=false;renderCustomerSelection();
  }
}

function clearCustomerSelection(){ customerDirectory.selected.clear(); renderCustomerDirectory(); }

/* ---------- Eventi ---------- */
if(typeof document!=='undefined'&&document.addEventListener){
  document.addEventListener('click',event=>{
    const t=event.target;
    if(!t||!t.closest)return;
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
    const slot=t.closest('[data-cx-slot]');if(slot){openCustomerDrawer(Number(slot.dataset.cxSlot),'edit',true);return;}
    const edit=t.closest('[data-cx-edit]');if(edit){openCustomerDrawer(Number(edit.dataset.cxEdit),'edit');return;}
    const open=t.closest('[data-cx-open]');if(open){openCustomerDrawer(Number(open.dataset.cxOpen),'view');return;}
    if(t.closest('.cx-cb'))return;
    const row=t.closest('[data-cx-row]');
    if(row&&!t.closest('button,a,input,select,label'))openCustomerDrawer(Number(row.dataset.cxRow),'view');
  });
  document.addEventListener('change',event=>{
    const t=event.target;if(!t||!t.closest||!t.closest('#tab-clienti'))return;
    if(t.dataset&&t.dataset.cxCbAll!==undefined){toggleVisibleCustomers(t.checked);return;}
    if(t.dataset&&t.dataset.cxCb){
      const id=Number(t.dataset.cxCb);
      if(t.checked)customerDirectory.selected.add(id);else customerDirectory.selected.delete(id);
      renderCustomerDirectory();
    }
  });
  document.addEventListener('click',event=>{
    const menu=cxEl('customerFiltersMenu');
    if(menu?.open&&!menu.contains(event.target))menu.open=false;
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&cxEl('customerFiltersMenu')?.open){cxEl('customerFiltersMenu').open=false;return;}
    if(event.key!=='Escape')return;
    if(customerDrawer.current)closeCustomerDrawer();
  });
  document.addEventListener('DOMContentLoaded',()=>{
    if(typeof window!=='undefined'&&window.innerWidth<760)customerDirectory.view='grid';
    if(cxEl('customerResults'))renderCustomerDirectory();
  },{once:true});
}
