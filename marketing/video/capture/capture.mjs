// Cattura gli stati reali del gestionale (viewport 1440x1500, scala 2) e le posizioni degli elementi.
import { open, sleep } from './lib.mjs';
import { setv } from './flow.mjs';
import fs from 'fs';
const OUT = new URL('./', import.meta.url).pathname + 'cap/'; fs.mkdirSync(OUT, { recursive: true });
const { b, p } = await open({ scale: 2, w: 1440, h: 1500 });
const boxes = {};
const box = async (name, fn) => { boxes[name] = await p.evaluate(fn); };
const shot = async n => { await sleep(700); await p.screenshot({ path: OUT + n + '.png' }); console.log('shot', n); };
const vis = s => [...document.querySelectorAll(s)].filter(x => x.offsetParent !== null);
const R = e => { if (!e) return null; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
p.exposeFunction && 0;
await sleep(1000);
await p.evaluate(() => { const e = [...document.querySelectorAll('button')].find(x => x.innerText.includes('Ho capito')); e && e.click(); });
await p.evaluate(() => window.scrollTo(0, 0));

// D0: giri programmati prima
await p.evaluate(() => openDashboardScheduledPage()); await sleep(2000);
await shot('D0');

// A: clienti
await p.evaluate(() => choosePlanningStart('customers')); await sleep(2200);
await p.evaluate(() => window.scrollTo(0, 0));
await shot('A0');
for (let i = 0; i < 12; i++) { const bx = (await p.$$('tbody input[type=checkbox]'))[i]; await bx.click(); await sleep(120); }
await p.evaluate(() => window.scrollTo(0, 0));
await shot('A1');
boxes.rows = await p.evaluate(() => [...document.querySelectorAll('#tab-clienti tbody tr, tbody tr')].filter(x => x.offsetParent !== null).slice(0, 18).map(r => { const b = r.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; }));
boxes.thead = await p.evaluate(() => { const t = [...document.querySelectorAll('thead')].find(x => x.offsetParent !== null); const b = t.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; });
boxes.selbar = await p.evaluate(() => { const b = document.getElementById('customersGoPlanning'); let e = b; while (e && e.parentElement && e.parentElement.getBoundingClientRect().width < 700) e = e.parentElement; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.goBtn = await p.evaluate(() => { const r = document.getElementById('customersGoPlanning').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });

// B: pianificazione
await p.click('#customersGoPlanning'); await sleep(2500);
await p.evaluate(() => window.scrollTo(0, 0));
await shot('B0');
await setv(p, 'routeDate', '2026-11-18'); await sleep(600);
await shot('B1');
await setv(p, 'routeStart', '07:30'); await sleep(1000);
await shot('B2');
const fieldBox = id => p.evaluate(id => { let e = document.getElementById(id); const f = e.closest('label, .gf-field, div'); const r = f.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }, id);
boxes.fDate = await fieldBox('routeDate'); boxes.fStart = await fieldBox('routeStart');
boxes.kicker = await p.evaluate(() => { const r = document.getElementById('routeAutoNameTitle').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.headCard = await p.evaluate(() => { const r = document.getElementById('routeDate').closest('section, .gf-card, .gf-panel').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.segSingle = await p.evaluate(() => { const e = [...document.querySelectorAll('button')].filter(x => x.offsetParent !== null).find(x => x.innerText.trim() === 'Un solo mezzo'); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.segFleet = await p.evaluate(() => { const e = [...document.querySelectorAll('button')].filter(x => x.offsetParent !== null).find(x => x.innerText.trim() === 'Più mezzi'); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.whoCard = await p.evaluate(() => { const h = [...document.querySelectorAll('h2,h3')].find(x => x.innerText.trim() === 'Chi fa le consegne?'); const r = h.closest('section, .gf-card, .gf-panel').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
await p.evaluate(() => selectPlanningModeCard('fleet')); await sleep(1200);
await p.evaluate(() => document.getElementById('fleetAdd').click()); await sleep(800);
await p.evaluate(() => window.scrollTo(0, 0));
await shot('B3');
for (const [i, v, d] of [[0, '1', '1'], [1, '2', '2'], [2, '3', '3']]) { await setv(p, 'fleetVehicle' + i, v); await sleep(300); await setv(p, 'fleetDriver' + i, d); await sleep(300); }
await setv(p, 'fleetStrategy', 'balanced'); await sleep(900);
await p.evaluate(() => window.scrollTo(0, 0));
await shot('B4');
boxes.fleetCards = await p.evaluate(() => [0, 1, 2].map(i => { const r = document.getElementById('fleetVehicle' + i).closest('article, .gf-card, .gf-panel, .fleet-card, section').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
boxes.calcBtn = await p.evaluate(() => { const r = document.getElementById('routeCalculateBtn').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.calcBar = await p.evaluate(() => { let e = document.getElementById('routeCalculateBtn'); while (e.parentElement && e.parentElement.getBoundingClientRect().width < 700) e = e.parentElement; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.subtitle = await p.evaluate(() => { const r = document.getElementById('routeAutoNameTitle').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });

// C: anteprima calcolata
await p.evaluate(() => optimizeRoute());
for (let i = 0; i < 25; i++) { await sleep(1000); if (p.url().endsWith('#route-preview')) break; }
await sleep(3500);
await p.evaluate(() => window.scrollTo(0, 0));
await shot('C0');
boxes.kpis = await p.evaluate(() => { const t = [...document.querySelectorAll('*')].find(x => x.children.length === 0 && (x.innerText||'').trim() === 'Km totali'); let e = t; while (e && e.getBoundingClientRect().width < 1000) e = e.parentElement; return [...e.children].map(c => { const r = c.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); });
boxes.cmp = await p.evaluate(() => { const h = [...document.querySelectorAll('h2,h3')].find(x => x.innerText.trim() === 'Confronto dei giri'); const r = h.closest('section, .gf-card, .gf-panel').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.cmpRows = await p.evaluate(() => { const h = [...document.querySelectorAll('h2,h3')].find(x => x.innerText.trim() === 'Confronto dei giri'); return [...h.closest('section, .gf-card, .gf-panel').querySelectorAll('tbody tr')].map(r => { const b = r.getBoundingClientRect(); return { x: b.x, y: b.y, w: b.width, h: b.height }; }); });
boxes.map = await p.evaluate(() => { const m = document.querySelector('.leaflet-container'); const r = [...document.querySelectorAll('.leaflet-container')].filter(x => x.offsetParent !== null)[0].getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.planBtn = await p.evaluate(() => { const e = [...document.querySelectorAll('button')].filter(x => x.offsetParent !== null).find(x => x.innerText.trim() === 'Pianifica giri'); const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });

// D1: giri programmati dopo
await p.evaluate(() => { [...document.querySelectorAll('button')].filter(x => x.offsetParent !== null).find(x => x.innerText.trim() === 'Pianifica giri').click(); });
await sleep(1800);
await p.evaluate(() => window.scrollTo(0, 0));
await shot('D1');
boxes.days = await p.evaluate(() => { const t = [...document.querySelectorAll('*')].filter(x => x.children.length === 0 && x.offsetParent !== null && /^(LUN|MAR|MER|GIO|VEN|SAB|DOM)$/.test((x.innerText||'').trim())); return t.map(x => { let e = x; while (e.getBoundingClientRect().height < 300) e = e.parentElement; const r = e.getBoundingClientRect(); return { d: x.innerText.trim(), x: r.x, y: r.y, w: r.width, h: r.height }; }); });
boxes.toast = await p.evaluate(() => { const t = [...document.querySelectorAll('*')].filter(x => x.offsetParent !== null && x.children.length === 0 && (x.innerText || '').includes('Giri programmati correttamente'))[0]; let e = t; while (e.parentElement && e.parentElement.getBoundingClientRect().width < 500) e = e.parentElement; const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
boxes.dayTable = await p.evaluate(() => { const h = [...document.querySelectorAll('h2,h3')].filter(x => x.offsetParent !== null).find(x => /Mercoled/.test(x.innerText)); const r = h.closest('section, .gf-card, .gf-panel').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
fs.writeFileSync(OUT + 'boxes.json', JSON.stringify(boxes, null, 1));
await b.close();
console.log('done');
