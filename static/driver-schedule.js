/* Shared break rows for dashboard, driver portal and printed stop lists. */
window.GFDriverBreaks=(()=>{
 const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const label=b=>'Pausa del turno dalle '+escape(b.start)+' alle '+escape(b.end);
 const note=b=>Number(b.duration_min)+' minuti di riposo per l\u2019autista';
 // Riga senza numero, in giallo, tra le fermate: la pausa non è una consegna.
 function table(route,after,columns=6){return (route?.driver_breaks||[]).filter(b=>b.after_order===after).map(b=>`<tr class="driver-break-row" data-break-after="${after}"><td aria-hidden="true"></td><td colspan="${columns-1}"><strong>${label(b)}</strong><small>${note(b)}</small></td></tr>`).join('');}
 function cards(route,after,tag='div',extra=''){return (route?.driver_breaks||[]).filter(b=>b.after_order===after).map(b=>`<${tag} class="driver-break-card ${extra}"><strong>${label(b)}</strong><small>${note(b)}</small></${tag}>`).join('');}
 return {table,cards};
})();
