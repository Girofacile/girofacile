/* Real browser smoke: node tests/check_tracking_responsive.js.
 * Serves committed assets locally; all application APIs are intercepted.
 * No production database, external browser page or messaging provider is used.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, 'test-results/tracking-browser');
  fs.mkdirSync(output, {recursive:true});
  const server = http.createServer((req,res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    const file = path.resolve(root, '.' + (pathname === '/tracking' ? '/static/tracking/index.html' : pathname));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404); res.end(); return; }
    const types = {'.html':'text/html', '.css':'text/css', '.js':'application/javascript', '.svg':'image/svg+xml'};
    res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({headless:true, ...(process.env.TRACKING_BROWSER_CHANNEL ? {channel:process.env.TRACKING_BROWSER_CHANNEL} : {})});
    const token = 'a'.repeat(64) + '.' + 'b'.repeat(64);
    const url = base + '/tracking#' + token;
    let body = {status:'in_consegna', scheduled_date:'2026-10-04', timezone:'Europe/Rome', eta:{at:'2026-10-04T15:35:00+02:00',source:'execution',updated_at:'2026-10-04T14:10:00+02:00'}, stops_before:3, completed_at:null, refresh_after_seconds:30};
    let code = 200, reads = 0;
    const page = await browser.newPage({timezoneId:'Pacific/Pago_Pago'});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('**/api/public/tracking', route => {
      assert.equal(route.request().headers()['x-tracking-token'], token);
      assert.equal(new URL(route.request().url()).search, '');
      reads++;
      return route.fulfill({status:code, contentType:'application/json', body:JSON.stringify(body)});
    });
    for (const width of [320,390,768,1440]) {
      await page.setViewportSize({width,height:900});
      await page.goto(url);
      await page.locator('#stops').waitFor({state:'visible'});
      assert.match(await page.locator('#stops').innerText(), /3 fermate previste/);
      assert.equal(await page.locator('#date').innerText(), '4 ottobre 2026');
      assert.match(await page.locator('#eta').innerText(), /15:35/);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({path:path.join(output,`customer-${width}.png`),fullPage:true});
    }
    // Advance the actual browser clock to verify automatic polling and terminal stop.
    await page.clock.install();
    body = {...body, status:'completata', eta:{at:null,source:null,updated_at:null}, stops_before:null,
      completed_at:'2026-10-04T15:32:00+02:00',refresh_after_seconds:0};
    await page.clock.fastForward(31000);
    await page.waitForFunction(() => document.querySelector('#title').textContent === 'Consegna completata');
    assert.equal(await page.locator('#refresh').isVisible(), false);
    const closedReads = reads;
    await page.clock.fastForward(90000);
    assert.equal(reads, closedReads);
    await page.clock.resume();
    await page.screenshot({path:path.join(output,'completed.png'),fullPage:true});
    code = 404;
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#message').textContent.includes('scaduto'));
    assert.equal(await page.locator('#details').isVisible(),false);
    code = 503;
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#message').textContent.includes('temporaneamente'));
    assert.equal(await page.locator('#details').isVisible(),false);
    await page.goto(base+'/tracking');
    await page.waitForFunction(() => document.querySelector('#message').textContent.includes('incompleto'));
    assert.deepEqual(errors, []);
    await page.close();

    const routeData = {id:1,nome:'Consegne del giorno',status:'programmato',data_giro:'2026-10-04',
      consegne:[{id:11,ordine:1,cliente_nome:'Cliente prova',indirizzo:'Via di prova',arrivo_stimato:'15:35',delivery_status:'in_attesa'}]};
    for (const [portal, width] of [['dashboard',390],['dashboard',1440],['mobile',390]]) {
      const company = await browser.newPage({viewport:{width,height:844}});
      let revoked = false;
      await company.route('**/api/**', route => {
        const pathname = new URL(route.request().url()).pathname;
        let data = [];
        if (pathname === '/api/deliveries/11/tracking') {
          revoked = route.request().method() === 'DELETE';
          data = revoked ? {ok:true} : {url,expires_at:'2026-10-12T00:00:00Z'};
        } else if (pathname === '/api/me') data = {authenticated:true,username:'test',company_name:'Test',
          role:'admin',onboarding_completed:true,workspace_operational:true,plan:'business',plan_status:'active',limits:{}};
        else if (pathname.endsWith('catalog.js')) {
          return route.fulfill({contentType:'application/javascript',body:'window.GF_PLANS = {};'});
        } else if (pathname.includes('profile') || pathname.includes('settings') || pathname.includes('status') || pathname.includes('my-plan')) data = {completed:true,workspace_operational:true};
        return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
      });
      await company.route(/^https:\/\//, route => route.abort());
      await company.goto(`${base}/static/${portal}/index.html`);
      await company.waitForFunction(() => typeof trackingButton === 'function');
      await company.evaluate(({portal, routeData}) => {
        document.body.innerHTML = '<div id="tracking-test"></div>';
        if (portal === 'dashboard') renderUnifiedRouteView(routeData,'tracking-test');
        else renderMobileRouteDetails(routeData,'tracking-test');
      }, {portal,routeData});
      await company.getByRole('button',{name:'Tracking cliente',exact:true}).click();
      await company.locator('[data-action="copy"]:enabled').waitFor();
      assert.equal(await company.locator('#customerTrackingUrl').inputValue(),url);
      const bounds = await company.locator('dialog').boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x+bounds.width <= width+1);
      assert.ok(await company.locator('dialog').evaluate(el => el.scrollWidth <= el.clientWidth));
      await company.screenshot({path:path.join(output,`${portal}-${width}-dialog.png`),fullPage:true});
      await company.getByRole('button',{name:'Copia link',exact:true}).click();
      await company.waitForFunction(() => /copiato|copia/.test(document.querySelector('#customerTrackingMessage').textContent));
      await company.evaluate(() => Object.defineProperty(navigator,'share', {configurable:true, value:async data => { window.trackingShared = data; }}));
      await company.getByRole('button',{name:'Condividi',exact:true}).click();
      assert.equal(await company.evaluate(() => window.trackingShared.url),url);
      await company.getByRole('button',{name:'Revoca link',exact:true}).click();
      await company.waitForFunction(() => document.querySelector('#customerTrackingMessage').textContent.includes('revocato'));
      assert.equal(revoked,true);
      assert.equal(await company.locator('#customerTrackingUrl').inputValue(),'');
      await company.getByRole('button',{name:'Chiudi',exact:true}).click();
      assert.equal(await company.locator('dialog').count(),0);
      await company.close();
    }
    console.log('PASS: customer 320/390/768/1440px, polling, completion, invalid links, outage, desktop/mobile company controls, copy and revocation.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { console.error(error); process.exitCode=1; });
