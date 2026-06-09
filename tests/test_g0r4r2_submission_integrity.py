"""G0R4R2 verbatim authoritative baseline resubmission integrity tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_g0r4r2_script_no_unrestricted_staging() -> None:
    src = Path("tools/complete_g0r4r2_submission.py").read_text(encoding="utf-8")
    assert '["git", "add", "-A"]' not in src
    assert "BASELINE_VERBATIM_MAPPINGS" in src
    assert "discover_required_inputs" in src
    assert "incoming_external_reviews/g0r4r2" in src


def test_g0r4r2_verbatim_verification_artifact_schema() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R4R2_AUTHORITATIVE_BASELINE_VERBATIM_VERIFICATION.json")
    if not path.is_file():
        pytest.skip("verbatim verification not generated")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload.get("phase") == "G0R4R2_VERBATIM_AUTHORITATIVE_BASELINE_RESUBMISSION"
    assert len(payload.get("entries") or []) == 7


def test_g0r4r2_attestation_outside_zip() -> None:
    att = Path("codex_g0r4r2_detached_submission_attestation.json")
    zip_path = Path("codex_g0r4r2_verbatim_authoritative_baseline_resubmission.zip")
    if not att.is_file() or not zip_path.is_file():
        pytest.skip("package not built")
    payload = json.loads(att.read_text(encoding="utf-8"))
    assert payload.get("attestation_not_contained_in_zip") is True
    assert payload.get("external_sealed") is False
    assert payload.get("g1_authorized") is False
