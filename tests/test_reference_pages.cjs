// Guardia della pulizia: i vecchi fogli di adattamento sono eliminati e pagine e finestre usano i componenti.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const read=name=>fs.readFileSync(path.join(root,name),'utf8');
const base='static/design-system/';
const LEGACY=['design-system/reference-theme.css','design-system/reference-pages.css','design-system/reference-dialogs.css',
  'design-system/unified.css','design-system/sidebar-unified.css','design-system/tokens.css','dashboard/css/orders.css',
  'dashboard/css/scheduled.css','dashboard/css/completed.css','dashboard/css/collaborators.css','dashboard/css/fleet-planning.css'];

test('i fogli della vecchia interfaccia non esistono più e nessuna pagina li carica',()=>{
  const pages=['dashboard/index','admin/index','admin/login'].map(p=>read('static/'+p+'.html')).join('\n');
  for(const file of LEGACY){
    assert.ok(!fs.existsSync(path.join(root,'static',file)),file+' should be deleted');
    assert.ok(!pages.includes('/static/'+file),file+' still linked');
  }
});

test('la home della Dashboard mantiene il pannello giro collegato alle API',()=>{
  const home=read('static/dashboard/index.html');
  assert.match(home,/id="gfRefHeroWrap"/);
  assert.match(home,/id="gfRefRouteDrawing"/);
  assert.match(read('static/dashboard/js/core.js'),/renderGFReferenceDashboardHero/);
});

test('le finestre operative usano i componenti gf-overlay / gf-modal e restano uniche',()=>{
  const html=read('static/dashboard/index.html');
  const core=read('static/dashboard/js/core.js');
  const components=read(base+'components.css');
  for(const id of ['agentOverlay','depositOverlay','driverFormOverlay','customerOverlay','customerImportOverlay',
    'deliveryDetailsOverlay','onboardingOverlay','profileOverlay','orderModal','collaboratorDialog','supportTicketModalV60']){
    const converted=new RegExp('id="'+id+'" class="gf-(overlay|modal)').test(html)
      || (id==='supportTicketModalV60' && /wrap\.className = "gf-overlay hidden"/.test(core));
    assert.ok(converted,'Popup senza componente '+id);
  }
  for(const id of ['orderModal','agentOverlay','depositOverlay','driverFormOverlay','customerOverlay','customerImportOverlay',
    'deliveryDetailsOverlay','onboardingOverlay','profileOverlay','customerDrawer','collaboratorDialog']){
    assert.equal((html.match(new RegExp('id="'+id+'"','g'))||[]).length,1,id);
  }
  assert.match(components,/dialog\.gf-modal::backdrop/);
  assert.match(components,/max-height:calc\(100dvh - var\(--gf-space-8\)\)/);
});

test('i fogli rimasti della Dashboard usano solo variabili del tema e non contengono logica',()=>{
  const files=fs.readdirSync(path.join(root,'static/dashboard/css')).map(f=>'static/dashboard/css/'+f).concat([base+'workspace.css']);
  for(const file of files){
    const css=read(file);
    let depth=0;
    for(const ch of css){ if(ch==='{')depth++; if(ch==='}')depth--; assert.ok(depth>=0,file+': unexpected closing brace'); }
    assert.equal(depth,0,file+': unclosed CSS block');
    assert.doesNotMatch(css.replace(/\/\*[\s\S]*?\*\//g,''),/#[0-9a-f]{3,8}\b|rgba?\(/i,file+': colore scritto a mano');
    assert.doesNotMatch(css,/fetch\s*\(|XMLHttpRequest|localStorage|location\.href/);
  }
});
