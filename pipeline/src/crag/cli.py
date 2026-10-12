"""CLI.
Original v1 pipeline:  python -m crag.cli {verify-refs|fetch|retrieve|assess|evaluate|report|all}
Research upgrade:      python -m crag.cli {bench-download|bench-run|bny-run|smoke}  (settings: config/experiments.json)
"""
import argparse
import json

from . import assess, evaluate, fetch, llm, report, retrieval, verify_refs
from .common import load

V1_STEPS = ["verify-refs", "fetch", "retrieve", "assess", "evaluate", "report"]


def _bench(name, split, n, data_dir=None, **kw):
    from .benchmarks import load_averitec, load_fincausal
    return load_fincausal(split, n, data_dir=data_dir, **kw) if name == "fincausal2026" else load_averitec(split, n, data_dir=data_dir, **kw)


def main():
    p = argparse.ArgumentParser(description="Causal RAG: BNY case study + external benchmarks")
    p.add_argument("step", choices=V1_STEPS + ["all", "bench-download", "bench-run", "bny-run", "smoke"])
    p.add_argument("--refresh", action="store_true", help="re-download sources (default: use cached raw files)")
    p.add_argument("--profile", default="dev", help="profile in config/experiments.json (dev | full)")
    p.add_argument("--dataset", choices=["fincausal2026", "averitec", "both"], default="both")
    p.add_argument("--backend", choices=["llm", "heuristic"], help="override profile backend")
    a = p.parse_args()
    if a.step in V1_STEPS + ["all"]:
        for s in (V1_STEPS if a.step == "all" else [a.step]):
            print(f"\n=== {s} ===")
            {"verify-refs": verify_refs.run, "fetch": lambda: fetch.run(refresh=a.refresh), "retrieve": retrieval.run, "assess": assess.run,
             "evaluate": lambda: print(json.dumps({k: v for k, v in evaluate.run().items() if k in ("controls", "llm_blocked")}, indent=1)),
             "report": report.run}[s]()
        print(f"\nuncached LLM calls this run: {llm.stats()}")
        return

    from . import benchmarks, experiment
    cfg = load("experiments.json")["profiles"][a.profile]
    backend = a.backend or cfg["backend"]
    names = ["fincausal2026", "averitec"] if a.dataset == "both" else [a.dataset]
    if a.step == "bench-download":
        for n in names:
            benchmarks.download(n)
    elif a.step == "bench-run":
        for n in names:
            c = cfg[n]
            if n == "averitec" and c.get("stratify_causal"):
                b1 = _bench(n, c["split"], c["n"] // 2, causal_only=True)
                b2 = _bench(n, c["split"], c["n"] - c["n"] // 2, causal_only=False)
                b = benchmarks.Benchmark(n, c["split"], b1.cases + b2.cases, {**b1.corpora, **b2.corpora},
                                         benchmarks.GoldStore({**b1.gold._rows, **b2.gold._rows}),
                                         {**b1.info, "n_cases": len(b1.cases) + len(b2.cases),
                                          "sampling_note": f"Stratified dev sample: {len(b1.cases)} annotated causal + {len(b2.cases)} other claims (selection uses claim_types annotations; recorded, not used at inference)."})
            else:
                b = _bench(n, c["split"], c["n"], **({"n_distractors": c["n_distractors"]} if "n_distractors" in c else {}))
            res = experiment.run_benchmark(b, backend, c["budget"], cfg["repeats"], cfg.get("workers", 4), label=a.profile)
            res["config"] = {"profile": a.profile, **c, "repeats": cfg["repeats"]}
            print(experiment.write_artifact("benchmarks", f"{n}__{c['split']}__{a.profile}__{backend}", res))
    elif a.step == "bny-run":
        res = experiment.run_bny(backend, cfg["bny_repeats"])
        print(experiment.write_artifact("bny", f"bny_three_method__{a.profile}__{backend}", res))
    elif a.step == "smoke":
        from .smoke import run as smoke
        smoke()
    print(f"\nuncached LLM calls this run: {llm.stats()}")


if __name__ == "__main__":
    main()
