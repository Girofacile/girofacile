import puppeteer from 'puppeteer-core';
import fs from 'fs';
const LEAF = new URL('./', import.meta.url).pathname + 'node_modules/leaflet/dist/';
// tassello piatto nel colore mappa del design system (le tile OSM non sono raggiungibili da qui)
const TILE = fs.readFileSync(new URL('./', import.meta.url).pathname + 'tile.png');

export async function open({ scale = 2, w = 1440, h = 900 } = {}) {
  const b = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'],
    defaultViewport: { width: w, height: h, deviceScaleFactor: scale }, userDataDir: new URL('./', import.meta.url).pathname + 'profile' });
  const p = await b.newPage();
  await p.setRequestInterception(true);
  p.on('request', r => {
    const u = r.url();
    if (u.startsWith('https://unpkg.com/leaflet@1.9.4/dist/')) {
      const f = LEAF + u.split('/dist/')[1];
      if (fs.existsSync(f)) return r.respond({ status: 200, contentType: f.endsWith('.css') ? 'text/css' : f.endsWith('.png') ? 'image/png' : 'application/javascript', body: fs.readFileSync(f) });
    }
    if (u.includes('tile.openstreetmap.org')) return r.respond({ status: 200, contentType: 'image/png', body: TILE });
    if (u.startsWith('http://127.0.0.1') || u.startsWith('data:') || u.startsWith('blob:')) return r.continue();
    return r.abort();
  });
  p.on('pageerror', e => console.log('PAGEERR', e.message.slice(0, 200)));
  await p.goto('http://127.0.0.1:8000/login', { waitUntil: 'domcontentloaded' });
  await sleep(1200);
  if (p.url().includes('#') === false || (await p.$('#loginUser:not([hidden])'))) {
    const vis = await p.evaluate(() => { const e = document.getElementById('loginUser'); return e && e.offsetParent !== null; });
    if (vis) {
      await p.type('#loginUser', 'azienda_demo'); await p.type('#loginPass', 'DemoVideo2026!');
      await p.click('button[onclick="login()"]'); await sleep(3500);
    }
  }
  return { b, p };
}
export const sleep = ms => new Promise(r => setTimeout(r, ms));
export async function texts(p, sel) {
  return p.evaluate(s => [...document.querySelectorAll(s)].filter(e => e.offsetParent !== null).map(e => (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 80)).filter(Boolean), sel);
}
