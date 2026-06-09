"""P4 shadow champion framework gate tests (master prompt §13.6)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_shadow_champion import (
    CHAMPION_REGISTRY,
    PROMOTION_STATUS_FILE,
    ROLLBACK_REGISTRY_FILE,
    SHADOW_OUTCOMES_FILE,
    SHADOW_SIGNALS_FILE,
    append_shadow_signals,
    build_rollback_registry,
    evaluate_promotion_gates,
    load_shadow_outcomes,
    load_shadow_signals,
    run_shadow_champion_sync,
)


def _seed_champion(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest_validated_run.json").write_text(
        json.dumps(
            {
                "variant_id": "R3_w075_q065_noexit",
                "run_id": "champion_run",
                "integrity_status": "PASS",
                "run_dir": str(out / "champion_run"),
            }
        ),
        encoding="utf-8",
    )
    (out / "latest_target_portfolio.csv").write_text("ticker,target_weight\nAAA,0.5\n", encoding="utf-8")


def _seed_research(root: Path, *, challenger: str, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "rebalance_date": "2020-01-02",
                "date": "2020-01-02",
                "ticker": "AAA",
                "target_weight": 0.2,
                "mu_hat": 0.01,
                "selection_score": 0.5,
                "target": 0.008,
            }
        ]
    ).to_csv(run_dir / "backtest_decisions.csv", index=False)
    payload = {
        "research_status": "PASS",
        "best_research_candidate": {"variant_id": challenger, "active": False},
        "entries": [
            {
                "variant_id": challenger,
                "is_research_candidate": True,
                "integrity_pass": True,
                "run_dir": str(run_dir),
                "status": "PASS",
            }
        ],
    }
    (root / "model_output" / "background_research_status.json").write_text(json.dumps(payload), encoding="utf-8")


def test_p4_shadow_does_not_change_active_portfolio(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _seed_champion(out)
    before = (out / "latest_target_portfolio.csv").read_text(encoding="utf-8")
    run_dir = root / "validation_runs" / "x_R0_LEGACY_ENSEMBLE"
    _seed_research(root, challenger="R0_LEGACY_ENSEMBLE", run_dir=run_dir)
    run_shadow_champion_sync(root, out)
    after = (out / "latest_target_portfolio.csv").read_text(encoding="utf-8")
    assert before == after
    assert (out / SHADOW_SIGNALS_FILE).is_file()


def test_p4_shadow_outcome_does_not_overwrite_champion_signal(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _seed_champion(out)
    run_dir = root / "validation_runs" / "x_R0_LEGACY_ENSEMBLE"
    _seed_research(root, challenger="R0_LEGACY_ENSEMBLE", run_dir=run_dir)
    run_shadow_champion_sync(root, out)
    pointer = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert pointer["run_id"] == "champion_run"
    outcomes = load_shadow_outcomes(out)
    if not outcomes.empty:
        assert outcomes.iloc[0]["outcome_status"] == "MATURE"


def test_p4_promotion_blocked_when_gate_fails(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _seed_champion(out)
    promo = evaluate_promotion_gates(root, out)
    assert promo["overall_status"] == "BLOCKED"
    assert promo["auto_promotion_enabled"] is False
    assert promo["auto_execute_real_money"] is False


def test_p4_rollback_registry_available(tmp_path: Path) -> None:
    root = tmp_path
    ctrl = root / "control"
    ctrl.mkdir(parents=True)
    (ctrl / "last_known_good_state.json").write_text(
        json.dumps({"validated_run_id": "good", "validated_variant_id": "R3", "artifact_hashes": {"a": "b"}}),
        encoding="utf-8",
    )
    reg = build_rollback_registry(root)
    assert reg["rollback_available"] is True
    assert reg["target_run_id"] == "good"


def test_p4_sync_writes_registries(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _seed_champion(out)
    run_dir = root / "validation_runs" / "x_R0_LEGACY_ENSEMBLE"
    _seed_research(root, challenger="R0_LEGACY_ENSEMBLE", run_dir=run_dir)
    (root / "control").mkdir(exist_ok=True)
    (root / "control" / "last_known_good_state.json").write_text('{"validated_run_id":"good"}', encoding="utf-8")
    summary = run_shadow_champion_sync(root, out)
    assert summary["status"] == "OK"
    assert (out / CHAMPION_REGISTRY).is_file()
    assert (out / PROMOTION_STATUS_FILE).is_file()
    assert (out / ROLLBACK_REGISTRY_FILE).is_file()
    assert len(load_shadow_signals(out)) >= 1


def test_p4_reappend_shadow_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path
    out = root / "model_output"
    _seed_champion(out)
    decisions = out / "backtest_decisions.csv"
    pd.DataFrame(
        [{"rebalance_date": "2020-01-02", "date": "2020-01-02", "ticker": "X", "target_weight": 0.1, "mu_hat": 0.01}]
    ).to_csv(decisions, index=False)
    n1 = append_shadow_signals(out, champion_variant="R3", challenger_variant="R0", decisions_path=decisions)
    n2 = append_shadow_signals(out, champion_variant="R3", challenger_variant="R0", decisions_path=decisions)
    assert n1 == 1
    assert n2 == 0
