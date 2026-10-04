const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('app/static/simple-ui.js','utf8');
async function scene({result={changed:true,status:'enriched'},edited=false,receipt=null,fail=false,catalog=false}={}){
 const nodes=[],events={},timers=[],saved=new Map(receipt?[['bibo-metadata-result:/item',receipt]]:[]),requests=[];let reloads=0;
 const make=()=>({children:[],className:'',hidden:false,classList:{add(name){this.added=name;}},setAttribute(){},append(...children){this.children.push(...children);},remove(){this.removed=true;}});
 const feedback={hidden:false,textContent:''},results={innerHTML:''};const catalogShell={dataset:{catalogUrl:'/collector/media/search?section=movies&ean=4010324037190'},querySelector(s){return s==='[data-catalog-feedback]'?feedback:results;}};
 const jobNode=receipt||catalog?null:{dataset:{autoMetadataJobs:JSON.stringify(['/metadata/auto/media/1','/metadata/auto/media/2'])}};
 const document={documentElement:{style:{setProperty(){}}},body:{appendChild(node){nodes.push(node);}},createElement:make,querySelectorAll(){return catalog?[catalogShell]:[];},querySelector(selector){return selector==='[data-auto-metadata-jobs]'?jobNode:null;},addEventListener(name,fn){events[name]=fn;}};
 const location={pathname:'/item',search:'',hash:'',origin:'https://bibo.test',href:'https://bibo.test/item',reload(){reloads++;}};
 let active=0;
 const fetch=async(url,options)=>{active++;assert.equal(active,1,'Jobs must be sequential to preserve queued cookies');requests.push({url,options});if(edited)events.input();await Promise.resolve();active--;if(fail)throw Error('offline');return {ok:true,json:async()=>result,text:async()=>'<article>Iron Man</article>'};};
 vm.runInNewContext(source,{document,location,fetch,sessionStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)},window:{scrollY:0,addEventListener(){}},setTimeout(fn,ms){timers.push({fn,ms});return timers.length;},clearTimeout(){},URL,requestAnimationFrame(fn){fn();}});
 for(let i=0;i<15;i++)await Promise.resolve();
 return {nodes,events,timers,saved,requests,feedback,results,get reloads(){return reloads;}};
}
(async()=>{
 const catalogue=await scene({catalog:true});assert.equal(catalogue.requests.length,1);assert.equal(catalogue.requests[0].url.searchParams.get('ean'),'4010324037190');assert.equal(catalogue.requests[0].url.searchParams.get('fragment'),'1');assert.equal(catalogue.results.innerHTML,'<article>Iron Man</article>');assert(catalogue.feedback.hidden);
 const failedCatalogue=await scene({catalog:true,fail:true});assert(failedCatalogue.feedback.textContent.includes('nicht erreichbar'));assert(!failedCatalogue.feedback.hidden);
 const normal=await scene();assert.equal(normal.requests.length,2);assert.equal(normal.reloads,1);assert(normal.saved.get('bibo-metadata-result:/item').includes('ergänzt'));assert.equal(normal.requests[0].options.method,'POST');assert.equal(normal.requests[0].options.credentials,'same-origin');
 const edited=await scene({edited:true});assert.equal(edited.reloads,0);assert(edited.nodes.at(-1).children.some(n=>n.textContent==='Aktualisierte Ansicht öffnen'));
 const noHit=await scene({result:{changed:false,status:'not_found'}});assert.equal(noHit.reloads,0);assert(noHit.nodes.at(-1).children.some(n=>n.textContent==='Keine weiteren Infos gefunden.'));
 const offline=await scene({fail:true});assert.equal(offline.reloads,0);assert(offline.nodes.at(-1).children.some(n=>String(n.textContent).includes('nicht erreichbar')));
 const receipt=await scene({receipt:'Zusatzinfos ergänzt.'});assert.equal(receipt.requests.length,0);assert.equal(receipt.saved.size,0);
 const css=fs.readFileSync('app/static/simple-ui.css','utf8');assert(css.includes('.page-loading,.metadata-loading{top:50%;transform:translate(-50%,-50%)}'));assert(css.includes('top:50%;left:50%;transform:translate(-50%,-50%)'));assert(css.includes('steps(4)'));assert(css.includes('@media(prefers-reduced-motion:reduce){.bibo-loading-runner{animation:none}}'));assert(css.includes('.page-loading[hidden]{display:none}'));
 const svg=fs.readFileSync('app/static/loading-runner.svg','utf8');assert.equal((svg.match(/<use /g)||[]).length,4);assert.equal((svg.match(/<image /g)||[]).length,1);
 console.log('OK: sequential enrichment, runner/status, reload receipt, edited forms preserved, no hits/offline and reduced motion');
})();
