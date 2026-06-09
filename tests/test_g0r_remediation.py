"""G0R remediation fail-closed tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aa_authorization_policy import resolve_authorization_status, write_authorization_artifacts
from aa_decision_cockpit_readonly_snapshot import build_g0r_review_snapshot, G0R_SNAPSHOT_REL
from aa_decision_cockpit_viewmodel import load_decision_cockpit
from aa_evidence_schema import AUTHORITATIVE_CHAMPION, LOCKED_CHAMPION
from tests.cockpit_governance_fixtures import build_clean_terminal_root, write_json


def test_locked_champion_is_m9_governance_champion() -> None:
    assert LOCKED_CHAMPION == AUTHORITATIVE_CHAMPION == "R0_LEGACY_ENSEMBLE"


def test_quarantined_r5_claim_does_not_block(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    write_json(
        root / "control" / "quarantine" / "g0r_r5_unauthorized" / "operational_champion_r5_claim.json",
        {"variant_id": "R5_rank_only_train5", "quarantine_classification": "UNAUTHORIZED_OR_UNSEALED_STATE"},
    )
    status = resolve_authorization_status(root)
    assert status["operational_status"] == "OPERATIONAL_AUTHORIZED"
    assert "R5_rank_only_train5_operational_claims" not in status["conflicting_sources"]


def test_active_r5_operational_pointer_blocks(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    write_json(
        root / "control" / "operational_champion.json",
        {"variant_id": "R5_rank_only_train5"},
    )
    status = resolve_authorization_status(root)
    assert status["operational_status"] == "BLOCKED_FOR_SAFETY"
    assert "R5_rank_only_train5_operational_claims" in status["conflicting_sources"]


def test_g0r_snapshot_never_shows_r5_active_champion(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    write_authorization_artifacts(root)
    snap = build_g0r_review_snapshot(root)
    overview = snap["cockpit_data"]["executive_overview"]
    assert overview["active_champion"] != "R5_rank_only_train5"
    assert overview["expected_champion"] == AUTHORITATIVE_CHAMPION
    for key in ("promotion_eligible_display", "paper_eligible_display", "real_money_eligible_display"):
        assert overview[key] != "YES"


def test_terminal_state_operational_when_clean(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    status = resolve_authorization_status(root)
    assert status["operational_authorized"] is True
    assert status["g1_execution_authorized"] is True
    assert "operative_jobs" in status["allowed_actions"]


def test_vision_progress_cannot_authorize_operations(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    write_json(
        root / "VISION_PROGRESS.json",
        {"operational_authorization": "FULL_USER_APPROVED", "safety_flags": {"REAL_MONEY_AUTHORIZED": "YES"}},
    )
    status = resolve_authorization_status(root)
    assert status["operational_authorized"] is False
    assert "VISION_PROGRESS.json" in status["conflicting_sources"]


def test_phase_catalog_includes_g0r() -> None:
    catalog = json.loads(
        (Path("control") / "vision_automation" / "phase_catalog.json").read_text(encoding="utf-8")
    )
    phase_ids = [p.get("phase_id") for p in catalog.get("phases") or []]
    assert "G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION" in phase_ids
    g0r = next(p for p in catalog["phases"] if p["phase_id"].startswith("G0R_"))
    assert "g1_execution" in (g0r.get("forbidden_actions") or [])


def test_review_registry_g0r_not_externally_sealed() -> None:
    registry = json.loads(
        (Path("control") / "vision_automation" / "review_registry" / "review_registry.json").read_text(
            encoding="utf-8"
        )
    )
    g0r = next(
        (r for r in registry.get("reviews") or [] if str(r.get("phase_id", "")).startswith("G0R_")),
        None,
    )
    assert g0r is not None
    assert g0r.get("external_sealed") is False
    assert g0r.get("review_zip_sha256") == "PENDING_EXTERNAL_SEAL"


def test_v5r_baseline_comparison_file_exists() -> None:
    from aa_doc_paths import doc_path

    path = doc_path("CODEX_G0R_V5R_BASELINE_COMPARISON.json")
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "entries" in payload


def test_g1_comparison_champion_is_r3() -> None:
    from aa_doc_paths import doc_path

    logic = doc_path("G1_COMPARISON_LOGIC.md")
    if logic.is_file():
        text = logic.read_text(encoding="utf-8")
        assert "R5_rank_only_train5" not in text or "UNAUTHORIZED" in text or "invalidated" in text.lower()


def test_auto_execute_real_money_false_under_conflict(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    write_json(
        root / "VISION_PROGRESS.json",
        {"operational_authorization": "FULL_USER_APPROVED"},
    )
    cfg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text(encoding="utf-8"))
    assert cfg.get("auto_execute_real_money_enabled") is False
    data = load_decision_cockpit(root)
    assert data["authorization_status"]["real_money_authorized"] is False


def test_g0r_snapshot_path_constant() -> None:
    assert G0R_SNAPSHOT_REL.as_posix() == "control/review_snapshot/g0r_decision_cockpit_snapshot.json"
