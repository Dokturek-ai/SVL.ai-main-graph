"""Deterministic hashing helpers (stable ids + content hashes)."""

from __future__ import annotations

import hashlib


def sha1_hex(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")  # separator so ("ab","c") != ("a","bc")
    return h.hexdigest()
