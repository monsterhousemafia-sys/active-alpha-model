#!/usr/bin/env python3
"""Startup/cache diagnostic: imports, cache load paths, pool rebind."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

import active_alpha_model as aam
import aa_features as aaf


def check_imports() -> Tuple[List[str], List[str]]:
    ok: List[str] = []
    bad: List[str] = []
    modules = [
        "numpy",
        "pandas",
        "scipy",
        "sklearn",
        "yfinance",
        "pyarrow",
        "matplotlib",
        "rich",
        "lxml",
        "bs4",
        "pytest",
    ]
    for name in modules:
        try:
            __import__(name)
            ok.append(name)
        except Exception as exc:
            bad.append(f"{name}: {exc}")
    return ok, bad


def test_feature_cache_startup(tmp_path: Path) -> str:
    cfg = aam.BacktestConfig(
        out_dir=str(tmp_path),
        reuse_feature_cache=True,
        write_feature_cache=True,
        membership_mode="off",
        n_jobs="1",
        cpu_cores=1,
    )
    features = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "ticker": ["AAPL", "AAPL"],
            "close": [100.0, 101.0],
        }
    )
    returns = pd.DataFrame(
        {"AAPL": [0.01, 0.02], "SPY": [0.005, 0.006]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )
    aam._save_feature_cache(tmp_path, cfg, 1, features, returns)

    calls: Dict[str, int] = {"backtest_state": 0}

    class TrackSession:
        workers = 1

        def __init__(self, cfg_in: aam.BacktestConfig) -> None:
            self.cfg = cfg_in

        def load_backtest_state(self, feat, ret, dates=None) -> None:
            calls["backtest_state"] += 1
            aam._CTX.features = feat
            aam._CTX.returns = ret

    timings = aam.PhaseTimings()
    timings.start("feature_cache_load")
    loaded, reason = aam._try_load_feature_cache(tmp_path, cfg, 1)
    timings.stop("feature_cache_load")
    if loaded is None:
        return f"FAIL feature cache load: {reason}"
    if timings.as_dict()["sections_seconds"].get("feature_cache_load", 0) < 0:
        return "FAIL feature_cache_load timing"

    feat2, _bench, ret2, from_cache = aam.build_or_load_features(
        cfg,
        ["AAPL"],
        tmp_path,
        pool_session=TrackSession(cfg),
        phase_timings=timings,
    )
    if len(feat2) != 2 or calls["backtest_state"] != 1 or not from_cache:
        return "FAIL build_or_load_features did not bind pool after cache hit"
    if aam._CTX.features is None or len(aam._CTX.features) != 2:
        return "FAIL worker context not bound after cache startup"
    return "OK feature cache startup + pool bind"


def test_price_cache_startup(tmp_path: Path) -> str:
    cfg = aam.BacktestConfig(
        out_dir=str(tmp_path),
        skip_download_if_cached=True,
        write_price_cache=True,
        price_cache_ttl_hours=24,
        membership_mode="off",
    )
    cache_dir = aam.resolve_price_cache_dir(cfg)
    tickers = ["AAPL", "SPY"]
    start = "2020-01-01"
    dates = pd.bdate_range(start, periods=260)
    data = {
        "AAPL": pd.DataFrame({"Close": 100.0, "Volume": 1e6}, index=dates),
        "SPY": pd.DataFrame({"Close": 200.0, "Volume": 2e6}, index=dates),
    }
    aaf._save_price_cache(cache_dir, tickers, start, data)

    loaded = aaf._load_price_cache(cache_dir, tickers, start, 24)
    if loaded is None or set(loaded.keys()) != set(tickers):
        return "FAIL price cache load"

    download_called = {"n": 0}

    import aa_features

    real_yf_download = None

    def guarded_yf_download(*args, **kwargs):
        download_called["n"] += 1
        raise RuntimeError("yfinance download should not run when price cache is valid")

    import yfinance as yf

    real_yf_download = yf.download
    yf.download = guarded_yf_download  # type: ignore[assignment]
    try:
        out = aaf.download_data(tickers, start, None, cfg=cfg, out_dir=tmp_path)
    finally:
        yf.download = real_yf_download  # type: ignore[assignment]

    if download_called["n"] != 0:
        return "FAIL yfinance.download invoked despite valid price cache"
    if len(out) != 2:
        return "FAIL price cache returned incomplete panel"
    return "OK price cache startup (no download)"


def test_existing_out_dir_cache(out_dir: Path) -> str:
    if not out_dir.is_dir():
        return f"SKIP no out_dir at {out_dir}"
    cfg = aam.BacktestConfig(out_dir=str(out_dir), membership_mode="off")
    lines = aam.collect_cache_status_lines(cfg, out_dir, n_tickers=500)
    text = "\n".join(lines)
    if "Cache Status" not in text:
        return "FAIL cache-status output"
    return f"OK cache-status ({len(lines)} lines)"


def main() -> int:
    print("=== Active Alpha Startup/Cache Diagnostic ===")
    ok, bad = check_imports()
    print(f"Imports OK ({len(ok)}): {', '.join(ok)}")
    if bad:
        print("Imports FAIL:")
        for item in bad:
            print(f"  - {item}")
        return 1

    results: List[str] = []
    tmp = ROOT / ".diagnose_cache_tmp"
    if tmp.exists():
        import shutil

        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    for name, fn in [
        ("feature_cache", lambda: test_feature_cache_startup(tmp / "feat")),
        ("price_cache", lambda: test_price_cache_startup(tmp / "price")),
        ("model_output_status", lambda: test_existing_out_dir_cache(ROOT / "model_output")),
    ]:
        try:
            msg = fn()
            results.append(f"{name}: {msg}")
            print(f"[{name}] {msg}")
        except Exception:
            results.append(f"{name}: EXCEPTION")
            print(f"[{name}] EXCEPTION")
            traceback.print_exc()

    import shutil

    shutil.rmtree(tmp, ignore_errors=True)

    failed = [r for r in results if "FAIL" in r or "EXCEPTION" in r]
    if failed:
        print("\nRESULT: FAIL")
        return 1
    print("\nRESULT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
