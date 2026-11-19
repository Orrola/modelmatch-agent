/* Read-only recommendation presentation. Scores, eligibility and membership come from Python. */
globalThis.ModelMatchRecommendations = {
  create(api) {
    const {state, el, text, button, badge, number, pretty, modelTitle, statusBadge, selectionControl,
      missingFor, evidenceFor, metricLabel, reasonLabel, renderCard} = api;
    function identity(decision = state.decision, source = state.modelIdentity, selection = state.selection) {
      if (!source || !source.models || !decision || source.retrieved_at !== decision.retrieved_at || source.snapshot_id !== decision.snapshot_id || source.data_mode !== decision.data_mode
          || (selection && (source.snapshot_fingerprint !== selection.snapshot_fingerprint))) return null;
      return source;
    }
    function metadata(id) { return identity()?.models[id] || null; }
    function rawRank(id, decision = state.decision) {
      for (const group of ['fully_evaluable', 'provisional']) {
        const row = decision?.rankings[group]?.find(row => row.model_id === id);
        if (row) return `Raw rank ${row.rank} · ${pretty(group)}`;
      }
      return 'Not numerically ranked';
    }
    function identityLine(id) {
      const meta = metadata(id);
      return meta?.creator_name ? `Creator: ${meta.creator_name}` : 'Creator unknown';
    }
    function operational(candidate) {
      const box = el('div', 'operational-summary'), observed = evidenceFor(candidate).filter(e => e.evidence_status === 'observed');
      const cost = observed.find(e => e.source_type === 'derived' && e.metric === 'monthly_cost_usd' && e.value === candidate.estimated_monthly_cost_usd);
      box.append(el('p', '', cost ? `Estimated monthly token cost: $${number(cost.value)}. Not a billing quote.` : 'Monthly cost not estimated in this decision. Inspect workload and pricing before comparing costs.'));
      for (const [metric, label] of [['pricing.price_1m_input_tokens', 'Input'], ['pricing.price_1m_output_tokens', 'Output']]) {
        const price = observed.find(e => e.metric === metric && e.source_type === 'artificial_analysis');
        if (price) box.append(el('p', '', `${label} token price: $${number(price.value)} per million tokens.`));
      }
      for (const [metric, label, unit] of [
        ['performance_v3.mean_time_to_first_token_seconds', 'Mean TTFT', 's'],
        ['performance_v3.mean_output_tokens_per_second', 'Mean output speed', 'tokens/s'],
      ]) {
        const record = observed.find(e => e.metric === metric && e.statistic === 'mean' && e.source_type === 'artificial_analysis');
        box.append(el('p', '', `${label}: ${record ? `${number(record.value)} ${unit}` : 'Unknown'}`));
      }
      return box;
    }
    function renderBestOverall(candidate) {
      const panel = document.getElementById('ranking');
      panel.dataset.count = candidate ? '1' : '0';
      if (!candidate) {
        const message = state.selector?.status === 'unavailable'
          ? 'Recommendation selection failed. Raw scores and evidence remain available below.'
          : !state.selection
            ? 'This analysis has no recommendation selection. Review the available scores in Raw Ranking.'
            : 'No eligible model has a complete decision score. See Model Evaluation Coverage for scoring blockers.';
        panel.replaceChildren(el('p', 'recommendation-empty', message));
        return;
      }
      const slot = state.selection.slots.best_overall;
      const card = el('article', 'model-card best-summary');
      card.dataset.modelId = candidate.model_id;
      card.dataset.role = 'best_overall';
      const header = el('div', 'best-header'), title = el('div', 'best-title');
      title.append(el('p', 'best-label', 'BEST OVERALL'), modelTitle(candidate), statusBadge(candidate));
      const score = el('div', 'score-block');
      score.append(el('strong', 'score-number', number(candidate.S)), el('span', 'score-caption', 'Decision score S · Custom policy points'));
      header.append(title, score);
      const metrics = el('div', 'metric-strip');
      for (const [key, label] of [['G', 'General Intelligence (G)'], ['U', 'Use-case Capability (U)'], ['O', 'Operational Adjustment (O)']]) {
        const item = el('div', 'metric-item');
        item.append(el('span', '', label), el('strong', '', number(candidate[key]))); metrics.append(item);
      }
      const eligibility = el('div', 'metric-item');
      eligibility.append(el('span', '', 'Eligibility'), badge(pretty(candidate.eligibility), candidate.eligibility === 'eligible' ? 'good' : 'warning'));
      metrics.append(eligibility);
      const reason = slot.reason_code === 'highest_original_rank_in_cohort'
        ? 'Highest-ranked qualified model in the supported scoring cohort.' : reasonLabel(slot.reason_code);
      const why = el('p', 'selection-reason'); why.append(el('strong', '', 'Why recommended: '), el('span', '', reason));
      card.append(header, metrics, why);
      const observed = evidenceFor(candidate).filter(e => e.evidence_status === 'observed' && Number.isFinite(e.value) && e.value >= 0);
      const highlights = el('div', 'best-highlights');
      const prices = ['pricing.price_1m_input_tokens', 'pricing.price_1m_output_tokens'].every(metric => observed.some(e => e.source_type === 'artificial_analysis' && e.metric === metric));
      const workload = ['monthly_requests', 'avg_input_tokens', 'avg_output_tokens'].every(key => Number.isFinite(candidate.workload?.[key]) && candidate.workload[key] >= 0);
      const cost = observed.find(e => e.source_type === 'derived' && e.metric === 'monthly_cost_usd' && e.value === candidate.estimated_monthly_cost_usd);
      if (cost && prices && workload) highlights.append(el('span', '', `Est. monthly API cost: $${number(cost.value)}`));
      for (const [metric, label, unit] of [
        ['performance_v3.mean_time_to_first_token_seconds', 'Mean TTFT', 's'],
        ['performance_v3.mean_output_tokens_per_second', 'Mean output speed', 'tokens/s'],
      ]) {
        const record = observed.find(e => e.metric === metric && e.statistic === 'mean' && e.source_type === 'artificial_analysis');
        if (record) highlights.append(el('span', '', `${label}: ${number(record.value)} ${unit}`));
      }
      if (highlights.children.length) card.append(highlights);
      if (typeof candidate.O === 'number' && candidate.O < 0) card.append(el('p', 'model-warning', `Your stated operational targets deduct ${number(-candidate.O)} points for this model.`));
      const gaps = missingFor(candidate.model_id);
      if (gaps.length) card.append(el('p', 'missing-signal', `${gaps.length} unavailable ${gaps.length === 1 ? 'metric' : 'metrics'} — inspect evidence details.`));
      const facts = el('details', 'card-evidence-details');
      facts.append(el('summary', '', 'Evidence details'), el('p', 'identity-line', identityLine(candidate.model_id)),
        el('p', 'raw-rank', `${rawRank(candidate.model_id)} · AA ID: ${candidate.model_id}`), operational(candidate));
      if (gaps.length) facts.append(el('p', 'field-help', gaps.map(g => `${metricLabel(g.metric)}: ${reasonLabel(g.reason)}`).join(' · ')));
      const actions = el('div', 'card-actions');
      actions.append(button('View model details ↗', () => api.openRawModel(candidate, state.decision, state.modelIdentity)), facts, selectionControl(candidate));
      card.append(actions);
      panel.replaceChildren(card);
    }
    function scoreCoverage() {
      // Tally existing backend blockers; never infer why a score should or should not exist.
      const candidates = Object.values(state.decision.candidates);
      const unscored = candidates.filter(c => !(Number.isFinite(c.S) && (!c.score_status || c.score_status === 'computed')));
      const evidenceCodes = ['missing_or_invalid_G', 'missing_or_invalid_U', 'requested_operational_evidence_incomplete',
        'unknown_cost_penalty', 'unknown_ttft_penalty', 'unknown_output_speed_penalty'];
      const missing = unscored.filter(c => (c.score_blockers || []).some(code => evidenceCodes.includes(code)) || missingFor(c.model_id).some(gap => gap.required));
      const unspecified = unscored.filter(c => !missing.includes(c) && (!Array.isArray(c.score_blockers) || !c.score_blockers.length));
      return {missing: missing.length, other: unscored.length - missing.length - unspecified.length, unspecified: unspecified.length,
        facets: [
          ['Missing or invalid G', c => (c.score_blockers || []).includes('missing_or_invalid_G')],
          ['Missing or invalid task-relevant U', c => (c.score_blockers || []).includes('missing_or_invalid_U')],
          ['Requested operational evidence incomplete', c => (c.score_blockers || []).includes('requested_operational_evidence_incomplete')],
          ['Operational penalty evidence unavailable or incompatible', c => (c.score_blockers || []).some(code => ['unknown_cost_penalty', 'unknown_ttft_penalty', 'unknown_output_speed_penalty'].includes(code))],
          ['Known hard-constraint failure', c => (c.score_blockers || []).includes('hard_constraints_ineligible')],
          ['Hard-constraint evidence unknown', c => (c.score_blockers || []).includes('hard_constraints_unverified')],
          ['Unsupported soft-requirement policy', c => (c.score_blockers || []).some(code => code.startsWith('no_soft_penalty_policy_for_'))],
          ['Nonfinite score blocked', c => (c.score_blockers || []).includes('nonfinite_score')],
        ].map(([label, predicate]) => [label, unscored.filter(predicate).length]),
        scored: candidates.length - unscored.length};
    }
    function renderCoverage() {
      const panel = document.getElementById('recommendation-coverage'), c = state.selection?.coverage, scores = scoreCoverage();
      panel.replaceChildren(el('h2', '', 'Model Evaluation Coverage'),
        el('p', 'coverage-subtitle', 'See how many models have enough evidence to be scored and compared.'));
      const grid = el('dl', 'coverage-grid coverage-primary');
      for (const [label, value, definition] of [
        ['Models considered', c?.total_candidate_entries ?? state.decision.counts_before_shortlist.total, 'Candidate entries in this snapshot, not new independent evaluations.'],
        ['Models with scores', c?.numerically_scored ?? scores.scored, 'Valid numerical decision scores reported by the backend.'],
        ['Missing required scores', scores.unspecified ? `${scores.missing} confirmed` : scores.missing, 'Unscored with reported missing or invalid required index or operational evidence.'],
      ]) { const cell = el('div'); cell.append(el('dt', '', label), el('dd', '', value), el('p', 'field-help', definition)); grid.append(cell); }
      panel.append(grid);
      if (scores.other || scores.unspecified) panel.append(el('p', 'coverage-other', `${scores.other} additional unscored entries have other reported blockers.${scores.unspecified ? ` ${scores.unspecified} lack enough reason data; the complete missing-evidence count is unknown.` : ''} Inspect the breakdown below.`));
      panel.append(el('p', 'field-help', 'Scoring completeness is different from hard-constraint eligibility. A numeric score alone does not establish recommendation eligibility. The current engine also blocks scores for failed or unverified hard constraints. Missing scores do not imply low model quality.'));
      const detail = el('details', 'coverage-secondary'); detail.append(el('summary', '', 'Evidence & qualification breakdown'));
      const secondary = el('dl', 'coverage-grid');
      for (const [label, value] of [
        ['G available', c?.G_valid], ['Task-relevant U available', c?.task_relevant_U_valid],
        ['Eligible', c?.eligibility?.eligible], ['Hard constraints unverified', c?.eligibility?.unverified], ['Ineligible', c?.eligibility?.ineligible],
      ]) { const cell = el('div'); cell.append(el('dt', '', label), el('dd', '', value ?? 'Unknown')); secondary.append(cell); }
      const breakdown = el('ul', 'score-blocker-breakdown');
      for (const [label, count] of scores.facets) if (count) breakdown.append(el('li', '', `${label}: ${count}`));
      if (!breakdown.children.length) breakdown.append(el('li', '', 'No specific unscored blocker categories reported.'));
      detail.append(secondary, el('h3', '', 'Reported reasons for unscored entries'), breakdown,
        el('p', 'field-help', 'Counts overlap. Evidence gaps and qualification blockers are separate dimensions; do not add them. A candidate can have multiple reported blockers.'));
      const source = identity();
      detail.append(el('p', 'field-help', source ? `Snapshot ${source.snapshot_id} · Retrieved ${source.retrieved_at || 'unknown'}` : 'Compatible snapshot identity metadata is unavailable.'));
      panel.append(detail);
    }
    function renderAlternatives() {
      const panel = document.getElementById('potential-alternatives'), potential = state.selection?.potential_alternatives;
      panel.replaceChildren(el('h2', '', 'Potential Alternatives — Limited Evidence'),
        el('p', 'field-help', 'Observed evidence, incomplete scoring. These are exploration candidates, not scored recommendations or a Top 3. Limited evidence does not imply poor quality.'));
      if (!potential || state.selector?.status === 'unavailable') { panel.append(el('p', '', 'Limited-evidence exploration is unavailable in this response. Inspect missing data in the candidate catalog.')); return; }
      panel.append(el('p', 'field-help', `Backend order: ${potential.ordering}. This is not a quality ranking. Only returned entries can be expanded.`));
      for (const kind of ['U_only', 'G_only']) {
        const group = el('section', 'alternative-group');
        group.append(el('h3', '', kind === 'U_only' ? 'Task-specific score available' : 'General score available'),
          el('p', 'field-help', kind === 'U_only'
            ? 'These models have a task-related capability score, but lack a General Intelligence score needed for the overall ranking.'
            : 'These models have a General Intelligence score, but lack the task-specific capability score needed for the overall ranking.'));
        const empty = el('details', 'empty-alternative-buckets'), emptySummary = el('summary');
        empty.append(emptySummary); const emptyLabels = []; let emptyCount = 0;
        for (const eligibility of ['eligible', 'unverified']) {
          const bucket = potential.buckets[kind][eligibility];
          if (!bucket.returned) {
            emptyCount++; emptyLabels.push(`${pretty(eligibility)}: ${bucket.returned} returned, ${bucket.omitted} omitted`);
            empty.append(el('p', 'field-help', `${pretty(eligibility)}: ${bucket.total_before_limit} before limit · ${bucket.returned} returned · ${bucket.omitted} omitted.${eligibility === 'unverified' ? ' Unverified means hard-constraint evidence is unknown.' : ''}`));
            continue;
          }
          const block = el('div', 'alternative-bucket');
          block.append(el('h4', '', `${pretty(eligibility)} · ${bucket.total_before_limit} before backend limit`),
            el('p', 'field-help', eligibility === 'unverified' ? 'A hard requirement has unknown evidence. Eligibility is not verified.' : 'No known hard-constraint blocker; required scoring evidence is still incomplete.'));
          const addEntry = row => {
            const item = el('article', 'alternative-card'); item.dataset.modelId = row.model_id;
            const candidate = state.decision.candidates[row.model_id];
            if (candidate) item.append(modelTitle(candidate)); else item.append(el('h5', '', row.name));
            item.append(el('p', 'alternative-evidence', `${kind === 'U_only' ? 'Observed U' : 'Observed G'}: ${number(row.available_index.value)} index points · Missing ${kind === 'U_only' ? 'G' : 'U'} · S: Unavailable`),
              badge(`Eligibility: ${pretty(row.eligibility)}`, 'warning'), badge(`Evidence: ${pretty(row.candidate_status)}`, 'neutral'));
            const gaps = el('details', 'alternative-missing');
            gaps.append(el('summary', '', 'Missing evidence details'), el('p', 'field-help', (row.missing_evidence_reasons || []).map(gap => typeof gap === 'string' ? reasonLabel(gap) : `${metricLabel(gap.metric || gap.field || 'evidence')}: ${reasonLabel(gap.reason || 'unknown')}`).join(' · ') || 'Inspect model details for missing dimensions.'));
            item.append(gaps); return item;
          };
          block.append(...bucket.entries.slice(0, 2).map(addEntry));
          if (bucket.entries.length > 2) { const more = el('details', 'more-alternatives'); more.append(el('summary', '', `Show ${bucket.entries.length - 2} more returned entries`), ...bucket.entries.slice(2).map(addEntry)); block.append(more); }
          block.append(el('p', 'field-help', `${bucket.returned} returned · ${bucket.omitted} omitted by the backend limit.`));
          group.append(block);
        }
        if (emptyCount === 2) group.append(el('p', 'empty-group-note', 'No entries returned in this evidence group.'));
        if (emptyCount) { emptySummary.textContent = `Other status buckets · ${emptyLabels.join(' · ')}`; group.append(empty); }
        panel.append(group);
      }
      panel.append(el('p', 'field-help', 'Omitted models remain inspectable in the candidate catalog. Known ineligible models are excluded from exploration buckets. Eligibility and scoring evidence remain separate.'));
    }
    function renderRawRanking() {
      const original = document.getElementById('ranking-scope').value === 'original';
      const decision = original ? state.original?.decision : state.decision, panel = document.getElementById('raw-ranking');
      panel.replaceChildren(); if (!decision) return;
      const source = original ? state.original.model_identity : state.modelIdentity;
      panel.append(el('p', 'field-help', `${original ? 'Original analysis' : 'Current'} weights: General ${Math.round(decision.weights.alpha * 100)}%. Raw Ranking keeps backend order and ties; exact model IDs are retained.`));
      for (const key of ['fully_evaluable', 'provisional']) {
        const rows = decision.rankings[key], block = el('details', 'raw-ranking-group');
        block.append(el('summary', '', `${pretty(key)} Raw Ranking (${rows.length})`));
        const addRow = row => {
          const c = decision.candidates[row.model_id], item = el('div', 'raw-ranking-row');
          const name = button(c.name, () => api.openRawModel(c, decision, source), 'model-title');
          item.append(el('strong', '', `#${row.rank}`), name,
            el('span', '', `G ${number(c.G)} · U ${number(c.U)} · O ${number(c.O)} · S ${number(c.S)}`),
            el('span', 'field-help', `Eligibility: ${pretty(c.eligibility)}`));
          return item;
        };
        block.append(...rows.slice(0, 20).map(addRow));
        if (rows.length > 20) { const more = el('details'); more.append(el('summary', '', `Show remaining ${rows.length - 20} ranked entries`), ...rows.slice(20).map(addRow)); block.append(more); }
        if (!rows.length) block.append(el('p', '', 'No numeric ranking in this cohort.'));
        panel.append(block);
      }
    }
    return {renderBestOverall, renderCoverage, scoreCoverage, renderAlternatives, renderRawRanking, identityLine, rawRank, metadata};
  },
};
