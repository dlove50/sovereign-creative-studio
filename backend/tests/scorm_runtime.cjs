const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
function launch(initial = '', connected = true) {
  const fields = {'cmi.suspend_data':initial}, calls = [], elements = {}, events = {};
  const element = () => ({children:[],hidden:false,textContent:'',pause(){},load(){},removeAttribute(){},focus(){},replaceChildren(){this.children=[]},appendChild(v){this.children.push(v)}});
  const get = id => elements[id] ||= element();
  const API = {LMSInitialize(){calls.push('initialize');return 'true'},LMSGetValue(k){return fields[k]||''},LMSSetValue(k,v){fields[k]=v;return 'true'},LMSCommit(){calls.push('commit');return 'true'},LMSFinish(){calls.push('finish');return 'true'}};
  const window = {API:connected?API:null,addEventListener:(k,v)=>events[k]=v,SOVEREIGN_LESSON:{title:'Test',start:'q',nodes:[
    {id:'q',title:'Question',question:'Choose',choices:[{label:'Wrong',next:'q',is_correct:false,feedback:'Try again'},{label:'Right',next:'end',is_correct:true}]},
    {id:'end',body:'Done',choices:[]}
  ]}};
  window.parent = window;
  vm.runInNewContext(source,{window,document:{getElementById:get,createElement:element},Date,console});
  return {fields,calls,get,events};
}
let run = launch();
assert.equal(run.calls[0], 'initialize');
run.get('choices').children[0].onclick();
assert.equal(run.get('feedback').textContent,'Try again');
assert.equal(run.fields['cmi.core.score.raw'],'0');
run.get('continue').onclick();
run.get('choices').children[1].onclick();
assert.equal(run.fields['cmi.core.score.raw'],'0','retry must not inflate first-attempt score');
assert.equal(run.fields['cmi.core.lesson_status'],'incomplete','final step needs explicit finish');
run.get('continue').onclick();
assert.equal(run.fields['cmi.core.lesson_status'],'completed');
assert.ok(run.fields['cmi.suspend_data'].length<4096);
const resumed = launch(run.fields['cmi.suspend_data']);
assert.equal(resumed.get('completion').hidden,false);
assert.equal(resumed.fields['cmi.core.score.raw'],'0');
run.events.pagehide();run.events.pagehide();
assert.equal(run.calls.filter(c=>c==='finish').length,1);
assert.match(run.fields['cmi.core.session_time'],/^\d{4}:\d{2}:\d{2}\.\d{2}$/);
assert.match(launch('',false).get('notice').textContent,/Preview mode/);
assert.equal(launch('{"current":999}').get('heading').textContent,'Question');
console.log('SCORM lifecycle, resume, completion, first-attempt scoring, and preview passed');
