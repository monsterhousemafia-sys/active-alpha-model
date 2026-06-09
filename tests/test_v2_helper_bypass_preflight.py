"""V2 helper-script bypass preflight tests."""
from __future__ import annotations

from pathlib import Path

from aa_v2_bypass_audit import audit_helper_scripts, _scan_file


def test_helper_scripts_no_completion_bypass():
    root = Path(__file__).resolve().parents[1]
    audit = audit_helper_scripts(root)
    assert audit["ok"] is True, audit.get("findings")


def test_synthetic_helper_bypass_detected(tmp_path: Path):
    bad = tmp_path / "tools" / "complete_bad_run.py"
    bad.parent.mkdir(parents=True)
    bad.write_text(
        "from aa_vision_controller import complete_v1_phase\ncomplete_v1_phase(root)\n",
        encoding="utf-8",
    )
    issues = _scan_file(bad)
    assert issues


def test_v1r3_seal_hash_constant():
    from aa_vision_controller import V1R3_REVIEW_ZIP

    assert V1R3_REVIEW_ZIP == "codex_v1r3_authorized_completion_review.zip"
