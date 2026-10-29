/* Tutor del primo giro: barra verde in alto e fumetto con freccia sul prossimo clic.
   I passi si spuntano dai dati reali (/api/onboarding/tutor); dentro una finestra il
   fumetto aspetta sul pulsante di salvataggio. Non cambia la logica delle sezioni. */
(function(){
  'use strict';
  const el=id=>document.getElementById(id);
  // Le voci di un gruppo chiuso del menu restano nel layout ma non si vedono: contano come nascoste.
  const visible=node=>!!node&&node.isConnected&&node.getClientRects().length>0&&!node.closest('details:not([open])>:not(summary)');
  const activeTab=()=>document.querySelector('#app .tab:not(.hidden)')?.id.slice(4)||'';
  const nav=name=>document.querySelector(`#app .gf-sidebar__item[data-tab="${name}"]`);
  const isOpen=id=>{const node=el(id);return !!node&&(node.tagName==='DIALOG'?node.open:!node.classList.contains('hidden')&&!node.hidden);};
  const TRACKED=/^\/api\/(company-profile|deposits|vehicles|drivers|orders|order-sources\/\d+\/runs\/\d+\/commit|routes\/optimize|routes\/recalculate-manual|routes\/\d+\/program|planning-drafts)/;
  let status=null,finished=false,target=null,scheduled=false,refreshTimer=null,openDialogs=0,started=false;

  function go(name,label,text){return {target:nav(name),placement:'right',title:`Apri «${label}»`,text};}
  function save(id,label,fields){return {target:el(id),placement:'auto-end',title:`Premi «${label}»`,text:`Compila ${fields}, poi salva: se manca un campo obbligatorio viene segnalato in rosso.`};}
  // Prossimo clic del passo corrente, letto dallo stato della pagina.
  function plan(step){
    const tab=activeTab();
    switch(step){
      case 'company':
        if(tab!=='company')return go('company','Azienda','Qui completi i dati della tua azienda.');
        if(visible(el('companySaveChangesBtn')))return {target:el('companySaveChangesBtn'),placement:'bottom-end',title:'Premi «Salva modifiche»',text:'Il passo si spunta appena i dati sono salvati.'};
        return {target:el('companyAddressInput'),placement:'bottom',title:'Indica la sede',text:'Compila nome e indirizzo della sede: comparirà il pulsante per salvare.'};
      case 'deposit':
        if(isOpen('depositOverlay'))return save('saveDepositBtn','Salva deposito','nome e indirizzo completo');
        if(tab==='depositi')return {target:el('newDepositBtn'),placement:'bottom-end',title:'Premi «Nuovo deposito»',text:'Il deposito è il punto da cui partono e rientrano i giri.'};
        return go('depositi','Depositi','Registra il magazzino da cui partono i giri.');
      case 'vehicle':
        if(isOpen('vehicleDrawer'))return save('saveVehicleBtn','Salva mezzo','targa e nome del mezzo');
        if(tab==='mezzi')return {target:el('newVehicleBtn'),placement:'bottom-end',title:'Premi «Nuovo mezzo»',text:'Si apre la scheda del veicolo da compilare.'};
        return go('mezzi','Mezzi','Registra il veicolo con cui partirà il giro.');
      case 'driver':
        if(isOpen('driverFormOverlay'))return save('saveDriverBtn','Salva autista','i dati dell’autista');
        if(tab==='autisti')return {target:el('newDriverBtn'),placement:'bottom-end',title:'Premi «Nuovo autista»',text:'Con l’email l’autista riceve l’invito all’app.'};
        return go('autisti','Autisti','Aggiungi chi guiderà il mezzo.');
      case 'orders':
        if(isOpen('orderModal')&&visible(el('orderSave')))return save('orderSave','Crea ordine','destinatario e indirizzo di consegna');
        if(tab==='ordini')return {target:el('ordersNew'),placement:'bottom-end',title:'Premi «Nuovo ordine»',text:'Inserisci la prima consegna. Puoi anche importare gli ordini da file.'};
        return go('ordini','Ordini','Qui arrivano le consegne da pianificare.');
      case 'route': {
        if(tab==='giro')return {target:el('routeCalculateBtn'),placement:'top-end',title:'Premi «Calcola percorso»',text:'Scegli data, deposito, mezzo e autista: GiroFacile ordina le fermate per te.'};
        if(tab!=='ordini')return go('ordini','Ordini','Seleziona le consegne del primo giro.');
        const proceed=el('ordersGoPlanning');
        if(visible(proceed)&&!proceed.disabled)return {target:proceed,placement:'top-end',title:'Premi «Vai alla pianificazione»',text:'Gli ordini selezionati passano al giro.'};
        return {target:[...document.querySelectorAll('#tab-ordini .order-select:not(.order-select-all)')].find(box=>visible(box)&&!box.disabled),placement:'right',title:'Seleziona gli ordini',text:'Spunta le consegne da mettere nel primo giro.'};
      }
      case 'program':
        if(tab==='route-preview')return {target:document.querySelector('#tab-route-preview [data-preview-program]'),placement:'bottom-end',title:'Premi «Programma giro»',text:'Controlla l’anteprima: con la programmazione il giro passa all’autista.'};
        if(tab==='giro')return {target:el('routeCalculateBtn'),placement:'top-end',title:'Premi «Calcola percorso»',text:'Poi programma il giro dall’anteprima.'};
        if(tab==='bozze')return {target:document.querySelector('#tab-bozze .gf-table button'),placement:'left',title:'Riprendi il giro in bozza',text:'Lo ritrovi dove l’avevi lasciato.'};
        return {target:visible(el('sidebarDraftsItem'))?el('sidebarDraftsItem'):null,placement:'right',title:'Riprendi il giro in bozza',text:'Il giro calcolato ti aspetta in «Giri in bozza».'};
    }
    return {target:null,placement:'bottom',title:'',text:''};
  }

  // Sul pulsante di salvataggio il fumetto va fuori dalla finestra se c'è spazio, così non copre i campi.
  function savePlacement(node,tip){
    const box=node.getBoundingClientRect(),size=tip.getBoundingClientRect(),width=size.width||300,height=size.height||220;
    if(innerWidth-box.right>width+48)return 'right';
    return innerHeight-box.bottom>height+48?'bottom-end':'top-end';
  }
  function setTarget(node){
    if(target===node)return;
    target?.removeAttribute('data-gf-tutor-target');
    target=node;target?.setAttribute('data-gf-tutor-target','');
  }
  function toggle(node,show){
    if(!node)return;
    if(show&&!node.matches(':popover-open'))node.showPopover();
    if(!show&&node.matches(':popover-open'))node.hidePopover();
  }
  function hide(){setTarget(null);['coachSpot','coachTip','coachBar'].forEach(id=>toggle(el(id),false));}
  function render(){
    scheduled=false;
    const bar=el('coachBar'),tip=el('coachTip'),spot=el('coachSpot');
    const resume=el('tutorResumeBtn');if(resume)resume.hidden=status?.state!=='chiuso';
    if(!status||(!finished&&status.state!=='attivo')){hide();return;}
    const steps=status.steps||[],index=steps.findIndex(step=>step.key===status.current);
    let step=finished?{target:null,placement:'bottom',title:'Complimenti, il primo giro è programmato!',text:'Lo trovi in «Giri programmati». La guida finisce qui.'}:plan(status.current);
    let node=step.target;
    // Voce dentro un gruppo chiuso del menu: prima si indica il gruppo da aprire.
    const summary=node&&!visible(node)?node.closest('details:not([open])')?.querySelector(':scope>summary'):null;
    if(visible(summary)){
      const group=summary.textContent.trim();
      step={...step,target:summary,placement:'right',title:`Apri «${group}»`,text:`Poi scegli ${step.title.replace(/^Apri /,'')}.`};node=summary;
    }
    if(!visible(node))node=null;
    // Una finestra appena aperta passa sopra: la guida torna in cima.
    const dialogs=document.querySelectorAll('dialog[open]').length;
    if(dialogs!==openDialogs){openDialogs=dialogs;hide();}
    setTarget(node||bar);
    const placement=node&&step.placement==='auto-end'?savePlacement(node,tip):step.placement;
    tip.dataset.placement=node?placement:'top';
    tip.toggleAttribute('data-modal',!!node?.closest('dialog[open]'));
    el('coachKicker').textContent=finished?'Primo giro creato':`Passo ${index+1} di ${steps.length} · ${steps[index]?.label||''}`;
    el('coachTitle').textContent=step.title;
    el('coachText').textContent=step.text;
    el('coachExit').hidden=finished;
    el('coachDone').hidden=!finished;
    el('coachCount').textContent=finished?`${status.total} di ${status.total}`:`Passo ${index+1} di ${steps.length}`;
    el('coachStep').textContent=finished?'Completato':steps[index]?.label||'';
    el('coachSegments').replaceChildren(...steps.map((item,i)=>{const s=document.createElement('span');if(item.done)s.className='is-done';if(i===index)s.setAttribute('aria-current','step');return s;}));
    toggle(spot,!!node);toggle(bar,true);toggle(tip,true);
  }
  function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(render);}}
  async function refresh(){
    try{
      const next=await api('/api/onboarding/tutor');
      if(status?.state==='attivo'&&next.state==='completato')finished=true;
      status=next;schedule();
    }catch(e){console.warn('GiroFacile: tutor non disponibile',e);}
  }
  function refreshSoon(){clearTimeout(refreshTimer);refreshTimer=setTimeout(refresh,300);}
  async function update(action){
    try{status=await api('/api/onboarding/tutor',{method:'POST',body:JSON.stringify({action})});finished=false;schedule();}
    catch(e){toast(e.message||'Operazione non riuscita.');}
  }
  function close(){
    if(finished){finished=false;hide();return;}
    if(confirm('Uscire dalla guida al primo giro? Potrai riprenderla da Azienda.'))update('close');
  }
  function start(){
    if(started||window.GFCompanyAccess?.isCollaborator()||!HTMLElement.prototype.showPopover||!el('coachTip'))return;
    started=true;
    // Dopo un salvataggio riuscito si rilegge lo stato: il passo avanza da solo.
    const nativeFetch=window.fetch;
    window.fetch=function(input,init){
      const request=nativeFetch.apply(this,arguments);
      const method=String(init?.method||input?.method||'GET').toUpperCase();
      const path=String(typeof input==='string'?input:input?.url||'').replace(location.origin,'');
      if(method!=='GET'&&TRACKED.test(path))request.then(response=>{if(response.ok)refreshSoon();},()=>{});
      return request;
    };
    new MutationObserver(records=>{if(records.some(r=>!r.target.closest?.('.gf-coach')))schedule();})
      .observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','hidden','open','disabled']});
    refresh();
  }
  window.GFTutor={start,refresh,close,resume:()=>update('resume'),state:()=>status};
})();
