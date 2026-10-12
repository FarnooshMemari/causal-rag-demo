"""Adapters for external labelled benchmarks: FinCausal 2026 (EN) and AVeriTeC.

Shared interface
  Benchmark.cases    list[Case]   - what retrieval / graph construction / assessment may see
  Benchmark.corpora  {id: [Passage]} - the eligible evidence pool per case
  Benchmark.gold     GoldStore    - sealed; only crag.experiment.evaluate_* reads it

Leakage rule: Case and Passage objects never carry gold answers, verdicts, annotated evidence or
annotator metadata. Gold lives only in GoldStore, which methods never receive.

Raw data is NOT committed (licences: FinCausal CC-BY-NC-SA-4.0, AVeriTeC CC-BY-NC-4.0). Download
with `python -m crag.cli bench-download` into data/benchmarks/ (git-ignored); see README.
"""
import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .common import ROOT
from .graph import CausalGraph, Edge, Node

BENCH_DIR = ROOT / "data" / "benchmarks"

SOURCES = {
    "fincausal2026": {
        "citation": "Moreno-Sandoval et al. (2026), The Financial Document Causality Detection Shared Task (FinCausal 2026), FNP@LREC 2026.",
        "paper": "https://aclanthology.org/2026.fnp-1.11/",
        "dataset_doi": "https://doi.org/10.21950/H7RKHH",
        "license": "CC-BY-NC-SA-4.0",
        "files": {"train_en_2000.csv": "https://edatos.consorciomadrono.es/api/access/datafile/51166",
                  "test_en_500.csv": "https://edatos.consorciomadrono.es/api/access/datafile/51165",
                  "readme-en.txt": "https://edatos.consorciomadrono.es/api/access/datafile/51163"},
        "format": "CSV ';'-separated: id;context;question;answer (train). Test has no answer column (gold withheld by organisers).",
    },
    "averitec": {
        "citation": "Schlichtkrull, Guo & Vlachos (2023), AVeriTeC: A Dataset for Real-world Claim Verification with Evidence from the Web, NeurIPS Datasets & Benchmarks.",
        "paper": "https://fever.ai/dataset/averitec.html",
        "license": "CC-BY-NC-4.0",
        "files": {"dev.json": "https://huggingface.co/chenxwh/AVeriTeC/resolve/main/data/dev.json",
                  "dev_top_k_sentences.json": "https://huggingface.co/chenxwh/AVeriTeC/resolve/main/data_store/dev_top_k_sentences.json"},
        "format": "JSON list of claims with label, questions[].answers[] (annotated QA evidence), claim_types, claim_date. "
                  "dev_top_k_sentences.json: per claim, the official baseline's top-100 sentences from the official dev knowledge store.",
    },
}

AVERITEC_LABELS = ["Supported", "Refuted", "Not Enough Evidence", "Conflicting Evidence/Cherry-picking"]
# Explicit, documented spelling alias found in the official files. Any other unseen label raises.
AVERITEC_ALIASES = {"Conflicting Evidence/Cherrypicking": "Conflicting Evidence/Cherry-picking"}


@dataclass(frozen=True)
class Passage:
    pid: str
    doc_id: str
    text: str
    url: str = ""
    available_at: str = ""


@dataclass
class Case:
    case_id: str
    task: str                  # extractive_qa | claim_verification
    text: str                  # question or claim
    corpus_id: str
    metadata: dict = field(default_factory=dict)
    graph: CausalGraph = None  # None => no causal structure detected


class GoldStore:
    """Sealed gold labels. Methods never receive this object."""

    def __init__(self, rows):
        self._rows = rows

    def __getitem__(self, case_id):
        return self._rows[case_id]

    def __contains__(self, case_id):
        return case_id in self._rows

    def __len__(self):
        return len(self._rows)


@dataclass
class Benchmark:
    name: str
    split: str
    cases: list
    corpora: dict
    gold: GoldStore
    info: dict


def _h(s, n=10):
    return hashlib.sha1(s.encode()).hexdigest()[:n]


def download(name, dest=BENCH_DIR):
    import requests
    out = Path(dest) / name
    out.mkdir(parents=True, exist_ok=True)
    for fn, url in SOURCES[name]["files"].items():
        p = out / fn
        if p.exists():
            continue
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        p.write_bytes(r.content)
        print(f"downloaded {p} ({len(r.content)} bytes)")
    return out


# ================================================================ causal-structure parsing
CAUSE_Q = re.compile(r"\b(why|reason\w*|cause\w*|caus\w+|due|driv\w*|contribut\w*|behind|factor\w*|led to|lead to|led|account\w* for|explain\w*|attribut\w*|result(?:ed)? (?:of|from)|because|basis|stemm\w*|prompt\w*|motivat\w*)\b", re.I)
EFFECT_Q = re.compile(r"\b(effect\w*|impl(?:y|ies|ied|ication\w*)|impact\w*|consequen\w*|outcome\w*|result(?:ed|s|ing)? in|what (?:did|has|have|will|does) .* (?:lead|result|cause|bring)|implication\w*|affect\w*)\b", re.I)
WH = re.compile(r"\b(what|which|why|how|who|when|was|were|is|are|did|does|do|has|have|had|the|a|an|of|to|in|for|that|this|behind|"
                r"reason\w*|cause\w*|caus\w+|factor\w*|contribut\w*|driv\w*|led|lead|result\w*|due|effect\w*|impact\w*|explain\w*|impl\w*|prompt\w*|consequen\w*|outcome\w*|primary|main|key|specific)\b", re.I)
CAUSAL_VOCAB = "due to because as a result of driven by owing to reflecting resulting in led to caused by attributable"


def focus_phrase(text):
    return re.sub(r"\s+", " ", WH.sub(" ", re.sub(r"[?.,;:]", " ", text))).strip()


def question_graph(question, case_id):
    """Deterministic 1-edge graph from the question ONLY (no context, no answer):
    which side of a cause->effect relation is asked for, and what the known side is about."""
    asks_effect = bool(EFFECT_Q.search(question)) and not re.search(r"\bwhy\b", question, re.I)
    asks_cause = bool(CAUSE_Q.search(question)) and not asks_effect
    known = focus_phrase(question) or question
    if asks_effect:
        nodes = {"known": Node("known", known), "asked": Node("asked", "unknown effect (answer)")}
        e = Edge("Q1", "known", "asked", 1, "", (), (), f"What does '{known}' lead to?", f"{known} {CAUSAL_VOCAB} || {known}", "asked_effect")
    else:
        nodes = {"asked": Node("asked", "unknown cause (answer)"), "known": Node("known", known)}
        e = Edge("Q1", "asked", "known", 1, "", (), (), f"What caused '{known}'?", f"{known} {CAUSAL_VOCAB} || {known}",
                 "asked_cause" if asks_cause else "asked_cause_default")
    return CausalGraph(f"fincausal:{case_id}", nodes, [e], {"P": ["Q1"]}, provenance="deterministic question parse (no gold)")


CLAIM_PATTERNS = [  # (regex, cause group, effect group)
    (re.compile(r"^(?P<e>.+?)\s+(?:is|are|was|were|has been|have been|can be|could be)\s+(?:caused|triggered|driven|linked to)\s+(?:by\s+)?(?P<c>.+)$", re.I), "c", "e"),
    (re.compile(r"^(?:due to|because of|thanks to|owing to)\s+(?P<c>.+?),\s*(?P<e>.+)$", re.I), "c", "e"),
    (re.compile(r"^(?P<e>.+?)\s+(?:because(?: of)?|due to|as a result of|owing to|thanks to|in response to)\s+(?P<c>.+)$", re.I), "c", "e"),
    (re.compile(r"^(?P<c>.+?)\s+(?:causes?|caused|leads? to|led to|results? in|resulted in|triggers?|triggered|contributes? to|contributed to|"
                r"increases?|increased|reduces?|reduced|prevents?|prevented|cures?|is linked to)\s+(?P<e>.+)$", re.I), "c", "e"),
]


def claim_graph(claim, case_id):
    """Deterministic causal decomposition of a claim from its text only. Returns None for claims
    without an explicit causal construction (they are evaluated as noncausal)."""
    text = claim.strip().rstrip(".")
    for rx, cg, eg in CLAIM_PATTERNS:
        m = rx.match(text)
        if m and len(m.group(cg).split()) >= 1 and len(m.group(eg).split()) >= 2:
            c, ef = m.group(cg).strip(), m.group(eg).strip()
            nodes = {"cause": Node("cause", c), "effect": Node("effect", ef)}
            edges = [Edge("C1", "cause", "effect", 1, "The claim asserts this link.", (), (), f"Did '{c}' cause or lead to '{ef}'?",
                          f"{c} {ef} because caused led to due to || {c} || {ef}", "claim")]
            return CausalGraph(f"averitec:{case_id}", nodes, edges, {"claim_path": ["C1"]}, provenance="deterministic claim parse (no gold)")
    return None


def causal_markers(text):
    return len(re.findall(r"\b(due to|because|as a result|result\w* in|led to|driven by|owing to|thanks to|caus\w+|reflect\w*|therefore|consequently|offset)\b", text, re.I))


# ================================================================ FinCausal 2026
def _read_csv(path):
    raw = Path(path).read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw), delimiter=";"))


def fincausal_split(case_id, dev_mod=5):
    """Deterministic internal split of the OFFICIAL TRAIN file: ~20% dev_internal for evaluation,
    the rest train_internal (used only as a distractor pool; nothing is trained). The official
    test file has no public gold, so it supports prediction-only runs."""
    return "dev_internal" if int(_h("fc26:" + case_id, 8), 16) % dev_mod == 0 else "train_internal"


def load_fincausal(split="dev_internal", n=None, n_distractors=200, data_dir=None):
    d = Path(data_dir or BENCH_DIR / "fincausal2026")
    if split == "test_unlabeled":
        rows, has_gold = _read_csv(d / "test_en_500.csv"), False
        pool = []
    else:
        allrows = _read_csv(d / "train_en_2000.csv")
        if split == "train_full":  # every labelled row; no separate distractor pool (fixtures / sanity runs)
            rows, pool = allrows, []
        else:
            rows = [r for r in allrows if fincausal_split(r["id"]) == split]
            pool = [r for r in allrows if fincausal_split(r["id"]) != split]
        has_gold = True
    rows = sorted(rows, key=lambda r: _h("order:" + r["id"]))[: n or None]
    ctx = {}
    for r in rows:
        ctx.setdefault(" ".join(r["context"].split()), None)
    eval_ctx = set(ctx)
    for r in sorted(pool, key=lambda r: _h("distractor:" + r["id"])):
        if len(ctx) >= len(eval_ctx) + n_distractors:
            break
        ctx.setdefault(" ".join(r["context"].split()), None)
    passages = [Passage("FC-" + _h(t), "FC-" + _h(t), t) for t in ctx]
    by_text = {p.text: p.pid for p in passages}
    cases, gold = [], {}
    for r in rows:
        cid = f"fc26-{r['id']}"
        cases.append(Case(cid, "extractive_qa", r["question"], "fincausal_controlled", {}, question_graph(r["question"], cid)))
        if has_gold:
            t = " ".join(r["context"].split())
            gold[cid] = {"answer": r["answer"], "relevant_pids": [by_text[t]],
                         "subgroup_multi_step_heuristic": causal_markers(t) >= 2, "context": r["context"]}
    info = {**SOURCES["fincausal2026"], "split": split, "n_cases": len(cases), "n_passages": len(passages),
            "n_distractor_passages": len(passages) - len(eval_ctx),
            "corpus_note": "Controlled retrieval corpus constructed for this project: every evaluated case's own context plus "
                           f"{len(passages) - len(eval_ctx)} distractor contexts from the other internal split. FinCausal is an "
                           "extractive QA dataset, not a native document-retrieval benchmark.",
            "split_note": "dev_internal = deterministic ~20% hash split of the official training file (the official test gold is not public).",
            "multi_step_note": "The released CSV does not mark multi-step chains; the subgroup flag (>=2 causal connectives in the gold context) is a heuristic computed in the evaluation layer only.",
            "has_gold": has_gold}
    return Benchmark("fincausal2026", split, cases, {"fincausal_controlled": passages}, GoldStore(gold), info)


# ================================================================ AVeriTeC
def canon_label(lbl):
    lbl = AVERITEC_ALIASES.get(lbl, lbl)
    if lbl not in AVERITEC_LABELS:
        raise ValueError(f"Unknown AVeriTeC label {lbl!r}; refusing to map it silently.")
    return lbl


def load_averitec(split="dev", n=None, data_dir=None, causal_only=None):
    d = Path(data_dir or BENCH_DIR / "averitec")
    claims = json.loads((d / f"{split}.json").read_text())
    pools = {}
    pool_file = d / f"{split}_top_k_sentences.json"
    if pool_file.exists():
        for line in pool_file.read_text().split("\n"):  # not splitlines(): sentences contain U+2028
            if line.strip():
                r = json.loads(line)
                pools[int(r["claim_id"])] = r
    idx = list(range(len(claims)))
    if causal_only is not None:  # selection uses annotator claim_types => recorded as evaluation subgroup choice
        idx = [i for i in idx if ("Causal Claim" in claims[i].get("claim_types", [])) == causal_only]
    idx = sorted(idx, key=lambda i: _h(f"averitec:{split}:{i}"))[: n or None]
    cases, corpora, gold = [], {}, {}
    for i in idx:
        c = claims[i]
        cid = f"averitec-{split}-{i}"
        pool = pools.get(i)
        if pool and pool["claim"] != c["claim"]:
            raise ValueError(f"evidence pool misaligned for claim {i}")
        corpora[cid] = [Passage(f"{cid}-s{j:03d}", s.get("url") or f"{cid}-s{j:03d}", s["sentence"], s.get("url", ""))
                        for j, s in enumerate(pool["top_100"])] if pool else []
        cases.append(Case(cid, "claim_verification", c["claim"], cid,
                          {"claim_date": c.get("claim_date"), "speaker": c.get("speaker")}, claim_graph(c["claim"], cid)))
        if "label" in c and c["label"] is not None:
            qa = [{"question": q["question"], "answers": [a.get("answer", "") + (f" ({a['boolean_explanation']})" if a.get("boolean_explanation") else "")
                                                          for a in q.get("answers", [])],
                   "source_urls": [a.get("source_url") for a in q.get("answers", []) if a.get("source_url")]} for q in c.get("questions", [])]
            gold[cid] = {"label": canon_label(c["label"]), "qa_evidence": qa, "justification": c.get("justification"),
                         "relevant_urls": sorted({u for q in qa for u in q["source_urls"]}),
                         "subgroup_causal_annotated": "Causal Claim" in c.get("claim_types", []),
                         "claim_types": c.get("claim_types", [])}
    info = {**SOURCES["averitec"], "split": split, "n_cases": len(cases),
            "corpus_note": "Per-claim evidence pool = the official baseline's top-100 sentences from the official dev knowledge store "
                           "(pre-ranked by the organisers with the claim as query, which can favour the ordinary claim query). "
                           "Each method selects its own evidence from this pool under the same budget.",
            "relevance_note": "No sentence-level gold relevance exists. Retrieval is reported only as a PROXY: whether a retrieved "
                              "sentence's URL equals an annotated answer source URL.",
            "time_note": "Pool sentences carry no publication date; point-in-time filtering relative to claim_date is not possible here.",
            "split_note": "Official dev split (labelled). The official test split has no public labels.",
            "has_gold": bool(gold), "n_cases_without_pool": sum(1 for c in cases if not corpora[c.case_id])}
    return Benchmark("averitec", split, cases, corpora, GoldStore(gold), info)
