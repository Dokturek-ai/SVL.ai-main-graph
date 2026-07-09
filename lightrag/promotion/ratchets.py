"""G4 — monotone ratchets: a regression across emits is a hard signal.

anchor coverage must stay 100%; quarantine count and orphan rate must not
increase; doc coverage must not decrease. Returns a list of violation strings
(empty = the ratchets hold).
"""

from __future__ import annotations

from .types import Manifest


def check(prev: Manifest, curr: Manifest) -> list[str]:
    p, c = prev.counts, curr.counts
    violations: list[str] = []
    if c.get("anchor_coverage") != 1.0:
        violations.append(f"anchor_coverage {c.get('anchor_coverage')} != 1.0")
    if c.get("quarantined", 0) > p.get("quarantined", 0):
        violations.append(f"quarantined rose {p.get('quarantined')} -> {c.get('quarantined')}")
    if c.get("orphan_rate", 0.0) > p.get("orphan_rate", 0.0):
        violations.append(f"orphan_rate rose {p.get('orphan_rate')} -> {c.get('orphan_rate')}")
    if c.get("doc_coverage", 0.0) < p.get("doc_coverage", 0.0):
        violations.append(f"doc_coverage fell {p.get('doc_coverage')} -> {c.get('doc_coverage')}")
    return violations
