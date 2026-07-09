"""The pure promotion spine: snapshot -> Bundle (grounded records + quarantine).

The repo is the last writer here. A node/edge enters the bundle only if G1
locates its surface form(s) in the chunk its ``source_id`` points to; the found
offsets become the anchor. Ungrounded -> quarantine (machine-readable reason),
never admitted-with-a-marker, never silently dropped (emitted-surface-forms +
quarantined covers every input). Grounded nodes are then merged by their
canonical key (G5), stamped with edition/supersession, and cross-edition
conflicts flagged (G3).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .canonicalize import load_aliases, load_type_enum, merge_key, validate_type
from .edition import (
    edition_sort_key,
    flag_conflicts,
    latest_edition,
    mark_supersession,
    work_latest_editions,
)
from .hashing import sha1_hex
from .locate import locate
from .registry import build_registry
from .types import Anchor, Bundle, GroundedEdge, GroundedNode, Quarantine


def _node_id(merge_key_: str, type_: str) -> str:
    # Keyed on the canonical merge key (not the display name) so case/diacritic
    # variants share an id and the id is stable across re-emits.
    return sha1_hex(merge_key_, type_)


def _edge_id(head_id: str, rel_type: str, tail_id: str, work_id: str, edition_date: str) -> str:
    return sha1_hex(head_id, rel_type, tail_id, work_id, edition_date)


# MinerU sidecar block IDs (tb-/im-/eq-<dochash>-NNNN) leak into extraction as entity
# names; they are never text and cannot ground. Drop them (and any edge that touches one)
# before the gate so they never pollute the quarantine sidecar
# (brief: guidelines-extraction-block-id-entities).
# The dochash is a 32-char hex; require >=16 hex (case-insensitive) so a real entity
# like `tb-abc123-01` can't be swept up, while any MinerU block id still matches.
_BLOCK_ID_RE = re.compile(r"^(tb|im|eq)-[0-9a-f]{16,}-\d+$", re.IGNORECASE)


def _is_block_id(name: str) -> bool:
    return bool(name) and _BLOCK_ID_RE.match(name) is not None


def promote(snapshot: dict[str, list[dict]], overrides=None) -> Bundle:
    registry = build_registry(snapshot["chunks"], snapshot["docs"], overrides)
    type_enum = load_type_enum()
    aliases = load_aliases()

    quarantine: list[Quarantine] = []

    # Pre-filter: drop MinerU block-ID pseudo-entities (and any edge touching one)
    # before the gate — they cannot ground and would only be quarantine noise.
    input_nodes = [n for n in snapshot["nodes"] if not _is_block_id(n.get("name", ""))]
    input_edges = [
        e
        for e in snapshot["edges"]
        if not (_is_block_id(e.get("head", "")) or _is_block_id(e.get("tail", "")))
    ]

    # Phase A — ground each input node (locate-or-quarantine).
    grounded: list[dict] = []
    for n in input_nodes:
        anchors: list[Anchor] = []
        editions: list[str] = []
        works: list[str] = []
        chunk_missing = False
        for sid in n.get("source_ids", []):
            chunk = registry.get(sid)
            if chunk is None:
                chunk_missing = True
                continue
            a = locate(n["name"], chunk.content, sid)
            if a:
                anchors.append(a)
                editions.append(chunk.edition_date)
                works.append(chunk.work_id)
        if not anchors:
            reason = "chunk-unresolved" if chunk_missing else "entity-not-found"
            quarantine.append(Quarantine("entity", n["name"], reason, n.get("source_ids", [])))
            continue
        grounded.append(
            {
                "name": n["name"],
                "type": validate_type(n.get("type", "Other"), type_enum),
                "anchors": anchors,
                "editions": editions,
                "works": works,
                "source_ids": n.get("source_ids", []),
                "concept_ref": n.get("concept_ref"),
                "description": n.get("description", ""),
            }
        )

    work_latest = work_latest_editions(registry)

    # Phase B — merge grounded nodes sharing a canonical key (case/diacritic/
    # alias). Grouped on the key ALONE (not key+type) so a name that LightRAG
    # emitted under two types collapses to one node instead of a name->node
    # collision; the type is the dominant one (deterministic tiebreak).
    groups: dict[str, list[dict]] = defaultdict(list)
    for g in grounded:
        groups[merge_key(g["name"], aliases)].append(g)

    nodes: list[GroundedNode] = []
    by_name: dict[str, GroundedNode] = {}
    for mkey, members in groups.items():
        names = sorted({m["name"] for m in members})
        counts = Counter(m["type"] for m in members)
        top = max(counts.values())
        type_ = sorted(t for t, c in counts.items() if c == top)[0]
        editions = [e for m in members for e in m["editions"]]
        works = sorted({w for m in members for w in m["works"]})
        appearances = {
            (w, e) for m in members for w, e in zip(m["works"], m["editions"])
        }
        # A concept is current if it appears in the latest edition of ANY of its
        # works (a node spans many works — e.g. Hypertenze in 17 DPs — so a single
        # work's edition can't decide supersession).
        current = any(work_latest.get(w) == e for w, e in appearances)
        superseded = (
            None
            if current
            else max((work_latest[w] for w in works), key=edition_sort_key, default=None)
        )
        node = GroundedNode(
            node_id=_node_id(mkey, type_),
            canonical_name=names[0],  # deterministic display among variants
            type=type_,
            surface_forms=names,
            as_of=latest_edition(editions),
            work_id=works[0] if works else "",
            edition_date=latest_edition(editions),
            anchors=[a for m in members for a in m["anchors"]],
            source_ids=sorted({s for m in members for s in m["source_ids"]}),
            description=next((m["description"] for m in members if m["description"]), ""),
            concept_ref=next((m["concept_ref"] for m in members if m["concept_ref"]), None),
            superseded_by_edition=superseded,
        )
        nodes.append(node)
        for m in members:
            by_name[m["name"]] = node

    # Phase C — edges: both endpoints admitted AND locatable in the edge's chunk.
    edges: list[GroundedEdge] = []
    for e in input_edges:
        head, tail = by_name.get(e["head"]), by_name.get(e["tail"])
        if head is None or tail is None:
            # an endpoint was itself quarantined / never extracted -> re-extract
            quarantine.append(
                Quarantine("edge", f'{e["head"]} -> {e["tail"]}', "endpoint-quarantined", e.get("source_ids", []))
            )
            continue
        candidates: list[tuple] = []
        for sid in e.get("source_ids", []):
            chunk = registry.get(sid)
            if chunk is None:
                continue
            ha, ta = locate(e["head"], chunk.content, sid), locate(e["tail"], chunk.content, sid)
            if ha and ta:
                candidates.append((chunk, ha))
        if not candidates:
            # both endpoints exist but never co-occur in a source chunk -> fix source_ids
            quarantine.append(
                Quarantine("edge", f'{e["head"]} -> {e["tail"]}', "endpoints-not-co-locatable", e.get("source_ids", []))
            )
            continue
        # An edge asserted across editions is stamped with its LATEST (current)
        # assertion; older-only edges fall out as superseded below.
        chunk, anchor = max(candidates, key=lambda c: edition_sort_key(c[0].edition_date))
        edition, work = chunk.edition_date, chunk.work_id
        rel_type = e.get("rel_type") or "related"
        edges.append(
            GroundedEdge(
                edge_id=_edge_id(head.node_id, rel_type, tail.node_id, work, edition),
                head_id=head.node_id,
                tail_id=tail.node_id,
                rel_type=rel_type,
                keywords=e.get("keywords", ""),
                description=e.get("description", ""),
                as_of=edition,
                work_id=work,
                edition_date=edition,
                anchor=anchor,
            )
        )

    # Phase D — edition supersession for edges (nodes handled per-work in Phase
    # B) + cross-edition conflict flags.
    mark_supersession(edges, work_latest)
    flag_conflicts(edges)

    return Bundle(nodes=nodes, edges=edges, quarantine=quarantine)
