/* Self-contained demo: no API requests, persistence, routing or notifications. */
(() => {
  'use strict';
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  const icons = {
    package:'M12 3 3 7.5v9L12 21l9-4.5v-9L12 3z M3 7.5l9 5 9-5 M12 12.5V21 M7.5 5.3l9 4.5v4',
    pin:'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0z M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4',
    weight:'M8 7V5a4 4 0 0 1 8 0v2 M5 7h14l2 14H3L5 7z M10 5h4',
    search:'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14 M15 15l6 6',
    check:'m5 12 4 4L19 6', truck:'M2 6h11v10H2z M13 9h5l3 3v4h-8z M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4 M18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4',
    fleet:'M1 10h10v9H1z M11 13h5l3 3v3h-8 M4 7V3h11v7 M15 5h4l3 3v3h-7 M5 21v-3 M15 21v-3',
    calendar:'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h3 M13 17h3',
    user:'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M4 21a8 8 0 0 1 16 0',
    settings:'M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6',
    route:'M5 5a2 2 0 1 0 0 .01 M19 19a2 2 0 1 0 0 .01 M9 5h7a4 4 0 0 1 0 8H8a3 3 0 0 0 0 6h7',
    depot:'m3 10 9-7 9 7v11H3V10z M8 21v-8h8v8', flag:'M5 22V3 M5 3h14l-3 4 3 4H5',
    spark:'m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7z',
    info:'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20 M12 11v6 M12 7v.1',
    edit:'m4 15 11-11 5 5L9 20H4v-5z M13 6l5 5'
  };
  const svg = name => '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + icons[name] + '"></path></svg>';
  $$('[data-icon]').forEach(el => el.innerHTML = svg(el.dataset.icon));
  const stops = [
    {id:1,name:'Farmacia Centrale',address:'Via Roma 12, Milano',packages:8,weight:180,window:'09:00–11:00',unload:10,tag:'ZTL'},
    {id:2,name:'Alimentari Verdi',address:'Via Volta 8, Sesto San Giovanni',packages:5,weight:160,window:'09:00–12:00',unload:15,tag:'Sponda'},
    {id:3,name:'Hotel Aurora',address:'Viale Monza 90, Milano',packages:4,weight:120,window:'10:00–12:00',unload:10,tag:''},
    {id:4,name:'Ristorante Portico',address:'Via Dante 6, Bresso',packages:7,weight:210,window:'10:00–13:00',unload:15,tag:''},
    {id:5,name:'Market Nord',address:'Via Libertà 20, Cinisello Balsamo',packages:6,weight:240,window:'09:00–12:00',unload:15,tag:'Sponda'},
    {id:6,name:'Bar Giardino',address:'Via Verdi 4, Milano',packages:2,weight:70,window:'09:00–12:00',unload:10,tag:''}
  ];
  const selected = new Set(stops.map(s => s.id));
  let stage = 0, reached = 0, completed = false;
  const value = id => $('#' + id).value;
  const format = n => Number(n).toLocaleString('it-IT',{maximumFractionDigits:1});
  const chosen = () => stops.filter(s => selected.has(s.id));
  const isFleet = () => $('input[name="mode"]:checked').value === 'fleet';
  const esc = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text = (selector, v) => $$(selector).forEach(el => el.textContent = v);
  const dateLabel = () => value('date') ? new Date(value('date') + 'T12:00:00').toLocaleDateString('it-IT',{day:'numeric',month:'long',year:'numeric'}) : 'Data da scegliere';
  function message(content) { $('#message').textContent=content; $('#message').hidden=!content; }
  function renderStops() {
    $('#stops').innerHTML=stops.map(s => `<article class="stop-row" data-row="${s.id}">
      <label class="stop-check"><input type="checkbox" data-select="${s.id}" checked aria-label="Seleziona ${esc(s.name)}"></label>
      <div><div class="stop-label"><strong>${esc(s.name)}</strong>${s.tag?`<span class="tag ${s.tag==='ZTL'?'amber':''}">${s.tag}</span>`:''}</div><small>${esc(s.address)}</small></div>
      <div class="stop-quantity"><span data-row-packages="${s.id}">${s.packages}</span> colli<small><span data-row-weight="${s.id}">${s.weight}</span> kg · ${s.window}</small></div>
      <button class="detail-button" data-detail="${s.id}" aria-expanded="false" aria-controls="editor-${s.id}" aria-label="Dettagli ${esc(s.name)}">${svg('edit')}</button>
      <div class="stop-editor" id="editor-${s.id}" hidden><div class="fields">
      <label>Colli<input type="number" min="1" max="9999" step="1" value="${s.packages}" data-edit="packages" data-id="${s.id}" required></label>
      <label>Peso (kg)<input type="number" min="0" max="100000" step="0.1" value="${s.weight}" data-edit="weight" data-id="${s.id}" required></label>
      <label>Scarico (minuti)<input type="number" min="1" max="240" step="1" value="${s.unload}" data-edit="unload" data-id="${s.id}" required></label>
      <label>Finestra oraria<select data-edit="window" data-id="${s.id}"><option>${s.window}</option><option>08:00–13:00</option><option>14:00–18:00</option></select></label></div>
      <p>${s.tag?`Requisito da rispettare: ${s.tag}. `:''}Nella versione reale sarà possibile gestire anche più fasce orarie e gli altri vincoli della consegna.</p></div></article>`).join('');
  }
  function update() {
    const list=chosen();
    text('[data-count]',list.length);
    text('[data-packages]',format(list.reduce((n,s)=>n+s.packages,0)));
    text('[data-weight]',format(list.reduce((n,s)=>n+s.weight,0)));
    text('#summary-name',value('name').trim() || 'Il tuo nuovo giro');
    text('#summary-depot','Da '+value('depot'));
    text('#summary-date',dateLabel()); text('#summary-time',value('time')?'Partenza alle '+value('time'):'Orario da scegliere');
    $('#fleet-fields').hidden=!isFleet();
    $('#select-all').checked=selected.size===stops.length;
    $('#select-all').indeterminate=selected.size>0&&selected.size<stops.length;
    text('#driver-avatar',value('driver').split(' ').map(w=>w[0]).join(''));
    text('#vehicle-hint',value('vehicle')==='van'?'Gasolio · portata 1.500 kg · accesso ZTL demo':'Elettrico · portata 1.200 kg · accesso ZTL demo');
    const titles=[`${list.length} fermate selezionate`,'La configurazione è quasi pronta','Controlla, poi pianifica','Simulazione completata'];
    const hints=['Nel prossimo passaggio scegli data, mezzo e autista.','Prosegui per vedere il riepilogo dimostrativo.','Conferma di aver controllato i dati per proseguire.','Puoi tornare a modificare la proposta.'];
    text('#action-title',titles[stage]); text('#action-hint',hints[stage]);
    $('#next').disabled=(stage===0&&!list.length)||(stage===2&&!$('#confirm-review').checked);
    text('#trip-status',completed?'Pianificato · demo':'In preparazione');
  }
  function invalidate() {
    completed=false; reached=Math.min(reached,1); $('#confirm-review').checked=false;
    message(''); updateSteps(); update();
  }
  const helps=[['Prima le consegne.','Parti dagli ordini già selezionati. Apri i dettagli solo per le fermate che richiedono attenzione.'],['Una scelta alla volta.','Usa le schede per scegliere un mezzo o una flotta. Rientro, costi e pause sono in “Personalizza il giro”.'],['Un controllo prima di partire.','Hai ancora la possibilità di correggere ogni dato. La conferma finale arriva solo dopo la tua verifica.'],['Dal piano alla strada.','Nel gestionale, il giro confermato sarà disponibile tra i giri programmati. Qui puoi continuare a provare il flusso.']];
  function updateSteps() {
    $$('[data-step]').forEach(btn=>{
      const n=Number(btn.dataset.step); btn.classList.toggle('done',n<stage);
      if(n===stage) btn.setAttribute('aria-current','step'); else btn.removeAttribute('aria-current');
      // Future steps are reached using the validated primary action.
      btn.disabled=n>reached || (n===3&&!completed);
      btn.querySelector('.step-number').textContent=n<stage?'✓':String(n+1).padStart(2,'0');
    });
  }
  function show(n) {
    stage=n; $$('[data-panel]').forEach(el=>el.hidden=Number(el.dataset.panel)!==n);
    $('#back').hidden=n===0||n===3; $('#next').hidden=n===3;
    $('#next').innerHTML=['Organizza il giro <span aria-hidden="true">→</span>','Verifica il percorso <span aria-hidden="true">→</span>','Pianifica il giro · demo <span aria-hidden="true">✓</span>',''][n];
    text('#help-title',helps[n][0]);text('#help-text',helps[n][1]);text('#progress-label',`Passaggio ${n+1} di 4`);$('#progress').value=n+1;
    updateSteps();update();message('');
    $('#title-'+n).focus({preventScroll:true});$('.steps').scrollIntoView({block:'start',behavior:'instant'});
  }
  function validStops() {
    if(!selected.size){message('Seleziona almeno una consegna per continuare.');return false;}
    const invalid=$$('[data-edit]').find(input=>selected.has(Number(input.dataset.id))&&!input.checkValidity());
    if(invalid){$('#search').value='';$('#search').dispatchEvent(new Event('input'));const editor=invalid.closest('.stop-editor');editor.hidden=false;$(`[aria-controls="${editor.id}"]`).setAttribute('aria-expanded','true');invalid.reportValidity();message('Controlla le quantità e i tempi della consegna evidenziata.');return false;}
    return true;
  }
  function validConfiguration() {
    const invalid=[...$('#configuration').elements].find(el=>el.willValidate&&!el.checkValidity());
    if(invalid){const options=invalid.closest('details');if(options)options.open=true;invalid.reportValidity();message('Completa i campi evidenziati prima di proseguire.');return false;}
    if(value('shift')<=value('time')){$('.options').open=true;$('#shift').focus();message('La fine turno deve essere successiva alla partenza.');return false;}
    const capacity=(value('vehicle')==='van'?1500:1200)+(isFleet()?1500:0);
    if(chosen().reduce((sum,s)=>sum+s.weight,0)>capacity){message(`Il peso selezionato supera la portata di ${format(capacity)} kg. Scegli più mezzi o modifica il carico.`);return false;}
    return true;
  }
  function review() {
    text('#review-date',dateLabel()+' · '+value('time'));text('#review-depot',value('depot'));
    text('#review-driver',value('driver')+(isFleet()?' + Luca Conti':''));
    text('#review-vehicle',$('#vehicle').selectedOptions[0].textContent+(isFleet()?' + Van 04':''));
    text('[data-depot]',value('depot'));$('#route-end').hidden=value('return')==='no';
    $('#review-stops').innerHTML=chosen().map(s=>`<li><div><strong>${esc(s.name)}</strong><small>${esc(s.address)}</small></div><span>${format(s.packages)} colli · ${format(s.weight)} kg<br>${esc(s.window)} · scarico ${s.unload} min</span></li>`).join('');
  }
  renderStops();update();updateSteps();
  $('#configuration').addEventListener('submit',e=>e.preventDefault());
  $('#configuration').addEventListener('input',invalidate);
  $('#configuration').addEventListener('change',invalidate);
  $('#stops').addEventListener('click',e=>{const btn=e.target.closest('[data-detail]');if(!btn)return;const editor=$('#editor-'+btn.dataset.detail);editor.hidden=!editor.hidden;btn.setAttribute('aria-expanded',String(!editor.hidden));});
  $('#stops').addEventListener('change',e=>{if(!e.target.matches('[data-select]'))return;const id=Number(e.target.dataset.select);if(e.target.checked)selected.add(id);else selected.delete(id);invalidate();});
  $('#stops').addEventListener('input',e=>{
    const input=e.target;if(!input.matches('[data-edit]'))return;
    invalidate();if(!input.checkValidity())return;
    const s=stops.find(s=>s.id===Number(input.dataset.id));s[input.dataset.edit]=input.dataset.edit==='window'?input.value:Number(input.value);
    text(`[data-row-packages="${s.id}"]`,format(s.packages));text(`[data-row-weight="${s.id}"]`,format(s.weight));
    // Keep the collapsed row consistent with the edited delivery window.
    $(`[data-row="${s.id}"] .stop-quantity small`).innerHTML=`<span data-row-weight="${s.id}">${format(s.weight)}</span> kg · ${esc(s.window)}`;
    update();
  });
  $('#select-all').addEventListener('change',e=>{stops.forEach(s=>{if(e.target.checked)selected.add(s.id);else selected.delete(s.id);$(`[data-select="${s.id}"]`).checked=e.target.checked;});invalidate();});
  $('#search').addEventListener('input',e=>{const q=e.target.value.toLocaleLowerCase('it-IT').trim();let visible=0;stops.forEach(s=>{const match=(s.name+' '+s.address).toLocaleLowerCase('it-IT').includes(q);$(`[data-row="${s.id}"]`).hidden=!match;if(match)visible++;});$('#empty-search').hidden=!!visible;});
  $('#confirm-review').addEventListener('change',update);
  $('#next').addEventListener('click',()=>{
    if(stage===0){if(!validStops())return;reached=Math.max(reached,1);show(1);}
    else if(stage===1){if(!validConfiguration())return;review();reached=2;show(2);}
    else if(stage===2&&$('#confirm-review').checked){completed=true;reached=3;text('#finish-name',value('name').trim()||'Il tuo nuovo giro');text('#finish-date',dateLabel()+' · '+value('time'));show(3);}
  });
  $('#back').addEventListener('click',()=>show(Math.max(0,stage-1)));
  $$('[data-step]').forEach(btn=>btn.addEventListener('click',()=>{
    const target=Number(btn.dataset.step);
    if(stage===0&&target>0&&!validStops())return;
    show(target);
  }));
  $$('[data-go]').forEach(btn=>btn.addEventListener('click',()=>show(Number(btn.dataset.go))));
  $('#edit-again').addEventListener('click',()=>{invalidate();show(1);});
  // The shell is decorative in this offline prototype; prevent navigation to real app routes.
  document.addEventListener('click',e=>{const nav=e.target.closest('[data-gf-shell] a');if(nav){e.preventDefault();message('La navigazione del gestionale è illustrativa. Prova i quattro passaggi della pianificazione.');}});
})();
