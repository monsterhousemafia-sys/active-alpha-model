from __future__ import annotations

from pathlib import Path

from execution.confirmed_live.pilot_live_trading_policy import (
    activation_phrase,
    disable_pilot_live_trading,
    enable_pilot_live_trading,
    is_pilot_live_trading_enabled,
    live_submission_allowed,
)


def test_enable_disable_pilot_trading(tmp_path: Path) -> None:
    assert activation_phrase() == ""
    res = enable_pilot_live_trading(tmp_path, risk_ack=True)
    assert res["ok"] is True
    assert is_pilot_live_trading_enabled(tmp_path)
    assert live_submission_allowed(tmp_path)
    off = disable_pilot_live_trading(tmp_path)
    assert off["ok"] is True
    assert not is_pilot_live_trading_enabled(tmp_path)
