const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const assets = 'static/design-system/';
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
test('tokens centrally define palette, geometry, spacing, typography and breakpoints',()=>{
  const css=read(assets+'tokens.css');
  for(const token of ['color-primary','color-bg','color-surface','color-text','color-muted','color-border','color-success','color-success-bg','color-warning','color-warning-bg','color-danger','color-danger-bg','color-info','color-info-bg','radius-sm','radius-md','radius-lg','shadow-sm','control-height','touch-height','font-size-base','font-size-header','breakpoint-sm','breakpoint-md','breakpoint-lg','breakpoint-xl','space-1','space-2','space-3','space-4','space-6','space-8'])
    assert.match(css,new RegExp('--gf-'+token+'\\s*:'));
  assert.match(css,/--gf-color-primary\s*:\s*#2563eb/i);
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
    for(const asset of ['tokens.css','components.css','layout.css','design-system.js'])
      assert.equal((html.match(new RegExp('/static/design-system/'+asset.replace('.','\\.'),'g'))||[]).length,1,page+': '+asset);
    assert.ok(html.indexOf('/static/design-system/tokens.css')<html.indexOf('/static/design-system/components.css'),page);
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
test('developer UI kit remains outside static hosting and deployable image',()=>{
  assert.ok(fs.existsSync(path.join(root,'docs/design-system/ui-kit.html')));
  assert.equal(fs.existsSync(path.join(root,'static/design-system/ui-kit.html')),false);
  assert.doesNotMatch(read('app/main.py'),/ui-kit|design-system\/ui/);
  assert.doesNotMatch(read('Dockerfile'),/COPY\s+(?:\.\s|docs\b)/);
  const kit=read('docs/design-system/ui-kit.html');
  assert.match(kit,/<dialog[^>]*class="gf-dialog"/);assert.match(kit,/role="tablist"/);assert.match(kit,/role="switch"/);assert.match(kit,/data-gf-responsive="cards"/);
  for(const [,source]of kit.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g))new vm.Script(source);
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


test('dashboard reference view uses shared tokens and bounded overview previews',()=>{
  const tokens=read(assets+'tokens.css');
  assert.match(tokens,/--gf-focus-ring\s*:\s*0 0 0 3px rgba\(37,99,235,\.16\)/i);
  assert.doesNotMatch(tokens,/--gf-focus-ring[^;]*11,99,246/i);

  const dashboard=read('static/dashboard/css/dashboard.css');
  assert.match(dashboard,/--dash-ink:var\(--gf-color-text/);
  assert.match(dashboard,/font-family:var\(--gf-font-family/);
  assert.match(dashboard,/outline:2px solid var\(--gf-color-primary/);

  const workspace=read(assets+'workspace.css');
  const home=workspace.slice(workspace.indexOf('/* Home dashboard follows'));
  assert.match(home,/\.dash-kpi-resources/);
  assert.match(home,/\.dash-list-card\{min-height:390px/);
  assert.doesNotMatch(home,/\.dash-route-list\{[^}]*overflow:auto/);
  assert.match(home,/\.dash-link-btn\{[^}]*background:var\(--gf-color-nav\)!important/);
  assert.doesNotMatch(home,/nth-child\(2\)>\.dash-link-btn/);
  assert.match(home,/\.dash-kpi-card\{[^}]*display:block!important[^}]*min-height:168px!important[^}]*padding:24px 28px!important/);
  assert.match(home,/\.dash-kpi-title\{[^}]*max-width:calc\(100% - 76px\)[^}]*font-size:var\(--gf-font-lg\)!important/);
  assert.match(home,/\.dash-kpi-standard \.dash-kpi-icon\{[^}]*position:absolute[^}]*top:24px[^}]*right:24px/);
  assert.match(home,/\.dash-kpi-metric\{[^}]*margin-top:auto/);
  assert.match(home,/\.dash-busy-split>div\{[^}]*position:relative[^}]*padding:0 10px 0 54px/);
  assert.match(home,/\.dash-resource-symbol\{[^}]*position:absolute[^}]*left:8px[^}]*width:40px[^}]*transform:translateY\(-50%\)/);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/scheduled\.slice\(0,3\)\.map/);
  assert.match(core,/progress\.slice\(0,3\)\.map/);
  const routeItem=core.slice(core.indexOf('function dashRouteItem'),core.indexOf('function gfTimeFromIso'));
  assert.match(routeItem,/dash-route-context/);
  assert.match(routeItem,/dash-route-progress-line/);
  assert.match(routeItem,/dash-route-issues/);
  assert.doesNotMatch(routeItem,/dash-live-grid|dash-next-stop/);
  assert.match(core,/completedToday\.slice\(0,3\)\.map/);

  const html=read('static/dashboard/index.html');
  for(const iconClass of ['orange','blue','green','purple'])
    assert.match(html,new RegExp('dash-kpi-icon '+iconClass));
  assert.equal((html.match(/dash-kpi-card dash-kpi-standard/g)||[]).length,3);
  assert.equal((html.match(/class="dash-kpi-content"/g)||[]).length,4);
  assert.equal((html.match(/class="dash-kpi-title/g)||[]).length,4);
  assert.equal((html.match(/class="dash-kpi-metric"/g)||[]).length,3);
  assert.match(html,/dash-kpi-card dash-kpi-resources/);
});


test('company profile uses the workspace topbar and keeps billing addresses always open',()=>{
  const html=read('static/dashboard/index.html');
  assert.match(html,/id="workspacePageTitle">Dashboard<\/h1>/);
  assert.match(html,/id="workspacePageSubtitle"/);
  assert.match(html,/id="companyTopbarStatus" class="company-topbar-status"/);
  assert.equal((html.match(/id="companyConfiguredBadge"/g)||[]).length,1);
  assert.equal((html.match(/id="showOnboardingBtn"/g)||[]).length,1);
  const company=html.slice(html.indexOf('<section id="tab-company"'),html.indexOf('<section id="tab-dashboard"'));
  assert.doesNotMatch(company,/<div class="dash-hero-row">/);
  assert.doesNotMatch(company,/<details class="company-address-details"/);
  assert.match(company,/<section class="card company-card-v29 company-address-details"[^>]*aria-labelledby="companyAddressesTitle"/);
  assert.match(company,/id="companyLegalAddressInput"/);
  assert.match(company,/id="companyBillingAddressInput"/);

  const navigation=read('static/dashboard/js/navigation.js');
  new vm.Script(navigation);
  assert.match(navigation,/function syncWorkspaceTopbar\(name\)/);
  assert.match(navigation,/company \? "Profilo azienda" : "Dashboard"/);
  assert.match(navigation,/classList\.toggle\("gf-company-page-active", company\)/);
  assert.match(navigation,/syncWorkspaceTopbar\(name\)/);

  const layoutCss=read(assets+'layout.css');
  assert.match(layoutCss,/#app:has\(#tab-company:not\(\.hidden\)\) \.topbar-dashboard-title\{display:block;min-width:0\}/);

  const companyCss=read('static/dashboard/css/company.css');
  assert.match(companyCss,/body:has\(#tab-company:not\(\.hidden\)\) \.topbar\s*\{[^}]*background: var\(--gf-color-surface/);
  assert.match(companyCss,/body\.gf-company-page-active \.topbar-new-route\s*\{\s*display: none !important/);
  assert.match(companyCss,/\.company-topbar-status \{ display: none/);
  assert.doesNotMatch(companyCss,/company-address-details summary/);

  const workspace=read(assets+'workspace.css');
  const innerSurface=workspace.slice(workspace.indexOf('.company-logo-row-v29'),workspace.indexOf('){',workspace.indexOf('.company-logo-row-v29')));
  assert.doesNotMatch(innerSurface,/company-address-details/);
  assert.match(workspace,/#app \.company-configured-badge-v40/);
});


test('company edits are saved from the topbar and bottom save actions are removed',()=>{
  const html=read('static/dashboard/index.html');
  assert.match(html,/id="companySaveBar" class="company-save-bar hidden"/);
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
  assert.match(companyCss,/\.company-save-bar\s*\{[^}]*position: absolute[^}]*left: 50%[^}]*top: 50%/);
  assert.match(companyCss,/\.company-save-bar\.hidden \{ display: none !important; \}/);
  assert.doesNotMatch(companyCss,/company-save-actions/);
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
  const topbar=html.slice(html.indexOf('<div class="top-actions">'),html.indexOf('</header>'));
  assert.match(topbar,/class="bell-icon-v30"[^>]*><svg/);
  assert.doesNotMatch(topbar,/>🔔</);
  assert.doesNotMatch(topbar,/id="logoutBtn"/);
  assert.match(topbar,/class="profile-button-chevron"/);

  const profile=html.slice(html.indexOf('<div id="profileOverlay"'),html.indexOf('<!-- COOKIE NOTICE'));
  assert.match(profile,/id="logoutBtn" class="profile-logout-btn hidden"/);
  assert.match(profile,/class="profile-modal-footer"/);
  assert.doesNotMatch(profile,/btn-danger/);
  assert.equal((html.match(/id="logoutBtn"/g)||[]).length,1);

  const layout=read(assets+'layout.css');
  assert.match(layout,/\.notification-bell-v30\{[^}]*border:0[^}]*background:transparent[^}]*box-shadow:none/);
  assert.match(layout,/\.bell-icon-v30 svg\{[^}]*stroke:currentColor/);
});

test('account profile modal follows the workspace design system',()=>{
  const html=read('static/dashboard/index.html');
  const profile=html.slice(html.indexOf('<div id="profileOverlay"'),html.indexOf('<!-- COOKIE NOTICE'));
  assert.match(profile,/class="profile-modal profile-modal-v2"/);
  assert.match(profile,/class="profile-modal-section profile-identity-section"/);
  assert.match(profile,/class="profile-modal-section profile-plan-section"/);
  assert.match(profile,/id="planStatusBox" class="profile-plan-status is-loading"/);
  assert.match(profile,/class="profile-plan-actions-v63 profile-plan-actions-v2"/);

  const core=read('static/dashboard/js/core.js');
  assert.match(core,/const setPlanStatusTone = \(tone, icon\)/);
  assert.match(core,/setPlanStatusTone\("is-success", "✓"\)/);
  assert.doesNotMatch(core,/statusBox\.style\.background/);
  assert.match(core,/plan-usage-chip-icon" aria-hidden="true"/);

  const components=read(assets+'components.css');
  assert.match(components,/Account profile dialog — GiroFacile workspace reference/);
  assert.match(components,/#profileOverlay \.profile-modal-v2\{[^}]*max-width:760px[^}]*box-shadow:var\(--gf-shadow-dialog\)/);
  assert.match(components,/#profileOverlay \.profile-logout-btn\{[^}]*background:var\(--gf-color-surface-subtle\)[^}]*color:var\(--gf-color-muted\)/);
  assert.match(components,/#profileOverlay \.profile-plan-usage\{[^}]*grid-template-columns:repeat\(5,minmax\(0,1fr\)\)/);
  assert.match(components,/#profileOverlay \.profile-field input:focus\{[^}]*box-shadow:var\(--gf-focus-ring\)/);
});


test('workspace sidebar uses the GiroFacile brand artwork',()=>{
  const html=read('static/dashboard/index.html');
  const brand=html.slice(html.indexOf('<div class="brand">'),html.indexOf('<nav class="side-nav">'));
  assert.match(brand,/class="brand-logo-img"/);
  assert.match(brand,/src="\/static\/girofacile-logo\.png\?v=20261007_sidebar"/);
  assert.match(brand,/class="reference-brand-name">GiroFacile<\/span>/);
  assert.doesNotMatch(brand,/reference-brand-icon/);
});


test('workspace legal links live in navigation and advanced legal docs live in support',()=>{
  const html=read('static/dashboard/index.html');
  const sidebar=html.slice(html.indexOf('<aside class="sidebar">'),html.indexOf('</aside>'));
  assert.match(sidebar,/class="side-footer"/);
  assert.match(sidebar,/class="side-footer-copyright">© 2026 GiroFacile/);
  assert.match(sidebar,/class="side-footer-version">v3\.11\.0/);
  assert.match(sidebar,/href="\/privacy-policy"[^>]*>Privacy<\/a>/);
  assert.match(sidebar,/href="\/termini-condizioni"[^>]*>Termini<\/a>/);
  assert.match(sidebar,/href="\/cookie-policy"[^>]*>Cookie<\/a>/);
  assert.doesNotMatch(sidebar,/Sicurezza|DPA|Fornitori|>API</);
  assert.doesNotMatch(html,/class="dashboard-legal-footer"/);

  const mobile=html.slice(html.indexOf('id="gfMobileMoreMenuV62"'),html.indexOf('<nav class="gf-mobile-bottom-nav-v62"'));
  assert.match(mobile,/class="gf-mobile-legal-v62"/);
  assert.match(mobile,/Privacy/);
  assert.match(mobile,/Termini/);
  assert.match(mobile,/Cookie/);

  const core=read('static/dashboard/js/core.js');
  const support=core.slice(core.indexOf('function ensureSupportModalV60'),core.indexOf('function openSupportPanelV49'));
  assert.match(support,/class="support-legal-v60"/);
  assert.match(support,/href="\/sicurezza"/);
  assert.match(support,/href="\/dpa-responsabile-trattamento"/);
  assert.match(support,/href="\/subprocessors"/);

  const layout=read(assets+'layout.css');
  assert.match(layout,/Workspace legal navigation consolidation/);
  assert.match(layout,/\.side-legal-links\{[^}]*justify-content:flex-start/);
  assert.match(layout,/\.gf-mobile-legal-v62\{display:none\}/);

  const components=read(assets+'components.css');
  assert.match(components,/Support legal resources moved out of the workspace footer/);
  assert.match(components,/\.support-legal-v60\{[^}]*background:var\(--gf-color-bg\)/);
});


test('dashboard resource panels match route panel headers and use neutral actions',()=>{
  const html=read('static/dashboard/index.html');
  const dashboard=html.slice(html.indexOf('<section id="tab-dashboard"'),html.indexOf('<section id="tab-dashboard-scheduled"'));
  assert.equal((dashboard.match(/class="dash-resource-action"/g)||[]).length,2);
  assert.match(dashboard,/class="dash-resource-action" onclick="showTab\('mezzi'\)"><span>Tutti i <\/span>/);
  assert.match(dashboard,/class="dash-resource-action" onclick="showTab\('autisti'\)"><span>Tutti gli <\/span>/);
  assert.doesNotMatch(dashboard,/dash-link-inline/);

  const workspace=read(assets+'workspace.css');
  assert.match(workspace,/\.dash-panel-title\{[^}]*background:var\(--gf-color-surface-subtle\)/);
  assert.match(workspace,/\.dash-resource-action\{[^}]*background:var\(--gf-color-surface\)[^}]*color:var\(--gf-color-text\)/);
  assert.match(workspace,/\.dash-resource-action:hover\{[^}]*background:var\(--gf-color-bg\)/);
});
