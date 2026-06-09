"""Pre-session trading day warnings."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analytics.pilot_trading_day_warnings import collect_trading_day_warnings, warnings_traffic_level
from execution.confirmed_live.us_equity_deferred_intents import (
    list_pending_intents,
    list_stale_pending_intents,
    prune_expired_intents,
)


def test_warnings_under_invested_critical(tmp_path: Path) -> None:
    snap = {
        "broker": {"cash_eur": 600.0},
        "n_positions": 0,
        "rebalance_status": {"is_due": True, "summary_de": "Rebalance fällig"},
        "reevaluation": {
            "urgency": "STALE_QUOTES",
            "quote_reason": "Keine Kurse",
            "exposure_check": {"under_invested": True, "cash_weight_pct": 100.0, "exposure_gap_pct": 100.0},
            "regime": "RISK_ON",
        },
        "guard": {"champion_ok": True, "signals_ok": True},
        "deferred": {"pending_count": 0, "policy": {}},
    }
    report = collect_trading_day_warnings(tmp_path, snap=snap)
    codes = {w["code"] for w in report["warnings"]}
    assert "STALE_QUOTES" in codes
    assert "UNDER_INVESTED_CASH" in codes
    assert "REBALANCE_DUE_NO_POSITIONS" in codes
    assert report["must_resolve_before_trading"] is True
    assert warnings_traffic_level(report) == "ROT"


def test_stale_fictive_state_not_critical_when_internet_ok(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/adaptive_runtime_state.json").write_text(
        json.dumps(
            {
                "price_source": "fictive",
                "context": {"internet_ok": False},
                "notes": ["Fictive/offline OHLCV active (internet later)"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("aa_adaptive_runtime.probe_internet_prices", lambda **k: True)
    report = collect_trading_day_warnings(tmp_path, snap={"guard": {"champion_ok": True, "signals_ok": True}})
    codes = {w["code"] for w in report["warnings"]}
    assert "OFFLINE_OR_FICTIVE_PRICES" not in codes
    state = json.loads((tmp_path / "control/adaptive_runtime_state.json").read_text(encoding="utf-8"))
    assert state.get("price_source") == "internet"


def test_prune_expired_deferred_intents(tmp_path: Path) -> None:
    past = (datetime.now(timezone.utc) - timedelta(days=2)).replace(microsecond=0).isoformat()
    queue = tmp_path / "live_pilot/confirmed_execution/us_equity_deferred_intents.json"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "intents": [
                    {
                        "status": "PENDING",
                        "instrument": "INTC",
                        "expires_at_utc": past,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert len(list_stale_pending_intents(tmp_path)) == 1
    assert prune_expired_intents(tmp_path) == 1
    assert list_pending_intents(tmp_path) == []


if __name__ == "__main__":
    from pathlib import Path as P
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = P(td)
        test_warnings_under_invested_critical(root)
        test_prune_expired_deferred_intents(root)
    print("OK")
