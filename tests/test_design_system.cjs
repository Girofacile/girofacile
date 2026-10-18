const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const assets = 'static/design-system/';
function ruleDeclarations(css,selector){
  const normalize=value=>value.trim().replace(/\s+/g,' ');
  const rules=[...css.replace(/\/\*[\s\S]*?\*\//g,'').matchAll(/([^{}]+)\{([^{}]*)\}/g)];
  const rule=rules.find(match=>match[1].split(',').some(value=>normalize(value)===normalize(selector)));
  assert.ok(rule,'Missing CSS selector: '+selector);
  return rule[2];
}
function element(tag) {
  const classes = new Set();
  const node = {
    nodeType:1, tagName:tag.toUpperCase(), children:[], dataset:{}, attributes:{}, style:{},
    textContent:'', className:'', hidden:false,
    classList:{add:(...names)=>names.forEach(name=>classes.add(name)),contains:name=>classes.has(name),
      remove:name=>classes.delete(name),[Symbol.iterator]:()=>classes[Symbol.iterator](),
      toggle(name,force){if(force===undefined)force=!classes.has(name);force?classes.add(name):classes.delete(name);}},
    setAttribute(name,value){this.attributes[name]=String(value);},
    getAttribute(name){return this.attributes[name]??null;},
    append(...items){this.children.push(...items);},
    appendChild(item){this.children.push(item);return item;},
    remove(){},addEventListener(){},querySelector(){return null;},querySelectorAll(){return [];},
  };
  Object.defineProperty(node,'innerHTML',{set(){throw new Error('Labels must not be interpreted as HTML');}});
  return node;
}
function runtime(){
  const body=element('body');body.dataset.gfSurface='workspace';
  const document={readyState:'loading',body,documentElement:element('html'),
    createElement:element,createTextNode:value=>({textContent:String(value)}),
    getElementById(){return null;},addEventListener(){},querySelector(){return null;},querySelectorAll(){return [];}};
  const values={'--gf-breakpoint-sm':'640px','--gf-breakpoint-md':'768px','--gf-breakpoint-lg':'1024px','--gf-breakpoint-xl':'1440px'};
  const getComputedStyle=()=>({getPropertyValue:name=>values[name]||''});
  const window={document,getComputedStyle,setTimeout(){},clearTimeout(){}};
  const context=vm.createContext({window,document,getComputedStyle,MutationObserver:class{observe(){}disconnect(){}},requestAnimationFrame:fn=>fn(),setTimeout(){},clearTimeout(){}});
  vm.runInContext(read(assets+'design-system.js'),context);
  return{api:window.GFDesignSystem,document,context};
}
test('theme.css centrally defines palette, geometry, spacing, typography and breakpoints',()=>{
  // Il vecchio alias tokens.css è stato unificato: le pagine includono direttamente theme.css.
  assert.ok(!fs.existsSync(path.join(root,assets,'tokens.css')),'tokens.css merged into theme.css');
  const css=read(assets+'theme.css');
  for(const token of ['color-primary','color-bg','color-surface','color-text','color-muted','color-border','color-border-strong','color-success','color-success-bg','color-warning','color-warning-bg','color-danger','color-danger-bg','color-info','color-info-bg','radius-sm','radius-md','radius-lg','shadow-sm','control-height','touch-height','font-size-base','font-size-header','breakpoint-sm','breakpoint-md','breakpoint-lg','breakpoint-xl','space-1','space-2','space-3','space-4','space-6','space-8'])
    assert.match(css,new RegExp('--gf-'+token+'\\s*:'));
  assert.match(css,/--gf-color-primary\s*:\s*#1665ff/i);
  assert.match(css,/--gf-font-display\s*:\s*"Bricolage Grotesque"/);
  assert.match(css,/--gf-font-family\s*:\s*"IBM Plex Sans"/);
  const defined=new Set([...css.matchAll(/(--gf-[\w-]+)\s*:/g)].map(match=>match[1]));
  for(const file of ['components.css','layout.css','workspace.css','portals.css']){
    for(const match of read(assets+file).matchAll(/var\((--gf-[\w-]+)/g))
      assert.ok(defined.has(match[1]),file+': missing '+match[1]);
  }
});
test('one component sheet includes the reusable kit and responsive table policy',()=>{
  const css=read(assets+'components.css');
  for(const name of ['button','input','select','textarea','switch','badge','card','stat','table','dialog','dropdown','pagination','tabs','toolbar','search','empty','loading','alert','toast','page-header'])
    assert.match(css,new RegExp('\\.gf-'+name+'(?:\\b|[\\s:[.#])'),name);
  for(const variant of ['primary','secondary','ghost','danger'])assert.match(css,new RegExp(variant));
  assert.match(css,/data-gf-responsive/);assert.match(css,/prefers-reduced-motion/);assert.match(css,/focus-visible/);
  assert.match(css,/dialog\.gf-dialog/,'Do not constrain legacy viewport overlays as dialog content');
});
test('all existing HTML applications load the same tokens and components',()=>{
  const pages=['dashboard/index','admin/index','admin/login','mobile/index','driver/index','driver/setup','operator/index','agent/index','agent/setup','tracking/index','landing/index','legal/index','legal/privacy-policy','legal/cookie-policy','legal/termini-condizioni','legal/sicurezza','legal/dpa-responsabile-trattamento','legal/subprocessors'];
  for(const page of pages){
    const html=read('static/'+page+'.html');assert.match(html,/data-gf-surface=/,page);
    for(const asset of ['theme.css','components.css','layout.css','design-system.js'])
      assert.equal((html.match(new RegExp('/static/design-system/'+asset.replace('.','\\.'),'g'))||[]).length,1,page+': '+asset);
    assert.ok(html.indexOf('/static/design-system/theme.css')<html.indexOf('/static/design-system/components.css'),page);
    for(const [,source]of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(source,{filename:page});
  }
});
test('component helpers retain plain text and accessible semantic elements',()=>{
  const{api}=runtime();assert.equal(typeof api.enhance,'function');assert.equal(typeof api.announce,'function');
  const payload='<img src=x onerror=alert(1)>',button=api.createButton(payload,{variant:'danger',type:'button'});
  assert.equal(button.tagName,'BUTTON');assert.equal(button.textContent,payload);assert.equal(button.dataset.variant,'danger');
  assert.equal(api.createBadge(payload,'warning').textContent,payload);
  assert.equal(api.createLoading('Caricamento lista').getAttribute('role'),'status');
  const descendants=node=>[node,...node.children.flatMap(descendants)];
  const header=api.pageHeader({title:payload,description:'Dati di esempio',action:button});
  assert.ok(descendants(header).some(node=>node.textContent===payload));assert.ok(descendants(header).includes(button));
  assert.ok(descendants(api.createEmptyState({title:'Nessun cliente',description:payload})).some(node=>node.textContent===payload));
});
test('runtime reads responsive tokens and does not contact application services',()=>{
  const{api}=runtime();assert.deepEqual(JSON.parse(JSON.stringify(api.breakpoints())),{sm:640,md:768,lg:1024,xl:1440});
  const source=read(assets+'design-system.js');
  assert.doesNotMatch(source,/\bfetch\s*\(|XMLHttpRequest|localStorage|sessionStorage|location\.(?:href|assign|replace)|\/api\//);
  new vm.Script(source);
});
test('component catalog replaces the UI kit and stays out of production',()=>{
  assert.equal(fs.existsSync(path.join(root,'docs/design-system/ui-kit.html')),false);
  assert.equal(fs.existsSync(path.join(root,'static/design-system/catalogo.html')),false);
  const main=read('app/main.py');
  assert.match(main,/@app\.get\("\/catalogo", include_in_schema=False\)/);
  assert.match(main,/if IS_PRODUCTION or not design_catalog_page\.is_file\(\):/);
  assert.doesNotMatch(read('Dockerfile'),/COPY\s+(?:\.\s|docs\b)/);
  const kit=read('docs/design-system/catalogo.html');
  assert.match(kit,/<dialog[^>]*class="gf-dialog"/);assert.match(kit,/role="tablist"/);assert.match(kit,/role="switch"/);assert.match(kit,/data-gf-responsive="cards"/);
  assert.match(kit,/data-gf-layout="base"/);assert.match(kit,/\/static\/design-system\/shell\.js/);
  for(const name of ['gf-button','gf-card','gf-panel','gf-table','gf-badge','gf-field','gf-route-panel','gf-stop-list','gf-alert','gf-filters','gf-chip','gf-stat-strip'])
    assert.match(kit,new RegExp('class="'+name+'[\\s"]'),name);
  assert.match(kit,/data-kind="ztl"/);assert.match(kit,/data-kind="tail-lift"/);
  assert.doesNotMatch(kit,/\sstyle="/,'No inline styles in the catalog markup');
  assert.doesNotMatch(kit,/<style[\s>]/,'No page-specific CSS in the catalog');
  for(const [,source]of kit.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(source);
});

test('unified components and shared layout use only theme variables',()=>{
  const components=read(assets+'components.css');
  const unified=components.slice(components.indexOf('Componenti del sistema unificato'));
  assert.ok(unified.length>1000,'Missing unified component section');
  for(const name of ['panel','stat-strip','field','form-grid','route-panel','route-map','stop-list','stop','progress','legend','filters','chip','icon-button','avatar','stack','cluster','grid','notifications','bottom-nav','savebar','overlay','modal','details','setting','stat-card','bar-chart','steps','chat','message','upload','auth','banner','hidden'])
    assert.match(unified,new RegExp('\\.gf-'+name+'(?:__|[\\s:[.#{])'),name);
  assert.doesNotMatch(unified,/#[0-9a-f]{3,8}\b/i,'Colors belong to theme.css');
  assert.doesNotMatch(unified,/font-family:\s*(?!var\(|inherit)["A-Za-z]/,'Fonts belong to theme.css');
  const layout=read(assets+'layout.css');
  const shellCss=layout.slice(layout.indexOf('Layout base condiviso'));
  assert.match(shellCss,/\.gf-shell\{/);assert.match(shellCss,/\.gf-sidebar__count\{/);assert.match(shellCss,/\.gf-shell>\.gf-bottom-nav/);assert.match(shellCss,/\.gf-sidebar__item\[aria-current="page"\]/);assert.match(shellCss,/\.gf-header__title\{/);
  assert.doesNotMatch(shellCss,/#[0-9a-f]{3,8}\b|rgba?\(/i,'Shell colors come from theme.css');
  const shell=read(assets+'shell.js');new vm.Script(shell);
  assert.doesNotMatch(shell,/innerHTML|insertAdjacentHTML|fetch\s*\(|\/api\//);
  for(const item of ['dashboard','company','ordini','clienti','depositi','mezzi','autisti','storico','settings'])
    assert.match(shell,new RegExp("id:'"+item+"'"),item);
  assert.doesNotMatch(shell,/\bid:\s*['"]giro['"]/,'Planning opens after order or customer selection');
  assert.match(read('static/dashboard/index.html'),/<section id="tab-giro"/);
});

test('derived operational badges follow real portal classes and state transitions',()=>{
  const{api}=runtime();
  for(const[names,status]of[
    ['rc-badge rb-cancel','danger'],['rc-badge rb-prog','warning'],
    ['rc-badge rb-done','success'],['rc-badge rb-corso','info'],
    ['fleet-status available','success'],['customer-status pending','warning']
  ]){
    const badge=element('span');badge.classList.add(...names.split(' '));
    const root={querySelectorAll:selector=>selector.includes('.rc-badge')?[badge]:[]};
    api.enhance(root);assert.equal(badge.dataset.status,status,names);
    if(names==='rc-badge rb-prog'){
      badge.classList.remove('rb-prog');badge.classList.add('rb-corso');
      api.enhance(root);assert.equal(badge.dataset.status,'info','Update derived state after rendering');
    }
  }
});


test('dashboard reference view shares tokens and retains live API connections',()=>{
  const tokens=read(assets+'theme.css');
  assert.match(tokens,/--gf-focus-ring\s*:\s*0 0 0 3px rgba\(22,101,255,\.17\)/i);
  assert.match(tokens,/--gf-sidebar-width\s*:\s*244px/);
  // La dashboard usa i componenti del sistema: striscia numeri, pannello giro, legenda, avanzamento e fermate.
  const components=read(assets+'components.css');
  for(const selector of ['.gf-stat-strip','.gf-route-panel','.gf-route-panel__canvas','.gf-crew','.gf-legend','.gf-progress','.gf-stop-list']){
    assert.ok(components.includes(selector),'Missing dashboard component '+selector);
  }
  assert.match(components,/\.gf-route-panel\{[^}]*grid-template-columns:/);
  const html=read('static/dashboard/index.html');
  const dashboard=html.slice(html.indexOf('<section id="tab-dashboard"'),html.indexOf('<section id="tab-dashboard-scheduled"'));
  for(const id of ['dashTodayScheduled','dashTodayProgress','dashTodayCompletedDeliveries','dashBusyDrivers','dashBusyVehicles','dashScheduledBadge','dashInProgressBadge','dashCompletedBadge','dashScheduledList','dashCompletedList','dashVehicleStatus','dashDriverStatus','gfRefRouteDrawing','gfRefStopList']){
    assert.equal((dashboard.match(new RegExp('id="'+id+'"','g'))||[]).length,1,'Missing or duplicate dashboard '+id);
  }
  for(const phrase of ['class="gf-stat-strip"','class="gf-route-panel" id="gfRefHeroWrap"','class="gf-stop-list" id="gfRefStopList"','class="gf-legend hidden" id="gfRefRouteLegend"'])
    assert.match(dashboard,new RegExp(phrase));
  assert.match(dashboard,/onclick="openDashboardInProgressPage\(\)"/);
  // Il vecchio foglio reference-theme.css è stato eliminato: la home usa solo i componenti.
  assert.doesNotMatch(html,/reference-theme\.css/);
  const core=read('static/dashboard/js/core.js');
  assert.match(core,/function renderGFReferenceDashboardHero\(summary\)/);
  assert.match(core,/api\(`\/api\/routes\/\$\{routeId\}`\)/);
  assert.match(core,/scheduled\.slice\(0,3\)\.map/);
  assert.match(core,/completedToday\.slice\(0,3\)\.map/);
  assert.match(core,/progress\.slice\(1,3\)\.map/);
  const routeItem=core.slice(core.indexOf('function dashRouteItem'),core.indexOf('function gfTimeFromIso'));
  assert.match(routeItem,/class="gf-list-item" role="button"/);
  assert.match(routeItem,/class="gf-progress__top"/);
  assert.match(routeItem,/issues\.length\?`<div class="gf-cluster">/);
  new vm.Script(core);
});

test('company profile uses the workspace topbar and keeps billing addresses always open',()=>{
  const html=read('static/dashboard/index.html');
  assert.match(html,/id="workspacePageTitle">Buongiorno<\/h1>/);
  assert.match(html,/id="workspacePageSubtitle"/);
  // Lo stato del profilo vive nell'intestazione condivisa e compare solo su Azienda.
  assert.match(html,/id="companyTopbarStatus" class="gf-cluster gf-hidden" data-show-on-tabs="company"/);
  assert.equal((html.match(/id="companyConfiguredBadge"/g)||[]).length,1);
  assert.equal((html.match(/id="showOnboardingBtn"/g)||[]).length,1);
  const company=html.slice(html.indexOf('<section id="tab-company"'),html.indexOf('<section id="tab-dashboard"'));
  assert.doesNotMatch(company,/<div class="dash-hero-row">/);
  assert.doesNotMatch(company,/<details[^>]*companyAddressesTitle/);
  assert.match(company,/<section class="gf-panel" aria-labelledby="companyAddressesTitle"/);
  assert.match(company,/id="companyLegalAddressInput"/);
  assert.match(company,/id="companyBillingAddressInput"/);

  const navigation=read('static/dashboard/js/navigation.js');
  new vm.Script(navigation);
  assert.match(navigation,/function syncWorkspaceTopbar\(name\)/);
  assert.match(navigation,/function dashboardGreetingTitle\(\)/);
  assert.match(navigation,/name==="dashboard"\?dashboardGreetingTitle\(\):meta\.title/);
  assert.match(navigation,/const WORKSPACE_TOPBAR_META =/);
  assert.match(navigation,/company:\s*\{[\s\S]*title: "Profilo azienda"/);
  assert.match(navigation,/classList\.toggle\("gf-company-page-active",company\)/);
  assert.match(navigation,/syncWorkspaceTopbar\(name\)/);

  // Il titolo è nell'intestazione condivisa; il pulsante "Nuovo giro" non compare su Azienda.
  assert.match(html,/id="companySaveBar" class="gf-savebar hidden" data-floating/);
  assert.match(html,/data-variant="primary" data-new-route-button data-show-on-tabs="dashboard"/);
});


test('company edits are saved from the topbar and bottom save actions are removed',()=>{
  const html=read('static/dashboard/index.html');
  assert.match(html,/id="companySaveBar" class="gf-savebar hidden" data-floating/);
  assert.match(html,/id="companySaveChangesBtn"[^>]*onclick="saveCompanyProfile\(\)"/);
  assert.match(html,/id="companyDiscardChangesBtn"[^>]*onclick="cancelCompanyProfileChanges\(\)"/);
  assert.doesNotMatch(html,/class="company-save-actions"/);
  assert.doesNotMatch(html,/>Salva profilo azienda</);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/let companyProfileDirtyV29 = false/);
  assert.match(core,/function getCompanyProfilePayload\(\)/);
  assert.match(core,/function updateCompanyProfileDirtyStateV29\(\)/);
  assert.match(core,/function blockCompanyNavigationForUnsavedChanges\(\)/);
  assert.match(core,/window\.addEventListener\("beforeunload"/);
  assert.match(core,/bindCompanyProfileDirtyTracking\(\)/);
  assert.match(core,/setCompanyProfileBaselineV29\(\)/);

  const navigation=read('static/dashboard/js/navigation.js');
  assert.match(navigation,/name !== "company"[^\n]*blockCompanyNavigationForUnsavedChanges/);

  const companyCss=read('static/dashboard/css/company.css');
  // La barra di salvataggio è il componente gf-savebar: il foglio Azienda non la ridisegna più.
  const components=read('static/design-system/components.css');
  assert.match(components,/\.gf-savebar\{/);
  assert.doesNotMatch(companyCss,/\.company-save-bar\s*\{|company-save-actions/);
});


test('dashboard salutation uses company name and never silently substitutes username',()=>{
  const navigation=read('static/dashboard/js/navigation.js');
  const FixedDate=class extends Date{
    constructor(...args){super(...(args.length?args:['2026-10-18T07:00:00Z']));}
  };
  const greeting=(user,companyCache='')=>vm.runInNewContext(
    navigation+';dashboardGreetingTitle()',
    {
      Date:FixedDate,
      currentSessionUser:user,
      localStorage:{getItem:key=>key==='girofacile_company_name'?companyCache:
        key==='girofacile_account_name'?'Mario':null}
    }
  );
  assert.equal(greeting({username:'Mario',company_name:'Trasporti Rossi SRL'},'Mario'),'Buongiorno, Trasporti Rossi SRL');
  assert.equal(greeting({username:'Mario',company_name:''},'Logistica Firenze'),'Buongiorno, Logistica Firenze');
  assert.equal(greeting({username:'Mario',company_name:''},'Mario'),'Buongiorno');
  assert.match(navigation,/currentSessionUser\?\.company_name/);
  assert.match(read('static/dashboard/index.html'),/navigation\.js\?v=[\w-]+/);
});

test('company name and account username use separate identity storage',()=>{
  const core=read('static/dashboard/js/core.js');
  assert.match(core,/const accountName = localStorage\.getItem\("girofacile_account_name"\)/);
  assert.match(core,/const companyName = localStorage\.getItem\("girofacile_company_name"\)/);
  assert.match(core,/setText\("topProfileName", companyName\)/);
  assert.match(core,/set\("profileName", accountName\)/);
  assert.match(core,/localStorage\.setItem\("girofacile_account_name", data\.username/);
  assert.match(core,/localStorage\.setItem\("girofacile_company_name", data\.company_name/);
  assert.doesNotMatch(core,/localStorage\.setItem\("girofacile_profile_name"/);
  const loadCompany=core.slice(core.indexOf('async function loadCompanyProfile'),core.indexOf('async function saveCompanyProfile'));
  assert.doesNotMatch(loadCompany,/girofacile_profile_photo/);
});


test('workspace topbar keeps modern notification and account actions',()=>{
  const html=read('static/dashboard/index.html');
  const topbar=html.slice(html.indexOf('<div class="gf-header__actions">'),html.indexOf('</header>'));
  assert.match(topbar,/id="notificationBellBtn" class="gf-icon-button"[^>]*><svg/);
  assert.doesNotMatch(topbar,/>🔔</);
  assert.doesNotMatch(topbar,/id="logoutBtn"/);
  assert.match(topbar,/class="gf-header__user" onclick="openProfilePanel\(\)"/);

  const profile=html.slice(html.indexOf('<div id="profileOverlay"'),html.indexOf('<!-- COOKIE NOTICE'));
  assert.match(profile,/id="logoutBtn" class="gf-button hidden" data-variant="ghost"/);
  assert.match(profile,/class="gf-modal__footer"/);
  assert.doesNotMatch(profile,/btn-danger/);
  assert.equal((html.match(/id="logoutBtn"/g)||[]).length,1);

  const components=read(assets+'components.css');
  assert.match(components,/\.gf-notifications__panel\{/);
  assert.match(components,/\.gf-icon-button svg,/);
});

test('account profile modal follows the workspace design system',()=>{
  const html=read('static/dashboard/index.html');
  const profile=html.slice(html.indexOf('<div id="profileOverlay"'),html.indexOf('<!-- COOKIE NOTICE'));
  assert.match(profile,/<div id="profileOverlay" class="gf-overlay hidden" onclick="closeProfilePanel\(event\)">/);
  assert.match(profile,/class="gf-modal" data-size="lg" role="dialog" aria-modal="true"/);
  assert.match(profile,/aria-labelledby="profileIdentityHeading"/);
  assert.match(profile,/aria-labelledby="profilePlanHeading"/);
  assert.match(profile,/id="planStatusBox" class="gf-alert" data-status="info"/);
  assert.match(profile,/id="btnPlanActive"[^>]*onclick="openPlanAccountPage\(\)"/);
  assert.match(profile,/onclick="openBillingPanel\(\)">Fatturazione</);
  assert.doesNotMatch(profile,/\sstyle="/);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/const setPlanStatusTone = \(tone, icon\)/);
  assert.match(core,/setPlanStatusTone\("is-success", "✓"\)/);
  assert.doesNotMatch(core,/statusBox\.style\.background/);
  assert.match(core,/<div class="gf-details__item"><dt>\$\{r\.label\}<\/dt><dd>\$\{maxLabel\}<\/dd><\/div>/);

  const components=read(assets+'components.css');
  assert.match(components,/\.gf-modal\[data-size="lg"\]\{/);
  assert.match(components,/\.gf-details\[data-layout="rows"\]/);
});


test('workspace sidebar uses the GiroFacile brand artwork',()=>{
  const html=read('static/dashboard/index.html');
  // Marchio del layout base: simbolo SVG con i colori del tema e nome GiroFacile.
  const brand=html.slice(html.indexOf('<a class="gf-sidebar__brand"'),html.indexOf('<nav class="gf-sidebar__nav"'));
  assert.match(brand,/class="gf-sidebar__mark"[^>]*aria-label="Logo GiroFacile"/);
  assert.match(brand,/class="gf-sidebar__brand-name">GiroFacile<\/span>/);
  assert.doesNotMatch(brand,/#[0-9a-f]{3,6}\b/i);
});


test('workspace legal links live in navigation and advanced legal docs live in support',()=>{
  const html=read('static/dashboard/index.html');
  const sidebarTag=[...html.matchAll(/<aside\b[^>]*>/g)].find(match=>(match[0].match(/\bclass="([^"]*)"/)?.[1] || '').split(/\s+/).includes('gf-sidebar'));
  assert.ok(sidebarTag,'Workspace sidebar (layout base)');
  const sidebarEnd=html.indexOf('</aside>',sidebarTag.index);
  assert.ok(sidebarEnd>sidebarTag.index,'Sidebar closing tag');
  const sidebar=html.slice(sidebarTag.index,sidebarEnd);
  assert.match(sidebar,/class="gf-sidebar__footer"/);
  assert.match(sidebar,/© 2026 GiroFacile · v3\.11\.0/);
  assert.match(sidebar,/href="\/privacy-policy"[^>]*>Privacy<\/a>/);
  assert.match(sidebar,/href="\/termini-condizioni"[^>]*>Termini<\/a>/);
  assert.match(sidebar,/href="\/cookie-policy"[^>]*>Cookie<\/a>/);
  assert.doesNotMatch(sidebar,/Sicurezza|DPA|Fornitori|>API</);
  assert.doesNotMatch(html,/class="dashboard-legal-footer"/);

  // Su smartphone le stesse voci legali restano nella sidebar, aperta dal pulsante "Altro".
  const mobile=html.slice(html.indexOf('id="gfMobileBottomNavV62"'),html.indexOf('</nav>',html.indexOf('id="gfMobileBottomNavV62"')));
  assert.match(mobile,/onclick="toggleMobileMoreMenuV62\(\)"/);
  assert.match(read('static/dashboard/js/core.js'),/function toggleMobileMoreMenuV62\(\)\{ window\.GFShell\?\.open\(\); \}/);

  const core=read('static/dashboard/js/core.js');
  const support=core.slice(core.indexOf('function ensureSupportModalV60'),core.indexOf('function openSupportPanelV49'));
  assert.match(support,/data-legal="support"/);
  assert.match(support,/href="\/sicurezza"/);
  assert.match(support,/href="\/dpa-responsabile-trattamento"/);
  assert.match(support,/href="\/subprocessors"/);

  const layout=read(assets+'layout.css');
  assert.match(layout,/\.gf-sidebar__links\{/);

  assert.match(support,/wrap.className = "gf-overlay hidden"/);
});


test('dashboard resources use reference rows and keep both navigation actions',()=>{
  const html=read('static/dashboard/index.html');
  const dashboard=html.slice(html.indexOf('<section id="tab-dashboard"'),html.indexOf('<section id="tab-dashboard-scheduled"'));
  assert.match(dashboard,/data-variant="link" onclick="showTab\('mezzi'\)">Tutti i mezzi/);
  assert.match(dashboard,/data-variant="link" onclick="showTab\('autisti'\)">Tutti gli autisti/);
  assert.match(dashboard,/id="dashVehicleStatus"/);
  assert.match(dashboard,/id="dashDriverStatus"/);
  // Le risorse sono tabelle del sistema con intestazioni Mezzo/Targa/Stato e Autista/Patente/Stato.
  assert.match(dashboard,/<th scope="col">Mezzo<\/th><th scope="col">Targa<\/th><th scope="col">Stato<\/th><\/tr><\/thead><tbody id="dashVehicleStatus">/);
  assert.match(dashboard,/<th scope="col">Autista<\/th><th scope="col">Patente<\/th><th scope="col">Stato<\/th><\/tr><\/thead><tbody id="dashDriverStatus">/);
  const core=read('static/dashboard/js/core.js');
  assert.match(core,/vehicles\.slice\(0,4\)\.map/);
  assert.match(core,/drivers\.slice\(0,4\)\.map/);
});

test('dashboard completed-deliveries KPI has fixed copy and uses actual completion events',()=>{
  const html=read('static/dashboard/index.html');
  const dashboard=html.slice(html.indexOf('<section id="tab-dashboard"'),html.indexOf('<section id="tab-dashboard-scheduled"'));
  assert.match(dashboard,/>Consegne completate<\/span><strong class="gf-stat-strip__value" id="dashTodayCompletedDeliveries">0<\/strong>/);
  assert.match(dashboard,/id="dashTodayCompletedDeliveries">0<\/strong><small class="gf-stat-strip__unit">dagli autisti oggi<\/small>/);
  assert.doesNotMatch(dashboard,/Consegne<\/span> merce/);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/api\("\/api\/dashboard\/completed-deliveries-today"\)/);
  assert.match(core,/const completedDeliveriesToday = Number\(completedDeliveriesSummary\?\.count\) \|\| 0/);

  const routes=read('app/routers/routes.py');
  assert.match(routes,/@router\.get\("\/api\/dashboard\/completed-deliveries-today"\)/);
  assert.match(routes,/DeliveryStatus\.status == "completata"/);
  assert.match(routes,/DeliveryStatus\.completata_il >= start/);
  assert.match(routes,/RoutePlan\.user_id == user\.id/);
});


test('account password UI stays compact and uses shared visual tokens',()=>{
  const html=read('static/dashboard/index.html');
  const profile=html.slice(html.indexOf('<div id="profileOverlay"'),html.indexOf('<!-- COOKIE NOTICE'));
  assert.match(profile,/class="gf-setting"[\s\S]*<strong>Cambio password<\/strong>/);
  assert.match(profile,/id="profileSecurityOpenBtn"[^>]*>Modifica<\/button>/);
  assert.match(profile,/id="profilePasswordChangePanel" class="gf-card gf-stack hidden"/);
  assert.doesNotMatch(profile,/Credenziali protette|Password dimenticata|profile-password-help|profile-password-collapse/);

  assert.doesNotMatch(profile,/linear-gradient|#cfe0ff|#fff7ed|#9a5a16|\sstyle="/);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/profileSecurityOpenBtn/);
  assert.match(core,/setAttribute\("aria-expanded", visible \? "true" : "false"\)/);
});


test('company profile visually follows the dashboard panel language',()=>{
  // Le cinque sezioni del profilo sono pannelli del sistema con icona neutra e campi gf-field.
  const html=read('static/dashboard/index.html');
  const company=html.slice(html.indexOf('<section id="tab-company"'),html.indexOf('<section id="tab-dashboard"'));
  for(const id of ['companyIdentityTitle','companyContactsTitle','companyFiscalTitle','companyOperationsTitle','companyAddressesTitle'])
    assert.match(company,new RegExp('<section class="gf-panel" aria-labelledby="'+id+'"'),id);
  assert.equal((company.match(/class="gf-stat-card__icon" data-tone="neutral"/g)||[]).length,5);
  assert.doesNotMatch(company,/company-card-v29|company-field|style="/);
  assert.match(company,/class="gf-field" for="companyNameInput"/);
  const components=read(assets+'components.css');
  assert.match(components,/\.gf-panel\{[^}]*border:var\(--gf-border\)/);
  assert.doesNotMatch(read('static/dashboard/js/company-profile.js'),/strokeDashoffset|insertBefore\(hero/);
});


test('resource directories keep titles in the topbar and create actions inside the list panel',()=>{
  const html=read('static/dashboard/index.html');
  assert.doesNotMatch(html,/workspaceDirectoryTopbarActions|workspaceDirectoryPrimaryAction|workspaceDirectorySecondaryAction/);

  for(const tab of ['clienti','depositi','mezzi','autisti','agenti']){
    const start=html.indexOf('<section id="tab-'+tab+'"');
    assert.ok(start>=0,tab);
    const next=html.indexOf('<section id="tab-',start+20);
    const block=html.slice(start,next>start?next:html.length);
    // Sezione convertita: niente titolo in pagina (è nell'intestazione) e azione nel pannello.
    const converted=/class="gf-panel__header"/.test(block);
    if(converted){
      assert.doesNotMatch(block,/<h1\b/,tab+' title stays in the topbar');
    }else{
      assert.match(block,/gf-directory-page/,tab+' page template');
      assert.match(block,/gf-directory-title/,tab+' mobile title fallback');
      assert.match(block,/gf-directory-head-actions/,tab+' panel actions');
    }
  }

  const customers=html.slice(html.indexOf('<section id="tab-clienti"'),html.indexOf('<section id="tab-depositi"'));
  // Clienti: importazione e nuovo cliente stanno nell'intestazione dell'elenco, come in Ordini.
  assert.doesNotMatch(html,/customersTopbarActionsHost/);
  assert.match(customers,/id="customerListTitle"[^]*?id="customersPanelActions"[^]*?openCustomerImportModal\(\)[^]*?openCustomerDrawer\(null,'new'\)[^]*?<\/header>/);
  const deposits=html.slice(html.indexOf('<section id="tab-depositi"'),html.indexOf('id="depositOverlay"'));
  assert.match(deposits,/class="gf-panel__header"[^]*\+ Nuovo deposito/);
  const vehicles=html.slice(html.indexOf('<section id="tab-mezzi"'),html.indexOf('<section id="tab-autisti"'));
  assert.match(vehicles,/class="gf-panel__header"[^]*\+ Nuovo mezzo/);
  const drivers=html.slice(html.indexOf('<section id="tab-autisti"'),html.indexOf('<section id="tab-storico"'));
  assert.match(drivers,/class="gf-panel__header"[^]*\+ Nuovo autista/);
  const agents=html.slice(html.indexOf('<section id="tab-agenti"'),html.indexOf('<section id="tab-report"'));
  assert.match(agents,/class="gf-panel__header"[^]*\+ Nuovo agente/);

  const navigation=read('static/dashboard/js/navigation.js');
  new vm.Script(navigation);
  for(const [name,title] of [['clienti','Clienti'],['depositi','Depositi'],['mezzi','Mezzi'],['autisti','Autisti'],['agenti','Agenti']]){
    assert.match(navigation,new RegExp(name+':[\\s\\S]*?title: "'+title+'"'),name+' topbar title');
  }
  assert.doesNotMatch(navigation,/WORKSPACE_DIRECTORY_ACTIONS|syncWorkspaceDirectoryActions|workspaceDirectoryPrimaryAction/);

  const layout=read(assets+'layout.css');
  // Nel layout base il titolo è sempre nell'intestazione, tranne le sezioni elencate in data-hide-on-tabs.
  const hidden=(html.match(/class="gf-header__titles" data-hide-on-tabs="([^"]*)"/)||[])[1];
  assert.ok(hidden!==undefined,'header titles');
  for(const tab of ['clienti','depositi','mezzi','autisti','agenti']){
    assert.ok(!hidden.split(' ').includes(tab),tab+' topbar visibility');
  }
  assert.doesNotMatch(layout,/workspace-directory-topbar-actions/);

  // Le azioni delle anagrafiche sono nei pannelli: workspace.css contiene solo gli adattatori dei moduli condivisi.
  const workspace=read(assets+'workspace.css');
  assert.doesNotMatch(workspace,/#tab-(clienti|depositi|mezzi|autisti|agenti)/);

  assert.match(vehicles,/id="fleetMetricTotal"/);
  assert.match(drivers,/id="driverTableWrap"/);
  assert.match(agents,/id="agentCards"/);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/localStorage\?\.getItem\('gfDepositView'\)/);
  assert.match(core,/localStorage\?\.getItem\('gfAgentView'\)/);
});


test('every page summary bar uses the shared strip with topic icons and colours',()=>{
  // Barra dei numeri unica (approvata il 18 ottobre 2026): stessa struttura e icone colorate per argomento.
  const html=read('static/dashboard/index.html');
  for(const tab of ['dashboard','collaboratori','ordini','clienti','agenti','depositi','mezzi','autisti']){
    const start=html.indexOf('<section id="tab-'+tab+'"');
    assert.ok(start>=0,tab+' section');
    const section=html.slice(start,html.indexOf('<section id="tab-',start+20));
    assert.match(section,/class="gf-stat-strip" data-icons="side"|id="ordersMetrics" class="gf-stat-strip" data-icons="side"|class="gf-stat-strip" data-icons="side" id="customerKpis"/,tab+' summary bar');
    // Le anagrafiche non hanno più schede numeriche separate: solo la barra.
    if(tab!=='dashboard')assert.doesNotMatch(section,/gf-stat-card/,tab+' no separate KPI cards');
    assert.doesNotMatch(section,/(customer|deposit|gf-directory)-metric-icon|stat-icon/,tab+' no legacy icons');
  }
  const components=read(assets+'components.css');
  assert.match(components,/\.gf-stat-strip\[data-icons="side"\] \.gf-stat-strip__icon\{grid-row:1\/span 2/);
  for(let i=1;i<=6;i++)assert.ok(components.includes('.gf-stat-strip__icon[data-tone="'+i+'"]{background:var(--gf-color-avatar-'+i+'-bg)'),'tono '+i);
  assert.match(components,/\.gf-stat-strip__icon\[data-tone="neutral"\]\{background:var\(--gf-color-bg\);color:var\(--gf-color-muted\)\}/);
  assert.match(read('static/dashboard/js/orders.js'),/class="gf-stat-strip__icon" data-tone="\$\{meta\.tone\}"/);
  assert.match(read('static/dashboard/js/customers.js'),/class="gf-stat-strip__icon" data-tone="/);
});


test('vehicle photo fallback uses a neutral outline icon instead of the truck emoji',()=>{
  const vehicles=read('static/dashboard/js/vehicles.js');
  assert.match(vehicles,/function vehiclePlaceholderSvg\(extraClass=''/);
  // L'icona usa la classe gf-icon del sistema (contorno, colore del testo).
  assert.match(vehicles,/class="gf-icon fleet-vehicle-placeholder-icon/);
  assert.match(vehicles,/function setVehiclePhotoPreview\(\)/);
  const fleetPhoto=vehicles.slice(vehicles.indexOf('function fleetPhoto'),vehicles.indexOf('function fleetStatus'));
  assert.doesNotMatch(fleetPhoto,/🚚/);
  assert.match(fleetPhoto,/fleet-photo-placeholder/);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/setVehiclePhotoPreview\(\)/);
  assert.doesNotMatch(core,/setImagePreview\("vehiclePhotoPreview","vPhotoUrl","🚚"\)/);

  const html=read('static/dashboard/index.html');
  const preview=html.slice(html.indexOf('id="vehiclePhotoPreview"'),html.indexOf('id="vPhotoFile"'));
  assert.match(preview,/gf-icon fleet-vehicle-placeholder-icon is-preview/);
  assert.doesNotMatch(preview,/🚚/);

  assert.match(read(assets+'components.css'),/\.gf-icon\{[^}]*fill:none;stroke:currentColor/);
});


test('planning page uses the shared topbar and dashboard visual language',()=>{
  const navigation=read('static/dashboard/js/navigation.js');
  assert.match(navigation,/giro:\s*\{[\s\S]*title: "Pianificazione giro consegne"[\s\S]*subtitle: "Seleziona clienti, configura risorse e calcola il percorso prima della programmazione\."/);


  // Layout C4: testata con nome automatico e numeri del giro, fermate apribili, scelta con due card,
  // sezioni a tutta larghezza con badge di stato; nessuna breve descrizione sotto i titoli.
  const html=read('static/dashboard/index.html');
  const planningHtml=html.slice(html.indexOf('<section id="tab-giro"'),html.indexOf('<section id="tab-route-preview"'));
  assert.match(planningHtml,/id="routeAutoNameTitle"/);
  assert.match(planningHtml,/<input type="hidden" id="routeName">/);
  assert.match(planningHtml,/class="gf-stat-strip" aria-label="Riepilogo pianificazione"/);
  for(const id of ['statDeliveries','statColli','statWarnings','statFuel'])assert.match(planningHtml,new RegExp('class="gf-stat-strip__value" id="'+id+'"'));
  assert.match(planningHtml,/aria-controls="deliveryTableArea" onclick="toggleRouteStopsTable\(this\)">Visiona tutte le fermate</);
  assert.equal((planningHtml.match(/data-planning-mode-card/g)||[]).length,2);
  assert.match(planningHtml,/<select class="gf-select" id="planningMode" hidden/);
  for(const n of [1,2])assert.match(planningHtml,new RegExp('id="planStepStatus'+n+'" class="gf-badge"'));
  assert.doesNotMatch(planningHtml,/<h1|page-title-row|style="/);
  assert.doesNotMatch(planningHtml,/<header class="gf-panel__header"><div><h2 class="gf-panel__title"[^>]*>[^<]*<\/h2><p class="gf-muted">/);
  const core=read('static/dashboard/js/core.js');
  assert.match(core,/badge\.dataset\.status = state === "complete" \? "success"/);
});


test('planning fuel KPI stays empty until a vehicle is selected',()=>{
  const html=read('static/dashboard/index.html');
  const planning=html.slice(html.indexOf('<section id="tab-giro"'),html.indexOf('<section id="tab-route-preview"'));
  assert.match(planning,/id="statFuel"><\/strong>/);
  assert.match(planning,/id="statFuelHint">Seleziona un mezzo<\/small>/);
  assert.doesNotMatch(planning,/id="statFuel">€ \/ L/);

  const core=read('static/dashboard/js/core.js');
  const start=core.indexOf('function updateDashboardStats()');
  const end=core.indexOf('async function api',start);
  const block=core.slice(start,end);
  assert.match(block,/if\(!sv\)\{[\s\S]*setText\("statFuel", ""\)[\s\S]*setText\("statFuelHint", "Seleziona un mezzo"\)/);
  assert.match(block,/const price=electric \? \(document\.getElementById\("electricityPrice"\)/);
  assert.match(block,/setText\("statFuel", price \? price\+" "\+unit : ""\)/);
  assert.match(block,/setText\("statFuelHint", price \? "Prezzo impostato" : "Prezzo da impostare"\)/);
});


test('login page uses the shared access screen with the same content and actions',()=>{
  const html=read('static/dashboard/index.html');
  const login=html.slice(html.indexOf('<section id="loginCard"'),html.indexOf('<div id="app"'));
  // Componente approvato del catalogo al posto del vecchio login.css.
  assert.match(login,/<section id="loginCard" class="gf-auth">/);
  assert.doesNotMatch(html,/\/static\/dashboard\/css\/login\.css/);
  assert.doesNotMatch(login,/\sstyle="/);
  // Stessi contenuti: tre punti di forza, informazioni legali, accesso, registrazione e recupero.
  for(const feature of ['Pianifica','Monitora','Analizza']) assert.match(login,new RegExp('<strong>'+feature+'</strong>'));
  assert.match(login,/aria-label="Informazioni legali"/);
  for(const [href,label] of [['privacy-policy','Privacy'],['termini-condizioni','Termini'],['cookie-policy','Cookie']])
    assert.match(login,new RegExp('href="/'+href+'"[^>]*>'+label+'</a>'));
  assert.match(login,/id="loginUser"/);assert.match(login,/id="loginPass"[^>]*type="password"/);
  assert.match(login,/onclick="login\(\)"[^>]*data-variant="primary">Accedi a GiroFacile →</);
  assert.match(login,/onclick="toggleSignup\(true\)">Registrati gratis</);
  assert.match(login,/oppure <button type="button" id="forgotPasswordBtn"/);
  // Registrazione a passaggi con il componente gf-steps; stato gestito con aria-current.
  assert.equal((login.match(/class="gf-step"/g)||[]).length,4);
  assert.equal((login.match(/data-signup-step="\d"/g)||[]).length,4);
  const core=read('static/dashboard/js/core.js');
  assert.match(core,/dot\.setAttribute\("aria-current", "step"\)/);
  assert.doesNotMatch(core,/loginCard\.style\.display|app\.style\.display/);
  const components=read(assets+'components.css');
  assert.match(components,/\.gf-auth__card\[data-size="lg"\]\{/);
});

test('every stylesheet resolves its referenced custom properties',()=>{
  const files=fs.readdirSync(path.join(root,'static'),{recursive:true}).filter(name=>name.endsWith('.css'));
  assert.ok(files.length>0,'Application stylesheets');
  const sheets=files.map(name=>({name,css:read(path.join('static',name))}));
  const defined=new Set(sheets.flatMap(({css})=>[...css.matchAll(/(--[\w-]+)\s*:/g)].map(match=>match[1])));
  for(const {name,css} of sheets){
    for(const match of css.matchAll(/var\(\s*(--[\w-]+)/g))
      assert.ok(defined.has(match[1]),name+': undefined '+match[1]);
  }
});

test('selection and unsaved-change bars share the floating savebar of the company profile',()=>{
  const html=read('static/dashboard/index.html');
  for(const id of ['companySaveBar','settingsSaveBar','customerBulkBar','ordersSelection'])
    assert.match(html,new RegExp('id="'+id+'"[^>]*|class="gf-savebar[^"]*"[^>]*id="'+id+'"'),id);
  for(const re of [/id="companySaveBar" class="gf-savebar hidden" data-floating/,/id="settingsSaveBar" class="gf-savebar hidden" data-floating/,/class="gf-savebar hidden" data-floating id="customerBulkBar"/,/id="ordersSelection" class="gf-savebar" data-floating/])assert.match(html,re);
  assert.match(read('static/dashboard/js/fleet-review.js'),/class="gf-savebar" data-floating/);
  const components=read(assets+'components.css');
  assert.match(components,/\.gf-savebar\[data-floating\]\{\s*position:fixed/);
  assert.match(components,/\.gf-savebar\[data-floating\] \.gf-dropdown \[data-gf-menu\]\{top:auto;bottom:/);
  // Lo stile non è più scritto solo per la pagina Azienda.
  assert.doesNotMatch(read('static/dashboard/css/company.css'),/#companySaveBar/);
});
