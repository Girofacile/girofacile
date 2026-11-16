/* Sales workspace. API is authoritative; no CRM data is persisted in the browser. */
window.GFCRM = (() => {
  const interests = {unknown:'Da qualificare',interested:'Interessato',later:'Da rivalutare',not_interested:'Non interessato'};
  const stages = {new:'Nuova',contacted:'Contatto avviato',qualified:'Qualificata',demo:'Demo',proposal:'Proposta',negotiation:'Negoziazione',won:'Vinta',lost:'Persa'};
  const statuses = {open:'Aperto',completed:'Completato',cancelled:'Annullato',overdue:'Scaduti'};
  const kinds = {note:'Nota',call:'Telefonata',email:'Email registrata',meeting:'Riunione'};
  const titles = {dashboard:'Dashboard',companies:'Aziende',detail:'Scheda azienda',contacts:'Contatti',opportunities:'Pipeline',followups:'Follow-up',activities:'Attività',reports:'Report'};
  let state = {tab:'dashboard',page:1,selected:null,rows:[],caps:null,request:0};
  let edit = null;
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(Number(value || 0));
  const date = value => value ? new Date(value).toLocaleString('it-IT',{dateStyle:'short',timeStyle:'short'}) : '—';
  const button = (label,action,variant='secondary') => `<button class="gf-button" data-variant="${variant}" type="button" data-crm-action="${action}">${label}</button>`;
  async function api(path, options={}) {
    const response = await fetch('/api/admin/crm'+path,{...options,headers:{'Content-Type':'application/json',...options.headers},cache:'no-store'});
    if(response.status===401){ location.href='/admin/login'; throw new Error('Accedi di nuovo'); }
    if(!response.ok){
      const body=await response.json().catch(()=>({}));
      if(response.status===403){ state.caps=null; state.rows=[]; state.selected=null; el('crm-content')?.replaceChildren(); el('crm-selection')?.replaceChildren(); el('crm-toolbar')?.replaceChildren(); el('crm-dialog')?.close(); el('crm-form-fields')?.replaceChildren(); edit=null; }
      const detail=Array.isArray(body.detail)?body.detail.map(e=>e.msg).join(' · '):body.detail;
      throw new Error(detail || 'Impossibile completare la richiesta');
    }
    return response.json();
  }
  function notice(message){ el('crm-message').textContent=message; el('crm-message').classList.toggle('gf-hidden',!message); }
  function pager(total){return `<nav class="gf-pagination" aria-label="Pagine CRM">${state.page>1?button('← Precedente','prev'):''}<span>${total} risultati · Pagina ${state.page} di ${Math.max(1,Math.ceil(total/30))}</span>${state.page*30<total?button('Successiva →','next'):''}</nav>`;}
  function table(headers,rows){return `<div class="gf-table-wrap"><table class="gf-table" data-gf-responsive="cards"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(cells=>`<tr>${cells.map((c,i)=>`<td data-label="${headers[i]}">${c}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}">Nessun risultato. Puoi aggiungere un’azienda o modificare i filtri.</td></tr>`}</tbody></table></div>`;}
  function renderReport(data){
    const cards=[['Aziende',data.companies],['Contatti',data.contacts],['Follow-up aperti',data.open_followups],['Follow-up scaduti',data.overdue_followups]];
    const stageRows=Object.entries(stages).map(([key,label])=>{const s=data.stages.find(x=>x.stage===key);return [label,String(s?.count||0),money(s?.amount)];});
    return `<div class="gf-grid" data-cols="4">${cards.map(([label,v])=>`<div class="gf-stat-card"><span class="gf-stat-card__label">${label}</span><strong class="gf-stat-card__value">${v}</strong></div>`).join('')}</div><section class="gf-panel"><header class="gf-panel__header"><h3 class="gf-panel__title">Pipeline commerciale</h3><span class="gf-badge" data-status="info">Conversione: ${data.win_rate===null?'—':data.win_rate+'%'}</span></header>${table(['Fase','Trattative','Valore EUR'],stageRows)}<div class="gf-panel__body"><p class="gf-muted">Intero periodo · ${data.scope==='all'?'Tutto il portafoglio':'Portafoglio assegnato'} · Aziende attive. Conversione = vinte / (vinte + perse). I valori sono commerciali, non incassi.</p></div></section>${state.tab==='dashboard'?`<div class="gf-cluster">${button('Gestisci aziende','companies','primary')}${button('Controlla follow-up','followups')}</div>`:''}`;
  }
  async function load(){
    const request=++state.request;
    notice(''); el('crm-content').innerHTML='<p class="gf-loading" role="status">Caricamento CRM…</p>';
    try {
      state.caps=await api('/me');
      if(request!==state.request)return;
      el('crm-tabs').innerHTML=Object.entries(titles).filter(([key])=>key!=='detail'||state.selected).map(([key,label])=>`<button class="gf-button" data-variant="${key===state.tab?'primary':'secondary'}" type="button" data-crm-action="${key}" aria-pressed="${key===state.tab}">${label}</button>`).join('');
      el('crm-selection').innerHTML=state.selected?`<strong>${esc(state.selected.name)}</strong> ${button('Tutte le aziende','clear')} ${state.selected.archived?'<span class="gf-badge" data-status="warning">Archiviata</span>':''}`:'';
      el('crm-toolbar').innerHTML='';
      const report=['dashboard','reports','detail'].includes(state.tab);
      el('crm-filters').classList.toggle('gf-hidden',report);
      el('crm-search-field').classList.toggle('gf-hidden',state.tab!=='companies');
      el('crm-archive-field').classList.toggle('gf-hidden',state.tab!=='companies');
      el('crm-status-field').classList.toggle('gf-hidden',!['companies','opportunities','followups'].includes(state.tab));
      if(state.tab==='detail' && state.selected){
        const [company,history]=await Promise.all([api('/companies/'+state.selected.id),api('/companies/'+state.selected.id+'/history')]);
        if(request!==state.request)return;
        state.selected=company;state.rows=[company];
        const owner=state.caps.assignees.find(a=>a.id===company.owner_id)?.name || (company.owner_id?'Commerciale assegnato':'Non assegnata');
        const details=[['Ragione sociale',company.name],['Email',company.email],['Telefono',company.phone],['Paese',company.country],['Partita IVA',company.vat],['Città',company.city],['Settore',company.sector],['Provenienza',company.source],['Interesse',interests[company.interest]],['Responsabile',owner],['Note',company.notes]];
        const actions={created:'Creato',updated:'Aggiornato'};
        function eventLabel(row){if(row.action.startsWith('stage:')){const [a,b]=row.action.slice(6).split('->');return 'Fase: '+(stages[a]||'Creazione')+' → '+(stages[b]||b);}return actions[row.action]||row.action;}
        const entities={crm_companies:'Azienda',crm_contacts:'Contatto',crm_opportunities:'Trattativa',crm_followups:'Follow-up',crm_activities:'Attività'};
        el('crm-toolbar').innerHTML=state.caps.write?button('Modifica azienda','edit:'+company.id,'primary'):'';
        el('crm-content').innerHTML=`<section class="gf-panel">${table(['Campo','Valore'],details.map(([k,v])=>[k,esc(v||'—')]))}</section><div class="gf-cluster">${button('Contatti','contacts')}${button('Trattative','opportunities')}${button('Follow-up','followups')}${button('Attività','activities')}</div><section class="gf-panel"><header class="gf-panel__header"><h3 class="gf-panel__title">Ultime 100 modifiche</h3></header>${table(['Data','Oggetto','Modifica','Autore'],history.map(r=>[date(r.created_at),entities[r.entity]||'Record',esc(eventLabel(r)),esc(r.actor)]))}</section>`;
        window.GFDesignSystem?.enhance();return;
      }
      if(report){
        const data=await api('/reports');if(request!==state.request)return;
        el('crm-content').innerHTML=renderReport(data);return;
      }
      if(state.tab==='companies'){
        el('crm-toolbar').innerHTML=(state.caps.write?button('Nuova azienda','new','primary'):'')+(state.caps.export?button('Esporta CSV','export'):'');
      } else if(state.caps.write && state.selected && !state.selected.archived){
        el('crm-toolbar').innerHTML=button({contacts:'Nuovo contatto',opportunities:'Nuova trattativa',followups:'Nuovo follow-up',activities:'Registra attività'}[state.tab],'new','primary');
      } else if(state.caps.write){el('crm-toolbar').innerHTML=button('Scegli un’azienda per aggiungere dati','companies');}
      const params=new URLSearchParams({page:state.page,page_size:30});
      if(state.tab==='companies'){
        params.set('q',el('crm-search').value);params.set('interest',el('crm-status').value);params.set('archived',el('crm-archived').checked);
      }else{
        if(state.selected)params.set('company_id',state.selected.id);
        params.set('status',el('crm-status').value);
      }
      const data=await api((state.tab==='companies'?'/companies':'/records/'+state.tab)+'?'+params);
      if(request!==state.request)return;
      state.rows=data.items;
      const editButton=r=>state.caps.write?button('Modifica','edit:'+r.id):'';
      let headers,rows;
      if(state.tab==='companies'){
        headers=['Azienda','Contatti aziendali','Interesse','Azioni'];
        rows=data.items.map(r=>[esc(r.name),`${esc(r.email)}<br>${esc(r.phone)}`,esc(interests[r.interest]),`${button('Apri','open:'+r.id)} ${editButton(r)}`]);
      }else if(state.tab==='contacts'){
        headers=['Referente','Azienda','Email / telefono','Ruolo','Azioni'];
        rows=data.items.map(r=>[`${esc(r.name)}${r.do_not_contact?'<br><span class="gf-badge" data-status="danger">Non contattare</span>':''}`,esc(r.company_name),`${esc(r.email)}<br>${esc(r.phone)}`,esc(r.role),editButton(r)]);
      }else if(state.tab==='opportunities'){
        headers=['Trattativa','Azienda','Fase','Valore','Chiusura prevista','Azioni'];
        rows=data.items.map(r=>[esc(r.title),esc(r.company_name),esc(stages[r.stage]),money(r.amount),date(r.expected_close),editButton(r)]);
      }else if(state.tab==='followups'){
        headers=['Attività','Azienda','Scadenza','Stato','Priorità','Azioni'];
        rows=data.items.map(r=>[esc(r.title),esc(r.company_name),date(r.due_at),`${esc(statuses[r.status])}${r.status==='open'&&new Date(r.due_at)<new Date()?'<br><span class="gf-badge" data-status="danger">Scaduto</span>':''}`,r.priority==='high'?'Alta':'Normale',editButton(r)]);
      }else{
        headers=['Data','Azienda','Tipo','Nota','Autore'];
        rows=data.items.map(r=>[date(r.occurred_at),esc(r.company_name),esc(kinds[r.kind]),esc(r.notes),esc(r.actor)]);
      }
      el('crm-content').innerHTML=`<section class="gf-panel">${table(headers,rows)}</section>${pager(data.total)}`;
      window.GFDesignSystem?.enhance();
    }catch(error){if(request===state.request){el('crm-content').replaceChildren();notice(error.message);}}
  }
  function tab(name){
    state.tab=name;state.page=1;
    const choices=name==='companies'?interests:name==='opportunities'?stages:name==='followups'?statuses:{};
    el('crm-status').innerHTML='<option value="">Tutti</option>'+Object.entries(choices).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
    load();
  }
  function field(key,label,type='text',value='',required=false,choices=null){
    const id='crm-field-'+key;
    let input;
    if(choices)input=`<select class="gf-select" id="${id}" name="${key}">${Object.entries(choices).map(([k,v])=>`<option value="${esc(k)}" ${String(value??'')===k?'selected':''}>${esc(v)}</option>`).join('')}</select>`;
    else if(type==='textarea')input=`<textarea class="gf-textarea" id="${id}" name="${key}" maxlength="10000" ${required?'required':''}>${esc(value)}</textarea>`;
    else if(type==='checkbox')input=`<input id="${id}" name="${key}" type="checkbox" ${value?'checked':''}>`;
    else input=`<input class="gf-input" id="${id}" name="${key}" type="${type}" value="${esc(value)}" ${required?'required':''} ${type==='number'?'min="0" step="'+(key==='amount'?'0.01':'1')+'"'+(key==='probability'?' max="100"':''):'maxlength="220"'}>`;
    return `<div class="gf-field"><label class="gf-field__label" for="${id}">${label}${required?' *':''}</label>${input}</div>`;
  }
  function localDate(value){const d=value?new Date(value):new Date();return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
  async function form(row=null){
    if(!state.caps?.write)return;
    const kind=state.tab==='detail'?'companies':state.tab;
    try{
      const parent=kind==='companies'?null:await api('/companies/'+(row?.company_id||state.selected?.id));
      if(parent?.archived)throw new Error('Ripristina prima l’azienda');
      edit={kind,row,parent};
      const v=row||{};let fields='';
      if(kind==='companies'){
        fields=field('name','Ragione sociale','text',v.name,true)+field('email','Email aziendale','email',v.email)+field('phone','Telefono','tel',v.phone)+field('country','Paese (codice a 2 lettere)','text',v.country||'IT')+field('vat','Partita IVA','text',v.vat)+field('city','Città','text',v.city)+field('sector','Settore','text',v.sector)+field('source','Provenienza','text',v.source)+field('interest','Interesse','text',v.interest||'unknown',false,interests);
        if(state.caps.view_all){const owners={'':'Non assegnata'};state.caps.assignees.forEach(a=>owners[a.id]=a.name);if(v.owner_id&&!owners[v.owner_id])owners[v.owner_id]='Assegnatario non più attivo';fields+=field('owner_id','Commerciale assegnato','text',v.owner_id,false,owners);if(row)fields+=field('archived','Archiviata (prima chiudere i follow-up aperti)','checkbox',v.archived);}
      }else if(kind==='contacts'){
        fields=field('name','Nome referente','text',v.name,true)+field('role','Ruolo','text',v.role)+field('email','Email','email',v.email)+field('phone','Telefono','tel',v.phone)+field('do_not_contact','Non contattare','checkbox',v.do_not_contact);
      }else if(kind==='opportunities'){
        fields=field('title','Trattativa','text',v.title,true)+field('stage','Fase','text',v.stage||'new',false,stages)+field('amount','Valore EUR','number',v.amount||0)+field('probability','Probabilità (%)','number',v.probability||0)+field('expected_close','Chiusura prevista','datetime-local',v.expected_close?localDate(v.expected_close):'')+field('lost_reason','Motivo perdita (obbligatorio per Persa)','text',v.lost_reason);
      }else if(kind==='followups'){
        fields=field('title','Attività da svolgere','text',v.title,true)+field('due_at','Scadenza (ora locale)','datetime-local',localDate(v.due_at),true)+field('status','Stato','text',v.status||'open',false,{open:'Aperto',completed:'Completato',cancelled:'Annullato'})+field('priority','Priorità','text',v.priority||'normal',false,{normal:'Normale',high:'Alta'});
      }else{
        fields=field('kind','Tipo','text','note',false,kinds)+field('occurred_at','Data e ora','datetime-local',localDate(),true);
      }
      fields+=field('notes',kind==='activities'?'Descrizione attività':'Note','textarea',v.notes,kind==='activities');
      el('crm-form-fields').innerHTML=fields;
      el('crm-dialog-title').textContent=(row?'Modifica · ':'Nuovo · ')+titles[kind];
      el('crm-form-company').textContent=parent?'Azienda: '+parent.name:'';
      el('crm-form-error').textContent='';el('crm-save').disabled=false;
      el('crm-dialog').showModal();
    }catch(error){notice(error.message);}
  }
  async function save(event){
    event.preventDefault();if(!edit)return;
    const snapshot=edit;const data=Object.fromEntries(new FormData(event.target));
    event.target.querySelectorAll('input[type="checkbox"]').forEach(i=>data[i.name]=i.checked);
    if(snapshot.kind!=='companies')data.company_id=snapshot.parent.id;
    else if('owner_id'in data)data.owner_id=data.owner_id?Number(data.owner_id):null;
    else data.owner_id=snapshot.row?.owner_id??null;
    for(const key of ['due_at','occurred_at','expected_close'])if(key in data)data[key]=data[key]?new Date(data[key]).toISOString():null;
    if('probability'in data)data.probability=Number(data.probability);
    if(snapshot.row)data.version=snapshot.row.version;
    el('crm-save').disabled=true;el('crm-form-error').textContent='';
    try{
      const result=await api('/'+snapshot.kind+(snapshot.row?'/'+snapshot.row.id:''),{method:snapshot.row?'PUT':'POST',body:JSON.stringify(data)});
      if(snapshot.kind==='companies'&&state.selected?.id===result.id)state.selected=result;
      el('crm-dialog').close();edit=null;await load();notice('Salvato correttamente.');
    }catch(error){el('crm-form-error').textContent=error.message;}finally{el('crm-save').disabled=false;}
  }
  async function action(value){
    if(value in titles){tab(value);return;}
    if(value==='new'){form();return;}
    if(value==='clear'){state.selected=null;tab(state.tab==='detail'?'companies':state.tab);return;}
    if(value==='prev'||value==='next'){state.page+=value==='prev'?-1:1;load();return;}
    if(value==='retry'){load();return;}
    if(value==='export'){
      try{const r=await fetch('/api/admin/crm/export',{cache:'no-store'});if(!r.ok)throw new Error((await r.json()).detail||'Esportazione non riuscita');const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download='crm-aziende.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){notice(e.message);}return;
    }
    const [operation,id]=value.split(':');const row=state.rows.find(r=>r.id===Number(id));
    if(!row)return;
    if(operation==='edit')form(row);
    if(operation==='open'){state.selected=row;tab('detail');}
  }
  document.addEventListener('DOMContentLoaded',()=>{
    el('section-crm').addEventListener('click',event=>{const target=event.target.closest('[data-crm-action]');if(target)action(target.dataset.crmAction);});
    el('crm-filters').addEventListener('submit',event=>{event.preventDefault();state.page=1;load();});
    el('crm-status').addEventListener('change',()=>{state.page=1;load();});
    el('crm-archived').addEventListener('change',()=>{state.page=1;load();});
    el('crm-form').addEventListener('submit',save);
    el('crm-close').addEventListener('click',()=>el('crm-dialog').close());
  });
  return {open:()=>load()};
})();
