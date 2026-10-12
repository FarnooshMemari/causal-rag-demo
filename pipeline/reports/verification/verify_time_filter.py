"""Fresh, read-only verification of the point-in-time filter (no LLM calls, no file writes)."""
import glob
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/far/causal-rag-mvp")
sys.path.insert(0, str(ROOT / "src"))
from crag import llm  # noqa: E402
from crag.assess import build_prompt  # noqa: E402
from crag.common import CORPUS, available_at, cutoff, load, read_jsonl  # noqa: E402
from crag.retrieval import BUDGET, BM25, chunk_doc, time_filter  # noqa: E402

# Guard: any attempt to reach a model fails loudly.
def _no_llm(*a, **k):
    raise AssertionError("LLM call attempted")
llm._claude_cli = llm._anthropic = llm._openai = _no_llm

results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))

def snapshot():
    files = sorted(glob.glob(str(ROOT / "data/corpus/**/*"), recursive=True)) + sorted(glob.glob(str(ROOT / "data/raw/*")))
    return {f: hashlib.sha256(open(f, "rb").read()).hexdigest() for f in files if Path(f).is_file()}

before = snapshot()

# ---- cutoff, timezone-aware
cut = cutoff()
print("cutoff:", cut.isoformat(), "| UTC:", cut.astimezone(timezone.utc).isoformat())
check("cutoff is timezone-aware", cut.tzinfo is not None and cut.utcoffset() is not None)
check("cutoff == 2023-08-15 14:00 UTC", cut == datetime(2023, 8, 15, 14, 0, tzinfo=timezone.utc))

# ---- fresh chunks, in memory, from stored corpus text
manifest = read_jsonl(CORPUS / "manifest.jsonl")
chunks = []
for d in manifest:
    avail = available_at(d["published_at"], d["timestamp_precision"])  # recomputed, not read from manifest
    assert avail.tzinfo is not None, d["doc_id"]
    for c in chunk_doc(d["doc_id"], (ROOT / d["text_file"]).read_text()):
        c.update(available_at_et=avail.isoformat(), role=d["role"])
        chunks.append(c)
print(f"\nfresh chunks: {len(chunks)} from {len(manifest)} manifest docs")

future = [d for d in manifest if d["role"] == "future_exclusion_test"]
print("\nPost-cutoff test documents in manifest:")
FUT = set()
for d in future:
    a = available_at(d["published_at"], d["timestamp_precision"])
    FUT.add(d["doc_id"])
    print(f"  {d['doc_id']:30s} published_at={d['published_at']:26s} precision={d['timestamp_precision']:5s} "
          f"available={a.isoformat()} ({a.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}) after_cutoff={a > cut}")
check("exactly 3 post-cutoff test docs in manifest", len(FUT) == 3, sorted(FUT))
check("every post-cutoff doc available strictly after cutoff", all(available_at(d["published_at"], d["timestamp_precision"]) > cut for d in future))
check("post-cutoff docs actually have chunks to exclude", all(any(c["doc_id"] == f for c in chunks) for f in FUT),
      {f: sum(c["doc_id"] == f for c in chunks) for f in FUT})

# ---- filter stage
eligible = time_filter(chunks, cut)
elig_docs = {c["doc_id"] for c in eligible}
check("filter stage: no post-cutoff doc among eligible chunks", not (elig_docs & FUT), f"{len(eligible)} eligible chunks, {len(elig_docs)} docs")
check("filter stage: all eligible chunks <= cutoff (tz-aware compare)", all(datetime.fromisoformat(c["available_at_et"]) <= cut for c in eligible))

d01 = next(d for d in manifest if d["doc_id"] == "D01_census_retail_2023_07")
d01_av = available_at(d01["published_at"], d01["timestamp_precision"])
print(f"\nD01 available {d01_av.isoformat()} = {d01_av.astimezone(timezone.utc).strftime('%H:%M UTC')}; margin before cutoff = {cut - d01_av}")
check("D01 eligible after filter", "D01_census_retail_2023_07" in elig_docs, f"{sum(c['doc_id']=='D01_census_retail_2023_07' for c in eligible)} D01 chunks eligible")

# ---- fresh retrieval, both strategies
graph, event = load("graph.json"), load("event.json")
index = BM25(eligible)
per_edge = BUDGET // len(graph["edges"])
ordinary = index.top(graph["ordinary_baseline"]["query"], BUDGET)
guided = {e["id"]: index.top(e["retrieval_query"], per_edge) for e in graph["edges"]}
ret_ids = {c["chunk_id"] for c in ordinary} | {c["chunk_id"] for v in guided.values() for c in v}
print(f"\nordinary retrieved {len(ordinary)} chunks; graph-guided retrieved {sum(map(len, guided.values()))} chunks")
check("retrieval stage (ordinary): no post-cutoff doc", not ({c['doc_id'] for c in ordinary} & FUT))
check("retrieval stage (graph-guided): no post-cutoff doc", not ({c['doc_id'] for v in guided.values() for c in v} & FUT))
print("D01 chunks retrieved: ordinary", [c["chunk_id"] for c in ordinary if c["doc_id"].startswith("D01")],
      "| graph", [c["chunk_id"] for v in guided.values() for c in v if c["doc_id"].startswith("D01")])

# Counterfactual: without the filter, would these queries reach future docs? (shows the test is not vacuous)
unf = BM25(chunks)
leak = {"ordinary": [c["chunk_id"] for c in unf.top(graph["ordinary_baseline"]["query"], BUDGET) if c["doc_id"] in FUT]}
leak.update({e["id"]: [c["chunk_id"] for c in unf.top(e["retrieval_query"], per_edge) if c["doc_id"] in FUT] for e in graph["edges"]})
n_leak = sum(map(len, leak.values()))
print("counterfactual unfiltered leaks:", {k: v for k, v in leak.items() if v})
check("counterfactual: unfiltered retrieval WOULD retrieve post-cutoff chunks (test is non-vacuous)", n_leak > 0, f"{n_leak} chunks")

# ---- evidence passed to the LLM: build the exact prompts the assessor would send (no call)
nodes = {n["id"]: n["label"] for n in graph["nodes"]}
prompts = {"ordinary": build_prompt(graph["edges"], ordinary, nodes, event)}
prompts.update({f"graph_{e['id']}": build_prompt([e], guided[e["id"]], nodes, event) for e in graph["edges"]})
bad = {k: [f for f in FUT if f in p] for k, p in prompts.items()}
check("LLM-input stage (fresh prompts): no post-cutoff doc id in any of 6 prompts", not any(bad.values()), {k: v for k, v in bad.items() if v} or "")
import re
for k, p in prompts.items():
    ids = re.findall(r'<excerpt chunk_id="([^"]+)"', p)
    assert set(ids) <= ret_ids
check("LLM-input stage: prompts contain only retrieved chunks", True)
check("D01 evidence present in LLM input (ordinary prompt)", "D01_census_retail_2023_07" in prompts["ordinary"])

# Cross-check: prompts actually sent in the saved run (cache records), read-only
recs = [json.load(open(f)) for f in glob.glob(str(ROOT / "cache/llm/*.json"))]
sent_bad = [(r["tag"], f) for r in recs for f in FUT if f in r["user"]]
check(f"historical LLM inputs ({len(recs)} cached calls): no post-cutoff doc id", not sent_bad, sent_bad or "")
fresh_match = all(any(r["user"] == p for r in recs) for p in prompts.values())
print(f"fresh prompts byte-identical to prompts sent in saved run: {fresh_match}")

after = snapshot()
check("no corpus/raw file modified (sha256 before == after)", before == after, f"{len(before)} files hashed")
print(f"\nSUMMARY: {sum(ok for _, ok in results)}/{len(results)} checks passed -> {'PASS' if all(ok for _, ok in results) else 'FAIL'}")
