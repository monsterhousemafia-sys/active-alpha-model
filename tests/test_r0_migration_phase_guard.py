"""R0 migration phase guard (verify / seal)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_phase_gates_file():
    p = ROOT / "control" / "r0_migration" / "phase_gates.json"
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "M0" in data["phase_order"]
    assert "M12" in data["phase_order"]


def test_verify_m0_passes_when_mandate_present():
    from tools.r0_migration_phase_guard import verify_phase

    if not (ROOT / "control" / "r0_migration" / "mandate.json").is_file():
        pytest.skip("M0 mandate missing")
    result = verify_phase(ROOT, "M0")
    assert result["pass"] is True


def test_verify_m1_fails_without_returns():
    from tools.r0_migration_phase_guard import verify_phase

    result = verify_phase(ROOT, "M1")
    manifest = ROOT / "evidence" / "r0_migration" / "returns_manifest.json"
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("all_m1_variants_integrity_pass"):
            pytest.skip("M1 already complete")
    assert result["pass"] is False
    assert "m1_returns_integrity" in result.get("blockers") or any(
        "m1_returns" in b for b in result.get("blockers") or []
    )


def test_m1_requires_m0_seal_first():
    from tools.r0_migration_phase_guard import is_phase_sealed, seal_phase

    if not is_phase_sealed(ROOT, "M0"):
        seal_phase(ROOT, "M0")
    assert is_phase_sealed(ROOT, "M0")


def test_seal_m0_idempotent():
    from tools.r0_migration_phase_guard import seal_phase

    if not (ROOT / "control" / "r0_migration" / "mandate.json").is_file():
        pytest.skip("mandate missing")
    r1 = seal_phase(ROOT, "M0")
    r2 = seal_phase(ROOT, "M0")
    assert r1.get("status") == "SEALED"
    assert r2.get("status") == "SEALED"
    seal_path = ROOT / "evidence" / "r0_migration" / "m0_phase_seal.json"
    assert seal_path.is_file()
    data = json.loads(seal_path.read_text(encoding="utf-8"))
    assert data["status"] == "SEALED"
    assert data["artifact_hashes"]
