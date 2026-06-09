from __future__ import annotations

from pathlib import Path

from execution.confirmed_live.trading_mode_policy import (
    apply_trading_mode,
    get_trading_mode,
    save_trading_mode,
)


def test_manual_mode_blocks_pilot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "0")
    apply_trading_mode(tmp_path, "ai_assisted", changed_by="test")
    apply_trading_mode(tmp_path, "manual", changed_by="test")
    assert get_trading_mode(tmp_path) == "manual"
    from execution.confirmed_live.pilot_live_trading_policy import is_pilot_live_trading_enabled

    assert not is_pilot_live_trading_enabled(tmp_path)


def test_ai_assisted_mode_enables_stack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    res = apply_trading_mode(tmp_path, "ai_assisted", changed_by="test")
    assert res.get("ok")
    assert get_trading_mode(tmp_path) == "ai_assisted"
    from execution.confirmed_live.confirmed_execution_mode_controller import is_active
    from execution.confirmed_live.pilot_live_trading_policy import is_pilot_live_trading_enabled

    assert is_pilot_live_trading_enabled(tmp_path)
    assert is_active(tmp_path)


def test_trading_readiness_checks(tmp_path: Path, monkeypatch) -> None:
    from execution.confirmed_live.trading_mode_policy import trading_readiness

    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    apply_trading_mode(tmp_path, "ai_assisted", changed_by="test")
    rd = trading_readiness(tmp_path)
    assert rd["mode"] == "ai_assisted"
    assert len(rd["checks"]) == 2


def test_preference_persists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    save_trading_mode(tmp_path, "manual", changed_by="test")
    apply_trading_mode(tmp_path, "manual", changed_by="test")
    assert get_trading_mode(tmp_path) == "manual"
