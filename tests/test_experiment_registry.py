"""Tests for aa_experiment_registry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_experiment_registry import (
    INITIAL_EXPERIMENT_ID,
    build_initial_mom_manifest,
    load_manifest,
    save_manifest,
    verify_manifest_provenance,
)


def test_initial_manifest_backtested_stage(tmp_path: Path):
    manifest = build_initial_mom_manifest(tmp_path)
    assert manifest["current_evidence_stage"] == "BACKTESTED"


def test_verify_provenance_ok(tmp_path: Path):
    from aa_experiment_registry import INITIAL_EXPERIMENT_ID, load_manifest

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "auto_promotion_status.json").write_text("{}", encoding="utf-8")
    manifest = build_initial_mom_manifest(tmp_path)
    save_manifest(tmp_path, manifest)
    ok, blockers = verify_manifest_provenance(tmp_path, load_manifest(tmp_path, INITIAL_EXPERIMENT_ID))
    assert ok
    assert not blockers


def test_verify_provenance_missing_file(tmp_path: Path):
    manifest = build_initial_mom_manifest(tmp_path)
    manifest["provenance"]["source_files"] = ["does/not/exist.json"]
    ok, blockers = verify_manifest_provenance(tmp_path, manifest)
    assert not ok
    assert "EVIDENCE_PROVENANCE_MISSING" in blockers


def test_duplicate_experiment_id_blocked(tmp_path: Path):
    manifest = build_initial_mom_manifest(tmp_path)
    save_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="duplicate"):
        save_manifest(tmp_path, manifest)


def test_registry_does_not_touch_protected_files(tmp_path: Path):
    protected = tmp_path / "control" / "last_known_good_state.json"
    protected.parent.mkdir(parents=True)
    before = {"validated_variant_id": "R3_w075_q065_noexit"}
    protected.write_text(json.dumps(before), encoding="utf-8")
    save_manifest(tmp_path, build_initial_mom_manifest(tmp_path))
    assert json.loads(protected.read_text(encoding="utf-8")) == before
