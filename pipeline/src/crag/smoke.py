"""Deterministic smoke test: whole pipeline on SYNTHETIC fixtures with the heuristic backend.
No network, no model calls, nothing written to artifacts/. Output numbers are not results."""
from pathlib import Path

from .benchmarks import load_averitec, load_fincausal
from .common import ROOT
from .experiment import run_benchmark, run_bny

FIX = ROOT / "tests" / "fixtures" / "benchmarks"


def run():
    fc = run_benchmark(load_fincausal("train_full", data_dir=FIX / "fincausal2026"), "heuristic", budget=3, workers=1, label="smoke")
    av = run_benchmark(load_averitec("dev", data_dir=FIX / "averitec"), "heuristic", budget=3, workers=1, label="smoke")
    bny = run_bny("heuristic", 1)
    m = fc["metrics"]
    print("SMOKE (synthetic fixtures, heuristic backend; NOT benchmark results)")
    print(" fincausal fixture:", {k: round(v["token_f1"], 2) for k, v in m.items()})
    print(" averitec fixture :", {k: round(v["accuracy"], 2) for k, v in av["metrics"].items()})
    print(" bny heuristic    : future chunks retrieved =", sum(len(r["future_chunks_retrieved"]) for v in bny["methods"].values() for r in v))
    reg = {(r["condition"], r["edge_id"], r["repeat"]): r["validator"] for r in bny["regression_on_recorded_v1"]["rows"]}
    assert reg[("graph_guided", "E1", 0)] == "insufficient_evidence", "E1 regression failed"
    assert reg[("ordinary", "E5", 0)] == "insufficient_evidence", "E5 regression failed"
    print(" validator regressions E1/E5: passed")
    return fc, av, bny
