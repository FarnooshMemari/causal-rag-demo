# Causal RAG MVP: feasibility summary

Duke × BNY capstone · frozen 2026-10-06 · from saved results only (`reports/FREEZE.sha256`)

**Question:** can a predefined economic graph guide point-in-time retrieval and traceable edge assessments? Causality and portfolio performance are out of scope.

## Setup

- **Event:** Census advance retail sales for July 2023, released 2023-08-15 08:30 EDT. Actual +0.7% m/m against a +0.4% consensus.
- **Cutoff:** 2023-08-15 10:00 EDT (14:00 UTC).
- **Corpus:** 19 pre-cutoff primary documents (statistical releases, Fed publications, six 8-Ks), plus 3 post-cutoff filter tests. 364 chunks, 281 eligible.
- **Retrieval:** BM25, 20-chunk budget each. Ordinary: one broad query. Graph-guided: 4 chunks × 5 edge queries.
- **Assessor:** an LLM labels edges supported, contradicted or insufficient_evidence; code checks quotes are verbatim.
- **Cost:** $1.3370356 over 53 calls, summed from unrounded CLI-reported amounts.

## Findings

1. **Time filter.** No post-cutoff chunks were retrieved; unfiltered, 8 would have been. D01 (08:30) stayed eligible. A session re-check passed 16/16, but its log is unavailable (`reports/verification/`). This tests filter logic, not timestamp correctness, and cannot remove the model's training knowledge.
2. **v1 E1 definition error.** The v1 target "expected earnings / revenues" let realised sales count. Graph-guided v1 labelled E1 supported from McDonald's Q2 revenue and called Home Depot's falling sales contradiction, though weak demand with weak results fits the edge's sign.
3. **Exploratory v2 correction.** E1 was redefined as consumer demand → forward earnings guidance, with explicit criteria. Pre-release documents count as context. Designed after inspecting v1, so not an independent test; v1 preserved.
4. **Coverage audit (provisional).** No explicit demand-to-guidance link exists in searchable or omitted text. Closest miss: Coca-Cola credited its guidance raise to "first half results" and resiliency, not demand. Mainly a corpus limitation.
5. **Real-data v2.** 3/3 insufficient_evidence in each condition; all quotes valid. An abstention check, not validation.
6. **Synthetic tests.**
    - r1: 2/3 PASS. The explicit-support fixture was discounted as "not a real document".
    - r2: 3/3 PASS. Disclosed revision, designed after r1: an added instruction to treat fictional statements as given premises, not assess authenticity.

   Both test interpretation of controlled text, not real documents.

## Feasible

Point-in-time corpora with timestamp evidence, an effective time filter, verbatim chunk-level citations, repeatable labels, abstention when evidence is absent, and pre-registered synthetic checks.

## Unproven

- **Semantic support.** Quote validation shows that a quote exists, not that it supports the edge; v1's valid quotes were misapplied.
- **False-negative risk.** Unresolved: no real supporting passage has been tested, and r2 passed only once the authenticity check was switched off.
- **Meaning of "contradicted".** Edges are conditional. "Contradicted" means the antecedent held (stronger demand) but the expected effect failed, with an offsetting mechanism stated. It does not mean the mechanism is false in general.
- **Also not established:** causal identification, any portfolio benefit, graph-guided superiority, human-reviewed labels, and generalisation beyond one event.

## Next experiment

Pick another retail-sales event before examining its documents, with a real pre-cutoff company disclosure explicitly tying a guidance change to consumer demand. Pre-register the frozen v2 criteria, that passage and its hidden expected label, the queries, and 3 repeats per condition.

**Pass:** E1 gets the expected label, citing that passage, in both retrieval conditions.
