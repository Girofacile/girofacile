const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const landing = fs.readFileSync('static/landing/index.html', 'utf8');
const inlineScripts = [...landing.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
const billing = fs.readFileSync('static/dashboard/js/billing.js', 'utf8');

function plan(name, bonus, price = 29) {
  return {name, electric_vehicle_bonus: bonus, price_eur: price, trial_days: 14, max_customers: 100,
    max_routes_per_month: 20, max_deliveries_per_month: 500, max_deposits: 1,
    max_vehicles: 10, max_drivers: 10};
}
function render(plans) {
  const nodes = {publicPricing: {innerHTML: ''}, electricPlanBonuses: {innerHTML: ''},
    heroTrialCopy: {dataset: {publicTrialCopy: 'hero'}, textContent: ''},
    ctaTrialCopy: {dataset: {publicTrialCopy: 'cta'}, textContent: ''},
    trialAction: {textContent: ''}, trialStat: {textContent: ''}};
  const context = vm.createContext({
    window: {GF_PLANS: plans},
    document: {getElementById: id => nodes[id], querySelectorAll: selector => ({
      '[data-public-trial-copy]': [nodes.heroTrialCopy, nodes.ctaTrialCopy],
      '[data-public-trial-action]': [nodes.trialAction],
      '[data-public-trial-stat]': [nodes.trialStat],
    }[selector] || [])},
    fetch() { throw new Error('Landing must reuse the existing catalogue without new requests'); },
  });
  vm.runInContext(billing, context);
  for (const script of inlineScripts) vm.runInContext(script, context);
  return {nodes, context};
}

test('landing and price cards show configured electric bonuses as visible plan benefits', () => {
  const {nodes} = render({
    starter: plan('Starter', 1), business: plan('Business', 2, 59), pro: plan('Pro', 5, 99),
  });
  for (const label of ['+1 veicolo elettrico bonus', '+2 veicoli elettrici bonus', '+5 veicoli elettrici bonus']) {
    assert.ok(nodes.publicPricing.innerHTML.includes(label), label);
    assert.ok(nodes.electricPlanBonuses.innerHTML.includes(label), label);
  }
  assert.equal((nodes.publicPricing.innerHTML.match(/pricing-electric-bonus"/g) || []).length, 3);
  assert.equal((nodes.publicPricing.innerHTML.match(/Slot aggiuntivi riservati ai mezzi elettrici/g) || []).length, 3);
  assert.match(landing, /senza consumare gli slot standard/);
});

test('benefits follow catalogue changes instead of duplicated plan constants', () => {
  const {nodes, context} = render({starter: plan('Starter', 1), business: plan('Business', 2), pro: plan('Pro', 5)});
  context.window.GF_PLANS = {starter: plan('Starter', 4), business: plan('Business', 0), pro: plan('Pro', 9)};
  vm.runInContext('renderPublicPlans()', context);
  assert.match(nodes.publicPricing.innerHTML, /\+4 veicoli elettrici bonus/);
  assert.match(nodes.electricPlanBonuses.innerHTML, /\+9 veicoli elettrici bonus/);
  assert.doesNotMatch(nodes.electricPlanBonuses.innerHTML, /Business/);
  assert.equal((nodes.publicPricing.innerHTML.match(/pricing-electric-bonus"/g) || []).length, 2);
  assert.equal((nodes.publicPricing.innerHTML.match(/pricing-card"/g) || []).length, 3);
});

test('old or incomplete catalogues never advertise unavailable electric slots', () => {
  const {nodes} = render({starter: plan('Starter', undefined), business: plan('Business', -1), pro: plan('Pro', 'invalid')});
  assert.doesNotMatch(nodes.publicPricing.innerHTML, /pricing-electric-bonus"/);
  assert.equal(nodes.electricPlanBonuses.innerHTML, '');
  assert.equal((nodes.publicPricing.innerHTML.match(/Prova gratis per 14 giorni/g) || []).length, 3);
});

test('catalogue names, features and checkout keys are rendered safely', () => {
  const {nodes} = render({'evil"><img': plan('<img src=x onerror=attack()>', 2, '<script>bad</script>')});
  assert.doesNotMatch(nodes.publicPricing.innerHTML, /<img|<script>/);
  assert.doesNotMatch(nodes.electricPlanBonuses.innerHTML, /<img/);
  assert.match(nodes.publicPricing.innerHTML, /&lt;img/);
  assert.match(nodes.publicPricing.innerHTML, /plan=evil%22%3E%3Cimg/);
});

test('landing retains route planning and cost messaging without absolute sustainability claims', () => {
  assert.match(landing, /Più spazio alla mobilità elettrica/);
  assert.match(landing, /ridurre chilometri inutili/);
  assert.match(landing, /controllare costi e consumi/);
  assert.match(landing, /Pianifica le consegne in pochi minuti/);
  assert.doesNotMatch(landing, /zero emissioni|rende la tua azienda sostenibile/i);
  assert.match(landing, /<script src="\/api\/billing\/catalog.js"><\/script>/);
});

test('electric section and price cards share responsive styles without hiding benefits on mobile', () => {
  assert.match(landing, /<meta name="viewport" content="width=device-width, initial-scale=1.0">/);
  // Layout from the shared components: wrapping badges and a price grid that stacks on phones.
  assert.doesNotMatch(landing, /<style[\s>]|\sstyle="/, 'No page-specific CSS or inline styles');
  assert.match(landing, /class="gf-panel electric-inner"/);
  assert.match(landing, /class="gf-cluster" id="electricPlanBonuses"/);
  assert.match(landing, /class="gf-grid pricing-grid" data-cols="3" id="publicPricing"/);
  assert.match(landing, /class="gf-badge electric-plan-bonus"/);
  assert.match(landing, /aria-labelledby="electricMobilityTitle"/);
});

test('every inline public script parses', () => {
  for (const script of inlineScripts) new vm.Script(script);
});


test('public trial copy follows runtime duration including a disabled trial', () => {
  const {nodes, context} = render({starter: {...plan('Starter', 1), trial_days: 7}});
  assert.match(nodes.publicPricing.innerHTML, /Prova gratis per 7 giorni/);
  assert.match(nodes.heroTrialCopy.textContent, /7 giorni di prova gratuita/);
  assert.match(nodes.ctaTrialCopy.textContent, /7 giorni/);
  assert.equal(nodes.trialStat.textContent, '7 gg');
  assert.doesNotMatch(nodes.publicPricing.innerHTML, /14 giorni/);
  context.window.GF_PLANS.starter.trial_days = 0;
  vm.runInContext('renderPublicPlans(); renderPublicTrial()', context);
  assert.match(nodes.publicPricing.innerHTML, /Scopri il piano/);
  assert.doesNotMatch(nodes.publicPricing.innerHTML, /Prova gratis/);
  assert.doesNotMatch(nodes.heroTrialCopy.textContent, /gratuit|prova/);
  assert.doesNotMatch(nodes.ctaTrialCopy.textContent, /gratuit|prova/);
  assert.equal(nodes.trialAction.textContent, 'Scopri il piano');
  assert.equal(nodes.trialStat.textContent, '—');
  context.window.GF_PLANS.starter.trial_days = 1;
  vm.runInContext('renderPublicPlans()', context);
  assert.match(nodes.publicPricing.innerHTML, /Prova gratis per 1 giorno</);
});
