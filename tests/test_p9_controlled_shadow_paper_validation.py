"""P9 controlled shadow/paper validation preparation gate tests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from aa_auto_promotion import CONFIG_FILE
from aa_p9_shadow_paper_prep import (
    STATUS_FILE,
    evaluate_p9_preparation_gates,
    run_p9_shadow_paper_prep_sync,
)
from aa_shadow_champion import SHADOW_OUTCOMES_FILE, SHADOW_SIGNALS_FILE


def _write_config(root: Path) -> None:
    cfg = {
        "schema_version": 1,
        "minimum_mature_shadow_outcomes": 1,
        "auto_research_enabled": True,
        "auto_promote_paper_enabled": False,
        "auto_promote_signal_enabled": False,
        "auto_execute_real_money_enabled": False,
    }
    (root / CONFIG_FILE).write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _seed_ready(root: Path, out: Path, *, champion: str = "R3_w075_q065_noexit") -> None:
    out.mkdir(parents=True, exist_ok=True)
    (root / "paper_trading_engine.py").write_text("# scaffold\n", encoding="utf-8")
    (root / "active_alpha_user_config.bat").write_text(
        'set "AA_PAPER_DIR=paper_output"\nset "AA_BACKTEST_OUT_DIR=model_output"\n',
        encoding="utf-8",
    )
    (out / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": champion, "run_id": "champion", "integrity_status": "PASS"}),
        encoding="utf-8",
    )
    research = {
        "entries": [
            {"variant_id": champion, "integrity_pass": True, "metrics": {"sharpe_0rf": 0.9}},
            {
                "variant_id": "M1_MOM_BLEND_MATCHED_CONTROLS",
                "integrity_pass": True,
                "metrics": {"sharpe_0rf": 0.95},
            },
            {
                "variant_id": "MOM_63_TOP12",
                "integrity_pass": True,
                "run_dir": str(root / "validation_runs" / "x"),
                "metrics": {"sharpe_0rf": 1.0, "max_drawdown": -0.2},
            },
        ]
    }
    (out / "background_research_status.json").write_text(json.dumps(research), encoding="utf-8")
    (out / "challenger_registry.json").write_text(
        json.dumps({"shadow_challenger_id": "MOM_63_TOP12", "challengers": []}),
        encoding="utf-8",
    )
    (out / "realtime_replay_status.json").write_text(json.dumps({"data_quality_status": "PASS"}), encoding="utf-8")
    pd.DataFrame([{"shadow_id": "s1", "challenger_variant_id": "MOM_63_TOP12"}]).to_parquet(
        out / SHADOW_SIGNALS_FILE, index=False
    )
    pd.DataFrame([{"shadow_id": "s1", "challenger_variant_id": "MOM_63_TOP12", "outcome_status": "MATURE"}]).to_parquet(
        out / SHADOW_OUTCOMES_FILE, index=False
    )
    ctrl = root / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    (ctrl / "last_known_good_state.json").write_text(
        json.dumps({"validated_variant_id": champion, "validated_run_id": "champion"}),
        encoding="utf-8",
    )


def test_p9_preparation_passes_with_champion_and_m1(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root)
    _seed_ready(root, out)
    gate = evaluate_p9_preparation_gates(root, out)
    assert gate["all_gates_pass"] is True
    assert gate["promotion_allowed"] is False


def test_p9_sync_writes_status_without_champion_change(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root)
    _seed_ready(root, out)
    champion_ptr = (out / "latest_validated_run.json").read_text(encoding="utf-8")
    result = run_p9_shadow_paper_prep_sync(root, out)
    assert result["status"] == "OK"
    assert result["champion_unchanged"] is True
    assert (out / STATUS_FILE).is_file()
    assert (root / "control" / STATUS_FILE).is_file()
    assert (out / "latest_validated_run.json").read_text(encoding="utf-8") == champion_ptr


def test_p9_blocks_when_promotion_enabled(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root)
    _seed_ready(root, out)
    cfg = yaml.safe_load((root / CONFIG_FILE).read_text(encoding="utf-8"))
    cfg["auto_promote_paper_enabled"] = True
    (root / CONFIG_FILE).write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    gate = evaluate_p9_preparation_gates(root, out)
    assert gate["all_gates_pass"] is False
    assert "promotion_blocked_gate" in gate["blocked_reasons"]


def test_p9_blocks_without_m1_control(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root)
    _seed_ready(root, out)
    research = json.loads((out / "background_research_status.json").read_text(encoding="utf-8"))
    research["entries"] = [e for e in research["entries"] if e["variant_id"] != "M1_MOM_BLEND_MATCHED_CONTROLS"]
    (out / "background_research_status.json").write_text(json.dumps(research), encoding="utf-8")
    gate = evaluate_p9_preparation_gates(root, out)
    assert gate["all_gates_pass"] is False
    assert "m1_control_gate" in gate["blocked_reasons"]


def test_p9_blocks_when_champion_differs_from_lkg(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _write_config(root)
    _seed_ready(root, out)
    (out / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": "OTHER", "run_id": "x", "integrity_status": "PASS"}),
        encoding="utf-8",
    )
    gate = evaluate_p9_preparation_gates(root, out)
    assert gate["all_gates_pass"] is False
    assert "champion_reference_gate" in gate["blocked_reasons"]
