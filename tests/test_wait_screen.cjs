const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
// Schermata di attesa a tutto schermo (1° novembre 2026): logo che si disegna, titolo con il numero di mezzi,
// durata minima di 2 secondi, avviso dopo un'attesa lunga, gestionale sotto non cliccabile.
function element(tag){
  const node={tagName:tag.toUpperCase(),className:'',textContent:'',attributes:{},children:[],removed:false,html:'',
    setAttribute(k,v){this.attributes[k]=String(v);},removeAttribute(k){delete this.attributes[k];},
    append(...items){this.children.push(...items);},insertAdjacentHTML(_,html){this.html+=html;},remove(){this.removed=true;}};
  return node;
}
function runtime(){
  const shell={inert:false},body=element('body');
  const document={readyState:'loading',body,createElement:element,addEventListener(){},querySelector:s=>s==='[data-gf-shell]'?shell:null,querySelectorAll:()=>[]};
  const window={document,setTimeout,clearTimeout,setInterval,clearInterval};
  vm.runInNewContext(fs.readFileSync('static/design-system/design-system.js','utf8'),{window,document,setTimeout,clearTimeout,setInterval,clearInterval,Date,Promise,Math});
  return {api:window.GFDesignSystem,body,shell};
}
const text=node=>[node.textContent,...(node.children||[]).map(text)].join(' ');
test('la schermata copre il gestionale con logo, titolo, frase e barra, e lo rende non cliccabile',async()=>{
  const {api,body,shell}=runtime();
  const wait=api.showWait({title:'Sto pianificando i giri di 4 mezzi',messages:['Divido le consegne tra i 4 mezzi…','Seconda'],minMs:0});
  const overlay=body.children[0];
  assert.equal(overlay.className,'gf-wait');
  assert.equal(shell.inert,true);
  const loader=overlay.children[0].children[0];
  assert.equal(loader.attributes.role,'status');
  assert.match(loader.html,/class="gf-anim-logo__bg"/);
  assert.match(text(overlay),/Sto pianificando i giri di 4 mezzi/);
  assert.match(text(overlay),/Divido le consegne tra i 4 mezzi…/);
  await wait.close();
  assert.equal(overlay.removed,true);
  assert.equal(shell.inert,false);
});
test('resta almeno il tempo minimo anche se il calcolo finisce prima, poi si chiude subito',async()=>{
  const {api}=runtime();
  let wait=api.showWait({title:'Sto calcolando il giro',minMs:120});
  let started=Date.now();await wait.close();
  assert.ok(Date.now()-started>=100,'chiusa troppo presto');
  wait=api.showWait({title:'Sto calcolando il giro',minMs:30});
  await new Promise(r=>setTimeout(r,60));
  started=Date.now();await wait.close();
  assert.ok(Date.now()-started<25,'non deve aspettare oltre il minimo');
});
test('dopo un’attesa lunga avvisa che ci vuole più del solito',async()=>{
  const {api,body}=runtime();
  const wait=api.showWait({title:'Sto pianificando',minMs:0,slowMs:20});
  await new Promise(r=>setTimeout(r,40));
  assert.match(text(body.children[0]),/Ci vuole un po’ più del solito/);
  await wait.close();
});
test('il numero di mezzi e di giri viene dai dati, mai scritto fisso; il giro singolo usa la stessa schermata',()=>{
  const fleet=fs.readFileSync('static/dashboard/js/fleet-planning.js','utf8');
  const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
  assert.match(fleet,/const vans=resources\.length===1\?'1 mezzo':`\$\{resources\.length\} mezzi`;/);
  assert.match(fleet,/title:`Sto pianificando i giri di \$\{vans\}`/);
  assert.doesNotMatch(fleet,/giri di 3 mezzi|tra i 3 mezzi/);
  assert.match(fleet,/preview',\{method:'POST',body:JSON\.stringify\(data\)\}\);await wait\?\.close\(\);/);
  assert.match(core,/showWait\(\{title:"Sto calcolando il giro"/);
  const optimize=core.slice(core.indexOf('async function optimizeRoute('),core.indexOf('\n}',core.indexOf('async function optimizeRoute(')));
  assert.equal((optimize.match(/await wait\?\.close\(\);/g)||[]).length,2,'chiusura sia dopo il calcolo sia in caso di errore');
});
