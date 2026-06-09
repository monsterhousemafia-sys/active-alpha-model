"""Fail-closed authorization conflict tests (G0 governance)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aa_authorization_policy import (
    REVIEW_SNAPSHOT_PATH,
    format_authorization_tab_lines,
    resolve_authorization_status,
    write_authorization_artifacts,
)
from aa_decision_cockpit_gui import build_cockpit_tab_labels
from aa_decision_cockpit_readonly_snapshot import build_review_snapshot
from aa_decision_cockpit_viewmodel import load_decision_cockpit
from aa_evidence_schema import LOCKED_CHAMPION
from tests.cockpit_governance_fixtures import (
    build_clean_terminal_root,
    build_g0_conflict_root,
    write_json,
)


@pytest.fixture
def g0_root(tmp_path: Path) -> Path:
    return build_g0_conflict_root(tmp_path)


def test_final_approval_forbids_operations_with_vision_conflict(g0_root: Path) -> None:
    status = resolve_authorization_status(g0_root)
    assert status["status"] == "CONFLICT_BLOCKED_FOR_SAFETY"
    assert status["operational_status"] == "BLOCKED_FOR_SAFETY"
    assert "VISION_PROGRESS.json" in status["conflicting_sources"]
    assert status["real_money_authorized"] is False


def test_real_money_remains_not_authorized(g0_root: Path) -> None:
    status = resolve_authorization_status(g0_root)
    assert status["real_money_authorized"] is False
    assert status["promotion_authorized"] is False


def test_conflict_state_allows_only_manual_read_only(g0_root: Path) -> None:
    status = resolve_authorization_status(g0_root)
    assert status["allowed_actions"] == ["manual_read_only_review"]
    assert "real_money_execution" in status["blocked_actions"]


def test_missing_final_approval_does_not_block_when_no_conflict(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    write_json(root / "VISION_PROGRESS.json", {"operational_authorization": "NONE"})
    status = resolve_authorization_status(root)
    assert status["authoritative_source_present"] is False
    assert status["operational_status"] == "OPERATIONAL_AUTHORIZED"
    assert status["operational_authorized"] is True


def test_gui_shows_conflict_and_blocked_status(g0_root: Path) -> None:
    data = load_decision_cockpit(g0_root)
    tabs = build_cockpit_tab_labels(data)
    auth = tabs["Authorization"]
    assert "BLOCKED" in auth.upper() or "CONFLICT" in auth.upper()
    assert "NOT AUTHORIZED" in auth.upper()
    assert data["authorization_status"]["real_money_authorized"] is False


def test_champion_unchanged_and_auto_real_money_disabled(g0_root: Path) -> None:
    data = load_decision_cockpit(g0_root)
    assert data["executive_overview"]["active_champion"] == LOCKED_CHAMPION
    assert data["safety_automation"]["AUTO_EXECUTE_REAL_MONEY"] in ("DISABLED", "UNKNOWN")


def test_write_authorization_artifacts(g0_root: Path) -> None:
    status = write_authorization_artifacts(g0_root)
    assert (g0_root / "control" / "authorization" / "authorization_source_policy.json").is_file()
    assert (g0_root / "control" / "authorization" / "current_authorization_status.json").is_file()
    assert status["operational_status"] == "BLOCKED_FOR_SAFETY"


def test_promotion_claim_does_not_authorize_with_phase_catalog_forbidding(g0_root: Path) -> None:
    status = resolve_authorization_status(g0_root)
    assert status["promotion_authorized"] is False
    assert status["operational_authorized"] is False


def test_registry_hash_missing_does_not_block_when_no_conflict(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "EXTERNAL_REVIEW_APPROVAL_FINAL.md").write_text(
        "No operational authorization is granted by this approval.\n",
        encoding="utf-8",
    )
    write_json(root / "VISION_PROGRESS.json", {"operational_authorization": "NONE"})
    write_json(
        root / "control" / "vision_automation" / "review_registry" / "review_registry.json",
        {"reviews": []},
    )
    status = resolve_authorization_status(root)
    assert status["operational_status"] == "OPERATIONAL_AUTHORIZED"
    assert "control/vision_automation/review_registry/review_registry.json" not in status["conflicting_sources"]


def test_operational_authorized_when_no_conflict(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    status = resolve_authorization_status(root)
    assert status["status"] == "OPERATIONAL_AUTHORIZED"
    assert status["operational_authorized"] is True
    assert not status["conflicting_sources"]
    data = load_decision_cockpit(root)
    auth = build_cockpit_tab_labels(data)["Authorization"]
    assert "OPERATIONAL AUTHORIZATION ACTIVE" in auth.upper() or "AUTHORIZED" in auth.upper()
    assert data["authorization_status"]["real_money_authorized"] is False


def test_auto_execute_real_money_false_despite_conflicting_progress(g0_root: Path) -> None:
    cfg = yaml.safe_load((g0_root / "promotion_gate_config.yaml").read_text(encoding="utf-8"))
    assert cfg.get("auto_execute_real_money_enabled") is False
    data = load_decision_cockpit(g0_root)
    assert data["safety_automation"]["AUTO_EXECUTE_REAL_MONEY"] in ("DISABLED", "UNKNOWN")
    assert data["authorization_status"]["real_money_authorized"] is False


def test_governance_display_keeps_real_money_disabled_when_operational(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    cfg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text(encoding="utf-8"))
    cfg["auto_execute_real_money_enabled"] = True
    cfg["auto_promote_paper_enabled"] = True
    (root / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["authorization_status"]["operational_authorized"] is True
    assert data["safety_automation"]["AUTO_EXECUTE_REAL_MONEY"] == "DISABLED"
    assert data["safety_automation"]["AUTO_PROMOTE_PAPER"] == "ENABLED"
    assert data["safety_automation"]["automation_blocked_for_safety"] is False


def test_review_snapshot_safety_automation_matches_governance(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    cfg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text(encoding="utf-8"))
    cfg["auto_execute_real_money_enabled"] = True
    (root / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    snap = build_review_snapshot(root)
    safety = snap["cockpit_data"]["safety_automation"]
    assert safety["AUTO_EXECUTE_REAL_MONEY"] == "DISABLED"
    assert snap["operational_authorization"] == "NONE"


def test_stale_review_snapshot_claims_conflict(tmp_path: Path) -> None:
    root = build_clean_terminal_root(tmp_path)
    write_json(
        root / REVIEW_SNAPSHOT_PATH,
        {
            "operational_authorization": "FULL_USER_APPROVED",
            "live_trading_allowed": True,
            "build_status": "OPERATIONAL_AUTHORIZATION_ACTIVE",
        },
    )
    status = resolve_authorization_status(root)
    assert str(REVIEW_SNAPSHOT_PATH).replace("\\", "/") in status["conflicting_sources"]
    assert status["operational_status"] == "BLOCKED_FOR_SAFETY"


def test_format_authorization_tab_lines_matches_gui(g0_root: Path) -> None:
    data = load_decision_cockpit(g0_root)
    direct = "\n".join(format_authorization_tab_lines(data["authorization_status"]))
    gui = build_cockpit_tab_labels(data)["Authorization"]
    assert direct == gui
