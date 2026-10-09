const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
function launch(initial = '', connected = true) {
  const fields = {'cmi.suspend_data':initial}, calls = [], elements = {}, events = {};
  const element = () => ({children:[],hidden:false,textContent:'',pause(){},load(){},removeAttribute(){},focus(){},replaceChildren(){this.children=[]},appendChild(v){this.children.push(v)}});
  const get = id => elements[id] ||= element();
  const API = {Initialize(){calls.push('initialize');return 'true'},GetValue(k){return fields[k]||''},SetValue(k,v){fields[k]=v;return 'true'},Commit(){calls.push('commit');return 'true'},Terminate(){calls.push('terminate');return 'true'}};
  const window = {API_1484_11:connected?API:null,API:{LMSInitialize(){throw new Error('SCORM 1.2 API must not be used')}},addEventListener:(k,v)=>events[k]=v,SOVEREIGN_LESSON:{title:'Test',start:'q',nodes:[
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
assert.equal(run.fields['cmi.score.raw'],'0');
run.get('continue').onclick();
run.get('choices').children[1].onclick();
assert.equal(run.fields['cmi.score.raw'],'0','retry must not inflate first-attempt score');
assert.equal(run.fields['cmi.score.scaled'],'0.00');
assert.equal(run.fields['cmi.completion_status'],'incomplete','final step needs explicit finish');
assert.equal(run.fields['cmi.exit'],'suspend');
run.get('continue').onclick();
assert.equal(run.fields['cmi.completion_status'],'completed');
assert.equal(run.fields['cmi.exit'],'normal');
assert.ok(run.fields['cmi.suspend_data'].length<64000);
const resumed = launch(run.fields['cmi.suspend_data']);
assert.equal(resumed.get('completion').hidden,false);
assert.equal(resumed.fields['cmi.score.raw'],'0');
run.events.pagehide();run.events.pagehide();
assert.equal(run.calls.filter(c=>c==='terminate').length,1);
assert.match(run.fields['cmi.session_time'],/^PT\d+H\d+M\d+S$/);
assert.match(launch('',false).get('notice').textContent,/Preview mode.*SCORM 2004/);
assert.equal(launch('{"current":999}').get('heading').textContent,'Question');
console.log('SCORM 2004 lifecycle, resume, completion, first-attempt scoring, and preview passed');
