/* Company profile reference restyle: keep all existing field IDs, handlers and API calls. */
(function () {
  'use strict';
  const byId = id => document.getElementById(id);
  const el = (root, selector) => root.querySelector(selector);
  function svg(path) { return '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="' + path + '"/></svg>'; }
  const icons = {
    company:'M4 21V4h12v17 M16 9h4v12 M3 21h18 M8 8h4 M8 12h4 M8 16h4',
    phone:'M7 3h3l2 5-2.5 2a14 14 0 0 0 4.5 4.5L16 12l5 2v4a3 3 0 0 1-3 3A15 15 0 0 1 3 6a3 3 0 0 1 4-3z',
    doc:'M7 3h8l4 4v14H7z M15 3v5h4 M10 13h6 M10 17h6',
    truck:'M2 7h12v10H2z M14 10h4l3 3v4h-7 M7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4 M18 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4',
    pin:'M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11z M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4',
    users:'M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1 M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z'
  };
  function init() {
    const tab=byId('tab-company'), root=byId('companyLayoutV29');
    if(!tab || !root || root.dataset.refInitialized) return;
    const grid=el(root,'.company-profile-grid'), cards=[...grid.querySelectorAll(':scope > .company-card-v29')];
    const onboarding=el(root,'.onboarding-card-v29');
    if(cards.length!==5 || !onboarding) return;
    root.dataset.refInitialized='1';
    root.classList.add('gf-ref-profile');
    const hero=document.createElement('section');
    hero.className='gf-ref-hero';
    hero.setAttribute('aria-label','Identità e anteprima aziendale');
    hero.innerHTML='<div class="gf-ref-identity">'+
      '<div class="gf-ref-banner" aria-hidden="true"><svg viewBox="0 0 800 132" preserveAspectRatio="xMidYMid slice"><path d="M-20 100 C100 30 190 120 320 70 S520 10 640 78 S760 50 830 22" fill="none" stroke="#fff" stroke-opacity=".38" stroke-width="3" stroke-linecap="round" stroke-dasharray="2 9"/><g fill="#fff" fill-opacity=".8"><circle cx="150" cy="82" r="5"/><circle cx="320" cy="70" r="5"/><circle cx="470" cy="38" r="5"/><circle cx="640" cy="78" r="5"/></g></svg></div>'+
      '<div class="gf-ref-logo-row"><div class="gf-ref-logo-host"></div><div class="gf-ref-logo-actions"></div></div>'+
      '<div class="gf-ref-company-copy"><h2 id="gfRefName">Nome azienda</h2><p id="gfRefDescription"></p><div id="gfRefFacts" class="gf-ref-facts"></div></div>'+
      '<div class="gf-ref-brand-controls"><div><strong>Colore del brand</strong><small>Anteprima locale del colore: non cambia il tracking pubblicato</small></div><div id="gfRefColors" class="gf-ref-swatches" role="group" aria-label="Colore di anteprima"></div></div>'+
    '</div><div class="gf-ref-preview"><h2>Anteprima per i tuoi clienti</h2><p>Simulazione del tracking. Nome e logo seguono i dati del profilo.</p>'+
      '<div class="gf-ref-phone"><div class="gf-ref-phone-head"><span id="gfRefPhoneLogo" class="gf-ref-phone-logo"></span><b id="gfRefPhoneName"></b></div>'+
      '<div class="gf-ref-phone-body"><small>Ordine di esempio</small><h3>È in consegna</h3><div class="gf-ref-eta"><span>Arrivo previsto</span><strong>16:20</strong></div>'+
      '<ol class="gf-ref-steps"><li class="done">Ordine preparato</li><li class="current">In viaggio verso di te</li><li>Consegnato</li></ol>'+
      '<div class="gf-ref-tracking-button">Segui l’autista</div></div></div></div>';
    root.insertBefore(hero,grid);

    const row=el(cards[0],'.company-logo-row-v29');
    const logo=byId('companyLogoPreview');
    el(hero,'.gf-ref-logo-host').appendChild(logo);
    const actions=el(hero,'.gf-ref-logo-actions');
    [...row.children].forEach(child => {
      if(child.contains(byId('companyLogoUrl')) || child.querySelector('input[type=file]')) actions.appendChild(child);
    });
    const clear=document.createElement('button');clear.type='button';clear.className='gf-ref-logo-remove';
    clear.textContent='Rimuovi logo';actions.appendChild(clear);
    clear.addEventListener('click',()=>{
      const hidden=byId('companyLogoUrl');hidden.value='';
      hidden.dispatchEvent(new Event('input',{bubbles:true}));
      if(typeof setCompanyLogoPreview==='function') setCompanyLogoPreview();
      sync();
    });
    const fileInput=el(actions,'input[type=file]');
    if(fileInput) fileInput.addEventListener('change',()=>{
      setTimeout(()=>{
        if(typeof updateCompanyProfileDirtyStateV29==='function')updateCompanyProfileDirtyStateV29();
        sync();
      },500);
    });
    if(logo) new MutationObserver(()=>{
      sync();
      if(typeof updateCompanyProfileDirtyStateV29==='function')updateCompanyProfileDirtyStateV29();
    }).observe(logo,{childList:true,characterData:true,subtree:true});

    const details=document.createElement('div');details.className='gf-ref-details';
    const stack=document.createElement('div');stack.className='gf-ref-stack';
    const rail=document.createElement('aside');rail.className='gf-ref-rail';
    details.append(stack,rail);
    root.insertBefore(details,grid);
    const names=['Identità','Contatti e sede','Dati fiscali','Operatività','Indirizzi legali e fatturazione'];
    const help=['Come si presenta la tua azienda ai clienti e agli autisti.','Recapiti e sede della tua azienda.','Informazioni fiscali e codice azienda.','Dimensioni della tua attività.','Indica indirizzi differenti dalla sede aziendale.'];
    ['company','phone','doc','truck','pin'].forEach((name,i)=>{
      const card=cards[i],heading=el(card,'.company-section-heading'),body=document.createElement('div');
      body.className='gf-ref-section-body';
      [...card.children].forEach(node=>{if(node!==heading)body.appendChild(node);});
      card.append(body);stack.appendChild(card);
      el(heading,'.company-section-icon').innerHTML=svg(icons[name]);
      el(heading,'h2').textContent=names[i];el(heading,'p').textContent=help[i];
    });
    // Match the reference's identity section: description alongside the company name.
    const description=el(cards[3],'.company-description');
    if(description)el(cards[0],'.gf-ref-section-body').appendChild(description);

    rail.innerHTML='<section class="gf-ref-completion"><div class="gf-ref-progress-head">'+
      '<div class="gf-ref-ring"><svg viewBox="0 0 84 84"><circle class="track" cx="42" cy="42" r="36"/><circle class="meter" id="gfRefMeter" cx="42" cy="42" r="36"/></svg><strong id="gfRefPercent">0%</strong></div>'+
      '<div><h2>Completamento del profilo</h2><p id="gfRefMissingTitle"></p></div></div><div id="gfRefTodo" class="gf-ref-todo"></div></section>';
    rail.appendChild(onboarding);
    grid.remove();

    const legal=el(cards[4],'.gf-ref-section-body'), legalInput=byId('companyLegalAddressInput'), billInput=byId('companyBillingAddressInput');
    const same=document.createElement('label');same.className='gf-ref-same-address';
    same.innerHTML='<span><b>Uguali alla sede aziendale</b><small>Usa la sede come indirizzo legale e di fatturazione</small></span><input id="gfRefSame" type="checkbox" role="switch">';
    legal.prepend(same);
    function syncSame(){
      const yes=!legalInput.value.trim()&&!billInput.value.trim();
      byId('gfRefSame').checked=yes;legal.classList.toggle('gf-ref-same-on',yes);
    }
    same.querySelector('input').addEventListener('change',e=>{
      if(e.target.checked&&(legalInput.value||billInput.value)&&!confirm('Usare la sede? Gli indirizzi differenti saranno svuotati dopo il salvataggio.')){e.target.checked=false;return;}
      if(e.target.checked)[legalInput,billInput].forEach(input=>{input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));});
      legal.classList.toggle('gf-ref-same-on',e.target.checked);
    });
    [legalInput,billInput].forEach(x=>x.addEventListener('input',syncSame));

    const colors=['#1F5BFF','#0B8A7C','#7B4FE0','#C2255C','#D9480F','#2B8A3E','#1F2A44'];
    const swatches=byId('gfRefColors');
    function selectColor(c){
      if(!/^#[0-9a-f]{6}$/i.test(c))return;
      root.style.setProperty('--gf-ref-color',c);
      [...swatches.querySelectorAll('button')].forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.color===c)));
    }
    colors.forEach(c=>{
      const btn=document.createElement('button');btn.type='button';btn.className='gf-ref-swatch';
      btn.style.background=c;btn.dataset.color=c;btn.setAttribute('aria-label','Anteprima '+c);
      btn.addEventListener('click',()=>selectColor(c));swatches.appendChild(btn);
    });
    const custom=document.createElement('input');custom.type='color';custom.value='#1F5BFF';
    custom.className='gf-ref-custom-color';custom.setAttribute('aria-label','Anteprima colore personalizzato');
    custom.addEventListener('input',()=>selectColor(custom.value));swatches.appendChild(custom);
    selectColor('#1F5BFF');

    const required=[
      ['companyNameInput','Nome azienda'],['companyPhoneInput','Telefono'],['companyEmailInput','Email aziendale'],
      ['companyAddressInput','Indirizzo sede'],['companyCityInput','Città'],['companyZipInput','CAP'],
      ['companyCountryInput','Paese'],['companyVatInput','Partita IVA'],['companyActivityTypeInput','Descrizione attività']
    ];
    function sync(){
      const val=id=>(byId(id)?.value||'').trim();
      const name=val('companyNameInput')||'Nome azienda';
      byId('gfRefName').textContent=name;byId('gfRefPhoneName').textContent=name;
      byId('gfRefDescription').textContent=val('companyActivityTypeInput')||'Aggiungi una descrizione dell’attività.';
      const ph=byId('gfRefPhoneLogo'),img=el(logo,'img');
      ph.replaceChildren();
      if(img){const copy=document.createElement('img');copy.src=img.src;copy.alt='';ph.append(copy);}
      else ph.textContent=(name.split(/\s+/).slice(0,2).map(word=>word[0]).join('')||'GF').toUpperCase();
      const facts=byId('gfRefFacts');facts.replaceChildren();
      const entries=[
        [val('companyCityInput'),'pin'],[val('companyVatInput')?'P. IVA '+val('companyVatInput'):'','doc'],
        [byId('companySizeInput')?.selectedOptions[0]?.textContent,'users'],
        [val('companyDailyDeliveriesInput')?byId('companyDailyDeliveriesInput').selectedOptions[0].textContent+' consegne al giorno':'','truck']
      ];
      entries.forEach(([text,ic])=>{
        if(!text||/Seleziona|Consegne medie/.test(text))return;
        const item=document.createElement('span');item.innerHTML=svg(icons[ic]);item.append(document.createTextNode(text));facts.append(item);
      });
      const missing=required.filter(([id])=>!val(id)),pct=Math.round((required.length-missing.length)*100/required.length);
      byId('gfRefPercent').textContent=pct+'%';
      byId('gfRefMeter').style.strokeDashoffset=String(2*Math.PI*36*(1-pct/100));
      byId('gfRefMissingTitle').textContent=missing.length?'Mancano '+missing.length+' '+(missing.length===1?'elemento':'elementi')+'.':'Dati principali completi.';
      const todo=byId('gfRefTodo');todo.replaceChildren();
      missing.forEach(([id,label])=>{
        const b=document.createElement('button');b.type='button';b.textContent=label+'  ›';
        b.addEventListener('click',()=>{byId(id).scrollIntoView({behavior:'smooth',block:'center'});byId(id).focus({preventScroll:true});});
        todo.append(b);
      });
      if(!missing.length){const p=document.createElement('p');p.textContent='✓ Il profilo contiene tutti i dati principali.';todo.append(p);}
      clear.hidden=!val('companyLogoUrl');syncSame();
    }
    tab.addEventListener('input',sync);tab.addEventListener('change',sync);
    sync();
    window.GFCompanyReference={refresh:sync};
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);
  else init();
})();
