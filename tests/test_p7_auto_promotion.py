"""P7 auto-promotion EXE visibility gate tests (master prompt §16.6)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from aa_auto_promotion import (
    CONFIG_FILE,
    SIGNAL_POINTER,
    attempt_auto_promotion,
    evaluate_auto_promotion_gates,
    execute_auto_rollback,
    load_promotion_gate_config,
    run_auto_promotion_sync,
)
from aa_shadow_champion import SHADOW_SIGNALS_FILE, load_shadow_signals


def _write_config(root: Path, **overrides) -> None:
    base = {
        "schema_version": 1,
        "promotion_mode": "MANUAL",
        "minimum_shadow_rebalances": 1,
        "minimum_mature_shadow_outcomes": 1,
        "required_comparisons": ["champion", "M1_MOM_BLEND_MATCHED_CONTROLS"],
        "cost_stress_scenarios": ["baseline"],
        "drawdown_tolerance": 0.35,
        "turnover_tolerance": 2.0,
        "rollback_thresholds": {"max_drawdown_breach": 0.40, "min_mature_paper_outcomes": 1},
        "auto_research_enabled": True,
        "auto_promote_paper_enabled": False,
        "auto_promote_signal_enabled": False,
        "auto_execute_real_money_enabled": False,
    }
    base.update(overrides)
    (root / CONFIG_FILE).write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")


def _seed_out(root: Path, out: Path, *, challenger: str = "MOM_63_TOP12", integrity: bool = True) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest_validated_run.json").write_text(
        json.dumps({"run_id": "champion", "integrity_status": "PASS", "variant_id": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    research = {
        "research_status": "PASS",
        "entries": [
            {
                "variant_id": "R3_w075_q065_noexit",
                "integrity_pass": True,
                "is_active_champion": True,
                "metrics": {"sharpe_0rf": 0.92, "max_drawdown": -0.26},
            },
            {
                "variant_id": "M1_MOM_BLEND_MATCHED_CONTROLS",
                "integrity_pass": True,
                "metrics": {"sharpe_0rf": 0.98, "max_drawdown": -0.24},
            },
            {
                "variant_id": challenger,
                "integrity_pass": integrity,
                "is_research_candidate": True,
                "run_dir": str(root / "validation_runs" / f"x_{challenger}"),
                "metrics": {"sharpe_0rf": 1.01, "max_drawdown": -0.24},
            },
        ],
    }
    (out / "background_research_status.json").write_text(json.dumps(research), encoding="utf-8")
    (out / "challenger_registry.json").write_text(
        json.dumps({"shadow_challenger_id": challenger, "challengers": []}),
        encoding="utf-8",
    )
    (out / "prediction_feedback_summary.json").write_text(json.dumps({"mature_outcomes": 10}), encoding="utf-8")
    (out / "realtime_replay_status.json").write_text(json.dumps({"data_quality_status": "PASS"}), encoding="utf-8")
    (out / "data_quality_report.csv").write_text("ok\n", encoding="utf-8")
    import pandas as pd

    pd.DataFrame([{"shadow_id": "s1", "challenger_variant_id": challenger}]).to_parquet(out / SHADOW_SIGNALS_FILE, index=False)
    pd.DataFrame([{"shadow_id": "s1", "challenger_variant_id": challenger, "outcome_status": "MATURE"}]).to_parquet(
        out / "shadow_outcomes.parquet", index=False
    )
    ctrl = root / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "last_known_good_state.json").write_text(
        json.dumps(
            {
                "validated_run_id": "champion",
                "validated_variant_id": "R3_w075_q065_noexit",
                "out_dir": str(out),
                "artifacts": ["latest_validated_run.json"],
                "pointer": json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8")),
            }
        ),
        encoding="utf-8",
    )


def test_p7_default_config_keeps_auto_promotion_disabled(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root)
    _seed_out(root, out)
    summary = run_auto_promotion_sync(root, out)
    assert summary["status"] == "OK"
    assert summary["auto_promotion_status"] == "DISABLED"
    cfg = load_promotion_gate_config(root)
    assert cfg.get("auto_execute_real_money_enabled") is False


def test_p7_integrity_fail_never_promoted(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True)
    _seed_out(root, out, integrity=False)
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["promotion_allowed"] is False
    assert "challenger_integrity_fail" in gate["blocked_reasons"]
    result = attempt_auto_promotion(root, out, mode="paper")
    assert result["status"] == "BLOCKED"


def test_p7_data_quality_fail_never_promoted(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True)
    _seed_out(root, out)
    (out / "realtime_replay_status.json").write_text(json.dumps({"data_quality_status": "FAIL"}), encoding="utf-8")
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["gates"]["DATA_QUALITY_GATE"]["pass"] is False
    assert gate["gates"]["DATA_QUALITY_GATE"]["evidence_state"] == "fail"
    assert gate["promotion_allowed"] is False
    assert "data_quality_fail" in gate["blocked_reasons"]


def test_p7_missing_data_quality_evidence_fail_closed(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True)
    _seed_out(root, out)
    (out / "realtime_replay_status.json").unlink(missing_ok=True)
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["gates"]["DATA_QUALITY_GATE"]["pass"] is False
    assert gate["gates"]["DATA_QUALITY_GATE"]["evidence_state"] == "missing"
    assert "data_quality_evidence_missing" in gate["blocked_reasons"]
    assert gate["promotion_allowed"] is False


def test_p7_data_quality_pass_when_evidence_present(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True)
    _seed_out(root, out)
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["gates"]["DATA_QUALITY_GATE"]["pass"] is True
    assert gate["gates"]["DATA_QUALITY_GATE"]["evidence_state"] == "pass"


def test_p7_invalid_promotion_mode_writes_no_artifacts(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True)
    _seed_out(root, out)
    champion_ptr = (out / "latest_validated_run.json").read_text(encoding="utf-8")
    for bad_mode in ("realtime", "", "PROMOTE"):
        result = attempt_auto_promotion(root, out, mode=bad_mode)
        assert result["status"] == "BLOCKED"
        assert result["reason"] == "invalid_promotion_mode"
    assert not (out / SIGNAL_POINTER).is_file()
    assert (out / "latest_validated_run.json").read_text(encoding="utf-8") == champion_ptr


def test_p7_missing_m1_blocks_promotion(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True)
    _seed_out(root, out)
    research = json.loads((out / "background_research_status.json").read_text(encoding="utf-8"))
    research["entries"] = [e for e in research["entries"] if e["variant_id"] != "M1_MOM_BLEND_MATCHED_CONTROLS"]
    (out / "background_research_status.json").write_text(json.dumps(research), encoding="utf-8")
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["promotion_allowed"] is False
    assert "m1_comparison_missing" in gate["blocked_reasons"]


def test_p7_signal_promotion_requires_shadow_gate(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_signal_enabled=True, minimum_mature_shadow_outcomes=1000)
    _seed_out(root, out)
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["promotion_allowed"] is False
    assert "shadow_gate_not_passed" in gate["blocked_reasons"]
    result = attempt_auto_promotion(root, out, mode="signal")
    assert result["status"] == "BLOCKED"


def test_p7_paper_promotion_blocked_without_cost_stress(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True, minimum_mature_shadow_outcomes=1)
    _seed_out(root, out)
    champion_ptr = (out / "latest_validated_run.json").read_text(encoding="utf-8")
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["all_required_gates_pass"] is False
    assert gate["promotion_allowed"] is False
    assert "cost_stress_not_passed" in gate["blocked_reasons"]
    result = attempt_auto_promotion(root, out, mode="paper")
    assert result["status"] == "BLOCKED"
    assert not (out / SIGNAL_POINTER).is_file()
    assert (out / "latest_validated_run.json").read_text(encoding="utf-8") == champion_ptr


def test_p7_signal_promotion_blocked_without_cost_stress(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_signal_enabled=True, minimum_mature_shadow_outcomes=1)
    _seed_out(root, out)
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["promotion_allowed"] is False
    assert "cost_stress_not_passed" in gate["blocked_reasons"]
    result = attempt_auto_promotion(root, out, mode="signal")
    assert result["status"] == "BLOCKED"


def test_p7_negative_economic_value_blocks_promotion(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True, minimum_mature_shadow_outcomes=1)
    _seed_out(root, out)
    research = json.loads((out / "background_research_status.json").read_text(encoding="utf-8"))
    for entry in research["entries"]:
        if entry["variant_id"] == "MOM_63_TOP12":
            entry["metrics"]["sharpe_0rf"] = 0.50
    (out / "background_research_status.json").write_text(json.dumps(research), encoding="utf-8")
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["promotion_allowed"] is False
    assert "economic_value_not_passed" in gate["blocked_reasons"]


def test_p7_negative_risk_gate_blocks_promotion(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True, minimum_mature_shadow_outcomes=1)
    _seed_out(root, out)
    research = json.loads((out / "background_research_status.json").read_text(encoding="utf-8"))
    for entry in research["entries"]:
        if entry["variant_id"] == "MOM_63_TOP12":
            entry["metrics"]["max_drawdown"] = -0.99
    (out / "background_research_status.json").write_text(json.dumps(research), encoding="utf-8")
    gate = evaluate_auto_promotion_gates(root, out)
    assert gate["promotion_allowed"] is False
    assert "risk_gate_not_passed" in gate["blocked_reasons"]


def test_p7_rollback_restores_champion_without_mutating_shadow(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_promote_paper_enabled=True, minimum_mature_shadow_outcomes=1)
    _seed_out(root, out)
    shadow_before = load_shadow_signals(out)
    (out / SIGNAL_POINTER).write_text(
        json.dumps(
            {
                "updated_at_utc": "2026-01-01T00:00:00+00:00",
                "promotion_mode": "PAPER",
                "variant_id": "MOM_63_TOP12",
                "run_dir": str(root / "validation_runs" / "x_MOM_63_TOP12"),
                "integrity_status": "PASS",
                "promoted_from_champion": "R3_w075_q065_noexit",
                "auto_promoted": True,
            }
        ),
        encoding="utf-8",
    )
    (out / "latest_validated_run.json").write_text(
        json.dumps({"run_id": "bad", "integrity_status": "PASS", "variant_id": "BAD"}),
        encoding="utf-8",
    )
    result = execute_auto_rollback(root, out, reason="test")
    assert result["shadow_signals_unchanged"] is True
    pointer = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert pointer["variant_id"] == "R3_w075_q065_noexit"
    shadow_after = load_shadow_signals(out)
    assert len(shadow_before) == len(shadow_after)


def test_p7_exe_status_fields(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    (root / "DEVELOPMENT_PIPELINE.json").write_text(
        json.dumps({"current_phase": "P7_AUTO_PROMOTION_EXE_VISIBILITY", "phases": []}),
        encoding="utf-8",
    )
    _write_config(root, auto_research_enabled=False)
    _seed_out(root, out)
    run_auto_promotion_sync(root, out)
    from aa_model_status import build_model_status, format_model_status_block

    status = build_model_status(out)
    assert status["auto_research_status"] == "DISABLED"
    assert status["auto_promotion_status"] == "DISABLED"
    assert status["auto_execute_real_money_status"] == "DISABLED"
    text = format_model_status_block(status)
    assert "AI-Entwicklung" in text
    assert "Echtgeld-Ausführung: DISABLED" in text


def test_p7_real_money_stays_disabled(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root, auto_execute_real_money_enabled=True)
    cfg = load_promotion_gate_config(root)
    assert cfg.get("auto_execute_real_money_enabled") is False
