"""Entity casing/whitespace dedup planner (spec 013).

The entity name is the primary key of a graph node across every store (Neo4j id, PGVector id, PGKV), and
extraction never casefolds, so one concept splits across casing/whitespace/diacritic variants
(`eGFR`/`EGFR`/`Egfr`; `Praktický lékař`/`Praktický Lékář`). This module is the PURE planner: it clusters a
list of live-graph nodes by the SAME canonicalizer promotion uses (`merge_key`), picks a deterministic
survivor per cluster, and reconciles the cluster's `concept_ref`. The (impure) runner feeds it a `NodeView`
list and executes each `Merge` via ``rag.amerge_entities(sources, survivor, target_entity_data={...})``.

Reconciliation only inspects MKN-10 codes (drug refs are `c_…` concept-ids — no dot/family semantics). Two
codes are compatible when they are the same after DOT-NORMALIZATION (`N48.4`≡`N484`) or one is the
category-rollup of the other in the same 3-char family (`N18`⊃`N18.9`); the survivor keeps the most-specific.
Only genuinely-different families are a conflict → excluded from the merge plan, never auto-picked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from lightrag.promotion.canonicalize import merge_key


@dataclass
class NodeView:
    """A live-graph entity, as the runner projects it (name = the storage key)."""

    name: str
    concept_ref: list[dict] | None = None  # list of {code, system, display, ...}
    degree: int = 0


@dataclass
class Merge:
    survivor: str
    sources: list[str]  # names to merge into survivor (distinct, != survivor)
    ref: list[dict] | None  # reconciled concept_ref to stamp on the survivor (via target_entity_data)


@dataclass
class Conflict:
    key: str
    names: list[str]
    codes: list[str]  # dot-normalized distinct codes that disagree across families


@dataclass
class DedupPlan:
    merges: list[Merge] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def collapsible(self) -> int:
        return sum(len(m.sources) for m in self.merges)


def _dotnorm(code: str) -> str:
    return (code or "").replace(".", "").upper()


def _is_drug(ref: dict) -> bool:
    """A drug ref = an mkn10 `c_…` concept-id (ATC system) — opaque, no dot/family semantics."""
    code = ref.get("code") or ""
    return code.startswith("c_") or "atc" in (ref.get("system") or "").lower()


def _mkn_refs(refs: list[dict] | None) -> list[dict]:
    """MKN-10 refs only (with a code) — skip drug `c_…` refs."""
    return [r for r in (refs or []) if r.get("code") and not _is_drug(r)]


def _pick_most_specific(refs: list[dict]) -> dict:
    """Among same-family refs, the most-specific spelling: longest dot-normalized code, code as tie-break."""
    return max(refs, key=lambda r: (len(_dotnorm(r.get("code", ""))), r.get("code", "")))


def _reconcile(cluster: list[NodeView]) -> tuple[list[dict] | None, list[str] | None]:
    """Return (chosen_ref | None, conflict_codes | None). Conflict ⇒ chosen_ref is None, cluster skipped.

    Conflict when the casing-twins disagree on identity: MKN codes span >1 3-char family, OR >1 distinct
    drug concept-id, OR a mix of disease (MKN) and drug on the same name. Otherwise pick the survivor's ref:
    the most-specific MKN code (`N18.9` over `N18`), else the sole drug ref.
    """
    refs = [r for n in cluster for r in (n.concept_ref or []) if r.get("code")]
    if not refs:
        return None, None
    mkn = [r for r in refs if not _is_drug(r)]
    drug_ids = {r["code"] for r in refs if _is_drug(r)}
    mkn_families = {_dotnorm(r["code"])[:3] for r in mkn}
    if len(mkn_families) > 1 or len(drug_ids) > 1 or (mkn and drug_ids):
        codes = {_dotnorm(r["code"]) for r in mkn} | drug_ids
        return None, sorted(codes)
    if mkn:
        return [_pick_most_specific(mkn)], None
    # sole drug id — return one representative drug ref
    return [next(r for r in refs if _is_drug(r))], None


def _specificity(node: NodeView) -> int:
    """Length of the node's most-specific dot-normalized MKN-10 code (0 if none) — N18.9→4 beats N18→3."""
    return max((len(_dotnorm(r.get("code", ""))) for r in _mkn_refs(node.concept_ref)), default=0)


def _survivor(cluster: list[NodeView]) -> str:
    """Survivor must stay GROUNDED whenever any node is (else amerge_entities, which does not carry
    concept_ref, would drop the code). Among the grounded pool pick the most-specific code, then highest
    degree, then lexicographically-first; if nothing is grounded, highest degree then lexmin.
    """
    grounded = [n for n in cluster if n.concept_ref]
    pool = grounded if grounded else cluster
    return sorted(pool, key=lambda n: (-_specificity(n), -n.degree, n.name))[0].name


def plan_dedup(nodes: list[NodeView]) -> DedupPlan:
    """Cluster nodes by `merge_key`; per multi-name cluster emit a Merge (or a Conflict)."""
    by_key: dict[str, list[NodeView]] = defaultdict(list)
    for n in nodes:
        if n.name:
            by_key[merge_key(n.name)].append(n)

    plan = DedupPlan()
    for key, cluster in by_key.items():
        names = {n.name for n in cluster}
        if len(names) <= 1:
            continue  # a single distinct surface form → nothing to collapse
        ref, conflict = _reconcile(cluster)
        if conflict is not None:
            plan.conflicts.append(Conflict(key=key, names=sorted(names), codes=conflict))
            continue
        survivor = _survivor(cluster)
        sources = sorted(name for name in names if name != survivor)
        plan.merges.append(Merge(survivor=survivor, sources=sources, ref=ref))
    return plan
