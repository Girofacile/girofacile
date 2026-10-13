/* Defaults on the driver, editable daily snapshots on individual/fleet routes. */
window.GFDriverSchedules=(()=>{
 const el=id=>document.getElementById(id);
 const copy=x=>JSON.parse(JSON.stringify(x||{start:null,end:null,breaks:[]}));
 const defaults=id=>copy((typeof driversCache!=='undefined'?driversCache:[]).find(d=>String(d.id)===String(id))?.work_schedule);
 function mount(host,value,changed=()=>{}){
   if(!host)return;
   const data=copy(value),prefix=host.id;
   host.innerHTML=`<div class="driver-schedule-fields"><div><label for="${prefix}Start">Inizio turno</label><input id="${prefix}Start" data-shift="start" type="time" value="${esc(data.start||'')}"></div><div><label for="${prefix}End">Fine turno</label><input id="${prefix}End" data-shift="end" type="time" value="${esc(data.end||'')}"></div></div><p class="driver-schedule-hint">Lascia entrambi vuoti se non vuoi impostare un turno. Gli orari si riferiscono alla stessa giornata.</p><div class="driver-break-inputs"></div><button type="button" class="btn-secondary" data-add-break>Aggiungi pausa</button><p class="driver-schedule-error" role="status"></p>`;
   function rows(){host.querySelector('.driver-break-inputs').innerHTML=(data.breaks||[]).map((b,i)=>`<div class="driver-break-input"><div><label for="${prefix}Break${i}Start">Pausa ${i+1} · dalle</label><input id="${prefix}Break${i}Start" type="time" data-break="${i}" data-part="start" value="${esc(b.start||'')}"></div><div><label for="${prefix}Break${i}End">Alle</label><input id="${prefix}Break${i}End" type="time" data-break="${i}" data-part="end" value="${esc(b.end||'')}"></div><button type="button" class="btn-secondary" data-remove-break="${i}" aria-label="Rimuovi pausa ${i+1}">Rimuovi</button></div>`).join('');host.querySelector('[data-add-break]').disabled=(data.breaks||[]).length>=8;}
   function notify(){host._schedule=copy(data);host.querySelector('.driver-schedule-error').textContent=error(data);changed(copy(data));}
   rows();host._schedule=copy(data);
   host.onchange=e=>{if(e.target.dataset.shift)data[e.target.dataset.shift]=e.target.value||null;if(e.target.dataset.break!==undefined)data.breaks[Number(e.target.dataset.break)][e.target.dataset.part]=e.target.value;notify();};
   host.onclick=e=>{if(e.target.closest('[data-add-break]')){data.breaks||=[];if(data.breaks.length<8)data.breaks.push({start:'',end:''});rows();notify();}const button=e.target.closest('[data-remove-break]');if(button){data.breaks.splice(Number(button.dataset.removeBreak),1);rows();notify();}};
 }
 function error(data){
   if(!data)return '';
   if(!!data.start!==!!data.end)return 'Completa inizio e fine turno.';
   if(data.start&&data.start>=data.end)return 'La fine turno deve essere successiva all’inizio, nella stessa giornata.';
   const breaks=[...(data.breaks||[])].sort((a,b)=>a.start.localeCompare(b.start));
   for(let i=0;i<breaks.length;i++){const b=breaks[i];if(!b.start||!b.end||b.start>=b.end)return 'Completa gli orari della pausa: la fine deve seguire l’inizio.';if(data.start&&(b.start<data.start||b.end>data.end))return 'Le pause devono essere comprese nel turno.';if(i&&breaks[i-1].end>b.start)return 'Le pause non possono sovrapporsi.';}
   return '';
 }
 const read=id=>copy(el(id)?._schedule);
 function driver(value){mount(el('driverWorkSchedule'),value);}
 function route(value){mount(el('routeDriverSchedule'),value,()=>{globalThis.GFOrderPlanning?.changed();updateRoutePlanningGateV68();});}
 const routePayload=()=>({driver_schedule:el('routeDriverSchedule')?._schedule?read('routeDriverSchedule'):defaults(el('routeDriver')?.value)});
 function missing(){return error(read('routeDriverSchedule'))?['turno e pause autista']:[];}
 function fleet(resources){resources.forEach((r,i)=>mount(el('fleetDriverSchedule'+i),r.driver_schedule??defaults(r.driver_id),value=>{r.driver_schedule=value;globalThis.GFOrderPlanning?.changed();updateRoutePlanningGateV68();}));}
 document.addEventListener('change',e=>{if(e.target.id==='routeDriver')route(defaults(e.target.value));});
 return {mount,driver,route,read,error,defaults,fleet,routePayload,missing};
})();
