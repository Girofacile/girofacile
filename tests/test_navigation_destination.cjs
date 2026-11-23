const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('stop navigation uses verified coordinates, otherwise the address text',()=>{
  const ctx=vm.createContext({});vm.runInContext(fs.readFileSync('static/format.js','utf8'),ctx);
  const nav=s=>vm.runInContext('gfNavDestination('+JSON.stringify(s)+')',ctx);
  assert.equal(nav({indirizzo:'Via roma 1, Italia 155',lat:40.8764449,lon:14.3410342}),'40.876445,14.341034');
  assert.equal(nav({indirizzo:'Via Roma',coord:{lat:40.1,lon:14.2}}),'40.100000,14.200000');
  assert.equal(nav({indirizzo:'Via Roma 1, Volla',lat:null,lon:null}),'Via Roma 1, Volla');
  assert.equal(nav({indirizzo:'Via Roma 1, Volla',lat:0,lon:0}),'Via Roma 1, Volla');
});
