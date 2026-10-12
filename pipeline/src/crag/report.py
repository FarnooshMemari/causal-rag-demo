"""Render outputs/comparison.md (side-by-side ordinary vs graph-guided) from saved outputs."""
import json
from collections import Counter

from .common import OUT, load
from .retrieval import chunk_lookup


def _short(t, n=170):
    t = " ".join(t.split())
    return t if len(t) <= n else t[:n] + "..."


def run():
    graph, event = load("graph.json"), load("event.json")
    ret = json.loads((OUT / "retrieval.json").read_text())
    asm = json.loads((OUT / "assessments.json").read_text())
    met = json.loads((OUT / "metrics.json").read_text())
    lk = chunk_lookup()
    L = []
    L.append("# Ordinary vs graph-guided retrieval: side-by-side\n")
    L.append(f"Event: {event['description']}. Cutoff {event['decision_cutoff']}. Budget: {ret['budget_total_chunks']} chunks per strategy "
             f"({ret['per_edge_k']} per edge for graph-guided). Eligible after time filter: {ret['n_chunks_eligible_after_time_filter']} chunks "
             f"from {ret['n_docs_eligible']} documents; excluded by filter: {', '.join(ret['excluded_docs_by_time_filter'])}.\n")
    L.append("> Relevance grades (`g=`) are **model-generated provisional labels** pending human review (annotations/relevance_annotation_sheet.csv).\n")

    rp = met["retrieval_provisional"]
    L.append("## Retrieval summary (provisional labels)\n")
    L.append("| metric | ordinary (1 broad query) | graph-guided (5 edge queries) |\n|---|---|---|")
    for k, lab in [("edges_covered_by_grade2", "edges with >=1 directly relevant chunk (of 5)"), ("slots_grade2_for_some_edge", "budget slots directly relevant to some edge (of 20)"),
                   ("unique_chunks", "unique chunks"), ("distinct_docs", "distinct documents")]:
        L.append(f"| {lab} | {rp['ordinary'][k]} | {rp['graph_guided'][k]} |")
    L.append(f"| document types | {rp['ordinary']['doc_types']} | {rp['graph_guided']['doc_types']} |")
    L.append("\nPer edge: directly-relevant (grade 2) chunks among those the assessor sees for that edge\n")
    L.append("| edge | ordinary: grade2 / offered | graph-guided: grade2 / offered |\n|---|---|---|")
    for e in graph["edges"]:
        o, g = rp["ordinary"]["per_edge"][e["id"]], rp["graph_guided"]["per_edge"][e["id"]]
        L.append(f"| {e['id']} {e['source']}→{e['target']} | {o['n_grade2']} / {o['chunks_offered']} | {g['n_grade2']} / {g['chunks_offered']} |")

    if asm.get("conditions"):
        am = met["assessment"]
        L.append("\n## Assessment summary (3 repeats each, identical inputs)\n")
        L.append("| metric | ordinary | graph-guided |\n|---|---|---|")
        for k in ["citation_validity", "label_evidence_consistency", "abstention_rate_validated", "conflict_rate_observed", "repeat_full_agreement_rate", "pairwise_label_agreement"]:
            L.append(f"| {k} | {am['ordinary'][k]} | {am['graph_guided'][k]} |")
        L.append(f"| quotes (valid/total) | {am['ordinary']['n_valid_quotes']}/{am['ordinary']['n_quotes']} | {am['graph_guided']['n_valid_quotes']}/{am['graph_guided']['n_quotes']} |")

        L.append("\n## Edge labels and encodings (validated label per repeat; code +1/0/-1)\n")
        L.append("| edge | ordinary r0, r1, r2 | graph-guided r0, r1, r2 |\n|---|---|---|")
        code = {"supported": "+1", "contradicted": "-1", "insufficient_evidence": "0"}
        for e in graph["edges"]:
            o = am["ordinary"]["labels_by_edge_across_repeats"][e["id"]]
            g = am["graph_guided"]["labels_by_edge_across_repeats"][e["id"]]
            fmt = lambda v: ", ".join(f"{x} ({code[x]})" for x in v)
            L.append(f"| {e['id']} | {fmt(o)} | {fmt(g)} |")
        L.append("\n### Pathway status (rule: chain_supported only if every edge supported; chain_broken if any edge contradicted; else chain_incomplete)\n")
        L.append("| pathway | ordinary r0/r1/r2 | graph-guided r0/r1/r2 |\n|---|---|---|")
        for pid in graph["pathways"]:
            f = lambda c: " / ".join(f"{p[pid]['status']} {p[pid]['edge_codes']}" for p in am[c]["pathways_by_repeat"])
            L.append(f"| {pid} | {f('ordinary')} | {f('graph_guided')} |")
        L.append("\nCodes are illustrative ordinal encodings of evidence labels; they are not probabilities, effect sizes or forecasts.\n")

    L.append("\n## Per-edge detail\n")
    rel = {}
    import csv
    from .common import ANNOT
    for row in csv.DictReader(open(ANNOT / "relevance_annotation_sheet.csv")):
        rel[(row["edge_id"], row["chunk_id"])] = row["model_provisional_grade"]
    for e in graph["edges"]:
        L.append(f"### {e['id']}: {e['source']} → {e['target']} (assumed sign {e['assumed_sign']:+d})\n")
        L.append(f"*Edge question:* {e['retrieval_question']}\n")
        L.append("**Graph-guided top-4**\n")
        for r in ret["graph_guided"][e["id"]]["results"]:
            L.append(f"- `{r['chunk_id']}` (bm25 {r['score']}, g={rel.get((e['id'], r['chunk_id']), '?')}): {_short(lk[r['chunk_id']]['text'])}")
        o_rel = [r for r in ret["ordinary"]["results"] if rel.get((e["id"], r["chunk_id"])) == "2"]
        L.append(f"\n**Ordinary top-20 chunks graded directly relevant to this edge:** {len(o_rel)}")
        for r in o_rel[:4]:
            L.append(f"- `{r['chunk_id']}`: {_short(lk[r['chunk_id']]['text'])}")
        if asm.get("conditions"):
            for cond in ("graph_guided", "ordinary"):
                it = next(x for x in asm["conditions"][cond][0]["edges"] if x["edge_id"] == e["id"])
                L.append(f"\n**{cond} assessment (repeat 0): {it['validated_label']}** (raw {it['label']}, conflict={it.get('conflict_observed')})")
                for side in ("supporting_evidence", "contradicting_evidence"):
                    for q in it[side]:
                        L.append(f"- {side.split('_')[0]} [{q['citation_status']}] `{q['chunk_id']}`: \"{_short(q['quote'], 260)}\"")
                L.append(f"- explanation: {it['explanation']}")
        L.append("")

    if asm.get("controls"):
        L.append("## Controls\n")
        for k, v in asm["controls"].items():
            r = v["result"]
            L.append(f"- **{k}**: {v['description']} → observed `{r['validated_label']}`"
                     + (f"; passed={v['passed']}" if "passed" in v else "") + (f". Explanation: {r['explanation']}" if r.get("explanation") else ""))
    L.append("\n## Future-document exclusion\n")
    fe = ret["future_exclusion_check"]
    L.append(f"- Future chunks in filtered results: {fe['future_chunks_in_filtered_results'] or 'none'} → passed={fe['passed']}")
    L.append(f"- Without the filter the same queries would have returned future chunks: " +
             "; ".join(f"{k}: {v}" for k, v in fe["future_chunks_that_unfiltered_retrieval_would_have_returned"].items() if v))
    (OUT / "comparison.md").write_text("\n".join(L) + "\n")
    print(f"wrote {OUT/'comparison.md'}")
