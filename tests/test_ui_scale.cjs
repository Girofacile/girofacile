const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
// Scala dell'interfaccia: il layout base mostra sempre circa 1707 × 960 px di area di lavoro.
function shell(width,height){
  const props={},listeners={};
  const doc={readyState:'complete',body:{dataset:{gfLayout:'base'}},documentElement:{style:{setProperty:(k,v)=>props[k]=v}},
    getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[],addEventListener(){}};
  const win={innerWidth:width,innerHeight:height,document:doc,addEventListener:(name,fn)=>listeners[name]=fn};
  vm.runInNewContext(fs.readFileSync('static/design-system/shell.js','utf8'),{window:win,document:doc});
  return {props,listeners,win,GFShell:win.GFShell};
}
test('la scala segue il lato più stretto rispetto alla vista di riferimento, tra 0,75 e 1,5',()=>{
  const {GFShell}=shell(1280,720);
  assert.equal(GFShell.uiScale(1280,720),.75);          // schermo con Windows al 150%: come lo zoom al 75%
  assert.equal(GFShell.uiScale(1707,960),1);            // vista di riferimento
  assert.equal(GFShell.uiScale(1920,960),1);            // largo ma basso: conta l'altezza
  assert.equal(GFShell.uiScale(3840,2160),1.5);         // schermi molto grandi: al massimo 1,5
  assert.equal(GFShell.uiScale(1100,600),.75);          // mai sotto 0,75
  assert.equal(GFShell.uiScale(900,1200),1);            // sotto 1024 px vale il layout a scomparsa
});
test('la pagina imposta --gf-ui-scale all’avvio e quando cambia la finestra o lo zoom',()=>{
  const s=shell(1280,720);
  assert.equal(s.props['--gf-ui-scale'],'0.750');
  s.win.innerWidth=2560;s.win.innerHeight=1440;s.listeners.resize();
  assert.equal(s.props['--gf-ui-scale'],'1.500');
});
test('il layout base applica la scala e misura la finestra nella pagina scalata',()=>{
  const theme=fs.readFileSync('static/design-system/theme.css','utf8');
  const layout=fs.readFileSync('static/design-system/layout.css','utf8');
  const components=fs.readFileSync('static/design-system/components.css','utf8');
  assert.match(theme,/--gf-ui-scale: 1;/);
  assert.match(theme,/--gf-viewport-height: calc\(100dvh \/ var\(--gf-ui-scale\)\);/);
  assert.match(layout,/body\[data-gf-layout="base"\]\{[^}]*zoom:var\(--gf-ui-scale\)/);
  // Con lo zoom 100vh e 100vw non coprirebbero più tutta la finestra.
  for(const css of [layout,components]) assert.doesNotMatch(css,/100d?vh|100vw/);
});
