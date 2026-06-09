"""R3 Handelsergebnis — Plattform vs. Active-Alpha-Engine."""
import json
from pathlib import Path

from analytics.r3_t212_prognosis import (
    build_r3_t212_daily_prognosis,
    load_product_roles,
    render_r3_t212_prognosis_section,
)


def test_product_roles_separate_engine() -> None:
    root = Path(__file__).resolve().parents[1]
    roles = load_product_roles(root)
    assert roles.get("r3_de", {}).get("role") == "Zentrale Handelsplattform"
    assert roles.get("active_alpha_model_de", {}).get("role") == "Algorithmus"
    assert "T212" in str(roles.get("r3_de", {}).get("delivers_de") or "") or "Trading212" in str(
        roles.get("r3_de", {}).get("delivers_de") or ""
    )


def test_build_prognosis_from_project() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_r3_t212_daily_prognosis(root, persist=False)
    assert doc.get("product_de") == "R3"
    assert doc.get("engine_de") == "Active Alpha Model"
    assert doc.get("broker_de") == "Trading212"
    if doc.get("ok"):
        assert int(doc.get("positions") or 0) > 0


def test_render_section_desktop_only() -> None:
    root = Path(__file__).resolve().parents[1]
    html_out = render_r3_t212_prognosis_section(root, desktop_only=True)
    if html_out:
        assert 'id="r3-desktop"' in html_out
        assert "r3-trading-functions" in html_out
        assert "r3-freigabe-btn" in html_out
        assert "Handelsplattform" not in html_out
        assert "r3-t212-prognosis" not in html_out


def test_build_prognosis_minimal(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_product_roles.json").write_text(
        '{"r3_de":{"delivers_de":"T212 Prognose"},"portfolio_artifact":"p.csv"}',
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        '{"ok":true,"signal_date":"2026-06-01","top_picks":[{"ticker":"SPY","target_weight":0.1},{"ticker":"MU","target_weight":0.05}]}',
        encoding="utf-8",
    )
    doc = build_r3_t212_daily_prognosis(
        tmp_path,
        persist=True,
        live_capital={"ok": True, "trusted": True, "capital_basis": {"investable_eur": 100.0, "planning_cash_eur": 105.0}},
    )
    assert doc.get("ok") is True
    assert doc.get("t212_trusted") is True
    assert doc.get("positions") == 1
    assert doc["top_picks"][0]["ticker"] == "MU"
    assert "SPY" not in {p["ticker"] for p in doc.get("top_picks") or []}
    assert (tmp_path / "evidence/r3_t212_prognosis_latest.json").is_file()


def test_prognosis_positions_match_plan(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_product_roles.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps(
            {
                "ok": True,
                "signal_date": "2026-06-05",
                "top_picks": [
                    {"ticker": "SPY", "target_weight": 0.13},
                    {"ticker": "STX", "target_weight": 0.06},
                    {"ticker": "CAT", "target_weight": 0.02},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "signal_date": "2026-06-05",
                "summary_de": "11 Positionen auf 641 € investierbar",
                "allocations": [
                    {"symbol": "STX", "model_weight_pct": 6.0},
                    {"symbol": "MU", "model_weight_pct": 4.6},
                ],
            }
        ),
        encoding="utf-8",
    )
    doc = build_r3_t212_daily_prognosis(tmp_path, persist=False)
    assert doc.get("positions") == 2
    tickers = [p["ticker"] for p in doc.get("top_picks") or []]
    assert tickers == ["STX", "MU"]
    assert "SPY" not in tickers


def test_prognosis_king_boost(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_product_roles.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        '{"ok":true,"signal_date":"2026-06-05"}',
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "signal_date": "2026-06-05",
                "allocations": [
                    {"symbol": "STX", "model_weight_pct": 6.0},
                    {"symbol": "MU", "model_weight_pct": 4.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "follow_on_suggestions": [
                    {"symbol": "STX", "worth_follow_on": True, "weight_boost_pct": 1.5},
                ]
            }
        ),
        encoding="utf-8",
    )
    doc = build_r3_t212_daily_prognosis(tmp_path, persist=False)
    stx = next(p for p in doc.get("top_picks") or [] if p.get("ticker") == "STX")
    assert stx.get("king_boost_pct") == 1.5
    assert float(stx.get("target_weight_pct") or 0) == 7.5


def test_prognosis_message_includes_king_operator_summary(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_product_roles.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        '{"ok":true,"signal_date":"2026-06-05","message_de":"Predict bereit."}',
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "signal_date": "2026-06-05",
                "allocations": [{"symbol": "STX", "model_weight_pct": 6.0}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "summary_de": "11 Käufe auf Live-Basis — STX Follow-on prüfen.",
                "operator_hint_de": "Erst Gesamtpaket bestätigen",
            }
        ),
        encoding="utf-8",
    )
    doc = build_r3_t212_daily_prognosis(tmp_path, persist=False)
    msg = str(doc.get("message_de") or "")
    assert "König:" in msg
    assert "STX" in msg or "Gesamtpaket" in msg
