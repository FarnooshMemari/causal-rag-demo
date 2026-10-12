"""Offline unit tests (no network, no LLM)."""
from datetime import datetime

from crag.assess import encode_pathways, validate
from crag.common import ET, available_at, load
from crag.retrieval import BM25, chunk_doc, time_filter

LOOKUP = {"D1#c000": {"doc_id": "D1", "text": "Retail sales  rose 0.7 percent\nin July, the “strongest” since January."}}


def _item(label, sup=(), con=()):
    ev = lambda xs: [{"doc_id": d, "chunk_id": c, "quote": q} for d, c, q in xs]
    return {"edge_id": "E1", "label": label, "supporting_evidence": ev(sup), "contradicting_evidence": ev(con), "conflict": False, "explanation": ""}


def test_date_precision_is_conservative():
    assert available_at("2023-08-15", "date") == datetime(2023, 8, 15, 23, 59, 59, tzinfo=ET)


def test_time_filter_excludes_future():
    cut = datetime.fromisoformat("2023-08-15T10:00:00-04:00")
    chunks = [{"available_at_et": "2023-08-15T08:30:00-04:00"}, {"available_at_et": "2023-08-15T10:00:01-04:00"}]
    assert time_filter(chunks, cut) == chunks[:1]


def test_registry_roles_match_cutoff():
    cut = datetime.fromisoformat(load("event.json")["decision_cutoff"])
    for s in load("sources.json")["sources"]:
        assert (available_at(s["published_at"], s["timestamp_precision"]) <= cut) == (s["role"] == "corpus"), s["doc_id"]


def test_quote_validation_whitespace_and_quotes_normalised():
    r = validate(_item("supported", [("D1", "D1#c000", 'rose 0.7 percent in July, the "strongest"')]), {"D1#c000"}, LOOKUP)
    assert r["supporting_evidence"][0]["citation_status"] == "valid" and r["validated_label"] == "supported"


def test_paraphrase_rejected_and_label_downgraded():
    r = validate(_item("supported", [("D1", "D1#c000", "sales increased 0.7 percent")]), {"D1#c000"}, LOOKUP)
    assert r["supporting_evidence"][0]["citation_status"] == "quote_not_found_in_chunk"
    assert r["validated_label"] == "insufficient_evidence" and not r["label_evidence_consistent"]


def test_unsupplied_chunk_and_doc_mismatch():
    r = validate(_item("contradicted", con=[("D1", "D9#c000", "x"), ("D2", "D1#c000", "Retail sales")]), {"D1#c000"}, LOOKUP)
    assert [e["citation_status"] for e in r["contradicting_evidence"]] == ["chunk_not_supplied", "doc_id_mismatch"]
    assert r["validated_label"] == "insufficient_evidence"


def test_conflict_observed():
    r = validate(_item("supported", [("D1", "D1#c000", "Retail sales")], [("D1", "D1#c000", "since January")]), {"D1#c000"}, LOOKUP)
    assert r["conflict_observed"]


def test_pathway_rule_never_completes_chain_with_gap():
    g = {"pathways": {"P": {"edges": ["A", "B"], "net_hypothesised_sign_on_equities": 1}}}
    mk = lambda c: {"code": c, "conflict_observed": False}
    assert encode_pathways([{"edge_id": "A", **mk(1)}, {"edge_id": "B", **mk(0)}], g)["P"]["status"] == "chain_incomplete"
    assert encode_pathways([{"edge_id": "A", **mk(1)}, {"edge_id": "B", **mk(-1)}], g)["P"]["status"] == "chain_broken"
    assert encode_pathways([{"edge_id": "A", **mk(1)}, {"edge_id": "B", **mk(1)}], g)["P"]["status"] == "chain_supported"


def test_bm25_and_chunking():
    docs = [{"chunk_id": "a", "text": "inflation pressure rising prices"}, {"chunk_id": "b", "text": "corporate earnings revenue growth"}]
    assert BM25(docs).top("earnings growth", 1)[0]["chunk_id"] == "b"
    ch = chunk_doc("D", "\n".join(["word " * 100] * 5))
    assert len(ch) >= 3 and all(len(c["text"].split()) <= 260 for c in ch)
