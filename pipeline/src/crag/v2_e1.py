"""Exploratory v2 correction for edge E1 only (post-hoc; see config/v2/e1_v2.json provenance).

    PYTHONPATH=src python -m crag.v2_e1 build                 # offline: retrieval + prompts + checks, no LLM
    PYTHONPATH=src python -m crag.v2_e1 assess --allow-llm    # LLM step (3 repeats x 2 conditions = 6 calls)

v1 files are never read for writing: outputs go to outputs/v2_e1/, LLM cache to cache/llm_e1_v2/.
Everything else (corpus, cutoff, filter, BM25, budget, provider/model, E2-E5) is reused unchanged.
"""
import argparse
import json
import re
from datetime import datetime

from .assess import SYSTEM as SYSTEM_V1, _norm
from .common import CONFIG, CORPUS, OUT, cutoff, load, read_jsonl, write_json
from .retrieval import BUDGET, BM25, time_filter

VERSION = "e1_v2"
V2_OUT = OUT / "v2_e1"
N_REPEATS = 3
LABELS = ["supported", "contradicted", "insufficient_evidence"]
EVIDENCE_TYPES = ["demand_linked_outlook_change", "demand_without_outlook_improvement", "offsetting_mechanism",
                  "historical_results", "guidance_unchanged", "demand_context", "other_context"]


def spec():
    return json.loads((CONFIG / "v2" / "e1_v2.json").read_text())


def system_prompt(s):
    c = s["edge"]["criteria"]
    return SYSTEM_V1 + f"""

Edge-specific criteria for E1 (version {VERSION}). These REPLACE the general label definitions in rule 3 for this edge:
- supported: {c['supported']}
- contradicted: {c['contradicted']}
- insufficient_evidence: {c['insufficient_evidence']}

Additional rules for E1:
8. Timing: documents published before the retail-sales release (2023-08-15 08:30 ET) are economic CONTEXT. They cannot be reactions to the July retail-sales surprise; never describe them as such.
9. Tag every quote with evidence_type: demand_linked_outlook_change (the quote itself ties a forward guidance/outlook change to consumer demand), demand_without_outlook_improvement (stronger demand stated, outlook not improved), offsetting_mechanism (states what offsets demand, e.g. margins/costs), historical_results (realised past sales/earnings), guidance_unchanged, demand_context, other_context.
10. Every substantive point in the explanation, including any number, must come from a quote you list (supporting, contradicting or context_evidence). Put quotes that inform the reasoning but support neither side in context_evidence."""


def schema():
    ev = {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                     "required": ["doc_id", "chunk_id", "quote", "evidence_type"],
                                     "properties": {"doc_id": {"type": "string"}, "chunk_id": {"type": "string"},
                                                    "quote": {"type": "string"}, "evidence_type": {"type": "string", "enum": EVIDENCE_TYPES}}}}
    item = {"type": "object", "additionalProperties": False,
            "required": ["edge_id", "label", "supporting_evidence", "contradicting_evidence", "context_evidence", "conflict", "explanation"],
            "properties": {"edge_id": {"type": "string"}, "label": {"type": "string", "enum": LABELS},
                           "supporting_evidence": ev, "contradicting_evidence": ev, "context_evidence": ev,
                           "conflict": {"type": "boolean"}, "explanation": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False, "required": ["assessments"],
            "properties": {"assessments": {"type": "array", "items": item}}}


def _timing(avail_iso, release):
    a = datetime.fromisoformat(avail_iso)
    return "pre_release_context" if a < release else "release_document" if a == release else "post_release"


def build_prompt(s, chunks, event):
    release = datetime.fromisoformat(event["release_timestamp"])
    e, n = s["edge"], s["nodes"]
    excerpts = "\n\n".join(
        f'<excerpt chunk_id="{c["chunk_id"]}" doc_id="{c["doc_id"]}" available_at="{c["available_at_et"]}" timing="{_timing(c["available_at_et"], release)}">\n{c["text"]}\n</excerpt>'
        for c in chunks)
    return (f"Decision time: {event['decision_cutoff']} (US Eastern). Event: {event['description']}; first-release actual "
            f"+{event['first_release_actual']['headline_mom_pct']}% m/m vs consensus +{event['consensus']['headline_mom_pct']}%, "
            f"released {event['release_timestamp']}. {n['consumer_demand']['event_context']}\n\n"
            f"Assess this hypothesised link (return exactly one assessment, edge_id E1):\n"
            f"- edge_id: E1\n  link: stronger \"{n['consumer_demand']['label']}\" -> improved \"{n['forward_earnings_expectations']['label']}\"\n"
            f"  condition under which theory expects it: {e['condition']}\n  question: {e['retrieval_question']}"
            f"\n\nExcerpts ({len(chunks)}), all published at or before the decision time:\n\n{excerpts}")


# ---------------------------------------------------------------- validation (deterministic)
NUM = re.compile(r"\d+(?:[.,]\d+)?")


def validate(item, supplied, lookup):
    out = dict(item)
    for side in ("supporting_evidence", "contradicting_evidence", "context_evidence"):
        res = []
        for ev in item[side]:
            cid = ev["chunk_id"]
            status = ("chunk_not_supplied" if cid not in supplied else
                      "doc_id_mismatch" if lookup[cid]["doc_id"] != ev["doc_id"] else
                      "quote_not_found_in_chunk" if not ev["quote"].strip() or _norm(ev["quote"]) not in _norm(lookup[cid]["text"]) else "valid")
            res.append({**ev, "citation_status": status})
        out[side] = res
    valid = lambda side, t=None: [e for e in out[side] if e["citation_status"] == "valid" and (t is None or e["evidence_type"] in t)]
    all_valid = valid("supporting_evidence") + valid("contradicting_evidence") + valid("context_evidence")
    rule_ok = {
        "supported": bool(valid("supporting_evidence", {"demand_linked_outlook_change"})),
        "contradicted": bool(valid("contradicting_evidence", {"demand_without_outlook_improvement"}))
                        and any(e["evidence_type"] == "offsetting_mechanism" for e in all_valid),
        "insufficient_evidence": True,
    }[item["label"]]
    quoted = " ".join(_norm(e["quote"]) for e in all_valid)
    unquoted_numbers = sorted({n for n in NUM.findall(item["explanation"]) if n not in quoted})
    out.update({
        "validated_label": item["label"] if rule_ok else "insufficient_evidence",
        "meets_v2_criteria": rule_ok,
        "explanation_numbers_not_in_quotes": unquoted_numbers,
        "conflict_observed": bool(valid("supporting_evidence")) and bool(valid("contradicting_evidence")),
        "code": {"supported": 1, "contradicted": -1, "insufficient_evidence": 0}[item["label"] if rule_ok else "insufficient_evidence"],
        "note": "evidence_type tags are model-assigned; code verifies quotes, not the semantics of the tags",
    })
    return out


# ---------------------------------------------------------------- build (offline)
def build():
    s, event, graph = spec(), load("event.json"), load("graph.json")
    cut = cutoff()
    chunks = read_jsonl(CORPUS / "chunks.jsonl")
    lookup = {c["chunk_id"]: c for c in chunks}
    future = {d["doc_id"] for d in read_jsonl(CORPUS / "manifest.jsonl") if d["role"] != "corpus"}
    eligible = time_filter(chunks, cut)
    index = BM25(eligible)
    per_edge = BUDGET // len(graph["edges"])  # unchanged: 4
    ordinary = index.top(graph["ordinary_baseline"]["query"], BUDGET)        # unchanged v1 broad query
    guided = index.top(s["edge"]["retrieval_query"], per_edge)               # new E1 v2 query
    v1_guided = index.top(next(e for e in graph["edges"] if e["id"] == "E1")["retrieval_query"], per_edge)

    sysp, sch = system_prompt(s), schema()
    prompts = {"ordinary": build_prompt(s, ordinary, event), "graph_guided": build_prompt(s, guided, event)}
    V2_OUT.mkdir(parents=True, exist_ok=True)
    (V2_OUT / "prompts").mkdir(exist_ok=True)
    (V2_OUT / "prompts" / "system.txt").write_text(sysp)
    write_json(V2_OUT / "prompts" / "schema.json", sch)
    for k, p in prompts.items():
        (V2_OUT / "prompts" / f"{k}_user.txt").write_text(p)

    from .llm import cache_path
    checks = {}
    ids_in = {k: re.findall(r'<excerpt chunk_id="([^"]+)"', p) for k, p in prompts.items()}
    checks["budget_unchanged"] = len(ordinary) == BUDGET and len(guided) == per_edge == 4
    checks["no_future_doc_in_retrieval"] = not ({c["doc_id"] for c in ordinary + guided} & future)
    checks["no_future_doc_in_prompts"] = not any(f in p for p in prompts.values() for f in future)
    checks["prompts_contain_exactly_retrieved_chunks"] = ids_in["ordinary"] == [c["chunk_id"] for c in ordinary] and ids_in["graph_guided"] == [c["chunk_id"] for c in guided]
    checks["all_prompt_chunks_at_or_before_cutoff"] = all(datetime.fromisoformat(lookup[i]["available_at_et"]) <= cut for v in ids_in.values() for i in v)
    checks["v2_cache_dir_separate_from_v1"] = all(cache_path(sysp, p, sch, r, VERSION).parent.name == "llm_e1_v2" for p in prompts.values() for r in range(N_REPEATS))
    pending = {f"{k}_r{r}": {"cache_file": str(cache_path(sysp, p, sch, r, VERSION).relative_to(OUT.parent)),
                             "status": "cached" if cache_path(sysp, p, sch, r, VERSION).exists() else "PENDING (no LLM call made)"}
               for k, p in prompts.items() for r in range(N_REPEATS)}
    strip = lambda rs: [{"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "score": r["score"]} for r in rs]
    res = {
        "version": VERSION, "provenance": s["provenance"],
        "cutoff": cut.isoformat(), "n_chunks_eligible": len(eligible),
        "ordinary": {"query": graph["ordinary_baseline"]["query"], "note": "same 20 chunks as v1; v2 assesses E1 alone against them (v1 judged all 5 edges in one call)", "results": strip(ordinary)},
        "graph_guided": {"question": s["edge"]["retrieval_question"], "query": s["edge"]["retrieval_query"], "results": strip(guided)},
        "v1_graph_guided_E1_for_comparison": strip(v1_guided),
        "offline_checks": checks,
        "llm_assessment_status": pending,
    }
    write_json(V2_OUT / "retrieval_and_status.json", res)
    print(f"v2 E1 graph-guided: {[r['chunk_id'] for r in guided]}")
    print(f"v1 E1 graph-guided: {[r['chunk_id'] for r in v1_guided]}")
    print(f"ordinary (unchanged): {len(ordinary)} chunks")
    for k, v in checks.items():
        print(f"[{'PASS' if v else 'FAIL'}] {k}")
    print(f"LLM assessments: {sum(v['status'].startswith('PENDING') for v in pending.values())}/{len(pending)} PENDING")
    if not all(checks.values()):
        raise SystemExit("offline checks failed")
    return res


def assess(allow_llm):
    if not allow_llm:
        raise SystemExit("Refusing to call the LLM without --allow-llm (6 calls, est. < $0.30).")
    from .llm import complete_json
    s, event = spec(), load("event.json")
    lookup = {c["chunk_id"]: c for c in read_jsonl(CORPUS / "chunks.jsonl")}
    ret = json.loads((V2_OUT / "retrieval_and_status.json").read_text())
    sysp, sch = system_prompt(s), schema()
    out = {"version": VERSION, "provenance": s["provenance"], "conditions": {}}
    for cond in ("ordinary", "graph_guided"):
        chunks = [lookup[r["chunk_id"]] for r in ret[cond]["results"]]
        user = build_prompt(s, chunks, event)
        assert user == (V2_OUT / "prompts" / f"{cond}_user.txt").read_text(), "prompt drift since build"
        for r in range(N_REPEATS):
            o, _ = complete_json(sysp, user, sch, repeat=r, tag=f"v2_E1_{cond}", version=VERSION)
            item = next((a for a in o["assessments"] if a["edge_id"] == "E1"), None)
            res = validate(item, {c["chunk_id"] for c in chunks}, lookup) if item else {"error": "E1 missing", "validated_label": "insufficient_evidence"}
            out["conditions"].setdefault(cond, []).append({"repeat": r, **res})
    write_json(V2_OUT / "assessments.json", out)
    for cond, runs in out["conditions"].items():
        print(cond, [x["validated_label"] for x in runs])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["build", "assess"])
    p.add_argument("--allow-llm", action="store_true")
    a = p.parse_args()
    build() if a.step == "build" else assess(a.allow_llm)


if __name__ == "__main__":
    main()
