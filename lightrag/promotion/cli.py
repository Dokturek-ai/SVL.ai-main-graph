"""``python -m promotion promote|delta`` — the pure emit + review glue.

``harvest`` is impure (needs a live LightRAG) and is driven by the smoke script,
not this CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import jsonl
from .bundle import build_manifest, write_bundle
from .delta import diff_dicts
from .promote import promote


def _read_snapshot(d: Path) -> dict[str, list[dict]]:
    return {name: jsonl.read_jsonl(d / f"{name}.jsonl") for name in ("docs", "chunks", "nodes", "edges")}


def _cmd_promote(args: argparse.Namespace) -> int:
    snapshot = _read_snapshot(Path(args.snapshot_dir))
    bundle = promote(snapshot)
    manifest = build_manifest(bundle, snapshot)
    write_bundle(bundle, manifest, args.out_dir)
    print(f"bundle -> {args.out_dir}  hash={manifest.content_hash[:12]}  counts={manifest.counts}")
    return 0


def _cmd_delta(args: argparse.Namespace) -> int:
    a, b = Path(args.prev_dir), Path(args.curr_dir)
    d = diff_dicts(
        jsonl.read_jsonl(a / "nodes.jsonl"),
        jsonl.read_jsonl(b / "nodes.jsonl"),
        jsonl.read_jsonl(a / "edges.jsonl"),
        jsonl.read_jsonl(b / "edges.jsonl"),
    )
    print(json.dumps(d, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="promotion")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("promote", help="snapshot dir -> bundle dir")
    p.add_argument("snapshot_dir")
    p.add_argument("out_dir")
    p.set_defaults(func=_cmd_promote)

    d = sub.add_parser("delta", help="diff two bundle dirs by stable id")
    d.add_argument("prev_dir")
    d.add_argument("curr_dir")
    d.set_defaults(func=_cmd_delta)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
