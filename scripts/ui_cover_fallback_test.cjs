const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const image=(inside=true)=>({tagName:'IMG',className:'top10-cover',alt:'Pokémon',complete:true,naturalWidth:0,closest:()=>inside,replaceWith(node){this.replaced=node;}});
const cached=image(),outside=image(false),loaded=image();loaded.naturalWidth=100;
let error;
vm.runInNewContext(fs.readFileSync('app/static/cover-fallback.js','utf8'),{document:{
  createElement:()=>({setAttribute(key,val){this[key]=val;}}),
  addEventListener(name,handler,capture){assert.equal(name,'error');assert.equal(capture,true);error=handler;},
  querySelectorAll:()=>[cached,outside,loaded]
}});
assert.equal(cached.replaced.role,'img');assert.match(cached.replaced['aria-label'],/Pokémon/);
assert.equal(outside.replaced,undefined);assert.equal(loaded.replaced,undefined);
const lazy=image();error({target:lazy});assert.equal(lazy.replaced.textContent,'📚');
error({target:{tagName:'SCRIPT'}});
console.log('OK: broken cached/lazy covers, accessible placeholder, loaded images and non-images preserved');
