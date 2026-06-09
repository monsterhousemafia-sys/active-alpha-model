"""Phase A truth inventory — smoke tests."""
from __future__ import annotations

import json
from pathlib import Path

from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tools.run_champion_evidence_phase_a import run_phase_a


def test_phase_a_generates_evidence_artifacts(tmp_path: Path) -> None:
    # Minimal tree: locked champion constant only; empty dirs OK for scan roots
    (tmp_path / "control" / "authorization").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    auth = {
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "status": "CONFLICT_BLOCKED_FOR_SAFETY",
        "conflict_details": [],
    }
    (tmp_path / "control" / "authorization" / "current_authorization_status.json").write_text(
        json.dumps(auth), encoding="utf-8"
    )
    summary = run_phase_a(tmp_path)
    assert summary.get("status") == "COMPLETE"
    for key in (
        "champion_pointer_audit.json",
        "variant_run_inventory.json",
        "calendar_mismatch_root_cause.md",
        "governance_baseline.json",
        "phase_a_truth_inventory_summary.json",
    ):
        assert (tmp_path / "evidence" / key).is_file(), key


def test_phase_a_full_repo_run() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = run_phase_a(root)
    assert summary.get("status") == "COMPLETE"
    audit = json.loads((root / "evidence" / "champion_pointer_audit.json").read_text(encoding="utf-8"))
    assert audit.get("locked_champion_code") == AUTHORITATIVE_CHAMPION
    inv = json.loads((root / "evidence" / "variant_run_inventory.json").read_text(encoding="utf-8"))
    r3 = next((v for v in inv.get("variants") or [] if v.get("variant_id") == "R3_w075_q065_noexit"), None)
    assert r3 is not None
    assert r3.get("n_days") is not None
    assert r3.get("run_dir") or r3.get("metrics_embedded")
