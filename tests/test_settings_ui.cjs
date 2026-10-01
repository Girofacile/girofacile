const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const core=fs.readFileSync('static/dashboard/js/core.js','utf8');
function fixture(){
 const fields=new Map(),calls=[];
 const node=id=>{if(!fields.has(id)){const classes=new Set(['hidden']);fields.set(id,{textContent:'',checked:false,disabled:false,dataset:{},classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c),toggle(c,force){if(force)classes.add(c);else classes.delete(c)}}})}return fields.get(id)};
 const ctx=vm.createContext({document:{getElementById:node},api:async(url,opts)=>{calls.push({url,payload:JSON.parse(opts.body)});return JSON.parse(opts.body)},applyUniversalFeaturesV891(){},refreshAgentsFeature:async()=>{},toast(){},alert(){}});
 vm.runInContext('let settingsV41={},gfUniversalFeaturesV891={};'+core.slice(core.indexOf('let gfSettingsDirtyV893='),core.indexOf('window.markSettingsDirtyV893')),ctx);
 return {node,ctx,calls,run:s=>vm.runInContext(s,ctx)};
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
test('detail chevrons expose their content and synchronize accessible state',()=>{
 const f=fixture(),attrs={'aria-expanded':'false','aria-controls':'detail'};f.ctx.button={getAttribute:k=>attrs[k],setAttribute:(k,v)=>attrs[k]=v};
 f.run('toggleSettingsDetail(button)');assert.equal(attrs['aria-expanded'],'true');assert.equal(f.node('detail').classList.contains('hidden'),false);
 f.run('toggleSettingsDetail(button)');assert.equal(attrs['aria-expanded'],'false');assert.equal(f.node('detail').classList.contains('hidden'),true);
});
