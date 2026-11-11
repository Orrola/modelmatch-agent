// Pure presentation and transport contracts; real DOM flows are exercised by ui_smoke.
load('static/modelmatch.js');
function assert(value, message) { if (!value) throw new Error(message); }
for (const key of ['fully_evaluable', 'provisional', 'unverified', 'ineligible']) assert(labels[key], 'Distinct candidate statuses');
assert(number(null) === 'Unknown' && number(0) === '0', 'Missing values stay distinct from zero');
assert(percent(.7) === '70%', 'Weights displayed as percentages, indices unchanged');
assert(metricLabel('evaluations.artificial_analysis_intelligence_index') === 'General Intelligence Index', 'Readable metrics');
assert(sourceCategory({source_type:'official_docs',verification_status:'verified'}, {data_mode:'mock'}).label === 'Synthetic fixture', 'Mock evidence never becomes official');
assert(providerName({name:'A name mentioning a provider'}) === null, 'Provider names are not guessed');
assert(rationale({G:null,U:20,eligibility:'eligible'},fixture.decision).includes('unavailable'), 'Missing index rationale');
const first=decodeFrames(': heartbeat\n\ndata: {"type":"start"}\r\n\r');
assert(first.events.length===0,'Wait for a complete CRLF delimiter');
const second=decodeFrames(first.buffer+'\n'+'data: {"type":"done",\n'+'data: "result":{}}\n\n');
assert(second.events.length===2 && second.events[1].type==='done','Chunked and multiline SSE');
const trace=['A','B','C'].flatMap((role,i)=>[{type:'researcher_start',role,round_number:0,context_id:role,monotonic:i},{type:'researcher_end',context_id:role,monotonic:10+i}]);
assert(observedParallel(trace), 'Observed execution overlap');
assert(!observedParallel([{type:'dispatch_batch',calls:['research_a','research_b','research_c']}]), 'Dispatch names alone do not prove parallelism');
assert(!observedParallel(trace.map(e=>e.type==='researcher_end'?{...e,monotonic:1}:e)), 'No invented execution overlap');

// Exercise request sequencing without pretending this small stub is a browser.
const nodes=new Map();
function node(){return {textContent:'',value:'',hidden:false,disabled:false,children:[],style:{setProperty(){}},setAttribute(){},append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},focus(){this.focused=true;},querySelector(){return null;},contains(){return false;},reportValidity(){return false;}};}
globalThis.document={createElement:()=>node(),querySelectorAll:()=>[],getElementById:id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}};
globalThis.AbortController=class {constructor(){this.signal={listeners:[],addEventListener(name,cb){this.listeners.push(cb);}};}abort(){for(const cb of this.signal.listeners)cb();}};
globalThis.clearTimeout=()=>{};
globalThis.TextDecoder=class {decode(value){return typeof value==='string'?value:'';}};
state.analysisId='synthetic-id';state.original=fixture;
const original=JSON.stringify(fixture);const requests=[];
renderDecision=function(d){state.decision=d;};
globalThis.fetch=(path,options)=>{const body=JSON.parse(options.body);requests.push({path,body});return Promise.resolve({ok:true,json:()=>Promise.resolve({decision:fixture.decision,writer_explanation_stale:true})});};
recalculate(.7).then(()=>{
  assert(requests[0].body.user_alpha===.7 && requests[0].path==='/api/modelmatch/recalculate','Server-side alpha recalculation');
  assert(state.writerStale,'Original Writer explanation marked stale');
  return recalculate(null);
}).then(()=>{
  assert(requests[1].body.user_alpha===null,'Reset uses backend task defaults');
  assert(JSON.stringify(state.original)===original,'Original analysis remains unchanged');
  const question=document.getElementById('question');question.value='Analyze financial documents';
  state.mode='live_vertex';
  document.querySelectorAll=selector=>selector==='input[name=hard]:checked'?[{value:'ttft'}]:[];
  let blocked=false;try{formInput();}catch(e){blocked=e.message.includes('Enter a target');}
  assert(blocked,'Missing hard target rejected before research');
  document.querySelectorAll=()=>[];
  assert(formInput().approve_live===true,'Run action explicitly requests the live backend');
  state.mode='offline_synthetic';
  assert(formInput().approve_live===false,'Synthetic mode is an explicit alternative');
  state.mode=null;
  let modeBlocked=false;try{formInput();}catch(e){modeBlocked=e.message.includes('Execution mode');}
  assert(modeBlocked,'Unavailable configuration cannot silently select a mode');
  state.mode='live_vertex';
  assert(analysisError({error:'snapshot_unavailable'}).includes('AA_API_KEY'),'AA errors have an actionable message');
  assert(analysisError({integration_usage:{records:[{status:'failed',error:{category:'authentication_failed'}}]}}).includes('ADC'),'Provider errors have an actionable message');
  // Renderers are isolated here; the actual state/stream/cancellation logic still executes.
  renderProgress=()=>{};renderPlan=()=>{};renderTechnical=()=>{};navigate=()=>{};
  globalThis.fetch=()=>Promise.resolve({ok:true,body:{getReader:()=>({read:()=>Promise.resolve({done:false,value:'data: {"type":"stage","agent":"Researcher A","stage":"research","status":"running"}\n\ndata: {"type":"error","message":"Synthetic stream failure"}\n\n'}),cancel:()=>Promise.resolve(),releaseLock(){}})}});
  return analyze();
}).then(()=>{
  assert(state.stages.get('A')==='failed','Observed running stage fails on stream error');
  assert(state.stages.get('writer')==='skipped','Unreached Writer is skipped');
  assert(!state.busy && document.getElementById('status').textContent==='Synthetic stream failure','Error releases controls');
  globalThis.fetch=(path,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{const error=new Error('Stopped');error.name='AbortError';reject(error);}));
  const pending=analyze();state.controller.abort();return pending;
}).then(()=>{
  assert(!state.busy && document.getElementById('status').textContent.includes('Analysis stopped'),'Cancellation releases controls');
  assert(![...state.stages.values()].includes('completed'),'Cancellation invents no completed stages');
  handle({type:'done',analysis_id:'clarification-id',result:{status:'clarification_needed',questions:['What concrete task?'],trace:[],tool_calls:[]}});
  assert(document.getElementById('questions').children.length===1 && !document.getElementById('clarification').hidden,'Readable clarification questions');
  assert(document.getElementById('answer').focused,'Clarification receives keyboard focus');
  print('Frontend contract checks passed');
}).catch(e=>{print(String(e));quit(1);});
