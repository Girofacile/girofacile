const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
const customers=fs.readFileSync('static/dashboard/js/customers.js','utf8');
const orders=fs.readFileSync('static/dashboard/js/orders.js','utf8');
const html=fs.readFileSync('static/dashboard/index.html','utf8');

test('verified customer surfaces both geographic notice badges',()=>{
 assert.match(customers,/function cxAccessBadges\(x\)/);
 assert.match(customers,/if\(x\.ztl\).*ZTL/);
 assert.match(customers,/if\(x\.pedestrian_area\).*Area pedonale/);
 assert.match(customers,/cxAccessBadges\(c\)/);
});

test('both notices pass unchanged into stop payload and route preview',()=>{
 assert.match(core,/pedestrian_area:!!c\.pedestrian_area/);
 assert.match(core,/pedestrian_area: !!d\.pedestrian_area/);
 assert.match(core,/if\(d\.pedestrian_area\) badges\.push/);
 assert.match(core,/counts\.pedonale/);
 assert.match(core,/Consegne in area pedonale/);
 assert.match(core,/d\.pedestrian_area\?\x27 <span class="gf-badge"/);
});

test('orders list and order details display separately detected access notices',()=>{
 assert.match(orders,/function accessBadges\(o\)/);
 assert.match(orders,/o\.ztl_notice/);
 assert.match(orders,/o\.pedestrian_area/);
 assert.match(orders,/accessBadges\(o\)/);
});

test('dashboard loads cache-busted scripts and describes both GeoJSON sources',()=>{
 assert.match(html,/customers\.js\?v=gf_access_notices_20261020/);
 assert.match(html,/core\.js\?v=gf_access_notices_20261020/);
 assert.match(html,/Avvisi ZTL \/ area pedonale indicativi/);
});
