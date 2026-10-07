const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function policy(){
  const context=vm.createContext({window:{}});
  vm.runInContext(fs.readFileSync('static/password-strength.js','utf8'),context);
  return context.window.GiroFacilePasswordStrength;
}

test('password strength accepts compliant passwords and exposes four levels',()=>{
  const p=policy();
  assert.equal(p.assess('Zebra!Ax',[]).acceptable,true);
  assert.equal(p.assess('Rotta!Blu8',[]).acceptable,true);
  assert.equal(p.assess('Rotta!Blu8Molto',[]).level,'strong');
  assert.equal(p.assess('zebra!ax',[]).acceptable,false);
  assert.equal(p.assess('ZebraAx8',[]).acceptable,false);
});

test('password strength blocks company account data and predictable passwords',()=>{
  const p=policy();
  const context=['Rossi Trasporti S.r.l.','mrossi','m.rossi@example.test'];
  assert.equal(p.assess('Rossi!Ax9',context).acceptable,false);
  assert.equal(p.assess('Mrossi!A9',context).acceptable,false);
  assert.equal(p.assess('Password!',[]).acceptable,false);
  assert.equal(p.assess('Abcdef!Q9',[]).acceptable,false);
});

test('all password creation surfaces load the shared meter',()=>{
  const dashboard=fs.readFileSync('static/dashboard/index.html','utf8');
  const driver=fs.readFileSync('static/driver/setup.html','utf8');
  const agent=fs.readFileSync('static/agent/setup.html','utf8');
  for(const source of [dashboard,driver,agent]){
    assert.match(source,/password-strength\.js/);
    assert.match(source,/password-strength\.css/);
  }
  for(const id of ['signupPasswordMeter','resetPasswordMeter','profilePasswordMeter']) assert.match(dashboard,new RegExp('id="'+id+'"'));
  assert.match(driver,/id="passwordMeter"/);
  assert.match(agent,/id="passwordMeter"/);
  assert.doesNotMatch(driver,/Minimo 6|Almeno 6/);
  assert.doesNotMatch(agent,/minlength="6"|Minimo 6|Almeno 6/);
});
