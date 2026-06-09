"""Tests for unattended pipeline autopilot."""
from __future__ import annotations

import json
from pathlib import Path

from aa_ops_refresh import AutopilotOutDirError, resolve_autopilot_out_dir
from aa_pipeline_autopilot import load_autopilot_config, run_autopilot_once, write_pending
from aa_pipeline_orchestration import enqueue_next_phase, load_pending, merge_maintenance_details


def test_load_autopilot_defaults(tmp_path: Path) -> None:
    cfg = load_autopilot_config(tmp_path)
    assert cfg["enabled"] is True


def test_write_pending(tmp_path: Path) -> None:
    _write_pipeline = tmp_path / "DEVELOPMENT_PIPELINE.json"
    _write_pipeline.write_text(
        '{"auto_continue_after_pass":true,"current_phase":"P2","phases":[]}',
        encoding="utf-8",
    )
    write_pending(tmp_path, has_work=True, followup_prompt="go")
    payload = json.loads((tmp_path / "control" / "pipeline_pending.json").read_text(encoding="utf-8"))
    assert payload["has_work"] is True
    assert payload.get("schema_version") == 1


def test_autopilot_disabled(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "autopilot.json").write_text('{"enabled": false}', encoding="utf-8")
    report = run_autopilot_once(tmp_path)
    assert report.steps[0]["status"] == "DISABLED"


def test_resolve_out_dir_from_bat_config(tmp_path: Path) -> None:
    (tmp_path / "active_alpha_user_config.bat").write_text(
        'set "AA_BACKTEST_OUT_DIR=model_output_sp500_pit_t212"\n',
        encoding="utf-8",
    )
    out_dir, _env = resolve_autopilot_out_dir(tmp_path, env={})
    assert out_dir == tmp_path / "model_output_sp500_pit_t212"


def test_resolve_out_dir_fail_closed_without_config(tmp_path: Path) -> None:
    try:
        resolve_autopilot_out_dir(tmp_path, env={})
        assert False, "expected AutopilotOutDirError"
    except AutopilotOutDirError as exc:
        assert "AA_BACKTEST_OUT_DIR" in str(exc)


def test_autopilot_fail_closed_skips_control_plane(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "DEVELOPMENT_PIPELINE.json").write_text(
        '{"current_phase":"P9","phases":[]}',
        encoding="utf-8",
    )
    health_before = (tmp_path / "control" / "system_health.json").is_file()
    report = run_autopilot_once(tmp_path)
    assert any(s.get("step") == "resolve_out_dir" and s.get("status") == "FAIL" for s in report.steps)
    assert (tmp_path / "control" / "system_health.json").is_file() == health_before


def test_maintenance_preserves_p9_pending(tmp_path: Path) -> None:
    p9 = "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION"
    p7 = "P7_AUTO_PROMOTION_EXE_VISIBILITY"
    (tmp_path / "DEVELOPMENT_PIPELINE.json").write_text(
        json.dumps(
            {
                "auto_continue_after_pass": True,
                "current_phase": p9,
                "control_policy": {"enqueue_next_phase_after_pass": True},
                "phases": [
                    {"id": p7, "status": "PASS", "next_phase": p9},
                    {"id": p9, "status": "NOT_STARTED", "next_phase": None},
                ],
            }
        ),
        encoding="utf-8",
    )
    enqueue_next_phase(
        tmp_path,
        pending_phase=p9,
        created_from_phase=p7,
        reason="P7 PASS; P9 permitted",
    )
    merge_maintenance_details(tmp_path, details={"batch_busy": False}, maintenance_has_work=False)
    pending = load_pending(tmp_path)
    assert pending["has_work"] is True
    assert pending["pending_phase"] == p9
