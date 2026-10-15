'use strict';
/* Static viewer for saved artifacts. Reads results.json (original record) and artifacts/*.json
   (offline runs). Never computes or invents a score: missing data is shown as unavailable. */
const Q = s => document.querySelector(s), QA = s => [...document.querySelectorAll(s)];
const H = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hum = x => String(x ?? 'not recorded').replaceAll('_', ' ');
const num = (x, d = 2) => x === null || x === undefined ? '—' : Number(x).toFixed(d);
const METHODS = [['ordinary', 'Ordinary RAG', 'var(--s1)'], ['multi_query', 'Multi-Query RAG', 'var(--s2)'], ['graph_guided', 'Graph-Guided RAG', 'var(--s3)']];
const ORACLE = ['oracle', 'Oracle evidence (diagnostic)', 'var(--s-oracle)'];
const state = { index: null, record: null, bny: null, poc: null, pocView: 'reviewed', pocPath: '', pocOrigPath: '', bench: {}, edge: 'E1', benchName: 'fincausal2026', metric: null, sample: 0, sampleMethod: 'graph_guided' };

async function getJSON(p) { const r = await fetch(p, { cache: 'no-cache' }); if (!r.ok) throw Error(p + ' HTTP ' + r.status); return r.json(); }
const pill = s => s === 'computed' ? '<span class="pill computed">Computed</span>' : s === 'recorded' ? '<span class="pill recorded">Recorded</span>' : '<span class="pill pending">Unavailable</span>';
const latest = (kind, ds, pre) => (state.index?.artifacts || []).filter(a => a.kind === kind && a.status === 'computed' && (!ds || a.dataset === ds) && (!pre || a.name.startsWith(pre))).sort((a, b) => b.created_utc.localeCompare(a.created_utc))[0];

/* ---------------- tabs */
function showTab() {
  const t = (location.hash || '#experiment').slice(1);
  const tab = ['experiment', 'benchmarks', 'guide'].includes(t) ? t : 'experiment';
  QA('.tab').forEach(s => s.hidden = s.id !== 'tab-' + tab);
  QA('nav a').forEach(a => a.dataset.tab === tab ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
}

/* ---------------- tooltip */
const tip = Q('#tip');
document.addEventListener('mouseover', e => { const t = e.target.closest('[data-tip]'); if (!t) return; tip.textContent = t.dataset.tip; tip.hidden = false; });
document.addEventListener('mousemove', e => { if (!tip.hidden) { tip.style.left = Math.min(e.clientX + 12, innerWidth - 270) + 'px'; tip.style.top = e.clientY + 14 + 'px'; } });
document.addEventListener('mouseout', e => { if (e.target.closest('[data-tip]')) tip.hidden = true; });

/* ---------------- Experiment: E3 -> E4 -> E5 demo (default page). Every finding below is derived from the saved artifact. */
const SHORT = { consumption: 'Consumer spending', inflation_pressure: 'Inflation pressure', rate_expectations: 'Expected rate path', equity_valuation_pressure: 'Equity valuations' };
function experiment() {
  const P = state.poc, el = Q('#exp-body');
  if (!P) { el.innerHTML = `<div class="panel">${pill('pending')} No demo run saved. Run <code>python -m crag.cli bny-poc</code>.</div>`; return; }
  const reviewed = !!P.run.review, useRev = reviewed && state.pocView === 'reviewed';
  const r = P.run, ids = P.edges_assessed, G = P.graph, lab = id => SHORT[id] || G.nodes.find(n => n.id === id)?.label || id;
  const E = ids.map(id => G.edges.find(e => e.id === id)), nodes = [E[0].source, ...E.map(e => e.target)];
  const runs = Object.fromEntries(METHODS.map(([m]) => [m, P.methods[m]?.[0]]));
  const ed = (m, id) => runs[m]?.edges.find(x => x.edge_id === id);
  const verdict = x => useRev || !x.original_validator ? x.validator : x.original_validator;
  const paths = m => (useRev || !runs[m].original_paths ? runs[m].paths : runs[m].original_paths).paths;
  const pathId = Object.keys(runs.graph_guided.paths.paths)[0];
  const rel = x => ['supporting_evidence', 'contradicting_evidence'].flatMap(k => x.validator.quotes[k] || []).filter(q => q.citation_status === 'valid' && q.kind !== 'off_target').length;
  const set = m => new Set(Object.values(runs[m].routing).flat()), ord = set('ordinary');
  // chain diagram
  const svg = `<ol class="chain" aria-label="Causal chain: ${nodes.map(lab).join(' to ')}">${nodes.map((n, i) => `<li class="cnode"><span class="dot" aria-hidden="true"></span>${H(lab(n))}</li>${E[i] ? `<li class="cedge" aria-label="${E[i].id}, hypothesised sign ${E[i].sign > 0 ? 'positive' : 'negative'}"><span>${E[i].id} (${E[i].sign > 0 ? '+' : '−'})</span></li>` : ''}`).join('')}</ol>`;
  // findings (computed, never hardcoded)
  const sup = METHODS.map(([m, n]) => [n, ids.filter(id => verdict(ed(m, id)).judgment === 'supported')]);
  const anySup = sup.filter(([, xs]) => xs.length);
  const chainSup = METHODS.filter(([m]) => paths(m)[pathId]?.status === 'supported').map(([, n]) => n);
  const changes = reviewed ? METHODS.flatMap(([m, n]) => ids.map(id => [n, id, ed(m, id)]).filter(([, , x]) => x.original_validator && x.original_validator.judgment !== x.validator.judgment)
    .map(([n, id, x]) => `${n} ${id}: ${hum(x.original_validator.judgment)} → ${hum(x.validator.judgment)}`)) : [];
  const findings = [
    anySup.length ? `Supported edges: ${anySup.map(([n, xs]) => `<b>${n.replace(' RAG', '')}</b> ${xs.join(', ')}`).join('; ')}. Other methods found no supported edge.` : 'No method found a supported edge.',
    chainSup.length ? `Full chain supported by: ${chainSup.join(', ')}.` : 'No method supports the full chain: at least one link lacks sufficient evidence in every method.',
    `Graph-Guided retrieved different evidence: ${[...set('graph_guided')].filter(c => ord.has(c)).length} of ${set('graph_guided').size} passages overlap with Ordinary RAG.`,
    ...(useRev && changes.length ? [`Validator v2 changed ${changes.join('; ')} (co-movement is not a causal contradiction).`] : [])];
  const cell = (m, id) => { const x = ed(m, id), v = verdict(x), n = rel(x);
    return `<td><span class="badge ${H(v.judgment)}" data-tip="${H(v.reasons.join(' '))}">${hum(v.judgment)}</span><div class="rel" data-tip="Relevance: valid, on-topic quotes the assessor cited. Independent of the validity verdict.">${n} relevant quote${n === 1 ? '' : 's'}</div></td>`; };
  el.innerHTML = `
    <div class="exp-meta"><span class="tag">Small qualitative demonstration</span><span class="muted small">${H(r.model)} · ${H(r.created_utc.slice(0, 10))} · 1 repeat · ${r.budget_chunks} passages per method · cost $${num(r.usage?.cost_usd_recorded, 2)}</span>
      ${reviewed ? `<div class="seg" role="tablist" aria-label="Assessment version"><button role="tab" data-pocview="reviewed" aria-selected="${useRev}">Reviewed (validator v2)</button><button role="tab" data-pocview="original" aria-selected="${!useRev}">Original run</button></div>` : ''}</div>
    <div class="panel chain-panel">${svg}</div>
    <div class="findings"><h2 class="h3">Key findings</h2><ul>${findings.map(f => `<li>${f}</li>`).join('')}</ul></div>
    <div class="tablewrap"><table class="data poc"><thead><tr><th>Link</th>${METHODS.map(([, n, c]) => `<th style="box-shadow:inset 0 3px 0 ${c}">${n}</th>`).join('')}</tr></thead><tbody>
      ${E.map(e => `<tr><th scope="row">${e.id} <span class="muted">${H(lab(e.source))} → ${H(lab(e.target))}</span></th>${METHODS.map(([m]) => cell(m, e.id)).join('')}</tr>`).join('')}
      <tr class="chainrow"><th scope="row">Chain ${H(pathId.replace('_', ' '))}</th>${METHODS.map(([m]) => { const s = paths(m)[pathId]; return `<td><span class="badge ${H(s?.status)}">${hum(s?.status)}</span></td>`; }).join('')}</tr>
    </tbody></table></div>
    <div class="keyline"><div><b>Verdict = causal validity.</b> Does the text state the mechanism, before the cutoff, without being off-target or merely correlated?</div><div><b>Relevant quotes = evidence relevance.</b> On-topic, verbatim quotes cited. Relevant is not the same as valid.</div><div><b>Chain rule.</b> Supported only if every link is; broken only by a validated causal contradiction.</div></div>
    <details class="panel"><summary>Explanations, quotes and retrieved passages</summary><div class="compare3">${METHODS.map(([m, name, c]) => { const run = runs[m];
      return `<div class="mcol" style="--c:${c}"><h3>${name}</h3>
        ${E.map(e => { const x = ed(m, e.id), v = verdict(x); return `<details><summary>${e.id}: ${hum(v.judgment)}</summary><ul class="reasons">${v.reasons.map(t => `<li>${H(t)}</li>`).join('')}</ul><p class="small"><b>Assessor:</b> ${H(x.explanation)}</p><h4 class="small">Supporting</h4>${quoteList(x.validator.quotes, 'supporting_evidence')}<h4 class="small">Contradicting</h4>${quoteList(x.validator.quotes, 'contradicting_evidence')}</details>`; }).join('')}
        <details><summary>Retrieved passages (${set(m).size})</summary><p class="small"><b>Queries:</b><br>${run.queries.map(H).join('<br>')}</p>${Object.entries(run.routing).map(([k, cs]) => `${k !== 'all' ? `<h4 class="small">Routed to ${H(k)}</h4>` : ''}${cs.map(cid => { const p = P.evidence[cid]; return `<details class="psg"><summary class="meta">${H(cid)} · ${H(p.available_at_et.slice(0, 10))}</summary><p class="small">${H(p.text)}</p></details>`; }).join('')}`).join('')}</details></div>`; }).join('')}</div></details>
    <details class="panel"><summary>Setup and limitations</summary><ul class="small">
      <li>Same corpus, BM25 retriever, model, assessor prompt and ${r.budget_chunks}-passage budget for all methods. Multi-Query uses as many queries as Graph-Guided (${runs.graph_guided.n_queries}), so differences are not just query count.</li>
      <li>Evidence must be public before ${H(r.cutoff.slice(0, 16).replace('T', ' '))} ET; future passages retrieved: ${METHODS.map(([m]) => runs[m].future_chunks_retrieved.length).reduce((a, b) => a + b, 0)}.</li>
      <li>One event, one repeat, no gold labels. This illustrates behaviour; it is not evidence that any method is superior, and no verdict establishes causality.</li>
      ${reviewed ? `<li>${H(r.review.note)} Validator: ${H(r.review.validator_version)}. Model calls for the review: ${r.review.model_calls}.</li>` : ''}
      <li>Artifacts: <a href="${H(state.pocPath)}">${H(state.pocPath)}</a>${state.pocOrigPath ? ` · original <a href="${H(state.pocOrigPath)}">${H(state.pocOrigPath)}</a>` : ''}</li></ul></details>`;
}

/* ---------------- BNY three-method */
const NODES = { consumption: [30, 120, 'Spending'], earnings_expectations: [140, 45, 'Earnings'], equity_support: [275, 45, 'Equities'],
  inflation_pressure: [100, 200, 'Inflation'], rate_expectations: [190, 200, 'Rates'], equity_valuation_pressure: [280, 200, 'Equities'] };
function bnyGraph(run) {
  const edges = state.bny.graph.edges;
  const j = id => run?.edges.find(x => x.edge_id === id)?.validator.judgment;
  const g = edges.map(e => {
    const [x1, y1] = NODES[e.source], [x2, y2] = NODES[e.target], mx = (x1 + x2) / 2, my = (y1 + y2) / 2, sel = e.id === state.edge;
    return `<g class="e" tabindex="0" role="button" aria-pressed="${sel}" aria-label="${e.id}: ${H(e.source)} to ${H(e.target)}" data-edge="${e.id}" data-tip="${e.id} · sign ${e.sign > 0 ? '+' : '−'} · graph-guided: ${hum(j(e.id))}">
      <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${sel ? 'var(--accent)' : 'var(--ink-3)'}" stroke-width="${sel ? 3 : 2}" marker-end="url(#ah)"/>
      <line class="hit" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="transparent" stroke-opacity="0" stroke-width="18"/>
      <rect x="${mx - 15}" y="${my - 10}" width="30" height="18" rx="4" fill="var(--surface)" stroke="${sel ? 'var(--accent)' : 'var(--line)'}"/>
      <text class="lbl" x="${mx}" y="${my + 3}" text-anchor="middle">${e.id}${e.sign > 0 ? '+' : '−'}</text></g>`;
  }).join('');
  const n = Object.entries(NODES).map(([id, [x, y, l]]) => `<circle cx="${x}" cy="${y}" r="6" fill="var(--accent)"/><text x="${x}" y="${y + (y > 130 ? 22 : -14)}" text-anchor="${x < 40 ? 'start' : x > 260 ? 'end' : 'middle'}">${l}</text>`).join('');
  Q('#bny-graph').innerHTML = `<svg viewBox="-10 0 345 235" role="group" aria-label="BNY causal graph; select an edge"><defs><marker id="ah" viewBox="0 0 10 10" refX="16" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--ink-3)"/></marker></defs>${g}${n}</svg>`;
}
function quoteList(q, side) {
  const xs = q[side] || [];
  return xs.length ? xs.map(x => `<blockquote>${H(x.quote)}<div class="meta">${H(x.chunk_id)} · ${hum(x.citation_status)} · ${hum(x.kind)}${x.excluded ? ' · excluded: ' + H(x.excluded) : ''}</div></blockquote>`).join('') : '<p class="muted small">None.</p>';
}
function bny() {
  const B = state.bny;
  if (!B) { Q('#bny-status').innerHTML = pill('pending') + ' No three-method run saved. Run <code>python -m crag.cli bny-run</code>.'; Q('#bny-compare').innerHTML = ''; return; }
  const r = B.run, gg = B.methods.graph_guided[0];
  Q('#bny-status').innerHTML = `${pill(r.status)} <span>${H(r.model)} · ${H(r.created_utc.slice(0, 10))} · budget ${r.budget_chunks} chunks/method · ${r.repeats} repeat · cost $${num(r.usage?.cost_usd_recorded, 2)}</span><span data-tip="${H(r.note)}">ⓘ one event, no gold</span>`;
  bnyGraph(gg);
  const e = B.graph.edges.find(x => x.id === state.edge), lab = id => B.graph.nodes.find(n => n.id === id)?.label || id;
  Q('#bny-edge-head').innerHTML = `<h2 class="h3" style="margin-top:0">${e.id} · ${H(lab(e.source))} → ${H(lab(e.target))}</h2><p class="muted small">Condition: ${H(e.condition)}</p>`;
  Q('#bny-compare').innerHTML = METHODS.map(([m, name, c]) => {
    const run = B.methods[m]?.[0], x = run?.edges.find(y => y.edge_id === state.edge);
    if (!x) return `<div class="mcol" style="--c:${c}"><h3>${name}</h3><p class="empty">Not recorded.</p></div>`;
    const v = x.validator, routed = run.routing[state.edge] || run.routing.all;
    return `<div class="mcol" style="--c:${c}"><h3>${name}</h3>
      <div><span class="badge ${H(x.citation_checked_label)}" data-tip="Model label after quote checks">${hum(x.citation_checked_label)}</span><span class="arrow">→</span><span class="badge ${H(v.judgment)}" data-tip="After causal validation">${hum(v.judgment)}</span></div>
      <ul class="reasons">${v.reasons.map(t => `<li>${H(t)}</li>`).join('')}</ul>
      <p class="small muted">Evidence kind: ${hum(x.evidence_kind)} · condition: ${hum(x.assumption_status)}</p>
      <details><summary>Explanation &amp; quotes</summary><p class="small">${H(x.explanation)}</p><h4 class="small">Supporting</h4>${quoteList(v.quotes, 'supporting_evidence')}<h4 class="small">Contradicting</h4>${quoteList(v.quotes, 'contradicting_evidence')}</details>
      <details><summary>Retrieval (${run.n_queries} quer${run.n_queries > 1 ? 'ies' : 'y'}, ${routed.length} chunks${run.routing[state.edge] ? ' for this edge' : ' shared by all edges'})</summary><p class="small">${run.queries.map(H).join('<br>')}</p><p class="meta">${routed.map(H).join(', ')}</p></details></div>`;
  }).join('');
  const P = ['P1_earnings', 'P2_rates'];
  Q('#bny-paths').innerHTML = `<div class="paths"><table><caption class="small muted" style="text-align:left">Pathways (never netted)</caption><thead><tr><th>Method</th>${P.map(p => `<th>${p.replace('_', ' ')}</th>`).join('')}</tr></thead><tbody>${
    METHODS.map(([m, name]) => `<tr><td>${name.replace(' RAG', '')}</td>${P.map(p => { const s = B.methods[m]?.[0].paths.paths[p]; return `<td><span class="badge ${s?.status}" data-tip="${s ? s.edges.map((id, i) => id + ': ' + hum(s.edge_states[i])).join(' · ') : ''}">${hum(s?.status)}</span></td>`; }).join('')}</tr>`).join('')}</tbody></table>
    <p class="small muted">A chain is supported only if every link is. ${H(gg.paths.net_conclusion_note)}</p></div>`;
  const rows = B.regression_on_recorded_v1.rows.filter(x => ['E1', 'E5'].includes(x.edge_id) && x.repeat === 0);
  Q('#bny-regression').innerHTML = `<p class="small muted">${H(B.regression_on_recorded_v1.note)}</p><div class="tablewrap"><table class="data"><thead><tr><th>Run</th><th>Edge</th><th>v1 label</th><th>Validator</th><th>Reason</th></tr></thead><tbody>${rows.map(x => `<tr><td>${hum(x.condition)} r0</td><td>${x.edge_id}</td><td><span class="badge ${x.v1_label}">${hum(x.v1_label)}</span></td><td><span class="badge ${x.validator}">${hum(x.validator)}</span></td><td style="text-align:left">${H(x.reasons[0])}</td></tr>`).join('')}</tbody></table></div>`;
}

/* ---------------- benchmarks */
const BENCH = {
  fincausal2026: { metrics: [['token_f1', 'Token F1'], ['exact_match', 'Exact Match'], ['gold_passage_hit_rate', 'Gold passage retrieved'], ['mrr', 'MRR'], ['span_citation_validity', 'Span citation validity']], primary: 'token_f1' },
  averitec: { metrics: [['macro_f1', 'Macro-F1'], ['accuracy', 'Accuracy'], ['quote_citation_validity', 'Quote citation validity'], ['proxy_source_url_hit_rate', 'Proxy: annotated source URL retrieved']], primary: 'macro_f1' }
};
function benchRows(d) { const rows = METHODS.map(m => [...m]); if (d.metrics.oracle) rows.push(ORACLE); return rows; }
function chart(d, key, label) {
  const rows = benchRows(d).filter(([m]) => d.metrics[m]?.[key] !== null && d.metrics[m]?.[key] !== undefined);
  if (!rows.length) return '<p class="empty">This metric is not available for this run.</p>';
  return `<div class="bars" role="img" aria-label="${H(label)} by method">${rows.map(([m, name, c]) => {
    const v = d.metrics[m][key], ci = key === 'token_f1' ? d.metrics[m].token_f1_ci95 : null;
    return `<div class="bar ${m}" style="--c:${c}" data-tip="${H(name)}: ${num(v, 3)}${ci ? ` (95% bootstrap CI ${num(ci[0])}–${num(ci[1])})` : ''} · n=${d.metrics[m].n}"><span>${H(name.replace(' (diagnostic)', ''))}${m === 'oracle' ? ' ◇' : ''}</span>
      <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(1, v)) * 100}%"></div>${ci ? `<div class="ci" style="left:${ci[0] * 100}%;width:${(ci[1] - ci[0]) * 100}%"></div>` : ''}</div><span class="val">${num(v)}</span></div>`;
  }).join('')}</div><p class="small muted">◇ Oracle = reference evidence given directly to the assessor. A diagnostic, not an end-to-end result.${key === 'token_f1' ? ' Whiskers: 95% bootstrap CI.' : ''}</p>`;
}
function metricTable(d) {
  const keys = [...new Set(Object.values(d.metrics).flatMap(v => Object.keys(v).filter(k => typeof v[k] === 'number')))];
  const cols = Object.keys(d.metrics);
  return `<div class="tablewrap"><table class="data"><thead><tr><th>Metric</th>${cols.map(c => `<th>${hum(c)}</th>`).join('')}</tr></thead><tbody>${keys.map(k => `<tr><td>${hum(k)}</td>${cols.map(c => `<td>${num(d.metrics[c][k], k.startsWith('mean_') || k === 'n' || k.includes('changed') ? 1 : 3)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function confusion(d) {
  const L = ['Supported', 'Refuted', 'Not Enough Evidence', 'Conflicting Evidence/Cherry-picking'], short = ['Sup', 'Ref', 'NEE', 'Conf', 'invalid'];
  return Object.entries(d.metrics).map(([m, v]) => `<details><summary>${hum(m)} · confusion matrix (rows = gold)</summary><div class="tablewrap"><table class="data"><thead><tr><th>gold \\ pred</th>${short.map(s => `<th>${s}</th>`).join('')}</tr></thead><tbody>${L.map((g, i) => `<tr><td>${short[i]}</td>${[...L, '(invalid)'].map(p => `<td>${v.confusion_matrix[g][p]}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
    <p class="small muted">Causal-annotated: n=${v.causal_annotated.n}, accuracy ${num(v.causal_annotated.accuracy)}, macro-F1 ${num(v.causal_annotated.macro_f1)} · Other: n=${v.noncausal_annotated.n}, accuracy ${num(v.noncausal_annotated.accuracy)}, macro-F1 ${num(v.noncausal_annotated.macro_f1)}</p></details>`).join('');
}
function sampleView(d) {
  const s = d.samples[state.sample], isFC = d.task === 'extractive_qa';
  const methods = benchRows(d).filter(([m]) => s.methods[m]);
  if (!s.methods[state.sampleMethod]) state.sampleMethod = 'graph_guided';
  const p = s.methods[state.sampleMethod];
  const gold = isFC ? `<dd>${H(s.gold.answer)}</dd>` : `<dd><span class="badge">${H(s.gold.label)}</span>${s.gold.causal_annotated ? ' <span class="pill pending">causal claim (annotated)</span>' : ''}</dd>`;
  const pred = isFC ? `<dd>${H(p.prediction) || '<i>abstained</i>'} <span class="muted small">EM ${p.em} · F1 ${num(p.f1)}</span></dd>` : `<dd><span class="badge">${H(p.prediction)}</span>${p.reconciliation ? `<div class="small muted">${H(p.reconciliation)}</div>` : ''}</dd>`;
  const graph = s.graph ? s.graph.edges.map(e => `${H(s.graph.nodes.find(n => n.id === e.source).label)} → ${H(s.graph.nodes.find(n => n.id === e.target).label)}`).join('; ') : 'none detected (non-causal handling)';
  const ev = p.retrieved.map(x => `<div class="ev ${x.gold ? 'gold' : ''}">${x.gold ? '<span class="mark">GOLD PASSAGE</span> ' : ''}${H(x.text.length > 600 ? x.text.slice(0, 600) + '…' : x.text)}${x.url ? `<div class="meta">${H(x.url)}</div>` : ''}</div>`).join('') || '<p class="empty">No evidence retrieved.</p>';
  return `<div class="seg" role="tablist" aria-label="Method">${methods.map(([m, n]) => `<button role="tab" data-smethod="${m}" aria-selected="${m === state.sampleMethod}">${H(n.replace(' (diagnostic)', ''))}</button>`).join('')}</div>
    <dl class="kv" style="margin-top:12px"><dt>Input</dt><dd>${H(s.input)}</dd><dt>Graph (from input)</dt><dd class="small">${graph}</dd><dt>Prediction</dt>${pred}<dt>Gold</dt>${gold}<dt>Error type</dt><dd>${H(p.error)}</dd><dt>Explanation</dt><dd class="small">${H(p.explanation)}</dd></dl>
    ${p.edges?.length ? `<details><summary>Edge validation</summary>${p.edges.map(e => `<p class="small">${e.edge_id}: ${hum(e.assessor_label)} → <span class="badge ${e.judgment}">${hum(e.judgment)}</span> — ${H(e.reasons.join(' '))}</p>`).join('')}</details>` : ''}
    ${p.quotes?.length ? `<details><summary>Quoted evidence (${p.quotes.length})</summary>${p.quotes.map(q => `<blockquote>${H(q.quote)}<div class="meta">${q.side} · ${hum(q.status)}</div></blockquote>`).join('')}</details>` : ''}
    <details><summary>Retrieved evidence (${p.retrieved.length})${p.queries.length ? ` · ${p.queries.length} quer${p.queries.length > 1 ? 'ies' : 'y'}` : ''}</summary>${p.queries.length ? `<p class="small muted">${p.queries.map(H).join('<br>')}</p>` : ''}${ev}</details>
    ${!isFC && s.gold.qa_evidence ? `<details><summary>Annotated reference evidence (gold, evaluation only)</summary>${s.gold.qa_evidence.map(q => `<p class="small"><b>${H(q.question)}</b><br>${H(q.answers.join(' / '))}</p>`).join('')}</details>` : ''}`;
}
function benchStatus() {
  const card = (name, ds, note) => { const a = latest('benchmarks', ds);
    return `<div class="card"><h3>${name}</h3><p>${a ? `${pill('computed')} Small-sample dev run · n=${a.n} · ${H(a.split)}` : `${pill('pending')} No run saved`}</p><p><span class="pill pending">Pending</span> Full evaluation · not run</p><p class="small muted">${note}</p></div>`; };
  Q('#bench-status').innerHTML = card('FinCausal 2026', 'fincausal2026', 'Extractive QA (EM, token F1) over a controlled corpus with distractors. Not a retrieval benchmark; test gold is not public.') +
    card('AVeriTeC', 'averitec', 'Four-label claim verification (macro-F1). Causal and non-causal claims scored separately. No gold causal graphs; test labels not public.');
}
function causalSplit(d) {
  if (d.task !== 'claim_verification') return '';
  const rows = benchRows(d), g = (m, k) => d.metrics[m]?.[k];
  return `<div class="tablewrap"><table class="data"><caption class="small muted" style="text-align:left">Macro-F1 by claim type (annotated causal vs non-causal). Very small n.</caption><thead><tr><th>Method</th><th>Causal claims</th><th>Non-causal claims</th></tr></thead><tbody>${
    rows.map(([m, n]) => `<tr><td>${H(n)}</td><td>${num(g(m, 'causal_annotated')?.macro_f1)} <span class="muted">(n=${g(m, 'causal_annotated')?.n ?? '—'})</span></td><td>${num(g(m, 'noncausal_annotated')?.macro_f1)} <span class="muted">(n=${g(m, 'noncausal_annotated')?.n ?? '—'})</span></td></tr>`).join('')}</tbody></table></div>`;
}
function benchmarks() {
  benchStatus();
  QA('[data-bench]').forEach(b => b.setAttribute('aria-selected', b.dataset.bench === state.benchName));
  const a = latest('benchmarks', state.benchName), d = state.bench[state.benchName], cfg = BENCH[state.benchName];
  if (!a || !d) { Q('#bench-body').innerHTML = `<div class="panel">${pill('pending')} <b>No computed run saved for this benchmark.</b><p class="muted">The adapter is implemented. Download the official data and run <code>python -m crag.cli bench-run --dataset ${state.benchName}</code>. No score is shown until a run exists.</p></div>`; return; }
  state.metric = cfg.metrics.some(([k]) => k === state.metric) ? state.metric : cfg.primary;
  const r = d.run, ds = d.dataset, label = cfg.metrics.find(([k]) => k === state.metric)[1];
  const tiles = benchRows(d).map(([m, n, c]) => `<div class="tile" style="--c:${c}"><div class="k">${H(n)}</div><div class="v">${num(d.metrics[m]?.[cfg.primary])}</div><div class="k">${cfg.metrics[0][1]}</div></div>`).join('');
  Q('#bench-body').innerHTML = `
    <div class="runline">${pill(r.status)} <span><b>${state.benchName === 'averitec' ? 'AVeriTeC' : 'FinCausal 2026'}</b> · split <b>${H(ds.split)}</b> · n=${ds.n_cases} · ${H(r.model)} · ${H(r.created_utc.slice(0, 10))} · budget ${r.budget_passages} passages · ${r.repeats} repeat · cost $${num(r.usage?.cost_usd_recorded)}</span></div>
    <p class="caution">Small development sample (n=${ds.n_cases}): differences between methods are descriptive and within noise. Not a benchmark score and not evidence of superiority.</p>
    <div class="tiles">${tiles}</div>
    ${causalSplit(d)}
    <details class="panel"><summary>Charts, all metrics and confusion matrices</summary><div class="chart-wrap"><div class="chart-head"><h2 class="h3" style="margin:0">${H(label)}</h2><label>Metric <select id="metric">${cfg.metrics.map(([k, l]) => `<option value="${k}" ${k === state.metric ? 'selected' : ''}>${l}</option>`).join('')}</select></label></div>
      ${chart(d, state.metric, label)}<details><summary>Table view: all metrics</summary>${metricTable(d)}</details>${d.task === 'claim_verification' ? `<details><summary>Confusion matrices &amp; causal vs non-causal claims</summary>${confusion(d).replaceAll('<details>', '<details class="inner">')}</details>` : ''}
      ${d.graph_construction_eval ? `<details><summary>Graph construction (evaluated separately)</summary><p class="small">${H(d.graph_construction_eval.note)} Detected &amp; annotated causal: ${d.graph_construction_eval.tp} · detected only: ${d.graph_construction_eval.fp} · annotated only: ${d.graph_construction_eval.fn} · neither: ${d.graph_construction_eval.tn}.</p></details>` : ''}</div></details>
    <details class="panel"><summary>Data, split and provenance</summary><p class="small">${H(ds.citation)} <a href="${H(ds.dataset_doi || ds.paper)}" target="_blank" rel="noopener">source</a> · licence ${H(ds.license)}</p>
      ${['split_note', 'corpus_note', 'relevance_note', 'multi_step_note', 'time_note', 'sampling_note'].filter(k => ds[k]).map(k => `<p class="small"><b>${hum(k.replace('_note', ''))}:</b> ${H(ds[k])}</p>`).join('')}
      <p class="small"><b>Config:</b> ${H(JSON.stringify(d.config))} · provider ${H(r.provider)} · cache ${H(r.llm_cache_namespace)} · artifact <a href="${H(a.path)}">${H(a.path)}</a></p></details>
    <details class="panel"><summary>Inspect samples</summary>
    <div class="samples"><div class="slist" role="list">${d.samples.map((s, i) => { const p = s.methods.graph_guided; const ok = d.task === 'extractive_qa' ? p.em : p.prediction === s.gold.label;
      return `<button role="listitem" data-sample="${i}" aria-pressed="${i === state.sample}">${ok ? '✓' : '✗'} ${H(s.input.slice(0, 90))}${s.input.length > 90 ? '…' : ''}</button>`; }).join('')}</div>
    <div class="panel" id="sample-view">${sampleView(d)}</div></div></details>`;
}

/* ---------------- wiring */
document.addEventListener('click', e => {
  const t = e.target.closest('[data-bench],[data-sample],[data-smethod],[data-view],[data-pocview],#bny-graph .e');
  if (!t) return;
  if (t.dataset.bench) { state.benchName = t.dataset.bench; state.sample = 0; state.metric = null; benchmarks(); }
  else if (t.dataset.sample) { state.sample = +t.dataset.sample; benchmarks(); }
  else if (t.dataset.smethod) { state.sampleMethod = t.dataset.smethod; Q('#sample-view').innerHTML = sampleView(state.bench[state.benchName]); }
  else if (t.dataset.pocview) { state.pocView = t.dataset.pocview; experiment(); }
  else if (t.dataset.view) { ['new', 'orig'].forEach(v => Q('#bny-' + v).hidden = v !== t.dataset.view); QA('[data-view]').forEach(b => b.setAttribute('aria-selected', b === t)); }
  else if (t.dataset.edge) { state.edge = t.dataset.edge; bny(); }
});
document.addEventListener('keydown', e => { const t = e.target.closest?.('#bny-graph .e'); if (t && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); state.edge = t.dataset.edge; bny(); Q(`#bny-graph [data-edge="${state.edge}"]`)?.focus(); } });
document.addEventListener('change', e => { if (e.target.id === 'metric') { state.metric = e.target.value; benchmarks(); } });
addEventListener('hashchange', showTab);

(async function init() {
  showTab();
  try { state.record = await getJSON('results.json'); } catch { state.record = null; }
  try { state.index = await getJSON('artifacts/index.json'); } catch { state.index = { artifacts: [] }; }
  const b = latest('bny', null, 'bny_three_method'), pc = (state.index.artifacts || []).find(a => a.name.startsWith('bny_poc') && a.name.endsWith('__reviewed_v2') && a.status === 'computed') || latest('bny', null, 'bny_poc'), po = (state.index.artifacts || []).find(a => a.name === 'bny_poc_E3_E4_E5__llm');
  if (b) try { state.bny = await getJSON(b.path); } catch { state.bny = null; }
  if (pc) try { state.poc = await getJSON(pc.path); state.pocPath = pc.path; state.pocOrigPath = po && po.path !== pc.path ? po.path : ''; } catch { state.poc = null; }
  for (const ds of ['fincausal2026', 'averitec']) { const a = latest('benchmarks', ds); if (a) try { state.bench[ds] = await getJSON(a.path); } catch {} }
  experiment(); bny(); benchmarks();
})();
