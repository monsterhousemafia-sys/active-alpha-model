"""Seal-readiness gate tests for G0R4R3 submission."""
from __future__ import annotations

from tools.g0r4r3_seal_readiness import BASELINE_EXPECTED, REQUIRED_AUDIT_ZIP_PATHS


def test_baseline_crlf_hashes_defined() -> None:
    assert len(BASELINE_EXPECTED) == 3
    assert all(len(h) == 64 for h in BASELINE_EXPECTED.values())


def test_mandatory_audit_zip_paths_count() -> None:
    assert len(REQUIRED_AUDIT_ZIP_PATHS) == 6
    assert any("g0r4r2_approval" in p for p in REQUIRED_AUDIT_ZIP_PATHS)
    assert any("g0r4r2_rejection" in p for p in REQUIRED_AUDIT_ZIP_PATHS)
    assert any("g0r4r3_approval" in p for p in REQUIRED_AUDIT_ZIP_PATHS)
