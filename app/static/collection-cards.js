
(()=>{
  if(window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  document.querySelectorAll('.collector-module-illustrated').forEach((tile,tileIndex)=>{
    const slides=[...tile.querySelectorAll('.collector-module-art')];
    if(slides.length<2)return;
    let current=0;
    const change=()=>{slides[current].classList.remove('is-active');current=(current+1)%slides.length;slides[current].classList.add('is-active');};
    window.setTimeout(()=>{change();window.setInterval(change,6000);},6000+(tileIndex*650));
  });
})();

const empty=document.querySelector('.dashboard-add-category');
empty?.addEventListener('click',()=>{const field=document.querySelector('#custom-category-create input[name=title]');const options=field?.closest('details');if(options)options.open=true;window.requestAnimationFrame(()=>field?.focus({preventScroll:true}));});
