"""Internet-Pflicht — R3 und Active Alpha Model."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_background_engine import tick_alpha_model_background
from analytics.r3_desktop_view import load_desktop_status, run_r3_background_refresh
from analytics.r3_internet_requirement import (
    probe_and_record_internet,
    require_internet_for,
)


def test_probe_records_evidence(tmp_path: Path) -> None:
    with patch(
        "analytics.r3_internet_requirement.probe_internet_stack",
        return_value={"internet_ok": True, "price_feed_ok": True, "generic_ok": True, "probes": []},
    ):
        doc = probe_and_record_internet(tmp_path, persist=True)
    assert doc.get("internet_ok") is True
    assert (tmp_path / "evidence/r3_internet_latest.json").is_file()


def test_engine_blocked_without_internet(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/alpha_model_background_engine_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/r3_internet_latest.json").write_text(
        json.dumps({"internet_ok": False, "message_de": "offline"}),
        encoding="utf-8",
    )
    with patch(
        "analytics.prediction_operations.maybe_run_eod_prediction_switch",
        return_value={"ok": True, "skipped": True},
    ), patch(
        "analytics.live_profile_governance.h1_backtest_status",
        return_value={"status": "MISSING"},
    ), patch(
        "analytics.r3_t212_prognosis.build_r3_t212_daily_prognosis",
        return_value={"ok": True},
    ):
        doc = tick_alpha_model_background(tmp_path, force=True)
    predict = next(s for s in doc.get("steps") or [] if s.get("step") == "predict")
    assert predict.get("reason_de") == "internet_required"


def test_background_refresh_stops_when_offline(tmp_path: Path) -> None:
    with patch(
        "analytics.r3_trading_cycle._run_cycle_steps",
        return_value={"ok": False, "steps": [{"id": "internet", "ok": False}]},
    ), patch(
        "analytics.r3_trading_cycle.evaluate_trading_cycle",
        return_value={"closed": False, "runtime_closed": False, "stages": [], "stages_ok": 0, "stages_total": 7},
    ):
        out = run_r3_background_refresh(tmp_path)
    assert out.get("ok") is False


def test_desktop_shows_internet_chip(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/r3_internet_latest.json").write_text(
        json.dumps({"internet_ok": True, "confirmation_de": "✓ Internet OK"}),
        encoding="utf-8",
    )
    status = load_desktop_status(tmp_path)
    labels = [c.get("label_de") for c in status.get("chips") or []]
    assert "Internet" in labels


def test_require_internet_reads_evidence(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    (tmp_path / "evidence").mkdir()
    fresh = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "evidence/r3_internet_latest.json").write_text(
        json.dumps({"internet_ok": True, "updated_at_utc": fresh}),
        encoding="utf-8",
    )
    gate = require_internet_for(tmp_path, consumer="alpha_engine")
    assert gate.get("allowed") is True


def test_require_internet_reprobes_stale_evidence(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/r3_internet_latest.json").write_text(
        json.dumps({"internet_ok": True, "updated_at_utc": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    with patch(
        "analytics.r3_internet_requirement.probe_and_record_internet",
        return_value={"internet_ok": True, "message_de": "refreshed"},
    ) as probe:
        gate = require_internet_for(tmp_path, consumer="alpha_engine")
    assert probe.called
    assert gate.get("allowed") is True
