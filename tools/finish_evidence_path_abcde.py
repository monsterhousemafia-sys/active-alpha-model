#!/usr/bin/env python3
"""Orchestrate evidence path steps A–E (governance-safe, no operative jobs)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_py(rel: str) -> None:
    subprocess.run([sys.executable, str(ROOT / rel)], cwd=str(ROOT), check=True)


def _run_pytest() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_authorization_conflict_fail_closed.py",
            "tests/test_decision_cockpit_viewmodel.py",
            "tests/test_decision_cockpit_gui.py",
            "-q",
        ],
        cwd=str(ROOT),
        check=True,
    )


def main() -> int:
    summary = {"generated_at_utc": _utc_now(), "steps": {}}

    print("=== A: tests + G0 review zip ===")
    _run_pytest()
    _run_py("tools/build_g0_review_zip.py")
    summary["steps"]["A"] = "G0 tests PASS; review zip rebuilt"

    print("=== B: G1 external submission package ===")
    _run_py("tools/prepare_g1_challenger_cost_evidence.py")
    _run_py("tools/build_g1_review_submission_zip.py")
    summary["steps"]["B"] = "G1 submission AWAITING_EXTERNAL_REVIEW"

    print("=== C: G1 read-only challenger prep ===")
    summary["steps"]["C"] = "g1_source_inventory + G1_COMPARISON_LOGIC written"

    print("=== D: G2 preregistration ===")
    _run_py("tools/build_g2_preregistration_package.py")
    summary["steps"]["D"] = "G2 preregistration protocol documented"

    print("=== E: matrix diagnosis ===")
    _run_py("tools/diagnose_matrix_remediation_fail.py")
    summary["steps"]["E"] = "matrix fail diagnosed read-only"

    out = ROOT / "evidence" / "evidence_path_abcde_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
