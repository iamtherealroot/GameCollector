(() => {
  const quickbar=document.querySelector('.bibo-quickbar');
  const measure=()=>{if(quickbar && quickbar.getBoundingClientRect().height)document.documentElement.style.setProperty('--bibo-quickbar-height',quickbar.getBoundingClientRect().height+'px');};
  if(quickbar && typeof ResizeObserver!=='undefined')new ResizeObserver(measure).observe(quickbar);
  measure();window.addEventListener('resize',measure);
  document.querySelectorAll('[data-copy-parts]').forEach(parts=>{
    const form=parts.closest('form');
    const sync=()=>{
      const physical=['movies','tv','music'].includes(form.elements.category.value) && form.elements.ownership_format.value!=='digital';
      parts.hidden=!physical;
      parts.querySelectorAll('input').forEach(input=>{input.disabled=!physical;});
    };
    form.addEventListener('change',sync);sync();
  });
  const key='bibo-scroll:'+location.pathname+location.search;
  const save=()=>{try{sessionStorage.setItem(key,String(window.scrollY));}catch(_){}};
  const restore=()=>{try{const y=Number(sessionStorage.getItem(key));if(y>0)requestAnimationFrame(()=>window.scrollTo(0,y));}catch(_){}};
  const makeFeedback=(className,label)=>{const shell=document.createElement('div');shell.className=className;shell.setAttribute('role','status');shell.setAttribute('aria-live','polite');const runner=document.createElement('span');runner.className='bibo-loading-runner';runner.setAttribute('aria-hidden','true');const text=document.createElement('span');text.textContent=label;shell.append(runner,text);document.body.appendChild(shell);return {shell,text,runner};};
  const dockMetadataFeedback=shell=>{const slot=document.querySelector('[data-metadata-feedback-slot]');if(slot){shell.classList.add('is-inline','flash');slot.appendChild(shell);}};
  const {shell:loader,runner:pageRunner,text:loaderText}=makeFeedback('page-loading','Seite wird geladen …');loader.hidden=true;
  const finishRunner=(runner,done=()=>{},duration=4070)=>{
    if(!runner || window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches){if(runner)runner.hidden=true;done();return;}
    clearTimeout(runner._biboFinishTimer);runner.hidden=false;runner.classList.add('is-finishing');
    runner._biboFinishTimer=setTimeout(()=>{runner.hidden=true;done();},duration);
  };
  const navigationReceipt='bibo-navigation-loading';
  let timer;
  const loading=()=>{save();clearTimeout(timer);clearTimeout(pageRunner._biboFinishTimer);loader.hidden=true;pageRunner.hidden=false;pageRunner.classList.remove('is-finishing');timer=setTimeout(()=>{loaderText.textContent='Seite wird geladen …';loader.hidden=false;try{sessionStorage.setItem(navigationReceipt,'1');}catch(_){}},800);};
  document.addEventListener('click',event=>{
    if(event.defaultPrevented || event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)return;
    const link=event.target.closest('a[href]');if(!link || link.target || link.hasAttribute('download'))return;
    const destination=new URL(link.href,location.href);
    if(destination.origin!==location.origin || (destination.pathname===location.pathname && destination.search===location.search))return;
    loading();
  });
  document.addEventListener('submit',event=>{if(!event.defaultPrevented && event.target.target!=='_blank')loading();});
  window.addEventListener('pagehide',save);
  window.addEventListener('pageshow',event=>{
    clearTimeout(timer);loader.hidden=true;if(!event.persisted)restore();
    try{if(sessionStorage.getItem(navigationReceipt)){
      sessionStorage.removeItem(navigationReceipt);
      loaderText.textContent='Fertig.';loader.hidden=false;
      finishRunner(pageRunner,()=>{loader.hidden=true;pageRunner.hidden=false;pageRunner.classList.remove('is-finishing');},650);
    }}catch(_){}
  });
  // Expand a category form hidden behind the simplified dashboard's options.
  const showCategory=()=>{if(location.hash==='#custom-category-create'){const panel=document.getElementById('custom-category-create');const options=panel?.closest('details');if(options)options.open=true;panel?.scrollIntoView();}};
  showCategory();window.addEventListener('hashchange',showCategory);
  document.querySelectorAll('[data-catalog-url]').forEach(shell=>{
    const url=new URL(shell.dataset.catalogUrl,location.href);url.searchParams.set('fragment','1');
    const feedback=shell.querySelector('[data-catalog-feedback]');const results=shell.querySelector('[data-catalog-results]');
    (async()=>{try{const response=await fetch(url,{credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});if(!response.ok)throw new Error(String(response.status));results.innerHTML=await response.text();const runner=feedback.querySelector?.('.bibo-loading-runner');if(runner?.nextElementSibling)runner.nextElementSibling.textContent='Treffer geladen.';finishRunner(runner,()=>{feedback.hidden=true;});}catch(_){feedback.textContent=shell.dataset.catalogError || 'Katalogsuche derzeit nicht erreichbar. Bitte „Weitere Katalogtreffer suchen“ erneut öffnen.';}})();
  });
  const jobsNode=document.querySelector('[data-auto-metadata-jobs]');
  const receiptKey='bibo-metadata-result:'+location.pathname;
  const messages={enriched:'Zusatzinfos ergänzt.',not_found:'Keine weiteren Infos gefunden.',unavailable:'Zusatzinfos derzeit nicht erreichbar. Später erneut versuchen.'};
  let edited=false;document.addEventListener('input',()=>{edited=true;});document.addEventListener('change',()=>{edited=true;});
  if(jobsNode){
    const jobs=JSON.parse(jobsNode.dataset.autoMetadataJobs);
    const feedback=makeFeedback('metadata-loading','Zusatzinfos werden gesucht …');
    feedback.shell.hidden=true;
    const feedbackTimer=setTimeout(()=>{feedback.shell.hidden=false;},800);
    (async()=>{let changed=false;let status='not_found';
      for(const url of jobs){try{const response=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});if(!response.ok)throw new Error(String(response.status));const result=await response.json();changed=changed||result.changed;if(result.status==='unavailable')status='unavailable';}catch(_){status='unavailable';}}
      clearTimeout(feedbackTimer);feedback.shell.hidden=false;
      if(changed)status='enriched';feedback.text.textContent=messages[status];feedback.shell.classList.add('is-complete');dockMetadataFeedback(feedback.shell);
      if(status!=='unavailable' && !(changed&&!edited))finishRunner(feedback.runner);
      if(!changed)setTimeout(()=>feedback.shell.remove(),8000);
      if(changed&&!edited){try{sessionStorage.setItem(receiptKey,messages[status]);location.reload();}catch(_){finishRunner(feedback.runner); /* Keep the saved page usable without storage. */}}
      else if(changed){const link=document.createElement('a');link.href=location.href;link.textContent='Aktualisierte Ansicht öffnen';feedback.shell.append(link);}
    })();
  }else{try{const receipt=sessionStorage.getItem(receiptKey);if(receipt){sessionStorage.removeItem(receiptKey);const feedback=makeFeedback('metadata-loading is-complete',receipt);dockMetadataFeedback(feedback.shell);finishRunner(feedback.runner);setTimeout(()=>feedback.shell.remove(),6000);}}catch(_){}}
})();
