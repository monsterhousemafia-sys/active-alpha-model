"""M0 R0 migration mandate artifacts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def mandate() -> dict:
    path = ROOT / "control" / "r0_migration" / "mandate.json"
    if not path.is_file():
        pytest.skip("M0 not executed: control/r0_migration/mandate.json missing")
    return json.loads(path.read_text(encoding="utf-8"))


def test_m0_mandate_doc_exists():
    assert (ROOT / "docs" / "R0_MIGRATION_MANDATE.md").is_file()


def test_m0_charter_draft_exists():
    assert (ROOT / "control" / "champion_decision_charter_r0_target_draft.md").is_file()


def test_m0_mandate_json_schema(mandate: dict):
    assert mandate["phase"] == "M0"
    assert mandate["status"] == "COMPLETE"
    assert mandate["authoritative_champion_until_m9"] == "R3_w075_q065_noexit"
    assert mandate["target_champion_primary"] == "R0_LEGACY_ENSEMBLE"
    assert mandate["decisions"]["auto_promotion"] is False
    assert mandate["decisions"]["paper_forward_required"] is True
    assert mandate["decisions"]["exe_os_rollout"] == "POST_M9_SEPARATE"
    gates = mandate["objective_function"]["gates_required"]
    assert "external_champion_change_approval" in gates


def test_m0_phase_status():
    path = ROOT / "control" / "r0_migration" / "phase_status.json"
    if not path.is_file():
        pytest.skip("phase_status.json missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["phases"]["M0"]["status"] in ("COMPLETE", "SEALED")
    assert data["phases"]["M1"]["status"] in ("PENDING", "IN_PROGRESS", "READY", "COMPLETE_WITH_BLOCKER")


def test_run_m0_tool_build_payload():
    from tools.run_r0_migration_phase_m0 import build_mandate_payload

    payload = build_mandate_payload(approved_at_utc="2026-05-31T12:00:00+00:00")
    assert payload["next_phase"] == "M1"
    assert "R5_rank_only_train5" in payload["decisions"]["excluded_variants"]
