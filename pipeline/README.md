# Causal RAG feasibility MVP: graph-guided point-in-time evidence retrieval

Duke × BNY macro-financial portfolio intelligence capstone. This project tests one question: **can a predefined economic graph guide the retrieval of point-in-time evidence and produce traceable, structured assessments of transmission pathways?** It does not test causal identification, trading performance, or portfolio optimisation. No asset-return data is used anywhere.

- **Event:** U.S. Census Bureau advance retail sales for July 2023, released 2023-08-15 08:30 EDT. First-release actual was +0.7% m/m against a public consensus of +0.4%, a surprise of +0.3 pp.
- **Decision cutoff:** 2023-08-15 10:00 EDT.
- **Graph:** two competing pathways, five edges, defined in [`config/graph.json`](config/graph.json).
- **Meeting report:** [`report/MEETING_REPORT.md`](report/MEETING_REPORT.md).
- **Side-by-side comparison:** [`outputs/comparison.md`](outputs/comparison.md).

## Run it

```bash
cd pipeline
pip install -r requirements.txt
PYTHONPATH=src python -m crag.cli all          # verify-refs → fetch → retrieve → assess → evaluate → report
PYTHONPATH=src python -m pytest -q tests       # offline unit tests (v1 + research upgrade)
```

Each step can also be run on its own: `PYTHONPATH=src python -m crag.cli {verify-refs|fetch|retrieve|assess|evaluate|report}`.

The repository already contains the cached raw documents (`data/raw`) and the cached LLM responses (`cache/llm`). Because of that, `all` reproduces every saved output **with zero new LLM calls and zero cost**. To re-query the model, delete `cache/llm/`. The last full run made 41 calls and cost $1.11 in total. Uncached calls are capped by `CRAG_MAX_LLM_CALLS` (default 60).

### LLM setup

| provider | how to enable | status |
|---|---|---|
| `claude_cli` (default) | The `claude` CLI (Claude Code) is installed and logged in. Calls run headless (`claude -p`) with all tools disabled, no user or project settings, and JSON-schema-constrained output. | **executed** (model `claude-sonnet-5-5`) |
| `anthropic` | `export CRAG_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=...` | implemented, not executed (no key on this machine) |
| `openai` | `export CRAG_LLM_PROVIDER=openai OPENAI_API_KEY=...` (same key as `protofin/.env`) | implemented, not executed (no key on this machine) |

Optional settings: `CRAG_LLM_MODEL` chooses the model. `CRAG_SEC_CONTACT="Name email"` adds a contact address to the SEC User-Agent; SEC's fair-access policy asks for one, and two EDGAR filings were blocked without it. No secrets appear in the code.

## Layout

```
config/event.json          event, timestamps, first-release actual, consensus (two sources), surprise
config/graph.json          nodes, directed edges, conditional signs, per-edge retrieval questions (frozen before any assessment)
config/references.json     literature behind each edge; verified against Crossref → outputs/reference_verification.json
config/sources.json        source registry: URL, availability timestamp, timestamp evidence, role
data/raw/                  original downloaded bytes (PDF/HTML) + per-file fetch metadata (retrieval time, Last-Modified, EDGAR Accepted)
data/corpus/manifest.jsonl corpus manifest (22 docs: 19 pre-cutoff + 3 future-exclusion tests; sha256 of raw files)
data/corpus/text/          extracted text;  data/corpus/chunks.jsonl  364 chunks (281 eligible at the cutoff)
src/crag/                  fetch · retrieval (chunking, BM25, time filter) · llm (cached client) · assess · evaluate · report · cli
outputs/retrieval.json     ordinary vs graph-guided results + future-exclusion check
outputs/assessments.json   all edge judgements (3 repeats × 2 conditions) + controls, with citation validation
outputs/metrics.json       retrieval (provisional), citation validity, consistency, abstention, conflict, repeatability
outputs/comparison.md      side-by-side report
outputs/archive/run1_*     first run, before the Beige Book extraction fix (kept for transparency)
annotations/*.csv          human-review sheets with MODEL-PROVISIONAL labels and blank human columns
cache/llm/                 every LLM request/response (prompt, schema, output, cost)
```

## Method (decisions and why)

- **Point-in-time filter before indexing.** Each document has an `available_at` timestamp. When only a date can be verified, it is set conservatively to 23:59:59 ET on that date. Chunks published after the cutoff are dropped **before** the BM25 index is built, so future documents cannot even influence IDF weights. Three real post-cutoff documents (the July FOMC minutes, the August retail-sales release, and Powell's Jackson Hole speech) are kept in the corpus specifically to test this filter. `retrieval.json` also shows which future chunks the same queries *would* have returned without it.
- **Timestamp evidence.**
  - EDGAR 8-Ks: the filing index "Accepted" time, re-checked automatically at fetch time; all 6 matched.
  - Statistical releases: the embargo or release time printed on the document.
  - Fed: the official release time. HTTP `Last-Modified` was *not* used for Fed HTML, because site rebuilds reset it. One exception: the Powell press-conference transcript PDF, whose `Last-Modified` of 2023-08-09 is later than the press conference, so the later date is used as its availability time.
- **Chunking.** Paragraphs are packed into chunks of about 170 words (maximum about 260), with no overlap. Each table row becomes one line. Legal safe-harbour boilerplate is dropped from the extracted text (raw files are untouched), and long documents are truncated at a per-source `max_chars`, which is recorded in the manifest.
- **Retriever.** Self-implemented Okapi BM25 (k1 = 1.5, b = 0.75) with stop-word removal and a light suffix stemmer. No embeddings and no frameworks.
- **Equal budget: 20 chunks per strategy.**
  - *Ordinary:* the top 20 for one broad event question. The assessor judges all 5 edges in one call against those 20.
  - *Graph-guided:* the top 4 for each of the 5 edge questions. The assessor judges each edge in its own call against its 4 chunks.
  - Corpus, tokenizer, retriever, assessor prompt and output schema are identical across the two strategies.
- **Assessor.**
  - It returns, per edge: `supported | contradicted | insufficient_evidence`, verbatim quotes on **both** sides with `doc_id` and `chunk_id`, a conflict flag, and an explanation.
  - The system prompt says to use only the excerpts, to treat excerpt text as untrusted data, and not to use knowledge of later events.
  - Code then checks that every quote appears verbatim (after whitespace and quote-mark normalisation) in the chunk it cites, that the chunk was actually supplied, and that the `doc_id` matches.
  - A directional label with no valid quote on its side is downgraded to `insufficient_evidence`. The raw label is kept alongside.
- **Encoding.**
  - Edge codes: +1 supported, −1 contradicted, 0 insufficient. Labels, conflicts and quote counts are kept separately.
  - Pathway rule: `chain_supported` only if **every** edge is supported; `chain_broken` if any edge is contradicted; otherwise `chain_incomplete`.
  - Codes are never multiplied into an effect size, and they are not probabilities.
- **Repeatability.** Each condition is run three times with identical inputs; only the cache key changes. The CLI provider does not expose temperature, so default sampling is used.
- **Controls.**
  - *Insufficient-evidence edge* (consumption → crop yields), using real retrieved agricultural chunks.
  - *Empty-excerpt case:* a deterministic code path with no LLM call.
  - *Prompt-injection fixture:* a clearly labelled **synthetic** chunk that is never part of the corpus or the results.

## Limitations

- **Hindsight is not removed.** The time filter removes future documents, but it cannot remove what the LLM learned in training about markets after August 2023, and the project author (an LLM agent) also has general knowledge of that period. The prompt instructions are mitigation only.
- **Labels are provisional.** All relevance grades come from the model and still need human review. Retrieval numbers are therefore provisional relevance rates, not objective precision. Recall is not reported, because no complete set of relevant evidence exists.
- **This is one event**, with a 19-document pre-cutoff corpus, 5 edges and 3 repeats. Fleiss' kappa on 5 items is unstable.
- **The consensus value relies on public reports** of proprietary surveys (an FXStreet pre-release preview and the CNBC/Dow Jones estimate).
- **Labels describe evidence, not causation.** "Supported" means the excerpts show the link operating in the period. It is not causal identification, and it is not about this single release.
- **Two SEC filings could not be fetched.** Target and Walmart 8-Ks (both future-exclusion test documents) were blocked by SEC's automated-tool policy. They are recorded in `data/corpus/fetch_failures.json`.

## Research upgrade (2026-10)

See the repository root `README.md` for commands. New modules: `graph.py`, `validator.py`, `metrics.py`, `benchmarks.py`, `experiment.py`, `smoke.py`; config `config/experiments.json` and `config/validation_rules.json` (post-hoc, exploratory). v1/v2 outputs, prompts and caches are untouched; new runs write to `../artifacts/` and cache to `cache/llm_bench_v1/`. Tests: `tests/test_research.py`; synthetic fixtures in `tests/fixtures/benchmarks/` (never reported as results).
