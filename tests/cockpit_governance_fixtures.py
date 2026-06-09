"""Shared fail-closed cockpit / authorization test fixtures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aa_evidence_schema import LOCKED_CHAMPION
from aa_experiment_registry import build_initial_mom_manifest, save_manifest

FINAL_APPROVAL_FIXTURE_TEXT = "\n".join(
    [
        "# External Review Approval — Final",
        "No operational authorization is granted by this approval.",
        "## Explicitly not authorized",
        "- Real-money execution",
    ]
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_final_approval_and_registry(root: Path) -> None:
    path = root / "EXTERNAL_REVIEW_APPROVAL_FINAL.md"
    path.write_text(FINAL_APPROVAL_FIXTURE_TEXT, encoding="utf-8")
    final_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    reg_dir = root / "control" / "vision_automation" / "review_registry"
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / "review_registry.json").write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "approval_file": "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
                        "approval_sha256": final_hash,
                        "phase_id": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
                        "external_sealed": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def build_g0_conflict_root(tmp_path: Path) -> Path:
    """Repo with deliberate authorization source conflict (G0 negative tests)."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "EXTERNAL_REVIEW_APPROVAL_FINAL.md").write_text(
        "\n".join(
            [
                "# External Review Approval — Final",
                "V5R is approved for transition to COMPLETE_AWAITING_OPERATIONAL_DECISION.",
                "No operational authorization is granted by this approval.",
                "## Explicitly not authorized",
                "- Shadow monitoring activation",
                "- Paper monitoring activation",
                "- Promotion execution",
                "- Real-money execution",
                "- Champion change",
            ]
        ),
        encoding="utf-8",
    )
    write_json(
        root / "VISION_PROGRESS.json",
        {
            "current_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "operational_authorization": "FULL_USER_APPROVED",
            "safety_flags": {
                "REAL_MONEY_AUTHORIZED": "YES",
                "PROMOTION_AUTHORIZED": "YES",
                "PAPER_MONITORING_ACTIVATED": "YES",
                "SHADOW_MONITORING_ACTIVATED": "YES",
                "CHAMPION_CHANGE_AUTHORIZED": "YES",
            },
        },
    )
    write_json(
        root / "control" / "operational_safety_flags.json",
        {"REAL_MONEY_AUTHORIZED": True, "AUTO_EXECUTE_REAL_MONEY": "ENABLED"},
    )
    write_json(
        root / "control" / "vision_automation" / "automation_state.json",
        {
            "current_executed_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "expected_next_phase": "NONE",
            "execution_status": "AWAITING_EXTERNAL_REVIEW",
            "next_phase_authorized": False,
            "operational_authorization": "FULL_USER_APPROVED",
        },
    )
    write_json(
        root / "control" / "vision_automation" / "review_registry" / "review_registry.json",
        {"reviews": []},
    )
    _write_minimal_cockpit_sources(root)
    return root


def build_clean_terminal_root(tmp_path: Path) -> Path:
    """Terminal read-only state without authorization conflicts."""
    root = tmp_path / "repo"
    root.mkdir()
    write_final_approval_and_registry(root)
    write_json(
        root / "VISION_PROGRESS.json",
        {
            "current_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "operational_authorization": "NONE",
            "informational_only": True,
            "safety_flags": {
                "REAL_MONEY_AUTHORIZED": "NO",
                "PROMOTION_AUTHORIZED": "NO",
                "PAPER_MONITORING_ACTIVATED": "NO",
                "SHADOW_MONITORING_ACTIVATED": "NO",
                "CHAMPION_CHANGE_AUTHORIZED": "NO",
            },
        },
    )
    write_json(
        root / "control" / "operational_safety_flags.json",
        {
            "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
            "REAL_MONEY_AUTHORIZED": "NO",
            "PROMOTION_AUTHORIZED": "NO",
        },
    )
    write_json(
        root / "control" / "vision_automation" / "automation_state.json",
        {
            "current_executed_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "expected_next_phase": "NONE",
            "authorized_phase": "",
            "current_running_phase": "",
            "execution_status": "AWAITING_EXTERNAL_REVIEW",
            "next_phase_authorized": False,
            "operational_authorization": "NONE",
        },
    )
    _write_minimal_cockpit_sources(root)
    return root


def _write_minimal_cockpit_sources(root: Path) -> None:
    save_manifest(root, build_initial_mom_manifest(root))
    write_json(root / "promotion_gate_config.yaml", {"auto_execute_real_money_enabled": False})
    write_json(root / "control" / "system_health.json", {"operational_health": "OK"})
    write_json(
        root / "control" / "last_known_good_state.json",
        {"validated_variant_id": LOCKED_CHAMPION},
    )
    write_json(
        root / "control" / "evidence" / "current_evidence_status.json",
        {
            "current_evidence_stage": "BACKTESTED",
            "source_classification": "RESEARCH",
            "champion_variant_id": LOCKED_CHAMPION,
            "promotion_eligible": False,
            "paper_eligible": False,
            "real_money_eligible": False,
            "blockers": ["P9_NOT_EXTERNALLY_REVIEWED"],
        },
    )
    write_json(
        root / "control" / "auto_promotion_status.json",
        {
            "champion_variant_id": LOCKED_CHAMPION,
            "gate_evaluation": {"champion_variant_id": LOCKED_CHAMPION},
        },
    )
    write_json(
        root / "model_output_sp500_pit_t212" / "latest_validated_run.json",
        {"variant_id": LOCKED_CHAMPION},
    )
    for name in (
        "cost_stress_status.json",
        "robustness_status.json",
        "multiple_testing_status.json",
        "forward_monitoring_readiness_status.json",
        "shadow_monitor_status.json",
        "paper_monitor_status.json",
    ):
        write_json(root / "control" / "evidence" / name, {"activation_status": "NOT_ACTIVATED"})
    write_json(root / "control" / "promotion_status.json", {"status": "BLOCKED"})
    write_json(root / ".cursor" / "hooks.json", {"version": 1, "hooks": {}})
    write_json(
        root / "control" / "evidence" / "forward_monitoring_data_requirements.json",
        {"schema_version": 1},
    )
