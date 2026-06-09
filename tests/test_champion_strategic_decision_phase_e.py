"""Phase E strategic champion decision tests."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from aa_champion_strategic_decision import apply_strategic_decision, evaluate_strategic_options
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tools.run_champion_evidence_phase_e import run_phase_e


def test_phase_e_selects_retain_r3(tmp_path: Path) -> None:
    root = tmp_path
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "control" / "champion_change_criteria.yaml").write_text(
        yaml.dump({"authoritative_champion": AUTHORITATIVE_CHAMPION, "auto_promotion_allowed": False}),
        encoding="utf-8",
    )
    (root / "evidence" / "canonical_model_comparison.json").write_text(
        json.dumps(
            {
                "headline": {
                    "matrix_embedded_sharpe_leader": "R0_LEGACY_ENSEMBLE",
                    "champion_sharpe_rank_matrix": 4,
                    "champion_is_sharpe_leader": False,
                },
                "rankings": {
                    "sharpe_matrix_embedded": [
                        {"variant_id": "R0_LEGACY_ENSEMBLE", "sharpe_0rf": 0.98, "rank": 1},
                        {"variant_id": AUTHORITATIVE_CHAMPION, "sharpe_0rf": 0.92, "rank": 4},
                    ]
                },
                "variants": [{"variant_id": AUTHORITATIVE_CHAMPION, "metrics": {"sharpe_0rf": 0.92}}],
            }
        ),
        encoding="utf-8",
    )
    decision = evaluate_strategic_options(root)
    assert decision["selected_option"] == "E1_RETAIN_R3"
    assert decision["champion_variant_after_decision"] == AUTHORITATIVE_CHAMPION
    assert decision["champion_change_executed"] is False
    e2 = next(o for o in decision["options"] if o["option_id"] == "E2_SWITCH_M1")
    assert e2["recommended"] is False


def test_e1_apply_reaffirms_r3(tmp_path: Path) -> None:
    root = tmp_path
    (root / "control").mkdir(parents=True)
    (root / "model_output_sp500_pit_t212").mkdir(parents=True)
    (root / "evidence").mkdir(parents=True)
    (root / "control" / "champion_change_criteria.yaml").write_text(
        yaml.dump({"authoritative_champion": AUTHORITATIVE_CHAMPION}),
        encoding="utf-8",
    )
    (root / "evidence" / "canonical_model_comparison.json").write_text(
        json.dumps({"headline": {}, "rankings": {}, "variants": []}),
        encoding="utf-8",
    )
    decision = evaluate_strategic_options(root)
    result = apply_strategic_decision(root, decision)
    assert result.get("applied") is True
    assert result.get("option") == "E1_RETAIN_R3"
    assert (root / "control" / "champion_operational_status.json").is_file()
    assert (root / "control" / "champion_rejected_alternatives.json").is_file()


def test_phase_e_tool_writes_artifacts(tmp_path: Path) -> None:
    root = tmp_path
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "control" / "champion_change_criteria.yaml").write_text(
        yaml.dump({"authoritative_champion": AUTHORITATIVE_CHAMPION}),
        encoding="utf-8",
    )
    (root / "evidence" / "canonical_model_comparison.json").write_text("{}", encoding="utf-8")
    out = run_phase_e(root)
    assert out["status"] in {"COMPLETE", "COMPLETE_WITH_WARNINGS"}
    assert out.get("e1_operational_applied") is True
    assert (root / "control" / "champion_strategic_decision.json").is_file()
    assert (root / "docs" / "CHAMPION_STRATEGIC_DECISION_RECORD.md").is_file() is False
    assert (root / "evidence" / "phase_e_strategic_decision_summary.json").is_file()


def test_adr_present_in_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "docs" / "CHAMPION_STRATEGIC_DECISION_RECORD.md").is_file()
