# Plan 001 — Verifiable ingest

Implements `spec.md`. Architecture, module layout, data model, read surfaces, phasing, testing.

## Architecture — three stages, one trust boundary

```
                   impure                         PURE (golden-testable)          consumer
  ┌────────────┐   harvest   ┌───────────────┐   promotion pass   ┌──────────┐   ┌────────┐
  │ LightRAG    │──────────▶ │ store snapshot │──────────────────▶│ bundle    │──▶│ mkn10  │
  │ deployed    │  reads DB   │ (files, raw)   │  file→file, no DB  │ nodes/    │   │ harvest│
  │ store        │            │ chunks/nodes/  │  no LLM            │ edges/    │   └────────┘
  │ (PG + Neo4j) │            │ edges/docmeta  │                    │ manifest  │
  └────────────┘            └───────────────┘                    └──────────┘
```

- **Harvest (impure, thin):** read the deployed store → write a raw snapshot as files. The *only* stage that touches a DB. Kept deliberately dumb (dump, don't transform) so all logic is testable.
- **Promotion pass (pure):** deterministic functions `snapshot files → bundle files`. No DB, no LLM, no network. This is the trust boundary and where all G1–G5 logic lives. **Golden-file tested.**
- **Bundle:** immutable `nodes.jsonl + edges.jsonl + manifest.json (+ quarantine.jsonl)`. The consumer (mkn10) harvests it; the graph-DB export stays a *projection* of the bundle, never the source of truth.

**Why the harvest/pure split:** the brief requires "pure deterministic functions over files" (acceptance #2) and golden tests without an LLM (#7). Snapshotting first makes G1–G4 unit-testable on a fixture and keeps the fork's vendored LightRAG untouched (clean upstream rebase).

## Module layout

New **top-level `promotion/` package** (NOT under `lightrag/` — keeps the fork delta off the vendored library, so upstream rebases don't conflict):

```
promotion/
  __init__.py
  harvest.py          # impure: deployed store → snapshot/ (the only DB-touching file)
  registry.py         # G2: build chunk_id → ChunkRecord registry from the snapshot
  locate.py           # G1: normalize + inflection-tolerant span match → (start,end) or None
  canonicalize.py     # G5: name normalization + versioned alias table + type-enum validation
  edition.py          # G3: filename/override manifest → (work_id, edition_date); supersession + conflict-key
  promote.py          # the pure spine: snapshot → GroundedRecord nodes/edges + quarantine
  bundle.py           # G4: canonical sort + content-hash manifest + write nodes/edges/manifest jsonl
  delta.py            # G4: bundle vs previous bundle → added/removed/changed by stable id
  ratchets.py         # G4: quarantine non-increasing, anchor coverage 100%, doc coverage non-decreasing
  types.py            # dataclasses: ChunkRecord, GroundedNode, GroundedEdge, Anchor, Manifest, Quarantine
  cli.py              # `python -m promotion harvest|promote|delta` glue
  enums/
    entity_types.yaml # the ~5–15 controlled entity-type enum
    aliases.yaml      # versioned alias table (canonical ← variants)
tests/promotion/
  fixtures/two-edition-corpus/   # tiny hand-made 2-edition snapshot (no LLM, no PDFs)
  test_locate.py test_edition.py test_promote.py test_bundle.py test_delta.py test_ratchets.py
```

## Read surfaces (harvest.py only)

| Data | Surface | Fields used |
|---|---|---|
| entities | `rag.chunk_entity_relation_graph.get_all_nodes()` (Neo4j `get_all_nodes`, `neo4j_impl.py:1766`) | `entity_id`/name, `entity_type`, `description`, `source_id` (`<SEP>`-joined chunk ids), `file_path` |
| edges | `...get_all_edges()` (`neo4j_impl.py:1791`) | `source`, `target`, `keywords`, `description`, `source_id`, `file_path` |
| chunks | chunk KV store (`PGKVStorage` text_chunks) `get_by_ids` / `get_all` | `chunk_id`, `content`, `full_doc_id`, `file_path`, `chunk_order_index` |
| corpus/doc status | `rag.get_docs_by_status()` (`lightrag.py:2469`) | `doc_id`, `file_path`, `status`, `content_summary`, counts |

Harvest writes: `snapshot/nodes.jsonl`, `snapshot/edges.jsonl`, `snapshot/chunks.jsonl`, `snapshot/docs.jsonl` (verbatim, no transform).

## Data model (`types.py`)

```
ChunkRecord   = {chunk_id, doc_id, work_id, edition_date, char_len, text, content_hash, page?=None}
Anchor        = {chunk_id, start, end, match: "exact"|"normalized"|"stemmed", page?=None}
GroundedNode  = {node_id, canonical_name, surface_forms[], type, as_of, work_id, edition_date,
                 anchors[], source_ids[], fidelity: "verified", superseded_by_edition?=None}
GroundedEdge  = {edge_id, head_id, rel_type, tail_id, keywords, description, as_of, work_id,
                 edition_date, anchor, fidelity: "verified"}         # label = source-anchored co-occurrence
Quarantine    = {kind: "entity"|"edge", raw_name/endpoints, source_id, reason, work_id, edition_date}
Manifest      = {content_hash, corpus:[{doc_id, work_id, edition_date, content_hash}], pins:{library_version,
                 prompt_hash, code_sha}, counts:{nodes, edges, quarantined, anchor_coverage=1.0, doc_coverage}}
```

Stable ids: `node_id = sha1(canonical_name, type)`; `edge_id = sha1(head_id, rel_type, tail_id, work_id, edition_date)`. Fact-key (conflict detection) = `(canonical_head, rel_type, canonical_tail_or_attr)`.

## G1 locate (`locate.py`) — the one subtle algorithm

`locate(surface_form, chunk_text) -> Anchor | None`:
1. Normalize both (NFC, casefold, strip diacritics via `unicodedata`, collapse whitespace/punct). Exact normalized substring → `match="exact/normalized"`, offsets mapped back to the raw chunk.
2. Miss → **token-level tolerant match**: stem each token (lightweight Czech suffix stripping — no heavy NLP dep) and find the minimal chunk window containing all stems in order-tolerant proximity; if coverage ≥ threshold (default 0.8) → `match="stemmed"`, span = window.
3. Below threshold → `None` → quarantine `entity-not-found`.

Edge admitted only if **both** endpoints locate in the same chunk (else `endpoint-missing`); `chunk-unresolved` if `source_id` has no registry entry. The matcher is pure + table-driven so its recall is measurable on the fixture and tunable without touching the spine.

## Phasing (brief order; each phase = one commit; no squash)

1. **P1 — G2 registry + harvest** (`harvest.py`, `registry.py`, `types.py`). Verify: harvest a snapshot from the live store into files; registry joins 100% of the fixture's `source_id`s.
2. **P2 — G1 promotion spine** (`locate.py`, `promote.py`, quarantine). Verify: on the fixture, every emitted node/edge has an anchor; ungrounded → quarantine.jsonl with the right reason; anchor coverage = 100% by construction.
3. **P3 — G3 editions** (`edition.py`; wire `as_of`/supersession/conflict-key into `promote.py`). Verify: 2-edition fixture → latest-edition default view, older-only fact `superseded_by_edition`, same-key-diff-value → conflict flag.
4. **P4 — G4 bundle + manifest-hash (ship first), then delta + ratchets** (`bundle.py`, then `delta.py`, `ratchets.py`, `cli.py`). Verify: re-emit of identical snapshot → identical content hash; a changed fixture → correct delta; ratchets catch a regression.
5. **P5 — G5 typing + canonicalization** (`canonicalize.py`, `enums/*.yaml`; validate at promotion). Verify: case-variant names merge (`Praktický lékář`); type ∉ enum → `other` or quarantine; alias table applied.
6. **Golden tests throughout** — each phase lands with its `tests/promotion/test_*.py` green (pure, no LLM/DB).

## Testing

- **Golden-file fixture** `tests/promotion/fixtures/two-edition-corpus/`: a hand-authored snapshot (chunks/nodes/edges/docs jsonl) covering two editions of one work with (a) a restated fact (overlap), (b) a changed fact (conflict), (c) an ungroundable entity (quarantine), (d) an inflected surface form (stemmed match). No PDFs, no LLM, no DB.
- `pytest -m offline` marker (matches repo convention); pure functions ⇒ deterministic asserts on the emitted bundle bytes + manifest hash.
- One **impure smoke** (opt-in, network-gated, not in CI): `harvest.py` against the live deployment produces a well-formed snapshot — kept out of the default suite.

## Risks / open items

- **Czech inflection recall.** Threshold-driven stemmer is a heuristic; the fixture measures recall, and misses quarantine (safe — never a false-admit). If recall is poor on real data, the follow-up is constraining the extraction prompt to quote its evidence (a separate change, flagged not gated).
- **Edition metadata from filenames.** Robust for the current corpus (`Work_YEAR.md`); the override manifest handles exceptions. Live 2-edition validation → child brief.
- **No page/bbox.** Anchors are char-span in chunk; page precision waits on PDF re-ingest (child brief).
- **Upstream rebase.** `promotion/` is decoupled; only `harvest.py` depends on LightRAG read APIs (a thin, single adapter point per the brief's G6).
