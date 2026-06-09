#!/usr/bin/env python3
"""Read-only diagnosis of V5R matrix remediation failure (no re-runs)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_safe_io import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
STAMP = "20260531T175100Z"
REMEDIATION_DIR = ROOT / "validation_runs" / f"v5r_matrix_remediation_{STAMP}"
REPORT = doc_path("CODEX_MATRIX_REMEDIATION_DIAGNOSIS.md")
INCIDENT_DIR = ROOT / "control" / "incidents"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_terminal_summary() -> Dict[str, Any]:
    terminals = Path(r"C:\Users\monst\.cursor\projects\e-active-alpha-model\terminals")
    summary = {"source": "terminal_log", "exit_code": 1, "verdict": "FAIL"}
    log = terminals / "911119.txt"
    if log.is_file():
        text = log.read_text(encoding="utf-8", errors="replace")
        if "INSUFFICIENT_CLASSIFICATION_RISK_CONTROL" in text:
            summary["primary_blocker"] = "INSUFFICIENT_CLASSIFICATION_RISK_CONTROL"
        if "V5R_MATRIX_EVALUATION: FAIL" in text:
            summary["matrix_verdict"] = "FAIL"
    return summary


def diagnose(root: Path | None = None) -> Dict[str, Any]:
    root = Path(root or ROOT)
    blockers: List[Dict[str, Any]] = [
        {
            "blocker_id": "INSUFFICIENT_CLASSIFICATION_RISK_CONTROL",
            "module": "aa_portfolio.py / tools/v5r_matrix_remediation_eval.py",
            "rule": "Unknown sector bucket must respect max_sector cap (0.55)",
            "remediation_status": "CODE_FIX_APPLIED_RE_RUN_NOT_AUTHORIZED",
            "note": "Governance blocks new matrix backtests without separate approval.",
        },
        {
            "blocker_id": "INCOMPLETE_COST_STRESS_MATRIX",
            "module": "cost_stress/",
            "rule": "4 cost scenarios required",
            "remediation_status": "PARTIAL_OR_NOT_PRESENT",
        },
    ]

    output_present = REMEDIATION_DIR.is_dir()
    output_files: List[str] = []
    if output_present:
        output_files = [str(p.relative_to(root)).replace("\\", "/") for p in REMEDIATION_DIR.rglob("*") if p.is_file()][:30]

    incident = {
        "incident_type": "V5R_MATRIX_REMEDIATION_FAIL",
        "severity": "TECHNICAL_EVIDENCE_BLOCKER",
        "detected_at_utc": _utc_now(),
        "stamp": STAMP,
        "remediation_dir": str(REMEDIATION_DIR.relative_to(root)).replace("\\", "/"),
        "output_present_on_disk": output_present,
        "primary_blocker": "INSUFFICIENT_CLASSIFICATION_RISK_CONTROL",
        "blockers": blockers,
        "operative_rerun_authorized": False,
        "production_state_modified": False,
        "recommended_next_step": "Separate technical approval for isolated matrix re-run after G1 governance track",
    }

    report_lines = [
        "# Matrix Remediation Diagnosis (Read-Only)",
        "",
        f"UTC: {_utc_now()}",
        f"Stamp: `{STAMP}`",
        "",
        "## Verdict",
        "",
        "`V5R_MATRIX_EVALUATION: FAIL`",
        "",
        "## Primary blocker",
        "",
        "**INSUFFICIENT_CLASSIFICATION_RISK_CONTROL**",
        "",
        "Unknown-sector weights exceeded `max_sector` cap during matrix evaluation. "
        "A code fix in `aa_portfolio.py` was integrated on branch `remediation/authorization-source-conflict`, "
        "but **no authorized re-run** was executed in this pipeline.",
        "",
        "## Secondary blockers",
        "",
        "- Incomplete cost-stress matrix (4 scenarios)",
        "- Output directory absent or not retained: "
        + ("present" if output_present else "**not found on disk**"),
        "",
        "## Governance",
        "",
        "Matrix remediation is a **separate technical track** from G0/G1. ",
        "Re-runs require explicit approval; operative status remains `BLOCKED_FOR_SAFETY`.",
        "",
        "## Recommended isolated fix path (when authorized)",
        "",
        "1. Verify unknown-sector cap in portfolio diagnostics on a single smoke run",
        "2. Re-run only `20260531T175100Z` cost scenarios missing PASS",
        "3. Regenerate matrix_summary without touching champion/evidence gates",
        "",
        "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
        "",
    ]

    INCIDENT_DIR.mkdir(parents=True, exist_ok=True)
    inc_path = INCIDENT_DIR / f"matrix_remediation_fail_{STAMP}.json"
    atomic_write_json(inc_path, incident)
    REPORT.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "incident_path": str(inc_path),
        "report": str(REPORT),
        "output_present": output_present,
        "terminal": _read_terminal_summary(),
    }


def main() -> int:
    result = diagnose()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
