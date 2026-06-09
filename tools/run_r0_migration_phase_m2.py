#!/usr/bin/env python3
"""Phase M2 — canonical comparison + aligned go/no-go (requires M1 sealed)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_canonical_comparison import build_canonical_model_comparison, format_canonical_comparison_md
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from aa_safe_io import atomic_write_json, atomic_write_text

ALIGNED_PATH = "evidence/r0_migration/aligned_comparison.json"
R0 = "R0_LEGACY_ENSEMBLE"
R3 = "R3_w075_q065_noexit"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _metric(doc: Dict[str, Any], vid: str) -> Dict[str, Any]:
    for row in doc.get("variants") or []:
        if str(row.get("variant_id")) == vid:
            return row
    return {}


def _go_no_go(doc: Dict[str, Any], *, min_delta: float = 0.02) -> Dict[str, Any]:
    r0 = _metric(doc, R0)
    r3 = _metric(doc, R3)
    r0_s = float(r0.get("sharpe_0rf") or 0)
    r3_s = float(r3.get("sharpe_0rf") or 0)
    r0_dd = float(r0.get("max_drawdown") or 0)
    r3_dd = float(r3.get("max_drawdown") or 0)
    sharpe_ok = r0_s >= r3_s + min_delta
    dd_ok = r0_dd <= r3_dd + 0.02
    if sharpe_ok and dd_ok:
        decision = "GO"
    elif not sharpe_ok and not dd_ok:
        decision = "NO_GO"
    else:
        decision = "CONDITIONAL"
    return {
        "decision": decision,
        "go_no_go": decision,
        "r0_sharpe": r0_s,
        "r3_sharpe": r3_s,
        "sharpe_delta": round(r0_s - r3_s, 4),
        "min_sharpe_delta_required": min_delta,
        "r0_max_drawdown": r0_dd,
        "r3_max_drawdown": r3_dd,
        "max_dd_degradation_allowed": 0.02,
        "dd_ok": dd_ok,
        "sharpe_ok": sharpe_ok,
    }


def run_m2(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase

    if not is_phase_sealed(root, "M1"):
        return {"status": "BLOCKED", "reason": "M1_not_sealed"}

    rc = subprocess.call(
        [str(root / ".venv" / "Scripts" / "python.exe"), str(root / "tools" / "build_canonical_model_comparison.py")],
        cwd=str(root),
    )
    if rc != 0:
        return {"status": "FAILED", "reason": "canonical_build_exit", "returncode": rc}

    doc = build_canonical_model_comparison(root)
    atomic_write_json(root / "evidence" / "canonical_model_comparison.json", doc)
    atomic_write_text(root / "evidence" / "canonical_model_comparison.md", format_canonical_comparison_md(doc))

    go = _go_no_go(doc)
    headline = doc.get("headline") or {}
    aligned = {
        "schema_version": 1,
        "phase": "M2",
        "generated_at_utc": _utc_now(),
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "alignment_mode": doc.get("alignment_mode"),
        "headline": headline,
        "go_no_go": go,
        "governance_blockers": doc.get("governance_blockers") or [],
    }
    atomic_write_json(root / ALIGNED_PATH, aligned)

    try:
        subprocess.call(
            [str(root / ".venv" / "Scripts" / "python.exe"), str(root / "tools" / "build_risk_off_episode_comparison.py")],
            cwd=str(root),
        )
    except Exception:
        pass

    seal = try_seal_phase(root, "M2") if go.get("decision") in ("GO", "CONDITIONAL") else {"status": "SEAL_SKIPPED"}
    return {"status": "COMPLETE", "aligned_comparison": aligned, "seal": seal}


def main() -> int:
    result = run_m2(ROOT)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
