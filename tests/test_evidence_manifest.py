"""Tests for aa_evidence_manifest fail-closed validation."""
from __future__ import annotations

import json
from pathlib import Path

from aa_evidence_manifest import compose_evidence_manifest, validate_evidence_manifest


def test_compose_and_validate_manifest_passes_with_matching_hashes(tmp_path: Path):
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    snap = out / "run_config_snapshot.txt"
    snap.write_text("cfg", encoding="utf-8")
    returns = out / "strategy_daily_returns.csv"
    returns.write_text("date,strategy_return\n2020-01-01,0.01\n", encoding="utf-8")
    report = out / "backtest_report.txt"
    report.write_text("report", encoding="utf-8")
    constraints = out / "constraint_binding_history.csv"
    constraints.write_text("date,x\n2020-01-01,1\n", encoding="utf-8")
    (out / "latest_validated_run.json").write_text(
        json.dumps({"run_id": "test_run", "variant_id": "R0_LEGACY"}), encoding="utf-8"
    )

    manifest = compose_evidence_manifest(tmp_path, out, variant="R0_LEGACY", run_id="test_run")
    ok, errors, checks = validate_evidence_manifest(tmp_path, manifest)
    assert ok, (errors, checks)


def test_validate_manifest_fail_closed_on_hash_mismatch(tmp_path: Path):
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    (out / "strategy_daily_returns.csv").write_text("date,strategy_return\n2020-01-01,0.01\n", encoding="utf-8")
    manifest = compose_evidence_manifest(tmp_path, out)
    manifest["strategy_returns_hash"] = "deadbeef"
    ok, errors, _ = validate_evidence_manifest(tmp_path, manifest)
    assert not ok
    assert any("HASH_MISMATCH" in e for e in errors)


def test_validate_manifest_fail_closed_when_missing(tmp_path: Path):
    ok, errors, _ = validate_evidence_manifest(tmp_path, {})
    assert not ok
    assert "EVIDENCE_MANIFEST_MISSING" in errors
