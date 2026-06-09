#!/usr/bin/env python3
"""Verify G1 observation package structure."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "outgoing_cursor_observation/g1_independent_next_level"

REQUIRED = (
    "cursor_g1_independent_next_level_development_package.zip",
    "cursor_g1_independent_next_level_development_package.zip.sha256",
    "CURSOR_G1_NEXT_LEVEL_EXECUTION_REPORT.md",
    "CURSOR_G1_NEXT_LEVEL_HASH_MANIFEST.json",
    "CURSOR_G1_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
)


def verify() -> dict:
    missing = [name for name in REQUIRED if not (OBS / name).is_file()]
    return {"ok": not missing, "missing": missing, "observation_dir": str(OBS)}


def main() -> int:
    result = verify()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
