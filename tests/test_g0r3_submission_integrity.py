"""G0R3 commit-bound package and manifest integrity tests."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from aa_decision_cockpit_readonly_snapshot import (
    G0R3_SNAPSHOT_REL,
    build_g0r3_review_snapshot,
)
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tests.cockpit_governance_fixtures import build_clean_terminal_root


def test_g0r3_script_forbids_unrestricted_git_add() -> None:
    source = Path("tools/complete_g0r3_submission.py").read_text(encoding="utf-8")
    assert '["git", "add", "-A"]' not in source
    assert 'git", "add", "."' not in source
    assert 'git", "commit", "-a"' not in source
    assert "AUTHORIZED_G0R3_COMMIT_PATHS" in source


def test_g0r3_script_has_allowlist_staging() -> None:
    source = Path("tools/complete_g0r3_submission.py").read_text(encoding="utf-8")
    assert "stage_allowlist_only" in source
    assert "verify_allowlist_drift" in source
    assert "UNEXPECTED_NON_ALLOWLIST_WORKTREE_DRIFT" in source


def test_g0r3_script_builds_zip_from_committed_bytes() -> None:
    source = Path("tools/complete_g0r3_submission.py").read_text(encoding="utf-8")
    assert "build_g0r3_zip_from_commit" in source
    assert "read_committed_bytes" in source


def test_g0r3_no_second_commit_after_zip_inputs() -> None:
    source = Path("tools/complete_g0r3_submission.py").read_text(encoding="utf-8")
    assert source.count('"git",\n            "commit"') + source.count('"git", "commit"') == 1
    assert "commit --amend" not in source


def test_g0r3_change_manifest_not_no_mutations_claim() -> None:
    path = Path("G0R3-CHANGE_MANIFEST.json")
    if not path.is_file():
        pytest.skip("G0R3 change manifest not generated yet")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("change_scope") == "PACKAGING_CHECKPOINT_AND_EVIDENCE_MANIFEST_ONLY"
    assert payload.get("protected_artefacts_modified_during_g0r3") is False
    note = json.dumps(payload)
    assert "no file mutations" not in note.lower()


def test_g0r3_v5r_snapshot_in_zip_scope() -> None:
    source = Path("tools/complete_g0r3_submission.py").read_text(encoding="utf-8")
    assert "control/review_snapshot/v5r_decision_cockpit_snapshot.json" in source


def test_g0r3_package_manifest_structure() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json")
    if not path.is_file():
        pytest.skip("G0R3 package manifest not generated yet")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("packaging_method") == "git_show_committed_bytes"
    entries = payload.get("entries") or []
    assert entries
    for entry in entries:
        assert "zip_path" in entry
        assert "sha256_of_included_bytes" in entry
        assert "git_commit" in entry


def test_g0r3_protected_baseline_unchanged() -> None:
    from aa_doc_paths import doc_path

    comp_path = doc_path("CODEX_G0R3_V5R_BASELINE_COMPARISON.json")
    if not comp_path.is_file():
        pytest.skip("G0R3 comparison not generated yet")
    v5r = json.loads(doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json").read_text(encoding="utf-8"))
    comparison = json.loads(comp_path.read_text(encoding="utf-8"))
    assert comparison.get("previous_pre_g0r_drift_detected") is True
    for rel in (
        "model_output_sp500_pit_t212/latest_validated_run.json",
        "model_output_sp500_pit_t212/background_research_status.json",
    ):
        row = next(e for e in comparison["entries"] if e["path"] == rel)
        assert row["match"] is True
        assert row["current_repository_sha256"] == v5r[rel]


def test_g0r3_report_no_zero_drift_claim() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md")
    if not path.is_file():
        pytest.skip("G0R3 report not generated yet")
    report = path.read_text(encoding="utf-8")
    for line in report.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Drift before remediation:"):
            assert stripped != "- Drift before remediation: 0"
    assert "PREVIOUS_PRE_G0R_DRIFT_DETECTED: YES" in report
    assert "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL" in report


def test_g0r3_phase_catalog_present() -> None:
    catalog = json.loads(
        (Path("control") / "vision_automation" / "phase_catalog.json").read_text(encoding="utf-8")
    )
    ids = [p.get("phase_id") for p in catalog.get("phases") or []]
    assert "G0R3_FINAL_COMMIT_BOUND_PACKAGE_AND_MANIFEST_REMEDIATION" in ids


def test_g0r3_registry_not_sealed() -> None:
    registry = json.loads(
        (Path("control") / "vision_automation" / "review_registry" / "review_registry.json").read_text(
            encoding="utf-8"
        )
    )
    g0r3 = next(r for r in registry["reviews"] if r["phase_id"].startswith("G0R3_"))
    assert g0r3.get("external_sealed") is False
    assert g0r3.get("review_zip_sha256") == "PENDING_EXTERNAL_SEAL"
    assert g0r3.get("g1_authorized") is False


def test_g0r3_snapshot_fail_closed(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    snap = build_g0r3_review_snapshot(root)
    overview = snap["cockpit_data"]["executive_overview"]
    assert overview["active_champion"] == AUTHORITATIVE_CHAMPION
    for key in ("promotion_eligible_display", "paper_eligible_display", "real_money_eligible_display"):
        assert overview[key] == "NO"
    assert snap["review_zip_sha256"] == "PENDING_EXTERNAL_SEAL"
    assert snap["g1_authorized"] is False


def test_g0r3_zip_contains_v5r_snapshot() -> None:
    zip_path = Path("codex_g0r3_final_commit_bound_package_review.zip")
    if not zip_path.is_file():
        pytest.skip("G0R3 review ZIP not built yet")
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "control/review_snapshot/v5r_decision_cockpit_snapshot.json" in names
        for required in (
            "model_output_sp500_pit_t212/latest_validated_run.json",
            "model_output_sp500_pit_t212/background_research_status.json",
            "DEVELOPMENT_PIPELINE.json",
            "DEVELOPMENT_PIPELINE.yaml",
        ):
            assert required in names


def test_g0r3_git_status_shows_head_changed() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R3_GIT_STATUS.txt")
    if not path.is_file():
        pytest.skip("G0R3 git status not written yet")
    text = path.read_text(encoding="utf-8")
    if "__G0R3_FINAL_INPUT_COMMIT__" in text:
        pytest.skip("G0R3 commit not completed yet")
    start = text.split("g0r3_start_head=")[1].splitlines()[0].strip()
    final = text.split("g0r3_final_input_commit=")[1].splitlines()[0].strip()
    assert start != final
    assert re.fullmatch(r"[0-9a-f]{40}", final)


def test_g0r3_zip_internal_pending_seal() -> None:
    zip_path = Path("codex_g0r3_final_commit_bound_package_review.zip")
    if not zip_path.is_file():
        pytest.skip("G0R3 review ZIP not built yet")
    report_name = "docs/phases/G0R3/CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md"
    with zipfile.ZipFile(zip_path) as zf:
        assert report_name in zf.namelist()
        report = zf.read(report_name).decode("utf-8")
        assert "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL" in report


def test_g0r3_snapshot_path() -> None:
    assert G0R3_SNAPSHOT_REL.as_posix() == "control/review_snapshot/g0r3_decision_cockpit_snapshot.json"
