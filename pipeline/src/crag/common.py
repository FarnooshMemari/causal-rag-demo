"""Paths, config loading, timestamps."""
import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
RAW = ROOT / "data" / "raw"
CORPUS = ROOT / "data" / "corpus"
CACHE = ROOT / "cache"
OUT = ROOT / "outputs"
ANNOT = ROOT / "annotations"
ET = ZoneInfo("America/New_York")

# Generic UA; SEC asks for a contact, supplied via env var rather than hard-coded.
USER_AGENT = os.environ.get("CRAG_USER_AGENT", "causal-rag-mvp academic research (Duke x BNY capstone)")


def load(name):
    return json.loads((CONFIG / name).read_text())


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def read_jsonl(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def available_at(published_at, precision):
    """Earliest time a document is treated as available. Date-only stamps are
    pushed to 23:59:59 ET that day, so they can never leak in early."""
    if precision == "date":
        d = datetime.fromisoformat(published_at).date()
        return datetime.combine(d, time(23, 59, 59), ET)
    dt = datetime.fromisoformat(published_at)
    return dt if dt.tzinfo else dt.replace(tzinfo=ET)


def cutoff():
    return datetime.fromisoformat(load("event.json")["decision_cutoff"])
