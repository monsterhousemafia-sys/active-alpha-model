from __future__ import annotations

from pathlib import Path

from analytics.human_vs_base_comparison import (
    build_trade_timeline,
    compare_human_vs_base,
    enrich_comparison_report,
    export_comparison_pdf,
    human_portfolio_from_broker,
    load_base_portfolio,
    render_comparison_dashboard_png,
)


def test_load_base_portfolio_has_positions():
    root = Path(__file__).resolve().parents[1]
    base = load_base_portfolio(root)
    assert base["status"] == "OK"
    assert len(base["positions"]) >= 4


def test_compare_with_live_broker_snapshot():
    root = Path(__file__).resolve().parents[1]
    broker = {
        "credentials_configured": True,
        "cash_eur": 444.0,
        "positions": [
            {
                "instrument": {"ticker": "VUSDl_EQ", "name": "Vanguard S&P 500"},
                "walletImpact": {"currentValue": 48.0},
            }
        ],
    }
    report = compare_human_vs_base(root, broker)
    assert report["status"] == "OK"
    assert report["metrics"]["cash_weight_human_pct"] > 50
    assert "VUSD" in report["metrics"]["symbols_held_not_in_base"]


def test_human_portfolio_from_broker():
    broker = {"cash_eur": 100, "positions": []}
    h = human_portfolio_from_broker(broker)
    assert h["cash_weight_pct"] == 100.0


def test_trade_timeline_from_position_created_at():
    root = Path(__file__).resolve().parents[1]
    broker = {
        "positions": [
            {
                "instrument": {"ticker": "VUSDl_EQ"},
                "walletImpact": {"currentValue": 50},
                "createdAt": "2026-01-15T10:00:00Z",
            }
        ]
    }
    tl = build_trade_timeline(root, broker)
    assert tl["event_count"] >= 1
    assert tl["events"][0]["symbol"] == "VUSD"


def test_enrich_adds_equity_and_metrics(tmp_path):
    base = load_base_portfolio(Path(__file__).resolve().parents[1])
    report = {
        "status": "OK",
        "base": base,
        "human": {"total_value_eur": 492.0, "cash_eur": 444.0, "cash_weight_pct": 90.0, "holdings": []},
        "rows": [],
        "metrics": {},
    }
    out = enrich_comparison_report(tmp_path, {"positions": []}, report)
    assert "equity_series" in out
    assert "trade_timeline" in out
    assert out["metrics"]["equity_point_count"] >= 1


def test_dashboard_and_pdf_render(tmp_path):
    root = Path(__file__).resolve().parents[1]
    broker = {
        "credentials_configured": True,
        "cash_eur": 400.0,
        "positions": [
            {
                "instrument": {"ticker": "VUSDl_EQ"},
                "walletImpact": {"currentValue": 48.0},
                "createdAt": "2026-02-01T12:00:00Z",
            }
        ],
    }
    report = compare_human_vs_base(root, broker)
    assert report["status"] == "OK"
    png = tmp_path / "dash.png"
    ok, _ = render_comparison_dashboard_png(report, png)
    assert ok and png.is_file()
    pdf = tmp_path / "report.pdf"
    ok_pdf, _ = export_comparison_pdf(report, pdf)
    assert ok_pdf and pdf.is_file()
