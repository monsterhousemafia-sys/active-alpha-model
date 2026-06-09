"""Tests for aa_monitoring_readiness."""
from __future__ import annotations

from aa_doc_paths import write_root_doc_file

import json
from pathlib import Path

import yaml

from aa_monitoring_readiness import (
    build_forward_monitoring_data_requirements,
    build_forward_monitoring_readiness,
    export_forward_monitoring_readiness,
)
from aa_experiment_registry import build_initial_mom_manifest, save_manifest


def _minimal_root(tmp_path: Path) -> Path:
    (tmp_path / "promotion_gate_config.yaml").write_text(
        yaml.dump(
            {
                "auto_research_enabled": False,
                "auto_promote_paper_enabled": False,
                "auto_promote_signal_enabled": False,
                "auto_execute_real_money_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control").mkdir()
    write_root_doc_file(tmp_path, "P9_EXTERNAL_REVIEW_STATUS.md", "PREEXISTING_UNREVIEWED_PASS\n")
    save_manifest(tmp_path, build_initial_mom_manifest(tmp_path))
    ev = tmp_path / "control" / "evidence"
    ev.mkdir(parents=True)
    (ev / "cost_stress_status.json").write_text(
        json.dumps(
            {
                "COST_STRESS_GATE": {
                    "pass": False,
                    "evaluation_status": "NOT_EVALUABLE",
                    "blockers": ["CHALLENGER_TURNOVER_NOT_VERIFIED"],
                }
            }
        ),
        encoding="utf-8",
    )
    (ev / "multiple_testing_status.json").write_text(
        json.dumps({"MULTIPLE_TESTING_EVIDENCE": {"pass": False, "blocker": "DSR_BELOW_REQUIRED_CONFIDENCE"}}),
        encoding="utf-8",
    )
    (ev / "robustness_status.json").write_text(
        json.dumps({"ROBUSTNESS_EVIDENCE": {"pass": False, "status": "PARTIAL_ONLY"}}),
        encoding="utf-8",
    )
    return tmp_path


def test_readiness_blocked_with_v2r_blockers(tmp_path: Path):
    root = _minimal_root(tmp_path)
    status = build_forward_monitoring_readiness(root)
    assert status["activation_status"] == "BLOCKED"
    assert "CHALLENGER_TURNOVER_NOT_VERIFIED" in status["active_blockers"]
    assert "DSR_BELOW_REQUIRED_CONFIDENCE" in status["active_blockers"]
    assert "FORWARD_MONITORING_NOT_EXTERNALLY_APPROVED" in status["active_blockers"]


def test_baseline_cost_reports_missing_note(tmp_path: Path):
    root = _minimal_root(tmp_path)
    status = build_forward_monitoring_readiness(root)
    assert status["baseline_cost_reports"]["external_inclusion_note"] == "BASELINE_COST_REPORT_NOT_EXTERNALLY_INCLUDED"


def test_data_requirements_do_not_activate(tmp_path: Path):
    req = build_forward_monitoring_data_requirements(tmp_path)
    assert req["V3S_SHADOW_OBSERVATION"]["activation_triggers_jobs"] is False
    assert req["V3P_PAPER_SIMULATION"]["activation_triggers_jobs"] is False


def test_export_only_writes_evidence(tmp_path: Path):
    root = _minimal_root(tmp_path)
    cfg = root / "promotion_gate_config.yaml"
    before = cfg.read_bytes()
    export_forward_monitoring_readiness(root)
    assert cfg.read_bytes() == before
    assert (root / "control" / "evidence" / "forward_monitoring_readiness_status.json").is_file()
