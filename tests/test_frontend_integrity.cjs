const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

test('dashboard modules parse and have no duplicate top-level function declarations', () => {
  const names = new Set();
  for(const path of ['static/dashboard/js/navigation.js','static/dashboard/js/reports.js','static/dashboard/js/customers.js','static/dashboard/js/core.js','static/dashboard/js/vehicles.js','static/dashboard/js/drivers.js']){
    const source=readFileSync(path,'utf8');
    new vm.Script(source,{filename:path});
    for(const [,name] of source.matchAll(/^(?:async )?function (\w+)\(/gm)){
      assert.ok(!names.has(name),`Duplicate function: ${name}`);
      names.add(name);
    }
  }
});

test('operator scripts parse and signature controls are wired', () => {
  const html=readFileSync('static/operator/index.html','utf8');
  for(const [,source] of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(source);
  new vm.Script(readFileSync('static/operator/signature.js','utf8'));
  assert.match(html,/operatorSignaturePayload\(\)/);
  assert.match(html,/id="operatorSignatureCanvas"/);
});

test('report export is implemented and unfinished features cannot be enabled in the UI', () => {
  const html=readFileSync('static/dashboard/index.html','utf8');
  assert.ok(html.indexOf('js/reports.js') < html.indexOf('js/core.js'));
  assert.match(html,/onclick="printReport\(\)"/);
  for(const id of ['featureRefrigeratedV89']){
    assert.match(html,new RegExp(`<input[^>]*id="${id}"[^>]*disabled`));
  }
});


test('account password change stays inline and separate from profile save', () => {
  const html=readFileSync('static/dashboard/index.html','utf8');
  const core=readFileSync('static/dashboard/js/core.js','utf8');
  assert.match(html,/id="profilePasswordChangePanel"[^>]*hidden/);
  assert.match(html,/id="profileCurrentPassword"/);
  assert.match(html,/id="profileNewPassword"/);
  assert.match(html,/id="profileConfirmPassword"/);
  assert.match(html,/onclick="changeProfilePassword\(\)"/);
  assert.match(html,/requestProfilePasswordReset\(\)/);
  assert.doesNotMatch(html,/id="profilePassword"/);
  assert.match(core,/\/api\/account-password\/change/);
  const saveBlock=core.match(/async function saveProfilePanel\(\)[\s\S]*?\n}\n/);
  assert.ok(saveBlock);
  assert.doesNotMatch(saveBlock[0],/new_password|profileCurrentPassword|profileNewPassword/);
});
