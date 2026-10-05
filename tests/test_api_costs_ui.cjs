const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');

const html=fs.readFileSync('static/admin/index.html','utf8');
const js=fs.readFileSync('static/admin/api-costs.js','utf8');

test('Super Admin exposes a dedicated API costs section on desktop and mobile',()=>{
  assert.match(html,/navigate\('api-costs'\)/);
  assert.match(html,/adminMobileGoV62\('api-costs'\)/);
  assert.match(html,/id="section-api-costs"/);
  assert.match(html,/Consumo e quota gratuita per servizio/);
});

test('API costs UI shows quota, cost, projection, company and settings surfaces',()=>{
  for(const id of ['api-cost-kpis','api-cost-tbody','api-cost-companies','api-cost-history','api-cost-settings-list']){
    assert.match(html,new RegExp('id="'+id+'"'));
  }
  assert.match(html,/static\/admin\/api-costs\.js/);
  assert.match(js,/free_remaining/);
  assert.match(js,/projected_costs/);
  assert.match(js,/saveApiCostSettings/);
});

test('API costs table has mobile responsive card treatment',()=>{
  assert.match(html,/#api-cost-table thead\{display:none\}/);
  assert.match(html,/data-label="Avanzamento"/);
});
