// Dependency-free DOM/fetch contract tests; not a visual browser test.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/release-news.js'),'utf8');
class Element {
  constructor(){this.hidden=true;this.disabled=false;this.listeners={};this.children=[];this.href='/whats-new';}
  addEventListener(name,fn){this.listeners[name]=fn;}
  append(...items){this.children.push(...items);}
  appendChild(item){this.children.push(item);}
  replaceChildren(){this.children=[];}
  showModal(){this.open=true;}
  close(){this.open=false;}
  querySelector(){return this.link;}
  async click(){const event={currentTarget:this,preventDefault(){}};if(this.disabled)return;if(this.onclick)await this.onclick(event);else if(this.listeners.click)await this.listeners.click(event);}
}
async function setup({news=true,fail=false,tutorial=true}={}){
  const ids=['release-news-dialog','release-news-version','release-news-highlights','release-news-close','release-news-dismiss','release-news-error','tutorial-dialog','tutorial-title','tutorial-progress','tutorial-description','tutorial-items','tutorial-next','tutorial-back','tutorial-skip','tutorial-error'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
  elements['release-news-dialog'].link=new Element();
  const calls=[],location={search:'',assign(href){this.destination=href;}};
  const state={fail,tourStarted:0};
  vm.runInNewContext(source,{
    document:{getElementById:id=>elements[id],createElement:()=>new Element(),createTextNode:text=>text},
    location,URLSearchParams,
    window:{BiboDashboardTour:{start:async()=>{state.tourStarted++;}}},
    fetch:async(url,options={})=>{
      calls.push({url,options});
      if(url==='/api/release-news')return {ok:true,json:async()=>({show:news,version:'5.0.2',token:'signed',highlights:['Test']})};
      if(url==='/api/release-news/ack')return {ok:!state.fail};
      if(url==='/api/tutorial')return {ok:true,json:async()=>({show:tutorial,token:'tutorial-signed',steps:[{title:'Sammlung',description:'Produkte',items:[{title:'Spiele',description:'Öffnen',url:'/collection'}]},{title:'Hilfe',description:'Support',items:[]}]})};
      if(url==='/api/tutorial/ack')return {ok:true};
      throw new Error(url);
    }
  });
  await new Promise(setImmediate);
  return {elements,calls,location,state};
}
(async()=>{
  let s=await setup();
  assert(s.elements['release-news-dialog'].open);
  await s.elements['release-news-close'].click();
  assert.equal(s.elements['release-news-dialog'].open,false);
  assert.equal(s.state.tourStarted,1);
  s=await setup();await s.elements['release-news-dialog'].link.click();
  assert.equal(s.location.destination,'/whats-new');
  assert(s.calls.some(c=>c.url==='/api/release-news/ack'));
  s=await setup({fail:true});await s.elements['release-news-close'].click();
  assert.equal(s.elements['release-news-error'].hidden,false);
  assert.equal(s.elements['release-news-dismiss'].hidden,false);
  s.state.fail=false;await s.elements['release-news-close'].click();
  assert.equal(s.elements['release-news-dialog'].open,false);
  assert.equal(s.calls.filter(c=>c.url==='/api/release-news').length,2);
  s=await setup({fail:true});await s.elements['release-news-dialog'].link.click();
  assert.equal(s.location.destination,undefined);
  await s.elements['release-news-dismiss'].click();
  assert.equal(s.elements['release-news-dialog'].open,false);
  s=await setup({news:false});assert.equal(s.state.tourStarted,1);
  console.log('OK: Verstanden, Alle Änderungen, Fehler/Retry/Schließen, Dashboard-Tour-Aufruf');
})().catch(error=>{console.error(error);process.exitCode=1;});
