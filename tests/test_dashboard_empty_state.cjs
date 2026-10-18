const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const core = fs.readFileSync('static/dashboard/js/core.js', 'utf8');
const html = fs.readFileSync('static/dashboard/index.html', 'utf8');
const mapSource = fs.readFileSync('static/dashboard/js/dashboard-real-map.js', 'utf8');
const mapCss = fs.readFileSync('static/dashboard/css/dashboard-real-map.css', 'utf8');
const coreCss = fs.readFileSync('static/dashboard/css/core.css', 'utf8');
const heroStart = core.indexOf('function renderGFReferenceDashboardHero(summary){');
const heroEnd = core.indexOf('\nasync function loadDashboardHome(){', heroStart);
assert.ok(heroStart >= 0 && heroEnd > heroStart, 'la funzione della dashboard deve essere presente');
const heroSource = core.slice(heroStart, heroEnd);

function makeNode(id, initialClasses = []) {
  const classes = new Set(initialClasses);
  return {
    id, dataset: {}, isConnected: true, textContent: '', innerHTML: '', attributes: {},
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
      toggle(name, force) {
        const next = force === undefined ? !classes.has(name) : !!force;
        if (next) classes.add(name); else classes.delete(name);
        return next;
      },
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    querySelectorAll() { return []; },
    addEventListener() {},
    matches() { return false; },
    getAttribute() { return ''; },
  };
}

function makeHarness() {
  const ids = [
    'gfRefHeroWrap','gfRefRouteTitle','gfRefRouteSubtitle','gfRefRouteStatus','gfRefRouteDrawing',
    'gfRefDriver','gfRefVehicle','gfRefCompleted','gfRefRemaining','gfRefProgressBar','gfRefMissed',
    'gfRefStopList','gfRefOtherActive','gfRefEmptyState','gfRefOperationalDetail','gfRefRouteLegend',
  ];
  const nodes = new Map(ids.map(id => [id, makeNode(id, id === 'gfRefEmptyState' ? ['hidden'] : [])]));
  const mapCalls = [];
  const deposits = [{id:1,nome:'Deposito principale',indirizzo:'Via Roma 1',predefinito:true,lat:45.4064,lon:11.8768}];
  const context = vm.createContext({
    document: {getElementById: id => nodes.get(id) || null},
    currentSessionUser: {company_city:'Padova',company_address:'Via Roma 1',company_zip:'35100',company_country:'Italia'},
    api: async path => {
      if (path === '/api/deposits') return deposits;
      if (path === '/api/routes/42') return {consegne:[]};
      throw new Error('endpoint inatteso: ' + path);
    },
    gfWidth5: value => Math.max(0,Math.min(100,Math.round((Number(value)||0)/5)*5)),
    esc: value => String(value ?? ''),
    window: {
      GiroFacileDashboardMap: {
        reset() { mapCalls.push({type:'reset'}); },
        renderEmpty(element, area) { mapCalls.push({type:'renderEmpty',element,area}); return Promise.resolve(); },
        render() { mapCalls.push({type:'render'}); },
      },
    },
  });
  vm.runInContext(heroSource, context, {filename:'dashboard-hero-function.js'});
  return {nodes,mapCalls,deposits,context};
}

test('when there is no active route, the area map and branded first-route action are shown', async () => {
  const app = makeHarness();
  await vm.runInContext('renderGFReferenceDashboardHero(null)', app.context);
  const get = id => app.nodes.get(id);
  assert.equal(get('gfRefHeroWrap').classList.contains('has-route'), false);
  assert.equal(get('gfRefHeroWrap').classList.contains('is-empty'), true);
  assert.equal(get('gfRefEmptyState').classList.contains('hidden'), false);
  assert.equal(get('gfRefOperationalDetail').classList.contains('hidden'), true);
  assert.equal(get('gfRefRouteLegend').classList.contains('hidden'), true);
  assert.equal(get('gfRefRouteTitle').textContent, 'La tua area operativa');
  assert.equal(get('gfRefRouteStatus').textContent, 'Area operativa');
  assert.equal(app.mapCalls.filter(call => call.type === 'renderEmpty').length, 1);
  const area = app.mapCalls.find(call => call.type === 'renderEmpty').area;
  assert.equal(area.city, 'Padova');
  assert.equal(area.deposits[0].lat, 45.4064);
  assert.match(html, /id="gfRefEmptyState"/);
  assert.match(html, /La tua prossima consegna inizia da qui/);
  assert.match(html, /onclick="showTab\('giro'\)"/);
  assert.match(html, /Calcola il primo giro/);
  assert.match(mapSource, /async function renderEmpty\(element, area = \{\}\)/);
  assert.match(mapSource, /"padova":\[45\.4064,11\.8768\]/);
  assert.match(mapSource, /tile\.openstreetmap\.org/);
  assert.match(mapCss, /\.gf-route-panel__empty-icon/);
  assert.ok(coreCss.includes('body.workspace-empty-v49-active #tab-dashboard > :not(#workspaceEmptyDashboardV49):not(#gfRefHeroWrap)'), 'la mappa deve restare visibile anche durante la configurazione iniziale');
  assert.match(html, /gf_dashboard_empty_state_20261018/);
});

test('when an active route exists, the current route detail remains visible', async () => {
  const app = makeHarness();
  app.context.activeSummary = {id:42,nome:'Giro demo',consegne_count:2,completed_count:1,missed_count:0};
  await vm.runInContext('renderGFReferenceDashboardHero(activeSummary)', app.context);
  const get = id => app.nodes.get(id);
  assert.equal(get('gfRefHeroWrap').classList.contains('has-route'), true);
  assert.equal(get('gfRefHeroWrap').classList.contains('is-empty'), false);
  assert.equal(get('gfRefEmptyState').classList.contains('hidden'), true);
  assert.equal(get('gfRefOperationalDetail').classList.contains('hidden'), false);
  assert.equal(get('gfRefRouteLegend').classList.contains('hidden'), false);
  assert.equal(get('gfRefRouteTitle').textContent, 'Giro demo');
  assert.equal(app.mapCalls.filter(call => call.type === 'renderEmpty').length, 0);
});
