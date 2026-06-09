"""Tests for aa_decision_cockpit_viewmodel (V4R / V4R2 fail-closed)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from aa_decision_cockpit_export import export_decision_cockpit_json, validate_export_directory
from aa_decision_cockpit_viewmodel import LOCKED_CHAMPION, load_decision_cockpit
from aa_experiment_registry import build_initial_mom_manifest, save_manifest
from tests.cockpit_governance_fixtures import write_final_approval_and_registry


def _shadow_monitor_payload(**overrides) -> dict:
    base = {
        "activation_status": "BLOCKED",
        "activation_externally_approved": False,
        "operative_jobs_started": False,
        "shadow_collection_started": False,
        "promotion_allowed": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "observation_type": "SHADOW_OBSERVATION",
        "active_blockers": ["SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED"],
    }
    base.update(overrides)
    return base


def _paper_monitor_payload(**overrides) -> dict:
    base = {
        "activation_status": "BLOCKED",
        "activation_externally_approved": False,
        "operative_jobs_started": False,
        "paper_simulation_started": False,
        "promotion_allowed": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "observation_type": "PAPER_SIMULATION",
        "active_blockers": ["PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED"],
    }
    base.update(overrides)
    return base


def _fixture_root(tmp_path: Path, *, include_champion: bool = True) -> Path:
    write_final_approval_and_registry(tmp_path)
    (tmp_path / "VISION_PROGRESS.json").write_text(
        json.dumps(
            {
                "current_phase": "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
                "operational_authorization": "NONE",
                "informational_only": True,
            }
        ),
        encoding="utf-8",
    )
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
    (tmp_path / "control").mkdir(exist_ok=True)
    auto = {
        "automation_modes": {"AUTO_RESEARCH": "DISABLED"},
        "champion_variant_id": LOCKED_CHAMPION if include_champion else None,
        "gate_evaluation": {
            "champion_variant_id": LOCKED_CHAMPION if include_champion else None,
            "gates": {"ECONOMIC_VALUE_GATE": {"pass": True}},
        },
    }
    (tmp_path / "control" / "auto_promotion_status.json").write_text(json.dumps(auto), encoding="utf-8")
    (tmp_path / "control" / "promotion_status.json").write_text(
        json.dumps(
            {
                "automation_modes": {"AUTO_RESEARCH": "DISABLED"},
                "all_gates_pass": False,
                "gates": {"ECONOMIC_VALUE_GATE": {"pass": False}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control" / "system_health.json").write_text(
        json.dumps({"operational_health": "OK"}), encoding="utf-8"
    )
    lkg = {"validated_variant_id": LOCKED_CHAMPION} if include_champion else {}
    (tmp_path / "control" / "last_known_good_state.json").write_text(json.dumps(lkg), encoding="utf-8")
    save_manifest(tmp_path, build_initial_mom_manifest(tmp_path))
    ev = tmp_path / "control" / "evidence"
    ev.mkdir(parents=True)
    evidence_payload = {
        "current_evidence_stage": "BACKTESTED",
        "source_classification": "PREEXISTING_UNREVIEWED",
        "promotion_eligible": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "current_active_blockers": [
            "CHALLENGER_TURNOVER_NOT_VERIFIED",
            "DSR_BELOW_REQUIRED_CONFIDENCE",
            "P9_NOT_EXTERNALLY_REVIEWED",
        ],
    }
    if include_champion:
        evidence_payload["champion_variant_id"] = LOCKED_CHAMPION
    (ev / "current_evidence_status.json").write_text(json.dumps(evidence_payload), encoding="utf-8")
    (ev / "cost_stress_status.json").write_text(
        json.dumps(
            {
                "COST_STRESS_GATE": {
                    "pass": False,
                    "evaluation_status": "NOT_EVALUABLE",
                    "blockers": ["CHALLENGER_TURNOVER_NOT_VERIFIED"],
                },
                "sensitivity_analysis": {"label": "NOT_GATE_EVIDENCE"},
            }
        ),
        encoding="utf-8",
    )
    (ev / "robustness_status.json").write_text(
        json.dumps(
            {
                "SUBPERIOD_STABILITY_SCREEN": {"pass": True},
                "ROBUSTNESS_EVIDENCE": {"pass": False, "status": "PARTIAL_ONLY"},
            }
        ),
        encoding="utf-8",
    )
    (ev / "multiple_testing_status.json").write_text(
        json.dumps(
            {
                "MULTIPLE_TESTING_EVIDENCE": {"pass": False, "status": "FAIL"},
                "deflated_sharpe": {"dsr_probability": 0.841, "dsr_required_probability": 0.95, "status": "FAIL"},
                "PBO_STATUS": "NOT_EVALUABLE",
            }
        ),
        encoding="utf-8",
    )
    (ev / "forward_monitoring_readiness_status.json").write_text(
        json.dumps({"activation_status": "BLOCKED", "observation_type": "FORWARD_MONITORING"}),
        encoding="utf-8",
    )
    (ev / "shadow_monitor_status.json").write_text(json.dumps(_shadow_monitor_payload()), encoding="utf-8")
    (ev / "paper_monitor_status.json").write_text(json.dumps(_paper_monitor_payload()), encoding="utf-8")
    (ev / "forward_monitoring_data_requirements.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    if include_champion:
        (tmp_path / "model_output_sp500_pit_t212" / "latest_validated_run.json").write_text(
            json.dumps({"variant_id": LOCKED_CHAMPION}), encoding="utf-8"
        )
    (tmp_path / "control" / "vision_automation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control" / "vision_automation" / "automation_state.json").write_text(
        json.dumps(
            {
                "current_executed_phase": "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
                "expected_next_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
                "authorized_phase": "",
                "current_running_phase": "",
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "next_phase_authorized": False,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "hooks.json").write_text('{"version": 1, "hooks": {}}', encoding="utf-8")
    return tmp_path


def test_viewmodel_backtested_stage(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    assert data["executive_overview"]["evidence_stage"] == "BACKTESTED"
    assert data["executive_overview"]["promotion_eligible_display"] == "NO"
    assert data["executive_overview"]["active_champion"] == LOCKED_CHAMPION
    assert data["executive_overview"]["candidate"] == "MOM_63_TOP12"


def test_champion_missing_evidence_source(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "control" / "evidence" / "current_evidence_status.json").unlink()
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["active_champion"] == "UNKNOWN"


def test_champion_missing_lkg_source(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "control" / "last_known_good_state.json").unlink()
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["active_champion"] == "UNKNOWN"


def test_champion_missing_auto_source(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "control" / "auto_promotion_status.json").unlink()
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["active_champion"] == "UNKNOWN"


def test_champion_missing_validated_run_source(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "model_output_sp500_pit_t212" / "latest_validated_run.json").unlink()
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["active_champion"] == "UNKNOWN"


def test_champion_missing_field_in_source(tmp_path: Path):
    root = _fixture_root(tmp_path)
    payload = json.loads((root / "control" / "evidence" / "current_evidence_status.json").read_text())
    payload.pop("champion_variant_id")
    (root / "control" / "evidence" / "current_evidence_status.json").write_text(json.dumps(payload), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["active_champion"] == "UNKNOWN"


def test_champion_conflict_shows_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "control" / "last_known_good_state.json").write_text(
        json.dumps({"validated_variant_id": "OTHER_VARIANT"}), encoding="utf-8"
    )
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["active_champion"] == "UNKNOWN"


def test_four_consistent_champion_sources(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    assert data["executive_overview"]["active_champion"] == LOCKED_CHAMPION
    assert data["source_health"]["champion_source_policy"]


def test_auto_promote_paper_enabled_blocks_safety(tmp_path: Path):
    root = _fixture_root(tmp_path)
    cfg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text())
    cfg["auto_promote_paper_enabled"] = True
    (root / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["automation_blocked_for_safety"] is True
    assert data["source_health"]["fail_closed"] is True
    assert "UNSAFE OR UNVERIFIED AUTOMATION CONFIGURATION" in data["safety_automation"]["safety_warnings"]


def test_auto_execute_real_money_enabled_blocks_safety(tmp_path: Path):
    root = _fixture_root(tmp_path)
    cfg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text())
    cfg["auto_execute_real_money_enabled"] = True
    (root / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["automation_blocked_for_safety"] is True
    assert data["source_health"]["blocked_for_safety"] is True


def test_missing_automation_flag_unknown_blocks_safety(tmp_path: Path):
    root = _fixture_root(tmp_path)
    cfg = yaml.safe_load((root / "promotion_gate_config.yaml").read_text())
    cfg.pop("auto_research_enabled", None)
    (root / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["AUTO_RESEARCH"] == "UNKNOWN"
    assert data["safety_automation"]["automation_blocked_for_safety"] is True


def test_all_automation_disabled_no_automation_block(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    assert data["safety_automation"]["AUTO_RESEARCH"] == "DISABLED"
    assert data["safety_automation"]["automation_blocked_for_safety"] is False


def test_empty_hooks_disabled(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    assert data["safety_automation"]["hooks_status"] == "DISABLED"
    assert data["safety_automation"]["hooks_blocked_for_safety"] is False


def test_active_hooks_block_safety(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text(
        json.dumps({"version": 1, "hooks": {"afterFileEdit": [{"command": "echo test"}]}}),
        encoding="utf-8",
    )
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "ACTIVE"
    assert data["safety_automation"]["hooks_blocked_for_safety"] is True
    assert "CURSOR HOOKS ACTIVE OR UNVERIFIED" in data["safety_automation"]["safety_warnings"]


def test_unparseable_hooks_block_safety(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text("{not-json", encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "UNKNOWN"
    assert data["safety_automation"]["hooks_blocked_for_safety"] is True


def test_empty_shadow_monitor_unknown_not_false(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "control" / "evidence" / "shadow_monitor_status.json").write_text("{}", encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["monitoring"]["shadow"]["evidence_missing"] is True
    assert data["monitoring"]["shadow"]["shadow_collection_started"] is None


def test_shadow_missing_required_field_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    payload = _shadow_monitor_payload()
    payload.pop("shadow_collection_started")
    (root / "control" / "evidence" / "shadow_monitor_status.json").write_text(json.dumps(payload), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["monitoring"]["shadow"]["evidence_missing"] is True
    assert data["monitoring"]["shadow"]["shadow_collection_started"] is None


def test_paper_missing_required_field_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    payload = _paper_monitor_payload()
    payload.pop("paper_simulation_started")
    (root / "control" / "evidence" / "paper_monitor_status.json").write_text(json.dumps(payload), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["monitoring"]["paper"]["evidence_missing"] is True
    assert data["monitoring"]["paper"]["paper_simulation_started"] is None


def test_complete_blocked_monitoring_shows_false(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    assert data["monitoring"]["shadow"]["shadow_collection_started"] is False
    assert data["monitoring"]["paper"]["paper_simulation_started"] is False


def test_manifest_missing_candidate_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    manifest_path = root / "control" / "experiments" / "EXP_INITIAL_MOM_63_TOP12.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest.pop("candidate_variant")
    manifest_path.write_text(yaml.dump(manifest), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["candidate"] == "UNKNOWN"
    assert data["executive_overview"]["manifest_blocked_for_safety"] is True


def test_missing_evidence_stage_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "control" / "evidence" / "current_evidence_status.json").unlink()
    data = load_decision_cockpit(root)
    assert data["executive_overview"]["evidence_stage"] == "UNKNOWN"


def test_source_conflicts_visible(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    assert any("ECONOMIC_VALUE_GATE" in c for c in data["why_not_promoted"]["source_conflicts"])


def test_export_blocked_under_control(tmp_path: Path):
    root = _fixture_root(tmp_path)
    with pytest.raises(ValueError, match="export_path_blocked"):
        export_decision_cockpit_json(root, root / "control" / "evidence")


def test_validate_export_allows_external_dir(tmp_path: Path):
    root = _fixture_root(tmp_path)
    ok, reason = validate_export_directory(root, tmp_path / "exports")
    assert ok
    assert reason == ""


def test_hooks_valid_empty_schema_disabled(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    assert data["safety_automation"]["hooks_status"] == "DISABLED"
    assert data["safety_automation"]["hooks_blocked_for_safety"] is False


def test_hooks_missing_file_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").unlink()
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "UNKNOWN"
    assert data["source_health"]["fail_closed"] is True


def test_hooks_empty_object_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text("{}", encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "UNKNOWN"
    assert data["safety_automation"]["hooks_blocked_for_safety"] is True


def test_hooks_null_hooks_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text('{"version": 1, "hooks": null}', encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "UNKNOWN"


def test_hooks_list_hooks_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text('{"version": 1, "hooks": []}', encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "UNKNOWN"


def test_hooks_wrong_version_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text('{"version": "1", "hooks": {}}', encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "UNKNOWN"


def test_hooks_active_nonempty_blocked(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / ".cursor" / "hooks.json").write_text(
        json.dumps({"version": 1, "hooks": {"afterFileEdit": [{"command": "echo"}]}}),
        encoding="utf-8",
    )
    data = load_decision_cockpit(root)
    assert data["safety_automation"]["hooks_status"] == "ACTIVE"
    assert data["source_health"]["blocked_for_safety"] is True


def test_controller_state_dynamic(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    ctrl = data["controller_state"]
    assert ctrl["current_executed_phase"] == "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE"
    assert ctrl["expected_next_phase"] == "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
    assert ctrl["execution_status"] == "AWAITING_EXTERNAL_REVIEW"
    assert ctrl["next_phase_authorized_display"] == "NO"
    assert "AWAITING V5 AUTHORIZATION" in ctrl.get("lifecycle_message", "")


def test_controller_missing_unknown(tmp_path: Path):
    root = _fixture_root(tmp_path)
    (root / "control" / "vision_automation" / "automation_state.json").unlink()
    data = load_decision_cockpit(root)
    assert data["controller_state"]["display"] == "UNKNOWN — BLOCKED FOR SAFETY"


def test_controller_next_phase_authorized_true_blocks(tmp_path: Path):
    root = _fixture_root(tmp_path)
    state = json.loads((root / "control" / "vision_automation" / "automation_state.json").read_text())
    state["next_phase_authorized"] = True
    (root / "control" / "vision_automation" / "automation_state.json").write_text(json.dumps(state), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["controller_state"]["blocked_for_safety"] is True


def test_experiment_panel_full_manifest(tmp_path: Path):
    data = load_decision_cockpit(_fixture_root(tmp_path))
    exp = data["experiment_registry"]
    assert exp["blocked_for_safety"] is False
    assert exp["candidate"] == "MOM_63_TOP12"
    assert exp["status"] == "RESEARCH_ONLY"


def test_experiment_missing_decision_status_blocks(tmp_path: Path):
    root = _fixture_root(tmp_path)
    path = root / "control" / "experiments" / "EXP_INITIAL_MOM_63_TOP12.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest.pop("decision_status")
    path.write_text(yaml.dump(manifest), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["experiment_registry"]["blocked_for_safety"] is True
    assert "UNKNOWN" in data["experiment_registry"]["display"]


def test_experiment_wrong_candidate_blocks(tmp_path: Path):
    root = _fixture_root(tmp_path)
    path = root / "control" / "experiments" / "EXP_INITIAL_MOM_63_TOP12.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["candidate_variant"] = "OTHER"
    path.write_text(yaml.dump(manifest), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["experiment_registry"]["blocked_for_safety"] is True


def test_experiment_wrong_champion_reference_blocks(tmp_path: Path):
    root = _fixture_root(tmp_path)
    path = root / "control" / "experiments" / "EXP_INITIAL_MOM_63_TOP12.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["champion_reference"] = "OTHER"
    path.write_text(yaml.dump(manifest), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["experiment_registry"]["blocked_for_safety"] is True


def test_experiment_wrong_evidence_stage_blocks(tmp_path: Path):
    root = _fixture_root(tmp_path)
    path = root / "control" / "experiments" / "EXP_INITIAL_MOM_63_TOP12.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["current_evidence_stage"] = "FORWARD_READY"
    path.write_text(yaml.dump(manifest), encoding="utf-8")
    data = load_decision_cockpit(root)
    assert data["experiment_registry"]["blocked_for_safety"] is True


def _write_automation(root: Path, payload: dict) -> None:
    path = root / "control" / "vision_automation" / "automation_state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_v5_build_in_progress_lifecycle(tmp_path: Path):
    root = _fixture_root(tmp_path)
    _write_automation(
        root,
        {
            "current_executed_phase": "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
            "expected_next_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
            "authorized_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
            "current_running_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
            "execution_status": "RUNNING_AUTHORIZED_PHASE",
            "next_phase_authorized": False,
        },
    )
    msg = load_decision_cockpit(root)["controller_state"]["lifecycle_message"]
    assert "V5 BUILD IN PROGRESS" in msg


def test_v5_build_complete_lifecycle(tmp_path: Path):
    root = _fixture_root(tmp_path)
    _write_automation(
        root,
        {
            "current_executed_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
            "expected_next_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "authorized_phase": "",
            "current_running_phase": "",
            "execution_status": "AWAITING_EXTERNAL_REVIEW",
            "next_phase_authorized": False,
        },
    )
    msg = load_decision_cockpit(root)["controller_state"]["lifecycle_message"]
    assert "EXE BUILD COMPLETE" in msg
    assert "NO LIVE TRADING" in msg


def test_terminal_complete_lifecycle(tmp_path: Path):
    root = _fixture_root(tmp_path)
    _write_automation(
        root,
        {
            "current_executed_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "expected_next_phase": "",
            "authorized_phase": "",
            "current_running_phase": "",
            "execution_status": "AWAITING_EXTERNAL_REVIEW",
            "next_phase_authorized": False,
        },
    )
    msg = load_decision_cockpit(root)["controller_state"]["lifecycle_message"]
    assert "DECISION COCKPIT AVAILABLE FOR MANUAL REVIEW" in msg


def test_terminal_complete_lifecycle_none_expected_next(tmp_path: Path):
    root = _fixture_root(tmp_path)
    _write_automation(
        root,
        {
            "current_executed_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "expected_next_phase": "NONE",
            "authorized_phase": "",
            "current_running_phase": "",
            "execution_status": "AWAITING_EXTERNAL_REVIEW",
            "next_phase_authorized": False,
        },
    )
    state = load_decision_cockpit(root)["controller_state"]
    assert state["blocked_for_safety"] is False
    assert "DECISION COCKPIT AVAILABLE FOR MANUAL REVIEW" in state["lifecycle_message"]


def test_unsafe_controller_next_auth_true(tmp_path: Path):
    root = _fixture_root(tmp_path)
    _write_automation(
        root,
        {
            "current_executed_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
            "expected_next_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "authorized_phase": "",
            "current_running_phase": "",
            "execution_status": "AWAITING_EXTERNAL_REVIEW",
            "next_phase_authorized": True,
        },
    )
    ctrl = load_decision_cockpit(root)["controller_state"]
    assert ctrl["blocked_for_safety"] is True
    assert "CONTROLLER STATE UNKNOWN OR UNSAFE" in ctrl["lifecycle_message"]
