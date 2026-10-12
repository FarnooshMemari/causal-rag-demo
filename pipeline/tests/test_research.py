"""Offline tests for the research upgrade: adapters, metrics, graph/path logic, validator,
citation checks, leakage guards, runner and site artifacts. Uses SYNTHETIC fixtures only."""
import dataclasses
import json
from pathlib import Path

import pytest

from crag.benchmarks import (AVERITEC_LABELS, Case, Passage, canon_label, claim_graph, fincausal_split, load_averitec,
                             load_fincausal, question_graph)
from crag.experiment import ARTIFACTS, METHODS, check_quotes, retrieve, run_benchmark, _Idx
from crag.graph import aggregate_graph, aggregate_path, bny_graph
from crag.metrics import classification_report, exact_match, ndcg_at_k, reciprocal_rank, token_f1
from crag.validator import classify_quote, validate_edge

FIX = Path(__file__).parent / "fixtures" / "benchmarks"
SITE = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- metrics
def test_em_and_f1_squad_normalisation():
    assert exact_match("The higher volumes.", "higher volumes") == 1.0
    assert token_f1("higher volumes in retail", "higher volumes") == pytest.approx(2 * 0.5 * 1 / 1.5)
    assert token_f1("", "x") == 0.0


def test_macro_f1_counts_all_reference_classes_and_confusion():
    rep = classification_report(["Supported", "Refuted"], ["Supported", "Supported"], AVERITEC_LABELS)
    assert rep["accuracy"] == 0.5
    assert rep["macro_f1"] == pytest.approx((2 / 3) / 4)
    assert rep["confusion_matrix"]["Refuted"]["Supported"] == 1


def test_ranking_metrics():
    assert reciprocal_rank(["a", "b"], {"b"}) == 0.5
    assert ndcg_at_k(["b", "a"], {"b"}) == 1.0


# ---------------------------------------------------------------- adapters + leakage
def test_fincausal_adapter_reads_official_format_and_seals_gold():
    b = load_fincausal("train_full", data_dir=FIX / "fincausal2026")
    assert len(b.cases) == 10 and b.info["has_gold"]
    case_fields = {f.name for f in dataclasses.fields(Case)}
    assert not case_fields & {"answer", "label", "gold"}
    for c in b.cases:
        g = b.gold[c.case_id]
        assert g["answer"] not in c.text and g["answer"] not in json.dumps(c.metadata)
        assert g["relevant_pids"][0] in {p.pid for p in b.corpora[c.corpus_id]}
        assert c.graph is not None and not c.graph.validate_structure()


def test_fincausal_unlabelled_test_split_has_no_metrics():
    b = load_fincausal("test_unlabeled", data_dir=FIX / "fincausal2026")
    assert not b.info["has_gold"] and len(b.gold) == 0


def test_fincausal_internal_split_is_deterministic_and_disjoint():
    ids = [str(i) for i in range(500)]
    dev = {i for i in ids if fincausal_split(i) == "dev_internal"}
    assert 50 < len(dev) < 150 and dev == {i for i in ids if fincausal_split(i) == "dev_internal"}


def test_averitec_labels_explicit_alias_only():
    assert canon_label("Conflicting Evidence/Cherrypicking") == "Conflicting Evidence/Cherry-picking"
    with pytest.raises(ValueError):
        canon_label("Mostly True")


def test_averitec_adapter_pools_and_gold_separation():
    b = load_averitec("dev", data_dir=FIX / "averitec")
    assert len(b.cases) == 4 and {b.gold[c.case_id]["label"] for c in b.cases} == set(AVERITEC_LABELS)
    for c in b.cases:
        assert b.corpora[c.corpus_id], "pool missing"
        assert "label" not in c.metadata and "questions" not in c.metadata


def test_graph_parsers_use_text_only():
    g = question_graph("What caused the decline in operating margin?", "x")
    assert g.edges[0].path == "asked_cause" and "decline operating margin" in g.node_label("known")
    assert question_graph("What was the effect of the impairment charge?", "y").edges[0].path == "asked_effect"
    cg = claim_graph("Carbon dioxide intoxication is caused by wearing face masks.", "z")
    assert cg.node_label("cause") == "wearing face masks" and cg.node_label("effect") == "Carbon dioxide intoxication"
    assert claim_graph("The mayor said the bridge opened in 2010.", "w") is None


# ---------------------------------------------------------------- graph / path logic
def test_bny_graph_frozen_and_connected():
    g = bny_graph()
    assert g.frozen and [e.id for e in g.edges] == ["E1", "E2", "E3", "E4", "E5"] and not g.validate_structure()


def test_unsupported_edge_never_yields_supported_chain():
    assert aggregate_path(["E3", "E4", "E5"], {"E3": "insufficient_evidence", "E4": "supported", "E5": "supported"})["status"] == "incomplete"
    assert aggregate_path(["E1", "E2"], {"E1": "supported", "E2": "contradicted"})["status"] == "broken"
    assert aggregate_path(["E1", "E2"], {"E1": "conflicting", "E2": "supported"})["status"] == "contested"
    assert aggregate_path(["E1", "E2"], {"E1": "supported", "E2": "supported"})["status"] == "supported"


def test_competing_pathways_not_collapsed():
    g = bny_graph()
    r = aggregate_graph(g, {e.id: "supported" for e in g.edges}, {"P1_earnings": 1, "P2_rates": -1})
    assert r["competing_pathways_both_supported"] and r["net_conclusion"] is None
    assert set(r["paths"]) == {"P1_earnings", "P2_rates"}


# ---------------------------------------------------------------- validator + citations
RULE = {"source_terms": ["consumer", "demand"], "target_terms": ["guidance", "outlook", "revenue"], "requires_forward_looking": True}
LOOK = {"c1": {"text": "x", "available_at_et": "2023-08-01T00:00:00-04:00"}, "c2": {"text": "x", "available_at_et": "2023-08-20T00:00:00-04:00"}}


def _it(label, sup=(), con=(), **kw):
    q = lambda xs: [{"chunk_id": c, "quote": t, "citation_status": "valid"} for c, t in xs]
    return {"edge_id": "E1", "label": label, "validated_label": label, "supporting_evidence": q(sup), "contradicting_evidence": q(con), **kw}


def test_validator_rejects_realised_results_for_expectation_target():
    v = validate_edge(_it("supported", [("c1", "Revenue increased 14%, reflecting strong consumer demand.")]), RULE)
    assert v["judgment"] == "insufficient_evidence" and "realised" in " ".join(v["reasons"])


def test_validator_accepts_forward_causal_statement_and_flags_condition():
    v = validate_edge(_it("supported", [("c1", "We raised full-year guidance because consumer demand stayed strong.")]), RULE, condition="no margin squeeze")
    assert v["judgment"] == "supported" and v["checks"]["assumptions"] == "not_verified"


def test_validator_off_target_and_association_only():
    off = validate_edge(_it("supported", [("c1", "Consumer demand was strong.")]), RULE)
    assert off["judgment"] == "insufficient_evidence" and "off-target" in off["reasons"][0]
    rule = {**RULE, "requires_forward_looking": False}
    assoc = validate_edge(_it("supported", [("c1", "Consumer demand and revenue were both up.")]), rule)
    assert assoc["judgment"] == "insufficient_evidence" and "association" in " ".join(assoc["reasons"])


def test_validator_point_in_time_conflict_and_never_upgrades():
    from datetime import datetime
    cut = datetime.fromisoformat("2023-08-15T10:00:00-04:00")
    late = validate_edge(_it("supported", [("c2", "Guidance was raised because consumer demand was strong.")]), RULE, LOOK, cut)
    assert late["judgment"] == "insufficient_evidence" and not late["checks"]["point_in_time"]
    rule = {**RULE, "requires_forward_looking": False}
    both = validate_edge(_it("supported", [("c1", "Revenue rose because consumer demand was strong.")], [("c1", "Revenue fell despite strong consumer demand.")]), rule)
    assert both["judgment"] == "conflicting"
    assert validate_edge(_it("insufficient_evidence", [("c1", "Revenue rose because consumer demand was strong.")]), rule)["judgment"] == "insufficient_evidence"


def test_e1_e5_regressions_on_recorded_v1():
    from crag.common import cutoff, load
    from crag.experiment import validator_regression_v1
    from crag.retrieval import chunk_lookup
    rows = validator_regression_v1(load("validation_rules.json"), chunk_lookup(), cutoff())["rows"]
    pick = lambda c, e: [r for r in rows if r["condition"] == c and r["edge_id"] == e]
    assert all(r["v1_label"] == "supported" and r["validator"] == "insufficient_evidence" for r in pick("graph_guided", "E1"))
    assert all(r["v1_label"] == "supported" and r["validator"] == "insufficient_evidence" for r in pick("ordinary", "E5"))


def test_check_quotes_statuses():
    sup = {"p1": {"text": "Sales rose due to   demand."}}
    out = check_quotes([{"chunk_id": "p1", "quote": "rose due to demand"}, {"chunk_id": "p2", "quote": "x"}, {"chunk_id": "p1", "quote": "fell"}], sup)
    assert [o["citation_status"] for o in out] == ["valid", "chunk_not_supplied", "quote_not_found_in_chunk"]


def test_classify_quote_kinds():
    assert classify_quote("Revenue rose due to demand.", {"source_terms": ["demand"], "target_terms": ["revenue"]})["kind"] == "causal_statement"
    assert classify_quote("Prices rose.", {"source_terms": ["demand"], "target_terms": ["revenue"]})["kind"] == "off_target"


# ---------------------------------------------------------------- retrieval fairness + runner
def test_methods_share_budget_and_multi_query_matches_query_count():
    b = load_fincausal("train_full", data_dir=FIX / "fincausal2026")
    idx, case = _Idx(b.corpora["fincausal_controlled"]), b.cases[0]
    rs = {m: retrieve(m, case, idx, 3, "heuristic") for m in METHODS}
    assert all(len(r["evidence"]) <= 3 for r in rs.values())
    assert rs["multi_query"]["n_queries"] == rs["graph_guided"]["n_queries"]
    assert rs["ordinary"]["n_queries"] == 1


def test_runner_end_to_end_on_fixtures_is_labelled_not_a_result():
    res = run_benchmark(load_averitec("dev", data_dir=FIX / "averitec"), "heuristic", budget=2, workers=1)
    assert res["run"]["status"] == "smoke_heuristic_not_a_result"
    assert set(res["metrics"]) >= {"ordinary", "multi_query", "graph_guided", "graph_guided_assessor_only", "oracle"}
    assert res["samples"][0]["gold"]["label"] in AVERITEC_LABELS


# ---------------------------------------------------------------- site data
def test_site_files_and_original_results_preserved():
    for f in ("index.html", "main.js", "explorer.js", "style.css", "results.json"):
        assert (SITE / f).exists()
    r = json.loads((SITE / "results.json").read_text())
    assert set(r["versions"]) == {"v1", "v2"} and [e["id"] for e in r["graph"]["edges"]] == ["E1", "E2", "E3", "E4", "E5"]


def test_artifact_index_consistent():
    idx_path = ARTIFACTS / "index.json"
    if not idx_path.exists():
        pytest.skip("no computed artifacts yet")
    for a in json.loads(idx_path.read_text())["artifacts"]:
        d = json.loads((SITE / a["path"]).read_text())
        assert d["run"]["status"] == a["status"] and a["status"] in ("computed", "smoke_heuristic_not_a_result")
        if a["kind"] == "benchmarks":
            assert d["dataset"]["n_cases"] == a["n"] == len(d["samples"])
