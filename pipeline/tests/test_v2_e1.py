"""Offline tests for the exploratory E1 v2 correction (no network, no LLM)."""
import glob
import json

from crag import llm
from crag.common import ROOT
from crag.v2_e1 import VERSION, schema, spec, system_prompt, validate

LOOKUP = {"X#c0": {"doc_id": "X", "text": "We raised our full-year outlook on strong consumer demand. Sales rose 14%. Margins were squeezed by higher costs."}}
SUP = {"X#c0"}


def item(label, sup=(), con=(), ctx=(), expl=""):
    ev = lambda xs: [{"doc_id": "X", "chunk_id": "X#c0", "quote": q, "evidence_type": t} for q, t in xs]
    return {"edge_id": "E1", "label": label, "supporting_evidence": ev(sup), "contradicting_evidence": ev(con),
            "context_evidence": ev(ctx), "conflict": False, "explanation": expl}


def test_v1_cache_keys_unchanged():
    """Every saved v1 record must still resolve to its own file under the new key function."""
    files = glob.glob(str(ROOT / "cache/llm/*.json"))
    assert files
    for f in files:
        r = json.load(open(f))
        assert str(llm.cache_path(r["system"], r["user"], r["schema"], r["repeat"])) == f


def test_v2_cache_separate():
    p = llm.cache_path("s", "u", {}, 0, VERSION)
    assert p.parent.name == "llm_e1_v2" and p != llm.cache_path("s", "u", {}, 0)


def test_historical_growth_alone_is_not_supported():
    r = validate(item("supported", sup=[("Sales rose 14%.", "historical_results")]), SUP, LOOKUP)
    assert r["validated_label"] == "insufficient_evidence" and not r["meets_v2_criteria"]


def test_demand_linked_outlook_supports():
    r = validate(item("supported", sup=[("We raised our full-year outlook on strong consumer demand.", "demand_linked_outlook_change")]), SUP, LOOKUP)
    assert r["validated_label"] == "supported"


def test_contradicted_requires_offsetting_mechanism():
    no_mech = item("contradicted", con=[("strong consumer demand", "demand_without_outlook_improvement")])
    assert validate(no_mech, SUP, LOOKUP)["validated_label"] == "insufficient_evidence"
    with_mech = item("contradicted", con=[("strong consumer demand", "demand_without_outlook_improvement"),
                                          ("Margins were squeezed by higher costs.", "offsetting_mechanism")])
    assert validate(with_mech, SUP, LOOKUP)["validated_label"] == "contradicted"


def test_paraphrased_quote_does_not_count():
    r = validate(item("supported", sup=[("Outlook raised due to demand.", "demand_linked_outlook_change")]), SUP, LOOKUP)
    assert r["supporting_evidence"][0]["citation_status"] == "quote_not_found_in_chunk"
    assert r["validated_label"] == "insufficient_evidence"


def test_unquoted_numbers_flagged():
    r = validate(item("insufficient_evidence", ctx=[("Sales rose 14%.", "historical_results")], expl="Sales rose 14% and U.S. 10.3%."), SUP, LOOKUP)
    assert r["explanation_numbers_not_in_quotes"] == ["10.3"]


def test_spec_and_prompt_alignment():
    s = spec()
    sp = system_prompt(s)
    for k in ("supported", "contradicted", "insufficient_evidence"):
        assert s["edge"]["criteria"][k] in sp
    assert "AFTER inspecting v1" in s["provenance"]
    assert schema()["properties"]["assessments"]["items"]["properties"]["context_evidence"]
