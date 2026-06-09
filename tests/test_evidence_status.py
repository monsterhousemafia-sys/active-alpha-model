"""Tests for aa_evidence_status."""
from __future__ import annotations

from aa_doc_paths import doc_path, doc_rel

import json
from pathlib import Path

import yaml

from aa_evidence_status import build_evidence_status, export_evidence_status
from aa_evidence_schema import LOCKED_CHAMPION
from aa_experiment_registry import build_initial_mom_manifest, save_manifest


def _write_config(root: Path, **overrides) -> None:
    cfg = {
        "auto_research_enabled": False,
        "auto_promote_paper_enabled": False,
        "auto_promote_signal_enabled": False,
        "auto_execute_real_money_enabled": False,
    }
    cfg.update(overrides)
    (root / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")


def _write_status_files(root: Path, *, auto=None, promo=None, health=None, lkg=None) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    auto = auto or {
        "champion_variant_id": LOCKED_CHAMPION,
        "promotion_allowed": False,
        "auto_execute_real_money_enabled": False,
        "automation_modes": {
            "AUTO_RESEARCH": "DISABLED",
            "AUTO_PROMOTE_PAPER": "DISABLED",
            "AUTO_PROMOTE_SIGNAL": "DISABLED",
            "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
        },
        "gate_evaluation": {
            "promotion_allowed": False,
            "champion_variant_id": LOCKED_CHAMPION,
            "gates": {
                "COST_STRESS_GATE": {"pass": None},
                "ECONOMIC_VALUE_GATE": {"pass": True},
                "RISK_GATE": {"pass": True},
                "DATA_QUALITY_GATE": {"pass": True},
            },
        },
    }
    promo = promo or {
        "all_gates_pass": False,
        "auto_execute_real_money": False,
        "automation_modes": {
            "AUTO_RESEARCH": "DISABLED",
            "AUTO_PROMOTE_PAPER": "DISABLED",
            "AUTO_PROMOTE_SIGNAL": "DISABLED",
            "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
        },
        "gates": {"COST_STRESS_GATE": {"pass": None}, "ECONOMIC_VALUE_GATE": {"pass": False}},
    }
    health = health or {"operational_health": "OK", "critical_errors": []}
    lkg = lkg or {"validated_variant_id": LOCKED_CHAMPION, "variant_id": LOCKED_CHAMPION}
    (root / "control" / "auto_promotion_status.json").write_text(json.dumps(auto), encoding="utf-8")
    (root / "control" / "promotion_status.json").write_text(json.dumps(promo), encoding="utf-8")
    (root / "control" / "system_health.json").write_text(json.dumps(health), encoding="utf-8")
    (root / "control" / "last_known_good_state.json").write_text(json.dumps(lkg), encoding="utf-8")
    p9 = root / doc_rel("P9_EXTERNAL_REVIEW_STATUS.md")
    p9.parent.mkdir(parents=True, exist_ok=True)
    p9.write_text("PREEXISTING_UNREVIEWED_PASS\n", encoding="utf-8")


def _fixture_with_manifest(tmp_path: Path) -> Path:
    _write_config(tmp_path)
    _write_status_files(tmp_path)
    save_manifest(tmp_path, build_initial_mom_manifest(tmp_path))
    return tmp_path


def test_build_does_not_write_or_create_manifest(tmp_path: Path):
    root = tmp_path
    _write_config(root)
    _write_status_files(root)
    build_evidence_status(root)
    assert not (root / "control" / "experiments").exists()


def test_missing_manifest_yields_idea_not_available(tmp_path: Path):
    _write_config(tmp_path)
    _write_status_files(tmp_path)
    status = build_evidence_status(tmp_path)
    assert status["current_evidence_stage"] == "IDEA"
    assert status["source_classification"] == "NOT_AVAILABLE"


def test_missing_provenance_file_yields_idea(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    manifest = build_initial_mom_manifest(root)
    manifest["provenance"]["source_files"] = ["missing/file.json"]
    save_manifest(root, manifest, allow_overwrite=True)
    status = build_evidence_status(root)
    assert status["current_evidence_stage"] == "IDEA"
    assert "EVIDENCE_PROVENANCE_MISSING" in status["blockers"]


def test_provenance_hash_mismatch_yields_idea(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    from aa_experiment_registry import INITIAL_EXPERIMENT_ID, load_manifest, save_manifest

    manifest = load_manifest(root, INITIAL_EXPERIMENT_ID)
    rel = "control/auto_promotion_status.json"
    manifest["provenance"]["source_hashes"][rel] = "0" * 64
    save_manifest(root, manifest, allow_overwrite=True)
    status = build_evidence_status(root)
    assert status["current_evidence_stage"] == "IDEA"
    assert "EVIDENCE_PROVENANCE_HASH_MISMATCH" in status["blockers"]


def test_missing_champion_evidence_null_champion(tmp_path: Path):
    _write_config(tmp_path)
    _write_status_files(
        tmp_path,
        auto={"gate_evaluation": {"gates": {}}},
        lkg={},
    )
    save_manifest(tmp_path, build_initial_mom_manifest(tmp_path))
    status = build_evidence_status(tmp_path)
    assert status["champion_variant_id"] is None
    assert "CHAMPION_EVIDENCE_MISSING" in status["blockers"]


def test_config_status_automation_conflict_detected(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    _write_config(root, auto_research_enabled=True)
    status = build_evidence_status(root)
    assert any("automation_mode:AUTO_RESEARCH" in c for c in status["source_conflicts"])


def test_stale_disabled_cannot_mask_enabled_config(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    cfg_path = root / "promotion_gate_config.yaml"
    cfg_path.write_text(yaml.dump({"auto_research_enabled": True}), encoding="utf-8")
    status = build_evidence_status(root)
    assert status["automation_modes"]["AUTO_RESEARCH"] == "ENABLED"
    assert any("UNSAFE_AUTOMATION_CONFIGURATION" in b for b in status["blockers"])


def test_missing_config_shows_unknown_not_disabled(tmp_path: Path):
    root = tmp_path
    (root / "control").mkdir()
    _write_status_files(root)
    save_manifest(root, build_initial_mom_manifest(root))
    status = build_evidence_status(root)
    assert status["automation_modes"]["AUTO_RESEARCH"] == "UNKNOWN"
    assert "AUTOMATION_CONFIG_MISSING_OR_INCOMPLETE" in status["blockers"]


def test_missing_provenance_display_message(tmp_path: Path):
    _write_config(tmp_path)
    _write_status_files(tmp_path)
    status = build_evidence_status(tmp_path)
    assert "Evidence is missing or not verified." in status["display_messages"][0]


def test_system_health_ok_when_operational_ok(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    status = build_evidence_status(root)
    assert status["gate_summary"]["system_health_ok"] is True


def test_system_health_blocks_when_missing(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    (root / "control" / "system_health.json").write_text("{}", encoding="utf-8")
    status = build_evidence_status(root)
    assert "SYSTEM_HEALTH_NOT_CONFIRMED" in status["blockers"]


def test_export_writes_only_evidence_file(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    lkg = root / "control" / "last_known_good_state.json"
    before = lkg.read_bytes()
    export_evidence_status(root)
    assert lkg.read_bytes() == before
    assert (root / "control" / "evidence" / "current_evidence_status.json").is_file()


def test_historical_and_current_blockers_separated(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    from aa_experiment_registry import INITIAL_EXPERIMENT_ID, load_manifest, save_manifest

    manifest = load_manifest(root, INITIAL_EXPERIMENT_ID)
    manifest["blockers"] = ["COST_STRESS_NOT_EVALUATED", "P9_NOT_EXTERNALLY_REVIEWED"]
    save_manifest(root, manifest, allow_overwrite=True)
    ev_dir = root / "control" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "cost_stress_status.json").write_text(
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
    status = build_evidence_status(root)
    assert "historical_manifest_blockers" in status
    assert "current_active_blockers" in status
    assert "resolved_or_superseded_blockers" in status
    assert "COST_STRESS_NOT_EVALUATED" in status["resolved_or_superseded_blockers"]
    assert "CHALLENGER_TURNOVER_NOT_VERIFIED" in status["current_active_blockers"]
    assert "COST_STRESS_NOT_EVALUATED" not in status["current_active_blockers"]


def test_no_contradiction_cost_pass_with_not_evaluated_blocker(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    ev_dir = root / "control" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "cost_stress_status.json").write_text(
        json.dumps({"COST_STRESS_GATE": {"pass": True, "evaluation_status": "PASS", "blockers": []}}),
        encoding="utf-8",
    )
    (ev_dir / "robustness_status.json").write_text(
        json.dumps({"ROBUSTNESS_EVIDENCE": {"pass": False, "status": "PARTIAL_ONLY"}}),
        encoding="utf-8",
    )
    (ev_dir / "multiple_testing_status.json").write_text(
        json.dumps({"MULTIPLE_TESTING_EVIDENCE": {"pass": False, "status": "NOT_EVALUABLE"}}),
        encoding="utf-8",
    )
    status = build_evidence_status(root)
    assert "COST_STRESS_NOT_EVALUATED" not in status["current_active_blockers"]


def test_invalid_v2_evidence_keeps_stage_backtested(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    ev_dir = root / "control" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / "cost_stress_status.json").write_text(
        json.dumps({"COST_STRESS_GATE": {"pass": False, "evaluation_status": "NOT_EVALUABLE"}}),
        encoding="utf-8",
    )
    status = build_evidence_status(root)
    assert status["current_evidence_stage"] == "BACKTESTED"
    assert status["promotion_eligible"] is False
    assert status["paper_eligible"] is False
    assert status["real_money_eligible"] is False


def test_p9_blocker_remains_visible(tmp_path: Path):
    root = _fixture_with_manifest(tmp_path)
    status = build_evidence_status(root)
    assert "P9_NOT_EXTERNALLY_REVIEWED" in status["current_active_blockers"] or any(
        "P9" in b for b in status["current_active_blockers"]
    )
