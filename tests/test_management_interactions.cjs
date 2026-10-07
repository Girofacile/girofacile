const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const core = fs.readFileSync('static/dashboard/js/core.js', 'utf8');

test('notification triggers stay open after their bubbling click, outside click and Escape close them', () => {
  const classes = new Set(['hidden']);
  const buttons = [new Map(), new Map()];
  const listeners = {};
  const context = vm.createContext({
    document: {
      getElementById: () => ({classList: {
        contains: value => classes.has(value),
        toggle: (value, force) => force ? classes.add(value) : classes.delete(value),
      }}),
      querySelectorAll: () => buttons.map(button => ({setAttribute: (k,v) => button.set(k,v)})),
      addEventListener: (name, fn) => listeners[name] = fn,
    },
    loadNotificationsV30: () => {},
  });
  vm.runInContext(core.slice(core.indexOf('function showNotificationsDropdownV30('), core.indexOf('window.toggleNotificationsDropdown =')), context);
  for (const selector of ['.notification-center-v30', '[data-gf-notification-trigger]']) {
    vm.runInContext('toggleNotificationsDropdown()', context);
    listeners.click({target:{closest: selectors => selectors.includes(selector) ? {} : null}});
    assert.equal(classes.has('hidden'), false, selector);
    assert.ok(buttons.every(button => button.get('aria-expanded') === 'true'));
    listeners.keydown({key:'Escape'});
    assert.equal(classes.has('hidden'), true);
  }
  vm.runInContext('toggleNotificationsDropdown()', context);
  listeners.click({target:{closest: () => null}});
  assert.equal(classes.has('hidden'), true);
  assert.ok(buttons.every(button => button.get('aria-expanded') === 'false'));
});

test('live route detail renders stops, routing summary and chat without undeclared preview variables', () => {
  const node = {innerHTML:''};
  const chats = [];
  const context = vm.createContext({
    document:{getElementById: () => node},
    esc: value => String(value ?? ''),
    dashboardRoutePicker: () => '',
    dashboardRouteSummaryCards: () => '<div>Metrics</div>',
    dashboardStopRowsUnified: () => '<table>Stops</table>',
    loadDashboardRouteChat: id => chats.push(id),
    GiroFacileLiveMap:{mount(){}},
    window:{GiroFacileRouting:{summaryHtml: route => `<div>Routing ${route.id}</div>`}},
    route:{id:42,status:'in_corso',consegne:[{cliente_nome:'Demo',delivery_status:'in_attesa'}]},
  });
  vm.runInContext(core.slice(core.indexOf('function renderDashboardInProgressSubpage('), core.indexOf('function renderUnifiedRouteView(')), context);
  vm.runInContext('renderDashboardInProgressSubpage([route], route)', context);
  assert.match(node.innerHTML, /Routing 42/);
  assert.match(node.innerHTML, /<table>Stops<\/table>/);
  assert.match(node.innerHTML, /sendDashboardRouteChat\(42\)/);
  assert.deepEqual(chats, [42]);
  vm.runInContext('renderDashboardInProgressSubpage([], null)', context);
  assert.match(node.innerHTML, /Nessun giro in corso/);
});


test('company dirty-state blocks navigation until save or cancel', () => {
  const navigation = fs.readFileSync('static/dashboard/js/navigation.js', 'utf8');
  const start = navigation.indexOf('function showTab(name)');
  const end = navigation.length;
  const classes = new Set();
  let blockedCalls = 0;
  const tabs = {
    'tab-company': {classList:{add(){},remove(){}}},
    'tab-dashboard': {classList:{add(){},remove(){}}},
  };
  const context = vm.createContext({
    window:{GFLiveDesign:{closeMap(){}}},
    document:{
      querySelectorAll: selector => selector === '.tab' ? Object.values(tabs) : [],
      getElementById: id => tabs[id] || null,
      body:{classList:{toggle(){}}},
    },
    blockCompanyNavigationForUnsavedChanges: () => { blockedCalls += 1; return true; },
    blockOperationalTabV49: () => false,
    agentsFeatureEnabled: () => true,
    showLockedOrProceed: () => false,
    syncWorkspaceTopbar: () => {},
    setTimeout: () => {},
  });
  vm.runInContext(navigation.slice(start,end), context);
  vm.runInContext("showTab('dashboard')", context);
  assert.equal(blockedCalls, 1);
});


test('opening account profile cannot replace the company label in the topbar', () => {
  const start = core.indexOf('function loadProfilePanel()');
  const end = core.indexOf('async function loadPlanInfo()', start);
  const values = new Map([
    ['girofacile_account_name','PICCOLO'],
    ['girofacile_company_name','ALIMENTARI IORIO'],
    ['girofacile_profile_email','account@example.com'],
    ['girofacile_profile_role','Amministratore'],
  ]);
  const nodes = {
    topProfileName:{textContent:''},
    topProfileRole:{textContent:''},
    topProfileAvatar:{innerHTML:''},
    profilePreview:{innerHTML:''},
    profileName:{value:''},
    profileEmail:{value:''},
    profileRole:{value:''},
  };
  const context = vm.createContext({
    localStorage:{getItem:key=>values.get(key) || null},
    currentSessionUser:null,
    document:{getElementById:id=>nodes[id] || null},
    set:(id,value)=>{ if(nodes[id]) nodes[id].value=value; },
  });
  vm.runInContext(core.slice(start,end), context);
  vm.runInContext('loadProfilePanel()', context);
  assert.equal(nodes.topProfileName.textContent, 'ALIMENTARI IORIO');
  assert.equal(nodes.profileName.value, 'PICCOLO');
});
