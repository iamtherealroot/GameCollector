const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(require('node:path').join(__dirname,'../app/static/dashboard-tour.js'),'utf8');
async function fixture({show=true,fail=false,search=''}={}){
  let document;
  class Element{
    constructor(){this.hidden=true;this.style={};this.disabled=false;this.inert=false;this.open=false;this.listeners={};this.offsetWidth=310;this.offsetHeight=160;}
    getBoundingClientRect(){return {left:30,top:60,right:180,bottom:110,width:150,height:50};}
    addEventListener(name,fn){this.listeners[name]=fn;}
    scrollIntoView(){}
    focus(){document.activeElement=this;}
    closest(){return menu;}
    replaceChildren(){}
    append(){}
    async click(){if(!this.disabled && this.onclick)await this.onclick();}
  }
  const ids=['dashboard-tour','tour-panel','tour-spotlight','tour-back','tour-next','tour-skip','tour-title','tour-description','tour-progress','tour-items','tour-error'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element()])),header=new Element(),target=new Element(),menu=new Element();
  let saved=0;
  document={activeElement:target,body:{children:[header,elements['dashboard-tour']]},
    getElementById:id=>elements[id],createElement:()=>new Element(),
    querySelector:selector=>selector==='[data-dashboard-tour-home]'?target:null,
    querySelectorAll:selector=>selector==='missing'?[]:selector==='home'||selector==='menu'?[target]:[menu]};
  const window={innerWidth:1200,innerHeight:900,scrollY:0,addEventListener(){},scrollTo(){}};
  vm.runInNewContext(code,{document,window,location:{search},URLSearchParams,requestAnimationFrame:fn=>fn(),
    fetch:async url=>url==='/api/tutorial'?{ok:true,json:async()=>({show,token:'signed',steps:[{title:'Home',description:'Start',selector:'home'},{title:'Missing',selector:'missing'},{title:'Menu',selector:'menu',menu:true,items:[]}]})}:{ok:!fail,json:async()=>{saved++;}}});
  return {window,elements,header,menu,get saved(){return saved;}};
}
(async()=>{
  let f=await fixture();await f.window.BiboDashboardTour.start();
  assert.equal(f.elements['dashboard-tour'].hidden,false);assert(f.header.inert);
  assert(f.elements['tour-spotlight'].style.width);
  await f.elements['tour-next'].click();assert.equal(f.elements['tour-title'].textContent,'Menu');assert(f.menu.open);
  await f.elements['tour-back'].click();assert.equal(f.elements['tour-title'].textContent,'Home');
  await f.elements['tour-skip'].click();assert(f.elements['dashboard-tour'].hidden);assert.equal(f.header.inert,false);assert.equal(f.menu.open,false);
  f=await fixture({show:false});await f.window.BiboDashboardTour.start();assert(f.elements['dashboard-tour'].hidden);
  f=await fixture({show:false,search:'?tutorial=1'});await f.window.BiboDashboardTour.start();assert.equal(f.elements['dashboard-tour'].hidden,false);
  await f.elements['tour-next'].click();await f.elements['tour-next'].click();assert(f.elements['dashboard-tour'].hidden);
  f=await fixture({fail:true});await f.window.BiboDashboardTour.start();await f.elements['tour-skip'].click();
  assert.equal(f.elements['tour-error'].hidden,false);await f.elements['tour-next'].click();assert(f.elements['dashboard-tour'].hidden);assert.equal(f.header.inert,false);
  console.log('OK: anchored tour, hidden-target skipping, back/finish/skip/replay, inert cleanup and failed-save escape');
})().catch(error=>{console.error(error);process.exitCode=1;});
