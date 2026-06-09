"""Tests for aa_robustness_evidence (V2R)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_robustness_evidence import build_robustness_status, export_robustness_status
from aa_robustness_evidence import _subperiod_screen


def test_missing_subperiod_inputs_not_evaluable():
    result = _subperiod_screen(pd.Series([0.01, -0.02]))
    assert result["status"] == "NOT_EVALUABLE"


def test_unstable_subperiods_fail():
    idx = pd.date_range("2019-01-01", periods=200, freq="B")
    first = pd.Series([0.01] * 100, index=idx[:100])
    second = pd.Series([-0.02] * 100, index=idx[100:])
    series = pd.concat([first, second])
    result = _subperiod_screen(series)
    assert result["status"] == "FAIL"


def test_positive_subperiods_can_pass():
    idx = pd.date_range("2019-01-01", periods=200, freq="B")
    series = pd.Series([0.001] * 200, index=idx)
    result = _subperiod_screen(series)
    assert result["status"] == "PASS"


def test_subperiod_screen_alone_not_full_robustness(tmp_path: Path):
    ev_dir = tmp_path / "control" / "evidence"
    ev_dir.mkdir(parents=True)
    (ev_dir / "cost_stress_status.json").write_text(
        json.dumps({"COST_STRESS_GATE": {"pass": False, "evaluation_status": "NOT_EVALUABLE"}}),
        encoding="utf-8",
    )
    (ev_dir / "multiple_testing_status.json").write_text(
        json.dumps({"MULTIPLE_TESTING_EVIDENCE": {"pass": False, "status": "NOT_EVALUABLE"}}),
        encoding="utf-8",
    )
    status = build_robustness_status(tmp_path)
    assert status["ROBUSTNESS_EVIDENCE"]["pass"] is False
    assert status["ROBUSTNESS_EVIDENCE"]["status"] in {"PARTIAL_ONLY", "NOT_EVALUABLE", "FAIL"}


def test_failed_cost_stress_limits_to_partial_only(tmp_path: Path):
    ev_dir = tmp_path / "control" / "evidence"
    ev_dir.mkdir(parents=True)
    (ev_dir / "cost_stress_status.json").write_text(
        json.dumps({"COST_STRESS_GATE": {"pass": False, "evaluation_status": "NOT_EVALUABLE"}}),
        encoding="utf-8",
    )
    (ev_dir / "multiple_testing_status.json").write_text(
        json.dumps({"MULTIPLE_TESTING_EVIDENCE": {"pass": True, "status": "PASS"}}),
        encoding="utf-8",
    )
    status = build_robustness_status(tmp_path)
    assert status["ROBUSTNESS_EVIDENCE"]["pass"] is False
    assert "COST_STRESS_GATE_NOT_PASSED" in status["ROBUSTNESS_EVIDENCE"]["blockers"]


def test_failed_multiple_testing_limits_to_partial_only(tmp_path: Path):
    ev_dir = tmp_path / "control" / "evidence"
    ev_dir.mkdir(parents=True)
    (ev_dir / "cost_stress_status.json").write_text(
        json.dumps({"COST_STRESS_GATE": {"pass": True, "evaluation_status": "PASS"}}),
        encoding="utf-8",
    )
    (ev_dir / "multiple_testing_status.json").write_text(
        json.dumps({"MULTIPLE_TESTING_EVIDENCE": {"pass": False, "status": "FAIL"}}),
        encoding="utf-8",
    )
    status = build_robustness_status(tmp_path)
    assert status["ROBUSTNESS_EVIDENCE"]["pass"] is False
    assert "MULTIPLE_TESTING_NOT_PASSED" in status["ROBUSTNESS_EVIDENCE"]["blockers"]


def test_no_stage_above_backtested(tmp_path: Path):
    status = build_robustness_status(tmp_path)
    assert "SUBPERIOD_STABILITY_SCREEN" in status
    assert status["ROBUSTNESS_EVIDENCE"]["pass"] is not True


def test_export_preserves_promotion_status(tmp_path: Path):
    (tmp_path / "control").mkdir()
    (tmp_path / "control" / "promotion_status.json").write_text('{"all_gates_pass": false}', encoding="utf-8")
    before = (tmp_path / "control" / "promotion_status.json").read_text(encoding="utf-8")
    export_robustness_status(tmp_path)
    after = (tmp_path / "control" / "promotion_status.json").read_text(encoding="utf-8")
    assert before == after
