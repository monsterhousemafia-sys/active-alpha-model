"""G0R4R3 final blob-zip verbatim submission integrity tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_g0r4r3_script_no_unrestricted_staging() -> None:
    src = Path("tools/complete_g0r4r3_submission.py").read_text(encoding="utf-8")
    assert '["git", "add", "-A"]' not in src
    assert "verify_final_git_blob_gate" in src
    assert "verify_final_zip_entry_verbatim_gate" in src
    assert "EXPECTED_VERBATIM_INPUTS_NAME" in src
    assert "incoming_external_reviews/g0r4r3/extracted" in src
    assert "GIT_BYTE_PRESERVE_PATHS" in src


def test_g0r4r3_expected_verbatim_inputs_no_false_zip_pass() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R4R3_EXPECTED_VERBATIM_INPUTS.json")
    if not path.is_file():
        pytest.skip("expected verbatim inputs not generated")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("final_zip_verification") == "DEFERRED"
    assert payload.get("final_zip_verification_deferred_to_detached_post_build_report") is True
    assert payload.get("target_to_zip_byte_identical") is None


def test_g0r4r3_attestation_outside_zip() -> None:
    att = Path("codex_g0r4r3_detached_submission_attestation.json")
    zip_path = Path("codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip")
    if not att.is_file() or not zip_path.is_file():
        pytest.skip("package not built")
    payload = json.loads(att.read_text(encoding="utf-8"))
    assert payload.get("attestation_not_contained_in_zip") is True
    assert payload.get("phase") == "G0R4R3_FINAL_BLOB_ZIP_VERBATIM_AND_AUDIT_INPUT_COMPLETENESS_REMEDIATION"
    assert payload.get("external_sealed") is False
    assert payload.get("g1_authorized") is False
    assert payload.get("internal_false_zip_pass_claims_absent") is True
