"""G4 — the reviewable delta between two bundles, by stable id.

added / removed / changed (same id, different content). A removal with no
corresponding corpus change is the red flag the review looks for. Works on
either ``Bundle`` objects (tests) or the written JSONL dicts (CLI).
"""

from __future__ import annotations

import json
from typing import Any

from .hashing import sha1_hex
from .types import Bundle


def _index(dicts: list[dict], id_field: str) -> dict[str, str]:
    return {
        d[id_field]: sha1_hex(json.dumps(d, sort_keys=True, ensure_ascii=False))
        for d in dicts
    }


def _kind_diff(prev: list[dict], curr: list[dict], id_field: str) -> dict[str, list[str]]:
    p, c = _index(prev, id_field), _index(curr, id_field)
    return {
        "added": sorted(set(c) - set(p)),
        "removed": sorted(set(p) - set(c)),
        "changed": sorted(i for i in set(p) & set(c) if p[i] != c[i]),
    }


def diff_dicts(
    prev_nodes: list[dict], curr_nodes: list[dict], prev_edges: list[dict], curr_edges: list[dict]
) -> dict[str, Any]:
    return {
        "nodes": _kind_diff(prev_nodes, curr_nodes, "node_id"),
        "edges": _kind_diff(prev_edges, curr_edges, "edge_id"),
    }


def diff(prev: Bundle, curr: Bundle) -> dict[str, Any]:
    return diff_dicts(
        [n.to_dict() for n in prev.nodes],
        [n.to_dict() for n in curr.nodes],
        [e.to_dict() for e in prev.edges],
        [e.to_dict() for e in curr.edges],
    )
