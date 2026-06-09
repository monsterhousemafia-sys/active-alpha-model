"""Phase D champion governance tests."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from aa_champion_governance import build_champion_governance_de, load_champion_change_criteria
from aa_decision_cockpit_gui import build_cockpit_tab_labels
from aa_decision_cockpit_viewmodel import load_decision_cockpit
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tools.run_champion_evidence_phase_d import run_phase_d


def test_charter_and_criteria_present() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "control" / "champion_decision_charter.md").is_file()
    crit, st = load_champion_change_criteria(root)
    assert st == "OK"
    assert crit.get("authoritative_champion") == AUTHORITATIVE_CHAMPION
    assert crit.get("auto_promotion_allowed") is False


def test_governance_panel_from_canonical(tmp_path: Path) -> None:
    root = tmp_path
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "control" / "champion_change_criteria.yaml").write_text(
        yaml.dump({"authoritative_champion": AUTHORITATIVE_CHAMPION, "auto_promotion_allowed": False}),
        encoding="utf-8",
    )
    (root / "control" / "champion_decision_charter.md").write_text("# charter\n", encoding="utf-8")
    (root / "evidence" / "canonical_model_comparison.json").write_text(
        json.dumps(
            {
                "headline": {
                    "champion_is_sharpe_leader": False,
                    "champion_sharpe_rank_matrix": 4,
                    "matrix_embedded_sharpe_leader": "R0_LEGACY_ENSEMBLE",
                },
                "rankings": {
                    "sharpe_matrix_embedded": [
                        {"rank": 1, "variant_id": "R0_LEGACY_ENSEMBLE", "sharpe_0rf": 0.98},
                        {"rank": 4, "variant_id": AUTHORITATIVE_CHAMPION, "sharpe_0rf": 0.92},
                    ]
                },
                "variants": [
                    {
                        "variant_id": AUTHORITATIVE_CHAMPION,
                        "metrics": {"sharpe_0rf": 0.92},
                    },
                    {
                        "variant_id": "M1_MOM_BLEND_MATCHED_CONTROLS",
                        "metrics": {"sharpe_0rf": 0.98},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    panel = build_champion_governance_de(root)
    assert panel["approval_status_de"] == "Freigegeben"
    assert panel["is_highest_backtest_sharpe"] is False
    assert panel["matrix_sharpe_rank"] == 4
    assert panel["m1_sharpe_delta"] is not None and panel["m1_sharpe_delta"] > 0
    assert any("nicht höchster Sharpe" in line for line in panel["lines_de"])


def test_phase_d_tool_complete(tmp_path: Path) -> None:
    root = tmp_path
    (root / "control").mkdir()
    (root / "control" / "champion_decision_charter.md").write_text("# c\n", encoding="utf-8")
    (root / "control" / "champion_change_criteria.yaml").write_text(
        yaml.dump({"authoritative_champion": AUTHORITATIVE_CHAMPION}),
        encoding="utf-8",
    )
    (root / "evidence").mkdir()
    (root / "evidence" / "canonical_model_comparison.json").write_text("{}", encoding="utf-8")
    summary = run_phase_d(root)
    assert summary["status"] == "COMPLETE"
    assert (root / "evidence" / "phase_d_governance_summary.json").is_file()


def test_viewmodel_includes_champion_governance_de(tmp_path: Path) -> None:
    from tests.test_decision_cockpit_viewmodel import _fixture_root

    root = _fixture_root(tmp_path)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "canonical_model_comparison.json").write_text(
        json.dumps(
            {
                "headline": {"champion_is_sharpe_leader": False, "champion_sharpe_rank_matrix": 3},
                "rankings": {"sharpe_matrix_embedded": []},
                "variants": [],
            }
        ),
        encoding="utf-8",
    )
    data = load_decision_cockpit(root)
    gov = data.get("champion_governance_de") or {}
    assert gov.get("authoritative_champion") == AUTHORITATIVE_CHAMPION
    assert gov.get("lines_de")

    tabs = build_cockpit_tab_labels(data)
    assert "Champion-Governance" in tabs
    assert "Freigegeben" in tabs["Champion-Governance"] or AUTHORITATIVE_CHAMPION in tabs["Champion-Governance"]
