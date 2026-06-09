"""Decision Cockpit Update — Kickoff ohne operative Phasen."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.decision_cockpit_update import kickoff_decision_cockpit_update


def _seed(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "control/vision_automation").mkdir(parents=True, exist_ok=True)
    (root / "control/review_snapshot").mkdir(parents=True, exist_ok=True)
    policy = Path(__file__).resolve().parents[1] / "control/series_readiness_policy.json"
    (root / "control/series_readiness_policy.json").write_text(
        policy.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "control/vision_automation/automation_state.json").write_text(
        json.dumps(
            {
                "current_executed_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "next_phase_authorized": False,
            }
        ),
        encoding="utf-8",
    )
    (root / "evidence/series_readiness_latest.json").write_text(
        json.dumps({"series_ready": True, "readiness_pct": 100}),
        encoding="utf-8",
    )
    (root / "evidence/r3_local_growth_latest.json").write_text(
        json.dumps({"growth_pct": 100}),
        encoding="utf-8",
    )
    (root / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True}),
        encoding="utf-8",
    )


def test_kickoff_writes_evidence(tmp_path: Path) -> None:
    _seed(tmp_path)

    def _fake_repair(root: Path):
        return {"ok": True, "series_ready": True, "readiness_pct": 100}

    def _fake_snapshot(root: Path):
        path = tmp_path / "control/review_snapshot/v5r_decision_cockpit_snapshot.json"
        path.write_text(json.dumps({"build_status": "MANUAL_READ_ONLY_REVIEW_ONLY"}), encoding="utf-8")
        return path

    def _fake_checklist(root: Path, *, persist: bool = True):
        path = root / "evidence/r3_operational_checklist_latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"checklist_ok": True, "items_ok": 30, "items_total": 30}),
            encoding="utf-8",
        )
        return {"ok": True, "checklist_ok": True, "items_ok": 30, "items_total": 30}

    (tmp_path / "control/decision_cockpit_r3_bridge.json").write_text(
        json.dumps({"mission_de": "test", "forbidden_de": ["no promote"]}),
        encoding="utf-8",
    )

    with (
        patch(
            "analytics.series_readiness.apply_series_readiness_repair",
            side_effect=_fake_repair,
        ),
        patch(
            "analytics.r3_operational_checklist.scan_operational_checklist",
            side_effect=_fake_checklist,
        ),
        patch(
            "aa_decision_cockpit_readonly_snapshot.refresh_live_review_snapshot",
            side_effect=_fake_snapshot,
        ),
        patch("analytics.alpha_model_cursor_bridge.push_cursor_to_king", return_value={"ok": True}),
        patch("analytics.king_network.sync_network_pulse", return_value={"ok": True, "phase": "build"}),
    ):
        doc = kickoff_decision_cockpit_update(tmp_path, persist=True)

    assert doc.get("ok") is True
    assert doc.get("series_ready") is True
    assert doc.get("checklist_ok") is True
    assert (tmp_path / "evidence/decision_cockpit_update_latest.json").is_file()
    assert doc.get("r3_vision_bridge_de", {}).get("r3_cycle_closed") is True
    assert doc.get("bridge_policy_ref") == "control/decision_cockpit_r3_bridge.json"
