"""r2 synthetic test-design revision for the frozen E1 v2 assessor (see revision.json).

    PYTHONPATH=src python tests/fixtures/e1_v2_synthetic_r2/run_fixtures_r2.py --allow-llm

Only change vs r1: the recorded instruction is prepended to each fixture's user input.
Results: outputs/v2_e1/synthetic_fixture_results_r2.json; cache: cache/llm_e1_v2_fixtures_r2/.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
from crag import llm  # noqa: E402
from crag.common import load, write_json  # noqa: E402
from crag.v2_e1 import V2_OUT, build_prompt, schema, spec, system_prompt, validate  # noqa: E402

if "--allow-llm" not in sys.argv:
    raise SystemExit("Refusing to call the LLM without --allow-llm (3 calls).")
llm.CALL_LIMIT = 3

rev = json.loads((HERE / "revision.json").read_text())
fx_path = ROOT / rev["fixtures_file"]
assert hashlib.sha256(fx_path.read_bytes()).hexdigest() == rev["fixtures_sha256"], "fixtures changed since revision was recorded"
fx = json.loads(fx_path.read_text())["fixtures"]
expected = json.loads((HERE / "expected_labels.json").read_text())
s, event = spec(), load("event.json")
sysp, sch = system_prompt(s), schema()
results = {"_doc": "SYNTHETIC r2 test-design revision: scenario interpretation of fictional premises; not real evidence.",
           "revision": rev["revision"], "instruction": rev["instruction"], "fixtures": []}
for f in fx:
    chunk = {k: f[k] for k in ("chunk_id", "doc_id", "available_at_et", "text")}
    user = rev["instruction"] + "\n\n" + build_prompt(s, [chunk], event)
    assert not any(lbl in user for lbl in ("supported", "contradicted", "insufficient_evidence", "expected_labels")), "label leaked"
    out, _ = llm.complete_json(sysp, user, sch, repeat=0, tag=f"v2_E1_fixture_r2_{f['fixture_id']}", version="e1_v2_fixtures_r2")
    item = next((a for a in out["assessments"] if a["edge_id"] == "E1"), None)
    res = validate(item, {chunk["chunk_id"]}, {chunk["chunk_id"]: chunk}) if item else {"error": "E1 missing", "label": None, "validated_label": "insufficient_evidence"}
    exp = expected[f["fixture_id"]]["expected"]
    results["fixtures"].append({"fixture_id": f["fixture_id"], "synthetic": True, "expected": exp,
                                "result": "PASS" if res["validated_label"] == exp else "FAIL", **res})
    print(f"{f['fixture_id']}: expected={exp} raw={res.get('label')} validated={res['validated_label']} -> {results['fixtures'][-1]['result']}")
write_json(V2_OUT / "synthetic_fixture_results_r2.json", results)
