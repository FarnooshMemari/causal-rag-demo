"""Chunking, Okapi BM25, point-in-time filter, ordinary vs graph-guided retrieval.

Design choices (documented in README):
- Chunks: paragraph-packed, target ~170 words, hard max ~260 words; long paragraphs split at
  sentence boundaries. No overlap (keeps chunk IDs stable and quotes unambiguous).
- The time filter is applied BEFORE indexing: the BM25 index (including IDF statistics) is
  built only from documents available at the cutoff, so future documents cannot even
  influence term weights.
- Equal budget: ordinary = top-K for one broad query; graph-guided = K / n_edges per edge
  query. Same corpus, tokenizer, BM25 parameters.
"""
import math
import re
from collections import Counter

from .common import CORPUS, OUT, ROOT, cutoff, load, read_jsonl, write_json, write_jsonl
from datetime import datetime

TARGET_WORDS, MAX_WORDS = 170, 260
BUDGET = 20  # total chunks per retrieval strategy
STOP = set("""a an and are as at be been but by for from has have in is it its of on or that the
their this to was were which will with we our not than these those also into over more such""".split())


def tokenize(text):
    toks = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
    return [_stem(t) for t in toks if t not in STOP and len(t) > 1]


def _stem(t):
    # tiny suffix stripper; enough to match "prices/price", "rates/rate", "increased/increase"
    for suf in ("ings", "ing", "ies", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)] + ("y" if suf == "ies" else "")
    return t


def _split_long(par):
    sents = re.split(r"(?<=[.!?])\s+", par)
    out, cur = [], []
    for s in sents:
        if cur and len(" ".join(cur + [s]).split()) > MAX_WORDS:
            out.append(" ".join(cur)); cur = []
        cur.append(s)
    if cur:
        out.append(" ".join(cur))
    return out


def chunk_doc(doc_id, text):
    pars = []
    for p in text.split("\n"):
        p = p.strip()
        if p:
            pars.extend(_split_long(p) if len(p.split()) > MAX_WORDS else [p])
    chunks, cur = [], []
    for p in pars:
        if cur and len(" ".join(cur + [p]).split()) > TARGET_WORDS:
            chunks.append("\n".join(cur)); cur = []
        cur.append(p)
    if cur:
        chunks.append("\n".join(cur))
    return [{"doc_id": doc_id, "chunk_id": f"{doc_id}#c{i:03d}", "text": c} for i, c in enumerate(chunks)]


def build_chunks():
    manifest = read_jsonl(CORPUS / "manifest.jsonl")
    rows = []
    for d in manifest:
        text = (ROOT / d["text_file"]).read_text()
        for c in chunk_doc(d["doc_id"], text):
            c.update(available_at_et=d["available_at_et"], role=d["role"])
            rows.append(c)
    write_jsonl(CORPUS / "chunks.jsonl", rows)
    print(f"{len(rows)} chunks from {len(manifest)} docs")
    return rows


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.toks = [tokenize(d["text"]) for d in docs]
        self.docs = docs
        self.avgdl = sum(map(len, self.toks)) / len(self.toks)
        df = Counter(t for ts in self.toks for t in set(ts))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(ts) for ts in self.toks]

    def scores(self, query):
        q = tokenize(query)
        out = []
        for tf, ts in zip(self.tf, self.toks):
            s, dl = 0.0, len(ts)
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out

    def top(self, query, k, exclude=()):
        sc = self.scores(query)
        order = sorted(range(len(sc)), key=lambda i: -sc[i])
        res = []
        for i in order:
            if sc[i] <= 0 or self.docs[i]["chunk_id"] in exclude:
                continue
            res.append({**self.docs[i], "score": round(sc[i], 3)})
            if len(res) == k:
                break
        return res


def time_filter(chunks, cut):
    return [c for c in chunks if datetime.fromisoformat(c["available_at_et"]) <= cut]


def run():
    chunks = build_chunks()
    graph = load("graph.json")
    cut = cutoff()
    eligible = time_filter(chunks, cut)
    index = BM25(eligible)
    per_edge = BUDGET // len(graph["edges"])

    ordinary = index.top(graph["ordinary_baseline"]["query"], BUDGET)
    guided = {}
    for e in graph["edges"]:
        guided[e["id"]] = index.top(e["retrieval_query"], per_edge)

    # Leakage check: same queries against an UNFILTERED index; report future chunks that
    # would have been retrieved had the filter not been applied.
    unfiltered = BM25(chunks)
    leak = {"ordinary": [c["chunk_id"] for c in unfiltered.top(graph["ordinary_baseline"]["query"], BUDGET) if c["role"] != "corpus"]}
    for e in graph["edges"]:
        leak[e["id"]] = [c["chunk_id"] for c in unfiltered.top(e["retrieval_query"], per_edge) if c["role"] != "corpus"]
    retrieved_future = [c["chunk_id"] for c in ordinary + sum(guided.values(), []) if datetime.fromisoformat(c["available_at_et"]) > cut]

    strip = lambda rs: [{k: r[k] for k in ("chunk_id", "doc_id", "score")} for r in rs]
    result = {
        "cutoff": cut.isoformat(),
        "budget_total_chunks": BUDGET,
        "per_edge_k": per_edge,
        "n_chunks_total": len(chunks),
        "n_chunks_eligible_after_time_filter": len(eligible),
        "n_docs_eligible": len({c["doc_id"] for c in eligible}),
        "excluded_docs_by_time_filter": sorted({c["doc_id"] for c in chunks} - {c["doc_id"] for c in eligible}),
        "ordinary": {"question": graph["ordinary_baseline"]["question"], "query": graph["ordinary_baseline"]["query"], "results": strip(ordinary)},
        "graph_guided": {e["id"]: {"question": e["retrieval_question"], "query": e["retrieval_query"], "results": strip(guided[e["id"]])} for e in graph["edges"]},
        "future_exclusion_check": {
            "future_chunks_in_filtered_results": retrieved_future,
            "passed": not retrieved_future,
            "future_chunks_that_unfiltered_retrieval_would_have_returned": leak,
        },
    }
    write_json(OUT / "retrieval.json", result)
    print(f"eligible chunks {len(eligible)}/{len(chunks)}; excluded docs {result['excluded_docs_by_time_filter']}")
    print(f"future-exclusion check passed: {result['future_exclusion_check']['passed']}; unfiltered would leak: { {k: len(v) for k, v in leak.items()} }")
    return result


def chunk_lookup():
    return {c["chunk_id"]: c for c in read_jsonl(CORPUS / "chunks.jsonl")}
