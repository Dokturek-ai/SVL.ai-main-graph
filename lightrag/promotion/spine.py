"""Vendored MKN-10 spine snapshot + deterministic ``concept_ref`` validation (Phase 1, spec 008).

Promotion runs with NO network (the reproducibility rule / Constitution VI). It validates only
that each ``concept_ref``'s MKN-10 code exists in a **pinned** ÚZIS code-set snapshot — a
verify-or-abstain guard: a code not in the pinned spine is dropped, not fetched. The snapshot is
vendored from mkn10 ``GET /v1/codes/spine`` (spec 138 / PR #239):
``{spine_hash, version, count, codes[]}``, ``spine_hash = sha256("\\n".join(sorted(set(codes))))``,
assignable codes only. Non-MKN-10 systems (SNOMED, ATC) pass through unchanged — mkn10 crosswalks
them downstream.

The vendored snapshot FILE is committed with the live probe run (it needs a live mkn10 fetch); this
module ships the loader + validator, tested against a fixture.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from lightrag.grounding import MKN10_SYSTEM


def spine_hash(codes) -> str:
    """``sha256("\\n".join(sorted(set(codes))))`` — mkn10's canonical spine hash (spec 138)."""
    return hashlib.sha256("\n".join(sorted(set(codes))).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Spine:
    """A pinned, verified MKN-10 code set. ``code in spine`` tests membership."""

    version: str
    spine_hash: str
    codes: frozenset

    def __contains__(self, code: object) -> bool:
        return code in self.codes


def load_spine(source: Any) -> Spine:
    """Load + verify a vendored spine snapshot from a path / dict / JSON string.

    Recomputes ``spine_hash`` over ``codes`` and raises if it disagrees with the pinned value
    (a tamper / truncation guard — a silently-altered snapshot is unusable).
    """
    if isinstance(source, dict):
        data = source
    else:
        text = Path(source).read_text() if not _looks_like_json(source) else source
        data = json.loads(text)

    codes = list(data["codes"])
    pinned = data["spine_hash"]
    computed = spine_hash(codes)
    if computed != pinned:
        raise ValueError(
            f"spine_hash mismatch: pinned {pinned[:12]}… != computed {computed[:12]}… "
            "(vendored snapshot altered or truncated)"
        )
    return Spine(
        version=str(data.get("version", "")),
        spine_hash=pinned,
        codes=frozenset(codes),
    )


def _looks_like_json(source: Any) -> bool:
    return isinstance(source, str) and source.lstrip().startswith("{")


def validate_concept_refs(
    refs: Optional[list[dict[str, str]]], spine: Spine
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Drop any ``concept_ref`` whose MKN-10 ``code ∉ spine``. Returns ``(kept, dropped)``.

    Verify-or-abstain, no network. Non-MKN-10 systems (SNOMED, ATC) are kept as-is — the spine is
    the MKN-10 code set only, and mkn10 crosswalks the other systems downstream.
    """
    kept: list[dict[str, str]] = []
    dropped: list[dict[str, str]] = []
    for ref in refs or []:
        if ref.get("system") == MKN10_SYSTEM and ref.get("code") not in spine:
            dropped.append(ref)
        else:
            kept.append(ref)
    return kept, dropped
