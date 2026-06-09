"""Tests for static V5R build provenance generation."""
from __future__ import annotations

import json
from pathlib import Path

from aa_decision_cockpit_readonly_snapshot import RELEASE_SNAPSHOT_SCOPE, build_v5r_neutral_release_snapshot
from tools.generate_v5r_build_provenance import (
    BUILD_SCOPE,
    VALIDATED_SOURCE_BASE,
    build_provenance_dict,
    write_build_provenance,
)


def test_build_provenance_fields():
    payload = build_provenance_dict()
    assert payload["validated_source_base"] == VALIDATED_SOURCE_BASE
    assert payload["build_scope"] == BUILD_SCOPE
    assert payload["release_snapshot_scope"] == RELEASE_SNAPSHOT_SCOPE
    assert len(payload["build_source_commit"]) >= 8


def test_neutral_snapshot_embeds_provenance(tmp_path: Path):
    provenance = {
        "build_source_commit": "abc123" * 5,
        "validated_source_base": VALIDATED_SOURCE_BASE,
        "build_scope": BUILD_SCOPE,
        "release_snapshot_scope": RELEASE_SNAPSHOT_SCOPE,
    }
    snap = build_v5r_neutral_release_snapshot(provenance=provenance)
    assert snap["release_snapshot_scope"] == RELEASE_SNAPSHOT_SCOPE
    assert snap["build_provenance"]["build_source_commit"] == provenance["build_source_commit"]


def test_write_build_provenance_files(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "build" / "decision_cockpit").mkdir(parents=True)
    import tools.generate_v5r_build_provenance as gen

    monkeypatch.setattr(gen, "ROOT", tmp_path)
    monkeypatch.setattr(gen, "MODULE_PATH", tmp_path / "aa_v5r_build_provenance.py")
    monkeypatch.setattr(gen, "JSON_PATH", tmp_path / "build" / "decision_cockpit" / "v5r_build_provenance.json")
    monkeypatch.setattr(gen, "resolve_build_source_commit", lambda root=None: "deadbeef" * 5)
    payload = write_build_provenance(root=tmp_path)
    assert (tmp_path / "aa_v5r_build_provenance.py").is_file()
    assert json.loads((tmp_path / "build" / "decision_cockpit" / "v5r_build_provenance.json").read_text())[
        "build_source_commit"
    ] == payload["build_source_commit"]


def test_smoke_evidence_uses_static_provenance(monkeypatch):
    import aa_v5r_build_provenance as prov

    monkeypatch.setattr(prov, "BUILD_SOURCE_COMMIT", "a" * 40)
    monkeypatch.setattr(prov, "VALIDATED_SOURCE_BASE", VALIDATED_SOURCE_BASE)
    monkeypatch.setattr(prov, "BUILD_SCOPE", BUILD_SCOPE)
    monkeypatch.setattr(prov, "RELEASE_SNAPSHOT_SCOPE", RELEASE_SNAPSHOT_SCOPE)
    monkeypatch.setattr(prov, "GENERATED_AT_UTC", "2026-01-01T00:00:00+00:00")
    from tools.decision_cockpit_readonly_launcher import build_smoke_evidence

    payload = build_smoke_evidence(
        root=Path("."),
        launcher_initialized=True,
        gui_initialization_reached=True,
        data={
            "gui_read_only": True,
            "operative_ui_actions_allowed": False,
            "source_health": {"fail_closed": True, "blocked_for_safety": True},
            "safety_automation": {},
        },
        operative_ui_actions_present=False,
        operative_import=False,
    )
    assert payload["source_commit"] == "a" * 40
    assert payload["build_provenance"]["build_scope"] == BUILD_SCOPE
