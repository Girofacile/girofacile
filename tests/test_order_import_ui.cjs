const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const script = fs.readFileSync('static/dashboard/js/order-import.js', 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

// Pop-up di importazione con un DOM minimo: file con codice univoco («ID») diverso dal numero ordine («Num»).
function harness() {
  const nodes = {};
  const node = () => ({innerHTML: '', textContent: '', hidden: false, open: false, value: '',
    files: [{name: 'ordini.csv', size: 100}], setAttribute() {}, replaceChildren() { this.innerHTML = ''; },
    closest: () => ({}), querySelectorAll: () => [], focus() {}, showModal() { this.open = true; }, close() {}});
  const selects = [];
  const timers = new Map();
  let timerId = 0;
  const requests = [];
  let holdPreview = null;
  const make = id => ({id, kind: 'file', status: 'active', version: 1, fields_configured: true, excluded_fields: [],
    mapping: {external_id: 'ID', number: 'Num', recipient_name: 'Nome', delivery_address: 'Indirizzo'}});
  const sources = {1: make(1), 2: make(2)};
  const respond = (path, options) => {
    const body = options?.body && typeof options.body === 'string' ? JSON.parse(options.body) : null;
    requests.push({path, method: options?.method || 'GET', body});
    if (path === '/api/order-sources') return {items: Object.values(sources), fields: ['external_id', 'number', 'recipient_name', 'delivery_address', 'phone'], total: 1};
    if (path.endsWith('/upload')) return {headers: ['ID', 'Num', 'Nome', 'Indirizzo', 'Telefono'], sample: [], total: 2, run_id: 5, suggested_mapping: {}};
    const saved = path.match(/^\/api\/order-sources\/(\d+)$/);
    if (saved && body) { const source = sources[saved[1]]; Object.assign(source, {mapping: body.mapping, version: source.version + 1}); return {...source}; }
    if (path.endsWith('/preview')) return {status: 'preview_ready', report: {total: 2}, rows: [], offset: 0};
    throw new Error('richiesta inattesa ' + path);
  };
  const context = vm.createContext({
    window: {},
    document: {
      getElementById: id => nodes[id] || (nodes[id] = node()),
      querySelectorAll: selector => selector === '[data-import-field]' ? selects : [],
    },
    FormData: class { append() {} },
    esc: value => String(value),
    gfCount: (n, one, many) => n + ' ' + (n === 1 ? one : many),
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: id => timers.delete(id),
    fetch: async (path, options) => {
      const data = respond(path, options);
      if (path.endsWith('/preview') && holdPreview) await holdPreview.promise;
      return {ok: true, json: async () => data};
    },
  });
  vm.runInContext(script, context);
  const api = context.window.GFOrderImport;
  return {
    api, nodes, requests, selects,
    select(field, value) { const found = selects.find(s => s.dataset.importField === field); if (found) found.value = value; else selects.push({dataset: {importField: field}, value}); },
    async runTimers() { const pending = [...timers.values()]; timers.clear(); pending.forEach(fn => fn()); for (let i = 0; i < 10; i += 1) await tick(); },
    hold() { let resolve; holdPreview = {promise: new Promise(r => { resolve = r; })}; return () => { holdPreview = null; resolve(); }; },
  };
}

async function uploaded(h) {
  await h.api.start(1);
  await h.api.upload();
  for (const [field, value] of [['number', 'Num'], ['recipient_name', 'Nome'], ['delivery_address', 'Indirizzo']]) h.select(field, value);
}

test('changing a column keeps the file own unique code instead of replacing it with the order number', async () => {
  const h = harness();
  await uploaded(h);
  h.select('phone', 'Telefono');
  h.api.changed();
  await h.runTimers();
  const saved = h.requests.filter(r => r.path === '/api/order-sources/1' && r.method === 'PUT');
  assert.equal(saved.length, 1);
  assert.equal(saved[0].body.mapping.external_id, 'ID');
  assert.equal(saved[0].body.mapping.number, 'Num');
  assert.match(h.nodes.orderImportConfirm.innerHTML, /orderImportCommit/);
});

test('a column changed while the check is running is checked again and the import button appears', async () => {
  const h = harness();
  const release = h.hold();
  const start = h.api.start(1).then(() => h.api.upload());
  for (let i = 0; i < 10; i += 1) await tick();
  // Il controllo automatico dopo il caricamento è in corso: si cambia una colonna.
  for (const [field, value] of [['number', 'Num'], ['recipient_name', 'Nome'], ['delivery_address', 'Indirizzo'], ['phone', 'Telefono']]) h.select(field, value);
  h.api.changed();
  await h.runTimers();
  assert.match(h.nodes.orderImportConfirm.innerHTML, /Controllo dei dati in corso/);
  release();
  await start;
  await h.runTimers();
  await h.runTimers();
  assert.match(h.nodes.orderImportConfirm.innerHTML, /orderImportCommit/);
  assert.equal(h.requests.filter(r => r.path.endsWith('/preview')).length, 2);
});

test('choosing the unique-code column as order number and back still keeps the unique code', async () => {
  const h = harness();
  await uploaded(h);
  h.select('number', 'ID');
  h.api.changed();
  h.select('number', 'Num');
  h.select('phone', 'Telefono');
  h.api.changed();
  await h.runTimers();
  const saved = h.requests.filter(r => r.path === '/api/order-sources/1' && r.method === 'PUT');
  assert.equal(saved.length, 1);
  assert.equal(saved[0].body.mapping.external_id, 'ID');
});

test('closing and opening another source cancels the pending check of the first one', async () => {
  const h = harness();
  await uploaded(h);
  h.select('phone', 'Telefono');
  h.api.changed();
  h.api.close();
  await h.api.start(2);
  await h.runTimers();
  assert.deepEqual(h.requests.filter(r => r.method === 'PUT'), []);
  assert.equal(h.requests.filter(r => r.path.endsWith('/preview')).length, 1);
});
