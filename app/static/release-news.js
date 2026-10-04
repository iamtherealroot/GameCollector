(async () => {
  const dialog=document.getElementById('release-news-dialog');
  if(!dialog || !dialog.showModal)return;
  try {
    const response=await fetch('/api/release-news',{cache:'no-store'});
    if(!response.ok)return;
    const data=await response.json();if(!data.show){await startTutorial();return;}
    document.getElementById('release-news-version').textContent=data.since_login
      ? `Seit deinem vorherigen Login: ${data.updates?.length || 1} Update(s) bis Bibo ${data.version}`
      : data.since_version ? `Seit deinem zuletzt dokumentierten Stand ${data.since_version} bis Bibo ${data.version}` : `Bibo ${data.version}`;
    const list=document.getElementById('release-news-highlights');
    data.highlights.forEach(text=>{const li=document.createElement('li');li.textContent=text;list.append(li);});
    const button=document.getElementById('release-news-close');
    const dismiss=document.getElementById('release-news-dismiss');
    let retry=false;
    const acknowledge=async()=>{
      if(button.disabled)return;button.disabled=true;
      try {
        if(retry){
          const refreshed=await fetch('/api/release-news',{cache:'no-store'});
          if(!refreshed.ok)throw new Error('refresh failed');
          const fresh=await refreshed.json();data.token=fresh.token;
          if(!fresh.show){dialog.close();return true;}
        }
        const saved=await fetch('/api/release-news/ack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:data.version,token:data.token})});
        if(!saved.ok)throw new Error('not saved');dialog.close();return true;
      }catch(_){retry=true;document.getElementById('release-news-error').hidden=false;dismiss.hidden=false;return false;}finally{button.disabled=false;}
    };
    button.addEventListener('click',async()=>{if(await acknowledge())await startTutorial();});
    dismiss.onclick=()=>dialog.close();
    dialog.querySelector('a').addEventListener('click',async event=>{event.preventDefault();const href=event.currentTarget.href;if(await acknowledge())location.assign(href);});
    dialog.addEventListener('cancel',async event=>{event.preventDefault();if(await acknowledge())await startTutorial();});
    dialog.showModal();
  }catch(_){/* Offline: never show stale release notices. */}
})();

async function startTutorial(){
  if(window.BiboDashboardTour)await window.BiboDashboardTour.start();
}
