/* GiroFacile · icone a linea condivise dai portali (14 ottobre 2026).
   Sostituiscono le emoji con lo stesso tratto delle icone della Dashboard.
   gfIcon(nome) restituisce un SVG statico (nessun dato utente al suo interno). */
(function(){
  const P = {
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    pin: '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
    route: '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7"/>',
    warehouse: '<path d="M3 21V9l9-5 9 5v12"/><path d="M7 21v-7h10v7M7 17h10"/>',
    check: '<path d="m5 12 4 4 10-10"/>',
    checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    xCircle: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    note: '<path d="M5 3h10l4 4v14H5Z"/><path d="M14 3v5h5M8 12h8M8 16h5"/>',
    pen: '<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z"/>',
    alert: '<path d="M12 3 2 20h20L12 3Z"/><path d="M12 10v4M12 17h.01"/>',
    tool: '<path d="M14 7a4 4 0 0 0 5 5l-8 8a2 2 0 0 1-3-3l8-8a4 4 0 0 0-2-2Z"/>',
    timer: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M9 2h6"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0 1 14 0M16 4.5a3.5 3.5 0 0 1 0 7M18 13.5a6 6 0 0 1 4 6"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="m6 6 12 12"/>',
    chat: '<path d="M21 12a8 8 0 0 1-11.5 7.2L4 20l1-4.5A8 8 0 1 1 21 12Z"/>',
    truck: '<path d="M3 6h11v10H3zM14 9h4l3 3v4h-7"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    box: '<path d="M21 8 12 3 3 8v8l9 5 9-5Z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    weight: '<path d="M6 8h12l2 12H4Z"/><circle cx="12" cy="5" r="2"/>',
    map: '<path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2Z"/><path d="M9 4v14M15 6v14"/>',
    euro: '<path d="M17 6a7 7 0 1 0 0 12M4 10h9M4 14h9"/>',
    star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9Z"/>',
    folder: '<path d="M3 6h6l2 2h10v11H3Z"/>',
    handshake: '<path d="m11 17 2 2a2 2 0 0 0 3-3M14 14l2.5 2.5a2 2 0 0 0 3-3L15 9l-3 1-2-2 3-3 4 1 4 4M3 11l4-4 4 1"/><path d="m7 15 2 2"/>',
    play: '<path d="M7 5v14l11-7Z"/>',
    back: '<path d="m15 18-6-6 6-6"/><path d="M9 12h10"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>'
  };
  window.gfIcon = function(name, extraClass){
    const body = P[name] || P.checkCircle;
    const cls = 'gf-i' + (extraClass ? ' ' + extraClass : '');
    return '<svg class="' + cls + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + body + '</svg>';
  };
})();
