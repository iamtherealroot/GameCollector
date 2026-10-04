const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const fields = {};
for (const name of ['box_present','media_present','manual_present','sealed','ownership_format','box_condition','media_condition']) {
  fields[name] = {checked:name==='media_present',value:name==='ownership_format'?'physical':'8',disabled:false,
    addEventListener(event,fn){this[event]=fn;}};
}
const form={querySelector(selector){return fields[selector.match(/name="([^"]+)"/)[1]];}};
vm.runInNewContext(fs.readFileSync('app/static/copy-condition.js','utf8'),{document:{getElementById(){return form;}}});
assert.equal(fields.box_condition.disabled,true);
assert.equal(fields.media_condition.disabled,false);
fields.box_present.checked=true;fields.box_present.change();assert.equal(fields.box_condition.disabled,false);
fields.box_present.checked=false;fields.box_present.change();assert.equal(fields.box_condition.disabled,true);
fields.sealed.checked=true;fields.sealed.change();
assert.equal(fields.box_present.checked,true);assert.equal(fields.manual_present.checked,true);assert.equal(fields.box_condition.disabled,false);
fields.box_present.checked=false;fields.box_present.change();assert.equal(fields.sealed.checked,false);assert.equal(fields.box_condition.disabled,true);
fields.media_present.checked=false;fields.media_present.change();assert.equal(fields.media_condition.disabled,true);
fields.ownership_format.value='digital';fields.ownership_format.change();assert.equal(fields.box_condition.disabled,true);assert.equal(fields.media_condition.disabled,true);
fields.ownership_format.value='physical';fields.ownership_format.change();assert.equal(fields.box_condition.disabled,true);
console.log('OK: initial loose copy, OVP toggling, sealed consistency, missing medium and digital conditions');
