"""Run the frozen E1 v2 assessor on the SYNTHETIC fixtures (one call each, max 3, no retries).

    PYTHONPATH=src python tests/fixtures/e1_v2_synthetic/run_fixtures.py --allow-llm

Uses the unchanged v2 system prompt, schema, prompt builder and validator. Results go to
outputs/v2_e1/synthetic_fixture_results.json; cache to cache/llm_e1_v2_fixtures/.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "src"))
from crag import llm  # noqa: E402
from crag.common import load, write_json  # noqa: E402
from crag.v2_e1 import V2_OUT, build_prompt, schema, spec, system_prompt, validate  # noqa: E402

if "--allow-llm" not in sys.argv:
    raise SystemExit("Refusing to call the LLM without --allow-llm (3 calls).")
llm.CALL_LIMIT = 3

fx = json.loads((HERE / "fixtures.json").read_text())["fixtures"]
expected = json.loads((HERE / "expected_labels.json").read_text())
s, event = spec(), load("event.json")
sysp, sch = system_prompt(s), schema()
results = {"_doc": "SYNTHETIC fixture test of the frozen E1 v2 assessor; not real evidence; tests interpretation of controlled text only.",
           "version": "e1_v2", "fixtures": []}
for f in fx:
    chunk = {k: f[k] for k in ("chunk_id", "doc_id", "available_at_et", "text")}
    user = build_prompt(s, [chunk], event)
    assert not any(lbl in user for lbl in ("supported", "contradicted", "insufficient_evidence", "expected_labels")), "label leaked into assessor input"
    out, rec = llm.complete_json(sysp, user, sch, repeat=0, tag=f"v2_E1_fixture_{f['fixture_id']}", version="e1_v2_fixtures")
    item = next((a for a in out["assessments"] if a["edge_id"] == "E1"), None)
    res = validate(item, {chunk["chunk_id"]}, {chunk["chunk_id"]: chunk}) if item else {"error": "E1 missing", "label": None, "validated_label": "insufficient_evidence"}
    exp = expected[f["fixture_id"]]["expected"]
    results["fixtures"].append({"fixture_id": f["fixture_id"], "synthetic": True, "expected": exp,
                                "result": "PASS" if res["validated_label"] == exp else "FAIL", **res})
    print(f"{f['fixture_id']}: expected={exp} raw={res.get('label')} validated={res['validated_label']} -> {results['fixtures'][-1]['result']}")
write_json(V2_OUT / "synthetic_fixture_results.json", results)
