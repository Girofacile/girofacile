// Regression guard for the 2026-10-12 visual rollout outside the home dashboard.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=name=>fs.readFileSync(path.join(root,name),'utf8');
const base='static/design-system/';

test('reference theme for pages and dialogs loads after all legacy CSS',()=>{
  const html=read('static/dashboard/index.html');
  const theme=html.indexOf('/static/design-system/reference-theme.css');
  const pages=html.indexOf('/static/design-system/reference-pages.css');
  const dialogs=html.indexOf('/static/design-system/reference-dialogs.css');
  assert.ok(theme>0&&pages>theme&&dialogs>pages,'Visual sheets should win the cascade');
  assert.equal((html.match(/reference-pages\.css/g)||[]).length,1);
  assert.equal((html.match(/reference-dialogs\.css/g)||[]).length,1);
});

test('the restyled workspace explicitly excludes the dashboard home',()=>{
  const pages=read(base+'reference-pages.css');
  assert.match(pages,/\.tab:not\(#tab-dashboard\)/);
  assert.doesNotMatch(pages,/#tab-dashboard\s+[.#]/);
  const home=read('static/dashboard/index.html');
  assert.match(home,/id="gfRefHeroWrap"/);
  assert.match(home,/id="gfRefRouteDrawing"/);
  // Styling elsewhere must not remove or rename the API-powered hero.
  assert.match(read('static/dashboard/js/core.js'),/renderGFReferenceDashboardHero/);
});

test('all major workspace sections share dashboard panel, table, toolbar and KPI styles',()=>{
  const css=read(base+'reference-pages.css');
  for(const selector of [
    '.customer-metric','.deposit-metric','.orders-metric-card','.driver-stat',
    '.collaborator-metrics>div','.report-kpi-card','.company-card-v29',
    '.orders-order-card','.fleet-card','.driver-directory-card',
    '.settings-panel','.driver-chat-room-card','.orders-view-switch',
    '.customer-view-controls','.deposit-view-controls','.fleet-views',
    '.gf-directory-metric','.plan-current-hero-v875','.billing-section-v876',
    '.result-table','.tableWrap','.orders-table-shell'
  ]){
    assert.ok(css.includes(selector),'Missing visual contract '+selector);
  }
  assert.match(css,/font-family:var\(--gf-font-display\)/);
  assert.match(css,/font-family:var\(--gf-font-family\)/);
  assert.match(css,/var\(--gf-color-primary\)/);
  assert.match(css,/var\(--gf-color-border\)/);
});

test('popup skins preserve overlays and all operational modal IDs',()=>{
  const css=read(base+'reference-dialogs.css');
  for(const selector of [
    '#agentOverlay','#depositOverlay','#driverFormOverlay','#customerOverlay',
    '#customerImportOverlay','#deliveryDetailsOverlay','#onboardingOverlay',
    '#profileOverlay','#orderModal','#customerDetailsDialog',
    '#collaboratorDialog','#supportTicketModalV60'
  ]){
    assert.ok(css.includes(selector),'Unstyled popup '+selector);
  }
  const html=read('static/dashboard/index.html');
  for(const id of ['orderModal','agentOverlay','depositOverlay','driverFormOverlay',
    'customerOverlay','customerImportOverlay','deliveryDetailsOverlay','onboardingOverlay',
    'profileOverlay','customerDetailsDialog','collaboratorDialog']){
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1);
  }
  assert.match(css,/::backdrop/);
  assert.match(css,/max-height:calc\(100dvh - 32px\)/);
});

test('reference skins have balanced CSS blocks and no JS business logic',()=>{
  for(const file of ['reference-pages.css','reference-dialogs.css']){
    const css=read(base+file);
    let depth=0;
    for(const ch of css){
      if(ch==='{') depth++;
      if(ch==='}') depth--;
      assert.ok(depth>=0,file+': unexpected closing brace');
    }
    assert.equal(depth,0,file+': unclosed CSS block');
    assert.doesNotMatch(css,/fetch\s*\(|XMLHttpRequest|localStorage|location\.href/);
    assert.doesNotMatch(css,/!important\s*!important/);
  }
});
