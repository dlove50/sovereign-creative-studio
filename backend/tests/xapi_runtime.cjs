const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
const ACTOR = {objectType:'Agent', name:'Learner', mbox:'mailto:learner@example.com'};
const lessonData = () => ({id:'L1', activity_id:'urn:sovereign:lesson:L1', title:'Test', start:'q', nodes:[
  {id:'q', title:'Question', question:'Choose', choices:[{label:'Wrong', next:'q', is_correct:false, feedback:'Try again'}, {label:'Right', next:'end', is_correct:true}]},
  {id:'end', body:'Done', choices:[]}
]});
async function launch({search = '', store = {}, statements = [], failStatements = false} = {}) {
  const elements = {}, events = {};
  const element = () => ({children:[],hidden:false,textContent:'',pause(){},load(){},removeAttribute(){},focus(){},replaceChildren(){this.children=[]},appendChild(v){this.children.push(v)}});
  const get = id => elements[id] ||= element();
  const requests = [];
  const fetchMock = async (url, options = {}) => {
    requests.push({url:String(url), method:options.method || 'GET', headers:options.headers || {}});
    const u = new URL(String(url));
    if (u.pathname.endsWith('/statements') && options.method === 'POST') {
      if (failStatements) return {ok:false, status:500};
      statements.push(JSON.parse(options.body)); return {ok:true, status:200, json:async()=>[]};
    }
    if (u.pathname.endsWith('/activities/state')) {
      const key = u.searchParams.get('activityId') + '|' + u.searchParams.get('stateId');
      if (options.method === 'PUT') { store[key] = JSON.parse(options.body); return {ok:true, status:204}; }
      return key in store ? {ok:true, status:200, json:async()=>store[key]} : {ok:false, status:404};
    }
    return {ok:false, status:404};
  };
  const window = {addEventListener:(k,v)=>events[k]=v, SOVEREIGN_LESSON:lessonData()};
  window.parent = window;
  vm.runInNewContext(source, {window, document:{getElementById:get, createElement:element}, location:{search}, URLSearchParams, URL, fetch:fetchMock, encodeURIComponent, Date, console, Promise});
  await new Promise(r => setTimeout(r, 30));
  return {get, events, requests, statements, store};
}
const query = '?endpoint=' + encodeURIComponent('https://lrs.example.com/xapi') + '&auth=' + encodeURIComponent('Basic abc') + '&actor=' + encodeURIComponent(JSON.stringify(ACTOR));
(async () => {
  let run = await launch({search:query});
  assert.equal(run.statements[0].verb.id, 'http://adlnet.gov/expapi/verbs/initialized');
  assert.equal(run.statements[0].actor.mbox, ACTOR.mbox);
  assert.equal(run.statements[0].object.id, 'urn:sovereign:lesson:L1');
  assert.equal(run.requests[0].url.startsWith('https://lrs.example.com/xapi/activities/state'), true, 'state is read before the first statement');
  assert.equal(run.requests.find(r => r.method === 'POST').headers['X-Experience-API-Version'], '1.0.3');
  assert.equal(run.requests.find(r => r.method === 'POST').headers.Authorization, 'Basic abc');
  run.get('choices').children[0].onclick();
  await new Promise(r => setTimeout(r, 30));
  const wrong = run.statements.find(s => s.verb.id.endsWith('/answered'));
  assert.equal(wrong.result.response, 'Wrong'); assert.equal(wrong.result.success, false);
  run.get('continue').onclick();
  run.get('choices').children[1].onclick();
  await new Promise(r => setTimeout(r, 30));
  assert.equal(run.statements.filter(s => s.verb.id.endsWith('/answered')).length, 1, 'a retry must not count as a second answer');
  run.get('continue').onclick();
  await new Promise(r => setTimeout(r, 30));
  const done = run.statements.find(s => s.verb.id.endsWith('/completed'));
  assert.equal(done.result.completion, true); assert.equal(done.result.score.raw, 0); assert.equal(done.result.score.scaled, 0);
  assert.match(done.result.duration, /^PT\d+H\d+M\d+S$/);
  run.events.pagehide(); run.events.pagehide();
  await new Promise(r => setTimeout(r, 30));
  assert.equal(run.statements.filter(s => s.verb.id.endsWith('/terminated')).length, 1);
  const saved = Object.values(run.store)[0];
  assert.equal(saved.complete, true);
  // A returning learner resumes where they stopped and gets a "resumed" statement.
  const resumed = await launch({search:query, store:run.store, statements:[]});
  assert.equal(resumed.statements[0].verb.id, 'http://adlnet.gov/expapi/verbs/resumed');
  assert.equal(resumed.get('completion').hidden, false);
  // Without launch parameters it is a preview and sends nothing.
  const preview = await launch({});
  assert.match(preview.get('notice').textContent, /Preview mode/);
  assert.equal(preview.requests.length, 0);
  assert.equal(preview.get('heading').textContent, 'Question');
  // A store that rejects statements is reported, not hidden.
  const broken = await launch({search:query, failStatements:true});
  assert.match(broken.get('notice').textContent, /did not accept/);
  console.log('xAPI statements, resume, retries, preview, and store errors passed');
})().catch(e => { console.error(e); process.exit(1); });
