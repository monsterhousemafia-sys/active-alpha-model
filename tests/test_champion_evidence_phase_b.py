"""Phase B champion artifact remediation tests."""
from __future__ import annotations

import json
from pathlib import Path

from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from tools.run_champion_evidence_phase_b import patch_champion_registry_to_r3, run_phase_b


def test_phase_b_patches_champion_registry_away_from_r5(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control" / "champion_registry.json").write_text(
        json.dumps(
            {
                "variant_id": "R5_rank_only_train5",
                "role": "CHAMPION",
                "run_id": "20260531T171255442Z_R5",
            }
        ),
        encoding="utf-8",
    )
    out = patch_champion_registry_to_r3(tmp_path)
    assert out.get("patched") is True
    reg = json.loads((tmp_path / "control" / "champion_registry.json").read_text(encoding="utf-8"))
    assert reg["variant_id"] == AUTHORITATIVE_CHAMPION


def test_phase_b_repair_pointer_and_reports(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    (out / "latest_validated_run.json").write_text(
        json.dumps(
            {
                "variant_id": "R3_w075_q065_noexit",
                "run_id": "20260531T171255442Z_R5_rank_only_train5_bad",
                "run_dir": str(out),
            }
        ),
        encoding="utf-8",
    )
    # Contaminated long calendar
    dates = __import__("pandas").date_range("2017-01-01", periods=2000, freq="B")
    __import__("pandas").Series(0.0001, index=dates).to_frame("strategy_return").to_csv(
        out / "strategy_daily_returns.csv"
    )
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "evidence" / "variant_run_inventory.json").write_text(
        json.dumps(
            {
                "variants": [
                    {
                        "variant_id": AUTHORITATIVE_CHAMPION,
                        "metrics_embedded": {"sharpe_0rf": 0.92, "n_days": 1860, "cagr": 0.19, "max_drawdown": -0.26},
                        "integrity": {"integrity_pass": True, "status": "PASS"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control" / "champion_lineage_policy.json").write_text("{}", encoding="utf-8")

    summary = run_phase_b(root)
    assert summary.get("status", "").startswith("COMPLETE")
    ptr = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert ptr["variant_id"] == AUTHORITATIVE_CHAMPION
    assert "R5" not in str(ptr.get("run_id") or "")
    report = json.loads((out / "challenger_report.json").read_text(encoding="utf-8"))
    assert report["champion_variant_id"] == AUTHORITATIVE_CHAMPION
    txt = (out / "challenger_report.txt").read_text(encoding="utf-8")
    assert "R5_rank_only_train5 [CHAMPION]" not in txt
