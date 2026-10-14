/* GiroFacile · layout base condiviso (sidebar + header).
   Una pagina dichiara <body data-gf-layout="base"> e un solo <main data-gf-shell-content>;
   questo script costruisce attorno al contenuto la sidebar blu notte e l'intestazione
   della Dashboard. Il menu è definito una sola volta qui (GFShell.NAV).

   Attributi letti dal body:
     data-gf-nav-active   voce attiva del menu (es. "clienti")
     data-gf-title        titolo nella barra in alto
     data-gf-subtitle     sottotitolo (facoltativo)
     data-gf-user-name    nome mostrato a destra (facoltativo)
     data-gf-user-role    ruolo sotto il nome (facoltativo)
   Elementi con data-gf-slot="header-actions" vengono spostati nell'intestazione.
   Un <script type="application/json" id="gf-shell-nav"> sostituisce il menu standard.
   Nessun testo viene interpretato come HTML. */
(function(global){
  'use strict';
  const doc = global.document;
  const SVG = 'http://www.w3.org/2000/svg';
  const ICONS = {
    dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z',
    company: 'M4 21V4a1 1 0 0 1 1-1h9a1 1 0 0 1 1 1v17 M15 9h4a1 1 0 0 1 1 1v11 M3 21h18 M8 7h3 M8 11h3 M8 15h3',
    calendar: 'M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M16 3v4 M8 3v4 M4 11h16',
    orders: 'M9 4h6v3H9z M7 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1 M9 12h6 M9 16h6',
    customers: 'M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1 M9.5 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M21 20v-1a4 4 0 0 0-3-3.9 M16 4.1a3.5 3.5 0 0 1 0 6.8',
    user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21a8 8 0 0 1 16 0',
    report: 'M3 3v18h18 M7 15l4-4 3 3 5-6',
    deposit: 'M3 10l9-6 9 6v10H3z M8 20v-6h8v6',
    truck: 'M2 6h11v10H2z M13 9h5l3 3v4h-8z M6.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z M17.5 19a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z',
    driver: 'M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z M5 16h4 M14 10h5 M14 14h5 M7 11.5a1.5 1.5 0 1 0 0-.01',
    history: 'M3 12a9 9 0 1 0 3-6.7 M3 4v5h5 M12 7v5l3 2',
    chat: 'M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z',
    support: 'M4 14v-2a8 8 0 0 1 16 0v2 M4 14h3v5H5a1 1 0 0 1-1-1z M20 14h-3v5h2a1 1 0 0 0 1-1z',
    settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1L7 17 M17 7l2.1-2.1',
    document: 'M7 3h7l5 5v13H7z M14 3v5h5 M10 13h6 M10 17h6',
    menu: 'M4 6h16 M4 12h16 M4 18h16',
    close: 'M6 6l12 12 M18 6L6 18'
  };
  // Menu standard del gestionale: stesso ordine e stesse voci della Dashboard.
  const NAV = [
    {items:[
      {id:'dashboard',label:'Dashboard',icon:'dashboard'},
      {id:'company',label:'Azienda',icon:'company'},
      {id:'giro',label:'Pianificazione',icon:'calendar'},
      {id:'ordini',label:'Ordini',icon:'orders'},
      {id:'clienti',label:'Clienti',icon:'customers'},
      {id:'collaboratori',label:'Collaboratori',icon:'user'},
      {id:'report',label:'Report',icon:'report'}
    ]},
    {label:'Risorse',items:[
      {id:'depositi',label:'Depositi',icon:'deposit'},
      {id:'mezzi',label:'Mezzi',icon:'truck'},
      {id:'autisti',label:'Autisti',icon:'driver'}
    ]},
    {label:'Sistema',items:[
      {id:'storico',label:'Storico',icon:'history'},
      {id:'chat-autisti',label:'Chat autisti',icon:'chat'},
      {id:'supporto',label:'Supporto',icon:'support'},
      {id:'settings',label:'Impostazioni',icon:'settings'}
    ]}
  ];
  const FOOTER_LINKS = [['Privacy','/privacy-policy'],['Termini','/termini-condizioni'],['Cookie','/cookie-policy']];

  function el(tag, className, text){
    const node = doc.createElement(tag);
    if(className) node.className = className;
    if(text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function icon(name, className){
    const svg = doc.createElementNS(SVG,'svg');
    svg.setAttribute('viewBox','0 0 24 24');
    svg.setAttribute('aria-hidden','true');
    svg.setAttribute('focusable','false');
    svg.setAttribute('class',className || 'gf-icon');
    const path = doc.createElementNS(SVG,'path');
    path.setAttribute('d',ICONS[name] || ICONS.document);
    svg.appendChild(path);
    return svg;
  }
  function brandMark(){
    const svg = doc.createElementNS(SVG,'svg');
    svg.setAttribute('viewBox','0 0 34 34');
    svg.setAttribute('class','gf-sidebar__mark');
    svg.setAttribute('aria-hidden','true');
    const rect = doc.createElementNS(SVG,'rect');
    rect.setAttribute('width','34');rect.setAttribute('height','34');rect.setAttribute('rx','9');
    rect.setAttribute('class','gf-sidebar__mark-bg');
    const path = doc.createElementNS(SVG,'path');
    path.setAttribute('d','M24 12.2A8.2 8.2 0 1 0 25 17.5H17.5');
    path.setAttribute('class','gf-sidebar__mark-g');
    const dot = doc.createElementNS(SVG,'circle');
    dot.setAttribute('cx','24.2');dot.setAttribute('cy','9.6');dot.setAttribute('r','2.4');
    dot.setAttribute('class','gf-sidebar__mark-dot');
    svg.append(rect,path,dot);
    return svg;
  }
  function initials(name){
    return String(name || '').trim().split(/\s+/).slice(0,2).map(part => part.charAt(0).toUpperCase()).join('') || 'GF';
  }
  function itemHref(item){
    if(item.href) return item.href;
    return '/dashboard';
  }

  function buildSidebar(sections, active){
    const aside = el('aside','gf-sidebar');
    aside.id = 'gf-shell-sidebar';
    aside.setAttribute('aria-label','Navigazione principale');
    const brand = el('a','gf-sidebar__brand');
    brand.href = '/dashboard';
    brand.append(brandMark(), el('span','gf-sidebar__brand-name','GiroFacile'));
    aside.appendChild(brand);
    const nav = el('nav','gf-sidebar__nav');
    nav.setAttribute('aria-label','Sezioni');
    sections.forEach(section => {
      const group = el('div','gf-sidebar__section');
      if(section.label) group.appendChild(el('p','gf-sidebar__label',section.label));
      (section.items || []).forEach(item => {
        const link = el('a','gf-sidebar__item');
        link.href = itemHref(item);
        link.dataset.gfNav = item.id;
        if(item.id === active) link.setAttribute('aria-current','page');
        link.append(icon(item.icon,'gf-sidebar__icon'), el('span',null,item.label));
        group.appendChild(link);
      });
      nav.appendChild(group);
    });
    aside.appendChild(nav);
    const footer = el('div','gf-sidebar__footer');
    footer.appendChild(el('span',null,'© 2026 GiroFacile'));
    const links = el('div','gf-sidebar__links');
    FOOTER_LINKS.forEach(([label,href]) => {
      const link = el('a',null,label);link.href = href;link.target = '_blank';link.rel = 'noopener';
      links.appendChild(link);
    });
    footer.appendChild(links);
    aside.appendChild(footer);
    return aside;
  }

  function buildHeader(options, shell){
    const header = el('header','gf-header');
    const menu = el('button','gf-icon-button gf-header__menu');
    menu.type = 'button';
    menu.setAttribute('aria-label','Apri il menu');
    menu.setAttribute('aria-controls','gf-shell-sidebar');
    menu.setAttribute('aria-expanded','false');
    menu.appendChild(icon('menu'));
    menu.addEventListener('click',() => setOpen(shell, menu, shell.dataset.gfShellOpen !== 'true'));
    const titles = el('div','gf-header__titles');
    titles.appendChild(el('h1','gf-header__title',options.title || ''));
    if(options.subtitle) titles.appendChild(el('p','gf-header__subtitle',options.subtitle));
    const actions = el('div','gf-header__actions');
    (options.actions || []).forEach(node => { node.removeAttribute('data-gf-slot'); actions.appendChild(node); });
    header.append(menu, titles, actions);
    if(options.userName){
      const user = el('div','gf-header__user');
      const avatar = el('span','gf-avatar',initials(options.userName));
      avatar.setAttribute('aria-hidden','true');
      const copy = el('span','gf-header__user-copy');
      copy.appendChild(el('strong',null,options.userName));
      if(options.userRole) copy.appendChild(el('small',null,options.userRole));
      user.append(avatar, copy);
      header.appendChild(user);
    }
    return {header, menu};
  }

  function setOpen(shell, menu, open){
    shell.dataset.gfShellOpen = open ? 'true' : 'false';
    menu.setAttribute('aria-expanded', String(open));
    menu.setAttribute('aria-label', open ? 'Chiudi il menu' : 'Apri il menu');
  }

  function readNav(){
    const source = doc.getElementById('gf-shell-nav');
    if(!source) return NAV;
    try { return JSON.parse(source.textContent); } catch(error){ return NAV; }
  }

  function mount(options){
    const body = doc.body;
    options = options || {};
    const content = options.content || doc.querySelector('[data-gf-shell-content]');
    if(!content || doc.querySelector('[data-gf-shell]')) return null;
    const shell = el('div','gf-shell');
    shell.dataset.gfShell = '';
    shell.dataset.gfShellOpen = 'false';
    const sidebar = buildSidebar(options.nav || NAV, options.active || '');
    const scrim = el('div','gf-shell__scrim');
    const main = el('div','gf-shell__main');
    const built = buildHeader(options, shell);
    scrim.addEventListener('click',() => setOpen(shell, built.menu, false));
    sidebar.addEventListener('click',event => { if(event.target.closest && event.target.closest('a')) setOpen(shell, built.menu, false); });
    doc.addEventListener('keydown',event => {
      if(event.key === 'Escape' && shell.dataset.gfShellOpen === 'true'){ setOpen(shell, built.menu, false); built.menu.focus(); }
    });
    content.classList.add('gf-shell__content');
    content.parentNode.insertBefore(shell, content);
    main.append(built.header, content);
    shell.append(sidebar, scrim, main);
    body.classList.add('gf-has-shell');
    return shell;
  }

  function autoMount(){
    const body = doc.body;
    if(!body || body.dataset.gfLayout !== 'base') return;
    mount({
      nav: readNav(),
      active: body.dataset.gfNavActive,
      title: body.dataset.gfTitle,
      subtitle: body.dataset.gfSubtitle,
      userName: body.dataset.gfUserName,
      userRole: body.dataset.gfUserRole,
      actions: Array.from(doc.querySelectorAll('[data-gf-slot="header-actions"]'))
    });
  }

  global.GFShell = {NAV, ICONS, mount, icon};
  if(doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', autoMount);
  else autoMount();
})(window);
