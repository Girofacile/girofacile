const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

const source = readFileSync('static/dashboard/js/reports.js', 'utf8') + readFileSync('static/dashboard/js/core.js', 'utf8');
function extract(name) {
  const start = source.search(new RegExp(`^(?:async )?function ${name}\\(`, 'm'));
  assert.ok(start >= 0, name);
  return source.slice(start, source.indexOf('\n}', start) + 2);
}

test('settings save applies agent visibility and clears stale filters only when disabled', async () => {
  const elements = new Map();
  for (const id of ['settingAgentsEnabled','settingDeliverySignature','cAgent','customerFilterAgent',
    'reportAgent','settingsSaveBtnV893','settingsSaveState','featureTimeWindowsV89']) {
    elements.set(id, {value: '', checked: false, disabled: false, dataset: {}, textContent: ''});
  }
  const root = {dataset: {}};
  const calls = [];
  const context = vm.createContext({
    document: {documentElement: root, getElementById: id => elements.get(id)},
    URLSearchParams,
    featureLockedForTab: () => null,
    set: (id, value) => { if(elements.has(id)) elements.get(id).value = value; },
    val: id => elements.get(id)?.value || '',
    updateReportFilterSummary: () => {},
    loadAgents: async () => {}, loadCustomers: async () => {}, loadCustomerPicker: async () => {},
    loadNotificationsV30: async () => {}, applyUniversalFeaturesV891: () => {},
    markSettingsCleanV893: () => {}, toast: () => {}, alert: message => {throw Error(message);},
    api: async (url, options) => {const payload = JSON.parse(options.body); calls.push({url, payload}); return payload;},
  });
  vm.runInContext(`let settingsV41={agents_enabled:false}; let agentsCache=[];
    let gfSettingsDirtyV893=true; let gfUniversalFeaturesV891={};
    ${['agentsFeatureEnabled','applyAgentsFeature','refreshAgentsFeature','reportParams','saveAllSettingsV893'].map(extract).join('\n')}`, context);
  elements.get('settingAgentsEnabled').checked = true;
  elements.get('settingDeliverySignature').checked = true;
  await vm.runInContext('saveAllSettingsV893()', context);
  assert.equal(root.dataset.gfAgents, 'on');
  assert.equal(elements.get('cAgent').disabled, false);
  assert.equal(calls[1].payload.agents_enabled, true);
  assert.equal(calls[1].payload.delivery_signature_enabled, true);
  elements.get('reportAgent').value = '42';
  assert.equal(vm.runInContext('reportParams().get("agent_id")', context), '42');

  elements.get('settingAgentsEnabled').checked = false;
  elements.get('cAgent').value = '42';
  elements.get('customerFilterAgent').value = '42';
  await vm.runInContext('saveAllSettingsV893()', context);
  assert.equal(root.dataset.gfAgents, 'off');
  for(const id of ['cAgent','customerFilterAgent','reportAgent']) {
    assert.equal(elements.get(id).value, '');
    assert.equal(elements.get(id).disabled, true);
  }
  assert.equal(vm.runInContext('reportParams().get("agent_id")', context), '');
  assert.equal(elements.get('settingDeliverySignature').checked, true);
});
