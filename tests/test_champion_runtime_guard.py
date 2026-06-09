"""Champion runtime guard — policy vs code vs signal freshness."""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from analytics.champion_runtime_guard import (
    ChampionRuntimeGuardError,
    enforce_champion_runtime_hard,
    verify_champion_runtime,
)


def _write_strategic_decision(root, *, active: str = "R0_LEGACY_ENSEMBLE") -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/champion_strategic_decision.json").write_text(
        json.dumps(
            {
                "active_champion": active,
                "prior_champion": "R3_w075_q065_noexit",
                "champion_change_executed": True,
            }
        ),
        encoding="utf-8",
    )


def _write_policy(root, *, champion: str = "R0_LEGACY_ENSEMBLE", auto_update: bool = False) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/learning_collection_policy.json").write_text(
        json.dumps(
            {
                "governance_champion_locked": champion,
                "active_champion_locked": champion,
                "auto_champion_update_enabled": auto_update,
                "auto_model_training_enabled": False,
            }
        ),
        encoding="utf-8",
    )


def _write_portfolio(root, signal_date: str) -> None:
    import pandas as pd

    out = root / "model_output_sp500_pit_t212"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"ticker": "INTC", "target_weight": 0.1, "alpha_lcb": 0.5, "signal_date": signal_date}]
    ).to_csv(out / "latest_target_portfolio.csv", index=False)


def test_verify_champion_runtime_ok(tmp_path, monkeypatch) -> None:
    ref = date.today()
    while ref.weekday() >= 5:
        ref -= timedelta(days=1)
    _write_strategic_decision(tmp_path)
    _write_policy(tmp_path)
    _write_portfolio(tmp_path, ref.isoformat())
    status = verify_champion_runtime(tmp_path)
    assert status.champion_ok
    assert status.signals_ok
    assert status.ok
    assert status.authoritative_champion == "R0_LEGACY_ENSEMBLE"


def test_verify_champion_mismatch_blocks(tmp_path, monkeypatch) -> None:
    ref = date.today()
    while ref.weekday() >= 5:
        ref -= timedelta(days=1)
    _write_strategic_decision(tmp_path, active="R0_LEGACY_ENSEMBLE")
    _write_policy(tmp_path, champion="R5_other_champion")
    _write_portfolio(tmp_path, ref.isoformat())
    status = verify_champion_runtime(tmp_path)
    assert not status.champion_ok
    assert "GOVERNANCE_CHAMPION_POLICY_MISMATCH" in status.blockers


def test_verify_stale_signal_warns_not_hard_block(tmp_path) -> None:
    _write_strategic_decision(tmp_path)
    _write_policy(tmp_path)
    _write_portfolio(tmp_path, "2020-01-02")
    status = verify_champion_runtime(tmp_path)
    assert status.champion_ok
    assert not status.signals_ok
    assert "SIGNAL_DATE_STALE" in status.warnings
    assert not status.hard_block


def test_enforce_raises_on_missing_portfolio(tmp_path) -> None:
    _write_strategic_decision(tmp_path)
    _write_policy(tmp_path)
    with pytest.raises(ChampionRuntimeGuardError) as exc:
        enforce_champion_runtime_hard(tmp_path)
    assert "PORTFOLIO_CSV_MISSING" in exc.value.report.get("blockers", [])


def test_pre_go_live_softens_h1_seal_blockers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AA_LINUX_NATIVE_APP", "1")
    ref = date.today()
    while ref.weekday() >= 5:
        ref -= timedelta(days=1)
    _write_strategic_decision(tmp_path)
    _write_policy(tmp_path)
    _write_portfolio(tmp_path, ref.isoformat())
    (tmp_path / "control").mkdir(exist_ok=True)
    (tmp_path / "control/AI_KERNEL.json").write_text(
        json.dumps(
            {
                "mode": "linux_native_pilot",
                "go_live_date": "2099-01-01",
                "learning": {"phase": "PRE_GO_LIVE_LEARNING"},
                "safety": {"auto_execute_real_money": False, "gui_confirm_required": True},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "active_profile": "daily_alpha_h1",
                "experimental_profiles": ["daily_alpha_h1"],
                "safety": {"real_money": True},
            }
        ),
        encoding="utf-8",
    )
    status = verify_champion_runtime(tmp_path)
    assert not status.hard_block
    assert "DAILY_ALPHA_H1_NOT_SEALED" in status.warnings


def test_enforce_skipped_with_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AA_SKIP_CHAMPION_RUNTIME_GUARD", "1")
    _write_strategic_decision(tmp_path)
    _write_policy(tmp_path)
    status = enforce_champion_runtime_hard(tmp_path)
    assert not status.ok
