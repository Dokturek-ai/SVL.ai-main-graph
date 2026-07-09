"""Verifiable-ingest promotion pass (spec 001).

Turns the LightRAG store (a disposable build artifact) into an owned,
deterministic, source-anchored, edition-aware bundle for the mkn10 consumer.
The repo — not the LLM — is the last writer of everything emitted.

Layers:
- ``harvest``    impure: deployed store -> snapshot files (the only DB-touching module)
- everything else PURE: snapshot files -> bundle files (golden-file testable, no DB/LLM)
"""
