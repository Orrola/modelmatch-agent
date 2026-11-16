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
const renderWorkflowProgress = renderProgress;
renderProgress=()=>{};
state.stages=new Map();
progress('Lead','running','parse',false);
progress('Lead','failed','parse',false);
for (const stage of ['dispatch','followup','review_final']) progress('Lead','not_reached',stage,false);
assert(state.stages.get('lead')==='failed','Observed production parse failure survives unreached dispatch cleanup');
finishProgress({diagnostics:{stages:{parse:{agent:'Lead',stage:'parse',status:'failed'},dispatch:{agent:'Lead',stage:'dispatch',status:'not_reached'}}}});
assert(state.stages.get('lead')==='failed','Final state replay preserves the actual failed Lead stage');
for (const status of ['completed','cancelled','interrupted','failed']) {
  state.stages=new Map(); progress('Lead',status,'parse',true); progress('Lead','not_reached','dispatch',false);
  assert(state.stages.get('lead')===status,'Cleanup cannot erase an observed terminal state');
}
state.stages=new Map();progress('Lead','skipped','parse');
assert(state.stages.get('lead')==='skipped','Intentional skip stays distinct from not reached');
state.stages=new Map();
progress('Lead','accepted','parse',true);
progress('Lead','accepted','dispatch',true);
for (const role of ['A','B','C']) progress(`Researcher ${role}`,'accepted',role,true);
progress('Lead','accepted','review',true);
progress('Lead','running','followup',false);
progress('Lead','failed','followup',false);
finishProgress({diagnostics:{stages:{parse:{agent:'Lead',stage:'parse',status:'accepted'},dispatch:{agent:'Lead',stage:'dispatch',status:'accepted'},review:{agent:'Lead',stage:'review',status:'accepted'},followup:{agent:'Lead',stage:'followup',status:'failed'},decision:{agent:'Decision Tool',stage:'decision',status:'not_reached'},writer:{agent:'Writer',stage:'writer',status:'not_reached'}}}});
assert(state.stages.get('lead')==='accepted' && state.stages.get('followup')==='failed','Later Lead failure cannot relabel accepted requirement parsing');
assert(state.stages.get('review')==='accepted' && state.stages.get('decision')==='not_reached','Review acceptance does not imply authorization and execution of all later stages');
renderWorkflowProgress();
assert(document.getElementById('progress').children[0].children.some(n=>n.textContent==='Follow-up dispatch: Failed'),'The actual failed Lead phase remains visible');
progress('Lead','failed','dispatch',false);
assert(state.stages.get('lead')==='accepted' && state.stages.get('dispatch')==='failed','Initial dispatch also stays distinct from parse');
assert(analysisError({error:'invalid_or_over_budget_followup'}).includes('controller could not authorize'),'Controller rejection has a precise safe message');
assert(analysisError({error:'researcher_evidence_conflict'}).includes('inconsistent researcher evidence'),'Evidence conflicts are not mislabeled as ADC failures');
assert(analysisError({error:'authorized_followup_tool_failed'}).includes('follow-up tool failed'),'Actual controller tool failure has an accurate message');
const quotaMessage = writerFailureMessage({writer_error:{category:'quota_or_rate_limit'}});
assert(quotaMessage.includes('quota or rate limit') && quotaMessage.includes('No automatic retry') && quotaMessage.includes('fallback'),'Writer 429 remains an explicit failed fallback');
assert(writerFailureMessage({writer_error:{category:'incomplete_generation'}}).includes('output limit'),'Writer truncation differs from schema and provider errors');
assert(writerFailureMessage({writer_error:{category:'malformed_json'}}).includes('not valid JSON'),'Writer JSON syntax error is explicit');
assert(writerFailureMessage({writer_error:{category:'schema_validation_error'}}).includes('schema validation'),'Writer schema error is explicit');
assert(writerFailureMessage({writer_error:{category:'evidence_validation_error'}}).includes('evidence or ranking'),'Writer evidence validation stays strict and distinct');
assert(analysisError({error:'model_request_timeout'}).includes('model request'),'Model timeout remains separate from workflow timeout');
assert(analysisError({error:'workflow_timeout'}).includes('overall time'),'Workflow timeout remains separate');
const adapterError = analysisError({integration_usage:{records:[{status:'failed',error:{category:'adapter_rejection'}}]}});
assert(adapterError.includes('unsupported request parameters') && !adapterError.includes('ADC') && !adapterError.includes('AA API access'),'Adapter rejection is not mislabeled as authentication failure');
assert(analysisError({integration_usage:{records:[{status:'failed',error:{category:'invalid_request_or_unsupported_combination'}}]}}).includes('feature combination'),'Provider request rejection remains distinct from adapter rejection');
assert(analysisError({diagnostics:{blocking_failure:{error:{output_diagnostics:{failure_category:'incomplete_generation'}}}}}).includes('output limit'),'Incomplete generation uses observed diagnostic evidence');
progress('Lead','completed','review',false);
assert(state.stages.get('review')==='validating','Generation completion is not controller acceptance');
progress('Lead','accepted','review',true);
progress('Lead','skipped','review_final',false);
assert(state.stages.get('review')==='accepted','Unused final review cannot overwrite accepted initial review');
progress('Writer','fallback','writer',false);
assert(state.stages.get('writer')==='fallback','Fallback cannot count as accepted Writer output');
finishProgress({diagnostics:{stages:{review:{agent:'Lead',stage:'review',status:'failed'},decision:{agent:'Decision Tool',stage:'decision',status:'not_reached'}}}});
assert(state.stages.get('review')==='failed' && state.stages.get('decision')==='not_reached','A rejected review does not imply a decision ran');
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
  assert(state.stages.get('A')==='interrupted','Stream errors do not prove that a running agent failed');
  assert(state.stages.get('writer')==='not_reached','Unreached Writer is distinct from a policy skip');
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
