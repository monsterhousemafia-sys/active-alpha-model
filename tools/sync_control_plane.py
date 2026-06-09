#!/usr/bin/env python3
"""Sync control plane state (health, last-known-good, next cursor prompt)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_control_plane import sync_control_plane, write_next_cursor_prompt  # noqa: E402
from aa_ops_refresh import resolve_out_dir  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Sync Active Alpha control plane")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out-dir", type=Path, default="")
    args = p.parse_args()
    root = Path(args.root)
    import os

    out_dir = Path(args.out_dir) if args.out_dir else resolve_out_dir(root, os.environ)
    health, pipeline = sync_control_plane(root, out_dir)
    write_next_cursor_prompt(root, pipeline)
    print(f"pipeline={health.get('pipeline_status')} analytical={health.get('analytical_validity')}")
    ok = str(health.get("analytical_validity", "")).upper() == "PASS" and str(
        health.get("pipeline_status", "")
    ).upper() != "FAILSAFE_MODE"
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
