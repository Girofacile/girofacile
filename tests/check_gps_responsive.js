/* Local browser integration: mocked GPS/network, real portal and Leaflet UI. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require('playwright');

async function main() {
  const root = path.resolve(__dirname,'..');
  const output = path.join(root,'test-results/gps-browser');
  fs.mkdirSync(output,{recursive:true});
  const leaflet = process.env.GPS_LEAFLET_DIR || path.dirname(require.resolve('leaflet/package.json'));
  const server = http.createServer((req,res) => {
    let pathname = new URL(req.url,'http://localhost').pathname;
    if (pathname.startsWith('/giro/')) pathname = '/static/operator/index.html';
    const file = path.resolve(root,'.'+pathname);
    if (!file.startsWith(root+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type', {'.html':'text/html','.css':'text/css','.js':'application/javascript'}[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({headless:true,...(process.env.TRACKING_BROWSER_CHANNEL ? {channel:process.env.TRACKING_BROWSER_CHANNEL}:{})});
    const errors=[];
    const detail={route:{id:1,nome:'Consegne Milano centro',status:'programmato',data_giro:'2026-10-05',orario_partenza:'08:00',driver_nome:'Marco Rossi'},
      consegne:[{id:11,ordine:1,cliente_nome:'Farmacia Centrale',indirizzo:'Via Roma 12, Milano',status:'in_attesa',arrivo_stimato:'10:30'}],
      progress:{totale:1,completate:0,mancate:0,rimanenti:1,percentuale:0,prossima_idx:0},tempo_scarico_options:[10,20],motivi_mancata:[],settings:{}};
    for (const portal of ['operator','driver']) {
      const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.clock.install();
      await page.addInitScript(() => {
        window.gpsCalls=0; window.gpsMode='ok';window.testHidden=false;
        Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.testHidden});
        Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(success,error){
          window.gpsCalls++;
          if(window.gpsMode==='denied') error({code:1});
          else if(window.gpsMode==='timeout') error({code:3});
          else success({timestamp:Date.now(),coords:{latitude:45.46,longitude:9.19,accuracy:20}});
        }}});
      });
      let uploads=0, closed=false, routeState='programmato', outage=false;
      await page.route('**/api/**', async route => {
        const url=new URL(route.request().url()).pathname;
        if (url.endsWith('/position')) {
          if(route.request().method()==='GET') return route.fulfill({json:{active:!closed && routeState==='in_corso'}});
          if(outage) return route.abort();
          uploads++;
          return route.fulfill({json:{accepted:true,captured_at:new Date().toISOString()}});
        }
        if (url.endsWith('/start')) routeState='in_corso';
        let body={};
        if(url==='/api/driver/me') body={driver_name:'Marco Rossi',driver_id:1};
        else if(url==='/api/driver/routes') body=[];
        else if(url.includes('/chat')) body=[];
        else if(url==='/api/operator/test-route' || url==='/api/driver/routes/1') body={...detail,route:{...detail.route,status:closed?'completato':routeState}};
        return route.fulfill({json:body});
      });
      await page.route(/^https:\/\//, route=>route.abort());
      await page.goto(portal==='operator'?base+'/giro/test-route':base+'/static/driver/index.html');
      if(portal==='driver') await page.evaluate(()=>openExecution(1));
      await page.locator('[data-gps-status]').waitFor({state:'visible'});
      assert.equal(uploads,0); assert.equal(await page.evaluate(()=>window.gpsCalls),0);
      if(portal==='operator') await page.locator('#operatorStartGPS').click();
      else await page.evaluate(()=>startRoute(1));
      await page.waitForFunction(()=>document.querySelector('[data-gps-status]').dataset.state==='active');
      assert.equal(uploads,1);
      if(portal==='operator') {
        assert.equal(await page.locator('#loadingScreen').isVisible(),false);
        assert.equal(await page.locator('#errorScreen').isVisible(),false);
        assert.equal(await page.locator('#completedScreen').isVisible(),false);
      }
      for(const width of [320,390,768,1440]) {
        await page.setViewportSize({width,height:900});
        await page.evaluate(()=>window.scrollTo(0,0));
        const box=await page.locator('[data-gps-status]').boundingBox();
        assert.ok(box.x>=0 && box.x+box.width<=width+1);
        assert.ok(await page.locator('[data-gps-status]').evaluate(el=>el.scrollWidth<=el.clientWidth));
        await page.screenshot({path:path.join(output,`${portal}-${width}.png`),fullPage:true});
      }
      await page.evaluate(()=>{window.testHidden=true;document.dispatchEvent(new Event('visibilitychange'));});
      const before=uploads;
      await page.clock.fastForward(90000);
      assert.equal(uploads,before);
      await page.evaluate(()=>{window.testHidden=false;window.gpsMode='denied';document.dispatchEvent(new Event('visibilitychange'));});
      await page.waitForFunction(()=>document.querySelector('[data-gps-status]').dataset.state==='denied');
      const deniedCalls=await page.evaluate(()=>window.gpsCalls);
      await page.clock.fastForward(60000);
      assert.equal(await page.evaluate(()=>window.gpsCalls),deniedCalls);
      await page.evaluate(()=>window.gpsMode='ok');
      await page.locator('[data-gps-retry]').click();
      await page.waitForFunction(()=>document.querySelector('[data-gps-status]').dataset.state==='active');
      outage=true;
      await page.clock.fastForward(31000);
      await page.waitForFunction(()=>document.querySelector('[data-gps-status]').dataset.state==='error');
      outage=false;
      await page.evaluate(()=>window.dispatchEvent(new Event('online')));
      await page.waitForFunction(()=>document.querySelector('[data-gps-status]').dataset.state==='active');
      closed=true;
      await page.clock.fastForward(31000);
      await page.waitForFunction(()=>document.querySelector('[data-gps-message]').textContent.includes('terminato'));
      const count=uploads;
      await page.clock.fastForward(90000);
      assert.equal(uploads,count);
      await page.close();
    }
    const company=await browser.newPage();company.on('pageerror',e=>errors.push(e.message));
    await company.clock.install();
    let state='fresh', offline=false, reads=0;
    await company.route('**/api/**',route=>{
      const url=new URL(route.request().url()).pathname;
      if(url==='/api/routes/1/position') {
        reads++;
        if(offline) return route.abort();
        return route.fulfill({json:{state,route_status:'in_corso',route_name:'Consegne Milano centro',vehicle_name:'Furgone 03',next_stop:'Farmacia Centrale',progress:40,
          position:state==='unavailable'?null:{latitude:45.46,longitude:9.19,accuracy:20,captured_at:new Date().toISOString()}}});
      }
      let data=[];
      if(url==='/api/me')data={authenticated:true,username:'test',role:'admin',onboarding_completed:true,workspace_operational:true,plan:'business',plan_status:'active',limits:{}};
      else if(url.includes('chat'))data={messages:[],unread:0};
      else if(url.endsWith('catalog.js'))return route.fulfill({contentType:'application/javascript',body:'window.GF_PLANS={};'});
      else if(/profile|settings|status|my-plan/.test(url))data={completed:true,workspace_operational:true};
      return route.fulfill({json:data});
    });
    await company.route(/^https:\/\//, route=>{
      const url=route.request().url();
      if(url.endsWith('leaflet.js') || url.endsWith('leaflet.css')) return route.fulfill({path:path.join(leaflet,'dist',url.endsWith('.js')?'leaflet.js':'leaflet.css')});
      if(url.includes('tile.openstreetmap.org'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#edf2ee"/><path d="M0 80H256M90 0V256M0 210H256" stroke="white" stroke-width="14"/></svg>'});
      return route.abort();
    });
    await company.goto(base+'/static/dashboard/index.html');
    await company.waitForFunction(()=>typeof renderDashboardInProgressSubpage==='function');
    await company.evaluate(()=>{
      document.body.innerHTML='<div id="app"><div class="gf-page"><div id="dashboardInProgressPage"></div></div></div>';
      const r={id:1,nome:'Consegne Milano centro',status:'in_corso',driver_name:'Marco Rossi',vehicle_name:'Furgone 03',consegne:[]};
      renderDashboardInProgressSubpage([r],r);
    });
    await company.locator('.gf-live-vehicle').waitFor();
    for(const width of [320,390,768,1440]) {
      await company.setViewportSize({width,height:1100});
      const box=await company.locator('#dashboardLiveGPS').boundingBox();
      assert.ok(box.x>=0 && box.x+box.width<=width+1,JSON.stringify(box));
      assert.ok(await company.locator('#dashboardLiveGPS').evaluate(el=>el.scrollWidth<=el.clientWidth));
      await company.screenshot({path:path.join(output,`dashboard-${width}.png`),fullPage:true});
    }
    state='stale';await company.clock.fastForward(31000);
    await company.waitForFunction(()=>document.querySelector('#dashboardLiveGPS').dataset.state==='stale');
    assert.equal(await company.locator('.gf-live-vehicle').evaluate(el=>el.style.opacity),'0.45');
    offline=true;await company.clock.fastForward(31000);
    await company.waitForFunction(()=>document.querySelector('[data-gps-state]').textContent.includes('Connessione'));
    offline=false;state='unavailable';await company.clock.fastForward(31000);
    await company.waitForFunction(()=>document.querySelector('#dashboardLiveGPS').dataset.state==='unavailable');
    assert.equal(await company.locator('.gf-live-vehicle').count(),0);
    assert.ok(reads>=4);
    assert.deepEqual(errors,[]);
    console.log('PASS GPS: driver/operator lifecycle, denial, background, reconnect; dashboard fresh/stale/offline; 320/390/768/1440px.');
  } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
