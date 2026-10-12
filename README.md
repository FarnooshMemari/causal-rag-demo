# Causal RAG: research viewer + offline pipeline

**Question:** does causal-graph structure improve evidence retrieval, verification and multi-step reasoning compared with ordinary and multi-query RAG?
Live site (static, no model calls): https://farnooshmemari.github.io/causal-rag-demo/

| Path | What |
|---|---|
| `index.html`, `main.js`, `style.css` | Site: Overview · BNY Case Study · Benchmarks · Guide |
| `explorer.js`, `results.json` | Original v1/v2 BNY explorer and record (unchanged) |
| `artifacts/` | Versioned machine-readable outputs of offline runs (`index.json` lists them) |
| `pipeline/` | Offline Python pipeline (original MVP + research upgrade); see `pipeline/README.md` |

## Run

```bash
cd pipeline && pip install -r requirements.txt
export PYTHONPATH=src
python -m pytest -q tests                      # offline tests (no network, no model)
python -m crag.cli smoke                       # synthetic fixtures, heuristic backend: NOT results
python -m crag.cli bench-download              # FinCausal 2026 EN + AVeriTeC dev into data/benchmarks/ (git-ignored)
python -m crag.cli bny-run   --profile dev     # BNY three-method case study
python -m crag.cli bench-run --profile dev     # small dev sample (12 cases per benchmark)
python -m crag.cli bench-run --profile full    # whole labelled split: check cost first
```
Profiles live in `pipeline/config/experiments.json`. Model calls go through the cached client (`crag/llm.py`; default `claude` CLI, `claude-sonnet-5-5`); `cache/llm_bench_v1/` lets the dev run reproduce with zero new calls. `CRAG_MAX_LLM_CALLS` caps uncached calls.
Preview the site locally: `python -m http.server` in the repo root.

## Architecture (pipeline/src/crag)
`graph.py` graph model + conservative path aggregation · `benchmarks.py` dataset adapters (gold sealed in `GoldStore`) · `experiment.py` three methods, shared assessor, oracle diagnostic, evaluation layer, BNY runner · `validator.py` causal evidence validator · `metrics.py` EM/F1, macro-F1, confusion matrix, ranking metrics, bootstrap CI.

- **Ordinary:** one query on the input. **Multi-query:** model-written queries from the input only, same count as graph-guided. **Graph-guided:** per-edge queries, evidence routed to edges, edge/path context in the prompt, validator, path rules. Same corpus, budget, model, prompt rubric and schema for all three.
- **Leakage:** gold answers/verdicts/annotated evidence exist only in `GoldStore`, read only by `evaluate_*` and the explicitly labelled oracle diagnostic.

## Data (not committed; licences)
- **FinCausal 2026** (doi:10.21950/H7RKHH, CC BY-NC-SA 4.0): extractive QA `id;context;question;answer`. Official test gold is not public, so evaluation uses `dev_internal`, a deterministic ~20% hash split of the official train file. Retrieval uses a *constructed* controlled corpus (case contexts + distractor contexts); FinCausal is not a native retrieval benchmark. Multi-step chains are not marked in the CSV; the subgroup flag is a heuristic.
- **AVeriTeC** (CC BY-NC 4.0): official dev split (4 labels; the file's "Cherrypicking" spelling is an explicit alias, other labels raise). Evidence pool per claim = the organisers' top-100 knowledge-store sentences (`dev_top_k_sentences.json`); the 11.5 GB knowledge store is not used. Retrieval relevance is a URL-match proxy only. Test labels are not public.

## Current results status
- BNY v1/v2: **recorded** (original, unchanged). BNY three-method: **computed**, one repeat, one event, no gold.
- FinCausal / AVeriTeC: **computed small dev runs** (n=12 each). Descriptive only, not benchmark performance; full-split runs **not executed**.

## Limitations
Labels describe evidence wording, not causal identification. The validator is lexical and its BNY rules were written after seeing the E1/E5 failures. Model training knowledge cannot be removed; multi-query generation may add background facts to queries (the time filter still governs the corpus). Small samples cannot show that any method is superior.
