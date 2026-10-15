window.GFFleetReview=(()=>{
'use strict';
let map=null,epoch=0,drag=null,dialog=null;
const palette=['#1F5BFF','#0B8A7C','#7B4FE0','#B7791F','#B73863','#1983A7','#487B4E','#8359A4','#C45D32','#3A7796'];
const color=i=>palette[i%palette.length];
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>x==null?'—':'€ '+Number(x).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
const count=(a,i)=>a.filter(v=>v===i).length;
const site=()=>document.getElementById('routePreviewResult');
const oldRoute=(plan,index)=>plan.routes.find(r=>r.stop_indexes.includes(index));
const ordered=(plan,assignment,lane)=>{
 const old=plan.routes.find(r=>r.resource===lane)?.stop_indexes||[];
 const list=old.filter(i=>assignment[i]===lane);
 assignment.forEach((v,i)=>{if(v===lane&&!list.includes(i))list.push(i);});
 return list;
};
const names=(plan,i)=>{
 const r=plan.routes.find(r=>r.resource===i),c=plan.configuration.resources[i];
 const cars=typeof resourcesAvailabilityCache==='undefined'?[]:resourcesAvailabilityCache.vehicles||[];
 const drivers=typeof resourcesAvailabilityCache==='undefined'?[]:resourcesAvailabilityCache.drivers||[];
 const v=cars.find(v=>Number(v.id)===Number(c.vehicle_id));
 const d=drivers.find(v=>Number(v.id)===Number(c.driver_id));
 return {driver:r?.driver_name||d?.full_name||[d?.nome,d?.cognome].filter(Boolean).join(' ')||'Autista '+(i+1),
 vehicle:r?.vehicle_name||v?.nome||'Mezzo '+(i+1),plate:v?.targa||'',r};
};
const initials=x=>String(x).split(/\s+/).slice(0,2).map(t=>t.charAt(0).toUpperCase()).join('');
function totals(plan,assignment,dirty){
 const used=plan.configuration.resources.filter((_,i)=>assignment.includes(i)).length;
 const km=plan.routes.reduce((x,r)=>x+Number(r.result.total_km||0),0);
 const cost=plan.routes.reduce((x,r)=>x+Number(r.fuel_cost||0),0);
 const ends=plan.routes.map(r=>r.result.return_time).filter(Boolean).sort();
 const stat=(label,value,sub,warning=false)=>'<div class="gf-stat-strip__cell"><span class="gf-stat-strip__label">'+esc(label)+'</span><strong class="gf-stat-strip__value">'+esc(value)+'</strong><small class="gf-stat-strip__unit">'+(warning?'<span class="gf-badge" data-status="warning">'+esc(sub)+'</span>':esc(sub))+'</small></div>';
 return '<section class="gf-stat-strip" aria-label="Totali della suddivisione">'+
 stat('Consegne',String(assignment.filter(x=>x!=null).length),'Assegnate a '+used+' mezzi')+
 stat('Km totali',dirty?'—':km.toLocaleString('it-IT',{maximumFractionDigits:1})+' km',dirty?'Da ricalcolare':'Somma dei percorsi',dirty)+
 stat('Carburante / energia',dirty?'—':money(cost),dirty?'Da ricalcolare':'Costo stimato',dirty)+
 stat('Ultimo rientro',dirty?'—':ends.at(-1)||'—',dirty?'Da ricalcolare':'Orario previsto',dirty)+'</section>';
}
function checks(plan,assignment,dirty){
 const missing=assignment.filter(x=>x==null).length;
 const numbers=plan.configuration.resources.map((_,i)=>count(assignment,i));
 const warn=plan.warnings?.find(w=>/approssimativ|routing stradale non disponibile/i.test(w));
 const mark=bad=>'<svg class="gf-alert__icon" viewBox="0 0 24 24" aria-hidden="true">'+(bad?'<path d="M12 3 2 21h20L12 3z M12 9v5m0 4h.01"/>':'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 6-6"/>')+'</svg>';
 const check=(title,desc,bad=false)=>'<div role="listitem" class="gf-alert" data-status="'+(bad?'warning':'success')+'">'+mark(bad)+'<div class="gf-alert__body"><p class="gf-alert__title">'+esc(title)+'</p><p>'+esc(desc)+'</p></div></div>';
 return (dirty?check('Ricalcolo necessario','Distanze, orari e costi precedenti non sono più validi.',true):'')+
 check(missing?missing+' consegne non assegnate':'Tutte le consegne assegnate',
 missing?'Assegna le consegne oppure conferma esplicitamente le esclusioni.':'Ogni fermata è assegnata a un mezzo.',!!missing)+
 check('Distribuzione tra i mezzi','Da '+Math.min(...numbers)+' a '+Math.max(...numbers)+' fermate per mezzo.',Math.max(...numbers)-Math.min(...numbers)>=5)+
 check('Verifica dei vincoli','Il motore controlla peso, colli, fasce orarie, attrezzature, durata, turni e pause degli autisti.')+
 (warn?check('Tratte da verificare','Alcune distanze possono essere approssimative.',true):'');
}
function stop(plan,assignment,dirty,index,lane){
 const delivery=plan.configuration.consegne[index],original=oldRoute(plan,index);
 const moved=original?.resource!==lane,timing=(!dirty&&!moved)?original?.result?.ordered?.[original.stop_indexes.indexOf(index)]:null;
 const move=plan.status==='preview'?'<select class="gf-select" data-fleet-move="'+index+'" aria-label="Sposta '+esc(delivery.cliente_nome)+'"><option value="">Sposta</option>'+
 plan.configuration.resources.map((_,i)=>i===lane?'':'<option value="'+i+'">Mezzo '+(i+1)+'</option>').join('')+'</select>':'';
 return '<li class="gf-stop'+(moved?' is-next':'')+'" data-fleet-stop="'+index+'" draggable="'+(plan.status==='preview')+'">'+
 '<span class="gf-stop__number">'+(ordered(plan,assignment,lane).indexOf(index)+1)+'</span>'+
 '<span class="gf-stop__main"><span class="gf-stop__name">'+esc(delivery.cliente_nome)+'</span><span class="gf-stop__meta">'+esc(delivery.indirizzo)+'</span>'+move+'</span>'+
 '<span class="gf-stop__time">'+esc(timing?.arrivo_stimato||'—')+'<br><small class="gf-muted">'+(dirty?'Da ricalcolare':'Arrivo previsto')+'</small></span></li>';
}
function lane(plan,assignment,dirty,i){
 const all=ordered(plan,assignment,i),info=names(plan,i),route=info.r;
 const invalid=dirty && (!route||route.stop_indexes.length!==all.length||all.some(k=>!route.stop_indexes.includes(k)));
 const max=plan.configuration.resources[i].max_minutes||480;
 const duration=!invalid&&route?Number(route.result.total_min):0;
 const width=invalid?0:Math.max(0,Math.min(100,Math.round(duration/max*20)*5));
 const head='<header class="gf-panel__header"><span class="gf-avatar" aria-hidden="true">'+esc(initials(info.driver))+'</span><div><h3 class="gf-panel__title">'+esc(info.driver)+'</h3><p class="gf-muted">Mezzo '+(i+1)+' · '+esc(info.vehicle)+' '+esc(info.plate)+'</p></div>'+
 (invalid?'<span class="gf-badge" data-status="warning">Da ricalcolare</span>':'')+'</header>';
 const stats='<div class="gf-panel__body gf-stack"><dl class="gf-details"><div class="gf-details__item"><dt>Consegne</dt><dd><strong>'+all.length+'</strong> fermate</dd></div>'+
 '<div class="gf-details__item"><dt>Percorso</dt><dd><strong>'+(!invalid&&route?Number(route.result.total_km).toLocaleString('it-IT',{maximumFractionDigits:1})+' km':'—')+'</strong></dd></div>'+
 '<div class="gf-details__item"><dt>Carburante</dt><dd><strong>'+(!invalid&&route?money(route.fuel_cost):'—')+'</strong></dd></div></dl>';
 const dur='<div class="gf-progress"><div class="gf-progress__top"><span><b>'+(!invalid&&route?Math.round(duration)+' min':'—')+'</b> di giro</span><span>'+(!invalid&&route?'Rientro '+esc(route.result.return_time||'—'):'Massimo '+max+' min')+'</span></div>'+
 '<div class="gf-progress__track" role="img" aria-label="Durata rispetto al massimo"><span class="gf-progress__done" data-gf-width="'+width+'"></span></div></div></div>';
 return '<section class="gf-panel" aria-label="Mezzo '+(i+1)+'">'+head+stats+dur+
 '<ol class="gf-stop-list" data-fleet-lane="'+i+'">'+
 (!dirty&&route?GFDriverBreaks.cards(route.result,0,'li'):'')+(all.length?all.map((k,position)=>stop(plan,assignment,dirty,k,i)+(!dirty&&route?GFDriverBreaks.cards(route.result,position+1,'li'):'')).join(''):'<li class="gf-empty"><p>Nessuna consegna</p><small>Trascina qui una consegna da un altro mezzo.</small></li>')+'</ol>'+
 (plan.status==='programmed'&&route&&plan.route_ids?.[plan.routes.indexOf(route)]
  ?'<footer class="gf-panel__footer"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-open="'+Number(plan.route_ids[plan.routes.indexOf(route)])+'">Apri giro programmato</button></footer>':'')+'</section>';
}
function stopMap(){epoch++;if(map){map.remove();map=null;}}
function highlight(index,on){site()?.querySelectorAll('[data-fleet-stop="'+index+'"],[data-fleet-pin="'+index+'"]').forEach(x=>x.classList.toggle(x.matches('[data-fleet-stop]')?'is-highlighted':'hl',on));}
async function drawMap(plan,assignment){
 const token=epoch,host=site()?.querySelector('[data-fleet-map]');if(!host)return;
 const known=new Map();
 plan.routes.forEach(r=>(r.stop_indexes||[]).forEach((index,j)=>{
  const item=r.result?.ordered?.[j]||{};
  const coord=item.coord||item;
  if(coord?.lat!=null&&coord?.lon!=null)known.set(index,[Number(coord.lat),Number(coord.lon)]);
 }));
 const coords=plan.configuration.consegne.map((d,i)=>known.get(i)||
  (d.lat==null||d.lon==null?null:[Number(d.lat),Number(d.lon)]))
  .map(p=>p&&p.every(Number.isFinite)&&Math.abs(p[0])<=90&&Math.abs(p[1])<=180?p:null);
 if(!coords.some(Boolean)){host.textContent='Coordinate delle fermate non disponibili.';return;}
 try{
  await loadRoadMapLibrary();if(token!==epoch||!host.isConnected)return;
  map=L.map(host,{scrollWheelZoom:false});map.attributionControl.setPrefix('');
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);
  const bounds=L.latLngBounds(coords.filter(Boolean));
  plan.configuration.resources.forEach((_,lane)=>{
   const positions=ordered(plan,assignment,lane),path=positions.map(i=>coords[i]).filter(Boolean);
   if(path.length>1)L.polyline(path,{color:color(lane),weight:2.4,opacity:.65,dashArray:'3 8'}).addTo(map);
   positions.forEach((i,j)=>{
    if(!coords[i])return;
    const pin=L.marker(coords[i],{icon:L.divIcon({className:'fleet-review-pin-icon',html:'<span class="fleet-review-pin" style="--lane:'+color(lane)+'" data-fleet-pin="'+i+'">'+(j+1)+'</span>',iconSize:[30,30],iconAnchor:[15,15]})}).addTo(map);
    const pop=document.createElement('div'),a=document.createElement('strong'),b=document.createElement('div');
    a.textContent=plan.configuration.consegne[i].cliente_nome;b.textContent=plan.configuration.consegne[i].indirizzo;pop.append(a,b);pin.bindPopup(pop);
    pin.on('mouseover',()=>highlight(i,true));pin.on('mouseout',()=>highlight(i,false));
   });
  });
  const depot=plan.routes.find(r=>r.result?.depot_coord)?.result?.depot_coord;
  if(depot?.lat!=null&&depot?.lon!=null){const d=[Number(depot.lat),Number(depot.lon)];bounds.extend(d);
   L.marker(d,{icon:L.divIcon({className:'fleet-review-pin-icon',html:'<span class="fleet-review-pin depot">D</span>',iconSize:[30,30],iconAnchor:[15,15]})}).addTo(map);}
  map.fitBounds(bounds,{padding:[22,22],maxZoom:12,animate:false});requestAnimationFrame(()=>map?.invalidateSize());
  setTimeout(()=>{if(token===epoch)map?.invalidateSize();},400);
 }catch(err){if(token!==epoch)return;host.textContent='Mappa temporaneamente non disponibile.';console.warn(err);}
}
function warning(onConfirm){
 if(dialog){dialog.remove();dialog=null;}
 const next=document.createElement('dialog');dialog=next;next.className='gf-modal';next.setAttribute('aria-labelledby','fleetWarningTitle');
 next.innerHTML='<header class="gf-modal__header"><div><h2 class="gf-modal__title" id="fleetWarningTitle">Attenzione alla modifica manuale</h2></div></header>'+
 '<div class="gf-modal__body gf-stack"><div class="gf-alert" data-status="warning"><div class="gf-alert__body"><p>Cambiando la suddivisione fra i mezzi, GiroFacile non può garantire la combinazione più efficiente tra tutte le fermate.</p></div></div>'+
 '<p>Il ricalcolo aggiornerà sequenza, distanze, tempi e costi, verificando i vincoli prima della pianificazione.</p></div>'+
 '<footer class="gf-modal__footer"><button type="button" class="gf-button" data-variant="secondary" data-cancel>Annulla</button><button type="button" class="gf-button" data-variant="primary" data-accept>Sposta comunque</button></footer>';
 document.body.appendChild(next);next.showModal();
 const close=()=>{if(dialog===next)dialog=null;next.remove();};
 next.querySelector('[data-cancel]').onclick=close;
 next.querySelector('[data-accept]').onclick=()=>{close();onConfirm();};
 next.addEventListener('close',close,{once:true});
}
function render({plan,assignment,dirty,busy,manualAdjusted,permission,onMove,onUndo,onRecalc,onPlan,onBack}){
 stopMap();if(dialog){dialog.remove();dialog=null;}
 const target=site();if(!target)return;
 const planned=plan.status==='programmed',saved=plan.status==='saved',missing=assignment.filter(v=>v==null).length,rows=plan.configuration.resources.length;
 const alert=dirty?'Hai modificato la distribuzione. Le stime precedenti non sono valide: ricalcola prima di pianificare.':
 manualAdjusted?'Suddivisione personalizzata: GiroFacile ottimizza le fermate all’interno dei mezzi scelti, ma non garantisce la migliore combinazione globale.':'';
 // Classe di ambito per i segnaposto della mappa (ancora sul vecchio foglio, in attesa di un componente mappa).
 target.classList.add('fleet-review-page');
 target.innerHTML='<section class="gf-stack" data-gap="lg" data-fleet-review>'+
 '<div class="gf-cluster" data-justify="between"><div><p class="gf-muted">Pianificazione <span aria-hidden="true">›</span> Controlla la suddivisione</p>'+
 '<h1 class="gf-title">Controlla la suddivisione</h1><p class="gf-muted">Verifica le consegne distribuite fra i mezzi. Puoi spostarle prima di pianificare i giri.</p></div>'+
 '<div class="gf-cluster"><button type="button" class="gf-button" data-variant="secondary" data-fleet-back>← Torna alla pianificazione</button>'+
 (planned?'<span class="gf-badge" data-status="success">Giri programmati</span>':'<button type="button" class="gf-button" data-variant="primary" data-fleet-plan '+(busy||dirty||!permission?'disabled':'')+'>Pianifica giri</button>')+'</div></div>'+
 (alert?'<div class="gf-alert" data-status="warning" role="status"><div class="gf-alert__body"><strong class="gf-alert__title">'+(dirty?'Ricalcolo necessario':'Suddivisione manuale')+'</strong><p>'+esc(alert)+'</p></div></div>':'')+
 (saved?'<div class="gf-alert" data-status="warning" role="status"><div class="gf-alert__body"><strong class="gf-alert__title">Giri in bozza, programmazione non completata</strong><p>Puoi riprovare con “Pianifica giri”. Non verranno duplicati giri.</p></div></div>':'')+
 totals(plan,assignment,dirty)+
 '<div class="gf-grid" data-cols="main-side"><section class="gf-panel"><header class="gf-panel__header"><div><h2 class="gf-panel__title">Distribuzione sulla mappa</h2><p class="gf-muted">Ogni colore è un mezzo. Passa su una fermata per individuarla.</p></div></header>'+
 '<div class="gf-panel__body gf-stack"><div class="gf-route-panel__canvas" data-fleet-map role="region" aria-label="Fermate della suddivisione sulla mappa"></div>'+
 '<div class="gf-legend">'+plan.configuration.resources.map((_,i)=>'<span><i style="background:'+color(i)+';border-color:'+color(i)+'"></i>Mezzo '+(i+1)+'</span>').join('')+
 '<span><i data-state="done"></i>Deposito</span><span><i></i>Collegamenti indicativi, non stradali</span></div></div></section>'+
 '<section class="gf-panel"><header class="gf-panel__header"><h2 class="gf-panel__title">Controlli sulla suddivisione</h2></header><div class="gf-panel__body gf-stack"><div class="gf-stack" data-gap="sm" role="list">'+checks(plan,assignment,dirty)+'</div>'+
 '<details class="gf-panel"><summary class="gf-panel__header">Come leggere le stime</summary><div class="gf-panel__body gf-stack"><p>Traffico e pedaggi saranno verificati alla programmazione. Il costo mostrato riguarda solo carburante ed energia.</p>'+
 '<p>I controlli automatici considerano peso e colli. Verifica separatamente volume, pallet e altri requisiti.</p></div></details></div></section></div>'+
 '<div><h2 class="gf-subtitle">Suddivisione per mezzo</h2><p class="gf-muted">Trascina una consegna su un altro mezzo oppure utilizza il selettore Sposta.</p></div>'+
 '<div class="gf-grid" data-cols="2">'+plan.configuration.resources.map((_,i)=>lane(plan,assignment,dirty,i)).join('')+'</div>'+
 (missing?'<section class="gf-panel"><header class="gf-panel__header"><div><h2 class="gf-panel__title">Consegne non assegnate ('+missing+')</h2><p class="gf-muted">Verifica prima di pianificare.</p></div></header><div class="gf-panel__body gf-stack">'+
 '<div class="gf-stack" data-gap="sm" role="list">'+assignment.map((v,i)=>v==null?'<div role="listitem" class="gf-cluster" data-justify="between"><span>'+esc(plan.configuration.consegne[i]?.cliente_nome||'Consegna')+'</span>'+
 (plan.status==='preview'?'<select class="gf-select" data-fleet-move="'+i+'" aria-label="Assegna '+esc(plan.configuration.consegne[i]?.cliente_nome||'Consegna')+'"><option value="">Assegna a mezzo</option>'+
 plan.configuration.resources.map((_,j)=>'<option value="'+j+'">Mezzo '+(j+1)+'</option>').join('')+'</select>':'')+'</div>':'').join('')+'</div>'+
 (plan.status==='preview'?'<label class="gf-check"><input type="checkbox" data-fleet-accept-unassigned> <span>Confermo che queste consegne rimangano non assegnate</span></label>':'')+'</div></section>':'')+
 (plan.warnings?.length?'<details class="gf-panel"><summary class="gf-panel__header">Note sul calcolo</summary><div class="gf-panel__body gf-stack">'+plan.warnings.map(w=>'<p>'+esc(w)+'</p>').join('')+'</div></details>':'')+
 '<div id="fleetMessage" role="status" tabindex="-1" class="gf-muted"></div>'+
 (dirty?'<div class="gf-savebar" role="region" aria-label="Modifiche in sospeso"><span><b>Assegnazioni modificate</b> · Ricalcola per aggiornare tempi e distanze.</span>'+
 '<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-fleet-undo>Annulla modifiche</button><button type="button" class="gf-button" data-variant="primary" data-size="sm" data-fleet-recalc '+(busy?'disabled':'')+'>Ricalcola assegnazioni</button></div>':'')+
 '</section>';
 target.querySelector('[data-fleet-back]')?.addEventListener('click',onBack);
 target.querySelector('[data-fleet-plan]')?.addEventListener('click',()=>onPlan(!!target.querySelector('[data-fleet-accept-unassigned]')?.checked));
 target.querySelector('[data-fleet-undo]')?.addEventListener('click',onUndo);
 target.querySelector('[data-fleet-recalc]')?.addEventListener('click',onRecalc);
 const move=(index,to)=>{
  if(!Number.isInteger(index)||to===assignment[index]||to<0||to>=rows)return;
  onMove(index,to);
 };
 target.querySelectorAll('[data-fleet-move]').forEach(select=>select.addEventListener('change',()=>{
  const i=Number(select.dataset.fleetMove),to=Number(select.value);select.value='';move(i,to);
 }));
 target.querySelectorAll('[data-fleet-stop]').forEach(stop=>{
  stop.addEventListener('dragstart',e=>{if(plan.status!=='preview'||busy){e.preventDefault();return;}drag=Number(stop.dataset.fleetStop);e.dataTransfer.setData('text/plain',String(drag));e.dataTransfer.effectAllowed='move';stop.classList.add('dragging');});
  stop.addEventListener('dragend',()=>{drag=null;target.querySelectorAll('.dragging,.over').forEach(el=>el.classList.remove('dragging','over'));});
  stop.addEventListener('mouseenter',()=>highlight(stop.dataset.fleetStop,true));stop.addEventListener('mouseleave',()=>highlight(stop.dataset.fleetStop,false));
 });
 target.querySelectorAll('[data-fleet-lane]').forEach(el=>{
  el.addEventListener('dragover',e=>{if(drag==null)return;e.preventDefault();el.classList.add('over');});
  el.addEventListener('dragleave',e=>{if(!el.contains(e.relatedTarget))el.classList.remove('over');});
  el.addEventListener('drop',e=>{e.preventDefault();el.classList.remove('over');if(drag!=null){const i=drag;drag=null;move(i,Number(el.dataset.fleetLane));}});
 });
 drawMap(plan,assignment);
}
return {render,warning,stopMap};
})();
