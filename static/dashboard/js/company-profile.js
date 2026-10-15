/* Profilo azienda: anteprima tracking, colore di prova, completamento e indirizzi uguali alla sede. */
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
    root.dataset.refInitialized='1';
    const logo=byId('companyLogoPreview'), clear=byId('companyLogoRemoveBtn');
    clear.addEventListener('click',()=>{
      const hidden=byId('companyLogoUrl');hidden.value='';
      hidden.dispatchEvent(new Event('input',{bubbles:true}));
      if(typeof setCompanyLogoPreview==='function') setCompanyLogoPreview();
      sync();
    });
    const fileInput=byId('companyLogoFile');
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

    const fields=byId('companyAddressFields'), legalInput=byId('companyLegalAddressInput'), billInput=byId('companyBillingAddressInput'), same=byId('gfRefSame');
    function syncSame(){
      const yes=!legalInput.value.trim()&&!billInput.value.trim();
      same.checked=yes;fields.hidden=yes;
    }
    same.addEventListener('change',e=>{
      if(e.target.checked&&(legalInput.value||billInput.value)&&!confirm('Usare la sede? Gli indirizzi differenti saranno svuotati dopo il salvataggio.')){e.target.checked=false;return;}
      if(e.target.checked)[legalInput,billInput].forEach(input=>{input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));});
      fields.hidden=e.target.checked;
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
      byId('gfRefMeter').dataset.gfWidth=String(Math.round(pct/5)*5);
      byId('gfRefMissingTitle').textContent=missing.length?'Mancano '+missing.length+' '+(missing.length===1?'elemento':'elementi')+'.':'Dati principali completi.';
      const todo=byId('gfRefTodo');todo.replaceChildren();
      missing.forEach(([id,label])=>{
        const b=document.createElement('button');b.type='button';b.className='gf-list-item';b.textContent=label+'  ›';
        b.addEventListener('click',()=>{byId(id).scrollIntoView({behavior:'smooth',block:'center'});byId(id).focus({preventScroll:true});});
        todo.append(b);
      });
      if(!missing.length){const p=document.createElement('p');p.className='gf-muted';p.textContent='✓ Il profilo contiene tutti i dati principali.';todo.append(p);}
      clear.hidden=!val('companyLogoUrl');syncSame();
    }
    tab.addEventListener('input',sync);tab.addEventListener('change',sync);
    sync();
    window.GFCompanyReference={refresh:sync};
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);
  else init();
})();
