// La pagina aperta resta nell'indirizzo: F5 la riapre, Indietro/Avanti la cambiano.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const navigation = fs.readFileSync('static/dashboard/js/navigation.js', 'utf8');
const NAMES = ['dashboard', 'ordini', 'mezzi', 'giro', 'ordini-importa', 'settings'];

function createApp({hash = '', allowed = () => true} = {}) {
  const tabs = new Map(NAMES.map(name => [name, {id: 'tab-' + name, hidden: name !== 'dashboard'}]));
  const tab = item => ({id: item.id, classList: {contains: c => c === 'hidden' && item.hidden}});
  const location = {pathname: '/dashboard', search: '', hash};
  const entries = [location.hash];
  const listeners = {};
  const history = {
    pushState(_, __, url) { location.hash = url.slice(url.indexOf('#')); entries.push(location.hash); },
    replaceState(_, __, url) { location.hash = url.slice(url.indexOf('#')); entries[entries.length - 1] = location.hash; },
  };
  const context = vm.createContext({
    document: {
      getElementById: id => (tabs.get(id.replace(/^tab-/, '')) ? tab(tabs.get(id.replace(/^tab-/, ''))) : null),
      querySelector: () => { const open = [...tabs.values()].find(item => !item.hidden); return open ? tab(open) : null; },
      querySelectorAll: () => [],
      body: {classList: {toggle() {}}},
    },
    window: {location, history, addEventListener: (name, fn) => { listeners[name] = fn; }, setInterval() {}, GFCompanyAccess: {allowedTab: allowed}},
    GFCompanyAccess: {allowedTab: allowed},
  });
  vm.runInContext(navigation, context, {filename: 'navigation.js'});
  const shown = [];
  // Versione ridotta di showTab: cambia la pagina visibile e la ricorda come quella vera.
  context.showTab = name => {
    if (name === 'blocked') return;
    shown.push(name);
    context.rememberTab(name);
    tabs.forEach((item, key) => { item.hidden = key !== name; });
  };
  const back = () => { entries.pop(); location.hash = entries[entries.length - 1]; listeners.popstate(); };
  return {context, location, entries, shown, back, visible: () => context.visibleTab()};
}

test('F5 reopens the page written in the address', () => {
  const app = createApp({hash: '#mezzi'});
  app.context.restoreTabFromUrl(null);
  assert.equal(app.visible(), 'mezzi');
  assert.deepEqual(app.entries, ['#mezzi']);
});

test('pages that depend on unfinished work reopen their starting page', () => {
  for (const hash of ['#giro', '#ordini-importa']) {
    const app = createApp({hash});
    app.context.restoreTabFromUrl(null);
    assert.equal(app.visible(), 'ordini');
    assert.equal(app.location.hash, '#ordini');
  }
});

test('without a saved page the dashboard stays open and is not reloaded twice', () => {
  const app = createApp();
  app.context.restoreTabFromUrl(null);
  assert.deepEqual(app.shown, []);
  assert.equal(app.location.hash, '#dashboard');
});

test('unknown or forbidden pages fall back safely', () => {
  const unknown = createApp({hash: '#<script>'});
  unknown.context.restoreTabFromUrl(null);
  assert.equal(unknown.visible(), 'dashboard');
  const forbidden = createApp({hash: '#mezzi', allowed: name => name !== 'mezzi'});
  forbidden.context.restoreTabFromUrl('settings');
  assert.equal(forbidden.visible(), 'settings');
  assert.equal(forbidden.location.hash, '#settings');
});

test('browser back and forward move between portal pages', () => {
  const app = createApp();
  app.context.restoreTabFromUrl(null);
  app.context.showTab('ordini');
  app.context.showTab('mezzi');
  assert.deepEqual(app.entries, ['#dashboard', '#ordini', '#mezzi']);
  app.back();
  assert.equal(app.visible(), 'ordini');
  app.back();
  assert.equal(app.visible(), 'dashboard');
  assert.deepEqual(app.entries, ['#dashboard']);
});

test('a page opened while the portal was still loading is not replaced', () => {
  const app = createApp({hash: '#mezzi'});
  app.context.showTab('ordini');
  app.context.restoreTabFromUrl(null);
  assert.equal(app.visible(), 'ordini');
  assert.equal(app.location.hash, '#ordini');
});
