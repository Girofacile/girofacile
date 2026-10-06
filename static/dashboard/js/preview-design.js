/* Layout only: preserve route data, warnings and existing action handlers. */
window.GFPreview = (() => {
  const paths = {
    fuel:'<path d="M5 21V3h9v18M5 8h9M3 21h13M14 11h2v7a2 2 0 0 0 4 0V9l-3-3m1 1v4h2"/>',
    road:'<path fill="currentColor" stroke="none" d="M6 3h12l5 19H1L6 3Zm5 2v5h2V5h-2Zm0 8v6h2v-6h-2Z"/>',
    coins:'<ellipse cx="9" cy="12" rx="7" ry="3"/><path d="M2 12v4c0 4 14 4 14 0v-4M2 16v4c0 4 14 4 14 0v-4M11 5c0-4 12-4 12 0s-12 4-12 0Zm12 0v4c0 2-3 3-6 3m6-3v5c0 2-2 3-5 3"/>',
    bolt:'<path d="m14 2-10 12h7l-1 8 10-13h-7z"/>',
    car:'<path d="m4 10 2-6h12l2 6M3 10h18v9H3zM5 19v3m14-3v3M6 14h2m8 0h2M7 7h10"/>',
    play:'<path d="m5 2 16 10L5 22z"/>',
    back:'<path d="m9 7-5 5 5 5M4 12h17"/>',
    external:'<path d="M14 3h7v7m0-7L11 13M10 5H4v16h16v-6"/>',
    calendar:'<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 2v6m8-6v6M4 11h16m-11 5 2 2 4-4"/>',
    grip:'<path d="M7 6h10M7 10h10M7 14h10M7 18h10"/>'
  };
  const svg = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
  function decorate(target){
    const root=target.querySelector('.route-preview-design');
    if(!root)return;
    const layout=root.querySelector('.result-layout'), main=root.querySelector('.result-main'), side=root.querySelector('.result-summary-card');
    const map=root.querySelector('.route-map-panel-v74');
    const stops=root.querySelector('.stops-panel');
    const alerts=root.querySelector('.alerts-panel');
    if(alerts)root.insertBefore(alerts,layout);
    root.insertBefore(stops,layout);
    if(map)layout.insertBefore(map,side);
    main.remove();
    side.querySelectorAll(':scope > .summary-row').forEach(el=>el.remove());
    side.querySelector(':scope > .preview-heading-copy').innerHTML=`<span class="preview-section-icon">${svg('bolt')}</span><div><h3>Azioni rapide</h3><p>Strumenti per verificare e procedere.</p></div>`;
    const program=side.querySelector('.preview-program'), back=side.querySelector('.preview-back');
    if(program)program.innerHTML=svg('play')+'Programma giro';
    back.innerHTML=svg('back')+'Torna alla pianificazione';
    const google=root.querySelector('.route-map-actions-v74 a');
    if(google){google.innerHTML=google.querySelector('svg').outerHTML+'<span>Apri in Google Maps</span>'+svg('external');side.insertBefore(google,program || back);}
    const eta=root.querySelector('.gf-routing-eta');
    const refresh=eta?.querySelector('button');
    if(refresh){refresh.innerHTML=svg('car')+'Aggiorna ETA con traffico';side.insertBefore(refresh,program || back);}
    if(eta)side.querySelector('.preview-extra').append(eta);
    root.querySelectorAll('.gf-routing-costs > div').forEach((card,i)=>{
      const content=document.createElement('div');
      while(card.firstChild)content.append(card.firstChild);
      card.append(content);
      card.insertAdjacentHTML('afterbegin',`<span class="preview-cost-icon ${['red','green','orange'][i]}">${svg(['fuel','road','coins'][i])}</span>`);
    });
    stops.querySelector('.preview-section-icon').innerHTML=svg('calendar');
    stops.querySelectorAll('.drag-handle').forEach(el=>{el.innerHTML=svg('grip');el.setAttribute('aria-hidden','true');});
    stops.querySelector('th:last-child').textContent='Azioni';
  }
  return {decorate};
})();
