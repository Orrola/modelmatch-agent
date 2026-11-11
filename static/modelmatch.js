/* ModelMatch UI: transport, presentation, and interaction stay separate from scoring. */
const $ = id => document.getElementById(id);
const labels = {fully_evaluable: 'Fully evaluable', provisional: 'Provisional', unverified: 'Unverified', ineligible: 'Ineligible'};
const stageNames = {lead: 'Lead', A: 'Researcher A', B: 'Researcher B', C: 'Researcher C', review: 'Evidence Review', decision: 'Decision', writer: 'Writer'};
const stageStates = {pending: 'Pending', running: 'Running', completed: 'Completed', failed: 'Failed', skipped: 'Not reached', interrupted: 'Stopped'};
const state = {
  view: 'overview', busy: false, mode: null, original: null, decision: null, analysisId: null,
  controller: null, generation: 0, stages: new Map(), traces: new Map(), activity: [],
  selected: new Set(), drawerId: null, drawerFocus: null, evidenceLimit: 40,
  weightSerial: 0, weightTimer: null, weightController: null, writerStale: false,
};

// Presentation helpers never normalize indices or calculate decision scores.
function el(tag, className = '', content = null) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== null) node.textContent = String(content);
  return node;
}
function text(id, content) { $(id).textContent = content; }
function pretty(value) { return String(value || 'Not specified').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); }
function number(value) { return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('en-US', {maximumFractionDigits: 2}) : 'Unknown'; }
function percent(alpha) { return `${Math.round(alpha * 100)}%`; }
function dateLabel(value) {
  if (!value) return 'Timestamp not supplied';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Timestamp unverified' : date.toLocaleString('en-US', {dateStyle: 'medium', timeStyle: 'short'});
}
function safeLink(url) {
  try { const u = new URL(url); return u.protocol === 'https:' && !u.username && !u.password ? u.href : null; }
  catch { return null; }
}
function link(url, caption) {
  const href = safeLink(url);
  if (!href) return el('span', 'field-help', 'Source unavailable');
  const a = el('a', '', caption); a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
}
function button(caption, action, className = 'text-button') {
  const b = el('button', className, caption); b.type = 'button'; b.addEventListener('click', action); return b;
}
function badge(caption, type = 'neutral') { return el('span', `badge ${type}`, caption); }
function statusBadge(candidate) {
  const tones = {fully_evaluable: 'good', provisional: 'warning', unverified: 'warning', ineligible: 'bad'};
  return badge(labels[candidate.candidate_status] || 'Unknown', tones[candidate.candidate_status]);
}
function metricLabel(metric) {
  const exact = {monthly_cost_usd: 'Monthly cost', context_window: 'Combined context', max_input_tokens: 'Input token limit', max_output_tokens: 'Output token limit', ttft: 'Mean time to first token', output_speed: 'Mean output speed', deployment: 'Deployment', data_residency: 'Data residency'};
  if (exact[metric]) return exact[metric];
  if (metric.includes('intelligence_index')) return 'General Intelligence Index';
  if (metric.includes('price_1m_input')) return 'Input price per 1M tokens';
  if (metric.includes('price_1m_output')) return 'Output price per 1M tokens';
  if (metric.includes('mean_time_to_first')) return 'Mean time to first token';
  if (metric.includes('mean_output_tokens')) return 'Mean output speed';
  return pretty(metric.split('.').pop().replace('artificial_analysis_', '').replace('_index', ' index'));
}
function reasonLabel(reason) {
  if (['value_null', 'field_absent'].includes(reason)) return 'Not available in the AA snapshot';
  if (String(reason).includes('official_verification')) return 'Official specification has not been verified';
  if (reason === 'missing_grounding_citations') return 'Official source citations are unavailable';
  if (reason === 'no_supported_relevant_index') return 'No supported Capability Index for this task';
  return String(reason || 'Evidence has not been verified').replace(/_/g, ' ');
}
function providerName(candidate) {
  const provider = candidate.provider || candidate.model_creator;
  return typeof provider === 'string' ? provider : provider?.name || null;
}
function missingFor(id, decision = state.decision) { return (decision?.missing_manifest || []).find(m => m.model_id === id)?.missing_fields || []; }
function evidenceFor(candidate, decision = state.decision) { return (candidate.evidence_ids || []).map(id => decision.evidence[id]).filter(Boolean); }
function monthlyCost(candidate) { return typeof candidate.estimated_monthly_cost_usd === 'number' ? `$${number(candidate.estimated_monthly_cost_usd)}` : 'Not estimated'; }
function rationale(candidate, decision = state.decision) {
  if (candidate.eligibility === 'ineligible') return 'A supplied hard requirement is not satisfied. Inspect the constraint checks before considering this model.';
  if (candidate.eligibility === 'unverified') return 'A hard requirement cannot be verified with the available evidence. This model is not a confirmed recommendation.';
  if (candidate.G == null || candidate.U == null) return 'A required index is unavailable. A reliable numeric comparison cannot be completed.';
  const relevance = decision.relevance.match_status === 'strong' ? 'The selected Capability Index is closely aligned with this task.' : 'The Capability Index is a partial proxy for this task; validate its fit on representative work.';
  return relevance + (typeof candidate.O === 'number' && candidate.O < 0 ? ` Stated operational targets deduct ${number(-candidate.O)} points.` : ' Review the operational tradeoffs before a pilot.');
}
function sourceCategory(evidence, decision = state.decision) {
  if (decision?.data_mode === 'mock') return {label: 'Synthetic fixture', tone: 'warning'};
  if (evidence.source_type === 'official_docs' && evidence.verification_status === 'verified') return {label: 'Verified official source', tone: 'good'};
  if (evidence.evidence_status !== 'observed') return {label: 'Unknown', tone: 'warning'};
  if (evidence.source_type === 'artificial_analysis') return {label: 'AA measurement', tone: 'neutral'};
  if (evidence.source_type === 'derived') return {label: 'Calculated from evidence', tone: 'neutral'};
  return {label: 'Unverified source', tone: 'warning'};
}
function setStatus(message, error = false) {
  $('status-banner').hidden = false; $('status-banner').className = `status-banner${error ? ' error' : ''}`; text('status', message);
}
function navigate(view, focus = false) {
  if (!['overview', 'comparison', 'evidence'].includes(view)) view = 'overview';
  state.view = view;
  for (const name of ['overview', 'comparison', 'evidence']) $(`view-${name}`).hidden = name !== view;
  document.querySelectorAll('.nav-item').forEach(b => {
    const active = b.dataset.view === view; b.className = `nav-item${active ? ' active' : ''}`;
    if (active) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  text('view-name', pretty(view));
  if (window.location.hash !== `#${view}`) window.history.replaceState(null, '', `#${view}`);
  if (focus) { $('main').focus({preventScroll: true}); window.scrollTo({top: 0, behavior: 'instant'}); }
}

// Workflow state is observation-based; pending stages become skipped only at termination.
function resetProgress() {
  state.stages = new Map(Object.keys(stageNames).map(key => [key, 'pending'])); renderProgress();
}
function progress(agent, status, stage = '') {
  const key = stage === 'review' || stage === 'review_final' ? 'review'
    : /^Researcher ([ABC])/.exec(agent)?.[1] || (agent === 'Decision Tool' ? 'decision' : agent === 'Writer' ? 'writer' : agent === 'Lead' ? 'lead' : null);
  if (!key) return;
  const normalized = status === 'cancelled' ? 'interrupted' : status;
  if (stageStates[normalized]) state.stages.set(key, normalized);
  renderProgress();
}
function nodeState(key) { return el('span', 'node-state', stageStates[state.stages.get(key)] || 'Pending'); }
function renderProgress() {
  const nodes = [];
  for (const key of ['lead', 'research', 'review', 'decision', 'writer']) {
    const node = el('div', `workflow-node ${state.stages.get(key) || ''}`);
    node.append(el('h3', '', key === 'research' ? 'Researchers' : stageNames[key]));
    if (key === 'research') {
      node.append(el('p', 'node-subtitle', 'Independent research tracks'));
      const tracks = el('div', 'research-tracks');
      for (const [role, label] of [['A', 'General intelligence'], ['B', 'Use-case fit'], ['C', 'Operational fit']]) {
        const track = el('div', `research-track ${state.stages.get(role)}`);
        track.append(el('strong', '', `${role} · ${label}`), nodeState(role)); tracks.append(track);
      }
      node.append(tracks);
    } else {
      node.append(el('p', 'node-subtitle', {lead: 'Interpret requirements', review: 'Same Lead, evidence check', decision: 'Deterministic ranking', writer: 'Grounded recommendation'}[key]), nodeState(key));
    }
    nodes.push(node);
  }
  $('progress').replaceChildren(...nodes);
}
function observedParallel(trace) {
  const starts = trace.filter(e => e.type === 'researcher_start' && e.round_number === 0);
  const ends = starts.map(s => trace.find(e => e.type === 'researcher_end' && e.context_id === s.context_id));
  return starts.length === 3 && new Set(starts.map(s => s.role)).size === 3 && ends.every(Boolean)
    && starts.every(s => typeof s.monotonic === 'number') && ends.every(e => typeof e.monotonic === 'number')
    && Math.max(...starts.map(e => e.monotonic)) < Math.min(...ends.map(e => e.monotonic));
}
function finishProgress(result = null, stopped = false) {
  for (const e of result?.trace || []) {
    if (e.type === 'researcher_end') progress(`Researcher ${e.role}`, e.status);
    if (e.type === 'lead_stage_completed') progress('Lead', 'completed', e.stage);
    if (e.type === 'decision_completed') progress('Decision Tool', 'completed');
  }
  if (result && 'writer_fallback' in result) progress('Writer', result.writer_fallback ? 'failed' : 'completed');
  for (const [key, value] of state.stages) {
    if (value === 'running') state.stages.set(key, stopped ? 'interrupted' : 'failed');
    if (value === 'pending') state.stages.set(key, 'skipped');
  }
  renderProgress();
  const parallel = result && observedParallel(result.trace || []);
  text('workflow-status', stopped ? 'Stopped' : parallel ? 'Parallel execution observed' : result?.status === 'clarification_needed' ? 'Awaiting clarification' : result?.decision ? 'Research complete' : 'Did not complete');
}
function addActivity(agent, message) {
  state.activity.push({agent, message});
  $('activity').replaceChildren(...state.activity.slice(-60).map(a => { const li = el('li'); li.append(el('strong', '', a.agent), el('span', '', ` · ${a.message}`)); return li; }));
}

// Requirement interpretation is a readable summary, with the original record kept in Technical Details.
function renderPlan(plan) {
  $('interpretation').hidden = false;
  const grid = el('dl', 'plan-grid');
  for (const [label, value] of [['Industry', plan.industry || 'Not specified'], ['Task type', pretty(plan.task_type)]]) {
    const item = el('div', 'plan-item'); item.append(el('dt', '', label), el('dd', '', value)); grid.append(item);
  }
  const chips = el('div', 'constraint-list');
  for (const c of plan.constraints || []) {
    const chip = el('div', `constraint-chip${c.hard ? ' hard' : ''}`);
    chip.append(el('strong', '', c.hard ? 'Hard requirement' : 'Soft preference'), el('span', '', `${metricLabel(c.metric)}: ${c.target == null ? 'No numeric target' : c.target}${c.statistic ? ` (${c.statistic})` : ''}`)); chips.append(chip);
  }
  const workload = Object.entries(plan.workload || {}).filter(([, v]) => v?.value != null).map(([key, v]) => `${pretty(key)}: ${number(v.value)}`);
  $('plan').replaceChildren(el('p', 'plan-task', plan.task_description || 'A concrete task is still needed.'), grid, chips,
    el('p', 'field-help', workload.length ? workload.join(' · ') : 'No workload supplied. Monthly cost cannot be estimated without workload and pricing.'));
}

// Comparison components only display the decision returned by the existing engine.
function selectionControl(candidate) {
  const label = el('label', 'select-model'), input = el('input'); input.type = 'checkbox'; input.dataset.modelSelect = candidate.model_id;
  input.checked = state.selected.has(candidate.model_id); input.setAttribute('aria-label', `Compare ${candidate.name}`);
  input.addEventListener('change', () => toggleSelection(candidate.model_id, input.checked));
  label.append(input, el('span', '', 'Compare')); return label;
}
function modelTitle(candidate) { return button(candidate.name, () => openModel(candidate.model_id), 'model-title'); }
function renderCard(candidate, index) {
  const card = el('article', 'model-card'); card.dataset.modelId = candidate.model_id;
  const top = el('div', 'card-topline'); top.append(el('span', 'rank-tag', `SHORTLIST ${String(index + 1).padStart(2, '0')}`), statusBadge(candidate));
  card.append(top, modelTitle(candidate));
  if (providerName(candidate)) card.append(el('p', 'provider-name', providerName(candidate)));
  const score = el('div', 'score-block'), caption = el('span', 'score-caption', 'Decision score S'); caption.append(el('span', '', 'Custom policy points'));
  score.append(el('strong', candidate.S == null ? 'score-number value-unknown' : 'score-number', number(candidate.S)), caption);
  const metrics = el('div', 'metric-strip');
  for (const [key, label] of [['G', 'General index'], ['U', 'Use-case index'], ['O', 'Operational adj.']]) {
    const item = el('div', 'metric-item'); item.append(el('span', '', label), el('strong', candidate[key] == null ? 'value-unknown' : '', number(candidate[key]))); metrics.append(item);
  }
  const signals = el('div', 'model-signals'); signals.append(badge(pretty(candidate.eligibility), candidate.eligibility === 'eligible' ? 'good' : 'warning'));
  const gaps = missingFor(candidate.model_id);
  if (gaps.length) signals.append(el('span', 'missing-signal', `${gaps.length} unavailable ${gaps.length === 1 ? 'metric' : 'metrics'}`));
  const actions = el('div', 'card-actions'); actions.append(button('View model details ↗', () => openModel(candidate.model_id)), selectionControl(candidate));
  card.append(score, metrics, el('p', 'rationale', rationale(candidate)), signals);
  if (typeof candidate.estimated_monthly_cost_usd === 'number') {
    const cost = el('p', 'cost-label'); cost.append(el('strong', '', monthlyCost(candidate)), el('span', '', ' estimated / month')); card.append(cost);
  }
  card.append(actions); return card;
}
function renderGroups(topIds) {
  const groups = [];
  for (const [status, label] of Object.entries(labels)) {
    const all = Object.values(state.decision.candidates).filter(c => c.candidate_status === status);
    const others = all.filter(c => !topIds.has(c.model_id));
    const group = el('details', 'candidate-group'); group.dataset.status = status;
    const summary = el('summary'); summary.append(el('span', '', topIds.size && all.length !== others.length ? `Other ${label.toLowerCase()} candidates` : label), el('span', 'group-count', others.length), el('span', 'chevron', '⌄'));
    group.append(summary);
    for (const candidate of others) {
      const row = el('div', 'candidate-row'), selection = selectionControl(candidate);
      // Compact rows use an accessible checkbox without duplicating its visible label.
      selection.lastChild.hidden = true;
      const name = el('div'); name.append(modelTitle(candidate), el('p', 'row-description', candidate.S == null ? 'Score unavailable — inspect missing evidence' : `${number(candidate.G)} G · ${number(candidate.U)} U · ${number(candidate.O)} O`));
      row.append(selection, name, statusBadge(candidate), el('strong', candidate.S == null ? 'row-score value-unknown' : 'row-score', number(candidate.S))); group.append(row);
    }
    if (!others.length) group.append(el('p', 'group-empty', all.length ? 'All models in this category are shown in the shortlist above.' : 'No candidates in this category.'));
    groups.push(group);
  }
  $('candidate-groups').replaceChildren(...groups);
}
function updateWeightLabels(alpha) {
  text('alpha-value', percent(alpha)); text('use-case-value', percent(1 - alpha));
  $('alpha').value = alpha; $('alpha').style.setProperty('--alpha-fill', percent(alpha));
  $('alpha').setAttribute('aria-valuetext', `${percent(alpha)} general intelligence, ${percent(1 - alpha)} use-case fit`);
}
function renderDecision(decision) {
  state.decision = decision;
  $('results').hidden = false; $('comparison-empty').hidden = true;
  updateWeightLabels(decision.weights.alpha);
  $('alpha').disabled = $('reset').disabled = !state.analysisId || state.busy;
  text('weight-source', `${pretty(decision.weights.task_type)} · Suggested ${percent(decision.weights.suggested_alpha)} General / ${percent(1 - decision.weights.suggested_alpha)} Use-case.`);
  text('weight-mode', decision.weights.weight_mode === 'user_override' ? 'Custom weights' : 'Task default');
  text('data-label', decision.data_mode === 'mock' ? 'SYNTHETIC DEMO · Fictional models and scores. Not real AA evaluations or purchasing advice.' : decision.catalog_complete ? 'Artificial Analysis evidence · Results are conditional on your requirements and available evidence.' : 'Limited catalog coverage · This shortlist is provisional and does not represent a complete market comparison.');
  const ranking = decision.rankings.fully_evaluable.length ? decision.rankings.fully_evaluable : decision.rankings.provisional;
  const top = ranking.slice(0, 3).map(r => decision.candidates[r.model_id]);
  text('ranking-title', top.length ? decision.rankings.fully_evaluable.length ? 'Your recommended shortlist' : 'Your provisional shortlist' : 'No supported numeric shortlist');
  text('ranking-subtitle', top.length ? `Up to three models ranked under your selected weights. Select models to compare side by side.` : 'Required evidence is missing or eligibility is unresolved. Inspect candidates below.');
  text('result-status', top.length ? decision.rankings.fully_evaluable.length && decision.catalog_complete ? 'Evidence supported' : 'Provisional' : 'Further validation needed');
  $('ranking').replaceChildren(...top.map(renderCard));
  $('ranking').dataset.count = top.length;
  const counts = decision.counts_before_shortlist;
  text('counts', `${counts.total} candidates before shortlist limits · ${counts.fully_evaluable} fully evaluable · ${counts.provisional} provisional · ${counts.unverified} unverified · ${counts.ineligible} ineligible`);
  renderGroups(new Set(top.map(c => c.model_id)));
  $('comparison-count').hidden = false; text('comparison-count', counts.total);
  state.selected = new Set([...state.selected].filter(id => decision.candidates[id]));
  updateSelection(); renderEvidence(); renderWriterNote();
  if (state.drawerId && $('model-drawer').open) renderDrawer(state.drawerId);
}
function toggleSelection(id, checked) {
  if (checked && !state.selected.has(id) && state.selected.size >= 3) {
    text('announcement', 'You can compare up to three models. Remove one before adding another.');
    setStatus('Select up to three models. Remove one to compare a different model.');
  } else if (checked) state.selected.add(id); else state.selected.delete(id);
  updateSelection();
}
function updateSelection() {
  document.querySelectorAll('[data-model-select]').forEach(input => { input.checked = state.selected.has(input.dataset.modelSelect); });
  $('compare-bar').hidden = !state.selected.size; text('selected-count', state.selected.size);
  $('show-comparison').disabled = state.selected.size < 2;
  if (!$('compare-panel').hidden) renderComparison();
}
function clearSelection() { state.selected.clear(); $('compare-panel').hidden = true; updateSelection(); }
function renderComparison() {
  if (state.selected.size < 2) { $('compare-panel').hidden = true; return; }
  const candidates = [...state.selected].map(id => state.decision.candidates[id]), table = el('table', 'compare-table');
  const caption = el('caption', 'sr-only', 'Selected models compared under the current weights'); table.append(caption);
  const head = el('thead'), header = el('tr'); header.append(el('th', '', 'Measure'));
  for (const c of candidates) { const th = el('th'); th.scope = 'col'; th.append(modelTitle(c)); header.append(th); } head.append(header); table.append(head);
  const body = el('tbody');
  const rows = [['Decision score S', c => number(c.S)], ['General Index G', c => number(c.G)], ['Use-case Index U', c => number(c.U)], ['Operational adjustment O', c => number(c.O)], ['Monthly estimate', c => monthlyCost(c)], ['Candidate status', c => labels[c.candidate_status]], ['Eligibility', c => pretty(c.eligibility)], ['Unavailable metrics', c => String(missingFor(c.model_id).length)]];
  for (const [label, value] of rows) { const tr = el('tr'); tr.append(el('td', '', label)); for (const c of candidates) tr.append(el('td', '', value(c))); body.append(tr); }
  table.append(body); $('comparison-table').replaceChildren(table);
}
function renderWriterNote() {
  if (!state.original?.decision) return;
  const originalAlpha = state.original.decision.weights.alpha;
  $('writer-stale').className = `writer-note${state.writerStale ? ' adjusted' : ''}`;
  $('writer-stale').replaceChildren(el('span', '', state.writerStale
    ? `Adjusted ranking · The original Writer report still describes ${percent(originalAlpha)} General / ${percent(1 - originalAlpha)} Use-case. Its explanation has not been regenerated.`
    : `Original analysis · Writer report at ${percent(originalAlpha)} General / ${percent(1 - originalAlpha)} Use-case.`),
    button('View original analysis →', () => { navigate('evidence', true); $('writer-report').open = true; $('writer-report').scrollIntoView({block: 'start'}); }));
}

// Evidence and model details keep record identifiers and JSON behind Technical Details.
function renderEvidence() {
  const d = state.decision;
  if (!d) return;
  $('evidence-empty').hidden = true; $('evidence-results').hidden = false;
  const records = Object.values(d.evidence), synthetic = d.data_mode === 'mock';
  const official = records.filter(e => !synthetic && e.source_type === 'official_docs' && e.verification_status === 'verified').length;
  $('evidence-stats').replaceChildren(...[[records.length, synthetic ? 'Synthetic evidence records' : 'Evidence records'], [official, 'Verified official specifications'], [records.filter(e => e.evidence_status !== 'observed').length, 'Unavailable measurements']].map(([value, label]) => { const box = el('div', 'stat-card'); box.append(el('strong', '', value), el('span', '', label)); return box; }));
  text('snapshot', `${synthetic ? 'Synthetic snapshot' : 'AA snapshot'} · ${dateLabel(d.retrieved_at)}. ${d.catalog_complete ? 'Complete supplied catalog.' : 'Catalog coverage is limited.'}`);
  text('relevance', `Use-case relevance: ${pretty(d.relevance.match_status)}. ${d.relevance.rationale}`);
  text('evidence-mode', synthetic ? 'Synthetic demo' : 'AA snapshot');
  renderEvidenceRows();
  const steps = el('ul', 'validation-list');
  for (const line of ['Pilot the shortlist on representative internal tasks and evaluate factual reliability.', 'Verify context, deployment, privacy, and data residency against exact official model versions.', 'Measure workload-specific cost, mean performance, and tail latency before production.']) steps.append(el('li', '', line));
  $('validation-steps').replaceChildren(steps);
  const gaps = (d.missing_manifest || []).filter(m => m.missing_fields.length);
  $('missing').replaceChildren(...gaps.map(m => {
    const row = el('div', 'missing-model'), candidate = d.candidates[m.model_id];
    row.append(el('strong', '', candidate?.name || 'Model not identified'), el('p', '', m.missing_fields.map(f => `${metricLabel(f.metric)}: ${reasonLabel(f.reason)}${f.required ? ' (required)' : ' (not required for this request)'}`).join(' · '))); return row;
  }));
  if (!gaps.length) $('missing').append(el('p', 'field-help', 'No missing metrics recorded for this candidate set. This does not establish production readiness.'));
  renderOriginalSummary(); renderTechnical();
}
function renderEvidenceRows() {
  if (!state.decision) return;
  const d = state.decision, search = $('evidence-search').value.trim().toLowerCase();
  const records = Object.values(d.evidence).filter(e => `${d.candidates[e.model_id]?.name || ''} ${e.model_id} ${metricLabel(e.metric)}`.toLowerCase().includes(search));
  text('evidence-count', `${records.length} matching records. Index versions are retained per measurement.`);
  $('evidence').replaceChildren(...records.slice(0, state.evidenceLimit).map(e => {
    const row = el('div', 'evidence-row'), model = el('div'); model.append(el('h3', '', d.candidates[e.model_id]?.name || 'Model not identified'), el('p', '', metricLabel(e.metric)));
    const value = el('div', e.value == null ? 'evidence-value value-unknown' : 'evidence-value', `${typeof e.value === 'number' ? number(e.value) : e.value || 'Unknown'}${e.value == null ? '' : ` ${e.unit || ''}`}`);
    value.append(el('small', '', e.reason ? reasonLabel(e.reason) : `Index version: ${e.index_version ?? 'not supplied'}${e.statistic ? ` · ${e.statistic}` : ''}`));
    const source = el('div', 'evidence-source'), category = sourceCategory(e); source.append(badge(category.label, category.tone));
    if (safeLink(e.source_url)) source.append(link(e.source_url, d.data_mode === 'mock' ? 'API reference only ↗' : 'Source ↗'));
    row.append(model, value, source); return row;
  }));
  if (!records.length) $('evidence').append(el('p', 'field-help', 'No evidence matches this search.'));
  $('more-evidence').hidden = records.length <= state.evidenceLimit;
}
function renderOriginalSummary() {
  const original = state.original?.decision;
  if (!original) return;
  text('report-note', `Original weights: ${percent(original.weights.alpha)} General / ${percent(1 - original.weights.alpha)} Use-case. This summary remains tied to the original analysis. The complete, unchanged Writer report is in Technical Details.`);
  const ranking = original.rankings.fully_evaluable.length ? original.rankings.fully_evaluable : original.rankings.provisional;
  const list = el('ul');
  for (const row of ranking.slice(0, 3)) list.append(el('li', '', `${original.candidates[row.model_id].name} — original decision score ${number(row.S)}`));
  $('report').replaceChildren(el('p', '', ranking.length ? 'Original shortlist, before any weight adjustments:' : 'The original analysis did not support a numeric shortlist.'), list,
    el('p', '', state.original.writer_fallback ? 'The live Writer output was unavailable or rejected. The backend supplied a deterministic fallback report.' : 'The Writer output passed the backend ranking and evidence checks.'));
}
function renderTechnical() {
  if (!$('technical-details').open) return;
  text('technical-data', state.decision ? JSON.stringify(state.decision, null, 2) : 'No decision records available.');
  text('technical-plan', JSON.stringify(state.original?.plan || {}, null, 2));
  text('technical-events', JSON.stringify(state.original?.trace || [], null, 2));
  renderTraces();
  if (!$('original-writer-text')) {
    const detail = el('details'), summary = el('summary', '', 'Complete original Writer report'), pre = el('pre'); pre.id = 'original-writer-text'; detail.append(summary, pre); $('technical-details').append(detail);
  }
  text('original-writer-text', state.original?.markdown || 'No Writer report available.');
}
function renderTraces() {
  if (!$('technical-details').open) return;
  $('traces').replaceChildren(...[...state.traces.values()].map(call => {
    const detail = el('details', 'trace-item'), summary = el('summary');
    summary.append(el('span', '', `${call.agent} → ${pretty(call.tool)}`), badge(pretty(call.status), call.status === 'failed' ? 'bad' : 'neutral'));
    detail.append(summary, el('pre', '', JSON.stringify(call, null, 2))); return detail;
  }));
}
function drawerSection(title, ...children) { const section = el('section', 'drawer-section'); section.append(el('h3', '', title), ...children); return section; }
function renderDrawer(id) {
  const c = state.decision?.candidates[id];
  if (!c) return;
  const title = el('h2', '', c.name); title.id = 'drawer-title';
  const children = [title];
  if (providerName(c)) children.push(el('p', 'provider-name', providerName(c)));
  const statuses = el('div', 'drawer-status'); statuses.append(statusBadge(c), badge(pretty(c.eligibility), c.eligibility === 'eligible' ? 'good' : 'warning')); children.push(statuses);
  const scores = el('div', 'drawer-scores');
  for (const [key, label] of [['S', 'Decision S'], ['G', 'General G'], ['U', 'Use-case U'], ['O', 'Adjustment O']]) { const cell = el('div'); cell.append(el('span', '', label), el('strong', c[key] == null ? 'value-unknown' : '', number(c[key]))); scores.append(cell); }
  children.push(scores, el('p', 'field-help', `Current weights: ${percent(state.decision.weights.alpha)} General / ${percent(1 - state.decision.weights.alpha)} Use-case. Scores are custom policy points, not accuracy percentages.`));
  children.push(drawerSection('Why this model is here', el('p', '', rationale(c))));
  const tradeoffs = el('ul');
  for (const [name, p] of Object.entries(c.operational_penalties || {})) tradeoffs.append(el('li', '', `${pretty(name)}: ${p.deduction == null ? 'adjustment unknown' : `${number(p.deduction)} points`} — ${p.status === 'not_applicable' ? 'no applicable soft target supplied' : reasonLabel(p.reason || p.status)}.`));
  if (typeof c.estimated_monthly_cost_usd === 'number') tradeoffs.append(el('li', '', `Estimated monthly token cost: ${monthlyCost(c)}. Actual bills can differ.`));
  else tradeoffs.append(el('li', '', 'Monthly cost is not estimated without sufficient workload and input/output prices.'));
  for (const check of c.constraint_checks || []) tradeoffs.append(el('li', '', `${check.hard ? 'Hard requirement' : 'Preference'} — ${metricLabel(check.metric)}: ${pretty(check.state || 'unknown')}. ${check.reason ? reasonLabel(check.reason) : ''}`));
  for (const gap of missingFor(id)) tradeoffs.append(el('li', '', `${metricLabel(gap.metric)}: ${reasonLabel(gap.reason)}${gap.required ? ' — required evidence' : ' — optional for this request'}.`));
  children.push(drawerSection('Tradeoffs & missing information', tradeoffs));
  const sources = el('div');
  for (const evidence of evidenceFor(c)) {
    const row = el('div', 'drawer-evidence'), category = sourceCategory(evidence);
    row.append(el('h3', '', metricLabel(evidence.metric)), el('p', '', `${typeof evidence.value === 'number' ? number(evidence.value) : evidence.value || 'Unknown'} ${evidence.unit || ''}`), badge(category.label, category.tone),
      el('p', '', `${dateLabel(evidence.retrieved_at)} · Index version: ${evidence.index_version ?? 'not supplied'}${evidence.statistic ? ` · Statistic: ${evidence.statistic}` : ''}`));
    if (evidence.supporting_excerpt) row.append(el('p', '', `Source excerpt: “${evidence.supporting_excerpt}”`));
    if (safeLink(evidence.source_url)) row.append(link(evidence.source_url, state.decision.data_mode === 'mock' ? 'API reference — not a real evaluation ↗' : 'Open source ↗'));
    sources.append(row);
  }
  children.push(drawerSection('Evidence & sources', sources), drawerSection('Suggested pilot', el('p', '', 'Evaluate representative tasks, factual reliability, workload cost, and latency. Verify exact model-version context and deployment requirements before production.')));
  const technical = el('details', 'panel technical-panel'); technical.append(el('summary', '', 'Technical details'), el('pre', '', JSON.stringify({aa_model_id: id, snapshot_id: c.snapshot_id, evidence_ids: c.evidence_ids, constraint_checks: c.constraint_checks}, null, 2))); children.push(technical);
  children.push(button(state.selected.has(id) ? 'Remove from comparison' : 'Add to comparison', () => { toggleSelection(id, !state.selected.has(id)); renderDrawer(id); }, 'button button-secondary'));
  $('drawer-content').replaceChildren(...children);
}
function openModel(id) {
  state.drawerId = id; state.drawerFocus = document.activeElement; renderDrawer(id);
  const drawer = $('model-drawer'); if (!drawer.open) drawer.showModal(); $('close-drawer').focus();
}

// HTTP/SSE transport: no local scoring and no automatic research retries.
function apiError(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(e => `${pretty((e.loc || []).filter(x => x !== 'body').join(' '))}: ${e.msg || 'Check this field.'}`).join(' ');
  return 'The request could not complete. Please check your inputs.';
}
function analysisError(result) {
  const failed = (result.integration_usage?.records || []).find(record => record.status === 'failed');
  const category = failed?.error?.category;
  const messages = {
    authentication_failed: 'Vertex AI authentication failed. Refresh your existing Application Default Credentials (ADC).',
    permission_or_service_access_denied: 'Vertex AI access was denied. Check permissions for the configured Google Cloud project.',
    model_or_resource_not_found: 'The configured Gemini model is unavailable or inaccessible in this Vertex location.',
    quota_or_rate_limit: 'The provider quota or rate limit was reached. No automatic analysis retry was made.',
    request_timeout: 'A model request exceeded its time limit. The analysis did not complete.',
    execution_budget_exceeded: 'The analysis reached its request or prompt limit before it could complete.',
  };
  const codes = {
    snapshot_unavailable: 'The Artificial Analysis snapshot could not be loaded. Check AA_API_KEY, API access, and connectivity.',
    workflow_timeout: 'The analysis exceeded its overall time limit.',
    lead_output_contract_failed: 'The Lead returned an invalid structured response. The analysis stopped safely.',
    researcher_evidence_incomplete: 'A researcher could not collect sufficient evidence. No recommendation was produced.',
  };
  return `${messages[category] || codes[result.error] || 'The live analysis could not complete. Check the configured Vertex project, ADC credentials, and AA API access.'} No synthetic results were substituted.`;
}
async function api(path, body, signal) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal});
  if (!response.ok) { let error; try { error = await response.json(); } catch { error = {}; } throw new Error(apiError(error.detail)); }
  return response;
}
function decodeFrames(buffer) {
  buffer = buffer.replace(/\r\n/g, '\n'); const events = []; let index;
  while ((index = buffer.indexOf('\n\n')) >= 0) {
    const frame = buffer.slice(0, index); buffer = buffer.slice(index + 2);
    const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (data) events.push(JSON.parse(data));
  }
  return {events, buffer};
}
function handle(event) {
  if (event.type === 'stage') { progress(event.agent, event.status, event.stage); text('workflow-status', 'In progress'); }
  if (event.type === 'activity') addActivity(event.agent, event.text);
  if (event.type === 'interpretation') renderPlan(event.plan);
  if (event.type === 'tool_trace') { state.traces.set(event.call.call_id, event.call); renderTraces(); }
  if (event.type === 'error') throw new Error(event.message);
  if (event.type !== 'done') return;
  state.analysisId = event.analysis_id; state.original = event.result; state.writerStale = false;
  const result = event.result;
  if (result.plan) renderPlan(result.plan);
  for (const call of result.tool_calls || []) state.traces.set(call.call_id, call);
  finishProgress(result);
  if (result.decision) {
    renderDecision(result.decision); navigate('comparison', true);
    setStatus(result.writer_fallback ? 'Analysis completed with a deterministic fallback report. The Writer output was unavailable or rejected.' : 'Analysis complete. Compare models and inspect the evidence behind the ranking.');
  } else if (result.status === 'clarification_needed') {
    navigate('overview', true); $('clarification').hidden = false;
    $('questions').replaceChildren(...(result.questions || []).map(q => el('li', '', q)));
    setStatus('A required detail is missing. Add a clarification to continue.'); $('answer').focus();
  } else {
    setStatus(analysisError(result), true);
  }
  renderTechnical();
}
function formInput() {
  if (!['live_vertex', 'offline_synthetic'].includes(state.mode)) throw new Error('Execution mode is unavailable. Reload the page after checking the application server.');
  const form = $('requirements');
  const invalid = form.querySelector(':invalid');
  if (invalid) { if ($('advanced').contains(invalid)) $('advanced').open = true; form.reportValidity(); return null; }
  // Clicking Run analysis is the explicit live action; API callers must still opt in.
  const body = {question: $('question').value.trim(), approve_live: state.mode === 'live_vertex', hard_constraints: []};
  if (!body.question || body.question.length < 3) throw new Error('Describe a concrete task using at least three characters.');
  document.querySelectorAll('#requirements input[type=number]').forEach(input => {
    if (input.value !== '') { const value = Number(input.value); if (!Number.isFinite(value)) throw new Error('Use finite numbers for operational requirements.'); body[input.name] = value; }
  });
  document.querySelectorAll('input[name=hard]:checked').forEach(input => {
    if (!(input.value in body)) { $('advanced').open = true; throw new Error(`Enter a target before marking ${pretty(input.value)} as a hard requirement.`); }
    body.hard_constraints.push(input.value);
  });
  return body;
}
function invalidateWeights() {
  clearTimeout(state.weightTimer); state.weightSerial++; state.weightController?.abort();
}
async function analyze() {
  if (state.busy) return;
  let body;
  try { body = formInput(); if (!body) return; }
  catch (error) { $('form-error').hidden = false; text('form-error', error.message); return; }
  $('form-error').hidden = true; invalidateWeights();
  const generation = ++state.generation;
  state.busy = true; state.controller = new AbortController(); state.analysisId = null; state.original = null; state.decision = null;
  state.traces.clear(); state.activity = []; state.evidenceLimit = 40; state.selected.clear(); state.drawerId = null;
  if ($('model-drawer').open) $('model-drawer').close();
  $('results').hidden = true; $('comparison-empty').hidden = false; $('evidence-results').hidden = true; $('evidence-empty').hidden = false;
  $('compare-panel').hidden = true; updateSelection(); resetProgress(); $('clarification').hidden = true; $('interpretation').hidden = true;
  $('comparison-count').hidden = true; $('evidence-search').value = ''; $('activity').replaceChildren(el('li', '', 'Waiting for the Lead to begin.'));
  $('analyze').disabled = true; $('cancel').disabled = false; $('alpha').disabled = $('reset').disabled = true;
  setStatus('Interpreting your task and collecting evidence…'); text('workflow-status', 'Starting');
  let reader;
  try {
    const response = await api('/api/modelmatch/analyze', body, state.controller.signal);
    reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '', terminal = false;
    while (true) {
      const {value, done} = await reader.read(); buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
      const parsed = decodeFrames(buffer); buffer = parsed.buffer;
      for (const event of parsed.events) { if (generation !== state.generation) return; handle(event); if (event.type === 'done') terminal = true; }
      if (done) break;
    }
    if (!terminal) throw new Error('The connection ended before a final result. No completed analysis is available.');
  } catch (error) {
    if (generation !== state.generation) return;
    const stopped = error.name === 'AbortError';
    finishProgress(null, stopped); setStatus(stopped ? 'Analysis stopped. Unfinished stages did not complete.' : error.message, !stopped);
    addActivity('Application', stopped ? 'Stopped by the user.' : 'Connection or analysis failed. No automatic retry was made.');
  } finally {
    if (reader) { try { await reader.cancel(); } catch { /* The stream may already be closed. */ } reader.releaseLock(); }
    if (generation === state.generation) {
      state.busy = false; $('analyze').disabled = false; $('cancel').disabled = true;
      $('alpha').disabled = $('reset').disabled = !state.analysisId || !state.decision;
    }
  }
}
async function recalculate(alpha) {
  if (!state.analysisId || state.busy) return;
  clearTimeout(state.weightTimer); const serial = ++state.weightSerial, id = state.analysisId;
  state.weightController?.abort(); state.weightController = new AbortController();
  text('weight-status', 'Updating ranking…');
  try {
    const response = await api('/api/modelmatch/recalculate', {analysis_id: id, user_alpha: alpha}, state.weightController.signal);
    const result = await response.json();
    if (serial !== state.weightSerial || id !== state.analysisId) return;
    state.writerStale = result.writer_explanation_stale;
    renderDecision(result.decision); text('weight-status', 'Updated from existing evidence. No research rerun.');
    text('announcement', `Ranking updated. ${percent(result.decision.weights.alpha)} General, ${percent(1 - result.decision.weights.alpha)} Use-case.`);
  } catch (error) {
    if (serial !== state.weightSerial || error.name === 'AbortError') return;
    updateWeightLabels(state.decision.weights.alpha); text('weight-status', 'Update failed. Previous ranking retained.'); setStatus(error.message, true);
  }
}
function queueWeight(alpha) {
  invalidateWeights(); updateWeightLabels(alpha); text('weight-status', 'Updating ranking…');
  state.weightTimer = setTimeout(() => recalculate(alpha), 180);
}

// Bind controls once; result components attach their own scoped handlers.
function initialize() {
  document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => navigate(b.dataset.view, true)));
  window.addEventListener('hashchange', () => navigate(window.location.hash.slice(1)));
  document.querySelectorAll('[data-example]').forEach(b => b.addEventListener('click', () => {
    $('question').value = b.dataset.example; text('character-count', `${$('question').value.length} / 6,000`); $('question').focus();
  }));
  $('question').addEventListener('input', () => text('character-count', `${$('question').value.length} / 6,000`));
  $('requirements').addEventListener('submit', event => { event.preventDefault(); analyze(); });
  $('cancel').addEventListener('click', () => state.controller?.abort());
  $('clarify').addEventListener('click', () => {
    if (!$('answer').value.trim()) { $('answer').focus(); return; }
    const question = `${$('question').value}\nAdditional task information: ${$('answer').value.trim()}`;
    if (question.length > 6000) { setStatus('Keep the combined task and clarification within 6,000 characters.', true); return; }
    $('question').value = question; $('answer').value = ''; text('character-count', `${question.length} / 6,000`); analyze();
  });
  $('alpha').addEventListener('input', () => queueWeight(Number($('alpha').value)));
  $('reset').addEventListener('click', () => { invalidateWeights(); recalculate(null); });
  $('show-comparison').addEventListener('click', () => { navigate('comparison'); $('compare-panel').hidden = false; renderComparison(); $('compare-panel').scrollIntoView({block: 'start', behavior: 'smooth'}); });
  $('clear-selection').addEventListener('click', clearSelection); $('clear-comparison').addEventListener('click', clearSelection);
  $('close-drawer').addEventListener('click', () => $('model-drawer').close());
  $('model-drawer').addEventListener('close', () => { state.drawerId = null; if (state.drawerFocus?.isConnected) state.drawerFocus.focus(); else $('main').focus({preventScroll: true}); });
  $('model-drawer').addEventListener('click', event => { if (event.target === $('model-drawer')) { const bounds = $('model-drawer').getBoundingClientRect(); if (event.clientX < bounds.left) $('model-drawer').close(); } });
  $('technical-details').addEventListener('toggle', renderTechnical);
  $('evidence-search').addEventListener('input', () => { state.evidenceLimit = 40; renderEvidenceRows(); });
  $('more-evidence').addEventListener('click', () => { state.evidenceLimit += 40; renderEvidenceRows(); });
  resetProgress(); navigate(window.location.hash.slice(1));
  fetch('/api/modelmatch/config').then(response => { if (!response.ok) throw new Error(); return response.json(); }).then(config => {
    if (!['live_vertex', 'offline_synthetic'].includes(config.mode)) throw new Error('Unknown execution mode');
    state.mode = config.mode; const offline = config.mode === 'offline_synthetic';
    text('mode', offline ? 'Synthetic offline demo' : 'Live Vertex mode'); text('mode-short', offline ? 'Synthetic demo · No live calls' : 'Live provider · Runs on request');
    $('approval').hidden = offline;
  }).catch(() => { state.mode = null; text('mode', 'Mode unavailable'); text('mode-short', 'Configuration unavailable'); $('approval').hidden = true; setStatus('Unable to check execution mode. No analysis will start until configuration is available.', true); });
}
if (typeof document !== 'undefined') initialize();
