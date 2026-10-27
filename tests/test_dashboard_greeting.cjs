const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const navigation = fs.readFileSync('static/dashboard/js/navigation.js', 'utf8');
const html = fs.readFileSync('static/dashboard/index.html', 'utf8');

function createContext({initialTime = '2026-10-18T09:59:00Z', visible = true, companyName = 'ALIMENTARI IORIO'} = {}) {
  let nowMs = Date.parse(initialTime);
  let hidden = !visible;
  let interval;
  const title = {textContent: ''};
  const dashboard = {classList: {contains: name => name === 'hidden' && hidden}};
  const values = new Map([
    ['girofacile_company_name', companyName],
    ['girofacile_account_name', 'PICCOLO'],
  ]);
  class ControlledDate extends Date {
    constructor(...args) {
      super(...(args.length ? args : [nowMs]));
    }
  }
  const context = vm.createContext({
    Date: ControlledDate,
    Intl,
    localStorage: {getItem: key => values.get(key) || null},
    currentSessionUser: {company_name: companyName, username: 'PICCOLO'},
    document: {
      getElementById: id => id === 'tab-dashboard' ? dashboard : id === 'workspacePageTitle' ? title : null,
      querySelectorAll: () => [],
      body: {classList: {toggle() {}}},
    },
    window: {
      setInterval(callback, milliseconds) {
        interval = {callback, milliseconds};
        return 1;
      },
    },
  });
  vm.runInContext(navigation, context, {filename: 'navigation.js'});
  return {
    context, title, interval: () => interval,
    setNow: value => { nowMs = Date.parse(value); },
    setHidden: value => { hidden = value; },
  };
}

test('dashboard greeting follows Italian time boundaries', () => {
  const app = createContext();
  const cases = [
    ['2026-10-18T02:59:00Z', 'Buonasera'],       // 04:59 a Roma
    ['2026-10-18T03:00:00Z', 'Buongiorno'],      // 05:00 a Roma
    ['2026-10-18T09:59:00Z', 'Buongiorno'],      // 11:59 a Roma
    ['2026-10-18T10:00:00Z', 'Buon pomeriggio'], // 12:00 a Roma
    ['2026-10-18T15:59:00Z', 'Buon pomeriggio'], // 17:59 a Roma
    ['2026-10-18T16:00:00Z', 'Buonasera'],       // 18:00 a Roma
  ];
  for (const [instant, greeting] of cases) {
    const actual = vm.runInContext('dashboardGreetingPrefix(new Date(' + JSON.stringify(instant) + '))', app.context);
    assert.equal(actual, greeting, instant);
  }
});

test('dashboard title keeps the company name and current greeting', () => {
  const app = createContext({initialTime:'2026-10-18T09:59:00Z'});
  assert.equal(vm.runInContext('dashboardGreetingTitle()', app.context), 'Buongiorno, ALIMENTARI IORIO');
  app.setNow('2026-10-18T10:00:00Z');
  assert.equal(vm.runInContext('dashboardGreetingTitle()', app.context), 'Buon pomeriggio, ALIMENTARI IORIO');
});

test('dashboard greeting refreshes every minute only while the dashboard is visible', () => {
  const app = createContext();
  assert.equal(app.interval()?.milliseconds, 60_000);
  app.setNow('2026-10-18T09:59:00Z');
  app.interval().callback();
  assert.equal(app.title.textContent, 'Buongiorno, ALIMENTARI IORIO');
  app.setNow('2026-10-18T10:00:00Z');
  app.interval().callback();
  assert.equal(app.title.textContent, 'Buon pomeriggio, ALIMENTARI IORIO');
  app.setHidden(true);
  app.title.textContent = 'Ordini';
  app.setNow('2026-10-18T16:00:00Z');
  app.interval().callback();
  assert.equal(app.title.textContent, 'Ordini', 'non deve sovrascrivere il titolo di un’altra sezione');
});

test('dashboard navigation script cache version is refreshed', () => {
  assert.match(html, /navigation\.js\?v=gf_bozze_pagina_20261027/);
});
