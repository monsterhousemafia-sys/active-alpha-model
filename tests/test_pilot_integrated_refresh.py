from analytics.pilot_integrated_refresh import build_refresh_status, estimate_cost_risk


def test_cost_risk_stress_stricter_than_base() -> None:
    cr = estimate_cost_risk(None, notional_eur=50.0, limit_price_eur=25.0)  # type: ignore[arg-type]
    assert cr["stress_round_trip_eur"] >= cr["base_round_trip_eur"]
    if not cr["worth_trading_stress"]:
        assert not cr["trade_allowed"]


def test_refresh_status_has_linked_rows() -> None:
    doc = build_refresh_status(
        None,  # type: ignore[arg-type]
        broker={"cash_eur": 100.0, "last_sync_utc": "2026-06-01T12:00:00+00:00", "status": "OK"},
        market_prices={
            "freshness": {"status": "FRESH", "reason": "ok"},
            "fetched_at_utc": "2026-06-01T12:00:00+00:00",
        },
        champion_guard={"champion_ok": True, "signals_ok": True, "status_de": "OK"},
        investment_plan={"primary_action": {"symbol": "INTC", "target_eur": 40}},
        reevaluation={
            "status": "OK",
            "quote_fresh": True,
            "urgency": "LOW",
            "summary_de": "ok",
            "trade_required": False,
            "generated_at_utc": "2026-06-01T12:00:00+00:00",
        },
        fx={"ok": True, "usd_per_eur": 1.08, "source": "T"},
        session={"open": True},
        cost_risk={
            "trade_allowed": True,
            "base_round_trip_eur": 0.5,
            "base_round_trip_pct": 1.0,
            "stress_round_trip_eur": 0.8,
            "stress_round_trip_pct": 2.0,
            "stress_add_bps": 35,
            "hurdle_eur": 12,
            "worth_trading_stress": True,
        },
    )
    keys = {r["key"] for r in doc["rows"]}
    assert "broker" in keys and "quotes" in keys and "trade_gate" in keys


def test_refresh_all_ok_tolerates_weekend_quote_warn() -> None:
    doc = build_refresh_status(
        None,  # type: ignore[arg-type]
        broker={"cash_eur": 100.0, "last_sync_utc": "2026-06-01T12:00:00+00:00", "status": "OK"},
        market_prices={
            "freshness": {"status": "STALE", "reason": "weekend"},
            "fetched_at_utc": "2026-06-01T12:00:00+00:00",
        },
        champion_guard={"champion_ok": True, "signals_ok": True, "status_de": "OK"},
        investment_plan={"primary_action": {"symbol": "INTC", "target_eur": 40}},
        reevaluation={
            "status": "OK",
            "quote_fresh": False,
            "urgency": "HIGH",
            "summary_de": "ok",
            "trade_required": True,
            "generated_at_utc": "2026-06-01T12:00:00+00:00",
        },
        fx={"ok": True, "usd_per_eur": 1.08, "source": "T"},
        session={"open": False},
        cost_risk={
            "trade_allowed": True,
            "base_round_trip_eur": 0.5,
            "base_round_trip_pct": 1.0,
            "stress_round_trip_eur": 0.8,
            "stress_round_trip_pct": 2.0,
            "stress_add_bps": 35,
            "hurdle_eur": 12,
            "worth_trading_stress": True,
        },
    )
    quotes = next(r for r in doc["rows"] if r["key"] == "quotes")
    assert quotes["status"] == "WARN"
    assert doc["all_ok"] is True
