const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

test('billing UI parses, uses server catalogue and preserves commercial entitlements', () => {
  const context = vm.createContext({window:{GF_PLANS:{starter:{name:'Starter',price_eur:29,max_customers:150,
    max_routes_per_month:100,max_deliveries_per_month:2000,max_deposits:1,max_vehicles:3,max_drivers:3,has_ai:false}}}});
  vm.runInContext(readFileSync('static/dashboard/js/billing.js','utf8'),context);
  const card = vm.runInContext("planFeatures('starter')", context);
  assert.equal(card.price,'€29');
  assert.ok(card.features.includes('150 clienti'));
  assert.ok(card.features.includes('100 giri/mese'));
  assert.ok(card.missing.includes('Funzioni AI senza quota mensile'));
  assert.ok(!readFileSync('static/dashboard/js/core.js','utf8').includes('/api/billing/select-plan'));
});

test('all modified HTML inline scripts parse', () => {
  for (const path of ['static/admin/index.html','static/landing/index.html','static/mobile/index.html']) {
    const html=readFileSync(path,'utf8');
    for(const [,source] of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(source,{filename:path});
  }
});
