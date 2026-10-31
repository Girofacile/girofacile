const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
function fixture(){
 const fields=new Map(),calls=[];
 const node=id=>{if(!fields.has(id)){const classes=new Set(['hidden']);fields.set(id,{textContent:'',checked:false,disabled:false,dataset:{},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c,force){if(force)classes.add(c);else classes.delete(c)}}})}return fields.get(id)};
 const counts=[];
 const ctx=vm.createContext({document:{getElementById:node,querySelectorAll:()=>counts},api:async(url,opts)=>{calls.push({url,payload:JSON.parse(opts.body)});return JSON.parse(opts.body)},planFeatureEnabled:()=>true,applyUniversalFeaturesV891(){},refreshAgentsFeature:async()=>{},toast(){},alert(){}});
 vm.runInContext('let settingsV41={},gfUniversalFeaturesV891={};'+core.slice(core.indexOf('let gfSettingsDirtyV893='),core.indexOf('window.markSettingsDirtyV893')),ctx);
 return {node,ctx,calls,counts,run:s=>vm.runInContext(s,ctx)};
}
test('save bar appears for edits and hides only after both settings writes succeed',async()=>{
 const f=fixture();f.node('settingDeliverySignature').checked=true;f.node('featureTailLiftV89').checked=true;
 f.run('markSettingsDirtyV893()');assert.equal(f.node('settingsSaveBar').classList.contains('hidden'),false);
 await f.run('saveAllSettingsV893()');assert.equal(f.calls.length,2);assert.equal(f.calls[0].payload.needs_tail_lift,true);assert.equal(f.calls[1].payload.delivery_signature_enabled,true);assert.equal(f.node('settingsSaveBar').classList.contains('hidden'),true);
});
test('failed persistence keeps edits and exposes an enabled retry action',async()=>{
 const f=fixture();f.ctx.api=async()=>{throw Error('Connessione interrotta')};f.node('featureZtlV89').checked=true;f.run('markSettingsDirtyV893()');await f.run('saveAllSettingsV893()');
 assert.equal(f.node('featureZtlV89').checked,true);assert.equal(f.node('settingsSaveBar').classList.contains('hidden'),false);assert.equal(f.node('settingsSaveBtnV893').disabled,false);assert.match(f.node('settingsSaveState').textContent,/Connessione interrotta/);
});
test('group counters show active usable switches and refresh on every edit',()=>{
 const f=fixture(),meta={dataset:{settingsCount:'featureTimeWindowsV89 featureZtlV89 featureRefrigeratedV89'},textContent:''};f.counts.push(meta);
 f.node('featureTimeWindowsV89').checked=true;f.node('featureRefrigeratedV89').disabled=true;
 f.run('markSettingsDirtyV893()');assert.equal(meta.textContent,'1 di 2 attive');
 f.node('featureZtlV89').checked=true;f.run('markSettingsDirtyV893()');assert.equal(meta.textContent,'2 di 2 attive');
 f.node('featureTimeWindowsV89').disabled=true;f.node('featureZtlV89').disabled=true;f.run('updateSettingsCountsV893()');assert.equal(meta.textContent,'');
});

test('Starter cannot persist premium preferences even when stale inputs remain checked',async()=>{
 const f=fixture();f.ctx.planFeatureEnabled=()=>false;
 f.node('settingDeliverySignature').checked=true;f.node('featurePhotoProofV89').checked=true;
 f.run('markSettingsDirtyV893()');await f.run('saveAllSettingsV893()');
 assert.equal(f.calls[0].payload.needs_photo_proof,false);
 assert.equal(f.calls[1].payload.delivery_signature_enabled,false);
});
