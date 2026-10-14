const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');

const html=fs.readFileSync('static/admin/index.html','utf8');
const js=fs.readFileSync('static/admin/api-costs.js','utf8');

test('Super Admin exposes a dedicated API costs section on desktop and mobile',()=>{
  assert.match(html,/navigate\('api-costs'\)/);
  // Su smartphone la voce resta nella sidebar, aperta dal pulsante "Altro" della barra in basso.
  assert.match(html,/data-admin-nav="api-costs"[^>]*onclick="navigate\('api-costs'\)/);
  assert.match(html,/class="gf-bottom-nav"[\s\S]*onclick="GFShell\.open\(true\)"/);
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
  // Le schede su smartphone vengono dalla regola comune delle tabelle data-gf-responsive.
  assert.match(html,/<table class="gf-table" id="api-cost-table" data-gf-responsive="cards">/);
  assert.match(js,/data-label="Avanzamento"/);
});
