'use strict';
const $ = id => document.getElementById(id);
let brand, token, project, active = 0, slideIndex = 0, logo, fontWarning = '';
const LAYOUTS = {
  route: {name:'Percorso',description:'Titoli ampi e una linea di percorso. Per attirare attenzione.',stage:'TOFU'},
  editorial: {name:'Editoriale',description:'Fondo chiaro e gerarchie ordinate. Per spiegare il metodo.',stage:'MOFU'},
  cards: {name:'Focus',description:'Blocchi separati e CTA in evidenza. Per guidare la scelta.',stage:'BOFU'}
};
const suggestedLayout = stage => Object.keys(LAYOUTS).find(key=>LAYOUTS[key].stage===stage) || 'route';
const status = (message, error = false) => { $('status').textContent = message; $('status').classList.toggle('error', error); };
function brief() { return Object.fromEntries(['topic','audience','facts','cta','stage','mode','count'].map(id => [id, id === 'count' ? Number($(id).value) : $(id).value])); }
async function api(path, data) {
  const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':token},body:JSON.stringify(data)});
  if (!response.ok) { const error = await response.json(); throw new Error(error.error || 'Operazione non riuscita.'); }
  return path === '/api/zip' ? response.blob() : response.json();
}
function download(blob, name) { const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),3000); }
function saveText(value,name,type='text/plain') { download(new Blob([value],{type}),name); }
const current = () => project.carousels[active];
function lines(ctx, text, width) {
  const result=[];
  for (const paragraph of text.split('\n')) {
    let line='';
    for (const word of paragraph.split(/\s+/).filter(Boolean)) {
      if (ctx.measureText((line ? line+' ' : '')+word).width <= width) { line+=(line?' ':'')+word; continue; }
      if (line) result.push(line);
      line='';
      for (const char of word) {
        if (ctx.measureText(line+char).width > width && line) { result.push(line); line=''; }
        line+=char;
      }
    }
    result.push(line);
  }
  return result;
}
function textBlock(ctx,text,x,y,width,maxHeight,startSize,font,weight=400) {
  let size=startSize, wrapped;
  do { ctx.font=`${weight} ${size}px "${font}", sans-serif`; wrapped=lines(ctx,text,width); if(wrapped.length*size*1.2<=maxHeight) break; size-=2; } while(size>=24);
  if (wrapped.length*size*1.2>maxHeight) throw new Error('Il testo non entra nella slide. Accorcialo prima di esportare.');
  wrapped.forEach((line,i)=>ctx.fillText(line,x,y+i*size*1.2));
  return wrapped.length*size*1.2;
}
function draw(canvas, item, index, total, stage, layout = current().layout || 'route') {
  const h=Number($('format').value), c=brand.colors, cover=index===0, last=index===total-1;
  canvas.width=1080;canvas.height=h;
  const ctx=canvas.getContext('2d');
  if(layout!=='route') {
    drawAlternative(ctx,item,index,total,h,layout);
    return;
  }
  const dark=cover||last, bg=cover?c.navy:last?c.primary:'#ffffff', fg=dark?'#ffffff':c.text;
  ctx.fillStyle=bg;ctx.fillRect(0,0,1080,h);
  ctx.save();ctx.globalAlpha=cover?.85:.12;ctx.strokeStyle=dark?c.accent:c.primary;ctx.lineWidth=28;
  ctx.beginPath();ctx.moveTo(820,180);ctx.lineTo(960,180);ctx.quadraticCurveTo(1025,180,1025,245);ctx.lineTo(1025,h-240);ctx.quadraticCurveTo(1025,h-180,960,h-180);ctx.lineTo(790,h-180);ctx.stroke();
  for(const y of [250,h-290]) {ctx.beginPath();ctx.arc(1025,y,20,0,Math.PI*2);ctx.fillStyle=c.accent;ctx.fill();}ctx.restore();
  ctx.fillStyle='#ffffff';ctx.fillRect(72,64,64,64);
  const ratio=Math.min(56/logo.naturalWidth,56/logo.naturalHeight);ctx.drawImage(logo,76+(56-logo.naturalWidth*ratio)/2,68+(56-logo.naturalHeight*ratio)/2,logo.naturalWidth*ratio,logo.naturalHeight*ratio);
  ctx.fillStyle=fg;ctx.font=`700 31px "${brand.fonts.display}", sans-serif`;ctx.fillText('GiroFacile',154,108);
  ctx.fillStyle=dark?c.accent:c.primary;ctx.font=`500 19px "${brand.fonts.body}", sans-serif`;ctx.fillText(`${String(index+1).padStart(2,'0')}  /  ${String(total).padStart(2,'0')}`,875,106);
  ctx.fillStyle=dark?c.accent:c.primary;ctx.font=`500 20px "${brand.fonts.body}", sans-serif`;
  ctx.fillText(cover?'ORGANIZZARE MEGLIO. LAVORARE MEGLIO.':last?'IL PROSSIMO PASSO':`IL TUO GIRO, PASSO ${index}`,72,218);
  ctx.fillStyle=fg;
  const titleY=cover?Math.round(h*.29):290, titleMax=cover?h*.34:h*.28;
  const used=textBlock(ctx,item.title,72,titleY,855,titleMax,cover?88:70,brand.fonts.display,700);
  const bodyY=titleY+used+44;
  ctx.fillStyle=dark?'#ffffff':c.muted;
  textBlock(ctx,item.body,72,bodyY,850,h-140-bodyY,cover?38:36,brand.fonts.body);
  ctx.strokeStyle=dark?'rgba(255,255,255,.28)':c.background;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(72,h-100);ctx.lineTo(1008,h-100);ctx.stroke();
  ctx.fillStyle=fg;ctx.font=`500 18px "${brand.fonts.body}", sans-serif`;ctx.fillText('GIROFACILE  /  CONSEGNE, CON METODO',72,h-55);ctx.fillText(last?'●':'SCORRI  →',last?990:890,h-55);
}
function drawAlternative(ctx,item,index,total,h,layout) {
  const c=brand.colors,last=index===total-1,cover=index===0,number=String(index+1).padStart(2,'0');
  const label=cover?'CONSEGNE, CON METODO':last?'IL PROSSIMO PASSO':`PASSO ${number}`;
  const rect=(x,y,w,height,color)=>{ctx.fillStyle=color;ctx.fillRect(x,y,w,height);};
  const mark=(x,y,color)=>{
    const ratio=Math.min(56/logo.naturalWidth,56/logo.naturalHeight);
    ctx.drawImage(logo,x,y,logo.naturalWidth*ratio,logo.naturalHeight*ratio);
    ctx.fillStyle=color;ctx.font=`700 30px "${brand.fonts.display}", sans-serif`;ctx.fillText('GiroFacile',x+76,y+40);
  };
  if(layout==='editorial') {
    rect(0,0,1080,h,'#ffffff');rect(0,0,20,h,c.primary);
    mark(76,64,c.navy);
    ctx.fillStyle=c.primary;ctx.font=`700 96px "${brand.fonts.display}", sans-serif`;ctx.fillText(number,860,138);
    rect(76,180,928,3,c.navy);
    ctx.font=`500 20px "${brand.fonts.body}", sans-serif`;ctx.fillText(label,76,235);
    ctx.fillStyle=c.navy;
    textBlock(ctx,item.title,76,330,920,h*.28,cover?86:72,brand.fonts.display,700);
    const panelY=Math.round(h*.61);
    rect(76,panelY,928,h-panelY-140,c.background);rect(76,panelY,8,h-panelY-140,c.primary);
    ctx.fillStyle=c.text;textBlock(ctx,item.body,112,panelY+64,850,h-panelY-210,36,brand.fonts.body);
    ctx.fillStyle=c.muted;ctx.font=`500 18px "${brand.fonts.body}", sans-serif`;ctx.fillText('GIROFACILE  /  IDEE PER IL TUO LAVORO',76,h-65);ctx.fillText(last?'A TE LA SCELTA':'CONTINUA →',820,h-65);
  } else {
    rect(0,0,1080,h,c.background);rect(0,0,1080,170,c.navy);mark(72,57,'#ffffff');
    ctx.fillStyle=c.accent;ctx.font=`500 24px "${brand.fonts.body}", sans-serif`;ctx.fillText(`${number} / ${String(total).padStart(2,'0')}`,875,99);
    const titleY=218,titleH=Math.round(h*.37),bodyY=titleY+titleH+24,bodyH=h-bodyY-132;
    rect(56,titleY,968,titleH,last?c.primary:c.navy);
    ctx.fillStyle=c.accent;ctx.font=`500 20px "${brand.fonts.body}", sans-serif`;ctx.fillText(label,96,titleY+48);
    ctx.fillStyle='#ffffff';textBlock(ctx,item.title,96,titleY+128,884,titleH-150,cover?78:68,brand.fonts.display,700);
    rect(56,bodyY,968,bodyH,'#ffffff');rect(56,bodyY,12,bodyH,c.primary);
    ctx.fillStyle=c.text;textBlock(ctx,item.body,100,bodyY+64,875,bodyH-100,36,brand.fonts.body);
    ctx.fillStyle=c.navy;ctx.font=`500 18px "${brand.fonts.body}", sans-serif`;ctx.fillText(last?'FAI IL PROSSIMO PASSO':'UN PASSAGGIO ALLA VOLTA',72,h-63);
    rect(842,h-94,166,50,c.primary);ctx.fillStyle='#ffffff';ctx.fillText(last?'INIZIA →':'SCORRI →',864,h-61);
  }
}
function renderLayoutChoices() {
  const container=$('layoutChoices');container.replaceChildren();
  for(const [key,layout] of Object.entries(LAYOUTS)) {
    const button=document.createElement('button'),canvas=document.createElement('canvas'),title=document.createElement('strong'),desc=document.createElement('small'),state=document.createElement('span');
    button.type='button';button.className='layout-choice';button.dataset.layout=key;
    const selected=(current().layout || 'route')===key;
    button.setAttribute('aria-pressed',String(selected));button.setAttribute('aria-label',`Scegli layout ${layout.name}`);
    title.textContent=layout.name;desc.textContent=layout.description;state.className='layout-state';
    state.textContent=selected?'✓ Selezionato':suggestedLayout(current().stage)===key?`Suggerito per ${current().stage}`:'Scegli questo stile';
    try {draw(canvas,current().slides[slideIndex],slideIndex,current().slides.length,current().stage,key);}
    catch {state.textContent='Accorcia il testo per questo stile';button.disabled=true;}
    button.append(canvas,title,desc,state);
    button.onclick=()=>{
      try {
        const check=document.createElement('canvas');
        current().slides.forEach((slide,i)=>draw(check,slide,i,current().slides.length,current().stage,key));
        current().layout=key;render();status(`Layout ${layout.name} applicato a tutte le slide ${current().stage}. Testi conservati.`);
      } catch(error) {status(error.message,true);}
    };
    container.append(button);
  }
}
function showSlide() {
  const item=current().slides[slideIndex];
  $('slideTitle').value=item.title;$('slideBody').value=item.body;
  $('slideNumber').textContent=`Slide ${slideIndex+1} di ${current().slides.length}`;
  $('slideRole').textContent=slideIndex===0?'APERTURA':slideIndex===current().slides.length-1?'INVITO ALL’AZIONE':'SVILUPPO';
  $('prev').disabled=slideIndex===0;$('next').disabled=slideIndex===current().slides.length-1;
  draw($('preview'),item,slideIndex,current().slides.length,current().stage);
  [...$('thumbnails').children].forEach((button,i)=>button.setAttribute('aria-current',String(i===slideIndex)));
  renderLayoutChoices();
}
function render() {
  $('empty').hidden=true;$('output').hidden=false;$('tabs').replaceChildren();
  project.carousels.forEach((item,i)=>{const button=document.createElement('button');button.textContent=item.stage;button.setAttribute('aria-pressed',String(i===active));const small=document.createElement('small');small.textContent=brand.funnels[item.stage].goal;button.append(small);button.onclick=()=>{active=i;slideIndex=0;render();};$('tabs').append(button);});
  $('thumbnails').replaceChildren();
  current().slides.forEach((item,i)=>{const button=document.createElement('button'),canvas=document.createElement('canvas');button.setAttribute('aria-label',`Vai alla slide ${i+1}`);draw(canvas,item,i,current().slides.length,current().stage);button.append(canvas);button.onclick=()=>{slideIndex=i;showSlide();};$('thumbnails').append(button);});
  $('caption').value=current().caption;$('modeBadge').textContent=project.mode==='ai'?'Testi AI · da verificare':'Struttura locale';showSlide();
}
async function run(button, action) { button.disabled=true; try { await action(); } catch(error) {status(error.message,true);} finally {button.disabled=false;} }
$('briefForm').onsubmit=event=>{event.preventDefault();run($('generate'),async()=>{status('Preparazione dei caroselli…');const next=await api('/api/generate',brief());next.carousels.forEach(item=>{item.layout=suggestedLayout(item.stage);});project=next;active=0;slideIndex=0;render();status(`${project.carousels.length} caroselli pronti. Testi e caption sono modificabili. ${fontWarning}`);});};
function fillProjectBrief() {
  for (const id of ['topic','audience','facts','cta','stage','count','mode','format']) $(id).value=String(brand.default_brief[id]);
  $('mode').dispatchEvent(new Event('change'));
  $('briefSources').textContent=brand.brief_source_note;
  status('Brief GiroFacile già compilato dal progetto. Premi “Genera i caroselli” per creare TOFU, MOFU e BOFU.');
}
$('example').onclick=()=>{if(brand)fillProjectBrief();};
$('mode').onchange=()=>{$('modeHelp').textContent=$('mode').value==='ai'?'Il brief e le informazioni pubbliche del brand saranno inviati a OpenAI. La chiamata usa la chiave API del server e può avere un costo.':'La modalità locale conserva i tuoi punti e usa strutture editoriali predefinite. Non riscrive il brief con AI.';};
$('exportPrompt').onclick=()=>run($('exportPrompt'),async()=>{const result=await api('/api/prompt',brief());saveText(result.prompt,'girofacile-prompt.txt');status('Prompt con brand, brief e regole del funnel scaricato.');});
for(const [id,key] of [['slideTitle','title'],['slideBody','body']]) $(id).oninput=()=>{current().slides[slideIndex][key]=$(id).value;try{draw($('preview'),current().slides[slideIndex],slideIndex,current().slides.length,current().stage);draw($('thumbnails').children[slideIndex].firstChild,current().slides[slideIndex],slideIndex,current().slides.length,current().stage);renderLayoutChoices();}catch(error){status(error.message,true);}};
$('caption').oninput=()=>{current().caption=$('caption').value;};
$('prev').onclick=()=>{if(slideIndex>0){slideIndex--;showSlide();}};$('next').onclick=()=>{if(slideIndex<current().slides.length-1){slideIndex++;showSlide();}};
$('format').onchange=()=>{if(project)render();};
$('png').onclick=()=>run($('png'),async()=>{draw($('preview'),current().slides[slideIndex],slideIndex,current().slides.length,current().stage);const blob=await new Promise(resolve=>$('preview').toBlob(resolve,'image/png'));if(!blob)throw new Error('Esportazione PNG non riuscita.');download(blob,`girofacile-${current().stage.toLowerCase()}-${current().layout || 'route'}-${slideIndex+1}.png`);status(`PNG esportata a 1080 × ${$('format').value}. ${fontWarning}`);});
$('zip').onclick=()=>run($('zip'),async()=>{status('Esportazione delle slide…');const images=current().slides.map((item,i)=>{const canvas=document.createElement('canvas');draw(canvas,item,i,current().slides.length,current().stage);return canvas.toDataURL('image/png').split(',')[1];});download(await api('/api/zip',{images}),`girofacile-${current().stage.toLowerCase()}-${current().layout || 'route'}.zip`);status(`Carosello ${current().stage} esportato in ZIP. ${fontWarning}`);});
$('copyCaption').onclick=()=>run($('copyCaption'),async()=>{await navigator.clipboard.writeText(current().caption);status('Caption copiata.');});
$('saveDraft').onclick=()=>{saveText(JSON.stringify({...project,format:Number($('format').value)},null,2),'girofacile-caroselli.json','application/json');status('Progetto salvato con tutti i caroselli e i testi modificati.');};
function validateProject(value) {
  if(!value || !Array.isArray(value.carousels) || value.carousels.length<1 || value.carousels.length>3)throw new Error('Progetto non valido.');
  const stages=new Set();
  for(const item of value.carousels){
    if(!item || !Object.hasOwn(brand.funnels,item.stage) || stages.has(item.stage) || typeof item.caption!=='string' || item.caption.length>1800 || !Array.isArray(item.slides) || item.slides.length<5 || item.slides.length>9)throw new Error('Carosello non valido.');
    if(item.layout !== undefined && !Object.hasOwn(LAYOUTS,item.layout))throw new Error('Layout del progetto non riconosciuto.');
    item.layout = item.layout || 'route';
    stages.add(item.stage);
    for(const slide of item.slides)if(!slide || typeof slide.title!=='string' || slide.title.length>100 || typeof slide.body!=='string' || slide.body.length>360)throw new Error('Testi non validi nel progetto.');
  }
  return value;
}
$('loadDraft').onchange=async()=>{try{const file=$('loadDraft').files[0];if(!file)return;if(file.size>150000)throw new Error('File troppo grande.');const value=validateProject(JSON.parse(await file.text()));project=value;active=0;slideIndex=0;if([1080,1350].includes(value.format))$('format').value=String(value.format);if(value.brief)for(const id of ['topic','audience','facts','cta','stage','mode','count'])if(typeof value.brief[id]==='string'||typeof value.brief[id]==='number')$(id).value=value.brief[id];render();status('Progetto riaperto. Grafica aggiornata al brand attuale del repository.');}catch(error){status(error.message,true);}finally{$('loadDraft').value='';}};
async function init() {
  $('generate').disabled=true;
  try {
    const response=await fetch('/api/brand');if(!response.ok)throw new Error('Impossibile leggere il brand.');brand=await response.json();token=brand.token;
    fillProjectBrief();
    const card=$('brandCard');card.replaceChildren();const heading=document.createElement('h3');heading.textContent='Il tuo brand, già riconosciuto';card.append(heading);const swatches=document.createElement('div');swatches.className='swatches';
    for(const value of Object.values(brand.colors)){const swatch=document.createElement('span');swatch.style.background=value;swatch.title=value;swatches.append(swatch);}card.append(swatches);
    for(const text of [`${brand.fonts.display} + ${brand.fonts.body}`,`Repository Girofacile/girofacile · ${brand.revision}`,brand.tone_status]){const p=document.createElement('p');p.textContent=text;card.append(p);}
    const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Fonti rilevate';details.append(summary);const sources=document.createElement('p');sources.textContent=brand.sources.join(' · ');details.append(sources);card.append(details);
    if(brand.ai_available){$('aiOption').disabled=false;$('aiOption').textContent='AI · riscrive il brief';}
    logo=new Image();logo.src=brand.logo;await logo.decode();
    try {await Promise.all([document.fonts.load(`700 88px "${brand.fonts.display}"`),document.fonts.load(`400 36px "${brand.fonts.body}"`)]);if(!document.fonts.check(`700 88px "${brand.fonts.display}"`)||!document.fonts.check(`400 36px "${brand.fonts.body}"`))throw new Error();}catch{fontWarning='Font online non disponibili: anteprima ed export usano il font di sistema.';status(fontWarning,true);}
    $('generate').disabled=false;
  }catch(error){status(error.message,true);}
}
init();
