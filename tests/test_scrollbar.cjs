const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
// Barre di scorrimento (1° novembre 2026): sottili, grigie, frecce dello stesso grigio, anche nelle aree interne.
const theme=fs.readFileSync('static/design-system/theme.css','utf8');
const components=fs.readFileSync('static/design-system/components.css','utf8');
test('i colori della barra vengono dal tema: grigio tra bordi e testi secondari, frecce dello stesso grigio',()=>{
  assert.match(theme,/--gf-color-scrollbar: color-mix\(in srgb, var\(--gf-color-border\) 55%, var\(--gf-color-muted\)\);/);
  assert.match(theme,/--gf-color-scrollbar-arrow: var\(--gf-color-scrollbar\);/);
  assert.match(theme,/--gf-color-scrollbar-arrow-hover: var\(--gf-color-scrollbar-hover\);/);
});
test('pagina e aree interne usano la barra sottile con una freccia per estremità',()=>{
  const scope=':where(html:has(>body[data-gf-surface]),body[data-gf-surface] *)';
  for(const rule of ['::-webkit-scrollbar{width:var(--gf-space-2)','::-webkit-scrollbar-thumb{border-radius:var(--gf-radius-pill);background:var(--gf-color-scrollbar)}',
    '::-webkit-scrollbar-button{display:none}','::-webkit-scrollbar-button:single-button:vertical:decrement{background-image:conic-gradient(',
    '::-webkit-scrollbar-button:single-button:vertical:increment{background-image:conic-gradient('])
    assert.ok(components.includes(scope+rule),rule);
  assert.match(components,/\.gf-sidebar::-webkit-scrollbar-thumb\{background:var\(--gf-color-nav-selected-bg\)\}/);
});
test('scrollbar-color resta solo per Firefox: in Chrome annullerebbe frecce e forma della barra',()=>{
  const css=fs.readdirSync('static/design-system').filter(f=>f.endsWith('.css')).map(f=>fs.readFileSync('static/design-system/'+f,'utf8')).join('\n');
  const outside=css.replace(/@supports not selector\(::-webkit-scrollbar\)\{[^]*?\n\}/g,'');
  assert.doesNotMatch(outside,/scrollbar-(color|width)\s*:/);
});
