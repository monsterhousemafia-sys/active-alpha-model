"""Live execution outcome bridge tests."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from aa_prediction_outcomes import load_ledger
from execution.live_learning.live_execution_outcome_bridge import (
    SOURCE_LIVE,
    append_live_executions_from_submitted,
    make_live_prediction_id,
    sync_live_execution_outcomes,
)


def _setup(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/prediction_operations.json").write_text(
        json.dumps({"active_profile": "daily_alpha_h1", "profiles": {"daily_alpha_h1": {"variant_key": "DAILY_ALPHA_H1"}}}),
        encoding="utf-8",
    )
    out = root / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    sig = date.today().isoformat()
    pd.DataFrame(
        [{"ticker": "WDC", "target_weight": 0.05, "mu_hat": 0.001, "alpha_lcb": 0.0005, "signal_date": sig}]
    ).to_csv(out / "latest_target_portfolio.csv", index=False)
    cache = out / "price_cache"
    cache.mkdir(parents=True)
    days = pd.date_range(end=sig, periods=5, freq="D")
    panel = pd.DataFrame(
        {
            "date": days,
            "ticker": ["WDC"] * len(days),
            "close": [100.0, 101.0, 102.0, 103.0, 104.0],
        }
    )
    panel.to_parquet(cache / "ohlcv_panel.parquet", index=False)


def _write_submitted(root: Path, *, filled: bool = True) -> str:
    draft_id = "test-draft-001"
    folder = root / "live_pilot/confirmed_execution/submitted_orders"
    folder.mkdir(parents=True, exist_ok=True)
    resp = {"id": 123, "status": "FILLED" if filled else "NEW", "filledQuantity": 0.01 if filled else 0}
    doc = {
        "draft": {
            "draft_id": draft_id,
            "instrument": "WDC",
            "side": "BUY",
            "limit_price": 100.0,
            "source": "TEST",
        },
        "response": resp,
        "submitted_at_utc": f"{date.today().isoformat()}T12:00:00+00:00",
    }
    (folder / f"{draft_id}.json").write_text(json.dumps(doc), encoding="utf-8")
    return draft_id


def test_make_live_prediction_id_stable() -> None:
    assert make_live_prediction_id(draft_id="abc") == make_live_prediction_id(draft_id="abc")


def test_append_filled_submitted_to_ledger(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_submitted(tmp_path, filled=True)
    n = append_live_executions_from_submitted(tmp_path)
    assert n == 1
    ledger = load_ledger(tmp_path / "model_output_sp500_pit_t212")
    assert len(ledger) == 1
    assert ledger.iloc[0]["source_run_id"] == SOURCE_LIVE
    assert ledger.iloc[0]["status"] == "pending"
    n2 = append_live_executions_from_submitted(tmp_path)
    assert n2 == 0


def test_skip_unfilled_submitted(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_submitted(tmp_path, filled=False)
    assert append_live_executions_from_submitted(tmp_path) == 0


def test_sync_writes_evidence(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_submitted(tmp_path, filled=True)
    report = sync_live_execution_outcomes(tmp_path, refresh_history=False)
    assert report.get("ok") is True
    assert (tmp_path / "evidence/live_execution_outcome_sync_latest.json").is_file()
