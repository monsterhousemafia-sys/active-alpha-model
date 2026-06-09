"""R3 Gesamtpaket — Vorbestellung wenn Live-Kurse fehlen."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_stock_orders import submit_r3_initial_package
from execution.confirmed_live.us_equity_deferred_intents import (
    default_policy,
    limit_price_for_deferred,
    list_pending_r3_intents,
    save_policy,
)
from tests.r3_order_fixtures import seed_orders_stack


def _seed_deferred_env(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    save_policy(tmp_path, default_policy())
    (tmp_path / "paper/p16d/fx_observation_ledger").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper/p16d/fx_observation_ledger/fx_observations.jsonl").write_text(
        json.dumps({"usd_to_eur_rate": 0.86, "usd_fx_quality_gate": "PASS"}) + "\n",
        encoding="utf-8",
    )


def test_limit_price_for_deferred_uses_raw_usd(tmp_path: Path) -> None:
    _seed_deferred_env(tmp_path)
    snap = {
        "quotes_by_symbol": {
            "STX": {"raw_price": 100.0, "quote_currency": "USD", "price_eur": None},
        }
    }
    with patch(
        "execution.confirmed_live.us_equity_deferred_intents.limit_price_for_symbol",
        return_value=0.0,
    ):
        lim = limit_price_for_deferred(tmp_path, "STX", quote_snapshot=snap)
    assert lim > 0


@patch("analytics.r3_freigabe.auto_prepare_freigabe_for_desktop", return_value={"package_ready": True})
@patch("analytics.r3_stock_orders._live_submit_ready", return_value=False)
@patch("analytics.r3_stock_orders._resolve_limit_price", return_value=0.0)
@patch("execution.confirmed_live.us_equity_deferred_intents.limit_price_for_deferred", return_value=42.0)
def test_full_package_deferred_enqueue(
    _mock_deferred_price,
    _mock_limit,
    _mock_live,
    _mock_auto,
    tmp_path: Path,
) -> None:
    from analytics.r3_trading_functions import build_r3_trading_functions
    from analytics.r3_stock_orders import refresh_stock_order_evidence

    _seed_deferred_env(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    out = submit_r3_initial_package(tmp_path, confirmed=True)
    assert out["ok"] is True
    assert out["mode"] == "deferred_package"
    pending = list_pending_r3_intents(tmp_path)
    assert len(pending) >= 1
    assert all(i.get("source") == "R3_DESKTOP" for i in pending)
