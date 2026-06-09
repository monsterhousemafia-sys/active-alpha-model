"""P5 realtime replay foundation — sync status and normalized store."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from aa_intraday_data_quality import IntradayQualityResult, quality_result_to_dict, validate_replay_dataset
from aa_market_data import ReplayMarketDataProvider, default_replay_root, ensure_sample_replay_data
from aa_safe_io import atomic_write_json

STATUS_FILE = "realtime_replay_status.json"
QUALITY_FILE = "intraday_data_quality.json"
NORMALIZED_DIR = "market_data/normalized"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def status_path(root: Path) -> Path:
    return Path(root) / "control" / STATUS_FILE


def out_status_path(out_dir: Path) -> Path:
    return Path(out_dir) / STATUS_FILE


def replay_status_summary(out_dir: Path, root: Optional[Path] = None) -> Dict[str, Any]:
    root = root or Path(out_dir).parent
    for candidate in (out_status_path(out_dir), status_path(root)):
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                return {
                    "realtime_replay_status": str(data.get("provider_status", "NOT_CONFIGURED")),
                    "intraday_data_quality_status": str(data.get("data_quality_status", "NOT_VALIDATED")),
                    "last_processed_at_utc": str(data.get("last_processed_at_utc", "") or ""),
                    "last_bar_timestamp_utc": str(data.get("last_bar_timestamp_utc", "") or ""),
                    "realtime_provider_status": str(data.get("provider_status", "NOT_CONFIGURED")),
                }
            except Exception:
                pass
    return {
        "realtime_replay_status": "NOT_CONFIGURED",
        "intraday_data_quality_status": "NOT_VALIDATED",
        "last_processed_at_utc": "",
        "last_bar_timestamp_utc": "",
        "realtime_provider_status": "NOT_CONFIGURED",
    }


def _atomic_write_parquet(path: Path, frame: pd.DataFrame) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        frame.to_parquet(tmp_path, index=True)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)
    return path


def normalize_replay_bars(root: Path, provider: ReplayMarketDataProvider, tickers: List[str]) -> Path:
    norm_root = Path(root) / NORMALIZED_DIR / "bars_5m"
    norm_root.mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        bars = provider.get_historical_bars(ticker)
        if not bars.empty:
            _atomic_write_parquet(norm_root / f"{ticker.upper()}.parquet", bars)
    return norm_root


def build_realtime_replay_status(
    root: Path,
    *,
    quality: IntradayQualityResult,
    provider: ReplayMarketDataProvider,
    tickers: List[str],
) -> Dict[str, Any]:
    last_bar = ""
    for ticker in tickers:
        bars = provider.get_historical_bars(ticker)
        if not bars.empty:
            ts = bars.index.max()
            last_bar = max(last_bar, ts.isoformat()) if last_bar else ts.isoformat()
    return {
        "updated_at_utc": _utc_now(),
        "provider_status": provider.provider_name(),
        "provider_mode": "REPLAY",
        "live_provider_enabled": False,
        "data_quality_status": quality.status,
        "data_quality_passed": quality.passed,
        "last_processed_at_utc": _utc_now(),
        "last_bar_timestamp_utc": last_bar,
        "tickers_loaded": tickers,
        "spy_available": "SPY" in tickers and not quality.missing_spy,
        "quality_errors": list(quality.errors),
        "quality_warnings": list(quality.warnings),
        "behavioral_features_allowed": quality.passed,
    }


def write_realtime_replay_artifacts(
    root: Path,
    out_dir: Path,
    status: Dict[str, Any],
    quality: IntradayQualityResult,
) -> None:
    root = Path(root)
    out_dir = Path(out_dir)
    ctrl = root / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_status_path(out_dir), status)
    atomic_write_json(status_path(root), status)
    quality_path = root / "market_data" / "quality" / QUALITY_FILE
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(quality_path, quality_result_to_dict(quality))
    atomic_write_json(out_dir / QUALITY_FILE, quality_result_to_dict(quality))


def run_realtime_replay_sync(
    root: Path,
    out_dir: Path,
    *,
    tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Initialize replay provider, validate data quality, write status (no champion changes)."""
    root = Path(root)
    out_dir = Path(out_dir)
    replay_root = ensure_sample_replay_data(root)
    provider = ReplayMarketDataProvider(replay_root)
    tickers = list(tickers or ["SPY", "AAPL"])
    if "SPY" not in [t.upper() for t in tickers]:
        tickers.insert(0, "SPY")

    quality = validate_replay_dataset(provider, tickers=tickers, require_spy=True)
    normalize_replay_bars(root, provider, tickers)
    status = build_realtime_replay_status(root, quality=quality, provider=provider, tickers=tickers)
    write_realtime_replay_artifacts(root, out_dir, status, quality)

    return {
        "status": "OK" if quality.passed else "QUALITY_FAIL",
        "provider_status": status["provider_status"],
        "data_quality_status": quality.status,
        "last_bar_timestamp_utc": status.get("last_bar_timestamp_utc", ""),
        "behavioral_features_allowed": quality.passed,
    }
