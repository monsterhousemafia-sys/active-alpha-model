"""T212 order readiness gates."""
from __future__ import annotations

from integrations.trading212.t212_order_readiness import (
    assess_order_readiness,
    record_stock_buy_attempt,
    us_orders_allowed_now,
)


def test_us_orders_blocked_outside_session_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AA_ALLOW_US_ORDERS_OUTSIDE_SESSION", raising=False)

    class _Sess:
        def __init__(self) -> None:
            self.calls = 0

        def us_equity_regular_session_open_now(self):
            self.calls += 1
            return {"open": False, "reason_de": "closed"}

    stub = _Sess()
    monkeypatch.setattr(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        stub.us_equity_regular_session_open_now,
    )
    allowed, info = us_orders_allowed_now()
    assert allowed is False
    assert "closed" in str(info.get("reason_de", ""))


def test_assess_readiness_blocks_closed_session(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AA_ALLOW_US_ORDERS_OUTSIDE_SESSION", raising=False)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/trading_mode_preference.json").write_text(
        '{"mode":"ai_assisted","schema_version":1}', encoding="utf-8"
    )
    (tmp_path / "live_pilot/confirmed_execution").mkdir(parents=True, exist_ok=True)
    (tmp_path / "live_pilot/confirmed_execution/core_live_mode_state.json").write_text(
        '{"status":"ACTIVE_CONFIRM_BEFORE_SUBMIT_ONLY"}', encoding="utf-8"
    )
    (tmp_path / "control/p17_review_mode_user_preference.json").write_text(
        '{"review_mode_enabled":false}', encoding="utf-8"
    )
    monkeypatch.setattr(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        lambda: {"open": False, "reason_de": "US geschlossen"},
    )
    monkeypatch.setattr(
        "integrations.trading212.t212_dual_profile_credential_store.execution_configured",
        lambda: True,
    )
    r = assess_order_readiness(tmp_path, free_cash_eur=400.0)
    assert not r.ok
    assert "US_REGULAR_SESSION_CLOSED" in r.blockers


def test_record_stock_buy_insufficient_streak(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "integrations.trading212.t212_order_readiness.us_orders_allowed_now",
        lambda: (True, {"open": True, "reason_de": "test"}),
    )
    record_stock_buy_attempt(tmp_path, ok=False, error="insufficient-free-for-stocks-buy")
    doc = record_stock_buy_attempt(tmp_path, ok=False, error="insufficient-free-for-stocks-buy")
    assert int(doc.get("consecutive_insufficient") or 0) == 2
