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
// Tempi con traffico calcolati in anteprima, quando disponibili; altrimenti la stima stradale.
const withTraffic=r=>r?.traffic?.status==='updated';
const routeMinutes=r=>withTraffic(r)?r.traffic.total_min:r.result.total_min;
const routeReturn=r=>withTraffic(r)&&r.traffic.return_time?r.traffic.return_time:r.result.return_time;
const lateStops=plan=>plan.routes.flatMap(r=>withTraffic(r)?r.traffic.late||[]:[]);
function totals(plan,assignment,dirty){
 const used=plan.configuration.resources.filter((_,i)=>assignment.includes(i)).length;
 const approximate=plan.routes.some(r=>['estimated','mixed'].includes(r.result.base_routing_provider)) || (plan.warnings||[]).some(w=>/routing stradale non disponibile/i.test(w));
 const km=plan.routes.reduce((x,r)=>x+Number(r.result.total_km||0),0);
 const cost=plan.routes.reduce((x,r)=>x+Number(r.fuel_cost||0),0);
 const ends=plan.routes.map(routeReturn).filter(Boolean).sort();
 const traffic=plan.routes.length&&plan.routes.every(withTraffic);
 const stat=(label,value,sub,warning=false)=>'<div class="gf-stat-strip__cell"><span class="gf-stat-strip__label">'+esc(label)+'</span><strong class="gf-stat-strip__value">'+esc(value)+'</strong><small class="gf-stat-strip__unit">'+(warning?'<span class="gf-badge" data-status="warning">'+esc(sub)+'</span>':esc(sub))+'</small></div>';
 return '<section class="gf-stat-strip" aria-label="Totali della suddivisione">'+
 stat('Consegne',String(assignment.length),assignment.filter(x=>x==null).length+' non assegnate · '+gfCount(used,'mezzo','mezzi'),assignment.some(x=>x==null))+
 stat('Km totali',dirty?'—':km.toLocaleString('it-IT',{maximumFractionDigits:1})+' km',dirty?'Da ricalcolare':approximate?'Stima approssimativa':'Somma dei percorsi',dirty||approximate)+
 stat('Carburante / energia',dirty?'—':money(cost),dirty?'Da ricalcolare':'Costo stimato',dirty)+
 stat('Ultimo rientro',dirty?'—':ends.at(-1)||'—',dirty?'Da ricalcolare':traffic?'Con traffico':approximate?'Stima approssimativa':'Stima senza traffico',dirty||(approximate&&!traffic))+'</section>';
}
function stop(plan,assignment,dirty,index,lane){
 const delivery=plan.configuration.consegne[index];
 const moved=oldRoute(plan,index)?.resource!==lane;
 const reason=lane===null?plan.unassigned?.find(row=>row.index===index)?.reason:null;
 const lacksTailLift=lane!==null && delivery.sponda && plan.resource_capabilities?.[lane]?.has_tail_lift===false;
 const tailLiftWarning=lacksTailLift?'<p class="fleet-tail-lift-warning" role="status">Attenzione: questa consegna richiede la sponda, ma questo mezzo non la possiede.</p>':'';
 const lacksZtlAccess=lane!==null && delivery.ztl && plan.resource_capabilities?.[lane]?.has_ztl_access===false;
 const ztlWarning=lacksZtlAccess?'<p class="fleet-ztl-warning" role="status">Attenzione: questa consegna è in ZTL, ma questo mezzo non è abilitato all’accesso.</p>':'';
 const late=!dirty&&lane!==null?lateStops(plan).find(item=>item.stop_index===index):null;
 const lateWarning=late?'<p class="gf-alert" data-status="danger" role="status">Con il traffico lo scarico finisce alle '+esc(late.fine_servizio)+', oltre la fascia '+esc(late.window.start)+'–'+esc(late.window.end)+' ('+esc(late.lateness_min)+' min). Puoi spostarla in un altro giro, allargare la fascia o programmare comunque.</p>':'';
 const handle=plan.status==='preview'?'<button type="button" class="fleet-drag-handle" data-fleet-drag draggable="true" title="Trascina in un altro giro" aria-label="Trascina '+esc(delivery.cliente_nome)+'"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M5 12h14M5 17h14"/></svg></button>':'';
 return '<li class="fleet-delivery'+(moved&&lane!==null?' is-moved':'')+'" data-fleet-stop="'+index+'">'+handle+'<div class="fleet-delivery-content">'+
 '<strong>'+esc(delivery.cliente_nome)+'</strong><span class="gf-muted">'+esc(delivery.indirizzo)+'</span>'+lateWarning+tailLiftWarning+ztlWarning+
 (reason?'<details class="fleet-delivery-reason"><summary>Perché non assegnata?</summary><p>'+esc(reason)+'</p></details>':'')+'</div></li>';
}
function lane(plan,assignment,dirty,i){
 const all=ordered(plan,assignment,i),info=names(plan,i),route=info.r;
 const invalid=dirty;
 const metric=(value,label)=>'<span><strong>'+esc(value)+'</strong> '+label+'</span>';
 return '<section class="gf-panel fleet-lane" data-fleet-lane="'+i+'" aria-label="Giro '+(i+1)+'"><header class="gf-panel__header"><div><p class="gf-kicker">Giro '+(i+1)+'</p><h3 class="gf-panel__title">'+esc(info.driver)+'</h3><p class="gf-muted">'+esc(info.vehicle)+' '+esc(info.plate)+'</p></div><span class="gf-badge" data-status="neutral">'+all.length+(all.length===1?' fermata':' fermate')+'</span></header>'+
 '<div class="fleet-lane-metrics">'+metric(!invalid&&route?Number(route.result.total_km).toLocaleString('it-IT',{maximumFractionDigits:1}):'—','km')+
 metric(!invalid&&route?Math.round(routeMinutes(route)):'—',withTraffic(route)&&!invalid?'min con traffico':'min')+metric(!invalid&&route?money(route.fuel_cost):'—','')+'</div>'+
 (invalid?'<p class="fleet-lane-notice">Stime da ricalcolare</p>':'')+
 '<ol class="fleet-deliveries">'+
 (all.length?all.map(k=>stop(plan,assignment,dirty,k,i)).join(''):'<li class="gf-empty"><p>Nessuna fermata</p><small>Trascina qui una consegna.</small></li>')+'</ol>'+
 (!dirty&&route&&route.result.driver_breaks?.length?'<details class="fleet-lane-breaks"><summary>Turno e pause</summary>'+GFDriverBreaks.cards(route.result,0,'div')+route.stop_indexes.map((_,j)=>GFDriverBreaks.cards(route.result,j+1,'div')).join('')+'</details>':'')+
 (plan.status==='programmed'&&route&&plan.route_ids?.[plan.routes.indexOf(route)]?'<footer class="gf-panel__footer"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-open="'+Number(plan.route_ids[plan.routes.indexOf(route)])+'">Apri giro programmato</button></footer>':'')+'</section>';
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
 (!dirty&&plan.status==='preview'&&lateStops(plan).length?'<div class="gf-alert" data-status="danger" role="status"><div class="gf-alert__body"><strong class="gf-alert__title">Clienti fuori orario con il traffico</strong><p>'+gfCount(lateStops(plan).length,'consegna verrebbe servita','consegne verrebbero servite')+' oltre la fascia oraria. '+(lateStops(plan).length===1?'Puoi spostarla in un altro giro o allargare la sua fascia e ricalcolare':'Puoi spostarle in altri giri o allargare la loro fascia e ricalcolare')+', oppure programmare comunque: i giri verranno salvati con l’avviso.</p></div></div>':'')+
 (saved?'<div class="gf-alert" data-status="warning" role="status"><div class="gf-alert__body"><strong class="gf-alert__title">Giri in bozza, programmazione non completata</strong><p>Puoi riprovare con “Pianifica giri”. Non verranno duplicati giri.</p></div></div>':'')+
 totals(plan,assignment,dirty)+
 '<div class="gf-stack" data-gap="sm"><h2 class="gf-subtitle">Suddivisione per giro</h2><p class="gf-muted">Trascina le fermate tra le colonne usando la maniglia a tre linee. Dopo gli spostamenti, ricalcola tempi e costi.</p></div>'+
 '<div class="fleet-board" aria-label="Giri e fermate">'+plan.configuration.resources.map((_,i)=>lane(plan,assignment,dirty,i)).join('')+
 (missing?'<section class="gf-panel fleet-lane fleet-lane-unassigned" aria-label="Consegne non assegnate"><header class="gf-panel__header"><div><h2 class="gf-panel__title">Non assegnate</h2><p class="gf-muted">'+missing+' fermate da sistemare</p></div></header><ol class="fleet-deliveries">'+assignment.map((v,i)=>v==null?stop(plan,assignment,dirty,i,null):'').join('')+'</ol>'+
 (plan.status==='preview'?'<div class="gf-panel__body"><label class="gf-check"><input type="checkbox" data-fleet-accept-unassigned> <span>Confermo di programmare soltanto le consegne assegnate</span></label></div>':'')+'</section>':'')+'</div>'+
 '<section class="gf-panel"><div class="gf-panel__body"><div class="gf-route-panel__canvas" data-fleet-map role="region" aria-label="Mappa della suddivisione dei giri"></div></div></section>'+
 '<div id="fleetMessage" role="status" tabindex="-1" class="gf-muted"></div>'+
 (dirty?'<div class="gf-savebar" data-floating role="region" aria-label="Modifiche in sospeso"><span><b>Assegnazioni modificate</b> · Ricalcola per aggiornare tempi e distanze.</span>'+
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
 target.querySelectorAll('[data-fleet-stop]').forEach(stop=>{
  stop.addEventListener('dragstart',e=>{if(plan.status!=='preview'||busy||!e.target.closest('[data-fleet-drag]')){e.preventDefault();return;}drag=Number(stop.dataset.fleetStop);e.dataTransfer.setData('text/plain',String(drag));e.dataTransfer.effectAllowed='move';e.dataTransfer.setDragImage(stop,20,20);stop.classList.add('dragging');});
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
