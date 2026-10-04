(() => {
  const empty = document.querySelector('.dashboard-add-category');
  const field = document.querySelector('#custom-category-create input[name="title"]');
  if (empty && field) empty.addEventListener('click', () => {
    window.requestAnimationFrame(() => field.focus({preventScroll:true}));
  });
  const shelves = [...document.querySelectorAll('[data-shelf-cases]')].map(wrap => {
    let cases=[];
    try { cases=JSON.parse(wrap.dataset.shelfCases); } catch (_) { /* Keep the rendered shelf. */ }
    return {wrap, cases, offset:0, media:[...wrap.querySelectorAll('.regal-item')]};
  });
  let paused = false;
  const toggle = document.querySelector('.regal-rotation-toggle');
  toggle?.addEventListener('click', () => {
    paused=!paused;
    toggle.setAttribute('aria-pressed', String(paused));
    toggle.textContent=paused?'Titelwechsel fortsetzen':'Titelwechsel pausieren';
  });
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let shaking=false,sceneSequence=0;
  const isolateClipIds=(node,prefix)=>{
    const ids=new Map();
    for(const child of node.querySelectorAll?.('[id]') || []) {
      const old=child.getAttribute('id');ids.set(old,prefix+old);child.setAttribute('id',prefix+old);
    }
    for(const child of node.querySelectorAll?.('[clip-path]') || []) {
      const old=child.getAttribute('clip-path').slice(5,-1);
      if(ids.has(old)) child.setAttribute('clip-path','url(#'+ids.get(old)+')');
    }
  };
  const cabinet=document.querySelector('.collection-regal');
  const shake=document.querySelector('.regal-shake-trigger');
  let helpersLoaded=false,helpersLoading=false;
  shake?.addEventListener('click', async () => {
    if (shaking || !cabinet) return;
    if (reduced.matches) return;
    if(cabinet.dataset?.helpersUrl && !helpersLoaded) {
      if(helpersLoading)return;
      helpersLoading=true;shake.disabled=true;
      try {
        const response=await fetch(cabinet.dataset.helpersUrl,{credentials:'same-origin'});
        if(!response.ok)throw new Error('helpers unavailable');
        const payload=await response.json();
        cabinet.querySelectorAll('[data-helper-key]').forEach(set=>{
          const template=document.createElement('template');template.innerHTML=payload.helpers[set.dataset.helperKey] || '';
          const source=template.content.querySelector('[data-helper-set]');if(source)set.innerHTML=source.innerHTML;
        });
        document.querySelector('.regal-doorman')?.remove();
        cabinet.parentElement.insertAdjacentHTML('beforeend',payload.guard);
        helpersLoaded=true;
      } catch (_) { return; }
      finally {helpersLoading=false;shake.disabled=false;}
      if(reduced.matches)return;
    }

    shaking=true;shake.disabled=true;sceneSequence+=1;
    cabinet.setAttribute?.('data-helper-gesture',Math.random()<.5?'wiper':'finger');
    const stage=cabinet.querySelector?.('.regal-helper-stage');
    const securityPool=document.querySelector('.regal-security-pool');
    const crewTemplates=[...(securityPool?.querySelectorAll('.regal-security-template') || [])];
    const hasCrew=Boolean(stage && crewTemplates.length===4);
    const laddersByLane=new Map();
    const door=document.querySelector('.regal-helper-door');
    const guard=document.querySelector('.regal-doorman');
    if(door && guard) {
      const frame=cabinet.getBoundingClientRect(),entry=door.getBoundingClientRect();
      const compact=window.matchMedia('(max-width:720px)').matches;
      const width=compact?80:100,height=compact?76:96;
      const left=entry.left+entry.width-frame.left-width*.2;
      guard.style.setProperty('--guard-left',left+'px');
      guard.style.setProperty('--guard-top',(entry.bottom-frame.top-height)+'px');
      const dx=entry.left+entry.width/2-frame.left-left-width/2;
      guard.style.setProperty('--guard-door-x',dx+'px');
      guard.style.setProperty('--return-facing',dx<0?'-1':'1');
    }
    stage?.replaceChildren();
    const sportTargets=[];
    const usedCharacters=new Set();
    const usedThemes=new Set();
    const themeOf=character=>/^(sport|pirate|detective|rapper|profession|class|falconer)-/.exec(String(character||''))?.[1] || character;
    let helperCount=0,lastHelperStart=-1100;
    const laneStarts=new Map(),helperRoutes=[];
    cabinet.querySelectorAll('[data-helper-set]').forEach(set => {
      const helpers=[...set.querySelectorAll('.regal-helper')];
      if(!helpers.length) return;
      const previous=Number(set.dataset.previousHelper ?? -1);
      let available=helpers.map((helper,index)=>({helper,index})).filter(({helper})=>
        !helper.dataset?.character || (!usedCharacters.has(helper.dataset.character) && !usedThemes.has(themeOf(helper.dataset.character))));
      if(!available.length) {
        helpers.forEach(helper=>helper.classList.remove('is-selected'));
        return; // No duplicates when a category has exhausted its alternatives.
      }
      const preferred=available.filter(({helper})=>themeOf(helper.dataset?.character)===helper.dataset?.preferredTheme);
      if(preferred.length)available=preferred;
      if(previous<0) {
        const sports=available.filter(({helper})=>helper.dataset?.character?.startsWith('sport-') || helper.dataset?.character?.startsWith('pirate-') || helper.dataset?.character?.startsWith('detective-') || helper.dataset?.character?.startsWith('rapper-'));
        if(sports.length) available=sports;
      } else if(available.length>1) {
        available=available.filter(({index})=>index!==previous);
      }
      const next=available[Math.floor(Math.random()*available.length)].index;
      const character=helpers[next].dataset?.character;
      if(character) {usedCharacters.add(character);usedThemes.add(themeOf(character));}
      helpers.forEach((helper,index)=>helper.classList.toggle('is-selected',index===next));
      set.dataset.previousHelper=String(next);
      if(stage && door) {
        const compartment=set.closest('.shelf-compartment');
        const frame=cabinet.getBoundingClientRect();
        const box=compartment.getBoundingClientRect();
        const entry=door.getBoundingClientRect();
        const compact=window.matchMedia('(max-width:720px)').matches;
        const width=compact?68:90, height=compact?85:112;
        const parkX=compact?48:80;
        const board=compartment.querySelector?.('.regal-shelf-board');
        const left=box.left-frame.left+12;
        const floor=board ? board.getBoundingClientRect().top-frame.top+10 : box.bottom-frame.top-96;
        const lane=Math.round(left+width/2-12);
        const doorX=entry.left+entry.width/2-frame.left-left-width/2;
        const doorY=entry.bottom-frame.top-floor;
        const clone=helpers[next].cloneNode(true);
        clone.classList.add('regal-helper-clone');
        isolateClipIds(clone,'scene-'+sceneSequence+'-helper-'+helperCount+'-');
        clone.style.left=left+'px';clone.style.top=(floor-height)+'px';
        clone.style.setProperty('--door-x',doorX+'px');
        clone.style.setProperty('--door-y',doorY+'px');
        clone.style.setProperty('--out-facing',doorX>0?'-1':'1');
        clone.style.setProperty('--return-facing',doorX>0?'1':'-1');
        clone.style.setProperty('--gait-delay',-(next*90)+'ms');
        clone.style.setProperty('--park-x',parkX+'px');
        const start=Math.max(lastHelperStart+1100,(laneStarts.get(lane) ?? -6400)+6400);
        clone.style.setProperty('--helper-start',start+'ms');
        laneStarts.set(lane,start);lastHelperStart=start;
        helperRoutes.push({clone,lane,floor});
        helperCount+=1;
        const entryFloor=entry.bottom-frame.top;
        const ladderTop=Math.min(floor,entryFloor)-25;
        const ladderBottom=Math.max(floor,entryFloor);
        let ladder=laddersByLane.get(lane);
        if(!ladder) {
          ladder=document.createElement('span');ladder.className='regal-helper-ladder';
          ladder.style.left=lane+'px';ladder.style.top=ladderTop+'px';
          ladder.style.height=Math.max(40,ladderBottom-ladderTop)+'px';
          ladder.style.setProperty('--crew-delay',(laddersByLane.size%4)*1100+'ms');
          laddersByLane.set(lane,ladder);stage.appendChild(ladder);
        } else {
          const previousTop=parseFloat(ladder.style.top);
          const bottom=Math.max(previousTop+parseFloat(ladder.style.height),ladderBottom);
          const top=Math.min(previousTop,ladderTop);
          ladder.style.top=top+'px';ladder.style.height=Math.max(40,bottom-top)+'px';
        }
        stage.appendChild(clone);
        if(clone.dataset?.character==='falconer-ranger') {
          const birdTemplate=clone.querySelector('.regal-bird-template');
          [...compartment.querySelectorAll('.regal-item')].forEach((medium,index)=>{
            const target=medium.getBoundingClientRect(),bird=birdTemplate.cloneNode(true);
            isolateClipIds(bird,'scene-'+sceneSequence+'-bird-'+helperCount+'-'+index+'-');
            bird.classList.remove('regal-bird-template');bird.classList.add('regal-flying-bird');
            bird.style.left=(left+parkX+width*.6-28)+'px';bird.style.top=(floor-height*.6-50)+'px';
            bird.style.setProperty('--bird-x',(target.left+target.width/2-frame.left-left-parkX-width*.6)+'px');
            bird.style.setProperty('--bird-y',(target.top+target.height/2-frame.top-floor+height*.6)+'px');
            bird.style.setProperty('--bird-delay',(index%8)*1200+'ms');
            medium.classList.add('sport-restock');sportTargets.push(medium);stage.appendChild(bird);
          });
        }
        if(clone.dataset?.character?.startsWith('sport-') || clone.dataset?.character?.startsWith('pirate-')) {
          const pirate=clone.dataset.character.startsWith('pirate-');
          clone.style.setProperty('--sport-shots',String(compartment.querySelectorAll('.regal-item').length));
          // The shot starts at the helper's foot and ends at each real item.
          [...compartment.querySelectorAll('.regal-item')].forEach((medium,index)=>{
            const target=medium.getBoundingClientRect();
            const ball=document.createElement('span');
            ball.className=pirate?'regal-pirate-burst':'regal-sport-ball'+(clone.dataset.character==='sport-tennis'?' tennis-ball':'');
            ball.textContent=pirate?'✦':clone.dataset.character==='sport-tennis'?'':'⚽';
            ball.setAttribute('aria-hidden','true');
            const x=pirate?target.left+target.width/2-frame.left:left+parkX+width*.75;
            const y=pirate?target.top+target.height/2-frame.top:floor-15;
            ball.style.left=x+'px';ball.style.top=y+'px';
            ball.style.setProperty('--shot-x',(target.left+target.width/2-frame.left-x)+'px');
            ball.style.setProperty('--shot-y',(target.top+target.height/2-frame.top-y)+'px');
            ball.style.setProperty('--shot-delay',(index%8)*1200+300+'ms');
            medium.classList.add('sport-restock');
            sportTargets.push(medium);stage.appendChild(ball);
          });
        }
      }
    });
    // Upper helpers descend first. Every lane remains reserved through the
    // entire exit, so lower helpers wait off the ladder without being crossed.
    const returnLaneStarts=new Map();
    let lastReturnStart=-1100;
    helperRoutes.sort((a,b)=>a.floor-b.floor).forEach(({clone,lane})=>{
      const start=Math.max(lastReturnStart+1100,(returnLaneStarts.get(lane) ?? -6400)+6400);
      clone.style.setProperty('--helper-return-start',start+'ms');
      returnLaneStarts.set(lane,start);lastReturnStart=start;
    });
    if(hasCrew && door) {
      const frame=cabinet.getBoundingClientRect(),entry=door.getBoundingClientRect();
      const compact=window.matchMedia('(max-width:720px)').matches;
      const crewWidth=compact?68:90,crewHeight=compact?90:112;
      const originX=entry.left+entry.width/2-frame.left-crewWidth/2;
      const originY=entry.bottom-frame.top-crewHeight;
      const lanes=[...laddersByLane.keys()];
      crewTemplates.forEach((template,index)=>{
        const crew=template.cloneNode(true);
        crew.classList.add('regal-security-crew');
        isolateClipIds(crew,'scene-'+sceneSequence+'-security-'+index+'-');
        crew.style.left=originX+'px';crew.style.top=originY+'px';
        const lane=lanes[index%Math.max(1,lanes.length)] ?? originX;
        const supportOffset=index>=lanes.length?55:0;
        const dx=lane+12-originX-crewWidth/2+supportOffset;
        crew.style.setProperty('--crew-x',dx+'px');
        crew.style.setProperty('--out-facing',dx<0?'-1':'1');
        crew.style.setProperty('--return-facing',dx<0?'1':'-1');
        crew.style.setProperty('--crew-start',index*1100+'ms');
        const carried=document.createElement('span');carried.className='regal-carried-ladder';
        crew.appendChild(carried);stage.appendChild(crew);
      });
    }
    cabinet.querySelectorAll('.regal-media').forEach((medium,index) => {
      medium.style.setProperty('--fall-delay', (index%7)*35+'ms');
      medium.style.setProperty('--restock-delay', (index%8)*1200+'ms');
      medium.style.setProperty('--fall-tilt', ((index%5)-2)*19+'deg');
    });
    const queueDelay=Math.max(0,lastHelperStart);
    const returnQueueDelay=Math.max(0,lastReturnStart);
    const setupDuration=hasCrew?12700:1400;
    const removalDuration=hasCrew?11600:0;
    if(hasCrew) {
      window.setTimeout(()=>{
        cabinet.classList.add('is-security-building');
      },2200);
      window.setTimeout(()=>{
        cabinet.classList.remove('is-ladders-ready');cabinet.classList.add('is-security-removing');
      },25550+setupDuration+queueDelay+returnQueueDelay);
    }
    cabinet.classList.add('is-shaking');
    window.setTimeout(() => cabinet.classList.add('is-spilling'),400);
    // Last fall completes at 400 + 6*35 + 700 = 1310 ms.
    window.setTimeout(() => cabinet.classList.add('is-door-revealed'),1450);
    window.setTimeout(() => {
      cabinet.classList.remove('is-security-building');
      cabinet.classList.add('is-ladders-ready','is-helper-arriving');
    },1550+setupDuration);
    window.setTimeout(() => {
      cabinet.classList.remove('is-helper-arriving');cabinet.classList.add('is-restocking');
    },7550+setupDuration+queueDelay);
    window.setTimeout(() => {
      cabinet.classList.add('is-helper-returning');
    },19550+setupDuration+queueDelay);
    window.setTimeout(() => {
      cabinet.classList.remove('is-security-removing');
      cabinet.classList.add('is-helper-gesture');
    },25550+setupDuration+removalDuration+queueDelay+returnQueueDelay);
    window.setTimeout(() => {
      cabinet.classList.add('is-doorman-leaving');
    },29050+setupDuration+removalDuration+queueDelay+returnQueueDelay);
    window.setTimeout(() => cabinet.classList.add('is-door-closing'),31150+setupDuration+removalDuration+queueDelay+returnQueueDelay);
    window.setTimeout(() => {
      cabinet.classList.remove('is-shaking','is-spilling','is-door-revealed','is-restocking','is-helper-arriving','is-helper-returning','is-helper-gesture','is-doorman-leaving','is-door-closing','is-security-building','is-security-removing','is-ladders-ready');
      stage?.replaceChildren();
      sportTargets.forEach(medium=>medium.classList.remove('sport-restock'));
      shaking=false;shake.disabled=false;
    },32150+setupDuration+removalDuration+queueDelay+returnQueueDelay);
  });
  window.setInterval(() => {
    if (paused || shaking || reduced.matches || document.hidden) return;
    shelves.forEach(shelf => {
      if (shelf.cases.filter(item => item.title).length < 2 ||
          shelf.wrap.closest('.shelf-compartment').matches(':hover, :focus-within')) return;
      shelf.offset=(shelf.offset+1)%shelf.cases.length;
      const shown=shelf.media.map((_,index)=>shelf.cases[(shelf.offset+index)%shelf.cases.length])
        .sort((a,b)=>(a.height||0)-(b.height||0));
      shelf.media.forEach((media,index) => {
        const item=shown[index];
        media.className='regal-media regal-item case-'+item.style+(index===3?' regal-pull-default':'');
        if(item.height) media.style.setProperty('--case-height',item.height+'px');
        media.querySelector('.regal-spine-title').textContent=item.title;
        media.querySelector('.regal-case-brand').textContent=item.format || '';
        media.setAttribute('href',item.href || shelf.wrap.dataset.categoryHref);
        media.setAttribute('aria-label',(item.title || shelf.wrap.dataset.categoryTitle)+' öffnen');
        const side=media.querySelector('.regal-case-side');
        side.replaceChildren();
        if (item.cover) {
          const cover=document.createElement('img');
          cover.className='regal-side-cover';cover.alt='';cover.loading='lazy';cover.src=item.cover;
          side.appendChild(cover);
        }
        if (item.title) media.setAttribute('title',item.title); else media.removeAttribute('title');
      });
    });
  }, 12000);
})();
