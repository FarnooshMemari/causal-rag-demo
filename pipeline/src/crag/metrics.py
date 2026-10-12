"""Evaluation metrics. Pure functions; only the evaluation layer passes gold labels in."""
import math
import re
import string
from collections import Counter


# ---------------------------------------------------------------- extractive QA (SQuAD-style)
def normalize_answer(s):
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    return " ".join(s.split())


def exact_match(pred, gold):
    return float(normalize_answer(pred or "") == normalize_answer(gold))


def token_f1(pred, gold):
    p, g = normalize_answer(pred or "").split(), normalize_answer(gold).split()
    if not p or not g:
        return float(p == g)
    common = Counter(p) & Counter(g)
    same = sum(common.values())
    if same == 0:
        return 0.0
    prec, rec = same / len(p), same / len(g)
    return 2 * prec * rec / (prec + rec)


# ---------------------------------------------------------------- classification
def confusion_matrix(gold, pred, labels):
    m = {g: {p: 0 for p in labels + ["(invalid)"]} for g in labels}
    for g, p in zip(gold, pred):
        m[g][p if p in labels else "(invalid)"] += 1
    return m


def classification_report(gold, pred, labels):
    """Accuracy, per-class P/R/F1, macro-F1 over the reference label set (classes absent from
    gold still count, with F1 = 0 if predicted and undefined -> 0 otherwise)."""
    n = len(gold)
    per = {}
    for c in labels:
        tp = sum(g == c and p == c for g, p in zip(gold, pred))
        fp = sum(g != c and p == c for g, p in zip(gold, pred))
        fn = sum(g == c and p != c for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0, "support": tp + fn}
    return {"n": n, "accuracy": sum(g == p for g, p in zip(gold, pred)) / n if n else None,
            "macro_f1": sum(v["f1"] for v in per.values()) / len(labels) if n else None,
            "per_class": per, "confusion_matrix": confusion_matrix(gold, pred, labels)}


# ---------------------------------------------------------------- retrieval
def hit_at_k(ranked_ids, relevant, k=None):
    ids = ranked_ids[:k] if k else ranked_ids
    return float(any(i in relevant for i in ids))


def reciprocal_rank(ranked_ids, relevant):
    return next((1.0 / (i + 1) for i, x in enumerate(ranked_ids) if x in relevant), 0.0)


def recall_at_k(ranked_ids, relevant, k=None):
    ids = ranked_ids[:k] if k else ranked_ids
    return len(set(ids) & set(relevant)) / len(relevant) if relevant else None


def ndcg_at_k(ranked_ids, relevant, k=None):
    ids = ranked_ids[:k] if k else ranked_ids
    dcg = sum(1 / math.log2(i + 2) for i, x in enumerate(ids) if x in relevant)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), len(ids))))
    return dcg / ideal if ideal else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def bootstrap_ci(xs, n=1000, seed=0, alpha=0.05):
    """Percentile bootstrap CI of the mean (deterministic seed). Small samples => wide CIs."""
    import random
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    rng = random.Random(seed)
    ms = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(n))
    return [ms[int(alpha / 2 * n)], ms[int((1 - alpha / 2) * n) - 1]]
