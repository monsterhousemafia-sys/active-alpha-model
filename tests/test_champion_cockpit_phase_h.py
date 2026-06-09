"""Phase H operator transparency cockpit panels."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from aa_champion_cockpit_phase_h import (
    build_h1_model_comparison_de,
    build_h4_pointer_drift_de,
    build_operator_transparency_de,
)
from aa_decision_cockpit_gui import build_cockpit_tab_labels
from aa_decision_cockpit_viewmodel import load_decision_cockpit
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tools.run_champion_evidence_phase_h import run_phase_h


def test_h1_from_canonical(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence" / "canonical_model_comparison.json").write_text(
        json.dumps(
            {
                "headline": {
                    "matrix_embedded_sharpe_leader": "R0_LEGACY_ENSEMBLE",
                    "champion_sharpe_rank_matrix": 4,
                    "do_not_cross_compare_frames": True,
                },
                "variants": [{"variant_id": AUTHORITATIVE_CHAMPION, "role": "CHAMPION"}],
                "rankings": {
                    "sharpe_matrix_embedded": [
                        {"rank": 1, "variant_id": "R0_LEGACY_ENSEMBLE", "sharpe_0rf": 0.98},
                        {"rank": 4, "variant_id": AUTHORITATIVE_CHAMPION, "sharpe_0rf": 0.92},
                    ],
                    "sharpe_aligned_intersection": [
                        {"rank": 1, "variant_id": "MOM_63_TOP12", "sharpe_0rf": 1.03},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    h1 = build_h1_model_comparison_de(tmp_path)
    assert h1["status"] == "OK"
    text = "\n".join(h1["lines_de"])
    assert "R0_LEGACY_ENSEMBLE" in text
    assert AUTHORITATIVE_CHAMPION in text
    assert "WARNUNG" in text


def test_h4_drift_detected(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "challenger_report.json").write_text(
        json.dumps({"champion_variant_id": "WRONG_VARIANT"}),
        encoding="utf-8",
    )
    h4 = build_h4_pointer_drift_de(tmp_path)
    assert h4["drift_detected"] is True
    assert h4["failsafe_active"] is True
    assert "FAILSAFE" in h4["failsafe_banner_de"]


def test_cockpit_tabs_include_phase_h(tmp_path: Path) -> None:
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
    (root / "control" / "champion_decision_charter.md").write_text("# Charter\n\nR3 bleibt Champion.\n", encoding="utf-8")
    (root / "control" / "champion_change_criteria.yaml").write_text(
        yaml.dump({"authoritative_champion": AUTHORITATIVE_CHAMPION}),
        encoding="utf-8",
    )
    (root / "control" / "challenger_report.json").write_text(
        json.dumps({"champion_variant_id": AUTHORITATIVE_CHAMPION}),
        encoding="utf-8",
    )

    data = load_decision_cockpit(root)
    assert "operator_transparency_de" in data
    tabs = build_cockpit_tab_labels(data)
    assert "Modell-Vergleich (Research)" in tabs
    assert "Champion-Status" in tabs
    assert "Rebalance-Vorcheck" in tabs
    assert "Pointer-Drift" in tabs
    assert data["operator_transparency_de"]["h4_pointer_drift"]["drift_detected"] is False


def test_phase_h_tool_writes_evidence(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "champion_decision_charter.md").write_text("# c\n", encoding="utf-8")
    (tmp_path / "control" / "challenger_report.json").write_text(
        json.dumps({"champion_variant_id": AUTHORITATIVE_CHAMPION}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence" / "canonical_model_comparison.json").write_text(
        json.dumps({"headline": {}, "rankings": {}, "variants": []}),
        encoding="utf-8",
    )
    summary = run_phase_h(tmp_path)
    assert summary["status"] in {"COMPLETE", "PARTIAL"}
    assert (tmp_path / "evidence" / "phase_h_operator_transparency_summary.json").is_file()
    assert (tmp_path / "docs" / "PHASE_H_OPERATOR_TRANSPARENCY_REPORT.md").is_file()
