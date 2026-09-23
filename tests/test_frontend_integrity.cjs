const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

test('dashboard modules parse and have no duplicate top-level function declarations', () => {
  const names = new Set();
  for(const path of ['static/dashboard/js/reports.js','static/dashboard/js/core.js']){
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
  for(const id of ['featurePhotoProofV89','featureRefrigeratedV89']){
    assert.match(html,new RegExp(`<input[^>]*id="${id}"[^>]*disabled`));
  }
});
