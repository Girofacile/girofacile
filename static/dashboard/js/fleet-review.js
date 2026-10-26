window.GFFleetReview=(()=>{
'use strict';
let map=null,epoch=0,drag=null,dialog=null,selected=0,selectedPlan=null;
// Un colore per giro: gli stessi toni degli avatar di theme.css, in tabella e sulla mappa.
const tone=i=>String(i%6+1);
const color=i=>getComputedStyle(document.body).getPropertyValue('--gf-color-avatar-'+tone(i)).trim()||'#1F5BFF';
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=x=>x==null?'—':'€ '+Number(x).toLocaleString('it-IT',{minimumFractionDigits:2,maximumFractionDigits:2});
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
const duration=min=>{const m=Math.round(Number(min)||0);return m>=60?Math.floor(m/60)+' h '+(m%60?m%60+' min':''):m+' min';};
// Avvisi di una fermata nel giro in cui si trova ora (sponda e ZTL seguono subito il mezzo scelto).
function warnings(plan,dirty,index,lane){
 const delivery=plan.configuration.consegne[index],caps=lane===null?null:plan.resource_capabilities?.[lane];
 return {
  tailLift:lane!==null&&delivery.sponda&&caps?.has_tail_lift===false,
  ztl:lane!==null&&delivery.ztl&&caps?.has_ztl_access===false,
  late:!dirty&&lane!==null?lateStops(plan).find(item=>item.stop_index===index):null
 };
}
const ICONS={box:'M3 7l9-4 9 4-9 4-9-4z M3 7v10l9 4 9-4V7 M12 11v10',road:'M4 20 9 4 M20 20 15 4 M12 6v2 M12 11v2 M12 16v2',
 fuel:'M4 20V5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v15 M3 20h12 M7 8h4 M14 9h3l3 3v6a1.5 1.5 0 0 1-3 0v-3h-3',clock:'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2'};
function totals(plan,assignment,dirty){
 const used=plan.configuration.resources.filter((_,i)=>assignment.includes(i)).length;
 const approximate=plan.routes.some(r=>['estimated','mixed'].includes(r.result.base_routing_provider)) || (plan.warnings||[]).some(w=>/routing stradale non disponibile/i.test(w));
 const km=plan.routes.reduce((x,r)=>x+Number(r.result.total_km||0),0);
 const cost=plan.routes.reduce((x,r)=>x+Number(r.fuel_cost||0),0);
 const ends=plan.routes.map(routeReturn).filter(Boolean).sort();
 const traffic=plan.routes.length&&plan.routes.every(withTraffic);
 const stat=(icon,t,label,value,sub,warning=false)=>'<div class="gf-stat-strip__cell"><span class="gf-stat-strip__icon" data-tone="'+t+'" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="'+ICONS[icon]+'"/></svg></span><span class="gf-stat-strip__label">'+esc(label)+'</span><strong class="gf-stat-strip__value">'+esc(value)+'</strong><small class="gf-stat-strip__unit">'+(warning?'<span class="gf-badge" data-status="warning">'+esc(sub)+'</span>':esc(sub))+'</small></div>';
 return '<section class="gf-stat-strip" data-icons="side" aria-label="Totali della suddivisione">'+
 stat('box','1','Consegne',String(assignment.length),assignment.filter(x=>x==null).length+' non assegnate · '+gfCount(used,'mezzo','mezzi'),assignment.some(x=>x==null))+
 stat('road','2','Km totali',dirty?'—':km.toLocaleString('it-IT',{maximumFractionDigits:1})+' km',dirty?'Da ricalcolare':approximate?'Stima approssimativa':'Somma dei percorsi',dirty||approximate)+
 stat('fuel','3','Carburante / energia',dirty?'—':money(cost),dirty?'Da ricalcolare':'Costo stimato',dirty)+
 stat('clock','neutral','Ultimo rientro',dirty?'—':ends.at(-1)||'—',dirty?'Da ricalcolare':traffic?'Con traffico':approximate?'Stima approssimativa':'Stima senza traffico',dirty||(approximate&&!traffic))+'</section>';
}
function stop(plan,dirty,index,lane,position,busy){
 const delivery=plan.configuration.consegne[index];
 const route=oldRoute(plan,index),moved=route?.resource!==lane;
 const w=warnings(plan,dirty,index,lane);
 const timing=!dirty&&!moved?route?.result?.ordered?.[route.stop_indexes.indexOf(index)]:null;
 const badges=(w.late?'<span class="gf-badge" data-status="danger" data-fleet-warning="late" title="Con il traffico lo scarico finisce alle '+esc(w.late.fine_servizio)+', oltre la fascia '+esc(w.late.window.start)+'–'+esc(w.late.window.end)+'.">Fuori orario · fine '+esc(w.late.fine_servizio)+' (+'+esc(w.late.lateness_min)+' min)</span>':'')+
 (w.tailLift?'<span class="gf-badge" data-kind="tail-lift" data-fleet-warning="tail-lift" title="Questa consegna richiede la sponda, ma questo mezzo non la possiede.">Sponda mancante</span>':'')+
 (w.ztl?'<span class="gf-badge" data-kind="ztl" data-fleet-warning="ztl" title="Questa consegna è in ZTL, ma questo mezzo non è abilitato all’accesso.">ZTL senza permesso</span>':'')+
 (moved&&lane!==null?'<span class="gf-badge" data-status="info">Spostata</span>':'');
 const others=plan.configuration.resources.map((_,i)=>i).filter(i=>i!==lane);
 const moveTo=plan.status==='preview'&&others.length?'<span><select class="gf-select" data-fleet-move-to="'+index+'" aria-label="Sposta '+esc(delivery.cliente_nome)+' in un altro giro"'+(busy?' disabled':'')+'><option value="" selected>Sposta in…</option>'+
 others.map(i=>'<option value="'+i+'">Giro '+(i+1)+' · '+esc(names(plan,i).driver)+'</option>').join('')+'</select></span>':'';
 const handle=plan.status==='preview'?'<button type="button" class="gf-icon-button" data-fleet-drag draggable="true" title="Trascina su un giro della tabella" aria-label="Trascina '+esc(delivery.cliente_nome)+'"><svg class="gf-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M5 12h14M5 17h14"/></svg></button>':'';
 return '<li class="gf-stop" data-fleet-stop="'+index+'"><span class="gf-stop__number">'+(position+1)+'</span><span class="gf-stop__main"><span class="gf-stop__name">'+esc(delivery.cliente_nome)+'</span><span class="gf-stop__meta">'+esc(delivery.indirizzo)+badges+'</span>'+(moveTo||handle?'<span class="gf-cluster">'+moveTo+handle+'</span>':'')+'</span>'+
 '<span class="gf-stop__time">'+esc(timing?.arrivo_stimato||'')+'</span></li>';
}
// Tabella di confronto: una riga per giro, che è anche il punto in cui rilasciare una fermata trascinata.
function table(plan,assignment,dirty){
 return '<section class="gf-panel" aria-labelledby="fleetCompareTitle"><header class="gf-panel__header"><div><h2 class="gf-panel__title" id="fleetCompareTitle">Confronto dei giri</h2><p class="gf-muted">Scegli un giro per vederlo sulla mappa. Per spostare una fermata usa «Sposta in…» oppure trascinala sulla riga di un altro giro.</p></div></header>'+
 '<div class="gf-table-wrap"><table class="gf-table"><thead><tr><th>Giro</th><th>Fermate</th><th>Km</th><th>Costo</th><th>Rientro</th><th>Avvisi</th><th><span class="gf-hidden">Azione</span></th></tr></thead><tbody>'+
 plan.configuration.resources.map((_,i)=>{
  const info=names(plan,i),route=info.r,stops=ordered(plan,assignment,i);
  const alerts=stops.filter(k=>{const w=warnings(plan,dirty,k,i);return w.tailLift||w.ztl||w.late;}).length;
  const valid=!dirty&&route;
  return '<tr data-fleet-lane="'+i+'"><td><div class="gf-cluster"><span class="gf-avatar" data-tone="'+tone(i)+'" aria-hidden="true">'+esc(initials(info.driver))+'</span><div><strong>Giro '+(i+1)+' · '+esc(info.driver)+'</strong><br><span class="gf-muted">'+esc([info.vehicle,info.plate].filter(Boolean).join(' · '))+'</span></div></div></td>'+
  '<td>'+stops.length+'</td><td>'+(valid?Number(route.result.total_km).toLocaleString('it-IT',{maximumFractionDigits:1}):'—')+'</td><td>'+(valid?money(route.fuel_cost):'—')+'</td><td>'+esc(valid?routeReturn(route)||'—':'—')+'</td>'+
  '<td>'+(alerts?'<span class="gf-badge" data-status="warning" data-dot>'+alerts+'</span>':'<span class="gf-badge" data-status="success" data-dot>0</span>')+'</td>'+
  '<td><button type="button" class="gf-button" data-variant="ghost" data-size="sm" data-fleet-select="'+i+'" aria-pressed="'+(i===selected)+'">Vedi</button></td></tr>';
 }).join('')+'</tbody></table></div></section>';
}
// Il giro scelto: mappa e fermate in ordine, con gli avvisi del mezzo come etichette.
function lane(plan,assignment,dirty,i,busy){
 const all=ordered(plan,assignment,i),info=names(plan,i),route=info.r,valid=!dirty&&route;
 const metrics=valid?[Number(route.result.total_km).toLocaleString('it-IT',{maximumFractionDigits:1})+' km',duration(routeMinutes(route))+(withTraffic(route)?' con traffico':''),money(route.fuel_cost),'rientro '+(routeReturn(route)||'—')].join(' · '):'Stime da ricalcolare';
 const routeId=plan.status==='programmed'&&route?plan.route_ids?.[plan.routes.indexOf(route)]:null;
 return '<section class="gf-panel" data-fleet-lane="'+i+'" aria-labelledby="fleetLaneTitle"><header class="gf-panel__header"><div><h2 class="gf-panel__title" id="fleetLaneTitle">Giro '+(i+1)+' · '+esc(info.driver)+'</h2><p class="gf-muted">'+esc([info.vehicle,info.plate].filter(Boolean).join(' · '))+' · '+esc(metrics)+'</p></div><span class="gf-badge" data-status="info" data-dot>'+gfCount(all.length,'fermata','fermate')+'</span></header>'+
 '<div class="gf-panel__body"><div class="gf-route-panel__canvas" data-fleet-map role="region" aria-label="Mappa della suddivisione dei giri"></div></div>'+
 '<ol class="gf-stop-list" data-height="auto" aria-label="Fermate del giro '+(i+1)+'">'+
 (all.length?all.map((k,j)=>stop(plan,dirty,k,i,j,busy)).join(''):'<li class="gf-empty"><p>Nessuna fermata</p><small>Trascina qui una consegna.</small></li>')+'</ol>'+
 (valid&&route.result.driver_breaks?.length?'<details class="fleet-lane-breaks"><summary>Turno e pause</summary>'+GFDriverBreaks.cards(route.result,0,'div')+route.stop_indexes.map((_,j)=>GFDriverBreaks.cards(route.result,j+1,'div')).join('')+'</details>':'')+
 (routeId?'<footer class="gf-panel__footer"><button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-open="'+Number(routeId)+'">Apri giro programmato</button></footer>':'')+'</section>';
}
// "Da sistemare": solo consegne non assegnate e fuori orario.
function fixes(plan,assignment,dirty){
 const missing=assignment.map((v,i)=>v==null?i:null).filter(i=>i!==null);
 const late=dirty?[]:lateStops(plan).filter(item=>assignment[item.stop_index]!=null);
 const target=names(plan,selected);
 const rows=missing.map(i=>{
  const d=plan.configuration.consegne[i],reason=plan.unassigned?.find(row=>row.index===i)?.reason;
  return '<li class="gf-list-item" data-fleet-stop="'+i+'"><div class="gf-list-item__main"><strong>'+esc(d.cliente_nome)+'</strong><small>Non assegnata · '+esc(d.indirizzo)+'</small>'+(reason?'<small>'+esc(reason)+'</small>':'')+'</div>'+
  (plan.status==='preview'?'<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-fleet-assign="'+i+'">Assegna al giro '+(selected+1)+'</button>':'<span class="gf-badge" data-status="warning">Non assegnata</span>')+'</li>';
 }).concat(late.map(item=>{
  const lane=assignment[item.stop_index],d=plan.configuration.consegne[item.stop_index];
  return '<li class="gf-list-item" data-fleet-late="'+item.stop_index+'"><span class="gf-avatar" data-tone="'+tone(lane)+'" aria-label="Giro '+(lane+1)+'">'+(lane+1)+'</span><div class="gf-list-item__main"><strong>'+esc(d.cliente_nome)+'</strong><small>Giro '+(lane+1)+' · con il traffico lo scarico finisce alle '+esc(item.fine_servizio)+', oltre la fascia '+esc(item.window.start)+'–'+esc(item.window.end)+'</small></div>'+
  '<span class="gf-badge" data-status="danger">+'+esc(item.lateness_min)+' min</span></li>';
 }));
 return '<section class="gf-panel" aria-labelledby="fleetFixTitle"><header class="gf-panel__header"><div><h2 class="gf-panel__title" id="fleetFixTitle">Da sistemare</h2><p class="gf-muted">'+(rows.length?'Consegne non assegnate e fuori orario':'Tutto a posto')+'</p></div>'+(rows.length?'<span class="gf-badge" data-status="warning">'+rows.length+'</span>':'')+'</header>'+
 (rows.length?'<ul class="gf-list">'+rows.join('')+'</ul>':'<div class="gf-empty"><p>Nessuna consegna da sistemare</p><small>Tutte le consegne sono assegnate e in orario.</small></div>')+
 (missing.length&&plan.status==='preview'?'<div class="gf-panel__body gf-stack" data-gap="sm"><p class="gf-muted">«Assegna» la sposta nel giro che stai guardando ('+esc(target.driver)+').</p><label class="gf-check"><input type="checkbox" data-fleet-accept-unassigned> <span>Confermo di programmare soltanto le consegne assegnate</span></label></div>':'')+'</section>';
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
  const focus=ordered(plan,assignment,selected).map(i=>coords[i]).filter(Boolean);
  const bounds=L.latLngBounds(focus.length?focus:coords.filter(Boolean));
  // Tutti i giri sulla mappa; quello scelto in evidenza, gli altri attenuati.
  plan.configuration.resources.forEach((_,lane)=>{
   const on=lane===selected,positions=ordered(plan,assignment,lane),path=positions.map(i=>coords[i]).filter(Boolean);
   if(path.length>1)L.polyline(path,{color:color(lane),weight:on?3:2,opacity:on?.8:.25,dashArray:'3 8'}).addTo(map);
   positions.forEach((i,j)=>{
    if(!coords[i])return;
    const pin=L.marker(coords[i],{opacity:on?1:.45,zIndexOffset:on?500:0,icon:L.divIcon({className:'fleet-review-pin-icon',html:'<span class="fleet-review-pin" style="--lane:'+color(lane)+'" data-fleet-pin="'+i+'">'+(j+1)+'</span>',iconSize:[30,30],iconAnchor:[15,15]})}).addTo(map);
    const pop=document.createElement('div'),a=document.createElement('strong'),b=document.createElement('div');
    a.textContent=plan.configuration.consegne[i].cliente_nome;b.textContent='Giro '+(lane+1)+' · '+plan.configuration.consegne[i].indirizzo;pop.append(a,b);pin.bindPopup(pop);
    pin.on('mouseover',()=>highlight(i,true));pin.on('mouseout',()=>highlight(i,false));
   });
  });
  const depot=plan.routes.find(r=>r.result?.depot_coord)?.result?.depot_coord;
  if(depot?.lat!=null&&depot?.lon!=null){const d=[Number(depot.lat),Number(depot.lon)];bounds.extend(d);
   L.marker(d,{icon:L.divIcon({className:'fleet-review-pin-icon',html:'<span class="fleet-review-pin depot">D</span>',iconSize:[30,30],iconAnchor:[15,15]})}).addTo(map);}
  map.fitBounds(bounds,{padding:[22,22],maxZoom:13,animate:false});requestAnimationFrame(()=>map?.invalidateSize());
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
// Titolo, freccia "indietro" e "Pianifica giri" nella barra in alto, come nelle altre pagine.
function topbar(plan,dirty,busy,permission,onBack,onPlan){
 const planned=plan.status==='programmed',el=id=>document.getElementById(id);
 document.querySelector?.('.gf-header__titles')?.classList.remove('gf-hidden');
 const title=el('workspacePageTitle'),subtitle=el('workspacePageSubtitle'),badge=el('workspacePageBadge'),host=el('fleetTopbarActionsHost');
 if(title)title.textContent='Controlla la suddivisione';
 if(subtitle)subtitle.textContent='Verifica le consegne distribuite fra i mezzi. Puoi spostarle prima di pianificare i giri.';
 if(badge){badge.hidden=!planned;badge.textContent=planned?'Giri programmati':'';badge.dataset.status='success';}
 if(typeof gfRouteDetailBack==='function')gfRouteDetailBack('Torna alla pianificazione',onBack);
 if(!host)return;
 host.classList.remove('gf-hidden');
 host.innerHTML=planned?'':'<button type="button" class="gf-button" data-variant="primary" data-fleet-plan '+(busy||dirty||!permission?'disabled':'')+'>Pianifica giri</button>';
 host.querySelector('[data-fleet-plan]')?.addEventListener('click',onPlan);
}
function render(params){
 const {plan,assignment,dirty,busy,permission,error,onMove,onUndo,onRecalc,onPlan,onBack}=params;
 stopMap();if(dialog){dialog.remove();dialog=null;}
 const target=site();if(!target)return;
 const planned=plan.status==='programmed',saved=plan.status==='saved',rows=plan.configuration.resources.length;
 // Il giro scelto resta lo stesso tra un ricalcolo e l'altro dello stesso piano.
 if(selectedPlan!==plan.id){selectedPlan=plan.id;selected=0;}
 if(selected>=rows)selected=0;
 // Classe di ambito per i segnaposto della mappa (ancora sul vecchio foglio, in attesa di un componente mappa).
 target.classList.add('fleet-review-page');
 target.innerHTML='<section class="gf-stack" data-gap="lg" data-fleet-review>'+
 (saved?'<div class="gf-alert" data-status="warning" role="status"><div class="gf-alert__body"><strong class="gf-alert__title">Giri in bozza, programmazione non completata</strong><p>Puoi riprovare con “Pianifica giri”. Non verranno duplicati giri.</p></div></div>':'')+
 totals(plan,assignment,dirty)+
 '<div class="gf-grid" data-cols="main-side"><div class="gf-stack">'+table(plan,assignment,dirty)+lane(plan,assignment,dirty,selected,busy)+'</div>'+fixes(plan,assignment,dirty)+'</div>'+
 '<div id="fleetMessage" role="status" tabindex="-1" class="gf-muted"></div>'+
 (dirty?'<div class="gf-savebar" data-floating role="region" aria-label="Fermate spostate, giri da ripianificare">'+(error?'<span role="alert" data-fleet-error><b>Ripianificazione non riuscita</b> · '+esc(error)+' Sposta di nuovo le fermate o annulla le modifiche.</span>':'<span><b>Fermate spostate</b> · Ripianifica i giri per aggiornare ordine, tempi e costi.</span>')+
 '<button type="button" class="gf-button" data-variant="secondary" data-size="sm" data-fleet-undo>Annulla modifiche</button><button type="button" class="gf-button" data-variant="primary" data-size="sm" data-fleet-recalc '+(busy?'disabled':'')+'>Ripianifica giri</button></div>':'')+
 '</section>';
 topbar(plan,dirty,busy,permission,onBack,()=>onPlan(!!target.querySelector('[data-fleet-accept-unassigned]')?.checked));
 target.querySelector('[data-fleet-undo]')?.addEventListener('click',onUndo);
 target.querySelector('[data-fleet-recalc]')?.addEventListener('click',onRecalc);
 const move=(index,to)=>{
  if(!Number.isInteger(index)||to===assignment[index]||to<0||to>=rows)return;
  onMove(index,to);
 };
 target.querySelectorAll('[data-fleet-select]').forEach(button=>button.addEventListener('click',()=>{selected=Number(button.dataset.fleetSelect);render(params);}));
 target.querySelectorAll('[data-fleet-move-to]').forEach(select=>select.addEventListener('change',()=>{
  const to=select.value===''?null:Number(select.value);select.value='';
  if(to!==null&&!busy)move(Number(select.dataset.fleetMoveTo),to);
 }));
 target.querySelectorAll('[data-fleet-assign]').forEach(button=>button.addEventListener('click',()=>{if(!busy)move(Number(button.dataset.fleetAssign),selected);}));
 target.querySelectorAll('[data-fleet-stop]').forEach(stop=>{
  stop.addEventListener('dragstart',e=>{if(plan.status!=='preview'||busy||!e.target.closest('[data-fleet-drag]')){e.preventDefault();return;}drag=Number(stop.dataset.fleetStop);e.dataTransfer.setData('text/plain',String(drag));e.dataTransfer.effectAllowed='move';e.dataTransfer.setDragImage(stop,20,20);stop.classList.add('is-highlighted');});
  stop.addEventListener('dragend',()=>{drag=null;stop.classList.remove('is-highlighted');target.querySelectorAll('[data-fleet-lane][aria-dropeffect]').forEach(el=>el.removeAttribute('aria-dropeffect'));});
  stop.addEventListener('mouseenter',()=>highlight(stop.dataset.fleetStop,true));stop.addEventListener('mouseleave',()=>highlight(stop.dataset.fleetStop,false));
 });
 // Le righe della tabella (e il pannello del giro scelto) accolgono le fermate trascinate.
 target.querySelectorAll('[data-fleet-lane]').forEach(el=>{
  el.addEventListener('dragover',e=>{if(drag==null)return;e.preventDefault();el.setAttribute('aria-dropeffect','move');});
  el.addEventListener('dragleave',e=>{if(!el.contains(e.relatedTarget))el.removeAttribute('aria-dropeffect');});
  el.addEventListener('drop',e=>{e.preventDefault();el.removeAttribute('aria-dropeffect');if(drag!=null){const i=drag;drag=null;move(i,Number(el.dataset.fleetLane));}});
 });
 drawMap(plan,assignment);
}
return {render,warning,stopMap};
})();
