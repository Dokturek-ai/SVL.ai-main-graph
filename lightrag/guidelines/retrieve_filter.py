"""Retrieve v2 focus filters (spec 014) — PURE, no I/O.

Two levers the agent's `:retrieve` contract needs applied (v1 echoed them, unused):
- **concept_ref → chunks**: an MKN-10 code identifies a diagnosis; the entities grounded to it (or its
  code family) carry the `source_id` chunks of that dg. `build_code_index` + `chunks_for_code` turn a code
  into the set of in-scope chunk ids so the caller can post-filter retrieval to that subset.
- **facet**: derive the section focus from the passage's section-heading path (no G2 tagging pass yet).

Codes are matched DOT-NORMALIZED with a bidirectional 3-char-family prefix, so `I10` pulls `I10.9` and
`E11.9` pulls its `E11` category, but `I10` never matches `I11`.
"""

from __future__ import annotations

from typing import Iterable

GRAPH_SEP = "<SEP>"

# facet enum, checked in this precedence (first keyword hit wins)
_FACET_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("contraindication", ("kontraindik",)),
    ("dosing", ("dávkov", "davkov", "dávka", "davka", "dose", "dosing")),
    ("followup", ("sledován", "sledovan", "dispenzar", "kontrol", "monitor", "follow")),
    ("diagnosis", ("diagnos", "diagnóz", "diagnoz", "kritéri", "kriteri", "vyšetřen", "vysetren")),
    ("treatment", ("léčb", "lécb", "lecb", "terap", "farmakoterap", "management", "léčiv", "leciv")),
]


def dotnorm(code: str) -> str:
    return (code or "").replace(".", "").upper()


def _is_drug(ref: dict) -> bool:
    code = ref.get("code") or ""
    return code.startswith("c_") or "atc" in (ref.get("system") or "").lower()


def code_matches(entity_code: str, request_code: str) -> bool:
    """Same code family — dot-normalized bidirectional prefix. `I10`↔`I10.9`, `E11.9`↔`E11`; `I10`≠`I11`."""
    a, b = dotnorm(entity_code), dotnorm(request_code)
    if len(a) < 3 or len(b) < 3:
        return bool(a) and a == b
    return a.startswith(b) or b.startswith(a)


def build_code_index(entities: Iterable[tuple]) -> dict[str, set[str]]:
    """entities: iterable of ``(concept_ref_list | None, source_id_str | None)``.

    Returns ``dot-normalized MKN-10 code -> {chunk_id}`` (drug `c_…` refs skipped)."""
    index: dict[str, set[str]] = {}
    for refs, source_id in entities:
        chunks = {c for c in (source_id or "").replace(GRAPH_SEP, "\n").split("\n") if c.strip()}
        if not chunks:
            continue
        for r in refs or []:
            if _is_drug(r):
                continue
            code = dotnorm(r.get("code") or "")
            if len(code) < 3:
                continue
            index.setdefault(code, set()).update(chunks)
    return index


def chunks_for_code(index: dict[str, set[str]], request_code: str) -> set[str]:
    """Union of every indexed code's chunks whose code is in the requested code's family."""
    out: set[str] = set()
    if not request_code:
        return out
    for code, chunks in index.items():
        if code_matches(code, request_code):
            out |= chunks
    return out


def classify_facet(section_heading: str | None) -> str | None:
    """Map a section-heading path to the facet enum via a CZ keyword table; None if no keyword hits."""
    if not section_heading:
        return None
    h = section_heading.lower()
    for facet, keys in _FACET_RULES:
        if any(k in h for k in keys):
            return facet
    return None


def facet_matches(passage_facet: str | None, request_facet: str | None) -> bool:
    """No requested facet → everything matches; else exact enum match."""
    if not request_facet:
        return True
    return passage_facet == request_facet
