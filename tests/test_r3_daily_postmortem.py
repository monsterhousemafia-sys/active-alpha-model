"""Tages-Postmortem — read-only Pick-Returns vs. SPY."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_daily_postmortem import (
    format_postmortem_reply_de,
    run_daily_postmortem,
)


def _write_policy(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_daily_postmortem_policy.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "max_picks": 5,
                "bad_day_underperform_bps": 50,
                "bad_day_portfolio_pct": -0.01,
                "benchmark_ticker": "SPY",
                "exclude_tickers": ["SPY"],
            }
        ),
        encoding="utf-8",
    )


def test_postmortem_bad_day(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    (tmp_path / "control").mkdir(exist_ok=True)
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"signal_date": "2026-06-05", "ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "allocations": [
                    {"symbol": "STX", "model_weight_pct": 60.0},
                    {"symbol": "AMD", "model_weight_pct": 40.0},
                ]
            }
        ),
        encoding="utf-8",
    )

    panel = {
        "ok": True,
        "as_of_date": "2026-06-08",
        "prev_date": "2026-06-05",
        "returns": {
            "SPY": (100.0, 101.0, 0.01),
            "STX": (50.0, 48.0, -0.04),
            "AMD": (100.0, 99.0, -0.01),
        },
    }

    with patch("analytics.r3_daily_postmortem._load_panel_closes", return_value=panel), patch(
        "analytics.r3_daily_postmortem._stale_sync_warning", return_value=None
    ):
        doc = run_daily_postmortem(tmp_path, persist=True)

    assert doc.get("ok") is True
    assert doc.get("bad_day") is True
    assert doc.get("portfolio_return_pct") is not None
    assert (tmp_path / "evidence/r3_daily_postmortem_latest.json").is_file()
    reply = format_postmortem_reply_de(doc)
    assert "STX" in reply
    assert "Schlechter" in reply or "schwach" in reply.lower()


def test_postmortem_stale_sync_voice(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    (tmp_path / "control/prediction_readiness.json").write_text("{}", encoding="utf-8")

    with patch(
        "analytics.r3_daily_postmortem._load_panel_closes",
        return_value={"ok": False, "reason_de": "Panel fehlt"},
    ), patch(
        "analytics.r3_daily_postmortem._stale_sync_warning",
        return_value="Kontostand veraltet — Aktualisieren",
    ):
        doc = run_daily_postmortem(tmp_path, persist=False)

    assert doc.get("voice_warning_de") == "Kontostand veraltet — Aktualisieren"
