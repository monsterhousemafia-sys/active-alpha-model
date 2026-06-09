from pathlib import Path

from analytics.t212_broker_economics import (
    apply_buy_target_fee_adjustment,
    build_broker_economics_context,
    extract_currency_context,
    fee_policy_summary,
)


def test_extract_currency_context_eur_account() -> None:
    broker = {
        "cash_eur": 400.0,
        "cash_breakdown": {
            "currency": "EUR",
            "planning_cash_eur": 400.0,
            "reserved_for_orders_eur": 10.0,
            "total_account_value_eur": 600.0,
            "invested_current_value_eur": 200.0,
        },
        "positions": [{"instrument": {"ticker": "STX", "currency": "USD"}, "walletImpact": {"currentValue": 200.0}}],
    }
    ctx = extract_currency_context(broker)
    assert ctx["account_currency"] == "EUR"
    assert ctx["valuation_currency"] == "EUR"
    assert "USD" in ctx["position_quote_currencies"]
    assert "reserviert" in ctx["note_de"].lower()


def test_fee_policy_summary_loads_costs(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text(
        '{"costs":{"fx_bps":15.0,"slippage_bps":5.0,"min_trade_eur_floor":5.0}}',
        encoding="utf-8",
    )
    fees = fee_policy_summary(tmp_path)
    assert float(fees["fx_bps"]) == 15.0
    assert "FX" in fees["summary_de"]


def test_apply_buy_target_fee_adjustment_reduces_target(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text(
        '{"costs":{"fx_bps":15.0,"slippage_bps":5.0}}',
        encoding="utf-8",
    )
    adj = apply_buy_target_fee_adjustment(100.0, tmp_path)
    assert float(adj["target_eur_gross"]) == 100.0
    assert float(adj["target_eur"]) < 100.0
    assert float(adj["estimated_one_way_cost_eur"] or 0) > 0


def test_build_broker_economics_context(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text("{}", encoding="utf-8")
    broker = {"cash_eur": 500.0, "cash_breakdown": {"currency": "EUR"}}
    doc = build_broker_economics_context(tmp_path, broker, plan_capital_eur=500.0)
    assert doc.get("currency")
    assert doc.get("fees")
    assert doc.get("sample_round_trip")
