"""Minimal cached LLM client returning schema-constrained JSON.

Providers (CRAG_LLM_PROVIDER):
  claude_cli (default)  - the locally authenticated `claude` CLI in headless mode (-p) with all
                          tools disabled and no user/project settings loaded. No key in this code.
  anthropic             - ANTHROPIC_API_KEY, Messages API via HTTP          (implemented, not executed)
  openai                - OPENAI_API_KEY, Chat Completions json_schema       (implemented, not executed)
Model: CRAG_LLM_MODEL (default claude-sonnet-5-5 / gpt-4o for openai).

Every response is cached in cache/llm/<sha256>.json keyed on (provider, model, system, user,
schema, repeat). Re-running the pipeline never re-bills a call; delete the cache to re-query.
"""
import hashlib
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone

import requests

from .common import CACHE

PROVIDER = os.environ.get("CRAG_LLM_PROVIDER", "claude_cli")
MODEL = os.environ.get("CRAG_LLM_MODEL", "gpt-4o" if PROVIDER == "openai" else "claude-sonnet-5-5")
CALL_LIMIT = int(os.environ.get("CRAG_MAX_LLM_CALLS", "60"))  # hard cap on uncached calls per process
_calls = {"n": 0, "cost_usd": 0.0}
_lock = threading.Lock()  # complete_json may be called from a small thread pool


class LLMUnavailable(RuntimeError):
    pass


def _claude_cli(system, user, schema):
    cmd = ["claude", "-p", "--model", MODEL, "--tools", "", "--strict-mcp-config", "--setting-sources", "",
           "--no-session-persistence", "--system-prompt", system, "--output-format", "json",
           "--json-schema", json.dumps(schema)]
    try:
        p = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=600,
                           cwd=str(CACHE))  # neutral cwd: no project CLAUDE.md is picked up
    except FileNotFoundError as e:
        raise LLMUnavailable("`claude` CLI not found") from e
    if p.returncode != 0:
        raise LLMUnavailable(f"claude CLI failed: {p.stderr[:300] or p.stdout[:300]}")
    d = json.loads(p.stdout)
    if d.get("is_error") or d.get("structured_output") is None:
        raise RuntimeError(f"no structured output: {str(d.get('result'))[:300]}")
    return d["structured_output"], {"cost_usd": d.get("total_cost_usd"), "usage": d.get("usage", {}).get("output_tokens")}


def _anthropic(system, user, schema):
    key = os.environ.get("ANTHROPIC_API_KEY") or _missing("ANTHROPIC_API_KEY")
    tool = {"name": "submit", "description": "Submit the assessment", "input_schema": schema}
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=300, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 4096, "system": system, "tools": [tool],
              "tool_choice": {"type": "tool", "name": "submit"}, "messages": [{"role": "user", "content": user}]})
    r.raise_for_status()
    block = next(b for b in r.json()["content"] if b["type"] == "tool_use")
    return block["input"], {"usage": r.json().get("usage")}


def _openai(system, user, schema):
    key = os.environ.get("OPENAI_API_KEY") or _missing("OPENAI_API_KEY")
    r = requests.post("https://api.openai.com/v1/chat/completions", timeout=300, headers={"Authorization": f"Bearer {key}"},
                      json={"model": MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                            "response_format": {"type": "json_schema", "json_schema": {"name": "assessment", "schema": schema, "strict": False}}})
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"]), {"usage": r.json().get("usage")}


def _missing(var):
    raise LLMUnavailable(f"{var} is not set")


def cache_path(system, user, schema, repeat=0, version=None):
    """v1 keys (version=None) are unchanged; a version string adds to the key and selects
    its own cache directory (cache/llm_<version>/), so versions can never collide."""
    parts = [PROVIDER, MODEL, system, user, schema, repeat] + ([version] if version else [])
    key = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    return CACHE / (f"llm_{version}" if version else "llm") / f"{key}.json"


def complete_json(system, user, schema, repeat=0, tag="", version=None):
    path = cache_path(system, user, schema, repeat, version)
    if path.exists():
        rec = json.loads(path.read_text())
        return rec["output"], rec
    with _lock:
        if _calls["n"] >= CALL_LIMIT:
            raise LLMUnavailable(f"CRAG_MAX_LLM_CALLS={CALL_LIMIT} reached")
        _calls["n"] += 1  # reserve the slot before the call so concurrent workers respect the cap
    fn = {"claude_cli": _claude_cli, "anthropic": _anthropic, "openai": _openai}[PROVIDER]
    t0 = time.time()
    last = None
    for attempt in range(2):  # one retry on malformed output
        try:
            out, meta = fn(system, user, schema)
            break
        except LLMUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
    else:
        raise RuntimeError(f"LLM call failed twice: {last}")
    with _lock:
        _calls["cost_usd"] += (meta.get("cost_usd") or 0)
    rec = {"tag": tag, "version": version or "v1", "provider": PROVIDER, "model": MODEL, "repeat": repeat, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "latency_s": round(time.time() - t0, 1), "meta": meta, "system": system, "user": user, "schema": schema, "output": out}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    print(f"  LLM call [{tag} r{repeat}] {rec['latency_s']}s cost=${meta.get('cost_usd')}")
    return out, rec


def stats():
    return dict(_calls)
