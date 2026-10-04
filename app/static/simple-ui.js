(() => {
  const quickbar=document.querySelector('.bibo-quickbar');
  const measure=()=>{if(quickbar && quickbar.getBoundingClientRect().height)document.documentElement.style.setProperty('--bibo-quickbar-height',quickbar.getBoundingClientRect().height+'px');};
  if(quickbar && typeof ResizeObserver!=='undefined')new ResizeObserver(measure).observe(quickbar);
  measure();window.addEventListener('resize',measure);
  const key='bibo-scroll:'+location.pathname+location.search;
  const save=()=>{try{sessionStorage.setItem(key,String(window.scrollY));}catch(_){}};
  const restore=()=>{try{const y=Number(sessionStorage.getItem(key));if(y>0)requestAnimationFrame(()=>window.scrollTo(0,y));}catch(_){}};
  const makeFeedback=(className,label)=>{const shell=document.createElement('div');shell.className=className;shell.setAttribute('role','status');shell.setAttribute('aria-live','polite');const runner=document.createElement('span');runner.className='bibo-loading-runner';runner.setAttribute('aria-hidden','true');const text=document.createElement('span');text.textContent=label;shell.append(runner,text);document.body.appendChild(shell);return {shell,text,runner};};
  const {shell:loader}=makeFeedback('page-loading','Seite wird geladen …');loader.hidden=true;
  let timer;
  const loading=()=>{save();clearTimeout(timer);timer=setTimeout(()=>{loader.hidden=false;},180);};
  document.addEventListener('click',event=>{
    if(event.defaultPrevented || event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)return;
    const link=event.target.closest('a[href]');if(!link || link.target || link.hasAttribute('download'))return;
    const destination=new URL(link.href,location.href);
    if(destination.origin!==location.origin || (destination.pathname===location.pathname && destination.search===location.search))return;
    loading();
  });
  document.addEventListener('submit',event=>{if(!event.defaultPrevented && event.target.target!=='_blank')loading();});
  window.addEventListener('pagehide',save);
  window.addEventListener('pageshow',event=>{clearTimeout(timer);loader.hidden=true;if(!event.persisted)restore();});
  // Expand a category form hidden behind the simplified dashboard's options.
  const showCategory=()=>{if(location.hash==='#custom-category-create'){const panel=document.getElementById('custom-category-create');const options=panel?.closest('details');if(options)options.open=true;panel?.scrollIntoView();}};
  showCategory();window.addEventListener('hashchange',showCategory);
  document.querySelectorAll('[data-catalog-url]').forEach(shell=>{
    const url=new URL(shell.dataset.catalogUrl,location.href);url.searchParams.set('fragment','1');
    const feedback=shell.querySelector('[data-catalog-feedback]');const results=shell.querySelector('[data-catalog-results]');
    (async()=>{try{const response=await fetch(url,{credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});if(!response.ok)throw new Error(String(response.status));results.innerHTML=await response.text();feedback.hidden=true;}catch(_){feedback.textContent='Katalogsuche derzeit nicht erreichbar. Bitte „Weitere Katalogtreffer suchen“ erneut öffnen.';}})();
  });
  const jobsNode=document.querySelector('[data-auto-metadata-jobs]');
  const receiptKey='bibo-metadata-result:'+location.pathname;
  const messages={enriched:'Zusatzinfos ergänzt.',not_found:'Keine weiteren Infos gefunden.',unavailable:'Zusatzinfos derzeit nicht erreichbar. Später erneut versuchen.'};
  let edited=false;document.addEventListener('input',()=>{edited=true;});document.addEventListener('change',()=>{edited=true;});
  if(jobsNode){
    const jobs=JSON.parse(jobsNode.dataset.autoMetadataJobs);
    const feedback=makeFeedback('metadata-loading','Zusatzinfos werden gesucht …');
    (async()=>{let changed=false;let status='not_found';
      for(const url of jobs){try{const response=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});if(!response.ok)throw new Error(String(response.status));const result=await response.json();changed=changed||result.changed;if(result.status==='unavailable')status='unavailable';}catch(_){status='unavailable';}}
      if(changed)status='enriched';feedback.text.textContent=messages[status];feedback.shell.classList.add('is-complete');
      if(!changed)setTimeout(()=>feedback.shell.remove(),8000);
      if(changed&&!edited){try{sessionStorage.setItem(receiptKey,messages[status]);location.reload();}catch(_){/* Keep the saved page usable without storage. */}}
      else if(changed){const link=document.createElement('a');link.href=location.href;link.textContent='Aktualisierte Ansicht öffnen';feedback.shell.append(link);}
    })();
  }else{try{const receipt=sessionStorage.getItem(receiptKey);if(receipt){sessionStorage.removeItem(receiptKey);const feedback=makeFeedback('metadata-loading is-complete',receipt);setTimeout(()=>feedback.shell.remove(),6000);}}catch(_){}}
})();
