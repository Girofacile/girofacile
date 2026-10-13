window.GFFleetReview=(()=>{
'use strict';
let map=null,epoch=0,drag=null,dialog=null;
const palette=['#1F5BFF','#0B8A7C','#7B4FE0','#B7791F','#B73863','#1983A7','#487B4E','#8359A4','#C45D32','#3A7796'];
const color=i=>palette[i%palette.length];
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>x==null?'—':'€ '+Number(x).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
const count=(a,i)=>a.filter(v=>v===i).length;
const site=()=>document.getElementById('routePreviewResult');
const icon=(shape)=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(shape==='alert'?'<path d="M12 3 2 21h20L12 3z M12 9v5m0 4h.01"/>':shape==='check'?'<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 6-6"/>':'<circle cx="9" cy="5" r="1"/><circle cx="15" cy="5" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="19" r="1"/><circle cx="15" cy="19" r="1"/>')+'</svg>';
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
 const stat=(label,value,sub,warning=false)=>'<div><dt>'+esc(label)+'</dt><dd>'+esc(value)+'</dd><small class="'+(warning?'stale':'')+'">'+esc(sub)+'</small></div>';
 return '<section class="fleet-review-panel fleet-review-totals"><dl>'+
 stat('Consegne',String(assignment.filter(x=>x!=null).length),'Assegnate a '+used+' mezzi')+
 stat('Km totali',dirty?'—':km.toLocaleString('it-IT',{maximumFractionDigits:1})+' km',dirty?'Da ricalcolare':'Somma dei percorsi',dirty)+
 stat('Carburante / energia',dirty?'—':money(cost),dirty?'Da ricalcolare':'Costo stimato',dirty)+
 stat('Ultimo rientro',dirty?'—':ends.at(-1)||'—',dirty?'Da ricalcolare':'Orario previsto',dirty)+'</dl></section>';
}
function checks(plan,assignment,dirty){
 const missing=assignment.filter(x=>x==null).length;
 const numbers=plan.configuration.resources.map((_,i)=>count(assignment,i));
 const warn=plan.warnings?.find(w=>/approssimativ|routing stradale non disponibile/i.test(w));
 const check=(title,desc,bad=false)=>'<li><span class="fleet-review-check '+(bad?'warn':'ok')+'">'+icon(bad?'alert':'check')+'</span><span><b>'+esc(title)+'</b><small>'+esc(desc)+'</small></span></li>';
 return (dirty?check('Ricalcolo necessario','Distanze, orari e costi precedenti non sono più validi.',true):'')+
 check(missing?missing+' consegne non assegnate':'Tutte le consegne assegnate',
 missing?'Assegna le consegne oppure conferma esplicitamente le esclusioni.':'Ogni fermata è assegnata a un mezzo.',!!missing)+
 check('Distribuzione tra i mezzi','Da '+Math.min(...numbers)+' a '+Math.max(...numbers)+' fermate per mezzo.',Math.max(...numbers)-Math.min(...numbers)>=5)+
 check('Verifica dei vincoli','Il motore controlla peso, colli, fasce orarie, attrezzature e durata.')+
 (warn?check('Tratte da verificare','Alcune distanze possono essere approssimative.',true):'');
}
function stop(plan,assignment,dirty,index,lane){
 const delivery=plan.configuration.consegne[index],original=oldRoute(plan,index);
 const moved=original?.resource!==lane,timing=(!dirty&&!moved)?original?.result?.ordered?.[original.stop_indexes.indexOf(index)]:null;
 const move=plan.status==='preview'?'<label><span class="sr-only">Sposta consegna</span><select class="fleet-review-move" data-fleet-move="'+index+'" aria-label="Sposta '+esc(delivery.cliente_nome)+'"><option value="">Sposta</option>'+
 plan.configuration.resources.map((_,i)=>i===lane?'':'<option value="'+i+'">Mezzo '+(i+1)+'</option>').join('')+'</select></label>':'';
 return '<li class="fleet-review-stop'+(moved?' moved':'')+'" data-fleet-stop="'+index+'" draggable="'+(plan.status==='preview')+'">'+
 '<span class="fleet-review-grip">'+icon('grip')+'</span><span class="fleet-review-no">'+(ordered(plan,assignment,lane).indexOf(index)+1)+'</span>'+
 '<span class="fleet-review-customer"><b>'+esc(delivery.cliente_nome)+'</b><small>'+esc(delivery.indirizzo)+'</small></span>'+
 '<span class="fleet-review-time"><b>'+esc(timing?.arrivo_stimato||'—')+'</b><small>'+(dirty?'Da ricalcolare':'Arrivo previsto')+'</small></span>'+move+'</li>';
}
function lane(plan,assignment,dirty,i){
 const all=ordered(plan,assignment,i),info=names(plan,i),route=info.r;
 const invalid=dirty && (!route||route.stop_indexes.length!==all.length||all.some(k=>!route.stop_indexes.includes(k)));
 const max=plan.configuration.resources[i].max_minutes||480;
 const duration=!invalid&&route?Number(route.result.total_min):0;
 const section='<div class="fleet-review-lane-head"><span class="fleet-review-avatar">'+esc(initials(info.driver))+'</span><span><b>'+esc(info.driver)+'</b><small>Mezzo '+(i+1)+' · '+esc(info.vehicle)+' '+esc(info.plate)+'</small></span>'+
 (invalid?'<em>Da ricalcolare</em>':'')+'</div>';
 const stats='<div class="fleet-review-lane-stats"><div><small>Consegne</small><b>'+all.length+'</b><em>fermate</em></div>'+
 '<div><small>Percorso</small><b>'+(!invalid&&route?Number(route.result.total_km).toLocaleString('it-IT',{maximumFractionDigits:1})+' km':'—')+'</b></div>'+
 '<div><small>Carburante</small><b>'+(!invalid&&route?money(route.fuel_cost):'—')+'</b></div></div>';
 const dur='<div class="fleet-review-duration"><p><b>'+(!invalid&&route?Math.round(duration)+' min':'—')+' di giro</b><small>'+(!invalid&&route?'Rientro '+esc(route.result.return_time||'—'):'Massimo '+max+' min')+'</small></p>'+
 '<span><i style="width:'+(invalid?0:Math.min(100,Math.round(duration/max*100)))+'%"></i></span></div>';
 return '<section class="fleet-review-panel fleet-review-lane" style="--lane:'+color(i)+'" aria-label="Mezzo '+(i+1)+'">'+section+stats+dur+
 '<ol class="fleet-review-lane-list" data-fleet-lane="'+i+'">'+
 (all.length?all.map(k=>stop(plan,assignment,dirty,k,i)).join(''):'<li class="fleet-review-lane-empty">Nessuna consegna<small>Trascina qui una consegna da un altro mezzo.</small></li>')+'</ol>'+
 (plan.status==='programmed'&&route&&plan.route_ids?.[plan.routes.indexOf(route)]
  ?'<div class="fleet-review-lane-footer"><button type="button" data-open="'+Number(plan.route_ids[plan.routes.indexOf(route)])+'">Apri giro programmato</button></div>':'')+'</section>';
}
function stopMap(){epoch++;if(map){map.remove();map=null;}}
function highlight(index,on){site()?.querySelectorAll('[data-fleet-stop="'+index+'"],[data-fleet-pin="'+index+'"]').forEach(x=>x.classList.toggle('hl',on));}
async function drawMap(plan,assignment){
 const token=epoch,host=site()?.querySelector('.fleet-review-map');if(!host)return;
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
 const next=document.createElement('dialog');dialog=next;next.className='fleet-review-warning-dialog';
 next.innerHTML='<div><span class="fleet-review-dialog-icon">'+icon('alert')+'</span><h2>Attenzione alla modifica manuale</h2>'+
 '<p>Cambiando la suddivisione fra i mezzi, GiroFacile non può garantire la combinazione più efficiente tra tutte le fermate.</p>'+
 '<p>Il ricalcolo aggiornerà sequenza, distanze, tempi e costi, verificando i vincoli prima della pianificazione.</p>'+
 '<footer><button type="button" data-cancel>Annulla</button><button type="button" data-accept>Sposta comunque</button></footer></div>';
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
 target.classList.add('fleet-review-page');
 target.innerHTML='<div class="fleet-review-header"><div><p class="fleet-review-breadcrumb">Pianificazione <span>›</span> Controlla la suddivisione</p>'+
 '<h1>Controlla la suddivisione</h1><p>Verifica le consegne distribuite fra i mezzi. Puoi spostarle prima di pianificare i giri.</p></div>'+
 '<div class="fleet-review-header-actions"><button type="button" data-fleet-back>← Torna alla pianificazione</button>'+
 (planned?'<span class="fleet-review-success">Giri programmati</span>':'<button type="button" class="fleet-review-primary" data-fleet-plan '+(busy||dirty||!permission?'disabled':'')+'>Pianifica giri</button>')+'</div></div>'+
 (alert?'<div class="fleet-review-alert" role="status">'+icon('alert')+'<span><b>'+(dirty?'Ricalcolo necessario':'Suddivisione manuale')+'</b><small>'+esc(alert)+'</small></span></div>':'')+
 (saved?'<div class="fleet-review-alert" role="status">'+icon('alert')+'<span><b>Giri in bozza, programmazione non completata</b><small>Puoi riprovare con “Pianifica giri”. Non verranno duplicati giri.</small></span></div>':'')+
 totals(plan,assignment,dirty)+
 '<section class="fleet-review-panel fleet-review-overview"><div class="fleet-review-overview-map"><h2>Distribuzione sulla mappa</h2><p>Ogni colore è un mezzo. Passa su una fermata per individuarla.</p>'+
 '<div class="fleet-review-map-wrap"><div class="fleet-review-map" role="region" aria-label="Fermate della suddivisione sulla mappa"></div></div>'+
 '<div class="fleet-review-legend">'+plan.configuration.resources.map((_,i)=>'<span><i style="background:'+color(i)+'"></i>Mezzo '+(i+1)+'</span>').join('')+
 '<span><i class="depot"></i>Deposito</span><span><i class="line"></i>Collegamenti indicativi, non stradali</span></div></div>'+
 '<div class="fleet-review-overview-checks"><h2>Controlli sulla suddivisione</h2><ul>'+checks(plan,assignment,dirty)+'</ul>'+
 '<details><summary>Come leggere le stime <span>⌄</span></summary><p>Traffico e pedaggi saranno verificati alla programmazione. Il costo mostrato riguarda solo carburante ed energia.</p>'+
 '<p>I controlli automatici considerano peso e colli. Verifica separatamente volume, pallet e altri requisiti.</p></details></div></section>'+
 '<div class="fleet-review-section-title"><h2>Suddivisione per mezzo</h2><p>Trascina una consegna su un altro mezzo oppure utilizza il selettore Sposta.</p></div>'+
 '<div class="fleet-review-lanes">'+plan.configuration.resources.map((_,i)=>lane(plan,assignment,dirty,i)).join('')+'</div>'+
 (missing?'<section class="fleet-review-panel fleet-review-unassigned"><h2>Consegne non assegnate ('+missing+')</h2><p>Verifica prima di pianificare.</p>'+
 '<ul>'+assignment.map((v,i)=>v==null?'<li class="fleet-review-unassigned-row"><span>'+esc(plan.configuration.consegne[i]?.cliente_nome||'Consegna')+'</span>'+
 (plan.status==='preview'?'<label><span class="sr-only">Assegna consegna</span><select class="fleet-review-move" data-fleet-move="'+i+'" aria-label="Assegna '+esc(plan.configuration.consegne[i]?.cliente_nome||'Consegna')+'"><option value="">Assegna a mezzo</option>'+
 plan.configuration.resources.map((_,j)=>'<option value="'+j+'">Mezzo '+(j+1)+'</option>').join('')+'</select></label>':'')+'</li>':'').join('')+'</ul>'+
 (plan.status==='preview'?'<label><input type="checkbox" data-fleet-accept-unassigned> Confermo che queste consegne rimangano non assegnate</label>':'')+'</section>':'')+
 (plan.warnings?.length?'<details class="fleet-review-technical"><summary>Note sul calcolo</summary>'+plan.warnings.map(w=>'<p>'+esc(w)+'</p>').join('')+'</details>':'')+
 '<div id="fleetMessage" role="status" tabindex="-1" class="fleet-review-message"></div>'+
 (dirty?'<div class="fleet-review-changebar" role="region" aria-label="Modifiche in sospeso"><span><b>Assegnazioni modificate</b><small>Ricalcola per aggiornare tempi e distanze.</small></span>'+
 '<button type="button" data-fleet-undo>Annulla modifiche</button><button type="button" class="fleet-review-primary" data-fleet-recalc '+(busy?'disabled':'')+'>Ricalcola assegnazioni</button></div>':'');
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
