"""G0R4R verbatim external review chain resubmission integrity tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_g0r4r_script_no_unrestricted_staging() -> None:
    src = Path("tools/complete_g0r4r_submission.py").read_text(encoding="utf-8")
    assert '["git", "add", "-A"]' not in src
    assert "COMMIT_PLACEHOLDER" not in src
    assert "ensure_g0r3_rejection_inputs" not in src
    assert "VERBATIM_EXTERNAL_MAPPINGS" in src
    assert "verify_external_remediation_approval" in src
    assert "discover_required_inputs" in src
    assert "incoming_external_reviews/g0r4r" in src


def test_g0r4r_verbatim_verification_artifact_schema() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R4R_EXTERNAL_REVIEW_INPUT_VERBATIM_VERIFICATION.json")
    if not path.is_file():
        pytest.skip("verbatim verification not generated")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("phase") == "G0R4R_VERBATIM_EXTERNAL_REVIEW_CHAIN_RESUBMISSION"
    assert len(payload.get("entries") or []) == 10
    if payload.get("entries"):
        entry = payload["entries"][0]
        assert "byte_identical_source_to_target" in entry
        assert "byte_identical_target_to_zip" in entry
        assert "included_zip_entry_sha256" in entry


def test_g0r4r_attestation_outside_zip() -> None:
    att = Path("codex_g0r4r_detached_submission_attestation.json")
    zip_path = Path("codex_g0r4r_verbatim_external_review_chain_resubmission.zip")
    if not att.is_file() or not zip_path.is_file():
        pytest.skip("package not built")
    payload = json.loads(att.read_text(encoding="utf-8"))
    assert payload.get("attestation_not_contained_in_zip") is True
    assert payload.get("external_sealed") is False
    assert payload.get("g1_authorized") is False
