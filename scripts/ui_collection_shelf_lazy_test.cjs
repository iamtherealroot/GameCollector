const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app/static/collection-shelf.js','utf8');
function scene(fetch){
  let click;const timers=[],classes=new Set(),set={dataset:{helperKey:'games'},innerHTML:''},insertions=[];
  const knob={disabled:false,addEventListener(_,fn){click=fn;}};
  const cabinet={dataset:{helpersUrl:'/dashboard/easter-helpers?v=test'},parentElement:{insertAdjacentHTML(_,html){insertions.push(html);}},setAttribute(){},querySelector(){return null;},querySelectorAll(selector){return selector==='[data-helper-key]'?[set]:[];},classList:{add(...names){names.forEach(n=>classes.add(n));},remove(...names){names.forEach(n=>classes.delete(n));}}};
  vm.runInNewContext(source,{fetch,document:{hidden:false,querySelector(selector){return selector==='.regal-shake-trigger'?knob:selector==='.collection-regal'?cabinet:null;},querySelectorAll(){return [];},createElement(){return {innerHTML:'',content:{querySelector(){return {innerHTML:'supplied sprite markup'};}}};}},window:{matchMedia(){return {matches:false};},setInterval(){},setTimeout(fn){timers.push(fn);}}});
  return {click:()=>click(),knob,classes,set,timers,insertions};
}
(async()=>{
  let calls=0,resolve;const pending=new Promise(r=>resolve=r);
  const one=scene(async(url,options)=>{calls++;assert.equal(url,'/dashboard/easter-helpers?v=test');assert.equal(options.credentials,'same-origin');await pending;return {ok:true,json:async()=>({helpers:{games:'markup'},guard:'supplied security sheet'})};});
  const first=one.click();await one.click();assert.equal(calls,1);assert.equal(one.knob.disabled,true);resolve();await first;
  assert.equal(one.set.innerHTML,'supplied sprite markup');assert.deepEqual(one.insertions,['supplied security sheet']);assert(one.classes.has('is-shaking'));assert.equal(one.timers.length,9);
  one.timers.at(-1)();await one.click();assert.equal(calls,1);assert.equal(one.insertions.length,1);one.timers.at(-1)();
  let attempt=0;const retry=scene(async()=>({ok:++attempt>1,json:async()=>({helpers:{games:'markup'},guard:'security'})}));await retry.click();assert.equal(retry.knob.disabled,false);assert.equal(retry.classes.size,0);await retry.click();assert.equal(attempt,2);assert(retry.classes.has('is-shaking'));
  console.log('OK: sprites deferred until trigger, one fetch/scene on double-click, reuse, silent failure and retry');
})().catch(error=>{console.error(error);process.exit(1)});
