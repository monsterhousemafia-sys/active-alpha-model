"""GUI confirmation lease — mandatory before live T212 POST."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from execution.confirmed_live.gui_execution_confirmation import (
    consume_execution_slot,
    grant_execution_confirmation,
    has_active_execution_confirmation,
    manual_gui_confirm_enforced,
    revoke_execution_confirmation,
)
from execution.confirmed_live.order_confirmation_token_service import issue_token
from execution.confirmed_live.order_submission_service import submit_confirmed_order
from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "live_pilot/confirmed_execution").mkdir(parents=True, exist_ok=True)
    import json
    from datetime import date

    import pandas as pd

    sig = date.today().isoformat()
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"active_profile": "daily_alpha_h1", "profiles": {"daily_alpha_h1": {}}}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps(
            {
                "ok": True,
                "profile_used": "daily_alpha_h1",
                "signal_date": sig,
                "top_picks": [{"ticker": "INTC", "target_weight": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    import pandas as pd

    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": "INTC", "target_weight": 1.0, "signal_date": sig}]).to_csv(
        tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False
    )
    cache = tmp_path / "model_output_sp500_pit_t212/price_cache"
    cache.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(end=sig, periods=3, freq="D")
    pd.DataFrame({"date": days, "ticker": ["INTC"] * len(days), "close": [100.0, 101.0, 102.0]}).to_parquet(
        cache / "ohlcv_panel.parquet", index=False
    )
    return tmp_path


def test_manual_gui_confirm_enforced_by_default() -> None:
    assert manual_gui_confirm_enforced() is True


def test_grant_and_consume_slots(root: Path) -> None:
    grant_execution_confirmation(root, source="TEST", max_submissions=2)
    assert has_active_execution_confirmation(root)
    assert consume_execution_slot(root)["ok"] is True
    assert consume_execution_slot(root)["ok"] is True
    assert consume_execution_slot(root)["ok"] is False


def test_live_submit_blocked_without_gui_grant(root: Path) -> None:
    draft = {
        "draft_id": "d1",
        "instrument": "INTC",
        "side": "BUY",
        "quantity": 1.0,
        "limit_price": 22.0,
        "max_notional_eur": 50.0,
        "t212_instrument_id": "INTC_US_EQ",
        "order_type": "LIMIT",
    }
    token = issue_token(root, draft, profile=PROFILE_CONFIRMED_EXECUTION)
    with patch("execution.confirmed_live.order_submission_service.run_preflight", return_value={"passed": True}), patch(
        "execution.confirmed_live.p17_review_mode_guard.review_mode_active",
        return_value=False,
    ), patch(
        "execution.confirmed_live.pilot_live_trading_policy.live_submission_allowed",
        return_value=True,
    ), patch(
        "execution.linux_security_boundary.live_order_submission_blocked",
        return_value=False,
    ):
        result = submit_confirmed_order(
            root,
            draft,
            one_time_token=token["one_time_token"],
            readonly_cash=500.0,
            account_currency="EUR",
            dry_run=False,
        )
    assert result.get("ok") is False
    assert result.get("stage") == "gui_confirmation"


def test_live_submit_allowed_after_grant(root: Path) -> None:
    import json
    from datetime import date

    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/prediction_operations.json").write_text(
        json.dumps({"active_profile": "daily_alpha_h1", "profiles": {"daily_alpha_h1": {}}}),
        encoding="utf-8",
    )
    sig = date.today().isoformat()
    (root / "control/prediction_readiness.json").write_text(
        json.dumps(
            {
                "ok": True,
                "profile_used": "daily_alpha_h1",
                "signal_date": sig,
                "top_picks": [{"ticker": "INTC", "target_weight": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    import pandas as pd

    (root / "model_output_sp500_pit_t212").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": "INTC", "target_weight": 1.0, "signal_date": sig}]).to_csv(
        root / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False
    )
    cache = root / "model_output_sp500_pit_t212/price_cache"
    cache.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(end=sig, periods=3, freq="D")
    pd.DataFrame({"date": days, "ticker": ["INTC"] * len(days), "close": [100.0, 101.0, 102.0]}).to_parquet(
        cache / "ohlcv_panel.parquet", index=False
    )
    grant_execution_confirmation(root, source="ORDER_WORKFLOW_DIALOG", max_submissions=1)
    draft = {
        "draft_id": "d2",
        "instrument": "INTC",
        "side": "BUY",
        "quantity": 1.0,
        "limit_price": 22.0,
        "max_notional_eur": 50.0,
        "t212_instrument_id": "INTC_US_EQ",
        "order_type": "LIMIT",
    }
    token = issue_token(root, draft, profile=PROFILE_CONFIRMED_EXECUTION)
    with patch("execution.confirmed_live.order_submission_service.run_preflight", return_value={"passed": True}), patch(
        "execution.confirmed_live.p17_review_mode_guard.review_mode_active",
        return_value=False,
    ), patch(
        "execution.confirmed_live.pilot_live_trading_policy.live_submission_allowed",
        return_value=True,
    ), patch(
        "execution.linux_security_boundary.live_order_submission_blocked",
        return_value=False,
    ), patch(
        "integrations.trading212.t212_order_pacing.can_place_limit_order_now",
        return_value=(True, ""),
    ), patch(
        "integrations.trading212.t212_order_pacing.acquire_limit_order_slot",
    ), patch(
        "integrations.trading212.t212_order_pacing.record_limit_order_result",
    ), patch(
        "integrations.trading212.t212_confirmed_execution_client.T212ConfirmedExecutionClient.from_execution_profile",
    ) as client_factory:
        client = client_factory.return_value
        client.submit_limit_order.return_value = {"id": 1}
        result = submit_confirmed_order(
            root,
            draft,
            one_time_token=token["one_time_token"],
            readonly_cash=500.0,
            account_currency="EUR",
            dry_run=False,
        )
    assert result.get("ok") is True
    assert result.get("sent_to_t212") is True


def test_revoke_clears_lease(root: Path) -> None:
    grant_execution_confirmation(root, source="ORDER_WORKFLOW_DIALOG", max_submissions=1)
    revoke_execution_confirmation(root)
    assert has_active_execution_confirmation(root) is False
