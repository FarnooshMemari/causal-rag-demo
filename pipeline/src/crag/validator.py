"""Causal Evidence Validator: a deterministic, interpretable safeguard applied AFTER the assessor.

It never upgrades a label. It can only keep it or downgrade it, and every decision carries a
reason. It checks, per edge:
  citation        quote is verbatim in a supplied chunk (reuses assess.validate statuses)
  point_in_time   cited chunk was available at the decision cutoff (when a cutoff applies)
  relationship    quote mentions the TARGET concept, and the source concept or a causal link,
                  rather than only one node (off-target evidence cannot support the edge)
  mechanism       a stated causal/attributional link, not mere co-occurrence of the two concepts
  forward         for expectation-type targets, forward-looking language (realised results are
                  not expectations)
  conflict        valid, on-target quotes on both sides => 'conflicting'
  contradiction   (v2) a 'contradicted' label needs a genuine contradiction: a quote that negates the
                  link ("had little effect on", "not driven by") or an explicit counter-example
                  ("despite") with no alternative drivers named. Opposite co-movement ("rates rose;
                  meanwhile equities rose") and offsetting forces ("offset by") are correlation, not
                  evidence against a ceteris-paribus mechanism, and are downgraded.
  assumptions     edge condition is reported as verified / unmet / not verified
  confounding     alternative drivers named in the supporting quotes are surfaced

Validation is a reasoning safeguard based on wording, not a proof of causality. Lexical rules
are crude; the assessor's optional structured fields (evidence_kind, assumption_status,
alternative_explanations) are used when present.
"""
import re
from datetime import datetime

from .assess import _norm

CAUSAL = re.compile(r"\b(because|due to|driven by|drove|driving|reflect\w*|as a result|result\w* in|result\w* from|led to|lead\w* to|"
                    r"caus\w*|owing to|thanks to|attribut\w*|contribut\w*|boost\w*|weigh\w*|in response|in light of|given|"
                    r"therefore|consequently|hence|so that|offset\w*|impact\w* of|effect\w* of|warrant\w*|spurred|fuel\w*|"
                    r"push\w* (?:up|down)|helped|hurt|constrain\w*|dampen\w*|restrain\w*)\b", re.I)
FORWARD = re.compile(r"\b(expect\w*|outlook|guidance|forecast\w*|anticipat\w*|project\w*|will|going forward|full[- ]year|"
                     r"next (?:year|quarter)|raised (?:its|our|the)? ?(?:outlook|guidance|forecast))\b", re.I)
NEGATED_LINK = re.compile(r"\b(no (?:material |significant |discernible )?(?:effect|impact|influence)|(?:little|limited|negligible) (?:effect|impact|influence)|"
                          r"did not (?:affect|weigh|lead|cause|push|drive|reduce|lift|raise)|not (?:driven|caused|explained) by|"
                          r"unaffected|unrelated|insensitive|rather than|instead of|irrespective of|regardless of)\b", re.I)
COUNTER = re.compile(r"\b(despite|even as|even though|although|notwithstanding|in spite of)\b", re.I)
CONFOUNDERS = re.compile(r"\b(pric(?:e|es|ing) increases?|menu pric\w*|inflation\w*|weather|currenc\w*|foreign exchange|acquisition\w*|"
                         r"one[- ]time|non-repeat\w*|timing|calendar|strateg\w*|cost[- ]cutting|restructuring|tax\w*)\b", re.I)


def _after(stamp, cutoff):
    return bool(stamp) and datetime.fromisoformat(stamp) > cutoff


def _has(terms, text):
    t = _norm(text).lower()
    return any(term.lower() in t for term in terms)


def classify_quote(quote, rule):
    """Strength of one quote for one edge: causal_statement > co_mention > target_only > off_target."""
    tgt, src = _has(rule.get("target_terms", []), quote), _has(rule.get("source_terms", []), quote)
    causal = bool(CAUSAL.search(quote))
    if not tgt:
        kind = "off_target"
    elif causal and (src or rule.get("allow_implicit_source")):
        kind = "causal_statement"
    elif src:
        kind = "co_mention"
    else:
        kind = "target_only"
    contra = "negated_link" if NEGATED_LINK.search(quote) else "counter_example" if COUNTER.search(quote) else \
        "offsetting" if re.search(r"\boffset\w*", quote, re.I) else "co_movement"
    return {"kind": kind, "forward_looking": bool(FORWARD.search(quote)), "contradiction_type": contra,
            "confounders": sorted({m.group(0).lower() for m in CONFOUNDERS.finditer(quote)})}


def validate_edge(item, rule, lookup=None, cutoff=None, condition=""):
    """item: assessor output already passed through assess.validate (has citation_status,
    validated_label). rule: {source_terms, target_terms, requires_forward_looking, ...}.
    Returns an interpretable judgment that is never stronger than the assessor's label."""
    lookup = lookup or {}
    reasons, sides = [], {}
    for side in ("supporting_evidence", "contradicting_evidence"):
        kept = []
        for ev in item.get(side, []):
            d = {"chunk_id": ev.get("chunk_id"), "quote": ev.get("quote", ""), "citation_status": ev.get("citation_status", "unchecked")}
            if d["citation_status"] != "valid":
                d["excluded"] = "invalid citation"
            elif cutoff is not None and _after(lookup.get(ev.get("chunk_id"), {}).get("available_at_et"), cutoff):
                d["excluded"] = "published after the decision cutoff"
            d.update(classify_quote(d["quote"], rule))
            kept.append(d)
        sides[side] = kept
    usable = lambda side: [q for q in sides[side] if "excluded" not in q and q["kind"] != "off_target"]
    sup, con_all = usable("supporting_evidence"), usable("contradicting_evidence")
    raw = item.get("validated_label", item.get("label"))
    alternatives = sorted({c for q in con_all for c in q["confounders"]} | set(item.get("alternative_explanations") or []))
    # genuine contradiction: the link itself is negated, or an explicit counter-example with no other named drivers
    con = [q for q in con_all if q["kind"] != "target_only" and (q["contradiction_type"] == "negated_link"
           or (q["contradiction_type"] == "counter_example" and not alternatives))]
    kind_hint = item.get("evidence_kind")  # optional assessor field
    checks = {"citation": all(q["citation_status"] == "valid" for s in sides.values() for q in s),
              "point_in_time": not any(q.get("excluded") == "published after the decision cutoff" for s in sides.values() for q in s)}

    off = [q for q in sides["supporting_evidence"] if "excluded" not in q and q["kind"] == "off_target"]
    if off and raw == "supported":
        reasons.append(f"{len(off)} supporting quote(s) do not mention the target concept (off-target evidence).")
    if not checks["point_in_time"]:
        reasons.append("Some cited evidence was published after the decision cutoff and was excluded.")
    if not checks["citation"]:
        reasons.append("Some quotes could not be verified verbatim in the cited excerpt and were excluded.")

    strong = [q for q in sup if q["kind"] == "causal_statement" or (q["kind"] == "co_mention" and kind_hint in ("mechanism", "explicit_attribution"))]
    if rule.get("requires_forward_looking"):
        fwd = [q for q in strong if q["forward_looking"]]
        if strong and not fwd:
            reasons.append("Target is an expectation, but supporting quotes describe realised results, not forward-looking guidance.")
        strong = fwd
    checks.update(relationship=bool(sup), mechanism=bool(strong), conflict=bool(sup) and bool(con),
                  contradiction="causal" if con else ("correlation_only" if con_all else "none"))

    assumption = item.get("assumption_status") or "not_verified"
    checks["assumptions"] = assumption
    confounders = sorted({c for q in sup for c in q["confounders"]} | set(item.get("alternative_explanations") or []))
    checks["confounding"] = confounders

    if raw == "contradicted":
        judgment = "contradicted" if con else "insufficient_evidence"
        if not con_all:
            reasons.append("No valid, on-target contradicting quote.")
        elif not con:
            kinds = sorted({q["contradiction_type"].replace("_", "-") for q in con_all})
            reasons.append(f"Contradicting quotes show {', '.join(kinds)} only: concurrent movements are correlation and do not "
                           "refute a ceteris-paribus mechanism" + (f" (other drivers named: {', '.join(alternatives)})." if alternatives else "."))
        elif assumption == "unmet":
            judgment = "insufficient_evidence"
            reasons.append("The edge's condition is reported as unmet, so contrary evidence cannot test the edge.")
        elif sup:
            judgment = "conflicting"
            reasons.append("Valid on-target evidence exists on both sides.")
    elif raw == "supported":
        if not sup:
            judgment = "insufficient_evidence"
            reasons.append("No valid supporting quote addresses the claimed relationship.")
        elif not strong:
            judgment = "insufficient_evidence"
            if not rule.get("requires_forward_looking") or not reasons:
                reasons.append("Evidence shows the concepts together but states no causal link or mechanism (association only).")
        elif con:
            judgment = "conflicting"
            reasons.append("Valid on-target evidence exists on both sides.")
        elif assumption == "unmet":
            judgment = "insufficient_evidence"
            reasons.append("The edge's condition is reported as unmet.")
        else:
            judgment = "supported"
    else:
        judgment = "insufficient_evidence"
        if not sup and not con:
            reasons.append("Evidence is missing or does not address the relationship.")
    if judgment == "supported" and assumption == "not_verified" and condition:
        reasons.append("Supported wording only; the edge condition was not verified by the evidence.")
    if confounders and judgment in ("supported", "conflicting"):
        reasons.append("Plausible alternative drivers mentioned: " + ", ".join(confounders) + ".")
    if not reasons:
        reasons.append("Validator agrees with the assessor label.")
    return {"edge_id": item.get("edge_id"), "assessor_label": raw, "judgment": judgment,
            "downgraded": judgment != raw and raw != "insufficient_evidence", "reasons": reasons,
            "checks": checks, "quotes": sides,
            "disclaimer": "Wording-based safeguard; not proof of causality."}
