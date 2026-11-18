const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

test('billing UI parses, uses server catalogue and preserves commercial entitlements', () => {
  const context = vm.createContext({window:{GF_PLANS:{starter:{name:'Starter',price_eur:29,max_customers:150,
    max_orders_per_month:300,max_collaborators:2,max_deposits:1,max_vehicles:3,max_drivers:3,has_ai:false}}}});
  vm.runInContext(readFileSync('static/dashboard/js/billing.js','utf8'),context);
  const card = vm.runInContext("planFeatures('starter')", context);
  assert.equal(card.price,'€29');
  assert.ok(card.features.includes('150 clienti'));
  assert.ok(card.features.includes('300 ordini/mese'));
  assert.ok(card.missing.includes('Integrazione AI'));
  assert.ok(!readFileSync('static/dashboard/js/core.js','utf8').includes('/api/billing/select-plan'));
});

test('all modified HTML inline scripts parse', () => {
  for (const path of ['static/admin/index.html','static/landing/index.html','static/mobile/index.html']) {
    const html=readFileSync(path,'utf8');
    for(const [,source] of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(source,{filename:path});
  }
});

async function pendingChangeRun(answers) {
  const calls = [], asked = [], went = [];
  const context = vm.createContext({window:{GF_PLANS:{starter:{name:'Starter',price_eur:29},business:{name:'Business',price_eur:59}},
      GFCompanyAccess:{isCollaborator:()=>false}, location:{assign:url=>went.push(url)}},
    document:{getElementById:()=>null}, console,
    confirm:text=>{asked.push(text); return answers.shift();}, toast:()=>{}, alert:text=>{throw new Error(text);}});
  vm.runInContext(readFileSync('static/dashboard/js/billing.js','utf8'),context);
  context.api = async (url, options) => {
    calls.push(url);
    if (url === '/api/billing/my-plan') return {plan_status:'active', billing:{checkout_enabled:true, subscription:true, mode:'live'}};
    if (url === '/api/billing/change-preview') return {direction:'pending', plan:'business', plan_name:'Business',
      payment_url:'https://invoice.stripe.com/i/change', amount_due_cents:2999};
    if (url === '/api/billing/cancel-checkout') return {ok:true, message:'Cambio piano in attesa annullato'};
    throw new Error('chiamata inattesa ' + url);
  };
  context.fmtEuroV63 = n => `€${n.toFixed(2)}`;
  context.refreshPlanPageAfterBilling = async () => calls.push('refresh');
  context.renderSubscriptionControls = () => {};
  vm.runInContext("_selectedUpgradePlan='business'; _currentPlan='starter';", context);
  await vm.runInContext('checkoutOrChangePlan()', context);
  return {calls, asked, went};
}

test('a plan change left unpaid can be paid now or cancelled instead of blocking the page', async () => {
  const pay = await pendingChangeRun([true]);
  assert.deepEqual(pay.went, ['https://invoice.stripe.com/i/change']);
  assert.match(pay.asked[0], /passaggio a Business aspetta ancora il pagamento \(€29\.99\)/);
  assert.ok(!pay.calls.includes('/api/billing/change-plan'));

  const cancel = await pendingChangeRun([false, true]);
  assert.deepEqual(cancel.went, []);
  assert.ok(cancel.calls.includes('/api/billing/cancel-checkout') && cancel.calls.includes('refresh'));

  const keep = await pendingChangeRun([false, false]);
  assert.ok(!keep.calls.includes('/api/billing/cancel-checkout'));
});
