from __future__ import annotations

from pathlib import Path

from integrations.trading212.t212_execution_profile_activation_guard import (
    can_activate_core_live,
    describe_core_live_prerequisites,
)


def test_can_activate_core_live_with_pilot_ack(tmp_path: Path, monkeypatch) -> None:
    from execution.confirmed_live.pilot_live_trading_policy import enable_pilot_live_trading, activation_phrase

    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    enable_pilot_live_trading(tmp_path, phrase=activation_phrase(), risk_ack=True)
    assert can_activate_core_live(tmp_path) is True
    pre = describe_core_live_prerequisites(tmp_path)
    assert pre.get("pilot_live") is True
