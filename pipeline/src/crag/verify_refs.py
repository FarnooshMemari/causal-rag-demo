"""Verify every literature reference in the graph against Crossref (DOI resolves, title matches)."""
import re

import requests

from .common import OUT, USER_AGENT, load, write_json


def _n(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def run():
    graph, refs = load("graph.json"), load("references.json")
    used = {d for e in graph["edges"] for d in e["references"]}
    out, ok = {}, True
    for doi in sorted(used):
        exp = refs.get(doi, {}).get("expected_title", "")
        try:
            m = requests.get(f"https://api.crossref.org/works/{doi}", headers={"User-Agent": USER_AGENT}, timeout=30).json()["message"]
            title = m["title"][0]
            match = _n(exp) in _n(title) if exp else False
            out[doi] = {"resolved_title": title, "authors": [a.get("family") for a in m.get("author", [])],
                        "journal": (m.get("container-title") or [""])[0], "volume": m.get("volume"), "pages": m.get("page"),
                        "expected_title": exp, "title_match": match, "citation": refs.get(doi, {}).get("citation")}
        except Exception as e:  # noqa: BLE001
            out[doi], match = {"error": str(e)[:200]}, False
        ok &= match
        print(("OK  " if match else "BAD ") + doi + "  " + out[doi].get("resolved_title", out[doi].get("error", ""))[:80])
    write_json(OUT / "reference_verification.json", {"all_verified": ok, "references": out})
    return ok
