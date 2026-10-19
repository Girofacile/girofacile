'use strict';
const $ = id => document.getElementById(id);
let brand, token, project, active = 0, slideIndex = 0, logo, fontWarning = '';
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
function draw(canvas, item, index, total, stage) {
  const h=Number($('format').value), c=brand.colors, cover=index===0, last=index===total-1;
  canvas.width=1080;canvas.height=h;
  const ctx=canvas.getContext('2d');
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
function showSlide() {
  const item=current().slides[slideIndex];
  $('slideTitle').value=item.title;$('slideBody').value=item.body;
  $('slideNumber').textContent=`Slide ${slideIndex+1} di ${current().slides.length}`;
  $('slideRole').textContent=slideIndex===0?'APERTURA':slideIndex===current().slides.length-1?'INVITO ALL’AZIONE':'SVILUPPO';
  $('prev').disabled=slideIndex===0;$('next').disabled=slideIndex===current().slides.length-1;
  draw($('preview'),item,slideIndex,current().slides.length,current().stage);
  [...$('thumbnails').children].forEach((button,i)=>button.setAttribute('aria-current',String(i===slideIndex)));
}
function render() {
  $('empty').hidden=true;$('output').hidden=false;$('tabs').replaceChildren();
  project.carousels.forEach((item,i)=>{const button=document.createElement('button');button.textContent=item.stage;button.setAttribute('aria-pressed',String(i===active));const small=document.createElement('small');small.textContent=brand.funnels[item.stage].goal;button.append(small);button.onclick=()=>{active=i;slideIndex=0;render();};$('tabs').append(button);});
  $('thumbnails').replaceChildren();
  current().slides.forEach((item,i)=>{const button=document.createElement('button'),canvas=document.createElement('canvas');button.setAttribute('aria-label',`Vai alla slide ${i+1}`);draw(canvas,item,i,current().slides.length,current().stage);button.append(canvas);button.onclick=()=>{slideIndex=i;showSlide();};$('thumbnails').append(button);});
  $('caption').value=current().caption;$('modeBadge').textContent=project.mode==='ai'?'Testi AI · da verificare':'Struttura locale';showSlide();
}
async function run(button, action) { button.disabled=true; try { await action(); } catch(error) {status(error.message,true);} finally {button.disabled=false;} }
$('briefForm').onsubmit=event=>{event.preventDefault();run($('generate'),async()=>{status('Preparazione dei caroselli…');const next=await api('/api/generate',brief());project=next;active=0;slideIndex=0;render();status(`${project.carousels.length} caroselli pronti. Testi e caption sono modificabili. ${fontWarning}`);});};
$('example').onclick=()=>{ $('topic').value='Dai fogli sparsi a un giro di consegne organizzato';$('audience').value='responsabili di piccole flotte e attività con consegne locali';$('facts').value='GiroFacile permette di pianificare le consegne.\nPuoi gestire gli autisti e seguire le missioni.\nI report aiutano a consultare le informazioni del lavoro svolto.';$('count').value='6';status('Esempio caricato dalle funzioni presenti nella landing. Premi Genera i caroselli.'); };
$('mode').onchange=()=>{$('modeHelp').textContent=$('mode').value==='ai'?'Il brief e le informazioni pubbliche del brand saranno inviati a OpenAI. La chiamata usa la chiave API del server e può avere un costo.':'La modalità locale conserva i tuoi punti e usa strutture editoriali predefinite. Non riscrive il brief con AI.';};
$('exportPrompt').onclick=()=>run($('exportPrompt'),async()=>{const result=await api('/api/prompt',brief());saveText(result.prompt,'girofacile-prompt.txt');status('Prompt con brand, brief e regole del funnel scaricato.');});
for(const [id,key] of [['slideTitle','title'],['slideBody','body']]) $(id).oninput=()=>{current().slides[slideIndex][key]=$(id).value;try{draw($('preview'),current().slides[slideIndex],slideIndex,current().slides.length,current().stage);draw($('thumbnails').children[slideIndex].firstChild,current().slides[slideIndex],slideIndex,current().slides.length,current().stage);}catch(error){status(error.message,true);}};
$('caption').oninput=()=>{current().caption=$('caption').value;};
$('prev').onclick=()=>{if(slideIndex>0){slideIndex--;showSlide();}};$('next').onclick=()=>{if(slideIndex<current().slides.length-1){slideIndex++;showSlide();}};
$('format').onchange=()=>{if(project)render();};
$('png').onclick=()=>run($('png'),async()=>{draw($('preview'),current().slides[slideIndex],slideIndex,current().slides.length,current().stage);const blob=await new Promise(resolve=>$('preview').toBlob(resolve,'image/png'));if(!blob)throw new Error('Esportazione PNG non riuscita.');download(blob,`girofacile-${current().stage.toLowerCase()}-${slideIndex+1}.png`);status(`PNG esportata a 1080 × ${$('format').value}. ${fontWarning}`);});
$('zip').onclick=()=>run($('zip'),async()=>{status('Esportazione delle slide…');const images=current().slides.map((item,i)=>{const canvas=document.createElement('canvas');draw(canvas,item,i,current().slides.length,current().stage);return canvas.toDataURL('image/png').split(',')[1];});download(await api('/api/zip',{images}),`girofacile-${current().stage.toLowerCase()}.zip`);status(`Carosello ${current().stage} esportato in ZIP. ${fontWarning}`);});
$('copyCaption').onclick=()=>run($('copyCaption'),async()=>{await navigator.clipboard.writeText(current().caption);status('Caption copiata.');});
$('saveDraft').onclick=()=>{saveText(JSON.stringify({...project,format:Number($('format').value)},null,2),'girofacile-caroselli.json','application/json');status('Progetto salvato con tutti i caroselli e i testi modificati.');};
function validateProject(value) {
  if(!value || !Array.isArray(value.carousels) || value.carousels.length<1 || value.carousels.length>3)throw new Error('Progetto non valido.');
  const stages=new Set();
  for(const item of value.carousels){
    if(!item || !Object.hasOwn(brand.funnels,item.stage) || stages.has(item.stage) || typeof item.caption!=='string' || item.caption.length>1800 || !Array.isArray(item.slides) || item.slides.length<5 || item.slides.length>9)throw new Error('Carosello non valido.');
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
