import {open, sleep, texts} from './lib.mjs';
export async function toPlanning(n=12, scale=1){
  const {b,p} = await open({scale});
  await sleep(1200);
  await p.evaluate(()=>{const e=[...document.querySelectorAll('button')].find(x=>x.innerText.includes('Ho capito')); e&&e.click();});
  await p.evaluate(()=>choosePlanningStart('customers'));
  await sleep(2000);
  for (let i=0;i<n;i++){ const bx=(await p.$$('tbody input[type=checkbox]'))[i]; await bx.click(); await sleep(120); }
  await sleep(500);
  await p.click('#customersGoPlanning');
  await sleep(2500);
  return {b,p};
}
export const setv = (p,id,v)=>p.evaluate((id,v)=>{const e=document.getElementById(id); e.value=v; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));},id,v);
export async function fillFleet(p){
  const s = ms=>new Promise(r=>setTimeout(r,ms));
  await p.evaluate(()=>window.scrollTo(0,0));
  await setv(p,'routeDate','2026-11-18'); await s(400);
  await setv(p,'routeStart','07:30'); await s(1000);
  await p.evaluate(()=>selectPlanningModeCard('fleet')); await s(1200);
  await p.evaluate(()=>document.getElementById('fleetAdd').click()); await s(800);
  for (const [i,v,d] of [[0,'1','1'],[1,'2','2'],[2,'3','3']]) { await setv(p,'fleetVehicle'+i,v); await s(300); await setv(p,'fleetDriver'+i,d); await s(300); }
  await setv(p,'fleetStrategy','balanced'); await s(800);
}
