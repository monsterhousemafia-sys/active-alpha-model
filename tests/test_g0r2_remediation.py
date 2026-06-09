"""G0R2 clean checkpoint and evidence completeness tests."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aa_decision_cockpit_readonly_snapshot import G0R2_SNAPSHOT_REL, build_g0r2_review_snapshot
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tests.cockpit_governance_fixtures import build_clean_terminal_root


def test_g0r2_comparison_records_pre_g0r_drift() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R2_V5R_BASELINE_COMPARISON.json")
    if not path.is_file():
        pytest.skip("G0R2 comparison not generated yet")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("previous_g0r_pre_remediation_drift_detected") is True
    drifted = [e for e in payload["entries"] if e.get("pre_g0r_drift_detected")]
    paths = {e["path"] for e in drifted}
    assert "model_output_sp500_pit_t212/latest_validated_run.json" in paths
    assert "model_output_sp500_pit_t212/background_research_status.json" in paths


def test_g0r2_restored_pointers_match_v5r_baseline() -> None:
    from aa_doc_paths import doc_path

    comp_path = doc_path("CODEX_G0R2_V5R_BASELINE_COMPARISON.json")
    if not comp_path.is_file():
        pytest.skip("G0R2 comparison not generated yet")
    v5r = json.loads(doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json").read_text(encoding="utf-8"))
    comparison = json.loads(comp_path.read_text(encoding="utf-8"))
    for rel in (
        "model_output_sp500_pit_t212/latest_validated_run.json",
        "model_output_sp500_pit_t212/background_research_status.json",
    ):
        row = next(e for e in comparison["entries"] if e["path"] == rel)
        assert row["match"] is True
        assert row["current_repository_sha256"] == v5r[rel]
        assert row["classification"] in {"RESTORED_TO_V5R_BASELINE", "UNCHANGED"}


def test_g0r2_report_does_not_claim_zero_pre_drift() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R2_EXTERNAL_REJECTION_REMEDIATION_REPORT.md")
    if not path.is_file():
        pytest.skip("G0R2 report not generated yet")
    report = path.read_text(encoding="utf-8")
    # Reject active false claims, not quoted prior-G0R documentation.
    for line in report.splitlines():
        stripped = line.strip()
        if stripped.startswith("- Drift before remediation:"):
            assert stripped != "- Drift before remediation: 0"
        if stripped == "Drift before remediation: 0":
            pytest.fail("Report must not assert zero pre-remediation drift")
    assert "PREVIOUS_G0R_PRE_REMEDIATION_DRIFT_DETECTED: YES" in report


def test_g0r2_phase_catalog_present() -> None:
    catalog = json.loads(
        (Path("control") / "vision_automation" / "phase_catalog.json").read_text(encoding="utf-8")
    )
    ids = [p.get("phase_id") for p in catalog.get("phases") or []]
    assert "G0R2_CLEAN_CHECKPOINT_AND_EVIDENCE_COMPLETENESS_REMEDIATION" in ids


def test_g0r2_registry_not_externally_sealed() -> None:
    registry = json.loads(
        (Path("control") / "vision_automation" / "review_registry" / "review_registry.json").read_text(
            encoding="utf-8"
        )
    )
    g0r2 = next(r for r in registry["reviews"] if r["phase_id"].startswith("G0R2_"))
    assert g0r2.get("external_sealed") is False
    assert g0r2.get("review_zip_sha256") == "PENDING_EXTERNAL_SEAL"
    assert g0r2.get("g1_authorized") is False


def test_g0r2_snapshot_fail_closed(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    snap = build_g0r2_review_snapshot(root)
    overview = snap["cockpit_data"]["executive_overview"]
    assert overview["active_champion"] == AUTHORITATIVE_CHAMPION
    for key in ("promotion_eligible_display", "paper_eligible_display", "real_money_eligible_display"):
        assert overview[key] == "NO"
    assert snap["review_zip_sha256"] == "PENDING_EXTERNAL_SEAL"


def test_g0r2_zip_contains_mandatory_inspectable_files() -> None:
    zip_path = Path("codex_g0r2_clean_checkpoint_evidence_completeness_review.zip")
    if not zip_path.is_file():
        pytest.skip("G0R2 review ZIP not built yet")
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for required in (
            "model_output_sp500_pit_t212/latest_validated_run.json",
            "model_output_sp500_pit_t212/background_research_status.json",
            "DEVELOPMENT_PIPELINE.json",
            "DEVELOPMENT_PIPELINE.yaml",
            "control/evidence/forward_monitoring_data_requirements.json",
            "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
        ):
            assert required in names


def test_g0r2_git_status_shows_head_changed() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R2_GIT_STATUS.txt")
    if not path.is_file():
        pytest.skip("G0R2 git status not written yet")
    text = path.read_text(encoding="utf-8")
    if "head_changed=true" not in text:
        pytest.skip("G0R2 commit not completed yet")
    assert "start_head=" in text
    assert "g0r2_remediation_head=" in text
    start = text.split("start_head=")[1].splitlines()[0].strip()
    rem = text.split("g0r2_remediation_head=")[1].splitlines()[0].strip()
    assert start != rem


def test_g0r2_internal_docs_pending_external_seal() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R2_EXTERNAL_REJECTION_REMEDIATION_REPORT.md")
    if not path.is_file():
        pytest.skip("G0R2 report not generated yet")
    report = path.read_text(encoding="utf-8")
    assert "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL" in report
    assert "2a008e6eadee94d0a6e2b7faa772c8f3f1c35c7bab89e13078174c32bb41c679" not in report.split("Observed hash")[0]


def test_g0r2_snapshot_path() -> None:
    assert G0R2_SNAPSHOT_REL.as_posix() == "control/review_snapshot/g0r2_decision_cockpit_snapshot.json"
