/* Shared break rows for dashboard, driver portal and printed stop lists. */
window.GFDriverBreaks=(()=>{
 const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const label=b=>'Pausa autista dalle '+escape(b.start)+' alle '+escape(b.end);
 function table(route,after,columns=6){return (route?.driver_breaks||[]).filter(b=>b.after_order===after).map(b=>`<tr class="driver-break-row" data-break-after="${after}"><td aria-label="Pausa">Ⅱ</td><td colspan="${columns-1}"><strong>${label(b)}</strong><small>Riposo pianificato · ${Number(b.duration_min)} minuti</small></td></tr>`).join('');}
 function cards(route,after,tag='div',extra=''){return (route?.driver_breaks||[]).filter(b=>b.after_order===after).map(b=>`<${tag} class="driver-break-card ${extra}"><strong>Ⅱ ${label(b)}</strong><small>Riposo pianificato · ${Number(b.duration_min)} minuti</small></${tag}>`).join('');}
 return {table,cards};
})();
