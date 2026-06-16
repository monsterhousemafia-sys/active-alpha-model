"""R3 Quote-Keepalive — frische Kurse."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from analytics.r3_quote_keepalive import assess_quote_freshness, tick_quote_keepalive


def _policy(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "control/r3_quote_keepalive_policy.json").write_text(
        json.dumps({"enabled": True, "min_interval_s": 0, "max_stale_ingest_s": 300}),
        encoding="utf-8",
    )


def test_assess_stale_ingest(tmp_path: Path) -> None:
    _policy(tmp_path)
    (tmp_path / "evidence/r3_browser_ingest_latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "price_current": False,
                "updated_at_utc": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    with patch("analytics.r3_quote_keepalive._us_session_open", return_value=False), patch(
        "market.live_quote_engine.load_live_quote_snapshot", return_value=None
    ):
        assess = assess_quote_freshness(tmp_path)
    assert assess.get("needs_refresh") is True


def test_tick_skips_when_fresh(tmp_path: Path) -> None:
    _policy(tmp_path)
    from datetime import datetime, timezone

    fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "evidence/r3_browser_ingest_latest.json").write_text(
        json.dumps({"ok": True, "price_current": True, "updated_at_utc": fresh, "price_latest": "2026-06-09"}),
        encoding="utf-8",
    )
    with patch("analytics.r3_quote_keepalive.assess_quote_freshness") as assess:
        assess.return_value = {"needs_refresh": False, "headline_de": "Kurse frisch"}
        doc = tick_quote_keepalive(tmp_path, persist=False)
    assert doc.get("skipped") is True
    assert doc.get("reason_de") == "fresh"


def test_tick_runs_reeval_after_live_quotes(tmp_path: Path) -> None:
    _policy(tmp_path)
    (tmp_path / "control/r3_quote_keepalive_policy.json").write_text(
        json.dumps({"enabled": True, "min_interval_s": 0, "max_stale_ingest_s": 300}),
        encoding="utf-8",
    )
    with patch("analytics.r3_quote_keepalive.assess_quote_freshness") as assess, patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True},
    ), patch(
        "analytics.r3_browser_data.ingest_prognosis_data_from_internet",
        return_value={"ok": True, "price_latest": "2026-06-10"},
    ), patch(
        "market.live_quote_engine.ensure_live_quotes_fresh",
        return_value={"freshness": {"status": "FRESH"}},
    ), patch(
        "analytics.pilot_portfolio_reevaluation.run_periodic_reevaluation",
        return_value={"ok": True},
    ) as reeval:
        assess.side_effect = [
            {"needs_refresh": True, "headline_de": "stale"},
            {"needs_refresh": False, "quote_status": "FRESH", "headline_de": "Kurse frisch"},
        ]
        doc = tick_quote_keepalive(tmp_path, persist=False, owner="mirror_poll")
    assert doc.get("skipped") is False
    reeval.assert_called_once()
    assert any(s.get("step") == "reeval" and s.get("ok") for s in doc.get("steps") or [])


def test_refresh_on_mirror_poll_policy_default(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_quote_keepalive_policy.json").write_text(
        json.dumps({"enabled": True, "refresh_on_mirror_poll": True, "min_interval_s": 0}),
        encoding="utf-8",
    )
    from analytics.r3_quote_keepalive import load_quote_keepalive_policy

    pol = load_quote_keepalive_policy(tmp_path)
    assert pol.get("refresh_on_mirror_poll") is True
