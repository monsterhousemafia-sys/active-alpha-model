"""Tests for V5R read-only review snapshot."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_decision_cockpit_readonly_snapshot import (
    BLOCKERS,
    EMBEDDED_FAIL_CLOSED_NAME,
    EMBEDDED_RELEASE_NAME,
    RELEASE_SNAPSHOT_SCOPE,
    V5R_NEUTRAL_BLOCKERS,
    _meipass_snapshot,
    build_review_snapshot,
    build_v5r_neutral_release_snapshot,
    cockpit_data_from_snapshot,
    is_neutral_release_snapshot,
    live_cockpit_requested,
    load_live_review_snapshot,
    write_review_snapshot,
    write_v5r_neutral_release_snapshot,
)


def test_snapshot_fields(tmp_path: Path):
    snap = build_review_snapshot(Path(__file__).resolve().parents[1])
    assert snap["mode"] == "READ_ONLY_REVIEW_SNAPSHOT"
    assert snap["operational_authorization"] == "NONE"
    assert snap["live_trading_allowed"] is False
    assert snap["auto_promotion_allowed"] is False
    assert snap["evidence_stage"] == "BACKTESTED"
    assert snap["forward_monitoring_status"] in ("BLOCKED", "NOT_AUTHORIZED")
    safety = (snap.get("cockpit_data") or {}).get("safety_automation") or {}
    assert safety.get("AUTO_EXECUTE_REAL_MONEY") == "DISABLED"
    assert len(snap["blockers"]) >= 1


def test_write_snapshot_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "promotion_gate_config.yaml").write_text(
        "auto_research_enabled: false\nauto_promote_paper_enabled: false\n"
        "auto_promote_signal_enabled: false\nauto_execute_real_money_enabled: false\n",
        encoding="utf-8",
    )
    for rel in (
        "control/auto_promotion_status.json",
        "control/promotion_status.json",
        "control/system_health.json",
        "control/last_known_good_state.json",
        "control/evidence/current_evidence_status.json",
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")
    path = write_review_snapshot(tmp_path)
    assert path.is_file()


def test_missing_snapshot_fail_closed():
    data = cockpit_data_from_snapshot({"missing_snapshot": True, "cockpit_data": None})
    assert "UNKNOWN" in str(data.get("banners"))


def test_snapshot_includes_blockers():
    root = Path(__file__).resolve().parents[1]
    snap = build_review_snapshot(root)
    assert "NO_OPERATIONAL_AUTHORIZATION" in snap["blockers"]
    assert snap["operational_authorization"] == "NONE"


def test_v5r_neutral_release_snapshot_scope_isolation():
    snap = build_v5r_neutral_release_snapshot()
    cockpit = snap["cockpit_data"]
    overview = cockpit["executive_overview"]
    assert overview["evidence_stage"] == "BACKTESTED"
    assert overview["v5r_external_acceptance"] == "PENDING_EXTERNAL_REVIEW"
    assert overview["promotion_eligible_display"] == "NO"
    assert overview["paper_eligible_display"] == "NO"
    assert overview["real_money_eligible_display"] == "NO"
    assert overview["active_champion"] == "NOT_DISCLOSED_IN_V5R_RELEASE"
    assert overview["candidate"] == "NOT_IN_V5R_RELEASE_SCOPE"
    assert overview["control_reference"] == "NOT_IN_V5R_RELEASE_SCOPE"
    assert "R3_w075" not in json.dumps(snap)
    assert "MOM_63_TOP12" not in json.dumps(snap)
    assert cockpit["source_health"]["fail_closed"] is True
    assert snap["release_snapshot_scope"] == RELEASE_SNAPSHOT_SCOPE
    assert "R3_w075" not in json.dumps(snap)


def test_write_neutral_release_snapshot_file(tmp_path: Path):
    path = write_v5r_neutral_release_snapshot(tmp_path)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["cockpit_data"]["gui_read_only"] is True


def test_meipass_snapshot_resolves_pyinstaller_embed_names(tmp_path: Path, monkeypatch):
    import sys

    meipass = tmp_path / "_MEIPASS"
    meipass.mkdir()
    (meipass / EMBEDDED_RELEASE_NAME).write_text('{"v5r_release_scope":"NEUTRAL_READ_ONLY_REVIEW_ONLY"}', encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    found = _meipass_snapshot()
    assert found is not None
    assert found.name == EMBEDDED_RELEASE_NAME


def test_live_cockpit_env_override(monkeypatch):
    monkeypatch.setenv("AA_V5R_LIVE_COCKPIT", "1")
    assert live_cockpit_requested() is True
    monkeypatch.setenv("AA_V5R_LIVE_COCKPIT", "neutral")
    assert live_cockpit_requested() is False


def test_neutral_release_snapshot_detection():
    assert is_neutral_release_snapshot({"v5r_release_scope": "NEUTRAL_READ_ONLY_REVIEW_ONLY"})
    assert not is_neutral_release_snapshot({"v5r_release_scope": "OTHER"})


def test_load_live_review_snapshot_uses_real_champion(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "promotion_gate_config.yaml").write_text(
        "auto_research_enabled: false\nauto_promote_paper_enabled: false\n"
        "auto_promote_signal_enabled: false\nauto_execute_real_money_enabled: false\n",
        encoding="utf-8",
    )
    for rel in (
        "control/auto_promotion_status.json",
        "control/promotion_status.json",
        "control/system_health.json",
        "control/last_known_good_state.json",
        "control/evidence/current_evidence_status.json",
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")
    snap = load_live_review_snapshot(tmp_path)
    assert snap.get("v5r_live_mode") is True
    assert snap.get("cockpit_data") is not None

