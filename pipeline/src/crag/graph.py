"""Reusable causal-graph representation and conservative path-level aggregation.

A graph is a hypothesis to be checked against evidence, never a finding. Edges carry their
assumed direction/sign, the condition under which theory expects them, assumptions, source
references, and the question/query used to look for evidence. Paths are ordered edge lists.

The BNY E1-E5 graph is loaded read-only from config/graph.json (frozen v1). Benchmark graphs
are built per case by the benchmark adapters; a case may have no graph at all.
"""
from dataclasses import asdict, dataclass, field

from .common import load


@dataclass(frozen=True)
class Node:
    id: str
    label: str


@dataclass(frozen=True)
class Edge:
    id: str
    source: str
    target: str
    sign: int = 1                       # +1 / -1: hypothesised direction of change, not an estimate
    condition: str = ""
    assumptions: tuple = ()
    references: tuple = ()
    question: str = ""
    query: str = ""
    path: str = ""


@dataclass
class CausalGraph:
    graph_id: str
    nodes: dict
    edges: list
    paths: dict = field(default_factory=dict)     # path_id -> [edge_id, ...]
    frozen: bool = False
    provenance: str = ""

    def edge(self, eid):
        return next(e for e in self.edges if e.id == eid)

    def node_label(self, nid):
        return self.nodes[nid].label if nid in self.nodes else nid

    def validate_structure(self):
        """Every edge connects known nodes; every path is a connected directed chain."""
        problems = [f"{e.id}: unknown node" for e in self.edges if e.source not in self.nodes or e.target not in self.nodes]
        ids = {e.id for e in self.edges}
        for pid, eids in self.paths.items():
            if any(x not in ids for x in eids):
                problems.append(f"{pid}: unknown edge")
                continue
            chain = [self.edge(x) for x in eids]
            if any(a.target != b.source for a, b in zip(chain, chain[1:])):
                problems.append(f"{pid}: edges do not form a connected chain")
        return problems

    def to_dict(self):
        return {"graph_id": self.graph_id, "frozen": self.frozen, "provenance": self.provenance,
                "nodes": [asdict(n) for n in self.nodes.values()], "edges": [asdict(e) for e in self.edges],
                "paths": self.paths}


def bny_graph():
    """The original frozen BNY retail-sales graph (config/graph.json), unchanged."""
    g = load("graph.json")
    nodes = {n["id"]: Node(n["id"], n["label"]) for n in g["nodes"]}
    edges = [Edge(e["id"], e["source"], e["target"], e["assumed_sign"], e["condition"], (e.get("mechanism", ""),),
                  tuple(e.get("references", [])), e["retrieval_question"], e["retrieval_query"], e["pathway"]) for e in g["edges"]]
    paths = {pid: p["edges"] for pid, p in g["pathways"].items()}
    return CausalGraph(g["graph_id"], nodes, edges, paths, frozen=True, provenance=g["frozen_note"])


# ------------------------------------------------------------- path-level reasoning
EDGE_STATES = ("supported", "contradicted", "conflicting", "insufficient_evidence")


def _state(j):
    """A judgment label, or a validator result. A 'contradicted' result without a causal contradiction
    (correlation only) is treated as insufficient evidence, so it cannot break a chain."""
    if isinstance(j, dict):
        if j["judgment"] == "contradicted" and j.get("checks", {}).get("contradiction", "causal") != "causal":
            return "insufficient_evidence"
        return j["judgment"]
    return j or "insufficient_evidence"


def aggregate_path(edge_ids, judgments):
    """Conservative chain rule. `judgments` maps edge_id -> validator judgment label (or validator result).
    - supported   only if EVERY edge is supported (one weak link => the chain is not supported)
    - broken      if any edge has a validated causal contradiction (co-movement alone never breaks a chain)
    - contested   if any edge has material evidence on both sides (and none is contradicted)
    - incomplete  otherwise (some edge lacks sufficient evidence)
    Edge states are never multiplied into an effect size or probability."""
    states = [_state(judgments.get(e)) for e in edge_ids]
    if all(s == "supported" for s in states):
        status = "supported"
    elif "contradicted" in states:
        status = "broken"
    elif "conflicting" in states:
        status = "contested"
    else:
        status = "incomplete"
    weakest = [e for e, s in zip(edge_ids, states) if s != "supported"]
    return {"edges": list(edge_ids), "edge_states": states, "status": status,
            "edges_supported": states.count("supported"), "edges_total": len(states), "unsupported_edges": weakest,
            "broken_by": [e for e, s in zip(edge_ids, states) if s == "contradicted"]}


def aggregate_graph(graph, judgments, path_signs=None):
    """Aggregate every path separately. Competing pathways are reported side by side; no net
    conclusion is computed, because the net effect of opposing channels is state-dependent and
    not identified by this evidence."""
    paths = {pid: aggregate_path(eids, judgments) for pid, eids in graph.paths.items()}
    for pid in paths:
        if path_signs and pid in path_signs:
            paths[pid]["hypothesised_sign_if_chain_holds"] = path_signs[pid]
    supported = [p for p, r in paths.items() if r["status"] == "supported"]
    signs = {path_signs.get(p) for p in supported} if path_signs else set()
    return {"paths": paths,
            "competing_pathways_both_supported": len(signs) > 1,
            "net_conclusion": None,
            "net_conclusion_note": "Not computed: opposing pathways are kept separate; evidence labels are not effect sizes."}
