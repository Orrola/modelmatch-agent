// Real presentation functions with a small DOM harness, not a browser layout claim.
load('static/recommendation_views.js');
load('static/modelmatch.js');
function assert(value, message) { if (!value) throw new Error(message); }
class Node {
  constructor(tag='div') {this.tagName=tag;this.className='';this.dataset={};this.children=[];this.value='';this.hidden=false;this.disabled=false;this.listeners={};this.style={setProperty(){}};this._text='';}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent||'').join(' ');}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this._text='';this.children=items;}
  setAttribute(){} addEventListener(name,cb){this.listeners[name]=cb;}
  get lastChild(){return this.children[this.children.length-1];}
  focus(){} scrollIntoView(){} querySelector(){return null;}
  showModal(){this.open=true;} close(){this.open=false;}
}
const nodes=new Map();
globalThis.document={createElement:tag=>new Node(tag),querySelectorAll:()=>[],getElementById:id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);}};
function all(node,predicate){return [node,...node.children.flatMap(c=>all(c,predicate))].filter(predicate);}
function setup(fixture){
 state.original=fixture;state.decision=fixture.decision;state.selection=fixture.selection||null;state.selector=fixture.selector||null;
 state.modelIdentity=fixture.model_identity||null;state.analysisId='synthetic';state.busy=false;state.drawerDecision=null;state.drawerId=null;
 $('model-drawer').open=false;$('ranking-scope').value='current';$('compare-panel').hidden=true;
}
const before=JSON.stringify(fixtures);
for(const [name,count] of [['one',1],['two',2],['three',3],['zero',0],['failure',0],['legacy',0]]){
 setup(fixtures[name]);renderDecision(state.decision);
 assert($('ranking').children.length===3,`${name}: exactly three named role slots`);
 assert(Number($('ranking').dataset.count)===count,`${name}: no invented choice`);
 assert(all($('ranking'),n=>n.className.includes('unavailable-slot')).length===3-count,`${name}: truthful empty slots`);
 assert($('recommendation-coverage').textContent.includes('Counts overlap'),'Coverage dimensions overlap');
 assert($('raw-ranking').textContent.includes('Raw Ranking'),'Raw ranking remains available');
}
setup(fixtures.states);renderDecision(state.decision);
const knownBlocked = Object.values(fixtures.states.decision.candidates).filter(c=>c.S===null);
const coverage = recommendationViews().scoreCoverage();
assert(knownBlocked.length===14 && coverage.missing===12 && coverage.other===2,'Known hard failures are not counted as missing scoring evidence');
assert($('recommendation-coverage').textContent.includes('Model Evaluation Coverage'),'Coverage title describes evaluation evidence');
assert($('recommendation-coverage').textContent.includes('See how many models have enough evidence to be scored and compared.'),'Exact coverage subtitle');
const primary=all($('recommendation-coverage'),n=>n.className.includes('coverage-primary'))[0];
assert(primary.children.length===3 && primary.children[0].children[0].textContent==='Models considered' && primary.children[1].children[0].textContent==='Models with scores' && primary.children[2].children[0].textContent==='Missing required scores','Exactly three visible primary metrics');
assert(primary.children[2].children[1].textContent==='12','Missing evidence count uses actual reported blockers');
assert(all($('recommendation-coverage'),n=>n.className==='coverage-secondary').every(n=>!n.open),'Secondary metrics collapsed by default');
assert($('recommendation-coverage').textContent.includes('Known hard-constraint failure: 2'),'Other score-blocking reasons remain visible in breakdown');
assert($('recommendation-coverage').textContent.includes('does not establish recommendation eligibility'),'Numeric score is not a recommendation eligibility claim');
setup(fixtures.policy);renderDecision(state.decision);
assert(recommendationViews().scoreCoverage().missing===0 && recommendationViews().scoreCoverage().other===6,'Policy-only blockers are not missing evidence');
assert($('recommendation-coverage').textContent.includes('Unsupported soft-requirement policy: 6'),'Policy failures are explained separately');
setup(fixtures.partial);renderDecision(state.decision);
assert($('ranking-subtitle').textContent.includes('partial proxy') && !$('ranking').textContent.includes('partial proxy'),'Generic proxy caveat occurs only near choices heading');
setup(fixtures.penalties);renderDecision(state.decision);
assert(all($('ranking'),n=>n.className==='model-warning').length>0,'Model-specific operational warnings remain on cards');
setup(fixtures.states);
state.decision=JSON.parse(JSON.stringify(state.decision));
for(const id of ['a','b']) delete state.decision.candidates[id].score_blockers;
renderDecision(state.decision);
assert(recommendationViews().scoreCoverage().unspecified===2 && $('recommendation-coverage').textContent.includes('confirmed'),'Missing reason metadata does not fabricate complete missing-score statistics');
setup(fixtures.three);renderDecision(state.decision);
assert($('ranking').children.map(c=>c.dataset.modelId).join(',')==='a,c,d','Canonical role IDs, not raw top three');
assert($('ranking').textContent.includes('Creator: Synthetic creator A'),'Creator comes from identity metadata');
assert($('ranking').textContent.includes('Synthetic fa'),'Family label comes from reviewed metadata');
assert($('ranking').textContent.includes('Raw rank 3'),'Alternative keeps original rank');
assert($('ranking').textContent.includes('non-dominated'),'Selection reason is explained');
const configs=all($('ranking').children[0],n=>n.className==='configuration-row');
assert(configs.length===1 && configs[0].textContent.includes('(b)'),'Only backend-defined other family members expand');
assert(all($('ranking'),n=>n.className==='family-configurations').length===1,'No zero-member family controls');
openModel('c');
assert(all($('drawer-content'),n=>n.className==='family-configurations').length===0,'Zero-member families do not create empty drawer expanders either');
$('model-drawer').open=false;
assert(all($('ranking'),n=>n.className==='rationale').length===0,'Generic task caveats are not repeated on cards');
assert(all($('ranking'),n=>n.className==='card-evidence-details').length===3 && all($('ranking'),n=>n.className==='card-evidence-details').every(n=>!n.open),'Card facts and operational detail are progressively disclosed');
assert(all($('potential-alternatives'),n=>n.className==='alternative-bucket').length===2,'Only nonempty exploration buckets get large panels');
assert(all($('potential-alternatives'),n=>n.className==='empty-alternative-buckets').length===2 && all($('potential-alternatives'),n=>n.className==='empty-alternative-buckets').every(n=>!n.open),'Empty statuses retain counts in collapsed details');
assert($('potential-alternatives').textContent.includes('Missing G') && $('potential-alternatives').textContent.includes('Missing U'),'Observed and missing dimensions are immediately explicit');
assert($('potential-alternatives').textContent.includes('Task-specific score available') && $('potential-alternatives').textContent.includes('General score available'),'G-only/U-only separate');
assert($('potential-alternatives').textContent.includes('These models have a task-related capability score, but lack a General Intelligence score needed for the overall ranking.') && $('potential-alternatives').textContent.includes('These models have a General Intelligence score, but lack the task-specific capability score needed for the overall ranking.'),'Both alternative descriptions match the approved wording');
assert($('potential-alternatives').textContent.includes('S: Unavailable'),'Alternatives never receive invented S');
assert(all($('potential-alternatives'),n=>n.className==='more-alternatives').length===2,'Bounded initial alternatives can expand returned entries');
assert($('potential-alternatives').textContent.includes('not a quality ranking'),'Alternative ordering is disclosed');
setup(fixtures.states);renderDecision(state.decision);
assert($('potential-alternatives').textContent.includes('A hard requirement has unknown evidence'),'Unverified hard constraint is explicit');
assert($('candidate-groups').textContent.includes('Ineligible'),'Known hard violators remain inspectable outside exploration');
openModel('a');
assert($('drawer-content').textContent.includes('Fail'),'Actual constraint_status is rendered, not mislabeled unknown');
setup(fixtures.one);renderDecision(state.decision);
assert($('ranking').textContent.includes('Family unknown'),'Unknown metadata is not inferred');
setup(fixtures.two);renderDecision(state.decision);
assert($('ranking').textContent.includes('Monthly cost not estimated'),'Missing price/workload stays unknown');
setup(fixtures.mismatch);renderDecision(state.decision);
assert($('recommendation-coverage').textContent.includes('do not match this snapshot'),'Mapping mismatch is explicit');
assert(all($('ranking'),n=>n.className==='configuration-row').length===0,'Mismatched mappings cannot supply family members');
setup(fixtures.failure);renderDecision(state.decision);finishProgress(fixtures.failure);
assert($('ranking').textContent.includes('selection failed'),'Selector failure is not a completed recommendation');
assert(state.stages.get('writer')==='skipped','Selector-unavailable skips Writer truthfully');
setup(fixtures.three);
const changed=fixtures.adjusted;
state.decision=changed.decision;state.selection=changed.selection;state.modelIdentity=changed.model_identity;state.writerStale=true;
renderDecision(state.decision);
assert($('ranking').children.map(c=>c.dataset.modelId).join(',')==='a,d,c','New alpha refreshes all roles from the actual deterministic engine');
assert(JSON.stringify(Object.keys(state.decision.candidates))===JSON.stringify(Object.keys(state.original.decision.candidates)),'Recalculation preserves the source universe');
assert($('writer-stale').textContent.includes('has not been regenerated'),'Old explanation is marked stale');
$('ranking-scope').value='original';recommendationViews().renderRawRanking();
const originalText=$('raw-ranking').textContent;
assert(originalText.includes('Original analysis') && originalText.includes('General 50%'),'Original weights retained');
const rawRows=all($('raw-ranking'),n=>n.className==='raw-ranking-row');
assert(rawRows.slice(0,3).map(n=>n.children[1].textContent).join(',')===['a','b','c'].map(id=>fixtures.three.decision.candidates[id].name).join(','),'Original raw order is not canonical a,c,d order');
rawRows[0].children[1].listeners.click();
assert($('drawer-content').textContent.includes('Original analysis values'),'Original detail drawer uses original evidence/weights');
assert(JSON.stringify(fixtures)===before,'Presentation never mutates original results');
print('Recommendation view checks passed');
