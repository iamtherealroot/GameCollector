(() => {
  const root=document.getElementById('dashboard-tour');
  if(!root)return;
  const panel=document.getElementById('tour-panel'),spot=document.getElementById('tour-spotlight');
  const back=document.getElementById('tour-back'),next=document.getElementById('tour-next'),skip=document.getElementById('tour-skip');
  let active=false,busy=false,index=0,data=null,target=null,details=[],inert=[],previousFocus=null,previousScroll=0;
  const visible=element=>{const r=element.getBoundingClientRect();return r.width>0 && r.height>0;};
  const position=()=>{
    if(!active || !target)return;
    const rect=target.getBoundingClientRect(),vw=window.innerWidth,vh=window.innerHeight;
    const left=Math.max(8,rect.left-6),top=Math.max(8,rect.top-6);
    const right=Math.min(vw-8,rect.right+6),bottom=Math.min(vh-8,rect.bottom+6);
    Object.assign(spot.style,{left:`${left}px`,top:`${top}px`,width:`${Math.max(10,right-left)}px`,height:`${Math.max(10,bottom-top)}px`});
    const width=panel.offsetWidth,height=panel.offsetHeight;
    let x=Math.min(Math.max(12,left),vw-width-12),y=bottom+16;
    if(y+height>vh-12){
      if(top-height-16>=12)y=top-height-16;
      else if(right+width+24<vw){x=right+16;y=Math.max(12,Math.min(top,vh-height-12));}
      else if(left-width-24>0){x=left-width-16;y=Math.max(12,Math.min(top,vh-height-12));}
      else y=rect.top>vh/2?12:Math.max(12,vh-height-12);
    }
    Object.assign(panel.style,{left:`${Math.max(12,x)}px`,top:`${Math.max(12,y)}px`});
  };
  const choose=step=>{
    document.querySelectorAll('.bibo-nav details,.bibo-mobile-menu,.bibo-mobile-panel details,.account-menu').forEach(menu=>{menu.open=false;});
    let candidates=[...document.querySelectorAll(step.selector)];
    let element=candidates.find(visible);
    if(!element && step.menu){
      const mobile=document.querySelector('.bibo-mobile-menu');
      if(mobile && visible(mobile)){mobile.open=true;element=candidates.find(visible);}
    }
    if(element && step.menu){const group=element.closest('details');if(group)group.open=true;}
    return element;
  };
  const render=()=>{
    const step=data.steps[index];target=choose(step);
    if(!target){ // A hidden/removed permission-dependent target is never guessed.
      data.steps.splice(index,1);
      if(!data.steps.length){close();return;}
      index=Math.min(index,data.steps.length-1);render();return;
    }
    document.getElementById('tour-title').textContent=step.title;
    document.getElementById('tour-description').textContent=step.description;
    document.getElementById('tour-progress').textContent=`Direkt im Dashboard · ${index+1} von ${data.steps.length}`;
    const list=document.getElementById('tour-items');list.replaceChildren();
    (step.items || []).forEach(item=>{const li=document.createElement('li');li.textContent=`${item.title}: ${item.description}`;list.append(li);});
    list.hidden=!step.items?.length;
    back.disabled=index===0;next.textContent=index===data.steps.length-1?'Tutorial abschließen':'Weiter';
    target.scrollIntoView({behavior:'instant',block:'center'});
    requestAnimationFrame(position);
    panel.focus({preventScroll:true});
  };
  const close=()=>{
    active=false;root.hidden=true;
    inert.forEach(([element,value])=>{element.inert=value;});
    details.forEach(([element,value])=>{element.open=value;});
    window.scrollTo({top:previousScroll,behavior:'instant'});
    if(previousFocus && visible(previousFocus))previousFocus.focus({preventScroll:true});
    else document.querySelector('.bibo-nav-home, .brand')?.focus({preventScroll:true});
  };
  const finish=async()=>{
    if(busy)return;busy=true;next.disabled=back.disabled=skip.disabled=true;
    try{
      const response=await fetch('/api/tutorial/ack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:data.token})});
      if(!response.ok)throw new Error('not saved');close();
    }catch(_){
      document.getElementById('tour-error').hidden=false;
      next.disabled=false;next.textContent='Jetzt schließen';next.onclick=close;
      requestAnimationFrame(position);
    }
  };
  root.addEventListener('click',event=>event.stopPropagation());
  panel.addEventListener('keydown',event=>{
    event.stopPropagation();
    if(event.key==='Escape'){event.preventDefault();if(busy)close();else finish();}
    if(event.key==='Tab'){
      const buttons=[back,next,skip].filter(button=>!button.disabled);
      if(!buttons.length){event.preventDefault();return;}
      const first=buttons[0],last=buttons.at(-1);
      if(event.shiftKey && (document.activeElement===first || document.activeElement===panel)){event.preventDefault();last.focus();}
      else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
    }
  });
  window.addEventListener('resize',()=>{if(active){target=choose(data.steps[index]);requestAnimationFrame(position);}});
  window.addEventListener('scroll',()=>requestAnimationFrame(position),true);
  window.BiboDashboardTour={start:async()=>{
    if(active || !document.querySelector('[data-dashboard-tour-home]'))return;
    try{
      const response=await fetch('/api/tutorial',{cache:'no-store'});if(!response.ok)return;
      data=await response.json();
      if((!data.show && new URLSearchParams(location.search).get('tutorial')!=='1') || !data.steps.length)return;
      previousFocus=document.activeElement;previousScroll=window.scrollY;
      details=[...document.querySelectorAll('.bibo-nav details,.bibo-mobile-menu,.bibo-mobile-panel details,.account-menu')].map(element=>[element,element.open]);
      inert=[...document.body.children].filter(element=>element!==root).map(element=>[element,element.inert]);
      inert.forEach(([element])=>{element.inert=true;});
      index=0;busy=false;active=true;root.hidden=false;
      document.getElementById('tour-error').hidden=true;
      next.disabled=skip.disabled=false;
      back.onclick=()=>{if(index>0){index--;render();}};
      next.onclick=()=>{if(index<data.steps.length-1){index++;render();}else return finish();};
      skip.onclick=finish;render();
    }catch(_){if(active)close();}
  }};
})();
