"""Config-as-code ingest denylist for out-of-corpus documents (spec 021).

Some PDFs are not SVL doporučené postupy and must never enter the guidelines graph — e.g.
`MANUÁL KÓDŮ PRO VPL`, a mako billing-code manual (see brief `manual-kodu-not-in-dp-corpus`). Deleting
such a doc is not durable: a re-upload re-poisons retrieval (that is how the `_2026` edition returned
after the 2026-07-12 delete). This denylist is checked on the ingest path (`pipeline_enqueue_file`) so a
known out-of-corpus filename is rejected before it becomes chunks/entities.

Patterns are ASCII substrings matched case-insensitively against the upload filename. Pure-ASCII is
deliberate: the discriminating diacritics ("MANUÁL KÓDŮ") are NFC/NFD-ambiguous, but "PRO VPL" is not, so
the match survives either normalization. The key is broader than the `PRO VPL_` DELETE-scrub key on
purpose — a filename guard must catch every edition (`_unknown`, `_2026`, `_<year>`) *and* a yearless
`… PRO VPL.pdf`. Verified unique to MANUÁL KÓDŮ across the live SVL corpus.
"""

from __future__ import annotations

INGEST_DENYLIST: tuple[str, ...] = (
    "PRO VPL",  # MANUÁL KÓDŮ PRO VPL — mako billing-code manual, not an SVL guideline (all editions)
)


def denylisted_reason(filename: str) -> str | None:
    """Return the matched denylist pattern if ``filename`` is out-of-corpus, else ``None``."""
    upper = filename.upper()
    for pattern in INGEST_DENYLIST:
        if pattern.upper() in upper:
            return pattern
    return None
