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
for(const [name,expected] of [['one','a'],['two','a'],['three','a'],['partial','a'],['zero',null],['failure',null],['legacy',null]]){
 setup(fixtures[name]);renderDecision(state.decision);
 const children=$('ranking').children;
 assert(children.length===1,`${name}: one recommendation or one compact message`);
 assert(Number($('ranking').dataset.count)===(expected ? 1 : 0),`${name}: no invented choice`);
 if(expected) assert(children[0].dataset.role==='best_overall' && children[0].dataset.modelId===expected,`${name}: only Best Overall is displayed`);
 else assert(children[0].tagName==='p' && children[0].className==='recommendation-empty',`${name}: no empty recommendation cards`);
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
const bestCard=$('ranking').children[0];
assert($('ranking').textContent.includes('Eligible') && $('ranking').textContent.includes('Decision score S'),'Best Overall retains the score and eligibility');
assert(all(bestCard,n=>n.className==='metric-item').length===4,'Best Overall keeps G/U/O and eligibility in one summary strip');
assert(all(bestCard,n=>n.className==='best-label')[0].textContent==='BEST OVERALL','Compact header identifies the recommendation role');
assert(all(bestCard,n=>n.className==='best-highlights')[0].children.length===3,'Only existing cost and performance evidence supplies highlights');
assert(all(bestCard,n=>n.className==='best-highlights')[0].textContent.includes('$100') && all(bestCard,n=>n.className==='best-highlights')[0].textContent.includes('Mean TTFT: 1 s'),'Cost and mean metrics retain their source values and units');
all(bestCard,n=>n.tagName==='button' && n.textContent.startsWith('View model details'))[0].listeners.click();
const identifiers=JSON.parse(all($('drawer-content'),n=>n.tagName==='pre')[0].textContent);
assert($('model-drawer').open && identifiers.aa_model_id==='a','Best Overall navigation opens the selected model');
assert(JSON.stringify(identifiers.evidence_ids)===JSON.stringify(state.decision.candidates.a.evidence_ids),'Model drawer preserves exact evidence IDs');
$('model-drawer').close();
clearSelection();
const bestControl=all(bestCard,n=>n.dataset.modelSelect==='a')[0];
bestControl.checked=true;bestControl.listeners.change();
const otherControl=all($('candidate-groups'),n=>n.dataset.modelSelect==='c')[0];
otherControl.checked=true;otherControl.listeners.change();
$('compare-panel').hidden=false;renderComparison();
assert($('comparison-table').textContent.includes(state.decision.candidates.a.name) && $('comparison-table').textContent.includes(state.decision.candidates.c.name),'Best Overall and another ranked model can still be compared');
clearSelection();
assert($('ranking').textContent.includes('Creator: Synthetic creator A'),'Creator comes from identity metadata');
assert($('ranking').textContent.includes('Synthetic fa'),'Family label comes from reviewed metadata');
assert($('ranking').textContent.includes('Raw rank 1'),'Best Overall shows the backend rank');
assert($('ranking').textContent.includes('Highest-ranked qualified model'),'Selection reason is explained');
const configs=all($('ranking').children[0],n=>n.className==='configuration-row');
assert(configs.length===1 && configs[0].textContent.includes('(b)'),'Only backend-defined other family members expand');
assert(all($('ranking'),n=>n.className==='family-configurations').length===1,'No zero-member family controls');
openModel('c');
assert(all($('drawer-content'),n=>n.className==='family-configurations').length===0,'Zero-member families do not create empty drawer expanders either');
$('model-drawer').open=false;
assert(all($('ranking'),n=>n.className==='rationale').length===0,'Generic task caveats are not repeated on cards');
assert(all($('ranking'),n=>n.className==='card-evidence-details').length===1 && all($('ranking'),n=>n.className==='card-evidence-details').every(n=>!n.open),'Card facts and operational detail are progressively disclosed');
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
setup(fixtures.zero);renderDecision(state.decision);
assert($('ranking').textContent.includes('No eligible model has a complete decision score'),'Missing Best Overall is explained');
setup(fixtures.one);renderDecision(state.decision);
assert(!all($('ranking'),n=>n.className.startsWith('badge') && n.textContent==='Family unknown').length,'Unknown family does not become a prominent recommendation badge');
assert(all($('ranking'),n=>n.className==='card-evidence-details')[0].textContent.includes('Family unknown'),'Family uncertainty remains accessible in technical detail');
setup(fixtures.two);renderDecision(state.decision);
assert($('ranking').textContent.includes('Monthly cost not estimated'),'Missing price/workload stays unknown');
assert(!all($('ranking'),n=>n.className==='best-highlights')[0].textContent.includes('monthly'),'O=0 never creates a zero-cost highlight');
const missingMetrics=JSON.parse(JSON.stringify(fixtures.three));
missingMetrics.decision.candidates.a.evidence_ids=missingMetrics.decision.candidates.a.evidence_ids.filter(id=>!['derived','artificial_analysis'].includes(missingMetrics.decision.evidence[id].source_type) || missingMetrics.decision.evidence[id].metric.startsWith('evaluations.'));
setup(missingMetrics);renderDecision(state.decision);
assert(all($('ranking'),n=>n.className==='best-highlights').length===0,'No empty highlights or invented measurements when operational evidence is absent');
const noPrice=JSON.parse(JSON.stringify(fixtures.three));
noPrice.decision.candidates.a.evidence_ids=noPrice.decision.candidates.a.evidence_ids.filter(id=>noPrice.decision.evidence[id].metric!=='pricing.price_1m_output_tokens');
setup(noPrice);renderDecision(state.decision);
assert(!all($('ranking'),n=>n.className==='best-highlights')[0].textContent.includes('monthly'),'A derived cost alone cannot supply a highlight without both prices');
const noWorkload=JSON.parse(JSON.stringify(fixtures.three));delete noWorkload.decision.candidates.a.workload;
setup(noWorkload);renderDecision(state.decision);
assert(!all($('ranking'),n=>n.className==='best-highlights')[0].textContent.includes('monthly'),'Monthly cost highlight requires recorded workload');
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
assert($('ranking').children[0].dataset.modelId==='d','New alpha updates Best Overall from the actual deterministic engine');
assert($('raw-ranking').textContent.includes('General 70%'),'Current ranking displays the adjusted weights');
assert(JSON.stringify(Object.keys(state.decision.candidates))===JSON.stringify(Object.keys(state.original.decision.candidates)),'Recalculation preserves the source universe');
assert($('writer-stale').textContent.includes('has not been regenerated'),'Old explanation is marked stale');
$('ranking-scope').value='original';recommendationViews().renderRawRanking();
const originalText=$('raw-ranking').textContent;
assert(originalText.includes('Original analysis') && originalText.includes('General 50%'),'Original weights retained');
const rawRows=all($('raw-ranking'),n=>n.className==='raw-ranking-row');
assert(rawRows.slice(0,3).map(n=>n.children[1].textContent).join(',')===['a','b','c'].map(id=>fixtures.three.decision.candidates[id].name).join(','),'Original raw ranking preserves backend order');
rawRows[0].children[1].listeners.click();
assert($('drawer-content').textContent.includes('Original analysis values'),'Original detail drawer uses original evidence/weights');
assert(JSON.stringify(fixtures)===before,'Presentation never mutates original results');
print('Recommendation view checks passed');
