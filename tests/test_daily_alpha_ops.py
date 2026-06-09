from pathlib import Path
from unittest.mock import patch

from analytics.daily_alpha_ops import rank_top_picks, run_daily_alpha_ops


def test_rank_top_picks_sorts_by_priority() -> None:
    ww = {
        "worthwhile_buys": [
            {"symbol": "AAA", "priority_score": 5, "side": "BUY"},
            {"symbol": "ZZZ", "priority_score": 42, "side": "BUY", "alpha_lcb": 0.02},
            {"symbol": "MMM", "priority_score": 20, "side": "BUY", "source": "investment_plan"},
        ]
    }
    picks = rank_top_picks(ww, max_picks=5, min_score=8.0)
    assert picks[0]["symbol"] == "ZZZ"
    assert any(p["symbol"] == "MMM" for p in picks)


def test_daily_alpha_ops_pre_us_chain(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/AI_KERNEL.json").write_text(
        '{"flags":{"auto_execute_real_money":false}}', encoding="utf-8"
    )
    (tmp_path / "control/daily_alpha_ops_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/r3_worthwhile_positions_latest.json").write_text(
        '{"worthwhile_buys":[{"symbol":"NVDA","priority_score":25,"side":"BUY"}],'
        '"capital_basis":{"investable_eur":679}}',
        encoding="utf-8",
    )

    kernel_doc = {
        "ok": True,
        "phase": "pre_us",
        "top_pick_count": 1,
        "governance": {"fail_closed": True},
        "steps": [{"id": "capital", "ok": True}],
    }
    with patch("analytics.r3_ops_kernel.run_ops_pipeline", return_value=kernel_doc):
        doc = run_daily_alpha_ops(tmp_path, phase="pre_us", persist=True)

    assert doc.get("phase") == "pre_us"
    assert doc.get("top_pick_count", 0) >= 1
    assert (doc.get("governance") or {}).get("fail_closed") is True
    assert (tmp_path / "evidence/daily_alpha_ops_latest.json").is_file()
