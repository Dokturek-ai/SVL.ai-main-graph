# Spec 001 — Verifiable ingest: own the egress, demote the GraphRAG store to a build artifact

- **Brief:** `dokturek/docs/briefs/2026-07-02-platform-to-guidelines-verifiable-ingest-design.md` (`status: open`)
- **Substrate decision:** `dokturek/docs/briefs/2026-07-07-platform-to-guidelines-lightrag-fork-substrate.md` — substrate = **this fork** (`Dokturek-ai/SVL.ai-main-graph`), in-repo `lightrag_local` wrapper superseded.
- **Standard:** `dokturek/docs/research/verifiable-ai-standard-2026-07.md` (Clause 1 grounded-record, Clause 2 snapshot+ratchet)
- **Process:** brief-driven → speckit-fast → implement → caveman-review, **no brainstorm, no squash**, per-phase commits.

## Problem

The SVL.ai LightRAG fork is a strong ingest+storage+retrieval substrate but **does not close any Verifiable-AI gap**. Confirmed against the live deployment (`scripts/scratch/svl-fork-experiment/RESULTS.md`, 2026-07-08):

1. **The LLM is the last writer of every node/edge** — no write-path verification. Grounding exists only on the read side (answer-from-passages). *Clause-1 violation.*
2. **No edition lineage.** Entities merge by exact case-sensitive name across all docs; no `as_of`/edition property anywhere. 57.1% of nodes already span ≥2 docs; `Hypertenze` is one node fed by 17 documents. If two editions of one DP were ingested, the 2004 and 2024 recommendations would collapse into one node with no way to tell them apart. **For a clinical KG this is a patient-safety defect.**
3. **No versioning / snapshot / delta / completeness.** Re-ingest merges into the same store. *Clause-2: none of it.*
4. **No canonicalization.** `Praktický lékář` (18 docs) and `Praktický Lékář` (17 docs) are two separate nodes (case variant).

## Measurement baseline (RESULTS.md, live deployment, 2026-07-08)

| Probe | Result | Consequence for this spec |
|---|---|---|
| `source_id` → chunk resolves | **100%** (162/162 entities, 2126/2126 edges) | A deterministic promotion pass IS viable; no library patch needed. |
| entity surface-form locatable in its chunk | **80.2%** (understated — Czech inflection: "Krevní tlak"→"krevního tlaku") | G1 locate MUST be **diacritic/case/inflection-tolerant**, not exact substring, or ~20% false-quarantine. |
| page/bbox via MinerU sidecar | **NOT AVAILABLE** (corpus ingested as pre-converted markdown; MinerU ran offline) | Anchors are **chunk + char-span only**; page/bbox is **out of scope** here → child brief `guidelines-pdf-reingest-for-anchors`. |
| golden questions | 10/10 cite correct DP | Retrieval is trusted; this spec does not touch the read path. |
| edition conflict | mechanism proven, **not live** (corpus = 47 DPs, single edition each) | G3 model is **built + fixture-tested**; live conflict test → child brief `guidelines-edition-conflict-live-test`. |

## Goals

Make guidelines conform to the Verifiable-AI Standard by inserting an **owned, deterministic promotion pass** between the LightRAG store and any downstream consumer (mkn10). The store becomes a **disposable intermediate build artifact**; the repo (not the LLM) is the last writer of everything emitted.

- **G1 write-path trust** — an extracted node/edge enters the bundle only if its surface form(s) are locatable in the source chunk its `source_id` points to; the found offsets **become** the anchor. Ungrounded → quarantine sidecar with a machine-readable reason. No second LLM judge.
- **G2 provenance** — own a chunk registry (`chunk_id → {doc_id, work_id, edition_date, page?, char_window, text, content_hash}`); the promotion pass joins `source_id → registry` and stamps the anchor. `unknown_source` becomes irrelevant.
- **G3 edition lineage** — every emitted fact stamped `as_of = edition_date`, derived deterministically from a corpus manifest (never mined from text). Editions of a work totally ordered; default view = latest edition; older-only fact = `superseded_by_edition`; same fact-key different value across editions = **conflict flag** (a review artifact, not auto-resolution).
- **G4 versioned emit** — an immutable bundle `nodes.jsonl + edges.jsonl + manifest.json`; manifest = content hash over canonicalized sorted records + corpus list + pipeline pins + counts. Stable ids; a re-emit produces a computed delta; monotone ratchets (quarantine non-increasing, anchor coverage 100%, doc coverage non-decreasing).
- **G5 typing/normalization (in-repo half)** — a small controlled entity-type enum (validated at promotion) + deterministic name canonicalization + a versioned alias table. Prerequisites for G3 conflict-keys and G4 stable ids.
- **G6 boundary** — LightRAG keeps extraction/embeddings/rerank/read-answering; the promotion pass + registry + edition model + bundle are in-repo; vocabulary resolution (`concept_ref`) + semantic conflict adjudication stay with mkn10.

## Key decisions (resolved by the measurement, recorded here)

1. **Substrate = the fork's deployed store** (PG chunks + Neo4j entities/edges), not the in-repo wrapper. Read via `get_all_nodes`/`get_all_edges` + chunk KV + `get_docs_by_status`.
2. **Anchors = chunk + normalized char-span.** Page/bbox deferred (no sidecar on live data).
3. **G1 locate is a normalize-then-tolerant-match** yielding char offsets: (a) case/diacritics/whitespace-normalized substring; (b) on miss, a stemmed/token-overlap match yielding the best span above a threshold; (c) below threshold → quarantine. The emitted claim is honestly labelled **"typed, source-anchored co-occurrence"**, not "verified clinical relation" — the write gate guarantees dereferenceability, not clinical truth. Semantic adjudication is mkn10's faithfulness judge.
4. **Edition metadata is derived from the filename manifest** (`Arteriální hypertenze_2024.md` → `work_id="Arteriální hypertenze"`, `edition_date=2024`), with an explicit override manifest for exceptions. The corpus filenames already encode `(work, edition)`.
5. **The promotion pass is pure functions over files.** A separate (impure) harvest step snapshots the deployed store to files; the promotion pass reads those files. This makes G1–G4 golden-file testable without an LLM or a DB.

## Acceptance criteria

0. *(Done)* Substrate confirmed = fork; measurement premises re-confirmed (RESULTS.md). Documented here.
1. *(Done)* Locatability measured (80.2%, inflection-limited) → G1 uses a tolerant matcher (decision 3); no extraction-prompt change is gated on this run.
2. A promotion pass exists as **pure deterministic functions over snapshot files** (store → bundle); every emitted node/edge carries a source anchor (doc/chunk/char-span); **anchor coverage = 100% by construction**; the read-time fuzzy-recovery hack is not relied upon by the emit path.
3. Ungrounded extractions are **quarantined** to a machine-readable sidecar (reasons: `entity-not-found` / `endpoint-missing` / `chunk-unresolved`), never admitted-with-a-marker, never silently dropped; the quarantine count is a ratchet.
4. Every fact carries `as_of = edition_date` from the corpus manifest; default view = latest edition; a same-key-different-value across editions raises a conflict flag; supersession is derived, not extracted.
5. The emit is an immutable `nodes.jsonl + edges.jsonl + manifest.json` bundle with a content-hash manifest + stable ids; a re-emit produces a computed delta; the ratchets hold. *(mkn10 pinning a bundle version = a mkn10-side task, tracked by the harvest-source brief; out of scope here.)*
6. A small owned entity-type enum is injected/validated; names are canonicalized + alias-tabled; vocabulary resolution (`concept_ref`) is left to mkn10 per the FHIR standard.
7. **Golden-file tests on a tiny two-edition fixture corpus** cover G1–G4 end-to-end **without touching an LLM** (the promotion pass, conflict-keying, and delta are pure).

## Out of scope (→ existing/child briefs)

- **Page/bbox span anchors** — need PDF re-ingest through the deployment's MinerU → `guidelines-pdf-reingest-for-anchors`.
- **Live edition-conflict test** — needs a 2nd edition ingested → `guidelines-edition-conflict-live-test`.
- **mkn10 emit consumption / `concept_ref` resolution / semantic conflict adjudication** — consumer side (mkn10), per the FHIR identity-&-coding standard.
- **Semantic entity resolution** (embedding clustering / LLM dedup) — exact-after-canonicalization + alias table until measured collision/split rates prove otherwise.
- **§5/CORS hygiene nits** (API on :8000 collides with mako's reserved port; `allow_origins=["*"]`) — separate hygiene brief if still present.
- **Query-path changes** — the read path (retrieval/answer) is trusted (probe 4) and untouched here; the parallel `feat/query-contextualization` PR is independent.
