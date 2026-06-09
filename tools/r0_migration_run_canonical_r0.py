#!/usr/bin/env python3
"""Blocking canonical R0 run via matrix logging (path-only + prediction cache)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "evidence" / "r0_migration" / "canonical_r0_run.json"


def run_canonical_r0(root: Path) -> dict:
    from aa_runtime_profile import resolve_effective_profile
    from aa_single_instance import is_interactive_session_running
    from tools.r0_migration_sla_enforce import _build_path_only_cmd, canonical_r0_dir
    from tools.run_validation_matrix import _is_pass_complete, _run_logged

    r0_dir = canonical_r0_dir(root)
    if _is_pass_complete(r0_dir):
        return {"verdict": "R0_ALREADY_PASS", "dir": str(r0_dir)}

    prof = resolve_effective_profile(
        __import__("os").environ.get("AA_RUNTIME_PROFILE", "turbo"),
        interactive_active=is_interactive_session_running(root),
    )
    cmd = _build_path_only_cmd(root, r0_dir)
    log_path = r0_dir / "validation_run_path_turbo.log"
    rc = _run_logged(cmd, log_path, prof)
    out = {
        "verdict": "R0_PASS" if _is_pass_complete(r0_dir) else "R0_FAIL",
        "returncode": rc,
        "log": str(log_path),
        "dir": str(r0_dir),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> int:
    result = run_canonical_r0(ROOT)
    print(json.dumps(result, indent=2))
    return 0 if result.get("verdict") in ("R0_PASS", "R0_ALREADY_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
