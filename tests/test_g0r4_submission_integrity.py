"""G0R4 detached attestation and exact-byte package integrity tests."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from aa_decision_cockpit_readonly_snapshot import G0R4_SNAPSHOT_REL, build_g0r4_review_snapshot
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tests.cockpit_governance_fixtures import build_clean_terminal_root


def test_g0r4_script_no_unrestricted_staging() -> None:
    src = Path("tools/complete_g0r4_submission.py").read_text(encoding="utf-8")
    assert '["git", "add", "-A"]' not in src
    assert "augment_binding" not in src
    assert "COMMIT_PLACEHOLDER" not in src
    assert "build_exact_byte_zip" in src


def test_g0r4_payload_manifest_self_exclusion() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R4_COMMITTED_PAYLOAD_MANIFEST.json")
    if not path.is_file():
        pytest.skip("manifest not generated")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("self_hash_included") is False
    assert payload.get("zip_hash_included") is False
    assert payload.get("git_commit_included") is False
    self_path = payload.get("self_path")
    listed = {e["zip_path"] for e in payload.get("payload_entries") or []}
    assert self_path not in listed


def test_g0r4_git_status_no_embedded_commit() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R4_GIT_STATUS.txt")
    if not path.is_file():
        pytest.skip("git status not generated")
    text = path.read_text(encoding="utf-8")
    assert "SEE_DETACHED_SUBMISSION_ATTESTATION" in text
    assert "pending_commit" not in text


def test_g0r4_snapshot_fail_closed(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    snap = build_g0r4_review_snapshot(root)
    overview = snap["cockpit_data"]["executive_overview"]
    assert overview["active_champion"] == AUTHORITATIVE_CHAMPION
    for key in ("promotion_eligible_display", "paper_eligible_display", "real_money_eligible_display"):
        assert overview[key] == "NO"


def test_g0r4_attestation_outside_zip() -> None:
    att = Path("codex_g0r4_detached_submission_attestation.json")
    zip_path = Path("codex_g0r4_detached_attestation_exact_byte_package_review.zip")
    if not att.is_file() or not zip_path.is_file():
        pytest.skip("package not built")
    with zipfile.ZipFile(zip_path) as zf:
        assert "codex_g0r4_detached_submission_attestation.json" not in zf.namelist()
    payload = json.loads(att.read_text(encoding="utf-8"))
    assert payload.get("attestation_not_contained_in_zip") is True
    assert payload.get("external_sealed") is False
    assert payload.get("g1_authorized") is False


def test_g0r4_zip_exact_byte_manifest_match() -> None:
    att = Path("codex_g0r4_detached_submission_attestation.json")
    zip_path = Path("codex_g0r4_detached_attestation_exact_byte_package_review.zip")
    if not att.is_file() or not zip_path.is_file():
        pytest.skip("package not built")
    att_data = json.loads(att.read_text(encoding="utf-8"))
    commit = att_data["final_input_commit"]
    manifest_path = "docs/phases/G0R4/CODEX_G0R4_COMMITTED_PAYLOAD_MANIFEST.json"
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read(manifest_path).decode("utf-8"))
        for entry in manifest["payload_entries"]:
            path = entry["zip_path"]
            zip_hash = __import__("hashlib").sha256(zf.read(path)).hexdigest()
            assert zip_hash == entry["sha256_of_committed_bytes"]
            proc = __import__("subprocess").run(
                ["git", "cat-file", "-p", f"{commit}:{path}"],
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0:
                commit_hash = __import__("hashlib").sha256(proc.stdout).hexdigest()
                assert commit_hash == zip_hash


def test_g0r4_v5r_snapshot_in_zip() -> None:
    zip_path = Path("codex_g0r4_detached_attestation_exact_byte_package_review.zip")
    if not zip_path.is_file():
        pytest.skip("zip not built")
    with zipfile.ZipFile(zip_path) as zf:
        assert "control/review_snapshot/v5r_decision_cockpit_snapshot.json" in zf.namelist()


def test_g0r4_manifest_excludes_zip_and_seal_claims() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R4_COMMITTED_PAYLOAD_MANIFEST.json")
    if not path.is_file():
        pytest.skip("manifest not generated")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("external_sealed") is False
    assert payload.get("zip_hash_included") is False
    assert payload.get("sidecar") not in payload


def test_g0r4_protected_artefacts_v5r_in_zip() -> None:
    zip_path = Path("codex_g0r4_detached_attestation_exact_byte_package_review.zip")
    if not zip_path.is_file():
        pytest.skip("zip not built")
    v5r = json.loads(
        Path("docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json").read_text(
            encoding="utf-8"
        )
    )
    with zipfile.ZipFile(zip_path) as zf:
        for rel, expected in v5r.items():
            assert rel in zf.namelist()
            actual = __import__("hashlib").sha256(zf.read(rel)).hexdigest()
            assert actual == expected


def test_g0r4_review_registry_detached_binding() -> None:
    registry = json.loads(
        (Path("control") / "vision_automation" / "review_registry" / "review_registry.json").read_text(
            encoding="utf-8"
        )
    )
    entry = next(
        r
        for r in registry.get("reviews") or []
        if r.get("phase_id") == "G0R4_DETACHED_ATTESTATION_AND_EXACT_BYTE_PACKAGE_BINDING_REMEDIATION"
    )
    assert entry.get("review_zip_sha256") == "DETACHED_ATTESTATION_ONLY"
    assert entry.get("external_sealed") is False
    assert entry.get("g1_authorized") is False


def test_g0r4_baseline_comparison_documents_prior_drift() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R4_V5R_BASELINE_COMPARISON.json")
    if not path.is_file():
        pytest.skip("comparison not generated")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("previous_pre_g0r_drift_detected") is True
    drifted = set(payload.get("previously_drifted_paths") or [])
    assert "model_output_sp500_pit_t212/background_research_status.json" in drifted
    assert "model_output_sp500_pit_t212/latest_validated_run.json" in drifted


def test_g0r4_phase_catalog() -> None:
    catalog = json.loads(
        (Path("control") / "vision_automation" / "phase_catalog.json").read_text(encoding="utf-8")
    )
    phase_id = "G0R4_DETACHED_ATTESTATION_AND_EXACT_BYTE_PACKAGE_BINDING_REMEDIATION"
    assert phase_id in [p.get("phase_id") for p in catalog.get("phases") or []]
    phase = next(p for p in catalog["phases"] if p.get("phase_id") == phase_id)
    forbidden = phase.get("forbidden_actions") or []
    assert "g1_execution" in forbidden
    assert "backtest_execution" in forbidden
