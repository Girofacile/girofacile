/* Mobile presentation of the Dashboard. Data still comes from loadDashboardHome. */
(function(){
  'use strict';
  const get=id=>document.getElementById(id);
  const text=(id,value)=>{const node=get(id);if(node)node.textContent=value;};
  let resourceHint='Caricamento risorse…';
  let canPlan=true;

  function syncHeader(){
    const user=typeof currentSessionUser!=='undefined'?(currentSessionUser||{}):{};
    const saved=localStorage.getItem('girofacile_company_name')||'';
    const account=user.username||localStorage.getItem('girofacile_account_name')||'';
    const company=String(user.company_name||(saved!==account?saved:'')).trim()||'La tua azienda';
    text('dashMobileCompany',company);
    if(get('dashMobileCompany'))get('dashMobileCompany').title=company;
    const now=new Date();
    const date=new Intl.DateTimeFormat('it-IT',{weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(now);
    const shortDate=new Intl.DateTimeFormat('it-IT',{weekday:'long',day:'numeric',month:'short'}).format(now);
    const iso=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');
    for(const [id,value] of [['dashMobileDate',date.charAt(0).toUpperCase()+date.slice(1)],['dashMobileShortDate',shortDate.toLocaleUpperCase('it-IT')]]){
      const node=get(id);
      if(node){node.textContent=value;node.dateTime=iso;}
    }
  }

  function syncResourceHint(){
    text('dashMobileResourceHint',canPlan?resourceHint:'Completa la configurazione per iniziare');
  }

  function loading(){
    get('dashMobileResources')?.setAttribute('aria-busy','true');
    const status=get('dashMobileAvailability');
    if(status){status.dataset.status='neutral';status.textContent='Caricamento…';}
    resourceHint='Caricamento risorse…';
    syncResourceHint();
    syncHeader();
  }

  function updateResources(drivers,vehicles){
    const count=(items,state)=>items.filter(item=>(item.stato||'Disponibile')===state).length;
    const busyDrivers=count(drivers,'In servizio'),busyVehicles=count(vehicles,'In uso');
    const freeDrivers=count(drivers,'Disponibile'),freeVehicles=count(vehicles,'Disponibile');
    text('dashMobileDriversCount',`${busyDrivers}/${drivers.length}`);
    text('dashMobileVehiclesCount',`${busyVehicles}/${vehicles.length}`);
    get('dashMobileDriversCount')?.parentElement.setAttribute('aria-label',`Autisti: ${busyDrivers} impegnati su ${drivers.length}, ${freeDrivers} disponibili`);
    get('dashMobileVehiclesCount')?.parentElement.setAttribute('aria-label',`Mezzi: ${busyVehicles} impegnati su ${vehicles.length}, ${freeVehicles} disponibili`);
    let label,tone;
    if(!drivers.length||!vehicles.length){
      label='Da configurare';tone='neutral';
      resourceHint=`Aggiungi ${!drivers.length&&!vehicles.length?'autisti e mezzi':!drivers.length?'autisti':'mezzi'} per iniziare`;
    }else if(freeDrivers===drivers.length&&freeVehicles===vehicles.length){
      label='Disponibili';tone='success';
      resourceHint='Tutti i mezzi e gli autisti sono liberi';
    }else{
      label=busyDrivers+busyVehicles?'In attività':'Disponibilità ridotta';tone='warning';
      resourceHint=`${freeDrivers} autist${freeDrivers===1?'a':'i'} e ${freeVehicles} mezz${freeVehicles===1?'o':'i'} disponibili`;
    }
    const status=get('dashMobileAvailability');
    if(status){status.textContent=label;status.dataset.status=tone;}
    get('dashMobileResources')?.setAttribute('aria-busy','false');
    syncResourceHint();
  }

  function loadError(){
    resourceHint='Disponibilità delle risorse non disponibile';
    text('dashMobileDriversCount','—');text('dashMobileVehiclesCount','—');
    const status=get('dashMobileAvailability');
    if(status){status.textContent='Dati non disponibili';status.dataset.status='neutral';}
    get('dashMobileResources')?.setAttribute('aria-busy','false');
    // Non lasciare i conteggi precedenti nelle etichette accessibili dopo un errore.
    get('dashMobileDriversCount')?.parentElement.setAttribute('aria-label','Apri autisti: disponibilità non disponibile');
    get('dashMobileVehiclesCount')?.parentElement.setAttribute('aria-label','Apri mezzi: disponibilità non disponibile');
    syncResourceHint();
  }

  function renderHero(summary,operational){
    canPlan=operational;
    const status=get('dashMobileRouteStatus');
    if(status)status.hidden=!!summary;
    if(summary)toggleMap(false);
    syncResourceHint();
  }

  function updateDepot(deposits,location){
    const valid=item=>item.lat!=null&&item.lon!=null&&String(item.lat).trim()!==''&&String(item.lon).trim()!==''
      &&Number.isFinite(Number(item.lat))&&Number.isFinite(Number(item.lon))&&Math.abs(Number(item.lat))<=90&&Math.abs(Number(item.lon))<=180;
    const depot=deposits.find(item=>item.predefinito&&valid(item))||deposits.find(valid);
    const place=String(location.city||'').trim();
    text('dashMobileDepotLocation',depot?[depot.nome||'Deposito',place].filter(Boolean).join(' · '):place?`Sede · ${place}`:'Configura la sede aziendale');
  }

  function toggleMap(force){
    const root=get('gfRefHeroWrap'),button=get('dashMobileMapToggle');
    if(!root||!button)return;
    const expanded=root.classList.toggle('is-map-expanded',typeof force==='boolean'?force:!root.classList.contains('is-map-expanded'));
    button.setAttribute('aria-expanded',String(expanded));
    button.textContent=expanded?'Riduci':'Espandi';
    // Il ResizeObserver della mappa reale aggiorna Leaflet alla nuova altezza.
  }

  function routeMeta(route){
    const raw=String(route.data_giro||'');
    const match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
    let date=raw||'Data da definire';
    if(match){
      const day=new Date(Number(match[1]),Number(match[2])-1,Number(match[3]));
      if(day.getFullYear()===Number(match[1])&&day.getMonth()===Number(match[2])-1&&day.getDate()===Number(match[3])){
        date=new Intl.DateTimeFormat('it-IT',{day:'numeric',month:'short'}).format(day);
      }
    }
    const stops=Math.max(0,Number(route.consegne_count)||0);
    const km=Number(route.totale_km);
    return `${date} · ${stops} fermat${stops===1?'a':'e'}${Number.isFinite(km)&&km>0?' · '+new Intl.NumberFormat('it-IT',{maximumFractionDigits:2}).format(km)+' km':''}`;
  }

  window.GFDashboardMobile=Object.freeze({syncHeader,loading,updateResources,loadError,renderHero,updateDepot,toggleMap,routeMeta});
})();
